import argparse,json,sys,time,platform,traceback,math
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import scipy
from .core import DEFAULT_RUN,DEFAULTS,ROOT,Data,require,write_json,sha
from .analyses import rq1,rq2,rq3,rq4,rq5
from .simulation import rq6,rq7
from . import __version__

MODELS={1:rq1,2:rq2,3:rq3,4:rq4,5:rq5,6:rq6,7:rq7}

def config(path):
    cfg=dict(DEFAULTS)
    if path:
        def reject(value):raise ValueError(f'Non-finite config value: {value}')
        supplied=json.loads(Path(path).read_text(encoding='utf-8-sig'),parse_constant=reject)
        require(isinstance(supplied,dict),'Config must be a JSON object')
        unknown=set(supplied)-set(cfg)-{'dex_fee_fraction'};require(not unknown,f'Unknown config keys: {sorted(unknown)}');cfg.update(supplied)
    for k,v in cfg.items():
        expected=DEFAULTS.get(k,.003)
        if isinstance(expected,(int,float)):
            require(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v),f'Invalid numeric config: {k}')
        if isinstance(expected,str):require(isinstance(v,str),f'Expected string config: {k}')
        if isinstance(expected,list):
            require(isinstance(v,list) and v,f'Expected nonempty list: {k}')
            if isinstance(expected[0],str):require(all(isinstance(x,str) for x in v),f'Expected strings: {k}')
            else:require(all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in v),f'Invalid numeric list: {k}')
    for k in ['max_rounds','seed','bootstrap_repetitions','recursive_window_hours']:require(isinstance(cfg[k],int),f'{k} must be an integer')
    require(not Path(cfg['snapshot']).is_absolute() and '..' not in Path(cfg['snapshot']).parts,'snapshot must stay inside data-run')
    require(not set(cfg['eth_symbols'])&set(cfg['btc_symbols']),'ETH/BTC factors overlap')
    require(0<cfg['shock_step']<=cfg['shock_max']<1,'Require 0 < shock_step <= shock_max < 1')
    require(cfg['shock_max']/cfg['shock_step']<=1000,'Limit static stress grid to 1000 intervals')
    require(.1<cfg['train_fraction']<.95,'train_fraction must be between .1 and .95')
    require(cfg['protocol'] in ['aave_v3','compound_v3_usdc','morpho_blue'],'Unknown protocol')
    require(cfg['recursive_label'] in ['temporal','verified'],'recursive_label must be temporal or verified')
    require(cfg['recursive_window_hours'] in [6,24,48],'Supported motif windows: 6,24,48')
    require(cfg['bootstrap_repetitions']>=20 and cfg['outcome_days']>0,'Invalid bootstrap/outcome horizon')
    require(cfg['max_rounds']>=1 and all(0<=s<1 for s in cfg['cascade_shocks']),'Invalid simulation rounds/shocks')
    require(all(h>0 for h in cfg['hawkes_half_lives_hours']),'Half-lives must be positive')
    require(cfg['hawkes_half_lives_hours'] and cfg['cascade_shocks'],'Half-life/shock lists cannot be empty')
    require(cfg['match_caliper']>0 and cfg['gas_usd']>=0 and cfg.get('dex_fee_fraction',.003)>=0,'Invalid matching/cost parameters')
    require(cfg['impact_coefficient']>=0 and 0<=cfg.get('dex_fee_fraction',.003)<1,'Invalid impact/fee')
    require(cfg['liquidity_depth_usd']>0 and 0<=cfg['sell_fraction']<=1 and 0<=cfg['impact_cap']<1 and 0<=cfg['oracle_pass_through']<=1,'Invalid liquidity/impact configuration')
    require(0<cfg['close_factor']<=1 and 0<=cfg['liquidation_bonus']<1,'Invalid close factor/bonus')
    require(all(0<x<=1 for x in cfg['policy_close_factors']) and all(0<=x<1 for x in cfg['policy_bonuses']) and all(-1<x<1 for x in cfg['policy_lt_shifts']),'Invalid policy grid')
    return cfg

def preflight(run,cfg=None,selected=None):
    selected=selected or list(MODELS)
    selected=selected or list(MODELS)
    errors=[];checks=[]
    for n,suffix in [(1,'structure'),(2,'onchain'),(3,'research')]:
        path=run/f'audit_{n}_{suffix}.json'
        if not path.exists():errors.append(f'Missing {path.name}');continue
        obj=json.loads(path.read_text(encoding='utf8'));checks.append({'audit':n,'integrity_passed':obj.get('all_integrity_passed')})
        if not obj.get('all_integrity_passed'):errors.append(f'Audit {n} integrity did not pass')
        if not set(selected).issubset(obj.get('models',range(1,8))):errors.append(f'Audit {n} does not cover selected models')
        if not set(selected).issubset(obj.get('models',range(1,8))):errors.append(f'Audit {n} does not cover selected models')
    cfg=cfg or dict(DEFAULTS);selected=selected or list(MODELS)
    needs={1:[],2:['liquidations_model_table.csv'],3:['liquidations_model_table.csv','recursive_candidates_full_history.csv' if cfg['recursive_label']=='temporal' else 'recursive_receipt_verification.csv'],4:['liquidations_model_table.csv','liquidations_hourly_full_period.csv','market_prices_hourly_full_period.csv'],5:['exposures_valued_sample.csv'],6:[],7:[]}
    try:
        data=Data(run,cfg)
        for name in sorted({n for i in selected for n in needs[i]}):data.path(name)
        if set(selected)&{1,3,6,7}:
            data.snapshot()
        if 3 in selected:
            require((run/'history.sqlite').is_file(),'Missing history.sqlite for RQ3 cutoff')
            require((run/'block_range.json').is_file(),'Missing block_range.json for RQ3 outcome horizon')
        checks.append({'required_inputs_and_hashes':True})
    except (ValueError,OSError,KeyError,TypeError) as exc:errors.append(str(exc))
    return {'passed':not errors,'checks':checks,'errors':errors,'note':'Integrity is not full-model readiness; RQ5-7 require exploratory flag'}

def main(argv=None):
    parser=argparse.ArgumentParser(description='Offline RQ1–7 research runners; see README_MODELS.md')
    parser.add_argument('model',choices=['check','all']+[f'rq{i}' for i in range(1,8)])
    parser.add_argument('--data-run',type=Path,default=DEFAULT_RUN);parser.add_argument('--config',type=Path)
    parser.add_argument('--out',type=Path);parser.add_argument('--allow-exploratory',action='store_true')
    parser.add_argument('--check-models',nargs='+',type=int,choices=range(1,8),help='Limit check to these RQs; only valid with check')
    parser.add_argument('--models',nargs='+',type=int,choices=range(1,8),help='Run a selected subset; only valid with all')
    parser.add_argument('--smoke',action='store_true',help='Small scenario grid; full historical RQ2/3/4 data still used')
    args=parser.parse_args(argv);cfg=config(args.config)
    require(args.check_models is None or args.model=='check','--check-models requires check')
    require(args.models is None or args.model=='all','--models requires all')
    selected=list(MODELS) if args.model in ('all','check') else [int(args.model[2:])]
    if args.check_models:selected=args.check_models
    if args.models:selected=list(dict.fromkeys(args.models))
    gate=preflight(args.data_run,cfg,selected)
    if args.model=='check':print(json.dumps(gate,ensure_ascii=False,indent=2));return 0 if gate['passed'] else 2
    require(gate['passed'],'Source integrity gate failed: '+ '; '.join(gate['errors']))
    if any(i>=5 for i in selected):require(args.allow_exploratory,'RQ5–7 need --allow-exploratory: sampled exposures / uncalibrated simulation. Read README_MODELS.md')
    if args.smoke:
        cfg.update(shock_step=.1,shock_max=.3,bootstrap_repetitions=30,cascade_shocks=[.2],max_rounds=3,
                   policy_close_factors=[.5],policy_bonuses=[.05],policy_lt_shifts=[0.0],hawkes_half_lives_hours=[.5,2])
    output=args.out or ROOT/'results'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    require(not output.exists(),f'Output exists: {output}. Choose a new --out; source/results are never silently overwritten')
    output.mkdir(parents=True);data=Data(args.data_run,cfg);write_json(output/'config.json',cfg)
    manifest={'started_utc':datetime.now(timezone.utc).isoformat(),'mode':'smoke' if args.smoke else 'research_run',
       'argv':sys.argv[1:] if argv is None else argv,'data_run':str(args.data_run.resolve()),'config':cfg,'preflight':gate,
       'versions':{'defi_models':__version__,'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__},'models':[]}
    manifest['code_files']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in sorted((ROOT/'defi_models').glob('*.py'))]
    failed=False
    for i in selected:
        target=output/f'rq{i}';target.mkdir();started=time.monotonic();print(f'RQ{i} starting',flush=True)
        try:
            result=MODELS[i](data,target,cfg);write_json(target/'summary.json',result)
            entry={'rq':i,'execution':'completed','readiness':result['status'],'warnings':result.get('warnings',[]),'seconds':time.monotonic()-started}
            print(f'RQ{i} completed ({result["status"]})',flush=True)
            for warning in result.get('warnings',[]):print(f'RQ{i} WARNING: {warning}',flush=True)
        except Exception as e:
            failed=True;entry={'rq':i,'execution':'failed','error':str(e),'seconds':time.monotonic()-started}
            (target/'error.txt').write_text(traceback.format_exc(),encoding='utf8');print(f'RQ{i} FAILED: {e}',flush=True)
        manifest['models'].append(entry);write_json(output/'manifest.json',manifest)
    # Freeze checksums for consumed flat files; database identity is tied to prior raw audit.
    manifest['input_files']=[dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p) if p.suffix!='.sqlite' else None,
       provenance='raw logical digest in audit_1_structure.json' if p.suffix=='.sqlite' else 'consumed file hash') for p in sorted(data.used)]
    manifest['finished_utc']=datetime.now(timezone.utc).isoformat();manifest['all_executed']=not failed
    write_json(output/'manifest.json',manifest)
    if not failed and any(r['rq']==7 for r in manifest['models']):
        try:
            from .policy_report import generate
            generate(output,output/'rq7/policy_report')
            manifest['policy_report']={'execution':'completed','folder':'rq7/policy_report'}
        except Exception as exc:
            failed=True;manifest['all_executed']=False
            manifest['policy_report']={'execution':'failed','error':str(exc)}
            print(f'RQ7 report FAILED: {exc}',flush=True)
        write_json(output/'manifest.json',manifest)
    text=['# Kết quả chạy mô hình','',f'Chế độ: {manifest["mode"]}.','',
          '| RQ | Chạy | Phạm vi kết quả |','|---|---|---|']
    text += [f'| RQ{r["rq"]} | {r["execution"]} | {r.get("readiness",r.get("error",""))} |' for r in manifest['models']]
    text += ['','Mỗi thư mục có summary.json ghi phương pháp và giới hạn, CSV ghi kết quả. completed không đồng nghĩa kết luận nghiên cứu đã được kiểm chứng.']
    (output/'RUN_REPORT.md').write_text('\n'.join(text),encoding='utf8');print(f'OUTPUT: {output.resolve()}',flush=True)
    return 1 if failed else 0

if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,FileNotFoundError) as e:print(f'ERROR: {e}',file=sys.stderr);sys.exit(2)
