from pathlib import Path
import hashlib

import teddy_patch_mobile


BOOTSTRAP = Path('teddy_bootstrap.py')
FINAL_BOOTSTRAP_SHA256 = 'b96850dbfaa585f5cf2abb3fdbe328030706fc159aba8875656fe2c775e433f3'


def replace_once(old, new, label):
    if hashlib.sha256(BOOTSTRAP.read_bytes()).hexdigest() == FINAL_BOOTSTRAP_SHA256:
        return
    text = BOOTSTRAP.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'browser runtime patch failed: {label}: expected 1 match, got {count}')
    BOOTSTRAP.write_text(text.replace(old, new, 1), encoding='utf-8')


def main():
    replace_once(
        'import teddy_storage\n',
        'import teddy_storage\nimport teddy_browser_config\n',
        'browser config import',
    )
    replace_once(
        'teddy_storage.install_file_routes(core)\n',
        'teddy_storage.install_file_routes(core)\nteddy_browser_config.install(core)\n',
        'browser config route install',
    )
    teddy_patch_mobile.main()
    print('browser runtime config patch: OK')


if __name__ == '__main__':
    main()
