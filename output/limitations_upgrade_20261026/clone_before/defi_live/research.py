"""Read-only research evidence API; no user-supplied filesystem paths."""
import csv,json
from pathlib import Path

def json_file(path,default=None):
    return json.loads(path.read_text(encoding='utf8')) if path.is_file() else default

def csv_file(path,limit=20000):
    if not path.is_file():return []
    with path.open(encoding='utf-8-sig',newline='') as f:
        rows=[]
        for i,row in enumerate(csv.DictReader(f)):
            if i>=limit:break
            rows.append(row)
    return rows

def generation_two(results,data):
    results=Path(results).parent/'research_h124_v2_20261024';data=Path(data).parent/'research_h124_v2_20261024'
    return {'manifest':json_file(results/'manifest.json',{}),'header_progress':json_file(data/'header_progress.json',{}),
      'models':csv_file(results/'h4/model_comparison.csv')+csv_file(results/'h4_nb/model_comparison.csv'),'coverage':csv_file(results/'h4_feature_coverage.csv'),
      'util_models':csv_file(results/'h4_util/model_comparison.csv')+csv_file(results/'h4_util_nb/model_comparison.csv'),
      'prefix_models':csv_file(results/'h4_prefix/model_comparison.csv')+csv_file(results/'h4_prefix_nb/model_comparison.csv'),
      'prefix_coverage':csv_file(results/'h4_prefix_feature_coverage.csv'),
      'prefix_residuals':{**json_file(results/'h4_prefix/residuals.json',{}),**json_file(results/'h4_prefix_nb/residuals.json',{})},
      'util_residuals':{**json_file(results/'h4_util/residuals.json',{}),**json_file(results/'h4_util_nb/residuals.json',{})},
      'utilization_progress':json_file(data/'utilization_progress.json',{}),'utilization_coverage':csv_file(results/'h4_reserve_usage_coverage.csv'),
      'quarterly_context':{'risk':csv_file(results/'h4_quarterly_risk_context.csv'),'reserves':csv_file(results/'h4_quarterly_reserve_context.csv'),'basis':csv_file(results/'h4_quarterly_basis.csv'),'basket':csv_file(results/'h4_quarterly_basket.csv')},
      'features':csv_file(results/'h4_feature_dictionary.csv'),'sources':csv_file(results/'source_capabilities.csv'),
      'h1_concentration':csv_file(results/'h1_attribution/concentration.csv'),'h1_composition':csv_file(results/'h1_attribution/token_composition.csv'),'h1_wallets':csv_file(results/'h1_attribution/top_wallets.csv'),
      'residuals':{**json_file(results/'h4/residuals.json',{}),**json_file(results/'h4_nb/residuals.json',{})},'h2':json_file(results/'h2_full_validation/summary.json',json_file(results/'h2/summary.json',{})),
      'cascade_scenarios':csv_file(results/'cascade/scenario_comparison.csv'),'cascade_backtests':csv_file(results/'cascade/actual_path_backtest.csv'),
      'quote_collection':json_file(results/'cascade/quote_collection.json',{}),'impact_calibration':json_file(results/'cascade/impact_calibration.json',{}),
      'event_plan':json_file(data/'cascade_snapshots/quarter_plan.json',[])}

def cascade_result(results,data,event_date,shock,feedback):
    root=Path(results).parent/'research_h124_v2_20261024';data=Path(data).parent/'research_h124_v2_20261024'
    dates={r['quarter'] for r in json_file(data/'cascade_snapshots/quarter_plan.json',[])}
    if event_date not in dates or shock not in [.1,.2,.3] or feedback not in [True,False]:raise ValueError('Invalid scenario; select an available date and shock 0.1/0.2/0.3')
    folder=root/'cascade'/event_date/f'shock_{shock}_feedback_{feedback}'
    return {'available':(folder/'summary.json').exists(),'summary':json_file(folder/'summary.json',{}),
      'rounds':csv_file(folder/'rounds.csv'),'actions':csv_file(folder/'actions.csv',limit=250),
      'action_preview_limit':250,'scope':'Precomputed exploratory sensitivity; not a live calibrated forecast'}

def research_data(results,data):
    results=Path(results);data=Path(data);tables={}
    selected={'h1_baseline':'h1/baseline_by_quarter.csv','h1_breakpoints':'h1/breakpoints.csv','h1_curves':'h1/stress_curves.csv',
      'h2_sensitivity':'h2/matched_concentration_sensitivity.csv','h2_coverage':'h2/matched_coverage.csv',
      'h4_comparison':'h4/model_comparison.csv','h4_rolling':'h4/rolling_quarter_scores.csv','h4_nb':'h4_nb/model_comparison.csv','h4_15min':'h4_15min/model_comparison.csv'}
    for name,rel in selected.items():
        file=results/rel;rows=[]
        if file.is_file():
            with file.open(encoding='utf-8-sig',newline='') as f:
                for i,row in enumerate(csv.DictReader(f)):
                    if i>=20000:raise ValueError('Research table exceeds supported size')
                    rows.append(row)
        tables[name]=rows
    snapshots=[]
    for item in json_file(data/'h1/quarter_plan.json',[]):
        scope=json_file(data/'h1'/item['quarter']/'scope.json',item);snapshots.append(scope)
    repair=results.parent/'research_h123_repair_20261024'
    repaired={'manifest':json_file(repair/'manifest.json',{}),'h1_sensitivity':csv_file(repair/'h1/denominator_sensitivity.csv'),'concentration':csv_file(repair/'h2/concentration.csv'),
      'coverage':csv_file(repair/'h2/coverage.csv'),'uncertainty':json_file(repair/'h2/uncertainty.json',[]),
      'models':csv_file(repair/'h3/model_comparison.csv'),'residuals':json_file(repair/'h3/residuals.json',{}),'rolling':csv_file(repair/'h3/rolling_quarter_scores.csv'),
      'extrapolation':csv_file(repair/'h3/extrapolation.csv')}
    stage=results.parent/'research_h123_sources_20261024'
    sources={'manifest':json_file(stage/'manifest.json',{}),'concentration':csv_file(stage/'h2_market_concentration.csv'),'coverage':csv_file(stage/'h2_market_coverage.csv'),
      'models':csv_file(stage/'h3/model_comparison.csv'),'residuals':json_file(stage/'h3/residuals.json',{}),'rolling':csv_file(stage/'h3/rolling_quarter_scores.csv'),
      'comparison':csv_file(stage/'h3/common_primary_comparison.csv'),'calibration':csv_file(stage/'h3/event_calibration.csv')}
    return {'source_stage':sources,'repair':repaired,'manifest':json_file(results/'manifest.json',{'status':'research_worker_starting'}),'snapshots':snapshots,'tables':tables,'v2':generation_two(results,data),
      'h4_residuals':json_file(results/'h4/residuals.json',{}),'h4_nb_residuals':json_file(results/'h4_nb/residuals.json',{}),
      'comet_state_validation':json_file(results/'h2/archive_state_validation.json',{}),
      'literature':json_file(results/'literature/sources.json',{}),'block_date_check':json_file(results/'literature/ssrn_preprint_block_date_check.json',{}),
      'scope':'Research results with explicit snapshots and fixed evaluation windows; separate from live market data.'}
