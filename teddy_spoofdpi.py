"""Bounded diagnostics for the existing SpoofDPI startup attempt."""

import re
import subprocess
import threading


MAX_CAPTURE_BYTES = 4096
MAX_LOG_CHARS = 600
_URL_RE = re.compile(r"\b(?:https?|socks(?:4|5)?)://[^\s\]\[<>\"']+", re.IGNORECASE)
_IP_RE = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
_IPV6_RE = re.compile(r"(?i)(?<![\w:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?![\w:])")
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[^\s,;]+")
_USERINFO_RE = re.compile(r"(?<![\w])[^\s/@:]+:[^\s/@]+@")
_SECRET_RE = re.compile(
    r"(?i)\b(?:token|access[_-]?token|cookie|password|passwd|secret|authorization|"
    r"proxy(?:[_-]?(?:auth|url|server|address|host|user|password))?)\b\s*[:=]\s*[^\s,;]+"
)


def redact_diagnostic(value):
    text = "".join(
        char if char >= " " and char != "\x7f" else " "
        for char in str(value or "")
    )
    text = _URL_RE.sub("[url-redacted]", text)
    text = _SECRET_RE.sub("[credential-redacted]", text)
    text = _BEARER_RE.sub("[bearer-redacted]", text)
    text = _USERINFO_RE.sub("[userinfo-redacted]@", text)
    text = _IPV6_RE.sub("[ip-redacted]", text)
    text = _IP_RE.sub("[ip-redacted]", text)
    return text[:MAX_LOG_CHARS]


class _BoundedDrain:
    """Drain continuously to prevent a child pipe from blocking; retain a cap."""

    def __init__(self, stream, limit=MAX_CAPTURE_BYTES):
        self.stream = stream
        self.limit = limit
        self.data = bytearray()
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        try:
            while True:
                chunk = self.stream.read(1024)
                if not chunk:
                    return
                remaining = self.limit - len(self.data)
                if remaining > 0:
                    with self.lock:
                        self.data.extend(chunk[:remaining])
        except Exception:
            return

    def text(self):
        with self.lock:
            value = bytes(self.data)
        return value.decode("utf-8", errors="replace")


def start_spoofdpi(popen, sleep, port, log):
    """Preserve the original argv and two-second readiness observation window."""
    try:
        proc = popen(["spoofdpi"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except FileNotFoundError:
        log("[System] SpoofDPI 진단: 바이너리를 찾을 수 없습니다 (FileNotFoundError).")
        return None
    except PermissionError as exc:
        log(f"[System] SpoofDPI 진단: 실행 권한 오류 ({type(exc).__name__}, errno={exc.errno}).")
        return None
    except OSError as exc:
        log(f"[System] SpoofDPI 진단: 프로세스 시작 오류 ({type(exc).__name__}, errno={exc.errno}).")
        return None

    capture = _BoundedDrain(proc.stdout) if proc.stdout is not None else None
    sleep(2)
    code = proc.poll()
    if code is None:
        log(f"[System] SpoofDPI 엔진 가동 성공 (Port: {port})")
        return proc

    if capture is not None:
        capture.thread.join(timeout=0.2)
        message = redact_diagnostic(capture.text())
    else:
        message = ""
    detail = f" exit_code={code}"
    if message:
        detail += f" output={message}"
    log(f"[System] SpoofDPI 조기 종료 진단:{detail}")
    return proc
