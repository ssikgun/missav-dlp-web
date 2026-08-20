(() => {
    const originalFetch = window.fetch.bind(window);
    let latestTasks = null;

    function formatSpeed(bytesPerSecond) {
        const bps = Number(bytesPerSecond) || 0;
        if (bps <= 0) return '';
        if (bps >= 1e9) return (bps / 1e9).toFixed(1) + ' GB/s';
        if (bps >= 1e6) return (bps / 1e6).toFixed(1) + ' MB/s';
        if (bps >= 1e3) return (bps / 1e3).toFixed(1) + ' KB/s';
        return Math.round(bps) + ' B/s';
    }

    function renderSpeeds() {
        if (!latestTasks) return;
        const entries = Object.entries(latestTasks).reverse();
        const cards = document.querySelectorAll('#taskList .task-card');

        entries.forEach(([, task], index) => {
            if (task.status !== '다운로드 중') return;
            const card = cards[index];
            if (!card) return;
            const text = card.querySelector('.progress-text');
            if (!text) return;

            const pct = task.progress || '0%';
            const speed = formatSpeed(task.speed_bps);
            text.textContent = speed ? `${pct} · ↓ ${speed}` : pct;
        });
    }

    window.fetch = function(input, init) {
        const requestUrl = typeof input === 'string' ? input : (input && input.url) || '';
        return originalFetch(input, init).then(response => {
            if (requestUrl.endsWith('/api/tasks') || requestUrl === '/api/tasks') {
                response.clone().json().then(data => {
                    latestTasks = data;
                    setTimeout(renderSpeeds, 0);
                }).catch(() => {});
            }
            return response;
        });
    };

    const observer = new MutationObserver(renderSpeeds);
    const taskList = document.getElementById('taskList');
    if (taskList) {
        observer.observe(taskList, { childList: true, subtree: true });
    }
})();
