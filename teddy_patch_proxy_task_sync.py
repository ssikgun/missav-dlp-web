from pathlib import Path


POOL = Path('teddy_proxy_pool.py')


def replace_once(old, new, label):
    text = POOL.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one patch anchor, found {count}')
    POOL.write_text(text.replace(old, new, 1), encoding='utf-8')


def main():
    replace_once(
        """    _save(core)\n    print(\n        f\"[Proxy] 실패 프록시 제외 -> 다음 후보: {old.get('proxy', '')} -> {new.get('proxy', '')} \"\n        f\"({new.get('latency_ms', 0)}ms)\",\n""",
        """    active_statuses = {'다운로드 중', '일시정지 요청 중', '대기 중'}\n    updated_tasks = 0\n    for task in core.tasks.values():\n        if task.get('network_mode') != 'proxy' or task.get('status') not in active_statuses:\n            continue\n        task['network_proxy'] = new.get('proxy', '')\n        task['network_proxy_latency_ms'] = int(new.get('latency_ms') or 0)\n        task['network_proxy_speed_bps'] = int(new.get('speed_bps') or 0)\n        task['network_proxy_learned_speed_bps'] = int(new.get('learned_speed_bps') or 0)\n        task['network_proxy_exit_ip'] = new.get('exit_ip', '')\n        updated_tasks += 1\n    if updated_tasks:\n        core.save_tasks()\n    _save(core)\n    print(\n        f\"[Proxy] 실패 프록시 제외 -> 다음 후보: {old.get('proxy', '')} -> {new.get('proxy', '')} \"\n        f\"({new.get('latency_ms', 0)}ms, 활성 작업 {updated_tasks}개 동기화)\",\n""",
        'sync active proxy task metadata on rotation',
    )
    print('proxy active-task metadata sync runtime patch: OK')


if __name__ == '__main__':
    main()
