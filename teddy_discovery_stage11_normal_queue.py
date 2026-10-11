#!/usr/bin/env python3
"""Feed new holdings to the existing Stage12 queue, then run one normal batch.

The existing inventory, title locks, state machine and no-overwrite publisher
remain the only owners. Existing failed/historical rows are never reinitialized.
"""
import argparse
import os
from pathlib import Path
import sys

import teddy_discovery_stage12_bulk_runner as bulk
from teddy_discovery_organizer import load_db_state
from teddy_discovery_stage12_inventory import Stage12HoldingsInventory,build_subtitle_ssh_reader
from teddy_discovery_stage12_rollout import Stage12RolloutStateStore


def seed_new_holdings(store, *, loader=load_db_state, subtitle_reader=None, limit=4):
    known={s.dvd_id for s in store.list_states()}
    state=loader(bulk.DISCOVERY_DB)
    rows=state.get('holdings')
    if type(rows) is not list: raise bulk.Stage12BulkRunnerError('holdings loader returned invalid state')
    # Admit only current canonical rows. The existing inventory checks source,
    # Korean siblings and ambiguity before creating a normal PENDING decision.
    rows=sorted((r for r in rows if r.get('dvd_id') not in known
        and r.get('dvd_id') and r.get('storage_root')=='jav' and r.get('present')==1
        and r.get('parse_status')=='MATCHED'),key=lambda r:r['dvd_id'])[:limit]
    if not rows: return {'new_holdings':0}
    if subtitle_reader is None: subtitle_reader=build_subtitle_ssh_reader(**bulk.NAS)
    report=Stage12HoldingsInventory(db_path=bulk.DISCOVERY_DB,subtitle_reader=subtitle_reader,
        holdings_loader=lambda _:dict(state,holdings=rows)).run()
    store.initialize_from_inventory(report)
    return {'new_holdings':len(report.records),'eligible':report.eligible_count,
            'existing_ko':report.existing_ko_count,'unresolved':report.unresolved_count}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-head',required=True)
    args=parser.parse_args()
    bulk.require_production_interpreter(); bulk.check_repo(args.expected_head)
    # Deployment-owned authorization. There is no per-title user confirmation.
    os.environ[bulk.AUTH_ENV]=bulk.AUTH_VALUE
    with bulk.RunnerLock(bulk.LOCK_PATH):
        store=Stage12RolloutStateStore(bulk.ROLLOUT_DB)
        if bulk.active_rollout_ids(store):
            bulk.emit('NORMAL_QUEUE','FAILED_ACTIVE_STATE'); return 1
        bulk.emit('NORMAL_QUEUE_SEED',seed_new_holdings(store))
    return bulk.run_live(expected_head=args.expected_head,batch_size=1,max_titles=1)


if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as error:
        bulk.emit('NORMAL_QUEUE','FAILED'); bulk.emit('ERROR',type(error).__name__+': '+str(error))
        raise SystemExit(1)
