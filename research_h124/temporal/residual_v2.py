"""Residual checks across every valid segment, never joining time across gaps."""
import math
import numpy as np
from scipy.special import ndtri
from .h4 import history,residual,ks_uniform

def segmented_acf(u,lengths,lags=12):
    z=ndtri(u);z-=z.mean();denom=float(np.dot(z,z));values=[]
    if not denom:return None
    starts=np.r_[0,np.cumsum(lengths)]
    for lag in range(1,lags+1):
        numerator=0.;pairs=0
        for lo,hi in zip(starts[:-1],starts[1:]):
            if hi-lo>lag:numerator+=float(np.dot(z[lo:hi-lag],z[lo+lag:hi]));pairs+=hi-lo-lag
        if pairs:values.append(abs(numerator/denom*len(z)/pairs))
    return max(values) if values else None

def bootstrap_segments(y,base,g,indices,eta,half,dt,repetitions=49,dispersion=None):
    from .h4_nb import pit
    if not repetitions:return {'status':'not_run'}
    segments=np.split(indices,np.where(np.diff(indices)>1)[0]+1);lengths=[len(s) for s in segments]
    rng=np.random.default_rng(42);decay=math.exp(-math.log(2)*dt/half);total=len(indices)
    draws=np.empty((repetitions,total),dtype=np.int64);offset=0
    for segment in segments:
        h=np.full(repetitions,g[segment[0]])
        for j in segment:
            mu=base[j]+eta*h
            values=rng.poisson(mu) if dispersion is None else rng.negative_binomial(dispersion,dispersion/(dispersion+mu))
            draws[:,offset]=values;h=decay*h+(1-decay)*values;offset+=1
    mu=base[indices]+eta*g[indices]
    u=residual(y[indices],mu,rng) if dispersion is None else pit(y[indices],mu,dispersion,rng)
    observed_ks=ks_uniform(u);observed_acf=segmented_acf(u,lengths);ks=[];acf=[]
    for simulation in draws:
        means=[];offset=0
        for segment in segments:
            n=len(segment);local=simulation[offset:offset+n]
            means.extend(base[segment]+eta*history(local,half,dt)+eta*g[segment[0]]*decay**np.arange(n));offset+=n
        means=np.asarray(means);u=residual(simulation,means,rng) if dispersion is None else pit(simulation,means,dispersion,rng)
        ks.append(ks_uniform(u));acf.append(segmented_acf(u,lengths))
    return {'status':'completed_all_valid_segments','replications':repetitions,'bins':total,'segments':len(segments),'fraction_test_bins_checked':1.,
      'KS':observed_ks,'max_abs_within_segment_ACF':observed_acf,'bootstrap_KS_p':(1+sum(k>=observed_ks for k in ks))/(repetitions+1),
      'bootstrap_acf_p':(1+sum(k is not None and k>=observed_acf for k in acf))/(repetitions+1) if observed_acf is not None else None,
      'scope':'All valid test segments; each conditions on observed pre-segment history; no ACF pairs across gaps; fixed parameters/market path, not causal identification'}
