from pathlib import Path


INDEX = Path('templates/index.html')
text = INDEX.read_text(encoding='utf-8')


def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'patch failed: {label}: expected 1 match, got {count}')
    text = text.replace(old, new, 1)


def replace_between(start_marker, end_marker, replacement, label):
    global text
    start = text.find(start_marker)
    if start < 0:
        raise SystemExit(f'patch failed: {label}: start marker not found')
    end = text.find(end_marker, start)
    if end < 0:
        raise SystemExit(f'patch failed: {label}: end marker not found')
    text = text[:start] + replacement + text[end:]


# --- Generic web branding ---
replace_once('<title>MissAV Downloader</title>', '<title>Downloader</title>', 'browser title')
replace_once('<div class="sidebar-logo">M</div>', '<div class="sidebar-logo">D</div>', 'sidebar logo')
replace_once(
    '<div class="page-subtitle">MissAV URL을 입력하면 서버에서 다운로드합니다</div>',
    '<div class="page-subtitle">URL을 입력하면 서버에서 다운로드합니다</div>',
    'download subtitle',
)
replace_once(
    '<input type="text" id="url" placeholder="https://missav01.com/ko/..." required>',
    '<input type="text" id="url" placeholder="https://..." required>',
    'generic url placeholder',
)
replace_once(
    '            <div style="margin-top:10px;font-size:13px;line-height:1.5;color:#e0a244;">💡 <b>missav01.com</b> 주소를 사용하세요. 통신사가 다른 미러(missav.ws / .ai 등)를 SNI 차단하면 접속이 안 될 수 있습니다.</div>\n',
    '',
    'site warning removal',
)
# Keep the site-specific mirror settings alive for backend compatibility, but do not expose them in the generic UI.
replace_once(
    '                <div class="setting-group">\n                    <label class="setting-label">미러 도메인 목록</label>\n                    <div class="setting-desc">missav 미러 도메인 (줄바꿈으로 구분)</div>',
    '                <div class="setting-group" style="display:none">\n                    <label class="setting-label">사이트 미러 도메인 목록</label>\n                    <div class="setting-desc">사이트별 미러 도메인 (줄바꿈으로 구분)</div>',
    'hide site mirror settings',
)


# --- Thumbnail styles ---
replace_once(
    '        /* --- Progress bar --- */\n',
    '''        /* --- Teddy thumbnail --- */
        .task-thumb {
            width: 112px;
            aspect-ratio: 16 / 9;
            object-fit: cover;
            border-radius: 7px;
            flex-shrink: 0;
            background: #e2e8f0;
            border: 1px solid #e2e8f0;
        }
        @media (max-width: 720px) {
            .task-thumb { width: 84px; }
        }

        /* --- Progress bar --- */
''',
    'thumbnail css',
)


# --- Duration formatter used by ETA ---
replace_once(
    '''    function formatDate(ts) {
        const d = new Date(ts * 1000);
        return d.toLocaleString('ko-KR', { year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' });
    }
''',
    '''    function formatDate(ts) {
        const d = new Date(ts * 1000);
        return d.toLocaleString('ko-KR', { year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' });
    }
    function formatDuration(seconds) {
        const s = Math.max(0, Math.round(Number(seconds) || 0));
        if (!s) return '';
        const h = Math.floor(s / 3600);
        const m = Math.floor((s % 3600) / 60);
        const r = s % 60;
        if (h) return h + '시간 ' + m + '분';
        if (m) return m + '분 ' + r + '초';
        return r + '초';
    }
''',
    'duration formatter',
)


# --- Stable, keyed task renderer ---
# The upstream page used taskList.innerHTML every 1.5s, which destroyed/recreated every button and caused flicker.
# Keep each card alive and update only the fields that actually changed.
replace_between(
    '    // --- Tasks ---\n    function fetchTasks() {',
    '\n\n    function deleteTask(id) {',
    '''    // --- Tasks ---
    const teddyTaskSamples = new Map();
    let teddyTaskOrderKey = '';

    function teddyEffectiveSpeed(id, task) {
        const now = performance.now() / 1000;
        const bytes = Number(task.downloaded_bytes) || 0;
        const apiSpeed = Number(task.speed_bps) || 0;
        const previous = teddyTaskSamples.get(id) || { time: now, bytes: bytes, speed: 0 };
        let deltaSpeed = 0;
        const elapsed = now - previous.time;
        if (elapsed > 0.25 && bytes > previous.bytes) {
            deltaSpeed = (bytes - previous.bytes) / elapsed;
        }

        let measured = apiSpeed || deltaSpeed || previous.speed || 0;
        if (measured > 0 && previous.speed > 0 && measured !== previous.speed) {
            measured = previous.speed * 0.65 + measured * 0.35;
        }
        teddyTaskSamples.set(id, { time: now, bytes: bytes, speed: measured });
        return measured;
    }

    function teddyActionState(task) {
        if (task.status === '다운로드 중') return 'downloading';
        if (task.status === '일시정지 요청 중') return 'pausing';
        if (task.status === '일시정지') return 'paused';
        if (task.status.includes('대기')) return 'waiting';
        if (task.status.includes('완료') && task.filename) return 'done:' + task.filename;
        if (task.status.includes('에러') || task.status.includes('취소')) return 'retry';
        return 'other';
    }

    function teddyActionsHtml(id, task) {
        if (task.status === '다운로드 중') {
            return '<button class="btn btn-primary" onclick="teddyPauseTask(\\'' + id + '\\')">Ⅱ 일시정지</button>';
        }
        if (task.status === '일시정지 요청 중') {
            return '<button class="btn btn-ghost" disabled>일시정지 중…</button>';
        }
        if (task.status === '일시정지') {
            return '<button class="btn btn-primary" onclick="teddyResumeTask(\\'' + id + '\\')">▶ 재개</button>' +
                   '<button class="btn btn-danger" onclick="teddyDeleteTask(\\'' + id + '\\')">삭제</button>';
        }
        if (task.status.includes('대기')) {
            return '<span class="btn stat-waiting" role="status">대기 중</span>' +
                   '<button class="btn btn-ghost" onclick="teddyDeleteTask(\\'' + id + '\\')">삭제</button>';
        }
        if (task.status.includes('완료') && task.filename) {
            return '<a class="btn btn-primary" href="/api/files/' + encodeURIComponent(task.filename) + '/download" style="text-decoration:none">↓ 받기</a>' +
                   '<button class="btn btn-ghost" onclick="deleteTask(\\'' + id + '\\')">✕</button>';
        }
        if (task.status.includes('에러') || task.status.includes('취소')) {
            return '<button class="btn btn-primary" onclick="retryTask(\\'' + id + '\\')">↻ 재시작</button>' +
                   '<button class="btn btn-ghost" onclick="teddyDeleteTask(\\'' + id + '\\')">✕</button>';
        }
        return '<button class="btn btn-ghost" onclick="teddyDeleteTask(\\'' + id + '\\')">✕</button>';
    }

    function teddyCreateTaskCard(id) {
        const card = document.createElement('div');
        card.className = 'task-card';
        card.dataset.taskId = id;
        card.innerHTML =
            '<div class="task-top">' +
                '<img class="task-thumb" alt="" loading="lazy" style="display:none">' +
                '<div style="flex:1;min-width:0">' +
                    '<div class="task-title"></div>' +
                    '<div class="task-meta"></div>' +
                '</div>' +
                '<div class="task-actions"></div>' +
            '</div>' +
            '<div class="progress-wrap" style="display:none">' +
                '<div class="progress-bg"><div class="progress-fill" style="width:0%"></div></div>' +
                '<div class="progress-text"></div>' +
            '</div>';
        return card;
    }

    function teddyUpdateTaskCard(id, task, card) {
        const isDone = task.status.includes('완료');
        const isError = task.status.includes('에러');
        const nextClass = 'task-card' + (isDone ? ' done' : (isError ? ' error' : ''));
        if (card.className !== nextClass) card.className = nextClass;

        const title = card.querySelector('.task-title');
        const nextTitle = task.display_title || task.filename || task.url || '';
        if (title.textContent !== nextTitle) title.textContent = nextTitle;

        const meta = card.querySelector('.task-meta');
        const nextMeta = isDone && task.filesize
            ? formatSize(task.filesize) + ' · 완료'
            : (task.status || '');
        if (meta.textContent !== nextMeta) meta.textContent = nextMeta;

        const thumb = card.querySelector('.task-thumb');
        if (task.thumbnail_url) {
            if (thumb.dataset.source !== task.thumbnail_url) {
                thumb.dataset.source = task.thumbnail_url;
                thumb.style.display = 'none';
                thumb.onload = function() { thumb.style.display = 'block'; };
                thumb.onerror = function() { thumb.style.display = 'none'; };
                thumb.src = '/api/tasks/' + encodeURIComponent(id) + '/thumbnail';
            }
        } else if (thumb.style.display !== 'none') {
            thumb.style.display = 'none';
        }

        const actions = card.querySelector('.task-actions');
        const actionState = teddyActionState(task);
        if (actions.dataset.state !== actionState) {
            actions.dataset.state = actionState;
            actions.innerHTML = teddyActionsHtml(id, task);
        }

        const progress = card.querySelector('.progress-wrap');
        const showProgress = task.status === '다운로드 중' || task.status === '일시정지 요청 중' || task.status === '일시정지';
        if (!showProgress) {
            if (progress.style.display !== 'none') progress.style.display = 'none';
            return;
        }

        if (progress.style.display === 'none') progress.style.display = '';
        const pct = task.progress || '0%';
        const fill = progress.querySelector('.progress-fill');
        if (fill.style.width !== pct) fill.style.width = pct;

        const downloaded = Number(task.downloaded_bytes) || 0;
        const totalEstimate = Number(task.total_bytes_estimate) || 0;
        const progressParts = [pct];
        if (downloaded && totalEstimate) {
            progressParts.push(formatSize(downloaded) + ' / 약 ' + formatSize(totalEstimate));
        } else if (downloaded) {
            progressParts.push(formatSize(downloaded));
        }

        if (task.status === '다운로드 중') {
            const speed = teddyEffectiveSpeed(id, task);
            if (speed > 0) {
                progressParts.push('↓ ' + formatSize(speed) + '/s');
                if (totalEstimate > downloaded) {
                    const eta = formatDuration((totalEstimate - downloaded) / speed);
                    if (eta) progressParts.push('남은 시간 약 ' + eta);
                }
            }
        }

        const progressText = progress.querySelector('.progress-text');
        const nextProgressText = progressParts.join(' · ');
        if (progressText.textContent !== nextProgressText) {
            progressText.textContent = nextProgressText;
        }
    }

    function fetchTasks() {
        fetch('/api/tasks').then(r => r.json()).then(tasks => {
            const entries = Object.entries(tasks).reverse();
            let downloading = 0, done = 0, waiting = 0, paused = 0, errors = 0;
            entries.forEach(([, task]) => {
                if (task.status === '다운로드 중' || task.status === '일시정지 요청 중') downloading++;
                else if (task.status.includes('완료')) done++;
                else if (task.status === '일시정지') paused++;
                else if (task.status.includes('대기')) waiting++;
                else if (task.status.includes('에러')) errors++;
            });

            const statsEl = document.getElementById('stats');
            let statsHtml = '';
            if (downloading) statsHtml += '<span class="stat-badge stat-downloading">↓ 진행 ' + downloading + '</span>';
            if (paused) statsHtml += '<span class="stat-badge stat-waiting">Ⅱ 일시정지 ' + paused + '</span>';
            if (done) statsHtml += '<span class="stat-badge stat-done">✓ 완료 ' + done + '</span>';
            if (waiting) statsHtml += '<span class="stat-badge stat-waiting">⏳ 대기 ' + waiting + '</span>';
            if (errors) statsHtml += '<span class="stat-badge stat-error">✕ 에러 ' + errors + '</span>';
            if (statsEl.innerHTML !== statsHtml) statsEl.innerHTML = statsHtml;

            const listEl = document.getElementById('taskList');
            if (entries.length === 0) {
                if (!listEl.querySelector('.empty')) {
                    listEl.innerHTML = '<div class="empty">다운로드 목록이 비어있습니다</div>';
                }
                teddyTaskOrderKey = '';
                return;
            }

            const empty = listEl.querySelector('.empty');
            if (empty) empty.remove();
            const wanted = new Set(entries.map(([id]) => id));
            listEl.querySelectorAll('.task-card[data-task-id]').forEach(card => {
                if (!wanted.has(card.dataset.taskId)) {
                    teddyTaskSamples.delete(card.dataset.taskId);
                    card.remove();
                }
            });

            entries.forEach(([id, task]) => {
                let card = listEl.querySelector('.task-card[data-task-id="' + id + '"]');
                if (!card) {
                    card = teddyCreateTaskCard(id);
                    listEl.appendChild(card);
                }
                teddyUpdateTaskCard(id, task, card);
            });

            const nextOrderKey = entries.map(([id]) => id).join('|');
            if (nextOrderKey !== teddyTaskOrderKey) {
                entries.forEach(([id]) => {
                    const card = listEl.querySelector('.task-card[data-task-id="' + id + '"]');
                    if (card) listEl.appendChild(card);
                });
                teddyTaskOrderKey = nextOrderKey;
            }
        });
    }''',
    'stable task renderer',
)

INDEX.write_text(text, encoding='utf-8')
print('teddy index patch: OK')
