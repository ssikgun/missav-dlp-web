(() => {
    const originalFetch = window.fetch.bind(window);
    let latestTasks = null;

    function formatBytes(bytes) {
        const value = Number(bytes) || 0;
        if (value <= 0) return '';
        if (value >= 1e9) return (value / 1e9).toFixed(1) + ' GB';
        if (value >= 1e6) return (value / 1e6).toFixed(1) + ' MB';
        if (value >= 1e3) return (value / 1e3).toFixed(1) + ' KB';
        return Math.round(value) + ' B';
    }

    function formatSpeed(bytesPerSecond) {
        const formatted = formatBytes(bytesPerSecond);
        return formatted ? formatted + '/s' : '';
    }

    function renderSpeedsAndSizes() {
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
            const downloaded = formatBytes(task.downloaded_bytes);
            const totalEstimate = formatBytes(task.total_bytes_estimate);

            const parts = [pct];
            if (downloaded && totalEstimate) {
                parts.push(`${downloaded} / 약 ${totalEstimate}`);
            } else if (downloaded) {
                parts.push(downloaded);
            }
            if (speed) {
                parts.push(`↓ ${speed}`);
            }

            const nextText = parts.join(' · ');
            if (text.textContent !== nextText) {
                text.textContent = nextText;
            }
        });
    }

    window.fetch = function(input, init) {
        const requestUrl = typeof input === 'string' ? input : (input && input.url) || '';
        return originalFetch(input, init).then(response => {
            if (requestUrl.endsWith('/api/tasks') || requestUrl === '/api/tasks') {
                response.clone().json().then(data => {
                    latestTasks = data;
                    // 원본 fetchTasks()가 DOM을 그린 직후 한 번만 속도/용량을 보정한다.
                    setTimeout(renderSpeedsAndSizes, 0);
                }).catch(() => {});
            }
            return response;
        });
    };
})();
