(() => {
    const button = document.querySelector('.sidebar-btn[data-page="browser"]');
    const frame = document.getElementById('teddyBrowserFrame');
    if (!button || !frame) return;

    function lanBrowserUrl() {
        const rawHost = window.location.hostname || 'localhost';
        const host = rawHost.includes(':') ? `[${rawHost}]` : rawHost;
        return `http://${host}:58001/`;
    }

    function showMessage(message) {
        frame.removeAttribute('src');
        frame.style.display = 'none';
        const shell = frame.parentElement;
        if (!shell) return;
        let note = shell.querySelector('.teddy-browser-message');
        if (!note) {
            note = document.createElement('div');
            note.className = 'teddy-browser-message';
            note.style.cssText = [
                'height:100%',
                'display:flex',
                'align-items:center',
                'justify-content:center',
                'padding:32px',
                'box-sizing:border-box',
                'text-align:center',
                'color:#cbd5e1',
                'font:600 14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif',
            ].join(';');
            shell.appendChild(note);
        }
        note.textContent = message;
    }

    async function resolveBrowserUrl() {
        let configured = '';
        try {
            const response = await fetch('/api/browser/config', { cache: 'no-store' });
            if (response.ok) {
                const payload = await response.json();
                configured = String(payload && payload.url ? payload.url : '').trim();
            }
        } catch (_) {}

        if (configured) {
            try {
                const target = new URL(configured, window.location.href);
                if (window.location.protocol === 'https:' && target.protocol !== 'https:') {
                    return {
                        url: '',
                        error: '외부 HTTPS 접속에서는 VPN Browser URL도 HTTPS여야 합니다. TEDDY_BROWSER_URL을 HTTPS 주소로 설정하세요.',
                    };
                }
                return { url: target.toString(), error: '' };
            } catch (_) {
                return { url: '', error: 'TEDDY_BROWSER_URL 설정값이 올바른 URL이 아닙니다.' };
            }
        }

        if (window.location.protocol === 'https:') {
            return {
                url: '',
                error: '외부 HTTPS 접속용 VPN Browser 주소가 설정되지 않았습니다. TEDDY_BROWSER_URL을 별도 HTTPS 프록시 주소로 설정하세요.',
            };
        }

        return { url: lanBrowserUrl(), error: '' };
    }

    async function ensureBrowserLoaded() {
        if (frame.dataset.loaded === '1') return;
        const resolved = await resolveBrowserUrl();
        if (!resolved.url) {
            showMessage(resolved.error || 'VPN Browser 주소를 확인할 수 없습니다.');
            return;
        }
        const note = frame.parentElement?.querySelector('.teddy-browser-message');
        if (note) note.remove();
        frame.style.display = 'block';
        frame.src = resolved.url;
        frame.dataset.loaded = '1';
    }

    button.addEventListener('click', ensureBrowserLoaded);

    if (document.getElementById('page-browser')?.classList.contains('active')) {
        ensureBrowserLoaded();
    }
})();
