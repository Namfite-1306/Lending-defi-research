"""Posthoc forecast diagnostics; execution success is not model acceptance."""
from .v2_common import *

def assess(row,residual):
    observed=float(row['test_events']);expected=float(row['expected_test_events'])
    ratio=expected/observed if observed else None
    ks=residual.get('bootstrap_KS_p');acf=residual.get('bootstrap_acf_p')
    residual_available=ks is not None and acf is not None
    residual_pass=min(ks,acf)>=.05 if residual_available else None
    # A descriptive gross-error screen, not a preregistered hypothesis test.
    gross_error=ratio is None or not .5<=ratio<=2
    return {'model':row['model'],'observed_events':observed,'expected_events':expected,'expected_observed_ratio':ratio,
      'residual_KS_p':ks,'residual_ACF_p':acf,'residual_pass_5pct':residual_pass,'gross_count_error_screen':gross_error,
      'deployment_ready':False,'status':'requires_recalibration' if gross_error or residual_pass is False else 'requires_residual_diagnostics' if not residual_available else 'requires_independent_validation',
      'note':'0.5–2 ratio screen and 5% residual screen are posthoc diagnostics; no model gains deployment approval from these alone'}

def run():
    rows=[]
    for folder in ['h4','h4_nb','h4_util','h4_util_nb','h4_prefix','h4_prefix_nb']:
        f=OUT/folder/'model_comparison.csv'
        if not f.exists():continue
        residuals=load(OUT/folder/'residuals.json',{})
        rows += [dict(variant=folder,**assess(r,residuals.get(r['model'],{}))) for r in read(f)]
    write(OUT/'model_quality.csv',rows)
    result={'updated_utc':now(),'models':rows,'scope':'Posthoc descriptive diagnostics, not automatic statistical or deployment certification'}
    save(OUT/'model_quality.json',result);return result
