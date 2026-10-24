"""Run verified-prefix sensitivity without promoting it to the full target."""
import traceback
from .v2_common import *

def run():
    stages={}
    from .h4_data import materialize
    from .h4_extended import run as fit
    from .h4_extended_nb import run as nb
    from .cascade import run as cascade
    from .audit_v2 import audit
    from .report_v2 import run as report
    jobs=[('prefix_panel',lambda:materialize(prefix=True)),
      ('prefix_h4',lambda:fit(panel_filename='h4_prefix_panel_5min.npz',readiness_filename='h4_prefix_data_readiness.json',output_subdir='h4_prefix')),
      ('prefix_nb',lambda:nb(panel_filename='h4_prefix_panel_5min.npz',primary_subdir='h4_prefix',output_subdir='h4_prefix_nb')),
      ('cascade',cascade),('audit',audit)]
    with worker_lock(DATA/'offline.lock'):
        for name,job in jobs:
            stages[name]={'status':'running'};save(OUT/'offline_status.json',{'updated_utc':now(),'stages':stages})
            try:
                job();stages[name]={'status':'completed'}
            except Exception as exc:
                traceback.print_exc();stages[name]={'status':'error','error':str(exc)}
            save(OUT/'offline_status.json',{'updated_utc':now(),'stages':stages});report()
    return stages

if __name__=='__main__':print(run(),flush=True)
