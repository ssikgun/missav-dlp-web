from pathlib import Path


def require(value, name):
    if not value:
        raise AssertionError(name)


def main():
    template = Path(
        "templates/index.html"
    ).read_text(encoding="utf-8")
    script = Path(
        "templates/teddy-subtitle-status.js"
    ).read_text(encoding="utf-8")
    css = Path(
        "templates/teddy-subtitle-status.css"
    ).read_text(encoding="utf-8")
    backend = Path(
        "teddy_subtitle_status.py"
    ).read_text(encoding="utf-8")

    for token in (
        'id="subtitle-status-panel"',
        'id="subtitle-status-badge"',
        'id="subtitle-count-published"',
        'id="subtitle-count-pending"',
        'id="subtitle-count-retryable"',
        'id="subtitle-count-terminal"',
        'id="subtitle-count-unresolved"',
    ):
        require(token in template, token)

    require(
        "/api/subtitles/status" in backend,
        "STATUS_API",
    )
    require(
        "mode=ro" in backend,
        "READ_ONLY_SQLITE",
    )
    require(
        "/api/subtitles/status" in script,
        "STATUS_UI_FETCH",
    )
    require(
        "setInterval" in script,
        "STATUS_UI_POLL",
    )
    require(
        ".subtitle-status-panel" in css,
        "STATUS_UI_STYLE",
    )

    panel = template.split(
        'id="subtitle-status-panel"',
        1,
    )[1].split("</section>", 1)[0]

    require(
        "<button" not in panel,
        "STATUS_PANEL_READ_ONLY",
    )

    print("SUBTITLE_STATUS_UI_SMOKE=PASS")


if __name__ == "__main__":
    main()
