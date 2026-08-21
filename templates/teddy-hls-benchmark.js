(function () {
    const WORKER_SETTING_ID = 'set-hls-workers';
    const WRITE_SETTING_ID = 'set-hls-write-mode';
    const TRANSPORT_SETTING_ID = 'set-hls-transport-mode';
    const POOL_SETTING_ID = 'set-hls-pool-clients';
    const ALLOWED_WORKERS = [2, 4, 8, 12, 16, 20, 24];
    const ALLOWED_WRITE_MODES = ['parts', 'ram'];
    const ALLOWED_TRANSPORT_MODES = ['per-worker', 'async-pool'];
    const ALLOWED_POOL_CLIENTS = [4, 8, 12, 16, 24];

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

    function normalizePoolClients(value) {
        const n = Number(value);
        return ALLOWED_POOL_CLIENTS.includes(n) ? n : 24;
    }

    function updatePoolEnabled(transportSelect, poolSelect) {
        const enabled = normalizeTransportMode(transportSelect.value) === 'async-pool';
        poolSelect.disabled = !enabled;
        poolSelect.title = enabled ? '' : 'Async shared pool에서만 적용됩니다.';
    }

    function loadSettings(workerSelect, writeSelect, transportSelect, poolSelect) {
        return fetch('/api/settings')
            .then(function (r) { return r.json(); })
            .then(function (settings) {
                workerSelect.value = String(normalizeWorkers(settings.hls_workers));
                writeSelect.value = normalizeWriteMode(settings.hls_write_mode);
                transportSelect.value = normalizeTransportMode(settings.hls_transport_mode);
                poolSelect.value = String(normalizePoolClients(settings.hls_pool_clients));
                updatePoolEnabled(transportSelect, poolSelect);
            })
            .catch(function () {
                workerSelect.value = '8';
                writeSelect.value = 'parts';
                transportSelect.value = 'per-worker';
                poolSelect.value = '24';
                updatePoolEnabled(transportSelect, poolSelect);
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
            defaultSettings.hls_pool_clients = 24;
        }

        const workerGroup = document.createElement('div');
        workerGroup.className = 'setting-group';
        workerGroup.innerHTML =
            '<label class="setting-label">HLS 연결 수 (성능 테스트)</label>' +
            '<div class="setting-desc">MissAV/HLS 스케줄러 worker 수입니다. 새로 시작하거나 재개하는 HLS 실행부터 적용됩니다. ' +
            'Async pool에서는 worker 수와 실제 pool 연결 수를 따로 비교할 수 있습니다.</div>' +
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
            '<div class="setting-desc">Per-worker Session은 기존 방식입니다. Async shared pool은 하나의 ' +
            'curl_cffi AsyncSession/AsyncCurl pool에서 연결을 재사용합니다. Proxy/Direct 벤치마크용이며, ' +
            'VPN은 자동 복구 안전성을 위해 실제 실행 시 Per-worker 방식으로 유지됩니다.</div>' +
            '<select id="' + TRANSPORT_SETTING_ID + '" class="setting-select">' +
                '<option value="per-worker">Per-worker Session (기존값)</option>' +
                '<option value="async-pool">Async shared pool benchmark</option>' +
            '</select>';
        workerGroup.insertAdjacentElement('afterend', transportGroup);

        const poolGroup = document.createElement('div');
        poolGroup.className = 'setting-group';
        poolGroup.innerHTML =
            '<label class="setting-label">Async pool 연결 수 (성능 테스트)</label>' +
            '<div class="setting-desc">Async shared pool의 실제 curl handle 최대 수입니다. HLS worker 수와 독립적이며 ' +
            'Async 방식에서만 적용됩니다. 24는 첫 Async 테스트와 같은 기존값입니다.</div>' +
            '<select id="' + POOL_SETTING_ID + '" class="setting-select">' +
                '<option value="4">4 connections</option>' +
                '<option value="8">8 connections</option>' +
                '<option value="12">12 connections</option>' +
                '<option value="16">16 connections</option>' +
                '<option value="24">24 connections (기존 Async값)</option>' +
            '</select>';
        transportGroup.insertAdjacentElement('afterend', poolGroup);

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
        poolGroup.insertAdjacentElement('afterend', writeGroup);

        const workerSelect = workerGroup.querySelector('#' + WORKER_SETTING_ID);
        const transportSelect = transportGroup.querySelector('#' + TRANSPORT_SETTING_ID);
        const poolSelect = poolGroup.querySelector('#' + POOL_SETTING_ID);
        const writeSelect = writeGroup.querySelector('#' + WRITE_SETTING_ID);
        loadSettings(workerSelect, writeSelect, transportSelect, poolSelect);

        workerSelect.addEventListener('change', function () {
            const workers = normalizeWorkers(workerSelect.value);
            workerSelect.value = String(workers);
            saveSetting(
                { hls_workers: workers },
                'HLS worker 수를 ' + workers + '로 저장했습니다. 다음 HLS 실행부터 적용됩니다.'
            ).catch(function (err) {
                if (typeof showToast === 'function') showToast('HLS worker 수 저장 실패: ' + err, 'error');
            });
        });

        transportSelect.addEventListener('change', function () {
            const mode = normalizeTransportMode(transportSelect.value);
            transportSelect.value = mode;
            updatePoolEnabled(transportSelect, poolSelect);
            const label = mode === 'async-pool' ? 'Async shared pool benchmark' : 'Per-worker Session';
            saveSetting(
                { hls_transport_mode: mode },
                'HLS 연결 방식을 ' + label + '로 저장했습니다. 다음 HLS 실행부터 적용됩니다.'
            ).catch(function (err) {
                if (typeof showToast === 'function') showToast('HLS 연결 방식 저장 실패: ' + err, 'error');
            });
        });

        poolSelect.addEventListener('change', function () {
            const clients = normalizePoolClients(poolSelect.value);
            poolSelect.value = String(clients);
            saveSetting(
                { hls_pool_clients: clients },
                'Async pool 연결 수를 ' + clients + '로 저장했습니다. 다음 HLS 실행부터 적용됩니다.'
            ).catch(function (err) {
                if (typeof showToast === 'function') showToast('Async pool 연결 수 저장 실패: ' + err, 'error');
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
                const currentPool = document.getElementById(POOL_SETTING_ID);
                if (currentWorkers && currentWrite && currentTransport && currentPool) {
                    loadSettings(currentWorkers, currentWrite, currentTransport, currentPool);
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
