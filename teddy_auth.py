import hmac
import ipaddress
import os
from datetime import timedelta
from urllib.parse import urlparse

from flask import (
    jsonify,
    redirect,
    render_template_string,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash


DEFAULT_AUTH_DIR = "/run/secrets/teddy-auth"
DEFAULT_COOKIE_DOMAIN = ".ssikgun.com"
DEFAULT_INTERNAL_HOST = "missav-dlp-web:5000"
DEFAULT_INTERNAL_NET = "172.18.0.0/16"

ALLOWED_NEXT_HOSTS = {
    "downloader.ssikgun.com",
    "browser.ssikgun.com",
    "mobile-browser.ssikgun.com",
    "selkies-mobile-test.ssikgun.com",
}

LOGIN_HTML = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Teddy Downloader 로그인</title>
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0;
    min-height: 100vh;
    min-height: 100dvh;
    display: grid;
    place-items: center;
    padding: 24px;
    background: #0f172a;
    color: #e2e8f0;
    font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  }
  .card {
    width: min(100%, 390px);
    padding: 28px;
    border: 1px solid #334155;
    border-radius: 18px;
    background: #111827;
    box-shadow: 0 24px 70px rgba(0,0,0,.35);
  }
  h1 { margin: 0 0 8px; font-size: 24px; }
  p { margin: 0 0 22px; color: #94a3b8; font-size: 14px; }
  label { display: block; margin: 14px 0 7px; font-size: 13px; font-weight: 700; }
  input {
    width: 100%;
    min-height: 46px;
    padding: 10px 12px;
    border: 1px solid #475569;
    border-radius: 10px;
    background: #020617;
    color: #f8fafc;
    font-size: 16px;
  }
  button {
    width: 100%;
    min-height: 48px;
    margin-top: 20px;
    border: 0;
    border-radius: 10px;
    background: #2563eb;
    color: white;
    font-size: 16px;
    font-weight: 800;
    cursor: pointer;
  }
  .error {
    margin-top: 14px;
    padding: 10px 12px;
    border-radius: 9px;
    background: #450a0a;
    color: #fecaca;
    font-size: 13px;
  }
</style>
</head>
<body>
  <main class="card">
    <h1>🐻 Teddy Downloader</h1>
    <p>계속하려면 로그인하세요.</p>

    <form method="post" action="{{ url_for('teddy_auth_login') }}">
      <input type="hidden" name="next" value="{{ next_url }}">

      <label for="username">사용자 이름</label>
      <input
        id="username"
        name="username"
        autocomplete="username"
        autocapitalize="none"
        required
      >

      <label for="password">비밀번호</label>
      <input
        id="password"
        name="password"
        type="password"
        autocomplete="current-password"
        required
      >

      <button type="submit">로그인</button>
    </form>

    {% if error %}
    <div class="error">{{ error }}</div>
    {% endif %}
  </main>
</body>
</html>
"""


def _read_required(path):
    with open(path, "r", encoding="utf-8") as handle:
        value = handle.read().strip()
    if not value:
        raise RuntimeError(f"empty auth secret: {path}")
    return value


def _safe_next(value):
    raw = str(value or "").strip()

    if not raw:
        return "/"

    if raw.startswith("/") and not raw.startswith("//"):
        return raw

    try:
        parsed = urlparse(raw)
    except ValueError:
        return "/"

    if (
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.hostname.lower() in ALLOWED_NEXT_HOSTS
    ):
        return raw

    return "/"


def _authenticated():
    return session.get("teddy_authenticated") is True


def _internal_extension_download(req, internal_network, internal_host):
    if req.method != "POST" or req.path != "/download":
        return False

    if str(req.host or "").lower() != internal_host.lower():
        return False

    # Requests passing through NPM/Cloudflare carry forwarding metadata.
    # The browser extension's Docker-internal request does not.
    forwarded_headers = (
        "X-Forwarded-For",
        "X-Forwarded-Host",
        "X-Forwarded-Proto",
        "X-Real-IP",
        "CF-Connecting-IP",
    )
    if any(req.headers.get(name) for name in forwarded_headers):
        return False

    try:
        remote = ipaddress.ip_address(req.remote_addr or "")
    except ValueError:
        return False

    return remote in internal_network


def install(core):
    app = core.app

    auth_dir = os.environ.get("TEDDY_AUTH_DIR", DEFAULT_AUTH_DIR)
    cookie_domain = os.environ.get(
        "TEDDY_AUTH_COOKIE_DOMAIN",
        DEFAULT_COOKIE_DOMAIN,
    ).strip()
    internal_host = os.environ.get(
        "TEDDY_INTERNAL_DOWNLOAD_HOST",
        DEFAULT_INTERNAL_HOST,
    ).strip()
    internal_net_raw = os.environ.get(
        "TEDDY_INTERNAL_DOWNLOAD_NET",
        DEFAULT_INTERNAL_NET,
    ).strip()

    username = _read_required(os.path.join(auth_dir, "username"))
    password_hash = _read_required(os.path.join(auth_dir, "password_hash"))
    session_secret = _read_required(os.path.join(auth_dir, "session_secret"))

    internal_network = ipaddress.ip_network(internal_net_raw, strict=False)

    app.secret_key = session_secret
    app.config.update(
        SESSION_COOKIE_NAME="teddy_auth",
        SESSION_COOKIE_DOMAIN=cookie_domain,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_REFRESH_EACH_REQUEST=True,
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )

    @app.route("/login", methods=["GET", "POST"], endpoint="teddy_auth_login")
    def login():
        next_url = _safe_next(
            request.form.get("next")
            if request.method == "POST"
            else request.args.get("next")
        )

        if request.method == "GET":
            if _authenticated():
                return redirect(next_url, code=302)

            response = app.make_response(
                render_template_string(
                    LOGIN_HTML,
                    error="",
                    next_url=next_url,
                )
            )
            response.headers["Cache-Control"] = "no-store"
            return response

        supplied_user = request.form.get("username", "")
        supplied_password = request.form.get("password", "")

        user_ok = hmac.compare_digest(str(supplied_user), username)
        password_ok = check_password_hash(password_hash, supplied_password)

        if not (user_ok and password_ok):
            response = app.make_response((
                render_template_string(
                    LOGIN_HTML,
                    error="사용자 이름 또는 비밀번호가 올바르지 않습니다.",
                    next_url=next_url,
                ),
                401,
            ))
            response.headers["Cache-Control"] = "no-store"
            return response

        session.clear()
        session["teddy_authenticated"] = True
        session["teddy_user"] = username
        session.permanent = True

        response = redirect(next_url, code=302)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.route(
        "/logout",
        methods=["GET", "POST"],
        endpoint="teddy_auth_logout",
    )
    def logout():
        session.clear()
        response = redirect(url_for("teddy_auth_login"), code=302)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.route(
        "/auth/check",
        methods=["GET"],
        endpoint="teddy_auth_check",
    )
    def auth_check():
        if not _authenticated():
            response = app.make_response(("", 401))
            response.headers["Cache-Control"] = "no-store"
            return response

        response = app.make_response(("", 204))
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.before_request
    def teddy_auth_guard():
        endpoint = request.endpoint or ""

        if endpoint in {
            "teddy_auth_login",
            "teddy_auth_logout",
            "teddy_auth_check",
            "static",
        }:
            return None

        if _internal_extension_download(
            request,
            internal_network,
            internal_host,
        ):
            return None

        if _authenticated():
            return None

        if request.path.startswith("/api/") or request.path == "/download":
            response = jsonify(
                {
                    "status": "error",
                    "message": "authentication required",
                }
            )
            response.status_code = 401
            response.headers["Cache-Control"] = "no-store"
            return response

        if request.method in {"GET", "HEAD"}:
            next_url = _safe_next(request.url)
            return redirect(
                url_for("teddy_auth_login", next=next_url),
                code=302,
            )

        response = jsonify(
            {
                "status": "error",
                "message": "authentication required",
            }
        )
        response.status_code = 401
        response.headers["Cache-Control"] = "no-store"
        return response
