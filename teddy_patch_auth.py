from pathlib import Path


BOOTSTRAP = Path("teddy_bootstrap.py")


def replace_once(old, new, label):
    text = BOOTSTRAP.read_text(encoding="utf-8")
    count = text.count(old)

    if count != 1:
        raise SystemExit(
            f"auth patch failed: {label}: expected 1 match, got {count}"
        )

    BOOTSTRAP.write_text(
        text.replace(old, new, 1),
        encoding="utf-8",
    )


def main():
    # browser-runtime patch runs before this patch in the Dockerfile.
    replace_once(
        "import teddy_browser_config\n",
        "import teddy_browser_config\nimport teddy_auth\n",
        "auth import",
    )

    # Install auth only after all existing route installers are present.
    replace_once(
        "teddy_proxy_pool.install(core, teddy_routing, teddy_network)\n",
        "teddy_proxy_pool.install(core, teddy_routing, teddy_network)\n"
        "teddy_auth.install(core)\n",
        "auth install",
    )

    print("auth runtime patch: OK")


if __name__ == "__main__":
    main()
