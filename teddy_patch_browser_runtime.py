from pathlib import Path


BOOTSTRAP = Path('teddy_bootstrap.py')


def replace_once(old, new, label):
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
    print('browser runtime config patch: OK')


if __name__ == '__main__':
    main()
