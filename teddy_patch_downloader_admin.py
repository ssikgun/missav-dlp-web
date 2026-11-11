from pathlib import Path
import hashlib


BOOTSTRAP = Path("teddy_bootstrap.py")
FINAL_BOOTSTRAP_SHA256 = 'b96850dbfaa585f5cf2abb3fdbe328030706fc159aba8875656fe2c775e433f3'
BOOTSTRAP_IS_FINAL = hashlib.sha256(BOOTSTRAP.read_bytes()).hexdigest() == FINAL_BOOTSTRAP_SHA256
text = BOOTSTRAP.read_text(encoding="utf-8")


def replace_once(old, new, label):
    global text
    if BOOTSTRAP_IS_FINAL:
        return
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
if not BOOTSTRAP_IS_FINAL:
    BOOTSTRAP.write_text(text, encoding="utf-8")
print("downloader admin runtime patch: OK")
