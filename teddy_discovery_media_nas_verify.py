"""Bounded read-only NAS path verification for one existing image target."""
from __future__ import annotations
import json
import shlex
import subprocess
from pathlib import PurePosixPath
from teddy_discovery_media_filestation import _video_paths

KEY = '/opt/missav-dlp-web/teddy-nas-transfer/id_ed25519'
KNOWN_HOSTS = '/opt/missav-dlp-web/teddy-nas-transfer/known_hosts'
HOST = 'ssikgun@192.168.1.201'
REMOTE = r'''import sys,os,stat,json,pwd,grp,re
root='/volume1/video/video2/JAV'
rel=sys.argv[1]
size=int(sys.argv[2])
parts=rel.split('/')
if not parts or any(not p or p in ('.','..') for p in parts): raise SystemExit(1)
path='/'
for part in (root.strip('/').split('/')+parts[:-1]):
 path=os.path.join(path,part)
 s=os.lstat(path)
 if not stat.S_ISDIR(s.st_mode) or stat.S_ISLNK(s.st_mode): raise SystemExit(2)
file=os.path.join(path,parts[-1]); s=os.lstat(file)
if not stat.S_ISREG(s.st_mode) or stat.S_ISLNK(s.st_mode) or s.st_size!=size: raise SystemExit(3)
pattern=re.compile(r'^(?:'+re.escape(parts[-2])+r'[-_. ])?(?:poster|cover|folder|default|movie)\.(?:jpg|jpeg|png|webp)$',re.I)
primary=False
with os.scandir(path) as entries:
 for entry in entries:
  if pattern.fullmatch(entry.name):
   x=entry.stat(follow_symlinks=False)
   if not stat.S_ISREG(x.st_mode) or stat.S_ISLNK(x.st_mode): raise SystemExit(4)
   primary=True
print(json.dumps({'user':pwd.getpwuid(s.st_uid).pw_name,'group':grp.getgrgid(s.st_gid).gr_name,'size':s.st_size,'primary':primary},separators=(',',':')))
'''

def verify_existing_path(dvd_id, holding, file_station, *, run=subprocess.run):
    """True only when SSH lstat and the existing FileStation view agree."""
    try:
        relative = holding['relative_path']
        size = holding['size_bytes']
        canonical, _, _ = _video_paths(relative, image_only=True)
        if canonical != relative or PurePosixPath(canonical).parent.name != dvd_id or type(size) is not int or size <= 0:
            return False
        remote = 'python3 -c ' + shlex.quote(REMOTE) + ' ' + shlex.quote(canonical) + ' ' + str(size)
        cmd = ['ssh','-T','-i',KEY,'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
               '-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+KNOWN_HOSTS,
               '-o','ConnectTimeout=8',HOST,remote]
        result = run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                     timeout=15, check=False)
        if result.returncode != 0 or len(result.stdout)>4096:
            return False
        data = json.loads(result.stdout)
        if not isinstance(data,dict) or set(data)!={'user','group','size','primary'} or type(data['primary']) is not bool:
            return False
        fs = file_station.stat_library(relative)
        return (isinstance(fs,dict) and type(data['size']) is int and data['size']==size==fs.get('size')
                and isinstance(data['user'],str) and bool(data['user']) and data['user']==fs.get('owner')
                and isinstance(data['group'],str) and bool(data['group']) and data['group']==fs.get('group')
                and file_station.thumbnail_poster_exists(dvd_id=dvd_id,video_relative=relative) is data['primary'])
    except Exception:
        return False
