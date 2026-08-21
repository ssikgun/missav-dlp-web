from pathlib import Path


INDEX = Path('templates/index.html')
text = INDEX.read_text(encoding='utf-8')


def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'browser patch failed: {label}: expected 1 match, got {count}')
    text = text.replace(old, new, 1)


# Keep the Browser entry directly after Download and before Files.
files_button = '''        <button class="sidebar-btn" data-page="files" title="파일 관리">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>
        </button>'''

browser_button = '''        <button class="sidebar-btn" data-page="browser" title="브라우저">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a15 15 0 010 18"/><path d="M12 3a15 15 0 000 18"/></svg>
        </button>'''

replace_once(
    files_button,
    browser_button + '\n' + files_button,
    'browser sidebar button',
)

replace_once(
    '''        <!-- Files Page -->''',
    '''        <!-- Browser Page -->
        <div id="page-browser" class="page">
            <div class="teddy-browser-shell">
                <iframe
                    id="teddyBrowserFrame"
                    class="teddy-browser-frame"
                    title="VPN Browser"
                    allow="clipboard-read; clipboard-write"
                ></iframe>
            </div>
        </div>

        <!-- Files Page -->''',
    'browser page',
)

# Static assets are served from templates/ by Flask's configured static folder.
replace_once(
    '</head>',
    '<link rel="stylesheet" href="/static/teddy-browser.css"></head>',
    'browser stylesheet',
)
replace_once(
    '</body>',
    '<script src="/static/teddy-browser.js"></script></body>',
    'browser script',
)

INDEX.write_text(text, encoding='utf-8')
print('teddy browser UI patch: OK')
