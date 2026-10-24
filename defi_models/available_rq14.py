"""Exploratory RQ1/RQ4 results from existing, explicitly limited observations.

Does not create recovery audits, modify raw SQLite, or certify full-market data.
"""
import argparse
import json
import math
import sqlite3
import subprocess
from datetime import datetime,timezone
from decimal import Decimal as D
from pathlib import Path

import numpy as np

from defi_data.recovery import merge_ranges
from defi_data.rpc import Rpc
from defi_live.models import SnapshotData
from .__main__ import config
from .analyses import rq1
from .core import ROOT,DEFAULT_RUN,Portfolio,rows,require,sha,stamp,iso,write_csv,write_json
from .statistics import hawkes_fit


def sample_portfolio(run,cfg):
    folder=Path(run)/'processed'
    names=['positions_point_in_time_sample.csv','position_checks.csv','historical_reserve_config_sample.csv','position_scope.json']
    paths=[folder/n for n in names]
    scope=json.loads(paths[3].read_text(encoding='utf8'));block=int(scope['block'])
    positions=list(rows(paths[0]));checks=list(rows(paths[1]));metadata=list(rows(paths[2]))
    require(positions and checks and metadata,'Sample positions/checks/reserve metadata are required')
    require(all(r['passed']=='True' and int(r['block_number'])==block and D(r['max_relative_error']).is_finite() and D(r['max_relative_error'])<=D('.0001') for r in checks),'Sample validation failed or blocks differ')
    require(len({r['account'] for r in checks})==len(checks),'Duplicate sample account checks')
    active={r['account']:r for r in checks if D(r['reported_debt_usd'])>0}
    meta={r['token_address']:r for r in metadata}
    require(all(int(r['block_number'])==block for r in metadata),'Reserve metadata must use sample block')
    selected=[];seen=set()
    for row in positions:
        require(row['validation_passed']=='True' and int(row['block_number'])==block,'Unvalidated or mixed-block position')
        key=(row['account'],row['token_address'])
        require(key not in seen,'Duplicate sample wallet/token');seen.add(key)
        if row['account'] not in active:continue
        m=meta[row['token_address']];decimals=int(m['decimals'])
        require(0<=decimals<=36 and row['symbol']==m['symbol'],'Invalid token metadata')
        require(D(row['price_usd'])==D(m['price']),'Position price differs from same-block reserve metadata')
        selected.append(dict(row,block=block,token=row['token_address'],effective_lt=row['effective_liquidation_threshold'],decimals=decimals,
            repayable_debt_usd=str(D(row['repayable_debt_raw'])/10**decimals*D(row['price_usd']))))
    require(selected,'No positive-debt validated sample wallets')
    p=Portfolio(selected,cfg);require(set(p.accounts)==set(active),'Sample position/check account sets differ')
    actual,_=p.stress()
    for i,a in enumerate(p.accounts):
        reported=D(active[a]['hf_reported']);debt=D(active[a]['reported_debt_usd'])
        require(abs(D(str(actual[i]))-reported)/max(abs(reported),D('1e-12'))<=D('.0001'),'Sample model HF does not reconcile')
        require(abs(D(str(p.d[i].sum()))-debt)/max(debt,D(1))<=D('.0001'),'Sample model debt does not reconcile')
    scope=dict(scope,full_universe=False,full_snapshot_complete=False,active_debt_wallets=len(active),candidate_wallets=len(checks),
        selection='existing pre-snapshot observed borrower sample; not all borrowers',baseline_hf_reconciled=True)
    return p,scope,paths


def prefix_events(connection,bounds,header_reader):
    """Pin a SQLite read snapshot and use only a complete leading block interval."""
    connection.execute('BEGIN')
    try:
        target_lo,target_hi=bounds['start_block'],bounds['end_block']
        intervals=merge_ranges([(max(target_lo,a),min(target_hi,b)) for a,b in connection.execute("SELECT lo,hi FROM ranges WHERE protocol='aave_v3'") if a<=target_hi and b>=target_lo])
        require(intervals and intervals[0][0]==target_lo,'No fully collected leading Aave history interval')
        lo,hi=intervals[0]
        first=connection.execute("SELECT min(stamp) FROM events WHERE protocol='aave_v3' AND block BETWEEN ? AND ?",(lo,hi)).fetchone()[0]
        require(first is not None,'No observed Aave events in prefix')
        header=header_reader(hi)
        require(isinstance(header,dict) and int(header['number'],16)==hi and header.get('hash'),'Invalid prefix boundary header')
        start=max(stamp(bounds['start_utc']),math.ceil(first/3600)*3600)
        end=min(stamp(bounds['end_exclusive_utc']),int(header['timestamp'],16)//3600*3600)
        require(end-start>240*3600,'Need more than 240 completely observed hours')
        events=[dict(timestamp_utc=iso(t),block=b,tx=tx,logidx=idx,block_hash=h) for t,b,tx,idx,h in connection.execute(
            "SELECT stamp,block,tx,idx,hash FROM events WHERE protocol='aave_v3' AND name='LiquidationCall' AND block BETWEEN ? AND ? AND stamp>=? AND stamp<? ORDER BY block,txidx,idx",(lo,hi,start,end))]
        require(len({(r['tx'],r['logidx']) for r in events})==len(events),'Duplicate liquidation keys')
        pinned_header={k:header[k] for k in ['number','hash','parentHash','timestamp'] if k in header}
        return start,end,events,{'prefix_start_block':lo,'prefix_end_block':hi,'boundary_header':pinned_header,
            'full_requested_period':False,'requested_start_utc':bounds['start_utc'],'requested_end_exclusive_utc':bounds['end_exclusive_utc'],
            'start_policy':'first full UTC hour after earliest observed Aave activity; not first liquidation',
            'end_policy':'last full UTC hour within complete leading block coverage','independent_audit_complete':False}
    finally:connection.rollback()


def fit_prefix(start,end,events,cfg,out):
    times=np.asarray(sorted((stamp(r['timestamp_utc'])-start)/3600 for r in events))
    hours=int((end-start)/3600);split=int(hours*cfg['train_fraction'])
    require(len(times)>20 and np.sum(times<split)>10 and np.sum(times>=split)>0,'Insufficient train/test liquidation events')
    best,candidates=hawkes_fit(times,hours,split,cfg['hawkes_half_lives_hours'])
    require(best is not None,'No Hawkes candidate converged')
    rate=float(np.sum(times<split)/split);test_n=int(np.sum(times>=split))
    poisson_ll=test_n*math.log(rate)-rate*(hours-split)
    counts,_=np.histogram(times,bins=np.arange(hours+1))
    write_csv(out/'observed_liquidations.csv',events)
    write_csv(out/'hourly_counts.csv',[dict(hour_utc=iso(start+i*3600),liquidation_events=int(n),sample='train' if i<split else 'test') for i,n in enumerate(counts)])
    write_csv(out/'hawkes_candidates.csv',candidates)
    return {'status':'exploratory','protocol':'aave_v3','method':'Univariate grouped-timestamp Hawkes vs constant Poisson; no price controls',
        'observation_start_utc':iso(start),'observation_end_exclusive_utc':iso(end),'train_end_utc':iso(start+split*3600),
        'events':len(events),'hours':hours,'hawkes':best,'poisson':{'converged':True,'kind':'constant rate MLE','rate_per_hour':rate,'test_loglik':poisson_ll,'price_controls_included':False},
        'hawkes_minus_constant_poisson_test_loglik':float(best['test_loglik']-poisson_ll),
        'warnings':['Partial-period extraction has not completed independent audits','Only contiguous complete block coverage is used; gaps are never zero-filled',
            'No ETH/BTC price-controlled Poisson here; full RQ4 pipeline remains required','Clustering and branching ratio are not causal self-excitation evidence']}


def run(sample_run,data_run,cfg,out,header_reader,models=None):
    selected=list(dict.fromkeys([1,4] if models is None else models))
    require(selected and set(selected).issubset({1,4}),'Select RQ1 and/or RQ4')
    require(cfg['protocol']=='aave_v3','Available-data runner only supports aave_v3')
    require(not out.exists(),f'Output already exists: {out}')
    out.mkdir(parents=True);failures=[];results=[];inputs=[]
    for rq in selected:
        dest=out/f'rq{rq}';dest.mkdir()
        try:
            if rq==1:
                p,scope,paths=sample_portfolio(sample_run,cfg);inputs+=paths
                result=rq1(SnapshotData(p,scope),dest,cfg)
                result['status']='exploratory';result.setdefault('warnings',[]).insert(0,'Validated observed borrower sample only; no full-universe conclusion')
                result['sample_wallets']=len(p.accounts)
                result['baseline_total_risk_debt_usd']=float(p.d.sum())
            else:
                bounds_path=data_run/'block_range.json';inputs.append(bounds_path)
                bounds=json.loads(bounds_path.read_text(encoding='utf8'))
                c=sqlite3.connect((data_run/'history.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
                try:start,end,events,scope=prefix_events(c,bounds,header_reader)
                finally:c.close()
                write_json(dest/'coverage_scope.json',scope)
                result=fit_prefix(start,end,events,cfg,dest);result.update(scope)
            write_json(dest/'summary.json',result)
            results.append({'rq':rq,'execution':'completed','readiness':'exploratory'})
        except (ValueError,OSError,KeyError,TypeError,ArithmeticError,sqlite3.Error) as exc:
            failures.append({'rq':rq,'error':str(exc)})
            write_json(dest/'error.json',{'error':str(exc)});results.append({'rq':rq,'execution':'failed','readiness':'unavailable'})
    revision=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
    manifest={'created_utc':datetime.now(timezone.utc).isoformat(),'mode':'exploratory_available_data','code_revision':revision,
        'code_dirty':bool(subprocess.run(['git','status','--porcelain'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()),
        'code_files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in [Path(__file__),ROOT/'defi_models/core.py',ROOT/'defi_models/analyses.py',ROOT/'defi_models/statistics.py',ROOT/'defi_live/models.py']],
        'config':cfg,'models':results,'all_executed':not failures,'errors':failures,'full_research_ready':False,
        'source_files':[{'path':str(p),'sha256':sha(p)} for p in inputs]}
    if 4 in selected:
        manifest['raw_database']={'path':str(data_run/'history.sqlite'),'sha256':None,'note':'Consumed event rows and prefix boundary are saved in rq4/; independent audits remain required'}
    write_json(out/'manifest.json',manifest)
    report=['# '+' và '.join(f'RQ{i}' for i in selected)+' từ dữ liệu hiện có','','Trạng thái: exploratory. Chưa phải kết quả toàn kỳ hoặc toàn bộ thị trường.',
        f'Commit gốc: `{revision}`; các thay đổi local được ghi SHA-256 trong manifest.','']
    if (out/'rq1/summary.json').exists():
        s=json.loads((out/'rq1/summary.json').read_text(encoding='utf8'))
        report += [f"RQ1: {s['sample_wallets']} ví có dư nợ, snapshot block {s['snapshot']['block']}; HF nền đã đối chiếu. Tổng risk debt mẫu: {s['baseline_total_risk_debt_usd']:,.2f} USD.",'',
            '| Kịch bản | Shock | Ví HF < 1 | Dư nợ đủ điều kiện (USD) |','|---|---:|---:|---:|']
        for r in rows(out/'rq1/stress_curve.csv'):
            shock=float(r['shock_fraction'])
            if any(abs(shock-x)<1e-8 for x in [0,.1,.2,.3,.4,.5,.6]):
                report.append(f"| {r['scenario']} | {shock:.0%} | {r['eligible_wallets']} | {float(r['eligible_risk_debt_usd']):,.2f} |")
        report += ['','Dư nợ có HF < 1 là eligible debt; không phải lượng thanh lý thực thi hoặc nợ xấu. Mẫu không đại diện toàn bộ người vay.','']
    if (out/'rq4/summary.json').exists():
        s=json.loads((out/'rq4/summary.json').read_text(encoding='utf8'));h=s['hawkes']
        report += [f"RQ4: {s['events']} liquidation, {s['hours']} giờ liên tục, từ {s['observation_start_utc']} đến trước {s['observation_end_exclusive_utc']}.",
            f"Train kết thúc: {s['train_end_utc']}. Hawkes half-life: {h['half_life_hours']:.4g} giờ; branching ratio: {h['branching_ratio']:.4f}.",
            f"Test log-likelihood Hawkes: {h['test_loglik']:.4f}; Poisson hằng: {s['poisson']['test_loglik']:.4f}.",'',
            'Chưa có ETH/BTC price controls và chưa hoàn thành audit độc lập. Không suy ra tự kích thích nhân quả từ branching ratio.',
            'Các khoảng chưa tải không được đưa vào panel dưới dạng 0; sự kiện cùng timestamp được giữ nguyên multiplicity.','']
    if failures:report += ['Các bước lỗi:',*['- RQ'+str(r['rq'])+': '+r['error'] for r in failures]]
    report += ['','Xem manifest.json, summary.json và các CSV để kiểm tra nguồn, phạm vi và kết quả.']
    (out/'RUN_REPORT.md').write_text('\n'.join(report),encoding='utf8')
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample-run',type=Path,default=ROOT/'data/runs/expansion_20260930')
    parser.add_argument('--data-run',type=Path,default=DEFAULT_RUN);parser.add_argument('--config',type=Path)
    parser.add_argument('--models',nargs='+',type=int,choices=[1,4],default=[1,4],help='Run only selected available-data models; RQ1 alone needs no RPC/history database')
    parser.add_argument('--out',type=Path,default=ROOT/'results'/('rq14_available_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')))
    a=parser.parse_args();rpc=Rpc(ROOT/'data/rpc_cache',timeout=20,retry_attempts=2)
    def boundary(n):
        require(int(rpc.one('eth_chainId',[],cache=False),16)==1,'Expected Ethereum mainnet boundary header')
        return rpc.one('eth_getBlockByNumber',[hex(n),False],cache=False)
    result=run(a.sample_run,a.data_run,config(a.config),a.out,boundary,models=a.models)
    print(json.dumps({'output':str(a.out),'models':result['models'],'errors':result['errors'],'full_research_ready':False},ensure_ascii=True,indent=2))
    return 0 if result['all_executed'] else 1


if __name__=='__main__':raise SystemExit(main())
