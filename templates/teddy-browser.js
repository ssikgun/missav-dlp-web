(() => {
    const button = document.querySelector('.sidebar-btn[data-page="browser"]');
    const frame = document.getElementById('teddyBrowserFrame');
    if (!button || !frame) return;

    function browserUrl() {
        const rawHost = window.location.hostname || 'localhost';
        const host = rawHost.includes(':') ? `[${rawHost}]` : rawHost;
        return `http://${host}:58001/`;
    }

    function ensureBrowserLoaded() {
        if (frame.dataset.loaded === '1') return;
        frame.src = browserUrl();
        frame.dataset.loaded = '1';
    }

    button.addEventListener('click', ensureBrowserLoaded);

    if (document.getElementById('page-browser')?.classList.contains('active')) {
        ensureBrowserLoaded();
    }
})();
