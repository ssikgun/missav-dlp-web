import base64
import struct
from pathlib import Path


INDEX = Path("templates/index.html")
TOUCH_ICON_SOURCE = Path("pwa/teddy-icon-180.png.b64")
TOUCH_ICON_DEST = Path("templates/teddy-icon-180.png")
MANIFEST = Path("templates/teddy-manifest.webmanifest")
VECTOR_ICON = Path("templates/teddy-icon.svg")

PWA_HEAD = """    <link rel=\"manifest\" href=\"/static/teddy-manifest.webmanifest\">\n    <link rel=\"icon\" href=\"/static/teddy-icon.svg\" type=\"image/svg+xml\">\n    <link rel=\"apple-touch-icon\" sizes=\"180x180\" href=\"/static/teddy-icon-180.png\">\n    <meta name=\"application-name\" content=\"Teddy Downloader\">\n    <meta name=\"mobile-web-app-capable\" content=\"yes\">\n    <meta name=\"apple-mobile-web-app-capable\" content=\"yes\">\n    <meta name=\"apple-mobile-web-app-title\" content=\"Teddy\">\n    <meta name=\"apple-mobile-web-app-status-bar-style\" content=\"default\">\n    <meta name=\"theme-color\" content=\"#0b74f1\" media=\"(prefers-color-scheme: light)\">\n    <meta name=\"theme-color\" content=\"#0f172a\" media=\"(prefers-color-scheme: dark)\">\n"""


def build_touch_icon():
    encoded = TOUCH_ICON_SOURCE.read_text(encoding="ascii").strip()
    try:
        payload = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise SystemExit(f"PWA touch icon base64 decode failed: {exc}") from exc

    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise SystemExit("PWA touch icon is not a PNG")
    if len(payload) < 24:
        raise SystemExit("PWA touch icon PNG is truncated")

    width, height = struct.unpack(">II", payload[16:24])
    if (width, height) != (180, 180):
        raise SystemExit(
            f"PWA touch icon dimensions must be 180x180, got {width}x{height}"
        )

    TOUCH_ICON_DEST.write_bytes(payload)


def inject_head_metadata():
    text = INDEX.read_text(encoding="utf-8")
    manifest_marker = 'rel="manifest" href="/static/teddy-manifest.webmanifest"'

    if manifest_marker not in text:
        count = text.count("</head>")
        if count != 1:
            raise SystemExit(f"PWA patch failed: </head> anchor count={count}")
        text = text.replace("</head>", PWA_HEAD + "</head>", 1)
        INDEX.write_text(text, encoding="utf-8")


def verify():
    rendered = INDEX.read_text(encoding="utf-8")
    required = (
        'rel="manifest" href="/static/teddy-manifest.webmanifest"',
        'rel="icon" href="/static/teddy-icon.svg"',
        'rel="apple-touch-icon" sizes="180x180" href="/static/teddy-icon-180.png"',
        'name="mobile-web-app-capable" content="yes"',
        'name="apple-mobile-web-app-capable" content="yes"',
        'name="apple-mobile-web-app-title" content="Teddy"',
        'name="theme-color" content="#0b74f1" media="(prefers-color-scheme: light)"',
        'name="theme-color" content="#0f172a" media="(prefers-color-scheme: dark)"',
    )
    missing = [marker for marker in required if marker not in rendered]
    if missing:
        raise SystemExit(f"PWA patch verification failed: {missing}")

    for path in (MANIFEST, VECTOR_ICON, TOUCH_ICON_DEST):
        if not path.is_file() or path.stat().st_size == 0:
            raise SystemExit(f"PWA asset missing or empty: {path}")

    if "serviceWorker" in rendered or "service-worker" in rendered:
        raise SystemExit("PWA phase 1 must not register a service worker")


def main():
    build_touch_icon()
    inject_head_metadata()
    verify()
    print("PWA phase 1 patch: OK")


if __name__ == "__main__":
    main()
