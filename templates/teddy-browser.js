(() => {
    const button = document.querySelector('.sidebar-btn[data-page="browser"]');
    const frame = document.getElementById('teddyBrowserFrame');
    const mobileMedia = window.matchMedia
        ? window.matchMedia('(max-width: 768px), (max-width: 1024px) and (hover: none) and (pointer: coarse)')
        : null;
    if (!button || !frame) return;

    function isMobileUI() {
        return Boolean(mobileMedia && mobileMedia.matches);
    }

    function lanBrowserUrl(mobile) {
        const rawHost = window.location.hostname || 'localhost';
        const host = rawHost.includes(':') ? `[${rawHost}]` : rawHost;
        return `http://${host}:${mobile ? '58003' : '58001'}/`;
    }

    function showMessage(message) {
        frame.removeAttribute('src');
        delete frame.dataset.loadedUrl;
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
        const mobile = isMobileUI();
        const envName = mobile ? 'TEDDY_MOBILE_BROWSER_URL' : 'TEDDY_BROWSER_URL';
        let configured = '';

        try {
            const response = await fetch('/api/browser/config', { cache: 'no-store' });
            if (response.ok) {
                const payload = await response.json();
                const raw = mobile ? payload?.mobile_url : payload?.url;
                configured = String(raw || '').trim();
            }
        } catch (_) {}

        if (configured) {
            try {
                const target = new URL(configured, window.location.href);
                if (window.location.protocol === 'https:' && target.protocol !== 'https:') {
                    return {
                        url: '',
                        error: `외부 HTTPS 접속에서는 VPN Browser URL도 HTTPS여야 합니다. ${envName}을 HTTPS 주소로 설정하세요.`,
                    };
                }
                return { url: target.toString(), error: '' };
            } catch (_) {
                return { url: '', error: `${envName} 설정값이 올바른 URL이 아닙니다.` };
            }
        }

        if (window.location.protocol === 'https:') {
            return {
                url: '',
                error: `외부 HTTPS 접속용 VPN Browser 주소가 설정되지 않았습니다. ${envName}을 별도 HTTPS 프록시 주소로 설정하세요.`,
            };
        }

        return { url: lanBrowserUrl(mobile), error: '' };
    }

    async function ensureBrowserLoaded() {
        const resolved = await resolveBrowserUrl();
        if (!resolved.url) {
            showMessage(resolved.error || 'VPN Browser 주소를 확인할 수 없습니다.');
            return;
        }

        if (frame.dataset.loadedUrl === resolved.url) return;

        const note = frame.parentElement?.querySelector('.teddy-browser-message');
        if (note) note.remove();
        frame.style.display = 'block';
        frame.src = resolved.url;
        frame.dataset.loadedUrl = resolved.url;
    }

    button.addEventListener('click', ensureBrowserLoaded);

    if (document.getElementById('page-browser')?.classList.contains('active')) {
        ensureBrowserLoaded();
    }
})();
