"""Bounded local coordinator; resumes data and never silently passes a gate."""
import argparse,time,traceback
from .v2_common import *

def run(minutes=360):
    from .report_v2 import run as report
    from .h4_data import build,upgrades
    from . import h4_data
    from .h4_extended import run as estimate
    from .cascade import run as cascade
    from .h4_extended_nb import run as estimate_nb
    from .h1_attribution import run as attribution
    from .quarter_context import run as context
    from .audit_v2 import audit
    deadline=time.monotonic()+minutes*60;attempted_model=None;attempted_nb=None;attempted_util=None;last_audit=None;last_quarters=None
    while time.monotonic()<deadline:
        stages={}
        quarter_key=tuple(r['quarter'] for r in load(H1_DATA/'h1/quarter_plan.json',[]) if load(H1_DATA/'h1'/r['quarter']/'scope.json',{}).get('full_snapshot_complete'))
        if quarter_key!=last_quarters:
            try:
                context();attribution();last_quarters=quarter_key
                stages['quarterly_context']='refreshed';stages['h1_attribution']='refreshed'
            except Exception as exc:stages['quarterly_context']={'status':'error','kind':type(exc).__name__,'message':str(exc)[:200]}
        else:stages['quarterly_context']='cached';stages['h1_attribution']='cached'
        if load(DATA/'header_progress.json',{}).get('complete'):
            try:
                readiness=load(OUT/'h4_data_readiness.json',{})
                if readiness.get('status')!='completed_scoped' or readiness.get('code_sha256')!=digest(h4_data.__file__):upgrades();build()
                panel_hash=load(OUT/'h4_data_readiness.json',{}).get('panel_sha256')
                if panel_hash and load(OUT/'h4/summary.json',{}).get('panel_sha256')!=panel_hash and attempted_model!=panel_hash:
                    attempted_model=panel_hash;estimate()
                stages['h4']='completed' if load(OUT/'h4/summary.json',{}).get('status')=='completed_exploratory' else 'waiting_or_failed'
                if stages['h4']=='completed' and load(OUT/'h4_nb/summary.json',{}).get('panel_sha256')!=panel_hash and attempted_nb!=panel_hash:
                    attempted_nb=panel_hash;estimate_nb()
            except Exception as exc:
                stages['h4']={'status':'error','kind':getattr(exc,'kind',type(exc).__name__),'message':str(exc)[:300]};print(traceback.format_exc(),flush=True)
        else:stages['h4']='waiting_for_all_oracle_headers'
        utility=load(OUT/'h4_util_data_readiness.json',{})
        if utility.get('status')=='completed_scoped' and attempted_util!=utility['panel_sha256']:
            try:
                attempted_util=utility['panel_sha256']
                if load(OUT/'h4_util/summary.json',{}).get('panel_sha256')!=attempted_util:
                    estimate(panel_filename='h4_util_panel_5min.npz',readiness_filename='h4_util_data_readiness.json',output_subdir='h4_util')
                if load(OUT/'h4_util_nb/summary.json',{}).get('panel_sha256')!=attempted_util:
                    estimate_nb(panel_filename='h4_util_panel_5min.npz',primary_subdir='h4_util',output_subdir='h4_util_nb')
                stages['h4_utilization']='completed'
            except Exception as exc:
                stages['h4_utilization']={'status':'error','kind':type(exc).__name__,'message':str(exc)[:300]};print(traceback.format_exc(),flush=True)
        try:cascade();stages['cascade']='refreshed'
        except Exception as exc:stages['cascade']={'status':'error','kind':getattr(exc,'kind',type(exc).__name__),'message':str(exc)[:300]};print(traceback.format_exc(),flush=True)
        save(OUT/'worker_status.json',{'updated_utc':now(),'stages':stages})
        audit_key=(load(DATA/'header_progress.json',{}).get('complete'),load(OUT/'h4/summary.json',{}).get('status'),len(quarter_key))
        if audit_key!=last_audit:
            try:audit(network=bool(audit_key[0]));last_audit=audit_key
            except Exception as exc:print('AUDIT ERROR',type(exc).__name__,flush=True)
        report()
        print(now(),stages,flush=True);time.sleep(30)
    report()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--minutes',type=float,default=360);a=p.parse_args();run(a.minutes)
