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
})();
