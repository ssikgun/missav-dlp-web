(() => {
    const originalFetch = window.fetch.bind(window);
    let latestTasks = null;

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
        const task = latestTasks && latestTasks[id];
        if (task && task.status === '다운로드 중') {
            if (typeof showToast === 'function') {
                showToast('먼저 일시정지한 뒤 삭제하세요.', 'error');
            }
            return;
        }
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

    function renderReliabilityControls() {
        if (!latestTasks) return;
        const entries = Object.entries(latestTasks).reverse();
        const cards = document.querySelectorAll('#taskList .task-card');

        entries.forEach(([id, task], index) => {
            const card = cards[index];
            if (!card) return;
            const actions = card.querySelector('.task-actions');
            if (!actions) return;

            if (task.status === '다운로드 중') {
                actions.innerHTML =
                    `<button class="btn btn-primary" onclick="teddyPauseTask('${id}')">Ⅱ 일시정지</button>`;
            } else if (task.status === '일시정지') {
                actions.innerHTML =
                    `<button class="btn btn-primary" onclick="teddyResumeTask('${id}')">▶ 재개</button>` +
                    `<button class="btn btn-danger" onclick="teddyDeleteTask('${id}')">삭제</button>`;
            } else if (!task.status.includes('완료')) {
                const deleteButton = actions.querySelector('button:last-child');
                if (deleteButton && /deleteTask\(/.test(deleteButton.getAttribute('onclick') || '')) {
                    deleteButton.setAttribute('onclick', `teddyDeleteTask('${id}')`);
                }
            }
        });
    }

    window.fetch = function(input, init) {
        const requestUrl = typeof input === 'string' ? input : (input && input.url) || '';
        return originalFetch(input, init).then(response => {
            if (requestUrl.endsWith('/api/tasks') || requestUrl === '/api/tasks') {
                response.clone().json().then(data => {
                    latestTasks = data;
                    setTimeout(renderReliabilityControls, 0);
                }).catch(() => {});
            }
            return response;
        });
    };

    const observer = new MutationObserver(renderReliabilityControls);
    const taskList = document.getElementById('taskList');
    if (taskList) {
        observer.observe(taskList, { childList: true, subtree: true });
    }
})();
