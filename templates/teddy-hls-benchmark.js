(function () {
    const SETTING_ID = 'set-hls-workers';
    const ALLOWED = [2, 4, 8];

    function normalize(value) {
        const n = Number(value);
        return ALLOWED.includes(n) ? n : 8;
    }

    function mount() {
        if (document.getElementById(SETTING_ID)) return;
        const maxConcurrent = document.getElementById('set-max-concurrent');
        if (!maxConcurrent) return;
        const anchor = maxConcurrent.closest('.setting-group');
        if (!anchor || !anchor.parentNode) return;

        const group = document.createElement('div');
        group.className = 'setting-group';
        group.innerHTML =
            '<label class="setting-label">HLS 연결 수 (성능 테스트)</label>' +
            '<div class="setting-desc">MissAV/HLS 전용 worker 수입니다. 새로 시작하는 HLS 작업부터 즉시 적용됩니다. ' +
            'Hitomi 비교용으로 2 / 4 / 8을 바꿔가며 같은 영상·같은 Proxy에서 테스트하세요.</div>' +
            '<select id="' + SETTING_ID + '" class="setting-select">' +
                '<option value="2">2 workers</option>' +
                '<option value="4">4 workers</option>' +
                '<option value="8">8 workers (기존값)</option>' +
            '</select>';
        anchor.insertAdjacentElement('afterend', group);

        const select = group.querySelector('#' + SETTING_ID);
        fetch('/api/settings')
            .then(function (r) { return r.json(); })
            .then(function (settings) {
                select.value = String(normalize(settings.hls_workers));
            })
            .catch(function () {
                select.value = '8';
            });

        select.addEventListener('change', function () {
            const workers = normalize(select.value);
            select.value = String(workers);
            fetch('/api/settings', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hls_workers: workers })
            })
            .then(function (r) { return r.json(); })
            .then(function (res) {
                if (typeof showToast === 'function') {
                    showToast('HLS 연결 수를 ' + workers + '로 저장했습니다. 새 작업부터 적용됩니다.',
                              res.status === 'success' ? 'success' : 'error');
                }
            })
            .catch(function (err) {
                if (typeof showToast === 'function') {
                    showToast('HLS 연결 수 저장 실패: ' + err, 'error');
                }
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', mount);
    } else {
        mount();
    }
})();
