(() => {
    const originalFetch = window.fetch.bind(window);

    function isHlsRemuxing(task) {
        const downloaded = Number(task && task.downloaded_bytes) || 0;
        const total = Number(task && task.total_bytes_estimate) || 0;
        return !!(
            task &&
            task.status === '다운로드 중' &&
            task.progress === '99%' &&
            task.hls_transport_mode &&
            downloaded > 0 &&
            total > 0 &&
            downloaded === total
        );
    }

    // The HLS runtime deliberately parks at 99% after every segment is safely
    // downloaded and sets speed to zero while ffmpeg creates the final MP4.
    // Present that deterministic backend sentinel as a finished-download/remux
    // phase without changing the runtime task state or pause/resume semantics.
    if (typeof window.teddyUpdateTaskCard === 'function' && !window.__teddyRemuxUiWrapped) {
        const originalUpdateTaskCard = window.teddyUpdateTaskCard;
        window.teddyUpdateTaskCard = function(id, task, card) {
            if (!isHlsRemuxing(task)) {
                return originalUpdateTaskCard(id, task, card);
            }

            const displayTask = Object.assign({}, task, {
                status: 'MP4 생성 중',
                progress: '100%',
                speed_bps: 0,
            });
            originalUpdateTaskCard(id, displayTask, card);

            const meta = card.querySelector('.task-meta');
            if (meta) meta.textContent = '다운로드 완료 · MP4 생성 중';

            const progress = card.querySelector('.progress-wrap');
            if (progress) {
                progress.style.display = '';
                const fill = progress.querySelector('.progress-fill');
                if (fill) fill.style.width = '100%';
                const progressText = progress.querySelector('.progress-text');
                if (progressText) progressText.textContent = '100% · 다운로드 완료 · MP4 생성 중…';
            }

            const actions = card.querySelector('.task-actions');
            if (actions) {
                actions.dataset.state = 'remux';
                actions.innerHTML = '<button class="btn btn-ghost" disabled>MP4 생성 중…</button>';
            }
        };
        window.__teddyRemuxUiWrapped = true;
    }

    async function taskAction(id, action) {
        const response = await originalFetch(`/api/tasks/${id}/${action}`, { method: 'POST' });
        let data = {};
        try {
            data = await response.json();
        } catch (_) {}
        if (!response.ok) {
            if (typeof showToast === 'function') {
                showToast(data.message || '요청에 실패했습니다.', 'error');
            }
            return;
        }
        if (typeof showToast === 'function') {
            showToast(data.message || '처리되었습니다.', 'success');
        }
        if (typeof fetchTasks === 'function') fetchTasks();
    }

    window.teddyPauseTask = id => taskAction(id, 'pause');
    window.teddyResumeTask = id => taskAction(id, 'resume');

    window.teddyDeleteTask = async id => {
        if (!window.confirm('작업 기록과 이어받기 데이터를 완전히 삭제하시겠습니까?')) return;
        const response = await originalFetch(`/api/tasks/${id}`, { method: 'DELETE' });
        let data = {};
        try {
            data = await response.json();
        } catch (_) {}
        if (!response.ok) {
            if (typeof showToast === 'function') {
                showToast(data.message || '삭제에 실패했습니다.', 'error');
            }
            return;
        }
        if (typeof fetchTasks === 'function') fetchTasks();
    };
})();
