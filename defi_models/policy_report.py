"""Validated, data-derived RQ7 exports. Importing this module writes no files."""
import argparse
import csv
import json
import math
from pathlib import Path
from .core import ROOT, require, sha, write_csv, write_json

SCENARIOS=[
    dict(scenario_id='S0',name='Co_so',close_factor=.5,bonus=.05,lt_shift=0.),
    dict(scenario_id='S1',name='Bonus_thap',close_factor=.5,bonus=.03,lt_shift=0.),
    dict(scenario_id='S2',name='Bonus_cao',close_factor=.5,bonus=.08,lt_shift=0.),
    dict(scenario_id='S3',name='Tang_LT_3_diem',close_factor=.5,bonus=.05,lt_shift=.03),
    dict(scenario_id='S4',name='Close_factor_100',close_factor=1.,bonus=.05,lt_shift=0.),
    dict(scenario_id='S5',name='CF25_bonus3_LTcong3',close_factor=.25,bonus=.03,lt_shift=.03),
]


def read_json(path):
    def reject(value):raise ValueError(f'Invalid JSON number: {value}')
    return json.loads(path.read_text(encoding='utf-8-sig'),parse_constant=reject)


def flag(value, name):
    require(value in ('True','False'),f'Invalid {name}: {value!r}')
    return value=='True'


def generate(run, out):
    run,out=Path(run).resolve(),Path(out).resolve()
    grid_path=run/'rq7/policy_grid.csv';summary_path=run/'rq7/summary.json'
    manifest_path=run/'manifest.json';config_path=run/'config.json'
    manifest,summary,cfg=[read_json(p) for p in (manifest_path,summary_path,config_path)]
    require(manifest.get('all_executed') is True,'Run is incomplete; do not export it as a successful policy result')
    require(any(r.get('rq')==7 and r.get('execution')=='completed' for r in manifest.get('models',[])),'No completed RQ7 in manifest')
    require(cfg==manifest.get('config'),'Run config differs from manifest')
    require(summary.get('status')=='exploratory','Policy result must retain exploratory status')
    with grid_path.open(encoding='utf-8-sig',newline='') as handle:grid=list(csv.DictReader(handle))
    require(grid and len(grid)==summary.get('scenarios'),'Empty or mismatched policy grid')
    index={};keys=['shock_fraction','close_factor','bonus_fraction','lt_shift']
    measures=['repaid_usd','seized_usd','terminal_collateral_shortfall_usd','max_cumulative_price_impact','liquidator_profit_usd']
    for row in grid:
        key=tuple(float(row[k]) for k in keys)
        require(all(math.isfinite(x) for x in key),'Non-finite policy parameters')
        require(key not in index,'Duplicate policy scenario')
        require(0<=key[0]<1 and 0<key[1]<=1 and 0<=key[2]<1 and -1<key[3]<1,'Invalid policy parameters')
        require(all(math.isfinite(float(row[k])) and float(row[k])>=0 for k in measures),'Invalid financial metric')
        require(float(row['max_cumulative_price_impact'])<1,'Invalid impact')
        limited=flag(row['reached_round_limit'],'reached_round_limit')
        evaluable=flag(row['pareto_evaluable'],'pareto_evaluable')
        require(evaluable== (not limited),'Inconsistent Pareto evaluation flag')
        pareto=row['pareto_nondominated']
        require((evaluable and pareto in ('True','False')) or (not evaluable and pareto==''),'Missing or misleading Pareto status')
        flag(row['incomplete_dynamics'],'incomplete_dynamics')
        require(int(row['terminal_eligible_wallets'])>=0,'Negative residual wallets')
        index[key]=row
    expected={(float(s),float(c),float(b),float(t)) for s in cfg['cascade_shocks'] for c in cfg['policy_close_factors'] for b in cfg['policy_bonuses'] for t in cfg['policy_lt_shifts']}
    require(set(index)==expected,'Policy grid does not match the configured Cartesian product')
    source_hashes={p.relative_to(run).as_posix():sha(p) for p in (grid_path,summary_path,config_path)}
    exported=[];missing=[]
    for scenario in SCENARIOS:
        for shock in cfg['cascade_shocks']:
            key=(float(shock),scenario['close_factor'],scenario['bonus'],scenario['lt_shift'])
            row=index.get(key)
            if row is None:
                missing.append(dict(scenario_id=scenario['scenario_id'],shock_fraction=shock));continue
            exported.append(dict(scenario_id=scenario['scenario_id'],scenario_name=scenario['name'],
                shock_fraction=shock,close_factor=scenario['close_factor'],bonus_fraction=scenario['bonus'],lt_shift=scenario['lt_shift'],
                repaid_usd=float(row['repaid_usd']),seized_usd=float(row['seized_usd']),
                terminal_collateral_shortfall_usd=float(row['terminal_collateral_shortfall_usd']),
                max_cumulative_price_impact=float(row['max_cumulative_price_impact']),liquidator_profit_usd=float(row['liquidator_profit_usd']),
                reached_round_limit=flag(row['reached_round_limit'],'reached_round_limit'),
                pareto_evaluable=flag(row['pareto_evaluable'],'pareto_evaluable'),
                pareto_nondominated=None if row['pareto_nondominated']=='' else row['pareto_nondominated']=='True',
                incomplete_dynamics=flag(row['incomplete_dynamics'],'incomplete_dynamics'),
                terminal_eligible_wallets=int(row['terminal_eligible_wallets']),stop_reason=row['stop_reason']))
    require(exported,'No configured scenario matches the named policy scenarios')
    # Validate everything before making an output directory; never overwrite reports.
    require(not out.exists(),f'Output exists: {out}. Select a new --out')
    require(not any(out==p or out in p.parents for p in (grid_path,summary_path,config_path,manifest_path)),'Output must not contain source files')
    out.mkdir(parents=True)
    write_csv(out/'policy_scenarios.csv',SCENARIOS)
    write_csv(out/'sensitivity_results.csv',exported)
    scope=summary.get('snapshot',{})
    lines=['# RQ7 — Độ nhạy chính sách (exploratory)','',
        f'Run nguồn: {run}',f"Snapshot block: {scope.get('block')}; ví có nợ: {scope.get('active_debt_wallets')}; reported debt: {scope.get('reported_debt_usd')} USD.",
        f"Cấu hình: max_rounds={cfg['max_rounds']}; grid={len(grid)}; named scenarios={len(exported)}.",'',
        'Các con số dưới đây được đọc trực tiếp từ CSV của run đã chọn; không tự chọn run theo mtime.',
        'Đây là mô phỏng giả định trên phạm vi snapshot trong summary, không phải chứng nhận dữ liệu toàn thị trường.','',
        '| Scenario | Shock | CF | Bonus | LT shift (điểm %) | Repaid USD | Seized USD | Shortfall USD | Impact | Pareto | Còn HF<1 | Stop |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---|']
    for r in exported:
        pareto='Chưa đánh giá' if r['pareto_nondominated'] is None else ('Không bị trội' if r['pareto_nondominated'] else 'Bị trội')
        lines.append(f"| {r['scenario_id']} | {r['shock_fraction']:.0%} | {r['close_factor']:.0%} | {r['bonus_fraction']:.0%} | {r['lt_shift']*100:+.1f} | {r['repaid_usd']:,.2f} | {r['seized_usd']:,.2f} | {r['terminal_collateral_shortfall_usd']:,.2f} | {r['max_cumulative_price_impact']:.3%} | {pareto} | {r['terminal_eligible_wallets']} | {r['stop_reason']} |")
    lines+=['','## Nhận xét tính từ grid đầy đủ','']
    for shock in cfg['cascade_shocks']:
        candidates=[r for r in grid if math.isclose(float(r['shock_fraction']),shock,rel_tol=0,abs_tol=1e-12) and r['pareto_evaluable']=='True']
        if not candidates:
            lines.append(f'- Shock {shock:.0%}: không có kịch bản đủ điều kiện so sánh Pareto.');continue
        minimum=min(float(r['terminal_collateral_shortfall_usd']) for r in candidates)
        best=[r for r in candidates if math.isclose(float(r['terminal_collateral_shortfall_usd']),minimum,rel_tol=0,abs_tol=1e-6)]
        labels='; '.join(f"CF={float(r['close_factor']):.0%}, bonus={float(r['bonus_fraction']):.0%}, LT={float(r['lt_shift'])*100:+.1f} điểm" for r in best)
        lines.append(f'- Shock {shock:.0%}: shortfall nhỏ nhất trong các kịch bản dừng trước giới hạn là {minimum:,.2f} USD; {labels}. Đây chỉ là tối thiểu theo một mục tiêu trong engine.')
    lines+=['','## Giới hạn diễn giải','',
        '- Tăng LT làm HF tăng khi giữ balances/prices cố định; không tự gọi đó là siết an toàn.',
        '- Collateral seized là tài sản bị thu giữ, không phải tổn thất ròng vì một phần nợ đã được trả.',
        '- Shortfall là chênh lệch kế toán mô hình, không phải bad debt ghi nhận on-chain.',
        '- Pareto so sánh trong cùng shock; kịch bản chạm giới hạn giữ trạng thái chưa đánh giá.',
        '- Còn vị thế HF<1 khi hết thanh lý sinh lời khác với chạm giới hạn vòng.',
        '- Không suy ra khuyến nghị CF/bonus cho Aave từ engine chưa hiệu chỉnh hoặc từ mẫu nhỏ.',
        f'- Kịch bản tham chiếu không có trong cấu hình hiện tại: {len(missing)}; xem export_manifest.json.',
        '- SHA-256 nguồn được lưu trong export_manifest.json; không có thao tác sửa dữ liệu/audit.']
    (out/'RQ7_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    metadata=dict(source_run=str(run),source_files=source_hashes,source_versions=manifest.get('versions'),
                  input_files=manifest.get('input_files',[]),source_code=manifest.get('code_files',[]),
                  status='exploratory',snapshot=scope,missing_named_scenarios=missing,
                  files={p.name:sha(p) for p in out.iterdir() if p.is_file()})
    write_json(out/'export_manifest.json',metadata)
    return metadata


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True,help='Explicit parent run containing manifest.json and rq7/')
    parser.add_argument('--out',type=Path,help='New destination; defaults to RUN/rq7/policy_report')
    args=parser.parse_args(argv)
    destination=args.out or args.run/'rq7/policy_report'
    try:result=generate(args.run,destination)
    except (ValueError,OSError,KeyError,TypeError) as exc:
        parser.exit(2,f'ERROR: {exc}\n')
    print(json.dumps({'output':str(destination.resolve()),'status':result['status'],'source':result['source_run']},ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
