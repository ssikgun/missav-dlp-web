(function () {
    const WORKER_SETTING_ID = 'set-hls-workers';
    const WRITE_SETTING_ID = 'set-hls-write-mode';
    const ALLOWED_WORKERS = [2, 4, 8, 12, 16, 20, 24];
    const ALLOWED_WRITE_MODES = ['parts', 'ram'];

    function normalizeWorkers(value) {
        const n = Number(value);
        return ALLOWED_WORKERS.includes(n) ? n : 8;
    }

    function normalizeWriteMode(value) {
        const mode = String(value || '').toLowerCase();
        return ALLOWED_WRITE_MODES.includes(mode) ? mode : 'parts';
    }

    function loadSettings(workerSelect, writeSelect) {
        return fetch('/api/settings')
            .then(function (r) { return r.json(); })
            .then(function (settings) {
                workerSelect.value = String(normalizeWorkers(settings.hls_workers));
                writeSelect.value = normalizeWriteMode(settings.hls_write_mode);
            })
            .catch(function () {
                workerSelect.value = '8';
                writeSelect.value = 'parts';
            });
    }

    function saveSetting(payload, successMessage) {
        return fetch('/api/settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(function (r) { return r.json(); })
        .then(function (res) {
            if (typeof showToast === 'function') {
                showToast(successMessage, res.status === 'success' ? 'success' : 'error');
            }
            return res;
        });
    }

    function mount() {
        if (document.getElementById(WORKER_SETTING_ID)) return;
        const maxConcurrent = document.getElementById('set-max-concurrent');
        if (!maxConcurrent) return;
        const anchor = maxConcurrent.closest('.setting-group');
        if (!anchor || !anchor.parentNode) return;

        // Extend the page's existing reset payload so "기본값 복원" also returns
        // both HLS benchmark knobs to the production-safe compatibility defaults.
        if (typeof defaultSettings !== 'undefined' && defaultSettings) {
            defaultSettings.hls_workers = 8;
            defaultSettings.hls_write_mode = 'parts';
        }

        const workerGroup = document.createElement('div');
        workerGroup.className = 'setting-group';
        workerGroup.innerHTML =
            '<label class="setting-label">HLS 연결 수 (성능 테스트)</label>' +
            '<div class="setting-desc">MissAV/HLS 전용 worker 수입니다. 새로 시작하거나 재개하는 HLS 실행부터 적용됩니다. ' +
            '같은 영상·같은 Proxy에서 값을 비교해 최적점을 찾으세요.</div>' +
            '<select id="' + WORKER_SETTING_ID + '" class="setting-select">' +
                '<option value="2">2 workers</option>' +
                '<option value="4">4 workers</option>' +
                '<option value="8">8 workers (기존값)</option>' +
                '<option value="12">12 workers</option>' +
                '<option value="16">16 workers</option>' +
                '<option value="20">20 workers</option>' +
                '<option value="24">24 workers</option>' +
            '</select>';
        anchor.insertAdjacentElement('afterend', workerGroup);

        const writeGroup = document.createElement('div');
        writeGroup.className = 'setting-group';
        writeGroup.innerHTML =
            '<label class="setting-label">HLS 저장 방식 (성능 테스트)</label>' +
            '<div class="setting-desc">Safe parts는 기존 방식입니다. RAM benchmark는 worker가 네트워크 수신만 하고 ' +
            '메인 coordinator가 같은 .parts 파일을 한 번에 하나씩 저장해 동시 NAS I/O 영향을 비교합니다. ' +
            '완료된 세그먼트 이어받기는 두 방식 모두 유지됩니다.</div>' +
            '<select id="' + WRITE_SETTING_ID + '" class="setting-select">' +
                '<option value="parts">Safe parts (기존값)</option>' +
                '<option value="ram">RAM benchmark</option>' +
            '</select>';
        workerGroup.insertAdjacentElement('afterend', writeGroup);

        const workerSelect = workerGroup.querySelector('#' + WORKER_SETTING_ID);
        const writeSelect = writeGroup.querySelector('#' + WRITE_SETTING_ID);
        loadSettings(workerSelect, writeSelect);

        workerSelect.addEventListener('change', function () {
            const workers = normalizeWorkers(workerSelect.value);
            workerSelect.value = String(workers);
            saveSetting(
                { hls_workers: workers },
                'HLS 연결 수를 ' + workers + '로 저장했습니다. 다음 HLS 실행부터 적용됩니다.'
            ).catch(function (err) {
                if (typeof showToast === 'function') showToast('HLS 연결 수 저장 실패: ' + err, 'error');
            });
        });

        writeSelect.addEventListener('change', function () {
            const mode = normalizeWriteMode(writeSelect.value);
            writeSelect.value = mode;
            const label = mode === 'ram' ? 'RAM benchmark' : 'Safe parts';
            saveSetting(
                { hls_write_mode: mode },
                'HLS 저장 방식을 ' + label + '로 저장했습니다. 다음 HLS 실행부터 적용됩니다.'
            ).catch(function (err) {
                if (typeof showToast === 'function') showToast('HLS 저장 방식 저장 실패: ' + err, 'error');
            });
        });

        // Existing settings navigation/reset calls loadSettingsUI(). Refresh the
        // separately injected fields at the same time without touching upstream UI.
        if (typeof window.loadSettingsUI === 'function' && !window.__teddyHlsLoadWrapped) {
            const originalLoadSettingsUI = window.loadSettingsUI;
            window.loadSettingsUI = function () {
                const result = originalLoadSettingsUI.apply(this, arguments);
                const currentWorkers = document.getElementById(WORKER_SETTING_ID);
                const currentWrite = document.getElementById(WRITE_SETTING_ID);
                if (currentWorkers && currentWrite) loadSettings(currentWorkers, currentWrite);
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
