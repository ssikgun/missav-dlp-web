from pathlib import Path


POOL = Path('teddy_proxy_pool.py')
ENTRYPOINT = Path('teddy_entrypoint.py')
BOOTSTRAP = Path('teddy_bootstrap.py')
ROUTING_PATCH = Path('teddy_patch_routing.py')
PROXY_JS = Path('templates/teddy-proxy.js')


def replace_once(path, old, new, label):
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one patch anchor, found {count}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


def main():
    replace_once(
        POOL,
        """    'manual_proxies': [],
    'healthy': [],
""",
        """    'manual_proxies': [],
    'performance': {},
    'healthy': [],
""",
        'proxy learning state',
    )

    replace_once(
        POOL,
        """    with _lock:
        _state['enabled'] = bool(raw.get('enabled', True))
        _state['manual_proxies'] = manual[:100]
        _state['proxy_switch_count'] = int(raw.get('proxy_switch_count') or 0)
""",
        """    performance = {}
    raw_performance = raw.get('performance') or {}
    if isinstance(raw_performance, dict):
        for key, value in raw_performance.items():
            normalized = _normalize_proxy(key)
            if not normalized or not isinstance(value, dict):
                continue
            performance[normalized] = {
                'learned_speed_bps': max(0, int(value.get('learned_speed_bps') or 0)),
                'transfer_samples': max(0, int(value.get('transfer_samples') or 0)),
                'transfer_bytes': max(0, int(value.get('transfer_bytes') or 0)),
                'task_success_count': max(0, int(value.get('task_success_count') or 0)),
                'failure_count': max(0, int(value.get('failure_count') or 0)),
                'failure_streak': max(0, min(8, int(value.get('failure_streak') or 0))),
                'last_success_at': max(0, int(value.get('last_success_at') or 0)),
                'last_failure_at': max(0, int(value.get('last_failure_at') or 0)),
                'last_failure_reason': str(value.get('last_failure_reason') or '')[:160],
            }
    with _lock:
        _state['enabled'] = bool(raw.get('enabled', True))
        _state['manual_proxies'] = manual[:100]
        _state['performance'] = dict(list(performance.items())[-200:])
        _state['proxy_switch_count'] = int(raw.get('proxy_switch_count') or 0)
""",
        'load proxy performance',
    )

    replace_once(
        POOL,
        """def _save(core):
    with _lock:
        payload = {
            'enabled': bool(_state['enabled']),
            'manual_proxies': list(_state['manual_proxies']),
            'proxy_switch_count': int(_state['proxy_switch_count']),
""",
        """def _save(core):
    with _lock:
        payload = {
            'enabled': bool(_state['enabled']),
            'manual_proxies': list(_state['manual_proxies']),
            'performance': dict(list(_state['performance'].items())[-200:]),
            'proxy_switch_count': int(_state['proxy_switch_count']),
""",
        'save proxy performance',
    )

    replace_once(
        POOL,
        """_core = None
_state = {
""",
        """_core = None
_learning_last_save_monotonic = 0.0
_state = {
""",
        'learning save throttle state',
    )

    replace_once(
        POOL,
        """def _rank_by_real_speed(core, healthy):
    # First keep only the already HTTPS-verified candidates. Benchmark a small
""",
        """def _performance_for(proxy):
    with _lock:
        return dict((_state.get('performance') or {}).get(proxy) or {})


def _apply_learned_stats(row):
    result = dict(row)
    stats = _performance_for(result.get('proxy') or '')
    result['learned_speed_bps'] = int(stats.get('learned_speed_bps') or 0)
    result['transfer_samples'] = int(stats.get('transfer_samples') or 0)
    result['transfer_bytes'] = int(stats.get('transfer_bytes') or 0)
    result['task_success_count'] = int(stats.get('task_success_count') or 0)
    result['failure_count'] = int(stats.get('failure_count') or 0)
    result['failure_streak'] = int(stats.get('failure_streak') or 0)
    result['last_success_at'] = int(stats.get('last_success_at') or 0)
    result['last_failure_at'] = int(stats.get('last_failure_at') or 0)
    return result


def _selection_key(row):
    learned = int(row.get('learned_speed_bps') or 0)
    samples = int(row.get('transfer_samples') or 0)
    benchmark = int(row.get('speed_bps') or 0)
    effective = learned if samples >= 2 and learned > 0 else benchmark
    if not effective:
        effective = max(1, 1_000_000 - int(row.get('latency_ms') or 999999))
    streak = min(6, int(row.get('failure_streak') or 0))
    penalty = 0.45 ** streak
    completed = min(5, int(row.get('task_success_count') or 0))
    success_bonus = 1.0 + completed * 0.04
    score = int(effective * penalty * success_bonus)
    return (-score, int(row.get('latency_ms') or 999999))


def _rank_by_real_speed(core, healthy):
    # First keep only the already HTTPS-verified candidates. Benchmark a small
""",
        'proxy learned ranking helpers',
    )

    replace_once(
        POOL,
        """    rows = []
    for row in healthy:
        rows.append(measured.get(row.get('proxy'), dict(row)))
    rows.sort(key=lambda row: (
        0 if int(row.get('speed_bps') or 0) > 0 else 1,
        -int(row.get('speed_bps') or 0),
        int(row.get('latency_ms') or 999999),
    ))
    return rows
""",
        """    rows = []
    for row in healthy:
        rows.append(_apply_learned_stats(measured.get(row.get('proxy'), dict(row))))
    rows.sort(key=_selection_key)
    return rows
""",
        'rank by learned real-world quality',
    )

    replace_once(
        POOL,
        """def current_proxy(core=None):
""",
        """def _maybe_save_learning(core, force=False):
    global _learning_last_save_monotonic
    now = time.monotonic()
    with _lock:
        if not force and now - _learning_last_save_monotonic < 30:
            return
        _learning_last_save_monotonic = now
    _save(core)


def _proxy_for_task(core, task_id):
    task = core.tasks.get(task_id) or {}
    if task.get('network_mode') != 'proxy':
        return ''
    proxy = str(task.get('network_proxy') or '').strip()
    if proxy:
        return proxy
    with _lock:
        return str(_state['healthy'][0].get('proxy') or '') if _state['healthy'] else ''


def observe_transfer(core, task_id, byte_count, elapsed):
    proxy = _proxy_for_task(core, task_id)
    byte_count = max(0, int(byte_count or 0))
    elapsed = float(elapsed or 0.0)
    if not proxy or byte_count < 64 * 1024 or elapsed <= 0:
        return
    speed = int(byte_count / max(elapsed, 0.001))
    now = int(time.time())
    with _lock:
        stats = _state['performance'].setdefault(proxy, {})
        old_speed = int(stats.get('learned_speed_bps') or 0)
        samples = int(stats.get('transfer_samples') or 0)
        learned = speed if not old_speed else int(old_speed * 0.75 + speed * 0.25)
        stats['learned_speed_bps'] = learned
        stats['transfer_samples'] = samples + 1
        stats['transfer_bytes'] = int(stats.get('transfer_bytes') or 0) + byte_count
        stats['failure_streak'] = 0
        stats['last_success_at'] = now
        for row in _state['healthy']:
            if row.get('proxy') == proxy:
                row.update({
                    'learned_speed_bps': learned,
                    'transfer_samples': samples + 1,
                    'transfer_bytes': int(stats['transfer_bytes']),
                    'failure_streak': 0,
                    'last_success_at': now,
                })
                break
    task = core.tasks.get(task_id)
    if task is not None:
        task['network_proxy_learned_speed_bps'] = learned
        task['network_proxy_learning_samples'] = samples + 1
    _maybe_save_learning(core)


def note_failure(core, reason=''):
    with _lock:
        current = dict(_state['healthy'][0]) if _state['healthy'] else {}
        proxy = str(current.get('proxy') or '')
        if not proxy:
            return
        stats = _state['performance'].setdefault(proxy, {})
        stats['failure_count'] = int(stats.get('failure_count') or 0) + 1
        stats['failure_streak'] = min(8, int(stats.get('failure_streak') or 0) + 1)
        stats['last_failure_at'] = int(time.time())
        stats['last_failure_reason'] = str(reason or '')[:160]
    _maybe_save_learning(core, force=True)


def observe_task_success(core, task_id):
    proxy = _proxy_for_task(core, task_id)
    if not proxy:
        return
    now = int(time.time())
    with _lock:
        stats = _state['performance'].setdefault(proxy, {})
        stats['task_success_count'] = int(stats.get('task_success_count') or 0) + 1
        stats['failure_streak'] = 0
        stats['last_success_at'] = now
        for row in _state['healthy']:
            if row.get('proxy') == proxy:
                row['task_success_count'] = int(stats['task_success_count'])
                row['failure_streak'] = 0
                row['last_success_at'] = now
                break
    _maybe_save_learning(core, force=True)
    stats = _performance_for(proxy)
    print(
        f"[Proxy 학습] 완료 성공: {proxy} · 실사용 {int(stats.get('learned_speed_bps') or 0) / 1024 / 1024:.2f} MB/s "
        f"· 완료 {int(stats.get('task_success_count') or 0)}회 · 실패 {int(stats.get('failure_count') or 0)}회",
        flush=True,
    )


def current_proxy(core=None):
""",
        'proxy real-use learning observers',
    )

    replace_once(
        POOL,
        """            'current_speed_bps': int(current.get('speed_bps') or 0),
            'current_bandwidth_ms': int(current.get('bandwidth_ms') or 0),
            'speed_tested_count': sum(1 for row in _state['healthy'] if int(row.get('speed_bps') or 0) > 0),
""",
        """            'current_speed_bps': int(current.get('speed_bps') or 0),
            'current_bandwidth_ms': int(current.get('bandwidth_ms') or 0),
            'current_learned_speed_bps': int(current.get('learned_speed_bps') or 0),
            'current_transfer_samples': int(current.get('transfer_samples') or 0),
            'current_task_success_count': int(current.get('task_success_count') or 0),
            'current_failure_count': int(current.get('failure_count') or 0),
            'current_failure_streak': int(current.get('failure_streak') or 0),
            'learned_proxy_count': sum(1 for row in _state['healthy'] if int(row.get('transfer_samples') or 0) >= 2),
            'speed_tested_count': sum(1 for row in _state['healthy'] if int(row.get('speed_bps') or 0) > 0),
""",
        'proxy learning status fields',
    )

    replace_once(
        POOL,
        """    routing_module.set_proxy_provider(lambda: current_proxy(core))

    @core.app.route('/api/proxy/status', methods=['GET'])
""",
        """    routing_module.set_proxy_provider(lambda: current_proxy(core))
    core._teddy_proxy_transfer_observer = lambda task_id, byte_count, elapsed: observe_transfer(
        core, task_id, byte_count, elapsed
    )

    @core.app.route('/api/proxy/status', methods=['GET'])
""",
        'install proxy transfer observer',
    )

    replace_once(
        ENTRYPOINT,
        """            batch_speed = batch_bytes / elapsed
            speed_samples.append(batch_speed)
""",
        """            batch_speed = batch_bytes / elapsed
            observer = getattr(core, '_teddy_proxy_transfer_observer', None)
            if observer:
                try:
                    observer(task_id, batch_bytes, elapsed)
                except Exception as exc:
                    print(f'[Proxy 학습] 전송 샘플 기록 실패: {exc}', flush=True)
            speed_samples.append(batch_speed)
""",
        'observe real HLS transfer speed',
    )

    replace_once(
        BOOTSTRAP,
        """                else:
                    if not teddy_proxy_pool.rotate_after_failure(core, reason=message):
                        raise
                    _proxy_last_rotation_at[task_id] = time.monotonic()
""",
        """                else:
                    teddy_proxy_pool.note_failure(core, reason=message)
                    if not teddy_proxy_pool.rotate_after_failure(core, reason=message):
                        raise
                    _proxy_last_rotation_at[task_id] = time.monotonic()
""",
        'learn only actual proxy rotations as failures',
    )

    replace_once(
        BOOTSTRAP,
        """        if status == 'complete':
            teddy_routing.learn_success(core, url, mode, source)
            return
""",
        """        if status == 'complete':
            if mode == 'proxy':
                teddy_proxy_pool.observe_task_success(core, task_id)
            teddy_routing.learn_success(core, url, mode, source)
            return
""",
        'learn completed proxy task',
    )

    replace_once(
        ROUTING_PATCH,
        """        const proxySpeed = Number(task.network_proxy_speed_bps) || 0;
        const proxyDetail = task.network_mode === 'proxy'
            ? (proxySpeed ? ' · 검사 ' + formatSize(proxySpeed) + '/s' : '') +
              (task.network_proxy_latency_ms ? ' · ' + task.network_proxy_latency_ms + 'ms' : '')
            : '';
""",
        """        const proxySpeed = Number(task.network_proxy_speed_bps) || 0;
        const proxyLearned = Number(task.network_proxy_learned_speed_bps) || 0;
        const proxyDetail = task.network_mode === 'proxy'
            ? (proxyLearned ? ' · 실사용 ' + formatSize(proxyLearned) + '/s'
                            : (proxySpeed ? ' · 검사 ' + formatSize(proxySpeed) + '/s' : '')) +
              (task.network_proxy_latency_ms ? ' · ' + task.network_proxy_latency_ms + 'ms' : '')
            : '';
""",
        'prefer learned speed on task card',
    )

    replace_once(
        PROXY_JS,
        """        const measuredSpeed = Number(data && data.current_speed_bps) || 0;
        const speedTested = Number(data && data.speed_tested_count) || 0;
""",
        """        const measuredSpeed = Number(data && data.current_speed_bps) || 0;
        const learnedSpeed = Number(data && data.current_learned_speed_bps) || 0;
        const learningSamples = Number(data && data.current_transfer_samples) || 0;
        const learnedCount = Number(data && data.learned_proxy_count) || 0;
        const completedCount = Number(data && data.current_task_success_count) || 0;
        const failureCount = Number(data && data.current_failure_count) || 0;
        const speedTested = Number(data && data.speed_tested_count) || 0;
""",
        'proxy learning panel values',
    )

    replace_once(
        PROXY_JS,
        """            status.textContent = `정상 ${healthy}개 / 후보 ${candidates}개 · 속도 측정 ${speedTested}개 · 마지막 갱신 ${lastRefresh} · 자동 교체 ${switches}회`;
""",
        """            status.textContent = `정상 ${healthy}개 / 후보 ${candidates}개 · 실사용 학습 ${learnedCount}개 · 검사 ${speedTested}개 · 마지막 갱신 ${lastRefresh} · 자동 교체 ${switches}회`;
""",
        'proxy learned count UI',
    )

    replace_once(
        PROXY_JS,
        """        const speedText = measuredSpeed ? ` · 검사 ${(measuredSpeed / 1024 / 1024).toFixed(2)} MB/s` : '';
        currentEl.textContent = current
            ? `현재 ${current}${speedText}${latency ? ` · ${latency}ms` : ''}${exitIp ? ` · 출구 ${exitIp}` : ''}${source ? ` · ${source}` : ''}`
            : '현재 선택된 프록시 없음';
""",
        """        const learnedText = learnedSpeed ? ` · 실사용 ${(learnedSpeed / 1024 / 1024).toFixed(2)} MB/s` : '';
        const speedText = measuredSpeed ? ` · 검사 ${(measuredSpeed / 1024 / 1024).toFixed(2)} MB/s` : '';
        const historyText = (learningSamples || completedCount || failureCount)
            ? ` · 학습 ${learningSamples}배치 · 완료 ${completedCount} · 실패 ${failureCount}`
            : '';
        currentEl.textContent = current
            ? `현재 ${current}${learnedText}${speedText}${historyText}${latency ? ` · ${latency}ms` : ''}${exitIp ? ` · 출구 ${exitIp}` : ''}${source ? ` · ${source}` : ''}`
            : '현재 선택된 프록시 없음';
""",
        'proxy real-use learning UI',
    )

    print('proxy real-use learning runtime patch: OK')


if __name__ == '__main__':
    main()
