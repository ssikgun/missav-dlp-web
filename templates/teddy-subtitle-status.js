(function () {
    'use strict';

    const STATUS_LABELS = {
        running: '🟢 작업 중',
        idle: '⚪ 대기',
        attention: '🔴 확인 필요',
        stale: '🔴 실행 상태 확인 필요',
        error: '🔴 오류',
        unavailable: '🔴 조회 실패'
    };

    function byId(id) {
        return document.getElementById(id);
    }

    function number(value) {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function formatTime(value) {
        if (!value) return '기록 없음';

        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return String(value);

        return date.toLocaleString('ko-KR', {
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    }

    function render(data) {
        const badge = byId('subtitle-status-badge');
        const current = byId('subtitle-status-current');
        const foot = byId('subtitle-status-foot');

        if (!badge || !current || !foot) return;

        const status = String(data.status || 'unavailable');

        badge.className = 'subtitle-status-badge ' + status;
        badge.textContent =
            STATUS_LABELS[status] || STATUS_LABELS.unavailable;

        if (status === 'unavailable') {
            current.textContent =
                data.message || '자막 처리 상태를 불러올 수 없습니다.';
        } else {
            const dvd = data.current_dvd_id || '없음';
            const progress = data.progress || {};
            let detail = '현재 작품: ' + dvd;

            if (
                Number.isInteger(progress.part_index)
                && Number.isInteger(progress.part_count)
                && progress.part_count > 0
            ) {
                detail +=
                    ' · Part '
                    + progress.part_index
                    + '/'
                    + progress.part_count;
            } else if (progress.stage) {
                detail += ' · ' + progress.stage;
            }

            current.textContent = detail;
        }

        const counts = data.counts || {};

        byId('subtitle-count-published').textContent =
            number(counts.PUBLISHED);
        byId('subtitle-count-pending').textContent =
            number(counts.PENDING);
        byId('subtitle-count-retryable').textContent =
            number(counts.FAILED_RETRYABLE);
        byId('subtitle-count-terminal').textContent =
            number(counts.FAILED_TERMINAL);
        byId('subtitle-count-unresolved').textContent =
            number(counts.UNRESOLVED);

        let heartbeatText = '';

        if (data.heartbeat && data.heartbeat.fresh) {
            heartbeatText = ' · heartbeat 정상';
        } else if (
            data.heartbeat
            && data.heartbeat.present
            && !data.heartbeat.fresh
        ) {
            heartbeatText = ' · heartbeat 오래됨';
        }

        foot.textContent =
            '마지막 활동: '
            + formatTime(data.last_activity_at)
            + heartbeatText;
    }

    async function loadSubtitleStatus() {
        const response = await fetch(
            '/api/subtitles/status',
            { cache: 'no-store' }
        );

        let data;

        try {
            data = await response.json();
        } catch (error) {
            data = {
                status: 'unavailable',
                message: '상태 응답을 읽을 수 없습니다.'
            };
        }

        if (!response.ok && !data.status) {
            data.status = 'unavailable';
        }

        render(data);
    }

    window.loadSubtitleStatus = loadSubtitleStatus;

    document.addEventListener('DOMContentLoaded', function () {
        const settingsButton = document.querySelector(
            '.sidebar-btn[data-page="settings"]'
        );

        if (settingsButton) {
            settingsButton.addEventListener(
                'click',
                loadSubtitleStatus
            );
        }

        const settingsPage = byId('page-settings');

        if (
            settingsPage
            && settingsPage.classList.contains('active')
        ) {
            loadSubtitleStatus();
        }

        setInterval(function () {
            const page = byId('page-settings');

            if (
                page
                && page.classList.contains('active')
            ) {
                loadSubtitleStatus();
            }
        }, 10000);
    });
})();
