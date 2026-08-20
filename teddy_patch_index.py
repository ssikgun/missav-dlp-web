from pathlib import Path


INDEX = Path('templates/index.html')
text = INDEX.read_text(encoding='utf-8')


def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'patch failed: {label}: expected 1 match, got {count}')
    text = text.replace(old, new, 1)


replace_once(
    '        /* --- Progress bar --- */\n',
    '''        /* --- Teddy thumbnail --- */\n        .task-thumb {\n            width: 112px;\n            aspect-ratio: 16 / 9;\n            object-fit: cover;\n            border-radius: 7px;\n            flex-shrink: 0;\n            background: #e2e8f0;\n            border: 1px solid #e2e8f0;\n        }\n        @media (max-width: 720px) {\n            .task-thumb { width: 84px; }\n        }\n\n        /* --- Progress bar --- */\n''',
    'thumbnail css',
)

replace_once(
    '''    function formatDate(ts) {\n        const d = new Date(ts * 1000);\n        return d.toLocaleString('ko-KR', { year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' });\n    }\n''',
    '''    function formatDate(ts) {\n        const d = new Date(ts * 1000);\n        return d.toLocaleString('ko-KR', { year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' });\n    }\n    function formatDuration(seconds) {\n        const s = Math.max(0, Math.round(Number(seconds) || 0));\n        if (!s) return '';\n        const h = Math.floor(s / 3600);\n        const m = Math.floor((s % 3600) / 60);\n        const r = s % 60;\n        if (h) return h + '시간 ' + m + '분';\n        if (m) return m + '분 ' + r + '초';\n        return r + '초';\n    }\n''',
    'duration formatter',
)

replace_once(
    '''                let progressHtml = '';\n                if (t.status === '다운로드 중') {\n                    const pct = t.progress || '0%';\n                    progressHtml =\n                        '<div class="progress-wrap">' +\n                            '<div class="progress-bg"><div class="progress-fill" style="width:' + pct + '"></div></div>' +\n                            '<div class="progress-text">' + escapeHtml(pct) + '</div>' +\n                        '</div>';\n                }\n''',
    '''                let progressHtml = '';\n                if (t.status === '다운로드 중') {\n                    const pct = t.progress || '0%';\n                    const downloaded = Number(t.downloaded_bytes) || 0;\n                    const totalEstimate = Number(t.total_bytes_estimate) || 0;\n                    const speed = Number(t.speed_bps) || 0;\n                    const progressParts = [pct];\n                    if (downloaded && totalEstimate) {\n                        progressParts.push(formatSize(downloaded) + ' / 약 ' + formatSize(totalEstimate));\n                    } else if (downloaded) {\n                        progressParts.push(formatSize(downloaded));\n                    }\n                    if (speed) {\n                        progressParts.push('↓ ' + formatSize(speed) + '/s');\n                        if (totalEstimate > downloaded) {\n                            const eta = formatDuration((totalEstimate - downloaded) / speed);\n                            if (eta) progressParts.push('남은 시간 약 ' + eta);\n                        }\n                    }\n                    progressHtml =\n                        '<div class="progress-wrap">' +\n                            '<div class="progress-bg"><div class="progress-fill" style="width:' + pct + '"></div></div>' +\n                            '<div class="progress-text">' + escapeHtml(progressParts.join(' · ')) + '</div>' +\n                        '</div>';\n                }\n''',
    'native progress details',
)

replace_once(
    '''                let actions = '';\n                if (t.status === '다운로드 중') {\n                    actions = '<button class="btn btn-danger" onclick="deleteTask(\\'' + id + '\\')">취소</button>';\n                } else if (t.status.includes('완료') && t.filename) {\n                    actions =\n                        '<a class="btn btn-primary" href="/api/files/' + encodeURIComponent(t.filename) + '/download" style="text-decoration:none">\\u2193 받기</a>' +\n                        '<button class="btn btn-ghost" onclick="deleteTask(\\'' + id + '\\')">\\u2715</button>';\n                } else if (t.status.includes('\\uc5d0\\ub7ec') || t.status.includes('\\ucde8\\uc18c')) {\n                    actions =\n                        '<button class="btn btn-primary" onclick="retryTask(\\'' + id + '\\')">\\u21bb \\uc7ac\\uc2dc\\uc791</button>' +\n                        '<button class="btn btn-ghost" onclick="deleteTask(\\'' + id + '\\')">\\u2715</button>';\n                } else {\n                    actions = '<button class="btn btn-ghost" onclick="deleteTask(\\'' + id + '\\')">\\u2715</button>';\n                }\n''',
    '''                let actions = '';\n                if (t.status === '다운로드 중') {\n                    actions = '<button class="btn btn-primary" onclick="teddyPauseTask(\\'' + id + '\\')">Ⅱ 일시정지</button>';\n                } else if (t.status === '일시정지 요청 중') {\n                    actions = '<button class="btn btn-ghost" disabled>일시정지 중…</button>';\n                } else if (t.status === '일시정지') {\n                    actions =\n                        '<button class="btn btn-primary" onclick="teddyResumeTask(\\'' + id + '\\')">▶ 재개</button>' +\n                        '<button class="btn btn-danger" onclick="teddyDeleteTask(\\'' + id + '\\')">삭제</button>';\n                } else if (t.status.includes('완료') && t.filename) {\n                    actions =\n                        '<a class="btn btn-primary" href="/api/files/' + encodeURIComponent(t.filename) + '/download" style="text-decoration:none">\\u2193 받기</a>' +\n                        '<button class="btn btn-ghost" onclick="deleteTask(\\'' + id + '\\')">\\u2715</button>';\n                } else if (t.status.includes('\\uc5d0\\ub7ec') || t.status.includes('\\ucde8\\uc18c')) {\n                    actions =\n                        '<button class="btn btn-primary" onclick="retryTask(\\'' + id + '\\')">\\u21bb \\uc7ac\\uc2dc\\uc791</button>' +\n                        '<button class="btn btn-ghost" onclick="teddyDeleteTask(\\'' + id + '\\')">\\u2715</button>';\n                } else {\n                    actions = '<button class="btn btn-ghost" onclick="teddyDeleteTask(\\'' + id + '\\')">\\u2715</button>';\n                }\n''',
    'native reliability actions',
)

replace_once(
    '''                const titleText = escapeHtml(t.filename || t.url);\n''',
    '''                const titleText = escapeHtml(t.display_title || t.filename || t.url);\n                const thumbHtml = t.thumbnail_url\n                    ? '<img class="task-thumb" src="/api/tasks/' + encodeURIComponent(id) + '/thumbnail" alt="" loading="lazy">'\n                    : '';\n''',
    'title and thumbnail data',
)

replace_once(
    '''                    '<div class="task-top">' +\n                        '<div style="flex:1;min-width:0">' +\n''',
    '''                    '<div class="task-top">' +\n                        thumbHtml +\n                        '<div style="flex:1;min-width:0">' +\n''',
    'thumbnail placement',
)

INDEX.write_text(text, encoding='utf-8')
print('teddy index patch: OK')
