"""Read-only Stage13 library API backed by Discovery holdings."""
from __future__ import annotations

import base64
from contextlib import closing
from datetime import datetime
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, jsonify, request, session

from teddy_discovery_completion_ssh import CompletionSSH
from teddy_discovery_subtitle import validate_canonical_holding, SubtitleCandidate
from teddy_discovery_stage12_inventory import _classify_subtitles
from teddy_discovery_jellyfin import JellyfinClient, jellyfin_media_path
from teddy_discovery_ids import parse_dvd_id
import teddy_storage
from teddy_library_delete_dryrun import (
    DeleteDryRunError, DeleteManifestReader, PrepareTokenRegistry,
    source_identity_fingerprint,
)
from teddy_public_origin import PublicOriginError, parse_origin, parse_public_origin, parse_request_host

LIBRARY_ROOT = "/volume1/video/video2/JAV"
MAX_TITLES = 250
MAX_ENTRIES_PER_TITLE = 512
MAX_ENTRIES_TOTAL = 30000
MAX_DEPTH = 5
MAX_INVENTORY_BYTES = 64 * 1024 * 1024
KST = ZoneInfo("Asia/Seoul")
UNRESOLVED_LABELS = {
    "STAGE12_UNSAFE_AUDIO_TIMELINE": "오디오 타임라인 이상",
    "STAGE12_BASELINE_ASR_NO_SPEECH": "음성 대사 없음",
    "SUBTITLE_INVENTORY_INVALID": "기존 자막 상태 확인 필요",
    "SUBTITLE_DIRECTORY_UNAVAILABLE": "자막 상태 확인 불가",
    "CANONICAL_KO_SRT_UNREADABLE_OR_MALFORMED": "자막 상태 확인 필요",
    "NONCANONICAL_KO_SUBTITLE_PRESENT": "기존 자막 상태 확인 필요",
}


class LibraryError(RuntimeError):
    pass


def _is_canonical_dvd_id(value):
    if not isinstance(value,str) or not value:
        return False
    parsed=parse_dvd_id(value)
    return parsed is not None and parsed.dvd_id==value


def _ro(path: str) -> sqlite3.Connection:
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def _kst_date(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(KST).date().isoformat()
    except (ValueError, TypeError):
        return None


def _holding_rows(db_path, rollout_path, dvd_id=None):
    with closing(_ro(db_path)) as db:
        rows = db.execute("""
            SELECT h.holding_id,h.storage_root,h.relative_path,h.dvd_id,
                   h.parse_status,h.present,h.size_bytes,h.mtime_ns,h.discovered_by,h.first_seen_at,
                   t.title,t.release_date,t.maker,t.cover_url,
                   j.status AS organizer_status,j.destination_path,
                   j.created_at AS organizer_created_at,
                   j.updated_at AS organizer_completed_at
            FROM holdings h
            LEFT JOIN titles t ON t.dvd_id=h.dvd_id
            LEFT JOIN organizer_jobs j ON j.job_id=(
              SELECT j2.job_id FROM organizer_jobs j2
              WHERE j2.dvd_id=h.dvd_id AND j2.status='COMPLETED'
                AND j2.destination_path=h.relative_path
              ORDER BY j2.job_id DESC LIMIT 1
            )
            WHERE h.storage_root='jav' AND h.present=1
              AND (? IS NULL OR h.dvd_id=?)
            ORDER BY h.dvd_id,h.holding_id
        """, (dvd_id,dvd_id)).fetchall()
    terminal = {}
    if rollout_path and Path(rollout_path).is_file():
        try:
            with closing(_ro(rollout_path)) as state:
                terminal = {r["dvd_id"]: dict(r) for r in state.execute(
                    "SELECT dvd_id,status,existing_ko,eligibility,inventory_reason,last_transition_reason FROM stage12_rollout_titles"
                )}
        except sqlite3.Error:
            terminal = {}
    return rows, terminal


def _nas_client_from_env():
    required = ("TEDDY_NAS_HOST", "TEDDY_NAS_USER", "TEDDY_NAS_KEY", "TEDDY_NAS_KNOWN_HOSTS")
    if not all(os.environ.get(k) for k in required):
        return None
    return CompletionSSH(
        host=os.environ["TEDDY_NAS_HOST"], user=os.environ["TEDDY_NAS_USER"],
        key=os.environ["TEDDY_NAS_KEY"], known_hosts=os.environ["TEDDY_NAS_KNOWN_HOSTS"],
        downloads_root="/", library_root=LIBRARY_ROOT,
    )


_INVENTORY_SCRIPT = r'''import base64,json,os,stat,sys
root=os.path.normpath(sys.argv[1]); requested=json.loads(sys.argv[2]); out={}; total=0; subtitle_bytes=0; limit_hit=False
def inside(p):
 r=os.path.realpath(root); q=os.path.realpath(p)
 return os.path.commonpath((r,q))==r
for rel in requested:
 if limit_hit:
  out[rel]={'status':'unknown','error':'global_entry_limit'}
  continue
 if not isinstance(rel,str) or rel.startswith('/') or '..' in rel.split('/'):
  raise SystemExit(3)
 title=os.path.join(root,rel); result={'status':'ok','bytes':0,'ko':None,'subtitle_names':[]}
 try:
  st=os.lstat(title)
  if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode) or not inside(title): raise ValueError('unsafe_title')
  stack=[(title,0)]; seen=0
  while stack:
   current,depth=stack.pop()
   if depth>5: raise ValueError('depth_limit')
   with os.scandir(current) as it:
    for ent in it:
     seen+=1
     if seen>512: raise ValueError('entry_limit')
     if total+seen>30000: raise ValueError('global_entry_limit')
     if ent.name.startswith('.') or ent.name=='@eaDir': continue
     entry_stat=ent.stat(follow_symlinks=False); mode=entry_stat.st_mode
     if stat.S_ISLNK(mode): raise ValueError('symlink')
     if stat.S_ISDIR(mode): stack.append((ent.path,depth+1)); continue
     if not stat.S_ISREG(mode): raise ValueError('unexpected_type')
     size=entry_stat.st_size
     result['bytes']+=size
     if current==title and ent.name.lower().endswith(('.srt','.vtt')):
      result['subtitle_names'].append(ent.name)
     if current==title and ent.name.lower()==(os.path.basename(title)+'.ko.srt').lower():
      if size>8388608: raise ValueError('subtitle_limit')
      if subtitle_bytes+size>16777216: raise ValueError('subtitle_inventory_budget')
      subtitle_bytes+=size
      fd=os.open(ent.path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
      try:
       opened=os.fstat(fd)
       if not stat.S_ISREG(opened.st_mode) or (opened.st_dev,opened.st_ino)!=(entry_stat.st_dev,entry_stat.st_ino): raise ValueError('subtitle_identity_changed')
       with os.fdopen(fd,'rb',closefd=False) as f: result['ko']=base64.b64encode(f.read(8388609)).decode('ascii')
      finally: os.close(fd)
 except FileNotFoundError:
  total+=seen; result={'status':'unknown','error':'missing'}
 except Exception as e:
  total+=seen; result={'status':'unknown','error':str(e)[:64]}
  if str(e)=='global_entry_limit': limit_hit=True
 else:
  total+=seen
 out[rel]=result
print(json.dumps(out,separators=(',',':')))
'''


class NASLibraryReader:
    def __init__(self, ssh): self.ssh = ssh
    def inventory(self, relatives):
        if len(relatives) > MAX_TITLES: raise LibraryError("title bound exceeded")
        raw = self.ssh._run_python(_INVENTORY_SCRIPT, LIBRARY_ROOT, json.dumps(relatives))
        if len(raw.encode("utf-8")) > MAX_INVENTORY_BYTES: raise LibraryError("inventory response bound exceeded")
        value=json.loads(raw)
        if not isinstance(value,dict) or set(value)!=set(relatives): raise LibraryError("inventory response invalid")
        for result in value.values():
            if not isinstance(result,dict) or result.get("status") not in {"ok","unknown"}:
                raise LibraryError("inventory response invalid")
            if result["status"]=="ok":
                size=result.get("bytes")
                if type(size) is not int or size<0 or not isinstance(result.get("subtitle_names"),list):
                    raise LibraryError("inventory response invalid")
                payload=result.get("ko")
                if payload is not None and (not isinstance(payload,str) or len(payload)>((8*1024*1024+2)//3)*4):
                    raise LibraryError("inventory response invalid")
        return value


def _jellyfin_paths():
    url=os.environ.get("TEDDY_JELLYFIN_URL","")
    key=os.environ.get("TEDDY_JELLYFIN_KEY","")
    if not url or not key: raise LibraryError("Jellyfin unavailable")
    client=JellyfinClient(base_url=url,api_key_path=key)
    # One bounded GET inventory, not per-title PlaybackInfo calls.
    response=client._request("GET", "/Items?Recursive=true&Fields=Path&IncludeItemTypes=Movie,Video&StartIndex=0&Limit=10000")
    if not isinstance(response,dict) or not isinstance(response.get("Items"),list): raise LibraryError("Jellyfin inventory invalid")
    total=int(response.get("TotalRecordCount",len(response["Items"])))
    if total>10000: raise LibraryError("Jellyfin inventory bound exceeded")
    if len(response["Items"])!=total: raise LibraryError("Jellyfin inventory is incomplete")
    return {str(item.get("Path")) for item in response["Items"] if isinstance(item,dict) and item.get("Path")}


def _reason(state):
    # Terminal transition reasons usually identify the concrete Stage12
    # failure, while inventory_reason may still describe the generic absence
    # that made the item eligible. Check both fields independently so one
    # generic value cannot hide a specific reason in the other field.
    for field in ("last_transition_reason", "inventory_reason"):
        candidate=str(state.get(field) or "")
        for needle, label in UNRESOLVED_LABELS.items():
            short=needle.removeprefix("STAGE12_")
            if needle in candidate or short in candidate: return needle, label
    if "UNRESOLVED" in str(state.get("status") or ""):
        return "STAGE12_UNRESOLVED", "자막 상태 확인 필요"
    return "SUBTITLE_INVENTORY_UNAVAILABLE", "자막 상태 확인 불가"


def _ko_state(row, video, inventory, terminal):
    if video is None:
        return "INVALID/MISMATCH", None, None
    if inventory.get("status")!="ok":
        return "UNRESOLVED", "SUBTITLE_INVENTORY_UNAVAILABLE", "자막 상태 확인 불가"
    directory=PurePosixPath(video.relative_path).parent.as_posix()
    names=inventory.get("subtitle_names")
    if not isinstance(names,list):
        return "UNRESOLVED", "SUBTITLE_INVENTORY_INVALID", "기존 자막 상태 확인 필요"
    class CachedReader:
        def list_subtitle_candidates(self, canonical_video):
            candidates=[]
            for name in names:
                candidates.append(SubtitleCandidate.sibling_text((PurePosixPath(directory)/name).as_posix()))
            return tuple(candidates)
        def read_subtitle_bytes(self, canonical_video, candidate):
            encoded=inventory.get("ko")
            if candidate.relative_path!=PurePosixPath(directory,Path(video.relative_path).stem+".ko.srt").as_posix() or not encoded:
                raise OSError("validated canonical KO bytes are unavailable")
            return base64.b64decode(encoded,validate=True)
    try:
        classified=_classify_subtitles(row,video,CachedReader())
        status=classified.existing_ko
        reason=str(classified.reason or "")
    except Exception:
        return "UNRESOLVED", "SUBTITLE_INVENTORY_INVALID", "기존 자막 상태 확인 필요"
    if status=="VALID": return "VALID",None,None
    if terminal.get("status")=="UNRESOLVED":
        code,label=_reason(terminal)
        return "UNRESOLVED",code,label
    if status=="ABSENT": return "ABSENT",None,None
    short=reason or "SUBTITLE_INVENTORY_INVALID"
    code,label=_reason({"inventory_reason":short})
    return "UNRESOLVED",code,label


def _build_items(db_path, rollout_path, nas_reader, jellyfin_loader, dvd_id=None):
    rows, terminal = _holding_rows(db_path, rollout_path, dvd_id)
    rows = [dict(r) for r in rows]
    if len(rows)>MAX_TITLES: raise LibraryError("holding count exceeds bound")
    relatives=[]; canonical_by_id={}
    counts={}
    for row in rows:
        if row.get("dvd_id"): counts[row["dvd_id"]]=counts.get(row["dvd_id"],0)+1
    for row in rows:
        dvd=row.get("dvd_id")
        try:
            if counts.get(dvd,0)!=1: raise ValueError()
            if row["parse_status"]!="MATCHED" or not _is_canonical_dvd_id(dvd): raise ValueError()
            video=validate_canonical_holding(row,dvd)
            directory=PurePosixPath(video.relative_path).parent.as_posix()
            relatives.append(directory); canonical_by_id[dvd]=(video,directory)
        except Exception:
            canonical_by_id[dvd]=(None,None)
    inv={}
    if nas_reader and relatives:
        try: inv=nas_reader.inventory(relatives)
        except Exception: inv={}
    try: jf_paths=jellyfin_loader()
    except Exception: jf_paths=None
    items=[]
    for row in rows:
        dvd=row.get("dvd_id"); video,directory=canonical_by_id.get(dvd,(None,None)); state=terminal.get(dvd,{})
        invrow=inv.get(directory,{}) if directory else {}
        mismatch=video is None
        size=invrow.get("bytes") if invrow.get("status")=="ok" else None
        ko,reason_code,reason_label=_ko_state(row,video,invrow,state)
        organizer_ok=(row.get("organizer_status")=="COMPLETED" and video is not None and row.get("destination_path")==video.relative_path)
        created=_kst_date(row.get("organizer_created_at")); completed=_kst_date(row.get("organizer_completed_at"))
        added=created if organizer_ok and created and created==completed else None
        media=video.relative_path if video else None
        jf="UNKNOWN" if jf_paths is None else ("RECOGNIZED" if media and jellyfin_media_path(media) in jf_paths else "ABSENT")
        raw_size_error=str(invrow.get("error") or "")
        size_error={"symlink":"SYMLINK","entry_limit":"ENTRY_LIMIT","depth_limit":"DEPTH_LIMIT","unexpected_type":"UNEXPECTED_TYPE","missing":"MISSING","global_entry_limit":"GLOBAL_ENTRY_LIMIT","subtitle_limit":"SUBTITLE_SIZE_LIMIT","unsafe_title":"UNSAFE_TITLE"}.get(raw_size_error,"REMOTE_OR_INVENTORY_ERROR" if raw_size_error or not nas_reader else ("CANONICAL_PATH_INVALID" if mismatch else "INVENTORY_UNAVAILABLE"))
        items.append({"dvd_id":dvd,"title":row.get("title"),"release_date":row.get("release_date"),"maker":row.get("maker"),"cover_url":row.get("cover_url") or (f"/api/discovery/media/cover/{dvd}" if dvd else None),"managed_relative_path":directory,"media_identity":PurePosixPath(media).name if media else None,"media_relative_path":media,"managed_size_bytes":size,"size_status":"KNOWN" if size is not None else "UNKNOWN","size_error_code":None if size is not None else size_error,"ko_status":ko,"stage12_status":state.get("status"),"unresolved_reason_code":reason_code,"unresolved_label":reason_label,"jellyfin_state":jf,"nas_added_date":added,"nas_added_at":None,"nas_added_date_status":"KNOWN_BOUNDED_DATE" if added else "UNKNOWN","nas_added_date_provenance":"ORGANIZER_COMPLETION_BOUNDED_DATE" if added else None,"mismatch":mismatch})
    return items


def _error(code,message,status): return jsonify({"status":"error","error":{"code":code,"message":message}}),status


def _delete_guard_log_value(value, limit=128):
    """Bound and sanitize a value before putting it in a guard diagnostic."""
    if value is None or value == "":
        return "missing"
    return re.sub(r"[^A-Za-z0-9._:\-\[\],]", "_", str(value)[:limit]) or "missing"


def _delete_origin_log_parts(origin):
    if not origin:
        return "missing", "missing"
    try:
        parsed = urlsplit(origin)
        hostname = parsed.hostname or "missing"
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        port = parsed.port
        host = f"{hostname}:{port}" if port is not None else hostname
        return _delete_guard_log_value(parsed.scheme), _delete_guard_log_value(host)
    except (TypeError, ValueError):
        return "invalid", "invalid"


def create_library_blueprint(db_path, rollout_path="", *, core=None, nas_reader=None, jellyfin_loader=None, stream_response=None, delete_manifest_reader=None, delete_token_registry=None):
    bp=Blueprint("teddy_library_api",__name__,url_prefix="/api/library")
    nas_reader=nas_reader if nas_reader is not None else (NASLibraryReader(_nas_client_from_env()) if _nas_client_from_env() else None)
    jellyfin_loader=jellyfin_loader or _jellyfin_paths
    if delete_manifest_reader is None and nas_reader is not None and hasattr(nas_reader, "ssh"):
        delete_manifest_reader = DeleteManifestReader(nas_reader.ssh, library_root=LIBRARY_ROOT)
    delete_token_registry = delete_token_registry or PrepareTokenRegistry()
    def query_items(): return _build_items(db_path,rollout_path,nas_reader,jellyfin_loader)
    @bp.get("")
    def listing():
        q=request.args.get("q","").strip().casefold(); ko=request.args.get("ko"); unresolved=request.args.get("unresolved"); mismatch=request.args.get("mismatch")
        sort=request.args.get("sort","dvd_id"); order=request.args.get("order","asc")
        if set(request.args)-{"q","ko","unresolved","mismatch","sort","order"} or any(len(request.args.getlist(key))!=1 for key in request.args) or ko not in (None,"present","absent") or unresolved not in (None,"true","false") or mismatch not in (None,"true","false") or sort not in {"nas_added","release_date","dvd_id","title","size","subtitle_status"} or order not in {"asc","desc"}:
            return _error("invalid_request","잘못된 검색 또는 정렬 조건입니다.",400)
        try: all_items=query_items(); items=list(all_items)
        except Exception: return _error("library_unavailable","라이브러리를 읽을 수 없습니다.",503)
        if q: items=[x for x in items if q in str(x.get("dvd_id") or "").casefold() or q in str(x.get("title") or "").casefold()]
        if ko: items=[x for x in items if x["ko_status"]==( "VALID" if ko=="present" else "ABSENT")]
        if unresolved is not None: items=[x for x in items if (x["ko_status"]=="UNRESOLVED")== (unresolved=="true")]
        if mismatch is not None: items=[x for x in items if x["mismatch"]== (mismatch=="true")]
        key={"nas_added":lambda x:x["nas_added_date"] or "","release_date":lambda x:x.get("release_date") or "","dvd_id":lambda x:x.get("dvd_id") or "","title":lambda x:(x.get("title") or "").casefold(),"size":lambda x:x["managed_size_bytes"] if x["managed_size_bytes"] is not None else -1,"subtitle_status":lambda x:x["ko_status"]}[sort]
        if sort=="nas_added":
            dated=[x for x in items if x["nas_added_date"] is not None]
            unknown=[x for x in items if x["nas_added_date"] is None]
            dated.sort(key=key,reverse=order=="desc")
            items=dated+unknown
        else:
            items.sort(key=key,reverse=order=="desc")
        known=[x["managed_size_bytes"] for x in all_items if x["managed_size_bytes"] is not None]
        summary={"total_titles":len(all_items),"ko_present_count":sum(x["ko_status"]=="VALID" for x in all_items),"unresolved_count":sum(x["ko_status"]=="UNRESOLVED" for x in all_items),"no_subtitle_count":sum(x["ko_status"]=="ABSENT" for x in all_items),"mismatch_count":sum(x["mismatch"] for x in all_items),"library_known_total_bytes":sum(known),"size_complete":len(known)==len(all_items),"size_unknown_count":len(all_items)-len(known)}
        return jsonify({"summary":summary,"items":items,"query":{"q":q,"ko":ko,"unresolved":unresolved,"mismatch":mismatch,"sort":sort,"order":order}})
    @bp.get("/<dvd_id>")
    def detail(dvd_id):
        if not _is_canonical_dvd_id(dvd_id): return _error("invalid_dvd_id","DVD-ID 형식이 잘못되었습니다.",400)
        try: items=_build_items(db_path,rollout_path,nas_reader,jellyfin_loader,dvd_id)
        except Exception: return _error("library_unavailable","라이브러리를 읽을 수 없습니다.",503)
        item=next((x for x in items if x["dvd_id"]==dvd_id),None)
        return (jsonify({"item":item}),200) if item else _error("not_found","보유 작품을 찾을 수 없습니다.",404)
    @bp.get("/<dvd_id>/stream")
    def stream(dvd_id):
        if not _is_canonical_dvd_id(dvd_id): return _error("invalid_dvd_id","DVD-ID 형식이 잘못되었습니다.",400)
        try: rows,_=_holding_rows(db_path,rollout_path,dvd_id)
        except Exception: return _error("library_unavailable","라이브러리를 읽을 수 없습니다.",503)
        matches=[dict(row) for row in rows if row["dvd_id"]==dvd_id]
        if not matches: return _error("not_found","보유 작품을 찾을 수 없습니다.",404)
        if len(matches)!=1: return _error("canonical_path_unavailable","정식 재생 경로를 확인할 수 없습니다.",409)
        try: video=validate_canonical_holding(matches[0],dvd_id)
        except Exception: return _error("canonical_path_unavailable","정식 재생 경로를 확인할 수 없습니다.",409)
        media_path=video.relative_path
        if stream_response: return stream_response(media_path)
        if core is None: return _error("playback_unavailable","재생 기능을 사용할 수 없습니다.",503)
        return teddy_storage.library_stream_response(core, media_path)

    def delete_intent_guard(intent):
        if session.get("teddy_authenticated") is not True:
            return _error("authentication_required", "인증이 필요합니다.", 401)
        origin = request.headers.get("Origin")
        sec_fetch_site = request.headers.get("Sec-Fetch-Site", "same-origin")

        def log_rejection(code, subreason):
            origin_scheme, origin_host = _delete_origin_log_parts(origin)
            current_app.logger.warning(
                "library_delete_guard reject=%s subreason=%s intent=%s method=%s "
                "mimetype=%s request_scheme=%s request_host=%s origin_scheme=%s "
                "origin_host=%s x_forwarded_proto=%s x_forwarded_host=%s "
                "sec_fetch_site=%s delete_intent=%s",
                code, subreason, _delete_guard_log_value(intent, 16),
                _delete_guard_log_value(request.method, 16),
                _delete_guard_log_value(request.mimetype, 48),
                _delete_guard_log_value(request.scheme, 16),
                _delete_guard_log_value(request.host), origin_scheme, origin_host,
                _delete_guard_log_value(request.headers.get("X-Forwarded-Proto")),
                _delete_guard_log_value(request.headers.get("X-Forwarded-Host")),
                _delete_guard_log_value(sec_fetch_site, 32),
                _delete_guard_log_value(request.headers.get("X-Teddy-Delete-Intent"), 32),
            )

        if request.mimetype != "application/json":
            log_rejection("invalid_request_boundary", "mimetype")
            return _error("invalid_request_boundary", "요청을 확인할 수 없습니다.", 403)
        if request.headers.get("X-Teddy-Delete-Intent") != intent:
            log_rejection("invalid_request_boundary", "intent_header")
            return _error("invalid_request_boundary", "요청을 확인할 수 없습니다.", 403)
        # Compare against centrally configured public origin. request.scheme can
        # describe the private HTTP hop behind TLS termination and is not trusted.
        origin_subreason = None
        try:
            expected = parse_public_origin(os.environ.get("TEDDY_PUBLIC_ORIGIN"))
        except PublicOriginError as exc:
            origin_subreason = exc.reason
            expected = None
        if origin_subreason is None and not origin:
            origin_subreason = "origin_missing"
        if origin_subreason is None:
            try:
                supplied = parse_origin(origin)
            except PublicOriginError as exc:
                origin_subreason = "origin_invalid"
            if origin_subreason is None:
                try:
                    actual_host = parse_request_host(request.host, scheme=expected.scheme)
                except PublicOriginError:
                    origin_subreason = "host_mismatch"
            if origin_subreason is None:
                if supplied.scheme != expected.scheme:
                    origin_subreason = "scheme_mismatch"
                elif (supplied.hostname, supplied.effective_port) != (expected.hostname, expected.effective_port):
                    origin_subreason = "host_mismatch"
                elif (actual_host.hostname, actual_host.effective_port) != (expected.hostname, expected.effective_port):
                    origin_subreason = "host_mismatch"
        if origin_subreason is None and sec_fetch_site == "cross-site":
            origin_subreason = "cross_site"
        if origin_subreason:
            log_rejection("invalid_request_origin", origin_subreason)
            return _error("invalid_request_origin", "요청 출처를 확인할 수 없습니다.", 403)
        return None

    def current_delete_identity(dvd_id):
        rows, terminal = _holding_rows(db_path, rollout_path, dvd_id)
        matches = [dict(row) for row in rows if row["dvd_id"] == dvd_id]
        if not matches:
            raise DeleteDryRunError("HOLDING_NOT_FOUND", 404)
        if len(matches) != 1:
            raise DeleteDryRunError("DUPLICATE_HOLDING")
        row = matches[0]
        if (row.get("storage_root") != "jav" or row.get("present") != 1
                or row.get("parse_status") != "MATCHED"):
            raise DeleteDryRunError("HOLDING_IDENTITY_MISMATCH")
        try:
            video = validate_canonical_holding(row, dvd_id)
        except Exception as exc:
            raise DeleteDryRunError("CANONICAL_PATH_MISMATCH") from exc
        if row.get("relative_path") != video.relative_path:
            raise DeleteDryRunError("CANONICAL_PATH_MISMATCH")
        return row, video, terminal.get(dvd_id, {})

    def current_delete_snapshot(dvd_id):
        if delete_manifest_reader is None:
            raise DeleteDryRunError("NAS_INSPECTION_UNAVAILABLE", 503)
        row, video, terminal = current_delete_identity(dvd_id)
        manifest = delete_manifest_reader.inspect(video, row)
        inventory = {"status": "ok", "bytes": manifest["total_bytes"],
                     "subtitle_names": manifest["subtitle_names"], "ko": manifest.get("ko")}
        ko_state, reason_code, reason_label = _ko_state(row, video, inventory, terminal)
        try:
            jellyfin = jellyfin_loader()
            jellyfin_state = ("RECOGNIZED" if jellyfin_media_path(video.relative_path) in jellyfin
                              else "ABSENT")
        except Exception:
            jellyfin_state = "UNKNOWN"
        source_fingerprint = source_identity_fingerprint(row, video.relative_path)
        return row, video, manifest, source_fingerprint, {
            "ko_state": ko_state, "unresolved_reason_code": reason_code,
            "unresolved_label": reason_label, "jellyfin_state": jellyfin_state,
        }

    @bp.post("/<dvd_id>/delete/prepare")
    def delete_prepare(dvd_id):
        guard = delete_intent_guard("prepare")
        if guard is not None: return guard
        if not _is_canonical_dvd_id(dvd_id):
            return _error("invalid_dvd_id", "DVD-ID 형식이 잘못되었습니다.", 400)
        body = request.get_json(silent=True)
        if body not in ({}, None):
            return _error("invalid_request", "요청 형식이 잘못되었습니다.", 400)
        try:
            row, video, manifest, fingerprint, states = current_delete_snapshot(dvd_id)
            token, expires_at = delete_token_registry.issue(
                dvd_id=dvd_id, manifest_sha256=manifest["manifest_sha256"],
                source_fingerprint=fingerprint,
            )
        except DeleteDryRunError as exc:
            return _error(exc.code.lower(), "삭제 준비 정보를 안전하게 확인하지 못했습니다.", exc.status)
        except Exception as exc:
            detail = str(exc)[:120] if isinstance(exc, AttributeError) else "internal"
            current_app.logger.warning("Library delete prepare failed (%s: %s)", type(exc).__name__, detail)
            return _error("prepare_unavailable", "삭제 준비 정보를 안전하게 확인하지 못했습니다.", 503)
        return jsonify({
            "status": "PREPARED", "dvd_id": dvd_id, "title": row.get("title"),
            "file_count": len(manifest["entries"]), "total_bytes": manifest["total_bytes"],
            "files": [entry["relative_name"] for entry in manifest["entries"]],
            "manifest_sha256": manifest["manifest_sha256"],
            "ko_state": states["ko_state"], "unresolved_reason_code": states["unresolved_reason_code"],
            "unresolved_label": states["unresolved_label"], "jellyfin_state": states["jellyfin_state"],
            "prepare_expires_at": expires_at, "prepare_token": token,
            "actual_delete_performed": False,
        })

    @bp.post("/<dvd_id>/delete/validate")
    def delete_validate(dvd_id):
        guard = delete_intent_guard("validate")
        if guard is not None: return guard
        if not _is_canonical_dvd_id(dvd_id):
            return _error("invalid_dvd_id", "DVD-ID 형식이 잘못되었습니다.", 400)
        body = request.get_json(silent=True)
        if (not isinstance(body, dict) or set(body) != {"prepare_token", "typed_dvd_id", "acknowledge"}
                or not isinstance(body.get("prepare_token"), str)
                or not (20 <= len(body["prepare_token"]) <= 256)
                or body.get("typed_dvd_id") != dvd_id
                or body.get("acknowledge") is not True):
            code = "WRONG_TYPED_DVD_ID" if isinstance(body, dict) and body.get("typed_dvd_id") != dvd_id else "ACKNOWLEDGEMENT_REQUIRED"
            return _error(code.lower(), "DVD-ID 입력과 영구 삭제 확인이 필요합니다.", 400)
        try:
            delete_token_registry.precheck(body["prepare_token"], dvd_id=dvd_id)
            row, video, manifest, fingerprint, _states = current_delete_snapshot(dvd_id)
            validated_at = delete_token_registry.validate(
                body["prepare_token"], dvd_id=dvd_id,
                manifest_sha256=manifest["manifest_sha256"], source_fingerprint=fingerprint,
            )
        except DeleteDryRunError as exc:
            if exc.code in {"CANONICAL_MEDIA_IDENTITY_MISMATCH", "CANONICAL_MEDIA_MISSING"}:
                return _error("manifest_changed", "준비 후 작품 파일이 변경되었습니다. 다시 준비해 주세요.", 409)
            return _error(exc.code.lower(), "삭제 준비 상태가 유효하지 않습니다. 다시 준비해 주세요.", exc.status)
        except Exception as exc:
            current_app.logger.warning("Library delete validation failed (%s)", type(exc).__name__)
            return _error("validation_unavailable", "삭제 준비 상태를 다시 확인할 수 없습니다.", 503)
        return jsonify({"status": "READY_FOR_COMMIT", "dvd_id": dvd_id,
                        "manifest_sha256": manifest["manifest_sha256"],
                        "validated_at": validated_at, "actual_delete_performed": False,
                        "message": "삭제 준비 검증 완료 · 실제 삭제는 아직 비활성"})
    return bp
