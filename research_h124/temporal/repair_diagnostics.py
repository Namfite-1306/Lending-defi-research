"""Explain old explosive NB predictions and compare exactly the same bins."""
import numpy as np
from .repair_common import *
from .h4_extended import feature_groups
from .h4 import history
from .repair_h3 import predict,masks,LONG_HALF,DT
from defi_models.core import iso

def run():
    with np.load(DATA/'h4_prefix_panel_5min.npz') as a:t=a['t'];y=a['y'];features=a['X'];names=a['names'].tolist();common=a['old_valid']&np.isfinite(features).all(axis=1)
    train,_,test=masks(t,common);raw=features[:,feature_groups(names)['oracle_gas']]
    old=load(V2_OUT/'h4_prefix/fitted_models.json')['oracle_gas_hawkes'];X=np.c_[np.ones(len(y)),np.nan_to_num((raw-np.array(old['center']))/np.array(old['scale']))]
    par=np.array(load(V2_OUT/'h4_prefix_nb/summary.json')['models']['extended_nb_no_excitation']);old_mu=np.exp(X@par[:X.shape[1]])*DT
    summary=load(OUT/'h3/summary.json');selected=summary['selected_by_validation'];new=load(OUT/'h3/fitted_models.json')[selected]
    adaptive=new['architecture']=='softplus_adaptive';slow=history(y,LONG_HALF,DT)
    raw_new=np.c_[raw,np.log1p(slow)] if adaptive else raw
    Xn=np.c_[np.ones(len(y)),np.nan_to_num((raw_new-np.array(new['center']))/np.array(new['scale']))]
    g=history(y,new['half'],DT) if new['excitation'] else np.zeros(len(y));new_mu,_=predict(Xn,g,np.array(new['parameters']),new['kind'],new['family'],new['excitation'])
    j=[names.index(n) for n in ['ETH_oracle_down_5m','ETH_oracle_down_60m','BTC_oracle_down_5m','BTC_oracle_down_60m']]
    rows=[]
    for i in np.flatnonzero(test)[np.argsort(old_mu[test])[-20:][::-1]]:
        count=int((features[train][:,j]>=features[i,j]).all(axis=1).sum())
        rows.append({'bin_start_utc':iso(int(t[i])),'observed':int(y[i]),'old_NB_without_excitation_expected':float(old_mu[i]),'new_selected_expected':float(new_mu[i]),
          'train_bins_all_four_returns_at_least_as_extreme':count,'all_four_within_individual_train_ranges':all(features[i,k]>=features[train,k].min() and features[i,k]<=features[train,k].max() for k in j)})
    write(OUT/'h3/rare_joint_states.csv',rows)
    result={'updated_utc':now(),'selected':selected,'largest_old_prediction':rows[0],
      'old_top10_prediction_share':float(np.sort(old_mu[test])[-10:].sum()/old_mu[test].sum()),
      'meaning':'Zero matching upper-orthant training bins flags joint rarity, not a complete density/OOD or causal proof'}
    save(OUT/'h3/explosive_bin_diagnosis.json',result);return result

if __name__=='__main__':print(run())
