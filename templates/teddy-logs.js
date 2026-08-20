(() => {
    const output = document.getElementById('teddyLogOutput');
    const status = document.getElementById('teddyLogStatus');
    const autoscroll = document.getElementById('teddyLogAutoscroll');
    const refreshButton = document.getElementById('teddyLogRefresh');
    const clearButton = document.getElementById('teddyLogClear');
    const logPageButton = document.querySelector('.sidebar-btn[data-page="logs"]');
    if (!output || !status || !autoscroll || !refreshButton || !clearButton || !logPageButton) return;

    const MAX_RENDERED_LINES = 1200;
    let latestSeq = 0;
    let rendered = [];
    let fetching = false;
    let initialized = false;

    function isActive() {
        const page = document.getElementById('page-logs');
        return !!(page && page.classList.contains('active'));
    }

    function formatEntry(entry) {
        const date = new Date((Number(entry.ts) || 0) * 1000);
        const clock = date.toLocaleTimeString('ko-KR', {
            hour12: false,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
        });
        return '[' + clock + '] ' + String(entry.text || '');
    }

    function render() {
        output.textContent = rendered.join('\n');
        status.textContent = '표시 중 ' + rendered.length + '줄 · 2초마다 갱신';
        if (autoscroll.checked) output.scrollTop = output.scrollHeight;
    }

    async function fetchLogs(forceReload = false) {
        if (fetching || (!isActive() && !forceReload)) return;
        fetching = true;
        try {
            const after = forceReload ? 0 : latestSeq;
            const url = '/api/logs?limit=' + (after ? '600' : '500') + (after ? '&after=' + encodeURIComponent(after) : '');
            const response = await fetch(url, { cache: 'no-store' });
            if (!response.ok) throw new Error('HTTP ' + response.status);
            const data = await response.json();
            const entries = Array.isArray(data.entries) ? data.entries : [];

            if (forceReload) rendered = [];
            if (entries.length) {
                rendered.push(...entries.map(formatEntry));
                if (rendered.length > MAX_RENDERED_LINES) {
                    rendered = rendered.slice(-MAX_RENDERED_LINES);
                }
            }
            latestSeq = Number(data.latest_seq) || latestSeq;
            initialized = true;
            render();
        } catch (error) {
            status.textContent = '로그 조회 실패: ' + error.message;
        } finally {
            fetching = false;
        }
    }

    logPageButton.addEventListener('click', () => {
        if (!initialized) fetchLogs(true);
        else fetchLogs(false);
    });

    refreshButton.addEventListener('click', () => fetchLogs(true));

    clearButton.addEventListener('click', () => {
        rendered = [];
        output.textContent = '';
        status.textContent = '화면을 지웠습니다 · 새 로그부터 표시합니다';
    });

    setInterval(() => {
        if (isActive() && !document.hidden) fetchLogs(false);
    }, 2000);
})();
