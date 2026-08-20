(() => {
    let mounted = false;
    let refreshing = false;

    function fmtTime(ts) {
        const value = Number(ts) || 0;
        if (!value) return '없음';
        try {
            return new Date(value * 1000).toLocaleString('ko-KR');
        } catch (_) {
            return '있음';
        }
    }

    async function apiJson(url, options) {
        const response = await fetch(url, options || {});
        let data = {};
        try { data = await response.json(); } catch (_) {}
        if (!response.ok) throw new Error(data.message || '요청에 실패했습니다.');
        return data;
    }

    function ensurePanel() {
        if (mounted) return document.getElementById('teddyProxyPoolPanel');
        const mount = document.getElementById('teddyProxyPoolMount');
        if (!mount) return null;
        mount.innerHTML = `
            <div class="teddy-proxy-panel" id="teddyProxyPoolPanel">
                <div class="teddy-proxy-head">
                    <div>
                        <div class="teddy-proxy-title">무료 Proxy Pool</div>
                        <div class="teddy-proxy-sub">공개 HTTP 프록시를 자동 수집한 뒤 HTTPS 실제 연결 검사를 통과한 후보만 사용합니다.</div>
                    </div>
                    <label class="teddy-proxy-toggle">
                        <input id="teddyProxyEnabled" type="checkbox">
                        <span>자동 사용</span>
                    </label>
                </div>
                <div class="teddy-proxy-status" id="teddyProxyStatus">상태 확인 중…</div>
                <div class="teddy-proxy-current" id="teddyProxyCurrent"></div>
                <div class="teddy-proxy-actions">
                    <button type="button" id="teddyProxyRefresh">지금 갱신</button>
                </div>
                <div class="teddy-proxy-manual-title">수동 프록시 추가 <span>선택 사항</span></div>
                <div class="teddy-proxy-manual-add">
                    <input id="teddyProxyManualInput" type="text" placeholder="1.2.3.4:8080 또는 http://1.2.3.4:8080">
                    <button type="button" id="teddyProxyManualAdd">추가</button>
                </div>
                <div class="teddy-proxy-manual-list" id="teddyProxyManualList"></div>
                <div class="teddy-proxy-note">공개 다운로드 전용 · 로그인/쿠키/개인정보가 필요한 요청에는 사용하지 않는 것을 권장합니다.</div>
            </div>`;
        mounted = true;

        document.getElementById('teddyProxyEnabled').addEventListener('change', toggleEnabled);
        document.getElementById('teddyProxyRefresh').addEventListener('click', refreshPool);
        document.getElementById('teddyProxyManualAdd').addEventListener('click', addManual);
        document.getElementById('teddyProxyManualInput').addEventListener('keydown', event => {
            if (event.key === 'Enter') {
                event.preventDefault();
                addManual();
            }
        });
        return document.getElementById('teddyProxyPoolPanel');
    }

    function renderManual(items) {
        const root = document.getElementById('teddyProxyManualList');
        if (!root) return;
        if (!items || !items.length) {
            root.innerHTML = '<div class="teddy-proxy-empty">수동 프록시 없음 · 자동 수집만 사용합니다.</div>';
            return;
        }
        root.innerHTML = '';
        items.forEach(proxy => {
            const row = document.createElement('div');
            row.className = 'teddy-proxy-manual-row';
            const text = document.createElement('code');
            text.textContent = proxy;
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = '삭제';
            button.addEventListener('click', async () => {
                try {
                    await apiJson('/api/proxy/manual', {
                        method: 'DELETE',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ proxy }),
                    });
                    await loadStatus();
                } catch (error) {
                    if (typeof showToast === 'function') showToast(error.message, 'error');
                }
            });
            row.appendChild(text);
            row.appendChild(button);
            root.appendChild(row);
        });
    }

    function render(data) {
        if (!ensurePanel()) return;
        const enabled = !!(data && data.enabled);
        const ready = !!(data && data.ready);
        const isRefreshing = !!(data && data.refreshing);
        const candidates = Number(data && data.candidate_count) || 0;
        const healthy = Number(data && data.healthy_count) || 0;
        const latency = Number(data && data.current_latency_ms) || 0;
        const current = data && data.current_proxy ? data.current_proxy : '';
        const exitIp = data && data.current_exit_ip ? data.current_exit_ip : '';
        const source = data && data.current_source ? data.current_source : '';
        const switches = Number(data && data.proxy_switch_count) || 0;
        const lastRefresh = fmtTime(data && data.last_refresh_at);

        const toggle = document.getElementById('teddyProxyEnabled');
        toggle.checked = enabled;

        const status = document.getElementById('teddyProxyStatus');
        if (!enabled) {
            status.textContent = '꺼짐 · 자동 경로는 Direct → VPN으로 동작합니다.';
        } else if (isRefreshing) {
            status.textContent = `갱신 중… · 현재 정상 ${healthy}개 / 후보 ${candidates}개`;
        } else if (ready) {
            status.textContent = `정상 ${healthy}개 / 후보 ${candidates}개 · 마지막 갱신 ${lastRefresh} · 자동 교체 ${switches}회`;
        } else {
            status.textContent = `사용 가능한 프록시 없음 · 마지막 갱신 ${lastRefresh}` + (data && data.last_error ? ` · ${data.last_error}` : '');
        }

        const currentEl = document.getElementById('teddyProxyCurrent');
        currentEl.textContent = current
            ? `현재 ${current}${latency ? ` · ${latency}ms` : ''}${exitIp ? ` · 출구 ${exitIp}` : ''}${source ? ` · ${source}` : ''}`
            : '현재 선택된 프록시 없음';

        const refresh = document.getElementById('teddyProxyRefresh');
        refresh.disabled = isRefreshing || refreshing;
        refresh.textContent = (isRefreshing || refreshing) ? '갱신 중…' : '지금 갱신';
        renderManual((data && data.manual_proxies) || []);
    }

    async function loadStatus() {
        try {
            const data = await apiJson('/api/proxy/status');
            render(data);
        } catch (error) {
            if (ensurePanel()) {
                document.getElementById('teddyProxyStatus').textContent = 'Proxy Pool 상태 조회 실패: ' + error.message;
            }
        }
    }

    async function toggleEnabled(event) {
        const enabled = !!event.target.checked;
        event.target.disabled = true;
        try {
            await apiJson('/api/proxy/enabled', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled }),
            });
            if (typeof showToast === 'function') showToast('무료 Proxy Pool ' + (enabled ? '켜짐' : '꺼짐'), 'success');
        } catch (error) {
            event.target.checked = !enabled;
            if (typeof showToast === 'function') showToast(error.message, 'error');
        } finally {
            event.target.disabled = false;
            await loadStatus();
        }
    }

    async function refreshPool() {
        if (refreshing) return;
        refreshing = true;
        render({ ...(await safeStatus()), refreshing: true });
        try {
            const data = await apiJson('/api/proxy/refresh', { method: 'POST' });
            if (typeof showToast === 'function') showToast(data.message || '무료 프록시 갱신을 시작했습니다.', 'success');
        } catch (error) {
            if (typeof showToast === 'function') showToast(error.message, 'error');
        } finally {
            refreshing = false;
            setTimeout(loadStatus, 1200);
        }
    }

    async function safeStatus() {
        try { return await apiJson('/api/proxy/status'); } catch (_) { return {}; }
    }

    async function addManual() {
        const input = document.getElementById('teddyProxyManualInput');
        if (!input || !input.value.trim()) return;
        try {
            const result = await apiJson('/api/proxy/manual', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ proxies: input.value.trim() }),
            });
            if (!result.count) throw new Error('유효한 공인 IP 프록시를 찾지 못했습니다.');
            input.value = '';
            if (typeof showToast === 'function') showToast('수동 프록시를 추가했습니다.', 'success');
            await loadStatus();
        } catch (error) {
            if (typeof showToast === 'function') showToast(error.message, 'error');
        }
    }

    ensurePanel();
    loadStatus();
    setInterval(loadStatus, 15000);
})();
