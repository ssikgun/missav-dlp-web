(() => {
    const originalFetch = window.fetch.bind(window);

    function hasFinishedPayload(task) {
        const downloaded = Number(task && task.downloaded_bytes) || 0;
        const total = Number(task && task.total_bytes_estimate) || 0;
        return downloaded > 0 && total > 0 && downloaded === total;
    }

    function isHlsRemuxing(task) {
        return !!(
            task &&
            task.status === '다운로드 중' &&
            task.progress === '99%' &&
            task.hls_transport_mode &&
            hasFinishedPayload(task)
        );
    }

    function isGenericPostprocessing(task) {
        return !!(
            task &&
            task.status === '다운로드 중' &&
            task.progress === '99%' &&
            task.engine === 'yt-dlp' &&
            !task.hls_transport_mode &&
            hasFinishedPayload(task)
        );
    }

    function genericPostprocessLabel(task) {
        const options = task && task.yt_dlp_options && typeof task.yt_dlp_options === 'object'
            ? task.yt_dlp_options
            : {};
        if (options.media_mode === 'audio') {
            const format = String(options.audio_format || 'audio').toUpperCase();
            return `${format} 변환 중`;
        }
        const container = String(options.video_container || 'video').toUpperCase();
        return `${container} 생성 중`;
    }

    function renderFinishedDownloadPhase(originalUpdateTaskCard, id, task, card, phaseLabel, actionState) {
        const displayTask = Object.assign({}, task, {
            status: phaseLabel,
            progress: '100%',
            speed_bps: 0,
        });
        originalUpdateTaskCard(id, displayTask, card);

        const meta = card.querySelector('.task-meta');
        if (meta) meta.textContent = `다운로드 완료 · ${phaseLabel}`;

        const progress = card.querySelector('.progress-wrap');
        if (progress) {
            progress.style.display = '';
            const fill = progress.querySelector('.progress-fill');
            if (fill) fill.style.width = '100%';
            const progressText = progress.querySelector('.progress-text');
            if (progressText) progressText.textContent = `100% · 다운로드 완료 · ${phaseLabel}…`;
        }

        const actions = card.querySelector('.task-actions');
        if (actions) {
            actions.dataset.state = actionState;
            actions.innerHTML = `<button class="btn btn-ghost" disabled>${phaseLabel}…</button>`;
        }
    }

    // Both HLS and generic yt-dlp deliberately park at 99% once all download
    // bytes are safely present, while ffmpeg performs the final remux/extract
    // post-processing step. Present that deterministic backend sentinel as a
    // completed download plus post-processing phase without changing runtime
    // task state or pause/resume semantics.
    if (typeof window.teddyUpdateTaskCard === 'function' && !window.__teddyRemuxUiWrapped) {
        const originalUpdateTaskCard = window.teddyUpdateTaskCard;
        window.teddyUpdateTaskCard = function(id, task, card) {
            if (isHlsRemuxing(task)) {
                renderFinishedDownloadPhase(
                    originalUpdateTaskCard,
                    id,
                    task,
                    card,
                    'MP4 생성 중',
                    'remux',
                );
                return;
            }

            if (isGenericPostprocessing(task)) {
                renderFinishedDownloadPhase(
                    originalUpdateTaskCard,
                    id,
                    task,
                    card,
                    genericPostprocessLabel(task),
                    'yt-dlp-postprocess',
                );
                return;
            }

            return originalUpdateTaskCard(id, task, card);
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

    async function teddyClearCompletedTasks() {
        const button = document.getElementById('teddy-clear-completed');
        try {
            const tasksResponse = await originalFetch('/api/tasks');
            if (!tasksResponse.ok) {
                throw new Error('작업 목록을 불러오지 못했습니다.');
            }
            const tasks = await tasksResponse.json();
            const completedIds = Object.entries(tasks)
                .filter(([, task]) => String((task && task.status) || '') === '완료')
                .map(([id]) => id);

            if (!completedIds.length) {
                if (typeof showToast === 'function') {
                    showToast('정리할 완료 작업이 없습니다.', 'success');
                }
                if (typeof fetchTasks === 'function') fetchTasks();
                return;
            }

            if (!window.confirm(
                `완료된 작업 기록 ${completedIds.length}개를 목록에서 삭제하시겠습니까?\n\n` +
                '다운로드된 파일은 삭제되지 않습니다.'
            )) return;

            if (button) {
                button.disabled = true;
                button.textContent = '정리 중…';
            }

            let removed = 0;
            let failed = 0;
            for (const id of completedIds) {
                try {
                    const response = await originalFetch(`/api/tasks/${encodeURIComponent(id)}`, {
                        method: 'DELETE',
                    });
                    if (response.ok) removed++;
                    else failed++;
                } catch (_) {
                    failed++;
                }
            }

            if (typeof showToast === 'function') {
                if (failed) {
                    showToast(`완료 작업 ${removed}개 정리 · ${failed}개 실패`, 'error');
                } else {
                    showToast(
                        `완료된 작업 기록 ${removed}개를 정리했습니다. 다운로드 파일은 유지됩니다.`,
                        'success',
                    );
                }
            }
            if (typeof fetchTasks === 'function') fetchTasks();
        } catch (error) {
            if (typeof showToast === 'function') {
                showToast(error && error.message ? error.message : '완료 작업 정리에 실패했습니다.', 'error');
            }
        } finally {
            const currentButton = document.getElementById('teddy-clear-completed');
            if (currentButton) {
                currentButton.disabled = false;
                currentButton.textContent = '완료 일괄 삭제';
            }
        }
    }

    window.teddyClearCompletedTasks = teddyClearCompletedTasks;

    function ensureCompletedCleanupButton() {
        const stats = document.getElementById('stats');
        if (!stats) return;

        const hasCompleted = !!stats.querySelector('.stat-done');
        let button = document.getElementById('teddy-clear-completed');
        if (!hasCompleted) {
            if (button) button.remove();
            return;
        }

        if (!button) {
            button = document.createElement('button');
            button.id = 'teddy-clear-completed';
            button.type = 'button';
            button.className = 'btn btn-ghost';
            button.textContent = '완료 일괄 삭제';
            button.title = '다운로드 파일은 유지하고 완료 작업 기록만 삭제합니다';
            button.style.display = 'block';
            button.style.margin = '-10px 0 16px auto';
            button.addEventListener('click', teddyClearCompletedTasks);
            stats.insertAdjacentElement('afterend', button);
        }
    }

    const stats = document.getElementById('stats');
    if (stats && !window.__teddyCompletedCleanupObserver) {
        const observer = new MutationObserver(ensureCompletedCleanupButton);
        observer.observe(stats, { childList: true });
        window.__teddyCompletedCleanupObserver = observer;
        ensureCompletedCleanupButton();
    }
})();