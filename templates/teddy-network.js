(() => {
    let panel = null;
    let rotateButton = null;
    let autoToggle = null;
    let rotating = false;
    let savingAuto = false;

    function ensurePanel() {
        if (panel) return panel;
        const stats = document.getElementById('stats');
        if (!stats || !stats.parentNode) return null;

        panel = document.createElement('div');
        panel.className = 'teddy-network-panel';
        panel.innerHTML =
            '<div class="teddy-network-main">' +
                '<div class="teddy-network-title">' +
                    '<span class="teddy-network-dot"></span>' +
                    '<span class="teddy-network-label">VPN 상태 확인 중…</span>' +
                '</div>' +
                '<div class="teddy-network-meta"></div>' +
                '<div class="teddy-network-recovery-meta"></div>' +
            '</div>' +
            '<div class="teddy-network-actions">' +
                '<label class="teddy-network-auto" title="반복적인 네트워크 오류가 발생하면 VPN IP를 자동 변경합니다.">' +
                    '<input class="teddy-network-auto-input" type="checkbox">' +
                    '<span>자동 복구</span>' +
                '</label>' +
                '<button class="teddy-network-button" type="button" disabled>IP 변경</button>' +
            '</div>';
        stats.parentNode.insertBefore(panel, stats);
        rotateButton = panel.querySelector('.teddy-network-button');
        autoToggle = panel.querySelector('.teddy-network-auto-input');
        rotateButton.addEventListener('click', rotateIp);
        autoToggle.addEventListener('change', setAutoRecovery);
        return panel;
    }

    function formatRecent(ts) {
        const value = Number(ts) || 0;
        if (!value) return '없음';
        try {
            return new Date(value * 1000).toLocaleString('ko-KR', {
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
            });
        } catch (_) {
            return '있음';
        }
    }

    function setStatus(data) {
        if (!ensurePanel()) return;
        const dot = panel.querySelector('.teddy-network-dot');
        const label = panel.querySelector('.teddy-network-label');
        const meta = panel.querySelector('.teddy-network-meta');
        const recoveryMeta = panel.querySelector('.teddy-network-recovery-meta');

        const controlReady = data && data.control_ready === true;
        const vpnStatus = data && data.vpn_status ? data.vpn_status : 'unknown';
        const ip = data && data.public_ip ? data.public_ip : '';
        const rotationInProgress = !!(data && data.rotation_in_progress);
        const placeParts = [];
        if (data && data.city) placeParts.push(data.city);
        if (data && data.region && data.region !== data.city) placeParts.push(data.region);
        if (data && data.country) placeParts.push(data.country);
        const place = placeParts.join(', ');

        dot.className = 'teddy-network-dot';
        if (rotationInProgress) {
            dot.classList.add('warn');
            label.textContent = 'VPN 재연결 중';
        } else if (vpnStatus === 'running' && ip) {
            dot.classList.add('ok');
            label.textContent = 'VPN 연결됨';
        } else if (!controlReady) {
            dot.classList.add('warn');
            label.textContent = ip ? 'VPN 연결됨 · 제어 설정 필요' : 'VPN 제어 설정 필요';
        } else if (vpnStatus === 'stopped') {
            dot.classList.add('error');
            label.textContent = 'VPN 중지됨';
        } else {
            dot.classList.add('warn');
            label.textContent = 'VPN 상태 확인 중';
        }

        const metaParts = [];
        if (ip) metaParts.push(ip);
        if (place) metaParts.push(place);
        if (data && data.message && !controlReady) metaParts.push(data.message);
        meta.textContent = metaParts.join(' · ') || '네트워크 정보를 가져오는 중입니다.';

        const autoEnabled = !!(data && data.auto_recovery_enabled);
        const autoCount = Number(data && data.auto_rotate_count) || 0;
        const recent = formatRecent(data && data.last_auto_rotate_at);
        const lastIp = data && data.last_auto_ip ? data.last_auto_ip : '';
        recoveryMeta.textContent =
            '자동 복구 ' + (autoEnabled ? '켜짐' : '꺼짐') +
            ' · 자동 IP 변경 ' + autoCount + '회' +
            ' · 최근 ' + recent +
            (lastIp ? ' · ' + lastIp : '');

        if (!savingAuto) {
            autoToggle.checked = autoEnabled;
        }
        autoToggle.disabled = savingAuto || !controlReady;

        const canRotate = !!(data && data.can_rotate && controlReady && !rotating && !rotationInProgress);
        rotateButton.disabled = !canRotate;
        rotateButton.textContent = (rotating || rotationInProgress) ? '변경 중…' : 'IP 변경';
        if (!controlReady) {
            rotateButton.title = 'Gluetun control API 설정이 필요합니다.';
        } else if (rotationInProgress) {
            rotateButton.title = 'VPN을 재연결하는 중입니다.';
        } else if (data && data.active_vpn_tasks > 0) {
            rotateButton.title = '먼저 진행 중인 VPN 다운로드를 일시정지하세요.';
        } else {
            rotateButton.title = 'VPN을 재연결해 새 출구 IP를 요청합니다.';
        }
    }

    async function fetchStatus() {
        try {
            const response = await fetch('/api/network/status', { cache: 'no-store' });
            const data = await response.json();
            setStatus(data);
        } catch (_) {
            setStatus({ control_ready: false, vpn_status: 'unknown', message: '상태 조회 실패' });
        }
    }

    async function setAutoRecovery() {
        if (savingAuto || !autoToggle) return;
        const enabled = !!autoToggle.checked;
        savingAuto = true;
        autoToggle.disabled = true;
        try {
            const response = await fetch('/api/network/auto-recovery', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled }),
            });
            let data = {};
            try { data = await response.json(); } catch (_) {}
            if (!response.ok) {
                autoToggle.checked = !enabled;
                if (typeof showToast === 'function') {
                    showToast(data.message || '자동 복구 설정 저장에 실패했습니다.', 'error');
                }
            } else if (typeof showToast === 'function') {
                showToast('VPN 자동 복구 ' + (enabled ? '켜짐' : '꺼짐'), 'success');
            }
        } catch (_) {
            autoToggle.checked = !enabled;
            if (typeof showToast === 'function') showToast('자동 복구 설정 요청에 실패했습니다.', 'error');
        } finally {
            savingAuto = false;
            await fetchStatus();
        }
    }

    async function rotateIp() {
        if (rotating || !rotateButton || rotateButton.disabled) return;
        rotating = true;
        rotateButton.disabled = true;
        rotateButton.textContent = '변경 중…';
        try {
            const response = await fetch('/api/network/rotate', { method: 'POST' });
            let data = {};
            try { data = await response.json(); } catch (_) {}
            if (!response.ok) {
                if (typeof showToast === 'function') {
                    showToast(data.message || 'IP 변경에 실패했습니다.', 'error');
                }
            } else if (typeof showToast === 'function') {
                const message = data.changed
                    ? `VPN IP 변경 완료: ${data.public_ip}`
                    : `VPN 재연결 완료${data.public_ip ? ': ' + data.public_ip : ''}`;
                showToast(message, 'success');
            }
        } catch (_) {
            if (typeof showToast === 'function') showToast('IP 변경 요청에 실패했습니다.', 'error');
        } finally {
            rotating = false;
            await fetchStatus();
        }
    }

    ensurePanel();
    fetchStatus();
    setInterval(fetchStatus, 12000);
})();
