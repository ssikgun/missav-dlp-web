(() => {
    const STORAGE_KEY = 'teddy-theme';
    const root = document.documentElement;
    const mobileMedia = window.matchMedia
        ? window.matchMedia('(max-width: 768px), (max-width: 1024px) and (hover: none) and (pointer: coarse)')
        : null;

    function isMobileUI() {
        return Boolean(mobileMedia && mobileMedia.matches);
    }

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

    function removeButton() {
        document.getElementById('teddy-theme-toggle')?.remove();
    }

    function installButton() {
        if (isMobileUI()) {
            removeButton();
            return;
        }

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
    }

    function syncTheme() {
        if (isMobileUI()) {
            applyTheme(systemTheme(), false);
            removeButton();
            return;
        }
        applyTheme(savedTheme() || systemTheme(), false);
    }

    syncTheme();

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            syncTheme();
            installButton();
        }, { once: true });
    } else {
        installButton();
    }

    const colorMedia = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
    if (colorMedia && colorMedia.addEventListener) {
        colorMedia.addEventListener('change', event => {
            if (isMobileUI() || !savedTheme()) {
                applyTheme(event.matches ? 'dark' : 'light', false);
            }
        });
    }

    if (mobileMedia && mobileMedia.addEventListener) {
        mobileMedia.addEventListener('change', () => {
            syncTheme();
            installButton();
        });
    }
})();
