"""Read-only validation of model output; standard library only."""
import argparse,csv,json,math
from pathlib import Path

def require(condition,message):
    if not condition:raise ValueError(message)
def load(path):
    def reject(value):raise ValueError(f'Non-finite JSON constant: {value} in {path}')
    return json.loads(path.read_text(encoding='utf8'),parse_constant=reject)
def read(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def main():
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path);args=parser.parse_args();root=args.run
    m=load(root/'manifest.json');require(m['all_executed'],'At least one model failed')
    checks=[]
    for item in m['models']:
        rq=item['rq'];folder=root/f'rq{rq}';s=load(folder/'summary.json')
        require(item['execution']=='completed',f'RQ{rq} did not complete')
        if rq==1:
            for r in read(folder/'stress_curve.csv'):
                require(0<=int(r['newly_eligible_wallets'])<=int(r['eligible_wallets']), 'Invalid wallet counts')
                require(0<=float(r['eligible_risk_debt_usd'])<=float(r['total_risk_debt_usd'])+1e-5,'Eligible debt exceeds total')
        if rq==2:
            for r in read(folder/'concentration.csv'):
                for key in ['hhi','gini','top1','top10']:
                    if r[key]:require(-1e-12<=float(r[key])<=1+1e-12,f'Invalid concentration {key}')
        if rq==3:
            pairs=read(folder/'matched_pairs.csv');require(len({r['control'] for r in pairs})==len(pairs),'Controls reused')
            require(len({r['treated'] for r in pairs})==len(pairs),'Treated reused')
            require(s['cutoff_utc']<s['outcome_end_utc'],'Invalid outcome horizon')
        if rq==4:
            require(s['poisson']['converged'] and s['hawkes']['converged'],'Estimator did not converge')
            require(0<=s['hawkes']['branching_ratio']<1,'Unstable Hawkes fit')
        if rq in [5,6,7]:require(s['status']=='exploratory','Insufficient data cannot be labeled research-ready')
        if rq in [6,7]:
            path=folder/('cascade_scenarios.csv' if rq==6 else 'policy_grid.csv')
            for r in read(path):
                for key in ['repaid_usd','seized_usd','terminal_collateral_shortfall_usd','max_cumulative_price_impact']:
                    require(math.isfinite(float(r[key])) and float(r[key])>=0,f'Invalid simulation result: {key}')
                require(float(r['max_cumulative_price_impact'])<1,'Nonpositive price factor')
                if rq==7 and r['reached_round_limit']=='True':
                    require(r.get('pareto_evaluable')=='False' and not r.get('pareto_nondominated'),'Truncated policy incorrectly classified on Pareto frontier')
        checks.append({'rq':rq,'outputs_validated':True,'readiness':s['status'],'warnings':s.get('warnings',[])})
    print(json.dumps({'passed':True,'checks':checks},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
