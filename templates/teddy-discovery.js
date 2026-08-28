(() => {
    'use strict';

    const pageButton = document.querySelector(
        '.sidebar-btn[data-page="discovery"]'
    );

    const page = document.getElementById(
        'page-discovery'
    );

    const list = document.getElementById(
        'discoveryList'
    );

    const status = document.getElementById(
        'discoveryStatus'
    );

    const summary = document.getElementById(
        'discoverySummary'
    );

    const genreControls = document.getElementById(
        'discoveryGenreControls'
    );

    const genreSelect = document.getElementById(
        'discoveryGenreSelect'
    );

    const tabs = Array.from(
        document.querySelectorAll(
            '[data-discovery-view]'
        )
    );

    if (
        !pageButton
        || !page
        || !list
        || !status
        || !summary
        || !genreControls
        || !genreSelect
        || tabs.length !== 4
    ) {
        return;
    }

    const state = {
        activeView: 'latest',
        loadedOnce: false,
        categoriesLoaded: false,
        requestToken: 0,
        activePreview: null,
    };

    const hoverPreviewMedia = window.matchMedia(
        '(hover: hover) and (pointer: fine)'
    );

    function escapeHtml(value) {
        const div = document.createElement(
            'div'
        );

        div.textContent = (
            value === null
            || value === undefined
        )
            ? ''
            : String(value);

        return div.innerHTML;
    }

    function textOrDash(value) {
        if (
            value === null
            || value === undefined
            || value === ''
        ) {
            return '—';
        }

        return String(value);
    }

    function joinOrDash(values) {
        if (
            !Array.isArray(values)
            || values.length === 0
        ) {
            return '—';
        }

        return values.join(', ');
    }

    async function fetchJson(url) {
        const response = await fetch(
            url,
            {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                },
            }
        );

        let payload = null;

        try {
            payload = await response.json();
        } catch (_) {
            throw new Error(
                '서버 응답을 읽을 수 없습니다'
            );
        }

        if (
            !response.ok
            || !payload
            || payload.status !== 'success'
            || typeof payload.data !== 'object'
        ) {
            const message = (
                payload
                && payload.error
                && payload.error.message
            )
                ? payload.error.message
                : 'Discovery 데이터를 불러오지 못했습니다';

            throw new Error(
                message
            );
        }

        return payload.data;
    }

    function availabilityBadge(
        source,
        availability
    ) {
        const value = (
            availability
            && availability[source]
        )
            ? availability[source]
            : {
                status: 'UNKNOWN',
                known: false,
            };

        const label = (
            source === 'missav'
        )
            ? 'MissAV'
            : '123AV';

        if (!value.known) {
            return (
                '<span class="discovery-badge discovery-unchecked">'
                + escapeHtml(label)
                + ' 미확인</span>'
            );
        }

        if (value.status === 'FOUND') {
            return (
                '<span class="discovery-badge discovery-found">'
                + escapeHtml(label)
                + ' 있음</span>'
            );
        }

        if (value.status === 'NOT_FOUND') {
            return (
                '<span class="discovery-badge discovery-not-found">'
                + escapeHtml(label)
                + ' 없음</span>'
            );
        }

        return (
            '<span class="discovery-badge discovery-unknown">'
            + escapeHtml(label)
            + ' 확인실패</span>'
        );
    }

    function downloadButton(item) {
        const sources = Array.isArray(
            item.available_sources
        )
            ? item.available_sources
            : [];

        const available = (
            sources.includes('missav')
            || sources.includes('123av')
        );

        return (
            '<button type="button"'
            + ' class="discovery-download-btn"'
            + ' data-discovery-download="'
            + escapeHtml(item.dvd_id)
            + '"'
            + (available ? '' : ' disabled')
            + '>'
            + (
                available
                    ? '다운로드'
                    : '다운로드 불가'
            )
            + '</button>'
        );
    }

    function downloadMessage(message, error) {
        status.className = (
            'discovery-status'
            + (error ? ' error' : '')
        );

        status.textContent = message;
    }

    async function requestDownload(
        dvdId,
        button
    ) {
        const originalText = (
            button.textContent
            || '다운로드'
        );

        button.disabled = true;
        button.textContent = '추가 중...';

        try {
            const response = await fetch(
                '/api/discovery/download',
                {
                    method: 'POST',
                    headers: {
                        'Accept': 'application/json',
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        dvd_id: dvdId,
                    }),
                }
            );

            let payload = null;

            try {
                payload = await response.json();
            } catch (_) {
                throw new Error(
                    '서버 응답을 읽을 수 없습니다'
                );
            }

            if (
                response.status === 409
                && payload
                && payload.status === 'duplicate'
            ) {
                button.textContent = '이미 큐에 있음';

                downloadMessage(
                    payload.message
                    || '이미 다운로드 큐에 있습니다.',
                    false,
                );

                return;
            }

            if (
                !response.ok
                || !payload
                || payload.status !== 'success'
            ) {
                throw new Error(
                    (
                        payload
                        && payload.message
                    )
                    || '다운로드를 추가하지 못했습니다'
                );
            }

            button.textContent = '추가됨';

            downloadMessage(
                dvdId + ' 다운로드를 추가했습니다.',
                false,
            );

        } catch (error) {
            button.disabled = false;
            button.textContent = originalText;

            downloadMessage(
                (
                    error
                    && error.message
                )
                    ? error.message
                    : '다운로드를 추가하지 못했습니다',
                true,
            );
        }
    }

    function bindDownloadActions() {
        list.querySelectorAll(
            '[data-discovery-download]'
        ).forEach(
            button => {
                button.addEventListener(
                    'click',
                    event => {
                        event.preventDefault();
                        event.stopPropagation();

                        const dvdId = (
                            button.dataset.discoveryDownload
                            || ''
                        ).trim();

                        if (!dvdId) {
                            return;
                        }

                        requestDownload(
                            dvdId,
                            button,
                        );
                    }
                );
            }
        );
    }

    function chips(values) {
        if (
            !Array.isArray(values)
            || values.length === 0
        ) {
            return (
                '<span class="discovery-detail-value">—</span>'
            );
        }

        return (
            '<div class="discovery-chips">'
            + values.map(
                value => (
                    '<span class="discovery-chip">'
                    + escapeHtml(value)
                    + '</span>'
                )
            ).join('')
            + '</div>'
        );
    }

    function rankingText(item) {
        const ranking = (
            item
            && item.ranking
        )
            ? item.ranking
            : {};

        if (ranking.kind === 'latest') {
            return (
                '현재 위치 '
                + textOrDash(
                    ranking.last_position
                )
                + ' · 마지막 확인 '
                + textOrDash(
                    ranking.last_seen_at
                )
            );
        }

        if (ranking.kind === 'weekly') {
            return (
                textOrDash(
                    ranking.period_display
                )
                + ' · 원본 순위 '
                + textOrDash(
                    ranking.snapshot_rank
                )
                + ' · 점수 '
                + textOrDash(
                    ranking.score
                )
            );
        }

        if (ranking.kind === 'monthly') {
            return (
                '4주 합산 '
                + textOrDash(
                    ranking.score
                )
                + '점 · 등장 '
                + textOrDash(
                    ranking.appearances
                )
                + '주 · 최신주 순위 '
                + textOrDash(
                    ranking.latest_week_rank
                )
            );
        }

        if (ranking.kind === 'category') {
            return (
                textOrDash(
                    ranking.category
                )
                + ' #'
                + textOrDash(
                    ranking.category_rank
                )
                + ' · 월간 #'
                + textOrDash(
                    ranking.monthly_rank
                )
                + ' · '
                + textOrDash(
                    ranking.score
                )
                + '점'
            );
        }

        return '—';
    }

    function coverEndpoint(dvdId) {
        return (
            '/api/discovery/media/cover/'
            + encodeURIComponent(
                String(dvdId)
            )
        );
    }


    function loadCover(
        row,
        dvdId
    ) {
        const base = row.querySelector(
            '.discovery-cover-base'
        );

        if (
            !base
            || row.dataset.coverRequested
            === '1'
        ) {
            return;
        }

        row.dataset.coverRequested = '1';

        const placeholder = (
            base.querySelector(
                '.discovery-cover-placeholder'
            )
        );

        if (placeholder) {
            placeholder.textContent = (
                '표지를 불러오는 중...'
            );
        }

        const image = document.createElement(
            'img'
        );

        image.className = (
            'discovery-cover-image'
        );

        image.alt = (
            String(dvdId)
            + ' 표지'
        );

        image.decoding = 'async';

        image.addEventListener(
            'load',
            () => {
                base.replaceChildren(
                    image
                );
            },
            {
                once: true,
            }
        );

        image.addEventListener(
            'error',
            () => {
                const failed = (
                    document.createElement(
                        'div'
                    )
                );

                failed.className = (
                    'discovery-cover-placeholder error'
                );

                failed.textContent = (
                    '표지를 불러올 수 없습니다'
                );

                base.replaceChildren(
                    failed
                );
            },
            {
                once: true,
            }
        );

        image.src = coverEndpoint(
            dvdId
        );
    }


    function previewEndpoint(dvdId) {
        return (
            '/api/discovery/media/preview/'
            + encodeURIComponent(
                String(dvdId)
            )
        );
    }


    function previewIdleText() {
        return hoverPreviewMedia.matches
            ? '마우스를 올리면 미리보기'
            : '탭하면 미리보기';
    }


    function setPreviewHint(
        slot,
        text,
        isError = false
    ) {
        const hint = slot.querySelector(
            '.discovery-preview-hint'
        );

        if (!hint) {
            return;
        }

        hint.textContent = text;

        hint.classList.toggle(
            'error',
            isError
        );
    }


    function stopActivePreview(
        row = null,
        restoreHint = true
    ) {
        const active = (
            state.activePreview
        );

        if (
            !active
            || (
                row
                && active.row !== row
            )
        ) {
            return;
        }

        state.activePreview = null;

        active.row.classList.remove(
            'discovery-preview-active'
        );

        try {
            active.video.pause();
        } catch (_) {
            // Best-effort media cleanup.
        }

        active.video.removeAttribute(
            'src'
        );

        try {
            active.video.load();
        } catch (_) {
            // Best-effort media cleanup.
        }

        active.video.remove();

        if (restoreHint) {
            setPreviewHint(
                active.slot,
                previewIdleText(),
                false
            );
        }
    }


    function startPreview(
        row,
        dvdId
    ) {
        const slot = row.querySelector(
            '.discovery-cover-slot'
        );

        if (
            !slot
            || !row.open
            || row.dataset.previewFailed
            === '1'
        ) {
            return;
        }

        if (
            state.activePreview
            && state.activePreview.row
            === row
        ) {
            return;
        }

        stopActivePreview();

        row.dataset.previewTouched = '1';

        setPreviewHint(
            slot,
            '미리보기를 불러오는 중...',
            false
        );

        const video = document.createElement(
            'video'
        );

        video.className = (
            'discovery-preview-video'
        );

        video.muted = true;
        video.loop = true;
        video.playsInline = true;
        video.preload = 'metadata';

        video.setAttribute(
            'aria-label',
            String(dvdId)
            + ' 미리보기'
        );

        video.addEventListener(
            'playing',
            () => {
                if (
                    !state.activePreview
                    || state.activePreview.video
                    !== video
                ) {
                    return;
                }

                row.classList.add(
                    'discovery-preview-active'
                );

                setPreviewHint(
                    slot,
                    '미리보기 재생 중',
                    false
                );
            },
            {
                once: true,
            }
        );

        video.addEventListener(
            'error',
            () => {
                if (
                    !state.activePreview
                    || state.activePreview.video
                    !== video
                ) {
                    return;
                }

                row.dataset.previewFailed = '1';

                stopActivePreview(
                    row,
                    false
                );

                setPreviewHint(
                    slot,
                    '미리보기를 불러올 수 없습니다',
                    true
                );
            },
            {
                once: true,
            }
        );

        slot.appendChild(
            video
        );

        state.activePreview = {
            row,
            slot,
            video,
            dvdId,
        };

        video.src = previewEndpoint(
            dvdId
        );

        const playResult = video.play();

        if (
            playResult
            && typeof playResult.catch
            === 'function'
        ) {
            playResult.catch(
                () => {
                    if (
                        !state.activePreview
                        || state.activePreview.video
                        !== video
                    ) {
                        return;
                    }

                    row.dataset.previewFailed = '1';

                    stopActivePreview(
                        row,
                        false
                    );

                    setPreviewHint(
                        slot,
                        '미리보기를 재생할 수 없습니다',
                        true
                    );
                }
            );
        }
    }


    function togglePreview(
        row,
        dvdId
    ) {
        if (
            state.activePreview
            && state.activePreview.row
            === row
        ) {
            stopActivePreview(
                row
            );

            return;
        }

        startPreview(
            row,
            dvdId
        );
    }


    function bindCoverLazyLoad(
        items
    ) {
        const rows = Array.from(
            list.querySelectorAll(
                '.discovery-row'
            )
        );

        rows.forEach(
            (row, index) => {
                const item = items[index];

                const dvdId = (
                    item
                    && item.dvd_id
                )
                    ? String(
                        item.dvd_id
                    )
                    : '';

                if (!dvdId) {
                    return;
                }

                row.addEventListener(
                    'toggle',
                    () => {
                        if (row.open) {
                            loadCover(
                                row,
                                dvdId
                            );
                        }
                    }
                );
            }
        );
    }


    function bindExclusiveRows() {
        const rows = Array.from(
            list.querySelectorAll(
                '.discovery-row'
            )
        );

        rows.forEach(
            row => {
                row.addEventListener(
                    'toggle',
                    () => {
                        if (!row.open) {
                            return;
                        }

                        rows.forEach(
                            otherRow => {
                                if (
                                    otherRow !== row
                                    && otherRow.open
                                ) {
                                    otherRow.open = false;
                                }
                            }
                        );
                    }
                );
            }
        );
    }


    function bindPreviewLazyLoad(
        items
    ) {
        const rows = Array.from(
            list.querySelectorAll(
                '.discovery-row'
            )
        );

        rows.forEach(
            (row, index) => {
                const item = items[index];

                const dvdId = (
                    item
                    && item.dvd_id
                )
                    ? String(
                        item.dvd_id
                    )
                    : '';

                const slot = row.querySelector(
                    '.discovery-cover-slot'
                );

                if (
                    !dvdId
                    || !slot
                ) {
                    return;
                }

                setPreviewHint(
                    slot,
                    previewIdleText(),
                    false
                );

                slot.addEventListener(
                    'pointerenter',
                    () => {
                        if (
                            hoverPreviewMedia.matches
                            && row.open
                        ) {
                            startPreview(
                                row,
                                dvdId
                            );
                        }
                    }
                );

                slot.addEventListener(
                    'pointerleave',
                    () => {
                        if (
                            hoverPreviewMedia.matches
                        ) {
                            stopActivePreview(
                                row
                            );
                        }
                    }
                );

                slot.addEventListener(
                    'click',
                    () => {
                        if (
                            !hoverPreviewMedia.matches
                            && row.open
                        ) {
                            togglePreview(
                                row,
                                dvdId
                            );
                        }
                    }
                );

                slot.addEventListener(
                    'keydown',
                    event => {
                        if (
                            !row.open
                            || (
                                event.key !== 'Enter'
                                && event.key !== ' '
                            )
                        ) {
                            return;
                        }

                        event.preventDefault();

                        togglePreview(
                            row,
                            dvdId
                        );
                    }
                );

                row.addEventListener(
                    'toggle',
                    () => {
                        if (!row.open) {
                            stopActivePreview(
                                row
                            );
                        }
                    }
                );
            }
        );
    }


    function renderItems(data) {
        stopActivePreview();

        const items = Array.isArray(
            data.items
        )
            ? data.items
            : [];

        if (items.length === 0) {
            list.innerHTML = (
                '<div class="discovery-empty">'
                + '표시할 항목이 없습니다'
                + '</div>'
            );

            return;
        }

        list.innerHTML = items.map(
            item => {
                const ownedBadge = item.owned
                    ? (
                        '<span class="discovery-badge discovery-owned">'
                        + '보유 '
                        + escapeHtml(
                            item.holding_count
                        )
                        + '</span>'
                    )
                    : (
                        '<span class="discovery-badge discovery-unowned">'
                        + '미보유</span>'
                    );

                const meta = [
                    item.release_date,
                    item.maker,
                ].filter(
                    value => (
                        value !== null
                        && value !== undefined
                        && value !== ''
                    )
                ).join(' · ');

                return (
                    '<details class="discovery-row">'
                    + '<summary class="discovery-row-summary">'
                    + '<div class="discovery-rank">#'
                    + escapeHtml(item.rank)
                    + '</div>'
                    + '<div class="discovery-id">'
                    + escapeHtml(item.dvd_id)
                    + '</div>'
                    + '<div class="discovery-title-wrap">'
                    + '<div class="discovery-title">'
                    + escapeHtml(
                        textOrDash(
                            item.title
                        )
                    )
                    + '</div>'
                    + '<div class="discovery-meta">'
                    + escapeHtml(
                        meta || '메타데이터 없음'
                    )
                    + '</div>'
                    + '</div>'
                    + '<div class="discovery-badges">'
                    + ownedBadge
                    + availabilityBadge(
                        'missav',
                        item.availability
                    )
                    + availabilityBadge(
                        '123av',
                        item.availability
                    )
                    + '</div>'
                    + '</summary>'
                    + '<div class="discovery-detail">'
                    + '<div class="discovery-cover-slot"'
                    + ' tabindex="0" role="button"'
                    + ' aria-label="미리보기 재생">'
                    + '<div class="discovery-cover-base">'
                    + '<div class="discovery-cover-placeholder">'
                    + '표지를 보려면 항목을 펼치세요'
                    + '</div>'
                    + '</div>'
                    + '<div class="discovery-preview-hint"'
                    + ' aria-hidden="true"></div>'
                    + '</div>'
                    + '<div class="discovery-detail-grid">'
                    + '<div class="discovery-detail-block">'
                    + '<div class="discovery-detail-label">출연</div>'
                    + chips(item.people)
                    + '</div>'
                    + '<div class="discovery-detail-block">'
                    + '<div class="discovery-detail-label">장르</div>'
                    + chips(item.genres)
                    + '</div>'
                    + '<div class="discovery-detail-block">'
                    + '<div class="discovery-detail-label">제작사 / 출시일</div>'
                    + '<div class="discovery-detail-value">'
                    + escapeHtml(
                        textOrDash(
                            item.maker
                        )
                    )
                    + ' · '
                    + escapeHtml(
                        textOrDash(
                            item.release_date
                        )
                    )
                    + '</div>'
                    + '</div>'
                    + '<div class="discovery-detail-block">'
                    + '<div class="discovery-detail-label">랭킹 근거</div>'
                    + '<div class="discovery-detail-value">'
                    + escapeHtml(
                        rankingText(item)
                    )
                    + '</div>'
                    + '</div>'
                    + '<div class="discovery-detail-block discovery-download-block">'
                    + '<div class="discovery-detail-label">다운로드</div>'
                    + downloadButton(item)
                    + '</div>'
                    + '</div>'
                    + '</div>'
                    + '</details>'
                );
            }
        ).join('');

        bindCoverLazyLoad(
            items
        );

        bindExclusiveRows();

        bindPreviewLazyLoad(
            items
        );

        bindDownloadActions();
    }

    function formatRefreshedAt(value) {
        const raw = String(
            value || ''
        ).trim();

        if (!raw) {
            return '';
        }

        const instant = new Date(
            raw
        );

        if (
            Number.isNaN(
                instant.getTime()
            )
        ) {
            return '';
        }

        const parts = {};

        new Intl.DateTimeFormat(
            'en-CA',
            {
                timeZone:
                    'Asia/Seoul',
                year:
                    'numeric',
                month:
                    '2-digit',
                day:
                    '2-digit',
                hour:
                    '2-digit',
                minute:
                    '2-digit',
                hourCycle:
                    'h23',
            }
        ).formatToParts(
            instant
        ).forEach(
            part => {
                if (
                    part.type
                    !== 'literal'
                ) {
                    parts[
                        part.type
                    ] = part.value;
                }
            }
        );

        if (
            !parts.year
            || !parts.month
            || !parts.day
            || !parts.hour
            || !parts.minute
        ) {
            return '';
        }

        return (
            parts.year
            + '-'
            + parts.month
            + '-'
            + parts.day
            + ' '
            + parts.hour
            + ':'
            + parts.minute
            + ' KST'
        );
    }


    function discoveryStatusText(data) {
        const label = String(
            (
                data
                && data.label
            )
            || ''
        ).trim();

        const refreshed = (
            formatRefreshedAt(
                data
                && data.refreshed_at
            )
        );

        if (!refreshed) {
            return label;
        }

        return (
            (
                label
                    ? label + ' · '
                    : ''
            )
            + '최근 갱신: '
            + refreshed
        );
    }


    function viewUrl(view) {
        if (view === 'latest') {
            return '/api/discovery/latest';
        }

        if (view === 'weekly') {
            return '/api/discovery/weekly';
        }

        if (view === 'monthly') {
            return '/api/discovery/monthly';
        }

        if (view === 'genre') {
            const value = (
                genreSelect.value || ''
            ).trim();

            if (!value) {
                return null;
            }

            return (
                '/api/discovery/category?name='
                + encodeURIComponent(value)
            );
        }

        throw new Error(
            '지원하지 않는 Discovery 보기입니다'
        );
    }

    function activateTab(view) {
        state.activeView = view;

        tabs.forEach(
            tab => {
                tab.classList.toggle(
                    'active',
                    tab.dataset.discoveryView
                    === view
                );
            }
        );

        genreControls.hidden = (
            view !== 'genre'
        );
    }

    function summaryText(data) {
        if (
            data.view === 'latest'
        ) {
            return (
                'Latest · '
                + textOrDash(
                    data.item_count
                )
                + '개'
            );
        }

        if (
            data.view === 'weekly'
        ) {
            return (
                textOrDash(
                    data.period_display
                )
                + ' · '
                + textOrDash(
                    data.item_count
                )
                + '개'
            );
        }

        if (
            data.view === 'monthly'
        ) {
            return (
                '최근 '
                + textOrDash(
                    data.window_weeks
                )
                + '주 · '
                + textOrDash(
                    data.item_count
                )
                + '개'
            );
        }

        if (
            data.view === 'category'
        ) {
            return (
                textOrDash(
                    data.category
                )
                + ' · '
                + textOrDash(
                    data.item_count
                )
                + '개'
            );
        }

        return 'Discovery';
    }

    async function ensureCategories() {
        if (
            state.categoriesLoaded
        ) {
            return;
        }

        const data = await fetchJson(
            '/api/discovery/categories'
        );

        const categories = Array.isArray(
            data.categories
        )
            ? data.categories
            : [];

        if (categories.length === 0) {
            throw new Error(
                '사용 가능한 장르가 없습니다'
            );
        }

        genreSelect.replaceChildren(
            ...categories.map(
                item => {
                    const option = document.createElement(
                        'option'
                    );

                    option.value = String(
                        item.name
                    );

                    option.textContent = (
                        String(
                            item.name
                        )
                        + ' ('
                        + String(
                            item.title_count
                        )
                        + ')'
                    );

                    return option;
                }
            )
        );

        state.categoriesLoaded = true;
    }

    async function loadView(view) {
        const token = (
            ++state.requestToken
        );

        activateTab(
            view
        );

        stopActivePreview();

        status.className = (
            'discovery-status'
        );

        status.textContent = (
            '불러오는 중...'
        );

        list.innerHTML = (
            '<div class="discovery-loading">'
            + 'Discovery 데이터를 불러오는 중입니다'
            + '</div>'
        );

        try {
            if (view === 'genre') {
                await ensureCategories();

                if (
                    token !== state.requestToken
                ) {
                    return;
                }
            }

            const url = viewUrl(
                view
            );

            if (!url) {
                throw new Error(
                    '장르를 선택하세요'
                );
            }

            const data = await fetchJson(
                url
            );

            if (
                token !== state.requestToken
            ) {
                return;
            }

            renderItems(
                data
            );

            summary.textContent = (
                summaryText(
                    data
                )
            );

            status.textContent = (
                discoveryStatusText(
                    data
                )
            );

        } catch (error) {
            if (
                token !== state.requestToken
            ) {
                return;
            }

            status.className = (
                'discovery-status error'
            );

            status.textContent = (
                error
                && error.message
            )
                ? error.message
                : 'Discovery 데이터를 불러오지 못했습니다';

            summary.textContent = (
                '오류'
            );

            list.innerHTML = (
                '<div class="discovery-empty">'
                + '데이터를 표시할 수 없습니다'
                + '</div>'
            );
        }
    }

    pageButton.addEventListener(
        'click',
        () => {
            if (
                !state.loadedOnce
            ) {
                state.loadedOnce = true;

                loadView(
                    state.activeView
                );
            }
        }
    );

    Array.from(
        document.querySelectorAll(
            '.sidebar-btn[data-page]'
        )
    ).forEach(
        button => {
            if (button === pageButton) {
                return;
            }

            button.addEventListener(
                'click',
                () => {
                    stopActivePreview();
                }
            );
        }
    );

    document.addEventListener(
        'visibilitychange',
        () => {
            if (document.hidden) {
                stopActivePreview();
            }
        }
    );

    tabs.forEach(
        tab => {
            tab.addEventListener(
                'click',
                () => {
                    loadView(
                        tab.dataset.discoveryView
                    );
                }
            );
        }
    );

    genreSelect.addEventListener(
        'change',
        () => {
            if (
                state.activeView === 'genre'
            ) {
                loadView(
                    'genre'
                );
            }
        }
    );
})();
