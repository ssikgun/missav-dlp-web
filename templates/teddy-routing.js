(() => {
    let lastState = null;
    let resolveTimer = null;

    function modeLabel(mode) {
        return mode === 'vpn' ? 'VPN' : 'Direct';
    }

    function sourceLabel(source) {
        if (source === 'manual') return '수동 규칙';
        if (source === 'learned') return '자동 학습';
        if (source === 'override') return '이번 작업';
        return '기본';
    }

    function formatLearnedMeta(rule) {
        const count = Number(rule && rule.success_count) || 0;
        const ts = Number(rule && rule.updated_at) || 0;
        const parts = [];
        if (count) parts.push('성공 ' + count + '회');
        if (ts) parts.push(new Date(ts * 1000).toLocaleString('ko-KR'));
        return parts.join(' · ') || '자동 학습';
    }

    async function apiJson(url, options) {
        const response = await fetch(url, options || {});
        let data = {};
        try { data = await response.json(); } catch (_) {}
        if (!response.ok) throw new Error(data.message || '요청에 실패했습니다.');
        return data;
    }

    function renderManual(state) {
        const root = document.getElementById('teddyManualRules');
        if (!root) return;
        const entries = Object.entries((state && state.manual_rules) || {}).sort((a, b) => a[0].localeCompare(b[0]));
        if (!entries.length) {
            root.innerHTML = '<div class="teddy-routing-empty">수동 규칙이 없습니다.</div>';
            return;
        }
        root.innerHTML = '';
        entries.forEach(([site, mode]) => {
            const row = document.createElement('div');
            row.className = 'teddy-routing-row';

            const info = document.createElement('div');
            info.innerHTML = '<div class="teddy-routing-site"></div><div class="teddy-routing-meta">수동 규칙 · 자동 학습보다 우선</div>';
            info.querySelector('.teddy-routing-site').textContent = site;

            const select = document.createElement('select');
            select.innerHTML = '<option value="direct">Direct</option><option value="vpn">VPN</option>';
            select.value = mode;
            select.addEventListener('change', async () => {
                try {
                    await apiJson('/api/routing/manual', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ target: site, mode: select.value })
                    });
                    if (typeof showToast === 'function') showToast(site + ' → ' + modeLabel(select.value), 'success');
                    await loadState();
                } catch (error) {
                    if (typeof showToast === 'function') showToast(error.message, 'error');
                    select.value = mode;
                }
            });

            const remove = document.createElement('button');
            remove.type = 'button';
            remove.textContent = '삭제';
            remove.addEventListener('click', async () => {
                try {
                    await apiJson('/api/routing/manual', {
                        method: 'DELETE',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ target: site })
                    });
                    await loadState();
                } catch (error) {
                    if (typeof showToast === 'function') showToast(error.message, 'error');
                }
            });

            row.appendChild(info);
            row.appendChild(select);
            row.appendChild(remove);
            root.appendChild(row);
        });
    }

    function renderLearned(state) {
        const root = document.getElementById('teddyLearnedRules');
        if (!root) return;
        const entries = Object.entries((state && state.learned_rules) || {}).sort((a, b) => a[0].localeCompare(b[0]));
        if (!entries.length) {
            root.innerHTML = '<div class="teddy-routing-empty">아직 학습된 사이트가 없습니다. 새 사이트는 Direct부터 시도합니다.</div>';
            return;
        }
        root.innerHTML = '';
        entries.forEach(([site, rule]) => {
            const row = document.createElement('div');
            row.className = 'teddy-routing-row';

            const info = document.createElement('div');
            info.innerHTML = '<div class="teddy-routing-site"></div><div class="teddy-routing-meta"></div>';
            info.querySelector('.teddy-routing-site').textContent = site;
            info.querySelector('.teddy-routing-meta').textContent = formatLearnedMeta(rule);

            const mode = document.createElement('div');
            mode.className = 'teddy-routing-site';
            mode.textContent = modeLabel(rule.mode);

            const forget = document.createElement('button');
            forget.type = 'button';
            forget.textContent = '학습 삭제';
            forget.addEventListener('click', async () => {
                try {
                    await apiJson('/api/routing/learned', {
                        method: 'DELETE',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ target: site })
                    });
                    await loadState();
                    scheduleResolve();
                } catch (error) {
                    if (typeof showToast === 'function') showToast(error.message, 'error');
                }
            });

            row.appendChild(info);
            row.appendChild(mode);
            row.appendChild(forget);
            root.appendChild(row);
        });
    }

    async function loadState() {
        try {
            lastState = await apiJson('/api/routing');
            renderManual(lastState);
            renderLearned(lastState);
        } catch (error) {
            if (typeof showToast === 'function') showToast('네트워크 규칙 조회 실패: ' + error.message, 'error');
        }
    }

    async function addManualRule() {
        const target = document.getElementById('teddyRoutingTarget');
        const mode = document.getElementById('teddyRoutingMode');
        if (!target || !mode || !target.value.trim()) return;
        try {
            const result = await apiJson('/api/routing/manual', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target: target.value.trim(), mode: mode.value })
            });
            target.value = '';
            if (typeof showToast === 'function') showToast(result.site + ' 규칙을 저장했습니다.', 'success');
            await loadState();
            scheduleResolve();
        } catch (error) {
            if (typeof showToast === 'function') showToast(error.message, 'error');
        }
    }

    async function resolveCurrent() {
        const input = document.getElementById('url');
        const select = document.getElementById('downloadNetworkMode');
        const hint = document.getElementById('teddyRouteHint');
        if (!input || !select || !hint) return;

        if (select.value === 'direct') {
            hint.textContent = '이번 작업만 Direct로 고정 · 자동 학습값은 변경하지 않음';
            return;
        }
        if (select.value === 'vpn') {
            hint.textContent = '이번 작업만 VPN으로 고정 · 자동 학습값은 변경하지 않음';
            return;
        }
        const url = input.value.trim();
        if (!url) {
            hint.textContent = '자동 · 새 사이트는 Direct 우선 → 네트워크 오류 시 VPN 재시도';
            return;
        }
        try {
            const result = await apiJson('/api/routing/resolve?mode=auto&url=' + encodeURIComponent(url));
            const label = modeLabel(result.mode);
            hint.textContent = '자동 선택: ' + label + ' · ' + sourceLabel(result.source) + (result.fixed ? '' : ' · 실패 시 반대 경로 재시도');
        } catch (_) {
            hint.textContent = '자동 · 새 사이트는 Direct 우선 → 네트워크 오류 시 VPN 재시도';
        }
    }

    function scheduleResolve() {
        clearTimeout(resolveTimer);
        resolveTimer = setTimeout(resolveCurrent, 250);
    }

    const add = document.getElementById('teddyRoutingAdd');
    if (add) add.addEventListener('click', addManualRule);

    const target = document.getElementById('teddyRoutingTarget');
    if (target) {
        target.addEventListener('keydown', event => {
            if (event.key === 'Enter') {
                event.preventDefault();
                addManualRule();
            }
        });
    }

    const input = document.getElementById('url');
    const select = document.getElementById('downloadNetworkMode');
    if (input) input.addEventListener('input', scheduleResolve);
    if (select) select.addEventListener('change', resolveCurrent);

    const settingsButton = document.querySelector('.sidebar-btn[data-page="settings"]');
    if (settingsButton) settingsButton.addEventListener('click', loadState);

    loadState();
    resolveCurrent();
})();
