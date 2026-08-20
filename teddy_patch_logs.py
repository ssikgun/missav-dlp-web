from pathlib import Path


INDEX = Path('templates/index.html')
text = INDEX.read_text(encoding='utf-8')


def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'log patch failed: {label}: expected 1 match, got {count}')
    text = text.replace(old, new, 1)


replace_once(
    '''        <button class="sidebar-btn" data-page="files" title="파일 관리">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>
        </button>
        <div style="flex:1"></div>''',
    '''        <button class="sidebar-btn" data-page="files" title="파일 관리">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>
        </button>
        <button class="sidebar-btn" data-page="logs" title="로그">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
        </button>
        <div style="flex:1"></div>''',
    'sidebar log button',
)

replace_once(
    '''        <!-- Settings Page -->
        <div id="page-settings" class="page">''',
    '''        <!-- Logs Page -->
        <div id="page-logs" class="page">
            <div class="teddy-log-header">
                <div>
                    <div class="page-title">로그</div>
                    <div class="page-subtitle teddy-log-subtitle">앱의 최근 동작 로그를 표시합니다 · 컨테이너 재시작 시 웹 로그 버퍼는 초기화됩니다</div>
                </div>
                <div class="teddy-log-controls">
                    <label class="teddy-log-autoscroll"><input type="checkbox" id="teddyLogAutoscroll" checked> 자동 스크롤</label>
                    <button type="button" id="teddyLogRefresh">새로고침</button>
                    <button type="button" id="teddyLogClear">화면 지우기</button>
                </div>
            </div>
            <div class="teddy-log-status" id="teddyLogStatus">로그를 불러오는 중…</div>
            <pre class="teddy-log-output" id="teddyLogOutput"></pre>
        </div>

        <!-- Settings Page -->
        <div id="page-settings" class="page">''',
    'log page',
)

INDEX.write_text(text, encoding='utf-8')
print('teddy log page patch: OK')
