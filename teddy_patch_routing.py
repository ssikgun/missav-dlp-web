from pathlib import Path


INDEX = Path('templates/index.html')
text = INDEX.read_text(encoding='utf-8')


def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'routing patch failed: {label}: expected 1 match, got {count}')
    text = text.replace(old, new, 1)


replace_once(
    '''            <form id="downloadForm" class="url-bar">
                <input type="text" id="url" placeholder="https://..." required>
                <button type="submit">추가</button>
            </form>''',
    '''            <form id="downloadForm" class="url-bar">
                <input type="text" id="url" placeholder="https://..." required>
                <select id="downloadNetworkMode" class="teddy-route-select" title="이번 다운로드의 네트워크 경로">
                    <option value="auto" selected>자동</option>
                    <option value="direct">Direct</option>
                    <option value="vpn">VPN</option>
                </select>
                <button type="submit">추가</button>
            </form>
            <div class="teddy-route-hint" id="teddyRouteHint">자동 · 새 사이트는 Direct 우선 → 네트워크 오류 시 VPN 재시도</div>''',
    'download route selector',
)

replace_once(
    '            body: new URLSearchParams({ url })',
    "            body: new URLSearchParams({ url, network_mode: document.getElementById('downloadNetworkMode').value })",
    'download route submission',
)

replace_once(
    '''        const meta = card.querySelector('.task-meta');
        const nextMeta = isDone && task.filesize
            ? formatSize(task.filesize) + ' · 완료'
            : (task.status || '');
        if (meta.textContent !== nextMeta) meta.textContent = nextMeta;''',
    '''        const meta = card.querySelector('.task-meta');
        const routeLabel = task.network_mode === 'vpn' ? 'VPN' : (task.network_mode === 'direct' ? 'Direct' : '');
        const statusText = isDone && task.filesize
            ? formatSize(task.filesize) + ' · 완료'
            : (task.status || '');
        const nextMeta = routeLabel ? statusText + ' · ' + routeLabel : statusText;
        if (meta.textContent !== nextMeta) meta.textContent = nextMeta;''',
    'task route label',
)

replace_once(
    '''                <div class="setting-actions">
                    <button class="btn-save" id="saveSettings">저장</button>''',
    '''                <div class="setting-group teddy-routing-settings">
                    <label class="setting-label">네트워크 라우팅</label>
                    <div class="setting-desc">자동 모드는 저장된 성공 경로를 사용하고, 처음 보는 사이트는 Direct로 시도한 뒤 네트워크성 실패에만 VPN으로 재시도합니다. 성공한 경로는 자동 학습됩니다.</div>

                    <div class="teddy-routing-summary">
                        <strong>기본 정책</strong>
                        <span>Direct 우선 → 실패 시 VPN → 성공 경로 학습</span>
                    </div>

                    <div class="teddy-routing-section-title">수동 사이트 규칙</div>
                    <div id="teddyManualRules" class="teddy-routing-list"></div>
                    <div class="teddy-routing-add">
                        <input type="text" id="teddyRoutingTarget" class="setting-input-wide" placeholder="https://example.com/video 또는 example.com">
                        <select id="teddyRoutingMode" class="setting-select">
                            <option value="direct">Direct</option>
                            <option value="vpn">VPN</option>
                        </select>
                        <button type="button" id="teddyRoutingAdd">추가</button>
                    </div>

                    <div class="teddy-routing-section-title">자동 학습된 사이트</div>
                    <div id="teddyLearnedRules" class="teddy-routing-list"></div>
                </div>

                <div class="setting-actions">
                    <button class="btn-save" id="saveSettings">저장</button>''',
    'routing settings section',
)

INDEX.write_text(text, encoding='utf-8')
print('teddy routing UI patch: OK')
