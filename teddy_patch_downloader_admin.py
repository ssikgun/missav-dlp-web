from pathlib import Path


BOOTSTRAP = Path("teddy_bootstrap.py")
text = BOOTSTRAP.read_text(encoding="utf-8")


def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"downloader admin patch failed: {label}: expected 1 match, got {count}")
    text = text.replace(old, new, 1)


replace_once(
    "import teddy_auth\n",
    "import teddy_auth\nimport teddy_downloader_admin\n",
    "admin import",
)
replace_once(
    "teddy_auth.install(core)\n",
    "teddy_auth.install(core)\nteddy_downloader_admin.install(core)\n",
    "admin install after authentication",
)
BOOTSTRAP.write_text(text, encoding="utf-8")
print("downloader admin runtime patch: OK")
