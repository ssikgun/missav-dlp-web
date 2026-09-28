(function () {
    'use strict';

    const page = document.getElementById('page-library');
    const tab = document.querySelector('.sidebar-btn[data-page="library"]');
    const list = document.getElementById('libraryList');
    const status = document.getElementById('libraryStatus');
    const summary = document.getElementById('librarySummary');
    const search = document.getElementById('librarySearch');
    const filter = document.getElementById('libraryFilter');
    const sort = document.getElementById('librarySort');
    if (!page || !tab || !list || !status || !summary || !search || !filter || !sort) return;

    let debounceTimer = null;
    let requestSerial = 0;

    function escapeHtml(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, ch => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        })[ch]);
    }

    function formatBytes(bytes) {
        if (typeof bytes !== 'number' || !Number.isFinite(bytes) || bytes < 0) return null;
        const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
        let value = bytes;
        let unit = 0;
        while (value >= 1024 && unit < units.length - 1) {
            value /= 1024;
            unit += 1;
        }
        return `${value.toFixed(unit === 0 || value >= 100 ? 0 : 1)} ${units[unit]}`;
    }

    function subtitleLabel(item) {
        switch (item.ko_status) {
            case 'VALID': return '📝 한국어 자막';
            case 'ABSENT': return '📭 자막 없음';
            case 'UNRESOLVED': return `🧩 자막 미해결${item.unresolved_label ? ` · ${escapeHtml(item.unresolved_label)}` : ''}`;
            default: return '⚠️ 자막 상태 확인 필요';
        }
    }

    function jellyfinLabel(state) {
        if (state === 'RECOGNIZED') return '🎞️ Jellyfin 인식';
        if (state === 'ABSENT') return '📺 Jellyfin 미인식';
        return '⚠️ Jellyfin 상태 확인 필요';
    }

    function dateLabel(item) {
        return item.nas_added_date ? `📅 ${escapeHtml(item.nas_added_date)}` : '📅 추가 날짜 확인 불가';
    }

    function sizeLabel(item) {
        const size = formatBytes(item.managed_size_bytes);
        return size && item.size_status === 'KNOWN' ? `💾 ${size}` : '💾 용량 확인 필요';
    }

    function renderSummary(data) {
        const value = data || {};
        const total = Number(value.total_titles) || 0;
        const size = formatBytes(value.library_known_total_bytes);
        const sizeText = value.size_complete && size
            ? `💾 전체 라이브러리 ${size}`
            : `💾 확인된 용량 ${size || '계산 불가'} · ${Number(value.size_unknown_count) || 0}개 확인 필요`;
        summary.innerHTML = `<div class="library-summary-text">
            <span>🎬 전체 ${total.toLocaleString()}작품</span>
            <span>📝 한국어 자막 ${Number(value.ko_present_count) || 0}</span>
            <span>🧩 자막 미해결 ${Number(value.unresolved_count) || 0}</span>
            <span>📭 자막 없음 ${Number(value.no_subtitle_count) || 0}</span>
            <span>${sizeText}</span>
        </div>`;
    }

    function detailCell(label, value) {
        return `<div class="discovery-detail-block"><div class="discovery-detail-label">${label}</div><div class="discovery-detail-value library-detail-value">${value || '확인 불가'}</div></div>`;
    }

    function renderItem(item) {
        const dvd = escapeHtml(item.dvd_id);
        const title = escapeHtml(item.title || '제목 정보 없음');
        const maker = escapeHtml(item.maker || '정보 없음');
        const release = escapeHtml(item.release_date || '출시일 확인 불가');
        const managedPath = escapeHtml(item.managed_relative_path || '정식 경로 확인 필요');
        const date = dateLabel(item);
        const size = sizeLabel(item);
        const subtitle = subtitleLabel(item);
        const jellyfin = jellyfinLabel(item.jellyfin_state);
        const coverUrl = `/api/discovery/media/cover/${encodeURIComponent(item.dvd_id || '')}`;
        const provenance = item.nas_added_date
            ? 'Organizer 생성일과 완료일이 같은 KST 날짜로 확인됨 · 정확한 배치 시각은 아님'
            : '실제 NAS 최종 배치일을 확인할 수 있는 기록이 없습니다.';
        const stage12 = item.stage12_status ? escapeHtml(item.stage12_status) : 'Stage12 기록 없음';
        const unresolved = item.unresolved_label ? escapeHtml(item.unresolved_label) : (item.unresolved_reason_code ? '자막 상태 확인 필요' : '해당 없음');
        const mismatch = item.mismatch ? '⚠️ 경로 또는 identity 확인 필요' : '확인된 불일치 없음';
        const bytes = formatBytes(item.managed_size_bytes);
        const rawBytes = item.size_status === 'KNOWN' && typeof item.managed_size_bytes === 'number'
            ? `${item.managed_size_bytes.toLocaleString()} bytes` : '용량 확인 필요';
        const coverAlt = `${dvd} cover`;
        return `<details class="discovery-row library-row">
            <summary class="discovery-row-summary library-row-summary">
                <span class="library-cover"><img loading="lazy" src="${coverUrl}" alt="${escapeHtml(coverAlt)}" onerror="this.remove();this.parentElement.innerHTML='<span class=&quot;library-cover-placeholder&quot;>포스터 없음</span>'"></span>
                <span class="discovery-id">${dvd}</span>
                <span class="library-summary-main"><span class="library-summary-title">${title}</span><span class="library-summary-meta"><span>📆 ${release}</span><span>${date}</span><span>${size}</span></span></span>
                <span class="library-row-side"><span class="library-badges"><span class="library-badge">${subtitle}</span><span class="library-badge">${jellyfin}</span></span><button type="button" class="library-play-button" data-play-dvd="${dvd}">▶️ 재생</button></span>
            </summary>
            <div class="discovery-detail library-detail"><div class="discovery-detail-grid library-detail-grid">
                ${detailCell('DVD-ID', dvd)}${detailCell('작품명', title)}${detailCell('제작사', maker)}
                ${detailCell('출시일', release)}${detailCell('관리 경로', managedPath)}${detailCell('NAS 추가일', `${date}<br><small>${provenance}</small>`)}
                ${detailCell('작품 전체 용량', `${size}<br><small>${rawBytes}</small>`)}${detailCell('자막 상태', subtitle)}${detailCell('Stage12 종단 상태', stage12)}
                ${detailCell('미해결 사유', unresolved)}${detailCell('Jellyfin 상태', jellyfin)}${detailCell('경로/identity 상태', mismatch)}
            </div></div>
        </details>`;
    }

    function queryUrl() {
        const params = new URLSearchParams();
        const q = search.value.trim();
        if (q) params.set('q', q);
        const selected = filter.value;
        if (selected === 'ko-present') params.set('ko', 'present');
        else if (selected === 'ko-absent') params.set('ko', 'absent');
        else if (selected === 'unresolved') params.set('unresolved', 'true');
        else if (selected === 'mismatch') params.set('mismatch', 'true');
        const [sortBy, order] = sort.value.split(':');
        params.set('sort', sortBy);
        params.set('order', order);
        return `/api/library?${params.toString()}`;
    }

    async function loadLibrary() {
        const serial = ++requestSerial;
        status.textContent = '라이브러리를 불러오는 중…';
        list.innerHTML = '<div class="discovery-loading">영상 라이브러리를 불러오는 중…</div>';
        try {
            const response = await fetch(queryUrl(), { headers: { 'Accept': 'application/json' } });
            if (!response.ok) throw new Error('request failed');
            const payload = await response.json();
            if (serial !== requestSerial) return;
            if (!payload || !payload.summary || !Array.isArray(payload.items)) throw new Error('invalid response');
            renderSummary(payload.summary);
            status.textContent = '';
            if (!payload.items.length) {
                list.innerHTML = '<div class="library-empty">조건에 맞는 작품이 없습니다.</div>';
                return;
            }
            list.innerHTML = payload.items.map(renderItem).join('');
        } catch (_) {
            if (serial !== requestSerial) return;
            status.textContent = '';
            list.innerHTML = '<div class="library-error">라이브러리 정보를 불러오지 못했습니다.</div>';
        }
    }

    tab.addEventListener('click', () => {
        if (page.classList.contains('active')) loadLibrary();
    });
    search.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(loadLibrary, 300);
    });
    filter.addEventListener('change', loadLibrary);
    sort.addEventListener('change', loadLibrary);
    list.addEventListener('click', event => {
        const button = event.target.closest('[data-play-dvd]');
        if (!button) return;
        event.preventDefault();
        event.stopPropagation();
        if (typeof window.playLibraryItem === 'function') window.playLibraryItem(button.dataset.playDvd);
    });
})();
