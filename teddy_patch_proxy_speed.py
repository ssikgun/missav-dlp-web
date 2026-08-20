from pathlib import Path


POOL = Path('teddy_proxy_pool.py')
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
        """CHECK_WORKERS = 12\nTEST_URL = 'https://api.ipify.org?format=json'\n""",
        """CHECK_WORKERS = 12\nTEST_URL = 'https://api.ipify.org?format=json'\nBANDWIDTH_TEST_BYTES = 512 * 1024\nBANDWIDTH_TEST_LIMIT = 8\nBANDWIDTH_TEST_WORKERS = 4\nBANDWIDTH_TIMEOUT_SECONDS = 10\nBANDWIDTH_URL = f'https://speed.cloudflare.com/__down?bytes={BANDWIDTH_TEST_BYTES}'\n""",
        'proxy bandwidth constants',
    )

    replace_once(
        POOL,
        """    except Exception:\n        return None\n\n\ndef refresh(core=None):\n""",
        """    except Exception:\n        return None\n\n\ndef _measure_bandwidth(core, row):\n    proxy = row.get('proxy') or ''\n    if not proxy:\n        return dict(row)\n    started = time.monotonic()\n    measured = dict(row)\n    measured['speed_bps'] = 0\n    measured['bandwidth_ms'] = 0\n    measured['bandwidth_bytes'] = 0\n    measured['bandwidth_error'] = ''\n    try:\n        response = core.cffi_requests.get(\n            BANDWIDTH_URL,\n            impersonate='firefox135',\n            timeout=BANDWIDTH_TIMEOUT_SECONDS,\n            headers={'Cache-Control': 'no-cache'},\n            proxies={'http': proxy, 'https': proxy},\n        )\n        if response.status_code != 200:\n            raise RuntimeError(f'HTTP {response.status_code}')\n        received = len(response.content or b'')\n        if received < BANDWIDTH_TEST_BYTES // 2:\n            raise RuntimeError(f'짧은 응답 {received} bytes')\n        elapsed = max(time.monotonic() - started, 0.001)\n        measured['speed_bps'] = int(received / elapsed)\n        measured['bandwidth_ms'] = int(elapsed * 1000)\n        measured['bandwidth_bytes'] = received\n        measured['bandwidth_checked_at'] = int(time.time())\n    except Exception as exc:\n        measured['bandwidth_error'] = str(exc)[:160]\n    return measured\n\n\ndef _rank_by_real_speed(core, healthy):\n    # First keep only the already HTTPS-verified candidates. Benchmark a small\n    # latency-shortlist so refresh traffic stays bounded even when feeds contain\n    # thousands of public proxies. A benchmark failure demotes but does not drop\n    # a proxy because some exits can block the speed-test host while still being\n    # useful for the actual media site.\n    healthy = sorted(healthy, key=lambda row: row.get('latency_ms', 999999))[:MAX_HEALTHY]\n    targets = healthy[:min(BANDWIDTH_TEST_LIMIT, len(healthy))]\n    measured = {}\n    if targets:\n        with ThreadPoolExecutor(max_workers=min(BANDWIDTH_TEST_WORKERS, len(targets))) as executor:\n            futures = {executor.submit(_measure_bandwidth, core, row): row.get('proxy') for row in targets}\n            for future in as_completed(futures):\n                result = future.result()\n                measured[result.get('proxy')] = result\n\n    rows = []\n    for row in healthy:\n        rows.append(measured.get(row.get('proxy'), dict(row)))\n    rows.sort(key=lambda row: (\n        0 if int(row.get('speed_bps') or 0) > 0 else 1,\n        -int(row.get('speed_bps') or 0),\n        int(row.get('latency_ms') or 999999),\n    ))\n    return rows\n\n\ndef refresh(core=None):\n""",
        'proxy bandwidth measurement helpers',
    )

    replace_once(
        POOL,
        """        healthy.sort(key=lambda row: row.get('latency_ms', 999999))\n        healthy = healthy[:MAX_HEALTHY]\n\n        with _lock:\n""",
        """        healthy = _rank_by_real_speed(core, healthy)\n\n        with _lock:\n""",
        'rank proxy pool by measured speed',
    )

    replace_once(
        POOL,
        """        print(\n            f'[Proxy] pool 갱신 완료: 후보 {len(candidates)}개 -> 정상 {len(healthy)}개'\n            + (f\" · 최고 {healthy[0]['latency_ms']}ms\" if healthy else ''),\n            flush=True,\n        )\n""",
        """        best_speed = int(healthy[0].get('speed_bps') or 0) if healthy else 0\n        best_detail = ''\n        if healthy:\n            if best_speed:\n                best_detail = f\" · 최고 {best_speed / 1024 / 1024:.2f} MB/s · {healthy[0]['latency_ms']}ms\"\n            else:\n                best_detail = f\" · 최고 {healthy[0]['latency_ms']}ms (전송속도 측정 실패)\"\n        print(\n            f'[Proxy] pool 갱신 완료: 후보 {len(candidates)}개 -> 정상 {len(healthy)}개' + best_detail,\n            flush=True,\n        )\n""",
        'proxy refresh speed log',
    )

    replace_once(
        POOL,
        """            'current_latency_ms': int(current.get('latency_ms') or 0),\n            'current_source': current.get('source', ''),\n""",
        """            'current_latency_ms': int(current.get('latency_ms') or 0),\n            'current_speed_bps': int(current.get('speed_bps') or 0),\n            'current_bandwidth_ms': int(current.get('bandwidth_ms') or 0),\n            'speed_tested_count': sum(1 for row in _state['healthy'] if int(row.get('speed_bps') or 0) > 0),\n            'bandwidth_test_bytes': BANDWIDTH_TEST_BYTES,\n            'current_source': current.get('source', ''),\n""",
        'proxy speed status fields',
    )

    replace_once(
        POOL,
        """    print('[Teddy] free proxy pool enabled: auto collect -> HTTPS verify -> fastest candidates', flush=True)\n""",
        """    print('[Teddy] free proxy pool enabled: auto collect -> HTTPS verify -> real-speed ranking', flush=True)\n""",
        'proxy pool startup log',
    )

    replace_once(
        BOOTSTRAP,
        """                current['network_proxy_latency_ms'] = int(record.get('latency_ms') or 0)\n                core.save_tasks()\n""",
        """                current['network_proxy_latency_ms'] = int(record.get('latency_ms') or 0)\n                current['network_proxy_speed_bps'] = int(record.get('speed_bps') or 0)\n                core.save_tasks()\n""",
        'proxy rotated task speed metadata',
    )

    replace_once(
        BOOTSTRAP,
        """            task['network_proxy_latency_ms'] = int(record.get('latency_ms') or 0)\n            task['network_proxy_exit_ip'] = record.get('exit_ip', '')\n        else:\n            task.pop('network_proxy', None)\n            task.pop('network_proxy_latency_ms', None)\n            task.pop('network_proxy_exit_ip', None)\n""",
        """            task['network_proxy_latency_ms'] = int(record.get('latency_ms') or 0)\n            task['network_proxy_speed_bps'] = int(record.get('speed_bps') or 0)\n            task['network_proxy_exit_ip'] = record.get('exit_ip', '')\n        else:\n            task.pop('network_proxy', None)\n            task.pop('network_proxy_latency_ms', None)\n            task.pop('network_proxy_speed_bps', None)\n            task.pop('network_proxy_exit_ip', None)\n""",
        'proxy task speed metadata',
    )

    replace_once(
        ROUTING_PATCH,
        """        const proxyDetail = task.network_mode === 'proxy' && task.network_proxy_latency_ms\n            ? ' · ' + task.network_proxy_latency_ms + 'ms'\n            : '';\n""",
        """        const proxySpeed = Number(task.network_proxy_speed_bps) || 0;\n        const proxyDetail = task.network_mode === 'proxy'\n            ? (proxySpeed ? ' · 검사 ' + formatSize(proxySpeed) + '/s' : '') +\n              (task.network_proxy_latency_ms ? ' · ' + task.network_proxy_latency_ms + 'ms' : '')\n            : '';\n""",
        'task proxy speed label',
    )

    replace_once(
        PROXY_JS,
        """                        <div class=\"teddy-proxy-sub\">공개 HTTP 프록시를 자동 수집한 뒤 HTTPS 실제 연결 검사를 통과한 후보만 사용합니다.</div>\n""",
        """                        <div class=\"teddy-proxy-sub\">공개 HTTP 프록시를 자동 수집하고 HTTPS 생존 검사 후 소량 실제 전송속도까지 측정해 빠른 후보를 우선 사용합니다.</div>\n""",
        'proxy panel speed description',
    )

    replace_once(
        PROXY_JS,
        """        const latency = Number(data && data.current_latency_ms) || 0;\n        const current = data && data.current_proxy ? data.current_proxy : '';\n""",
        """        const latency = Number(data && data.current_latency_ms) || 0;\n        const measuredSpeed = Number(data && data.current_speed_bps) || 0;\n        const speedTested = Number(data && data.speed_tested_count) || 0;\n        const current = data && data.current_proxy ? data.current_proxy : '';\n""",
        'proxy panel speed values',
    )

    replace_once(
        PROXY_JS,
        """            status.textContent = `정상 ${healthy}개 / 후보 ${candidates}개 · 마지막 갱신 ${lastRefresh} · 자동 교체 ${switches}회`;\n""",
        """            status.textContent = `정상 ${healthy}개 / 후보 ${candidates}개 · 속도 측정 ${speedTested}개 · 마지막 갱신 ${lastRefresh} · 자동 교체 ${switches}회`;\n""",
        'proxy panel tested count',
    )

    replace_once(
        PROXY_JS,
        """        currentEl.textContent = current\n            ? `현재 ${current}${latency ? ` · ${latency}ms` : ''}${exitIp ? ` · 출구 ${exitIp}` : ''}${source ? ` · ${source}` : ''}`\n            : '현재 선택된 프록시 없음';\n""",
        """        const speedText = measuredSpeed ? ` · 검사 ${(measuredSpeed / 1024 / 1024).toFixed(2)} MB/s` : '';\n        currentEl.textContent = current\n            ? `현재 ${current}${speedText}${latency ? ` · ${latency}ms` : ''}${exitIp ? ` · 출구 ${exitIp}` : ''}${source ? ` · ${source}` : ''}`\n            : '현재 선택된 프록시 없음';\n""",
        'proxy panel current speed',
    )

    print('proxy real-speed ranking runtime patch: OK')


if __name__ == '__main__':
    main()
