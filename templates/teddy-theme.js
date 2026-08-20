(() => {
    const STORAGE_KEY = 'teddy-theme';
    const root = document.documentElement;

    function systemTheme() {
        return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
            ? 'dark'
            : 'light';
    }

    function savedTheme() {
        const saved = localStorage.getItem(STORAGE_KEY);
        return saved === 'dark' || saved === 'light' ? saved : null;
    }

    function applyTheme(theme, persist) {
        const next = theme === 'dark' ? 'dark' : 'light';
        root.dataset.theme = next;
        if (persist) {
            localStorage.setItem(STORAGE_KEY, next);
        }
        const button = document.getElementById('teddy-theme-toggle');
        if (button) {
            const isDark = next === 'dark';
            button.textContent = isDark ? '☀' : '☾';
            button.title = isDark ? 'Day 모드로 전환' : 'Night 모드로 전환';
            button.setAttribute('aria-label', button.title);
        }
    }

    function installButton() {
        const sidebar = document.querySelector('.sidebar');
        if (!sidebar || document.getElementById('teddy-theme-toggle')) return;

        const settingsButton = sidebar.querySelector('[data-page="settings"]');
        const button = document.createElement('button');
        button.id = 'teddy-theme-toggle';
        button.className = 'sidebar-btn teddy-theme-toggle';
        button.type = 'button';
        button.addEventListener('click', () => {
            const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
            applyTheme(next, true);
        });

        if (settingsButton) {
            sidebar.insertBefore(button, settingsButton);
        } else {
            sidebar.appendChild(button);
        }
        applyTheme(root.dataset.theme || savedTheme() || systemTheme(), false);
    }

    applyTheme(savedTheme() || systemTheme(), false);

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', installButton, { once: true });
    } else {
        installButton();
    }

    const media = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
    if (media && media.addEventListener) {
        media.addEventListener('change', event => {
            if (!savedTheme()) {
                applyTheme(event.matches ? 'dark' : 'light', false);
            }
        });
    }
})();
