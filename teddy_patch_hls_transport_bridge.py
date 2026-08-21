from pathlib import Path


BOOTSTRAP = Path('teddy_bootstrap.py')


def main():
    text = BOOTSTRAP.read_text(encoding='utf-8')

    old_signature = 'def _fetch_segment_with_network_recovery(task_id, seg_url, headers):'
    new_signature = (
        "def _fetch_segment_with_network_recovery(task_id, seg_url, headers, "
        "transport_mode='per-worker', worker_count=None):"
    )
    signature_count = text.count(old_signature)
    if signature_count != 1:
        raise SystemExit(
            f'HLS transport bridge: expected one recovery-wrapper signature, found {signature_count}'
        )
    text = text.replace(old_signature, new_signature, 1)

    old_call = 'return _original_fetch_segment(task_id, seg_url, headers)'
    new_call = (
        'return _original_fetch_segment(task_id, seg_url, headers, '
        'transport_mode=transport_mode, worker_count=worker_count)'
    )
    call_count = text.count(old_call)
    if call_count != 3:
        raise SystemExit(
            f'HLS transport bridge: expected three wrapped segment calls, found {call_count}'
        )
    text = text.replace(old_call, new_call)

    BOOTSTRAP.write_text(text, encoding='utf-8')
    print('HLS recovery wrapper transport bridge: OK')


if __name__ == '__main__':
    main()
