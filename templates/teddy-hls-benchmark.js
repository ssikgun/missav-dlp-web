(function () {
    const PRESET_SETTING_ID = 'set-hls-performance-preset';
    const PRESET_HELP_ID = 'set-hls-performance-help';
    const DIAGNOSTIC_VALUE = 'diagnostic';

    const PRESETS = {
        fastest: {
            label: '🚀 최고속',
            workers: 24,
            pool: 24,
            description: '동시 다운로드 24개 · 연결 풀 24개 · Async 공유 연결 · HTTP/1.1 · 안전한 임시파일 저장',
            note: '최대 처리량을 우선합니다. Proxy와 서버에 가장 많은 동시 요청을 사용합니다.'
        },
        balanced: {
            label: '⚖️ 균형',
            workers: 16,
            pool: 16,
            description: '동시 다운로드 16개 · 연결 풀 16개 · Async 공유 연결 · HTTP/1.1 · 안전한 임시파일 저장',
            note: '속도를 높게 유지하면서 Proxy와 서버의 동시 요청 부담을 줄입니다.'
        },
        conservative: {
            label: '🛡️ 보수',
            workers: 8,
            pool: 8,
            description: '동시 다운로드 8개 · 연결 풀 8개 · Async 공유 연결 · HTTP/1.1 · 안전한 임시파일 저장',
            note: '동시 요청 부담을 낮게 유지합니다.'
        },
        stable: {
            label: '🧘 안정',
            workers: 4,
            pool: 4,
            description: '동시 다운로드 4개 · 연결 풀 4개 · Async 공유 연결 · HTTP/1.1 · 안전한 임시파일 저장',
            note: '동시 요청을 가장 낮게 유지해 CDN/VPN 경로가 불안정할 때 재시도 부담을 줄입니다.'
        }
    };

    function presetPayload(name) {
        const preset = PRESETS[name] || PRESETS.balanced;
        return {
            hls_workers: preset.workers,
            hls_pool_clients: preset.pool,
            hls_transport_mode: 'async-pool',
            hls_http_version: 'v1',
            hls_write_mode: 'parts'
        };
    }

    function inferPreset(settings) {
        const workers = Number(settings.hls_workers);
        const pool = Number(settings.hls_pool_clients);
        const transport = String(settings.hls_transport_mode || '').toLowerCase();
        const httpVersion = String(settings.hls_http_version || '').toLowerCase();
        const writeMode = String(settings.hls_write_mode || '').toLowerCase();

        for (const name of Object.keys(PRESETS)) {
            const preset = PRESETS[name];
            if (
                workers === preset.workers &&
                pool === preset.pool &&
                transport === 'async-pool' &&
                httpVersion === 'v1' &&
                writeMode === 'parts'
            ) {
                return name;
            }
        }
        return DIAGNOSTIC_VALUE;
    }

    function ensureDiagnosticOption(select, enabled) {
        let option = select.querySelector('option[value="' + DIAGNOSTIC_VALUE + '"]');
        if (enabled && !option) {
            option = document.createElement('option');
            option.value = DIAGNOSTIC_VALUE;
            option.textContent = '직접 설정됨 (터미널/진단)';
            option.disabled = true;
            select.appendChild(option);
        } else if (!enabled && option) {
            option.remove();
        }
    }

    function updateHelp(name, help) {
        if (name === DIAGNOSTIC_VALUE) {
            help.innerHTML =
                '<strong>직접 설정된 HLS 값이 사용 중입니다.</strong><br>' +
                '터미널/API에서 성능 진단용 세부 설정이 변경된 상태입니다. 위 모드 중 하나를 선택하면 검증된 프리셋으로 한 번에 정리됩니다.';
            return;
        }

        const preset = PRESETS[name] || PRESETS.balanced;
        help.innerHTML =
            '<strong>' + preset.label + ' 모드</strong><br>' +
            preset.description + '<br>' +
            preset.note + '<br>' +
            '<span style="opacity:.78">설정은 다음 HLS 다운로드 또는 일시정지 후 재개부터 적용됩니다. VPN은 기존 안전 정책에 따라 Per-worker 방식으로 실행될 수 있습니다.</span>';
    }

    function loadSettings(select, help) {
        return fetch('/api/settings')
            .then(function (r) { return r.json(); })
            .then(function (settings) {
                const name = inferPreset(settings);
                ensureDiagnosticOption(select, name === DIAGNOSTIC_VALUE);
                select.value = name;
                updateHelp(name, help);
            })
            .catch(function () {
                ensureDiagnosticOption(select, false);
                select.value = 'balanced';
                updateHelp('balanced', help);
            });
    }

    function savePreset(name) {
        return fetch('/api/settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(presetPayload(name))
        })
        .then(function (r) { return r.json(); })
        .then(function (res) {
            if (res.status !== 'success') {
                throw new Error(res.message || '설정 저장 실패');
            }
            return res;
        });
    }

    function mount() {
        if (document.getElementById(PRESET_SETTING_ID)) return;
        const maxConcurrent = document.getElementById('set-max-concurrent');
        if (!maxConcurrent) return;
        const anchor = maxConcurrent.closest('.setting-group');
        if (!anchor || !anchor.parentNode) return;

        // "기본값 복원"도 실사용 기본인 균형 프리셋으로 정리한다.
        // 세부 키는 backend/API에 그대로 남겨 성능 진단 시 직접 변경할 수 있다.
        if (typeof defaultSettings !== 'undefined' && defaultSettings) {
            defaultSettings.hls_workers = 16;
            defaultSettings.hls_pool_clients = 16;
            defaultSettings.hls_transport_mode = 'async-pool';
            defaultSettings.hls_http_version = 'v1';
            defaultSettings.hls_write_mode = 'parts';
        }

        const presetGroup = document.createElement('div');
        presetGroup.className = 'setting-group';
        presetGroup.innerHTML =
            '<label class="setting-label">HLS 성능 모드</label>' +
            '<div class="setting-desc">검증된 HLS 설정 조합을 한 번에 적용합니다. 세부 성능 옵션은 일반 설정에서 숨기고 진단용 backend 설정으로 유지합니다.</div>' +
            '<select id="' + PRESET_SETTING_ID + '" class="setting-select">' +
                '<option value="fastest">🚀 최고속</option>' +
                '<option value="balanced">⚖️ 균형 (권장)</option>' +
                '<option value="conservative">🛡️ 보수</option>' +
                '<option value="stable">🧘 안정</option>' +
            '</select>' +
            '<div id="' + PRESET_HELP_ID + '" class="setting-desc" style="margin-top:8px"></div>';
        anchor.insertAdjacentElement('afterend', presetGroup);

        const select = presetGroup.querySelector('#' + PRESET_SETTING_ID);
        const help = presetGroup.querySelector('#' + PRESET_HELP_ID);
        loadSettings(select, help);

        select.addEventListener('change', function () {
            const name = select.value;
            if (!PRESETS[name]) return;

            savePreset(name)
                .then(function () {
                    ensureDiagnosticOption(select, false);
                    select.value = name;
                    updateHelp(name, help);
                    if (typeof showToast === 'function') {
                        showToast(PRESETS[name].label + ' HLS 모드를 저장했습니다. 다음 HLS 실행부터 적용됩니다.', 'success');
                    }
                })
                .catch(function (err) {
                    if (typeof showToast === 'function') showToast('HLS 성능 모드 저장 실패: ' + err, 'error');
                    loadSettings(select, help);
                });
        });

        // Existing settings navigation/reset calls loadSettingsUI(). Refresh the
        // separately injected preset at the same time without touching upstream UI.
        if (typeof window.loadSettingsUI === 'function' && !window.__teddyHlsLoadWrapped) {
            const originalLoadSettingsUI = window.loadSettingsUI;
            window.loadSettingsUI = function () {
                const result = originalLoadSettingsUI.apply(this, arguments);
                const currentSelect = document.getElementById(PRESET_SETTING_ID);
                const currentHelp = document.getElementById(PRESET_HELP_ID);
                if (currentSelect && currentHelp) loadSettings(currentSelect, currentHelp);
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
