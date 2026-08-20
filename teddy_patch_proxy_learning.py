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
        """    'manual_proxies': [],\n    'healthy': [],\n""",
        """    'manual_proxies': [],\n    'performance': {},\n    'healthy': [],\n""",
        'proxy learning state',
    )

    replace_once(
        POOL,
        """    with _lock:\n        _state['enabled'] = bool(raw.get('enabled', True))\n        _state['manual_proxies'] = manual[:100]\n        _state['proxy_switch_count'] = int(raw.get('proxy_switch_count') or 0)\n""",
        """    performance = {}\n    raw_performance = raw.get('performance') or {}\n    if isinstance(raw_performance, dict):\n        for key, value in raw_performance.items():\n            normalized = _normalize_proxy(key)\n            if not normalized or not isinstance(value, dict):\n                continue\n            performance[normalized] = {\n                'learned_speed_bps': max(0, int(value.get('learned_speed_bps') or 0)),\n                'transfer_samples': max(0, int(value.get('transfer_samples') or 0)),\n                'transfer_bytes': max(0, int(value.get('transfer_bytes') or 0)),\n                'task_success_count': max(0, int(value.get('task_success_count') or 0)),\n                'failure_count': max(0, int(value.get('failure_count') or 0)),\n                'failure_streak': max(0, min(8, int(value.get('failure_streak') or 0))),\n                'last_success_at': max(0, int(value.get('last_success_at') or 0)),\n                'last_failure_at': max(0, int(value.get('last_failure_at') or 0)),\n                'last_failure_reason': str(value.get('last_failure_reason') or '')[:160],\n            }\n    with _lock:\n        _state['enabled'] = bool(raw.get('enabled', True))\n        _state['manual_proxies'] = manual[:100]\n        _state['performance'] = dict(list(performance.items())[-200:])\n        _state['proxy_switch_count'] = int(raw.get('proxy_switch_count') or 0)\n""",
        'load proxy performance',
    )

    replace_once(
        POOL,
        """            'manual_proxies': list(_state['manual_proxies']),\n            'proxy_switch_count': int(_state['proxy_switch_count']),\n""",
        """            'manual_proxies': list(_state['manual_proxies']),\n            'performance': dict(list(_state['performance'].items())[-200:]),\n            'proxy_switch_count': int(_state['proxy_switch_count']),\n""",
        'save proxy performance',
    )

    replace_once(
        POOL,
        """_core = None\n_state = {\n""",
        """_core = None\n_learning_last_save_monotonic = 0.0\n_state = {\n""",
        'learning save throttle state',
    )

    replace_once(
        POOL,
        """def _rank_by_real_speed(core, healthy):\n    # First keep only the already HTTPS-verified candidates. Benchmark a small\n""",
        """def _performance_for(proxy):\n    with _lock:\n        return dict((_state.get('performance') or {}).get(proxy) or {})\n\n\ndef _apply_learned_stats(row):\n    result = dict(row)\n    stats = _performance_for(result.get('proxy') or '')\n    result['learned_speed_bps'] = int(stats.get('learned_speed_bps') or 0)\n    result['transfer_samples'] = int(stats.get('transfer_samples') or 0)\n    result['transfer_bytes'] = int(stats.get('transfer_bytes') or 0)\n    result['task_success_count'] = int(stats.get('task_success_count') or 0)\n    result['failure_count'] = int(stats.get('failure_count') or 0)\n    result['failure_streak'] = int(stats.get('failure_streak') or 0)\n    result['last_success_at'] = int(stats.get('last_success_at') or 0)\n    result['last_failure_at'] = int(stats.get('last_failure_at') or 0)\n    return result\n\n\ndef _selection_key(row):\n    learned = int(row.get('learned_speed_bps') or 0)\n    samples = int(row.get('transfer_samples') or 0)\n    benchmark = int(row.get('speed_bps') or 0)\n    effective = learned if samples >= 2 and learned > 0 else benchmark\n    if not effective:\n        effective = max(1, 1_000_000 - int(row.get('latency_ms') or 999999))\n    streak = min(6, int(row.get('failure_streak') or 0))\n    penalty = 0.45 ** streak\n    completed = min(5, int(row.get('task_success_count') or 0))\n    success_bonus = 1.0 + completed * 0.04\n    score = int(effective * penalty * success_bonus)\n    return (-score, int(row.get('latency_ms') or 999999))\n\n\ndef _rank_by_real_speed(core, healthy):\n    # First keep only the already HTTPS-verified candidates. Benchmark a small\n""",
        'proxy learned ranking helpers',
    )

    replace_once(
        POOL,
        """    rows = []\n    for row in healthy:\n        rows.append(measured.get(row.get('proxy'), dict(row)))\n    rows.sort(key=lambda row: (\n        0 if int(row.get('speed_bps') or 0) > 0 else 1,\n        -int(row.get('speed_bps') or 0),\n        int(row.get('latency_ms') or 999999),\n    ))\n    return rows\n""",
        """    rows = []\n    for row in healthy:\n        rows.append(_apply_learned_stats(measured.get(row.get('proxy'), dict(row))))\n    rows.sort(key=_selection_key)\n    return rows\n""",
        'rank by learned real-world quality',
    )

    replace_once(
        POOL,
        """def current_proxy(core=None):\n""",
        """def _maybe_save_learning(core, force=False):\n    global _learning_last_save_monotonic\n    now = time.monotonic()\n    with _lock:\n        if not force and now - _learning_last_save_monotonic < 30:\n            return\n        _learning_last_save_monotonic = now\n    _save(core)\n\n\ndef _proxy_for_task(core, task_id):\n    task = core.tasks.get(task_id) or {}\n    if task.get('network_mode') != 'proxy':\n        return ''\n    proxy = str(task.get('network_proxy') or '').strip()\n    if proxy:\n        return proxy\n    with _lock:\n        return str(_state['healthy'][0].get('proxy') or '') if _state['healthy'] else ''\n\n\ndef observe_transfer(core, task_id, byte_count, elapsed):\n    proxy = _proxy_for_task(core, task_id)\n    byte_count = max(0, int(byte_count or 0))\n    elapsed = float(elapsed or 0.0)\n    if not proxy or byte_count < 64 * 1024 or elapsed <= 0:\n        return\n    speed = int(byte_count / max(elapsed, 0.001))\n    now = int(time.time())\n    with _lock:\n        stats = _state['performance'].setdefault(proxy, {})\n        old_speed = int(stats.get('learned_speed_bps') or 0)\n        samples = int(stats.get('transfer_samples') or 0)\n        learned = speed if not old_speed else int(old_speed * 0.75 + speed * 0.25)\n        stats['learned_speed_bps'] = learned\n        stats['transfer_samples'] = samples + 1\n        stats['transfer_bytes'] = int(stats.get('transfer_bytes') or 0) + byte_count\n        stats['failure_streak'] = 0\n        stats['last_success_at'] = now\n        for row in _state['healthy']:\n            if row.get('proxy') == proxy:\n                row.update({\n                    'learned_speed_bps': learned,\n                    'transfer_samples': samples + 1,\n                    'transfer_bytes': int(stats['transfer_bytes']),\n                    'failure_streak': 0,\n                    'last_success_at': now,\n                })\n                break\n    task = core.tasks.get(task_id)\n    if task is not None:\n        task['network_proxy_learned_speed_bps'] = learned\n        task['network_proxy_learning_samples'] = samples + 1\n    _maybe_save_learning(core)\n\n\ndef note_failure(core, reason=''):\n    with _lock:\n        current = dict(_state['healthy'][0]) if _state['healthy'] else {}\n        proxy = str(current.get('proxy') or '')\n        if not proxy:\n            return\n        stats = _state['performance'].setdefault(proxy, {})\n        stats['failure_count'] = int(stats.get('failure_count') or 0) + 1\n        stats['failure_streak'] = min(8, int(stats.get('failure_streak') or 0) + 1)\n        stats['last_failure_at'] = int(time.time())\n        stats['last_failure_reason'] = str(reason or '')[:160]\n    _maybe_save_learning(core, force=True)\n\n\ndef observe_task_success(core, task_id):\n    proxy = _proxy_for_task(core, task_id)\n    if not proxy:\n        return\n    now = int(time.time())\n    with _lock:\n        stats = _state['performance'].setdefault(proxy, {})\n        stats['task_success_count'] = int(stats.get('task_success_count') or 0) + 1\n        stats['failure_streak'] = 0\n        stats['last_success_at'] = now\n        for row in _state['healthy']:\n            if row.get('proxy') == proxy:\n                row['task_success_count'] = int(stats['task_success_count'])\n                row['failure_streak'] = 0\n                row['last_success_at'] = now\n                break\n    _maybe_save_learning(core, force=True)\n    stats = _performance_for(proxy)\n    print(\n        f\"[Proxy 학습] 완료 성공: {proxy} · 실사용 {int(stats.get('learned_speed_bps') or 0) / 1024 / 1024:.2f} MB/s \"\n        f\"· 완료 {int(stats.get('task_success_count') or 0)}회 · 실패 {int(stats.get('failure_count') or 0)}회\",\n        flush=True,\n    )\n\n\ndef current_proxy(core=None):\n""",
        'proxy real-use learning observers',
    )

    replace_once(
        POOL,
        """            'current_speed_bps': int(current.get('speed_bps') or 0),\n            'current_bandwidth_ms': int(current.get('bandwidth_ms') or 0),\n            'speed_tested_count': sum(1 for row in _state['healthy'] if int(row.get('speed_bps') or 0) > 0),\n""",
        """            'current_speed_bps': int(current.get('speed_bps') or 0),\n            'current_bandwidth_ms': int(current.get('bandwidth_ms') or 0),\n            'current_learned_speed_bps': int(current.get('learned_speed_bps') or 0),\n            'current_transfer_samples': int(current.get('transfer_samples') or 0),\n            'current_task_success_count': int(current.get('task_success_count') or 0),\n            'current_failure_count': int(current.get('failure_count') or 0),\n            'current_failure_streak': int(current.get('failure_streak') or 0),\n            'learned_proxy_count': sum(1 for row in _state['healthy'] if int(row.get('transfer_samples') or 0) >= 2),\n            'speed_tested_count': sum(1 for row in _state['healthy'] if int(row.get('speed_bps') or 0) > 0),\n""",
        'proxy learning status fields',
    )

    replace_once(
        POOL,
        """    routing_module.set_proxy_provider(lambda: current_proxy(core))\n\n    @core.app.route('/api/proxy/status', methods=['GET'])\n""",
        """    routing_module.set_proxy_provider(lambda: current_proxy(core))\n    core._teddy_proxy_transfer_observer = lambda task_id, byte_count, elapsed: observe_transfer(\n        core, task_id, byte_count, elapsed\n    )\n\n    @core.app.route('/api/proxy/status', methods=['GET'])\n""",
        'install proxy transfer observer',
    )

    replace_once(
        ENTRYPOINT,
        """            batch_speed = batch_bytes / elapsed\n            speed_samples.append(batch_speed)\n""",
        """            batch_speed = batch_bytes / elapsed\n            observer = getattr(core, '_teddy_proxy_transfer_observer', None)\n            if observer:\n                try:\n                    observer(task_id, batch_bytes, elapsed)\n                except Exception as exc:\n                    print(f'[Proxy 학습] 전송 샘플 기록 실패: {exc}', flush=True)\n            speed_samples.append(batch_speed)\n""",
        'observe real HLS transfer speed',
    )

    replace_once(
        BOOTSTRAP,
        """                else:\n                    if not teddy_proxy_pool.rotate_after_failure(core, reason=message):\n                        raise\n                    _proxy_last_rotation_at[task_id] = time.monotonic()\n""",
        """                else:\n                    teddy_proxy_pool.note_failure(core, reason=message)\n                    if not teddy_proxy_pool.rotate_after_failure(core, reason=message):\n                        raise\n                    _proxy_last_rotation_at[task_id] = time.monotonic()\n""",
        'learn only actual proxy rotations as failures',
    )

    replace_once(
        BOOTSTRAP,
        """        if status == 'complete':\n            teddy_routing.learn_success(core, url, mode, source)\n            return\n""",
        """        if status == 'complete':\n            if mode == 'proxy':\n                teddy_proxy_pool.observe_task_success(core, task_id)\n            teddy_routing.learn_success(core, url, mode, source)\n            return\n""",
        'learn completed proxy task',
    )

    replace_once(
        ROUTING_PATCH,
        """        const proxySpeed = Number(task.network_proxy_speed_bps) || 0;\n        const proxyDetail = task.network_mode === 'proxy'\n            ? (proxySpeed ? ' · 검사 ' + formatSize(proxySpeed) + '/s' : '') +\n              (task.network_proxy_latency_ms ? ' · ' + task.network_proxy_latency_ms + 'ms' : '')\n            : '';\n""",
        """        const proxySpeed = Number(task.network_proxy_speed_bps) || 0;\n        const proxyLearned = Number(task.network_proxy_learned_speed_bps) || 0;\n        const proxyDetail = task.network_mode === 'proxy'\n            ? (proxyLearned ? ' · 실사용 ' + formatSize(proxyLearned) + '/s'\n                            : (proxySpeed ? ' · 검사 ' + formatSize(proxySpeed) + '/s' : '')) +\n              (task.network_proxy_latency_ms ? ' · ' + task.network_proxy_latency_ms + 'ms' : '')\n            : '';\n""",
        'prefer learned speed on task card',
    )

    replace_once(
        PROXY_JS,
        """        const measuredSpeed = Number(data && data.current_speed_bps) || 0;\n        const speedTested = Number(data && data.speed_tested_count) || 0;\n""",
        """        const measuredSpeed = Number(data && data.current_speed_bps) || 0;\n        const learnedSpeed = Number(data && data.current_learned_speed_bps) || 0;\n        const learningSamples = Number(data && data.current_transfer_samples) || 0;\n        const learnedCount = Number(data && data.learned_proxy_count) || 0;\n        const completedCount = Number(data && data.current_task_success_count) || 0;\n        const failureCount = Number(data && data.current_failure_count) || 0;\n        const speedTested = Number(data && data.speed_tested_count) || 0;\n""",
        'proxy learning panel values',
    )

    replace_once(
        PROXY_JS,
        """            status.textContent = `정상 ${healthy}개 / 후보 ${candidates}개 · 속도 측정 ${speedTested}개 · 마지막 갱신 ${lastRefresh} · 자동 교체 ${switches}회`;\n""",
        """            status.textContent = `정상 ${healthy}개 / 후보 ${candidates}개 · 실사용 학습 ${learnedCount}개 · 검사 ${speedTested}개 · 마지막 갱신 ${lastRefresh} · 자동 교체 ${switches}회`;\n""",
        'proxy learned count UI',
    )

    replace_once(
        PROXY_JS,
        """        const speedText = measuredSpeed ? ` · 검사 ${(measuredSpeed / 1024 / 1024).toFixed(2)} MB/s` : '';\n        currentEl.textContent = current\n            ? `현재 ${current}${speedText}${latency ? ` · ${latency}ms` : ''}${exitIp ? ` · 출구 ${exitIp}` : ''}${source ? ` · ${source}` : ''}`\n            : '현재 선택된 프록시 없음';\n""",
        """        const learnedText = learnedSpeed ? ` · 실사용 ${(learnedSpeed / 1024 / 1024).toFixed(2)} MB/s` : '';\n        const speedText = measuredSpeed ? ` · 검사 ${(measuredSpeed / 1024 / 1024).toFixed(2)} MB/s` : '';\n        const historyText = (learningSamples || completedCount || failureCount)\n            ? ` · 학습 ${learningSamples}배치 · 완료 ${completedCount} · 실패 ${failureCount}`\n            : '';\n        currentEl.textContent = current\n            ? `현재 ${current}${learnedText}${speedText}${historyText}${latency ? ` · ${latency}ms` : ''}${exitIp ? ` · 출구 ${exitIp}` : ''}${source ? ` · ${source}` : ''}`\n            : '현재 선택된 프록시 없음';\n""",
        'proxy real-use learning UI',
    )

    print('proxy real-use learning runtime patch: OK')


if __name__ == '__main__':
    main()
