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
    };

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
                    ranking.period
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

    function renderItems(data) {
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
                    + '</div>'
                    + '</div>'
                    + '</details>'
                );
            }
        ).join('');
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
                    data.period
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
                        item.category
                    );

                    option.textContent = (
                        String(
                            item.category
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
                data.label || ''
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
