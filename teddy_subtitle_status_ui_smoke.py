from pathlib import Path
import re


def require(value, name):
    if not value:
        raise AssertionError(name)


def rule(css, selector):
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css, re.S):
        selectors = [part.strip() for part in match.group(1).split(",")]
        if selector in selectors:
            return match.group(2)
    raise AssertionError("missing CSS rule: " + selector)


def declaration(block, name, value, label):
    require(re.search(r"(?:^|;)\s*" + re.escape(name) + r"\s*:\s*"
                      + re.escape(value) + r"\s*(?:;|$)", block) is not None,
            label)


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

    settings = template.split('id="page-settings"', 1)[1].split("</div>", 1)[0]
    require('id="subtitle-status-panel"' not in settings,
            "subtitle status panel must not remain in Settings")
    require('data-file-management-view="subtitle-status"' in template,
            "subtitle status tab missing from File Management")
    require("data-file-management-panel=\"subtitle-status\"" in template,
            "subtitle status panel must be under File Management")

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
    require("file-management-view-subtitle-status" in script,
            "STATUS_UI_ACTIVE_SUBTAB_GUARD")
    require("page-library" in script and "page-settings" not in script,
            "STATUS_UI_PAGE_LIFECYCLE")
    for traffic_light in ("🟢", "🔴", "⚪"):
        require(traffic_light not in script, "traffic-light status emoji remains")
    for label in ("⚙️ 작업 중", "⏸️ 대기", "⚠️ 확인 필요", "⚠️ 실행 상태 확인 필요", "❗ 오류", "⚠️ 조회 실패"):
        require(label in script, "missing semantic status label: " + label)
    require(
        ".subtitle-status-panel" in css,
        "STATUS_UI_STYLE",
    )

    # Light-theme values remain the base; dark mode uses the app/library palette.
    light_checks = (
        (".subtitle-status-panel", "background", "#f8fafc"),
        (".subtitle-status-panel", "border", "1px solid #e2e8f0"),
        (".subtitle-status-current", "color", "#334155"),
        (".subtitle-status-metric", "background", "#ffffff"),
        (".subtitle-status-badge", "background", "#e2e8f0"),
        (".subtitle-status-badge", "color", "#475569"),
    )
    for selector, name, value in light_checks:
        declaration(rule(css, selector), name, value,
                    "LIGHT_THEME_REGRESSION:" + selector + ":" + name)

    dark_checks = (
        ('html[data-theme="dark"] .subtitle-status-panel', "background", "#111827"),
        ('html[data-theme="dark"] .subtitle-status-panel', "border-color", "#273449"),
        ('html[data-theme="dark"] .subtitle-status-title', "color", "#f8fafc"),
        ('html[data-theme="dark"] .subtitle-status-current', "color", "#cbd5e1"),
        ('html[data-theme="dark"] .subtitle-status-metric', "background", "#1f2937"),
        ('html[data-theme="dark"] .subtitle-status-metric strong', "color", "#f8fafc"),
        ('html[data-theme="dark"] .subtitle-status-metric span', "color", "#94a3b8"),
        ('html[data-theme="dark"] .subtitle-status-foot', "color", "#94a3b8"),
        ('html[data-theme="dark"] .subtitle-status-badge', "background", "#1f2937"),
        ('html[data-theme="dark"] .subtitle-status-badge', "color", "#e5e7eb"),
        ('html[data-theme="dark"] .subtitle-status-badge.idle', "background", "#1f2937"),
        ('html[data-theme="dark"] .subtitle-status-badge.running', "background", "#1f2937"),
        ('html[data-theme="dark"] .subtitle-status-badge.attention', "background", "#1f2937"),
        ('html[data-theme="dark"] .subtitle-status-badge.stale', "background", "#1f2937"),
        ('html[data-theme="dark"] .subtitle-status-badge.error', "background", "#1f2937"),
        ('html[data-theme="dark"] .subtitle-status-badge.unavailable', "background", "#1f2937"),
    )
    for selector, name, value in dark_checks:
        declaration(rule(css, selector), name, value,
                    "DARK_THEME_CONTRACT:" + selector + ":" + name)

    require("@media (max-width: 680px)" in css
            and "grid-template-columns: repeat(2, minmax(0, 1fr))" in css,
            "NARROW_METRIC_GRID_REGRESSION")

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
