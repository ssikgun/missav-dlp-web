(() => {
    const originalFetch = window.fetch.bind(window);

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
