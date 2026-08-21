(function () {
    const WORKER_SETTING_ID = 'set-hls-workers';
    const WRITE_SETTING_ID = 'set-hls-write-mode';
    const TRANSPORT_SETTING_ID = 'set-hls-transport-mode';
    const ALLOWED_WORKERS = [2, 4, 8, 12, 16, 20, 24];
    const ALLOWED_WRITE_MODES = ['parts', 'ram'];
    const ALLOWED_TRANSPORT_MODES = ['per-worker', 'async-pool'];

    function normalizeWorkers(value) {
        const n = Number(value);
        return ALLOWED_WORKERS.includes(n) ? n : 8;
    }

    function normalizeWriteMode(value) {
        const mode = String(value || '').toLowerCase();
        return ALLOWED_WRITE_MODES.includes(mode) ? mode : 'parts';
    }

    function normalizeTransportMode(value) {
        const mode = String(value || '').toLowerCase();
        return ALLOWED_TRANSPORT_MODES.includes(mode) ? mode : 'per-worker';
    }

    function loadSettings(workerSelect, writeSelect, transportSelect) {
        return fetch('/api/settings')
            .then(function (r) { return r.json(); })
            .then(function (settings) {
                workerSelect.value = String(normalizeWorkers(settings.hls_workers));
                writeSelect.value = normalizeWriteMode(settings.hls_write_mode);
                transportSelect.value = normalizeTransportMode(settings.hls_transport_mode);
            })
            .catch(function () {
                workerSelect.value = '8';
                writeSelect.value = 'parts';
                transportSelect.value = 'per-worker';
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

        // Extend the page's existing reset payload so "기본값 복원" returns all
        // HLS benchmark knobs to the proven production-safe defaults.
        if (typeof defaultSettings !== 'undefined' && defaultSettings) {
            defaultSettings.hls_workers = 8;
            defaultSettings.hls_write_mode = 'parts';
            defaultSettings.hls_transport_mode = 'per-worker';
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

        const transportGroup = document.createElement('div');
        transportGroup.className = 'setting-group';
        transportGroup.innerHTML =
            '<label class="setting-label">HLS 연결 방식 (성능 테스트)</label>' +
            '<div class="setting-desc">Per-worker Session은 현재 검증된 방식입니다. Async shared pool은 하나의 ' +
            'curl_cffi AsyncSession/AsyncCurl pool에서 연결을 재사용하는 비교 경로입니다. Proxy/Direct 벤치마크용이며, ' +
            'VPN은 자동 복구 안전성을 위해 실제 실행 시 기존 Per-worker 방식으로 유지됩니다.</div>' +
            '<select id="' + TRANSPORT_SETTING_ID + '" class="setting-select">' +
                '<option value="per-worker">Per-worker Session (기존값)</option>' +
                '<option value="async-pool">Async shared pool benchmark</option>' +
            '</select>';
        workerGroup.insertAdjacentElement('afterend', transportGroup);

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
        transportGroup.insertAdjacentElement('afterend', writeGroup);

        const workerSelect = workerGroup.querySelector('#' + WORKER_SETTING_ID);
        const transportSelect = transportGroup.querySelector('#' + TRANSPORT_SETTING_ID);
        const writeSelect = writeGroup.querySelector('#' + WRITE_SETTING_ID);
        loadSettings(workerSelect, writeSelect, transportSelect);

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

        transportSelect.addEventListener('change', function () {
            const mode = normalizeTransportMode(transportSelect.value);
            transportSelect.value = mode;
            const label = mode === 'async-pool' ? 'Async shared pool benchmark' : 'Per-worker Session';
            saveSetting(
                { hls_transport_mode: mode },
                'HLS 연결 방식을 ' + label + '로 저장했습니다. 다음 HLS 실행부터 적용됩니다.'
            ).catch(function (err) {
                if (typeof showToast === 'function') showToast('HLS 연결 방식 저장 실패: ' + err, 'error');
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
                const currentTransport = document.getElementById(TRANSPORT_SETTING_ID);
                if (currentWorkers && currentWrite && currentTransport) {
                    loadSettings(currentWorkers, currentWrite, currentTransport);
                }
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
