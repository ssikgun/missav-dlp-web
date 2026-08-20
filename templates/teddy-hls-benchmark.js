(function () {
    const SETTING_ID = 'set-hls-workers';
    const ALLOWED = [2, 4, 8, 12, 16];

    function normalize(value) {
        const n = Number(value);
        return ALLOWED.includes(n) ? n : 8;
    }

    function loadSetting(select) {
        return fetch('/api/settings')
            .then(function (r) { return r.json(); })
            .then(function (settings) {
                select.value = String(normalize(settings.hls_workers));
            })
            .catch(function () {
                select.value = '8';
            });
    }

    function mount() {
        if (document.getElementById(SETTING_ID)) return;
        const maxConcurrent = document.getElementById('set-max-concurrent');
        if (!maxConcurrent) return;
        const anchor = maxConcurrent.closest('.setting-group');
        if (!anchor || !anchor.parentNode) return;

        // Extend the page's existing reset payload so "기본값 복원" also returns
        // this benchmark knob to the compatibility default.
        if (typeof defaultSettings !== 'undefined' && defaultSettings) {
            defaultSettings.hls_workers = 8;
        }

        const group = document.createElement('div');
        group.className = 'setting-group';
        group.innerHTML =
            '<label class="setting-label">HLS 연결 수 (성능 테스트)</label>' +
            '<div class="setting-desc">MissAV/HLS 전용 worker 수입니다. 새로 시작하거나 재개하는 HLS 실행부터 적용됩니다. ' +
            '같은 영상·같은 Proxy에서 2 / 4 / 8 / 12 / 16을 비교해 최적값을 찾으세요.</div>' +
            '<select id="' + SETTING_ID + '" class="setting-select">' +
                '<option value="2">2 workers</option>' +
                '<option value="4">4 workers</option>' +
                '<option value="8">8 workers (기존값)</option>' +
                '<option value="12">12 workers</option>' +
                '<option value="16">16 workers</option>' +
            '</select>';
        anchor.insertAdjacentElement('afterend', group);

        const select = group.querySelector('#' + SETTING_ID);
        loadSetting(select);

        select.addEventListener('change', function () {
            const workers = normalize(select.value);
            select.value = String(workers);
            fetch('/api/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hls_workers: workers })
            })
            .then(function (r) { return r.json(); })
            .then(function (res) {
                if (typeof showToast === 'function') {
                    showToast('HLS 연결 수를 ' + workers + '로 저장했습니다. 다음 HLS 실행부터 적용됩니다.',
                              res.status === 'success' ? 'success' : 'error');
                }
            })
            .catch(function (err) {
                if (typeof showToast === 'function') {
                    showToast('HLS 연결 수 저장 실패: ' + err, 'error');
                }
            });
        });

        // Existing settings navigation/reset calls loadSettingsUI(). Refresh this
        // separately injected field at the same time without touching upstream UI.
        if (typeof window.loadSettingsUI === 'function' && !window.__teddyHlsLoadWrapped) {
            const originalLoadSettingsUI = window.loadSettingsUI;
            window.loadSettingsUI = function () {
                const result = originalLoadSettingsUI.apply(this, arguments);
                const current = document.getElementById(SETTING_ID);
                if (current) loadSetting(current);
                return result;
            };
            window.__teddyHlsLoadWrapped = true;
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', mount);
    } else {
        mount();
    }
})();
