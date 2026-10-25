"""Frozen-validation hyperparameters; rolling refits only on earlier dates."""
import numpy as np
from .next_common import *
from .hurdle_model import fit,predictions,score
from .h4_extended import feature_groups
from defi_models.core import stamp,iso

def run():
    out=OUT/'h3';models=load(out/'fitted_models.json',{});result=[]
    with np.load(DATA/'h4_prefix_panel_5min.npz') as a:
        keep=a['t']<PRIMARY_END;t=a['t'][keep];y=a['y'][keep];f=a['X'][keep];names=a['names'].tolist();common=a['old_valid'][keep]&np.isfinite(f).all(axis=1)
    with np.load(DATA_NEXT/'activity_panel.npz') as a:flows=a['X'];past=a['history']
    market=f[:,feature_groups(names)['oracle_gas']]
    raw={'constant':np.empty((len(y),0)),'market':market,'activity':np.c_[market,flows],'activity_history':np.c_[market,flows,past]}
    for name,model in models.items():
        X=np.c_[np.ones(len(y)),np.nan_to_num((raw[name]-np.array(model['center']))/np.array(model['scale']))]
        for lo,hi in [('2025-07-01','2025-10-01'),('2025-10-01','2026-01-01'),('2026-01-01','2026-04-01')]:
            lower=stamp(lo+'T00:00:00Z');upper=stamp(hi+'T00:00:00Z');tr=(t<lower)&common&(t>=t[0]+7*86400);te=(t>=lower)&(t<upper)&common
            params=fit(X,y,tr,model['ridge']);pr=predictions(X[te],params)
            result.append({'model':name,'start':lo,'end_exclusive':hi,'status':'scored_revised_primary_scope','train_end_exclusive':lo,'test_bins':int(te.sum()),'test_events':int(y[te].sum()),
              'test_loglik':float(score(y[te],pr).sum()),'expected_observed_ratio':float(pr[-1].sum()/y[te].sum()),'test_MAE':float(abs(pr[-1]-y[te]).mean())})
        write(out/'rolling_quarter_scores.csv',result);print('ROLLING',name,flush=True)
    return result

if __name__=='__main__':run()
