"""Primary H1 scope, independent-price concentration and stage report."""
import argparse,time
from collections import defaultdict
from .next_common import *
from .h2 import normalized
from defi_models.core import concentration

def h1_scope():
    accepted=[];checks=[]
    for q in load(H1_DATA/'h1/quarter_plan.json',[]):
        if q['cutoff_exclusive_utc']>PRIMARY_END_UTC:continue
        folder=H1_DATA/'h1'/q['quarter'];s=load(folder/'scope.json',{});freeze=load(folder/'freeze_manifest.json',{})
        valid=s.get('full_snapshot_complete') and bool(freeze) and all(digest(folder/n)==h for n,h in freeze.get('files',{}).items())
        checks.append({'quarter':q['quarter'],'complete_and_hash_verified':bool(valid),'historical_borrowers':s.get('historical_borrowers'),'active_debt_wallets':s.get('active_debt_wallets')})
        if valid:accepted.append(q['quarter'])
    result={'updated_utc':now(),'primary_start':'2023-01-27T00:00:00+00:00','primary_end_exclusive':PRIMARY_END_UTC,'last_quarter':'2026Q1','required_snapshots':13,'full_snapshots':len(accepted),
      'status':'completed_within_revised_scope' if len(accepted)==13 and len(checks)==13 else 'incomplete','quarters':checks,
      'scope_change':'User excluded Q2/Q3 2026; original datasets/results retained, not relabelled as full 15-quarter coverage',
      'limitations':['Within-scope interface/HF/debt reconciliation; independent-provider checks remain unavailable','Quarter-end stock is not high-frequency risk position history']}
    save(OUT/'h1_primary_scope.json',result);return result

def market_concentration():
    path=OUT/'market_event_quotes.csv'
    if not path.exists():return {}
    events=read(path);rows=[];coverage=[]
    for window,lo,hi in [('calendar_2024','2024-02-01','2025-01-01'),('primary_extended','2024-02-01',PRIMARY_END_UTC[:10])]:
      for token in ['0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2','0x2260fac5e5542a773aa44fbcfedf7c193bc2c599']:
       for protocol in ['aave_v3','compound_v3_usdc','morpho_blue']:
        sample=[r for r in events if r['protocol']==protocol and r['collateral_token']==token and lo<=r['date']<hi]
        groups=[('full_scope','none','count',sample),('full_scope','none','native_USDC',sample)]
        for age in [60,300,3600]:
            good=[r for r in sample if r['market_debt_usd']!='' and float(r['market_age_seconds'])<=age]
            shared=[r for r in good if r['oracle_debt_usd']!='' and r['oracle_age_seconds']!='' and float(r['oracle_age_seconds'])<=93600]
            coverage.append({'window':window,'token':token,'protocol':protocol,'max_age_seconds':age,'matched_events':len(sample),'market_priced_events':len(good),'market_coverage':len(good)/len(sample) if sample else None,'common_oracle_market_events':len(shared)})
            for support,rs,metrics in [('market_fresh',good,['count','native_USDC','market_USD']),('oracle_market_common',shared,['count','native_USDC','market_USD','oracle_USD'])]:
                groups += [(support,age,metric,rs) for metric in metrics]
        for support,age,metric,rs in groups:
            weights=defaultdict(float)
            for r in rs:weights[r['borrower']]+=1. if metric=='count' else float(r['debt_native_USDC']) if metric=='native_USDC' else float(r['market_debt_usd']) if metric=='market_USD' else float(r['oracle_debt_usd'])
            v=list(weights.values());rows.append({'window':window,'token':token,'protocol':protocol,'support':support,'max_age_seconds':age,'metric':metric,'priced_or_selected_events':len(rs),'matched_events':len(sample),**normalized(concentration(v),v)})
    write(OUT/'h2_market_concentration.csv',rows);write(OUT/'h2_market_coverage.csv',coverage)
    progress=load(OUT/'market_progress.json',{})
    return {'updated_utc':now(),'rows':len(rows),'coverage_rows':len(coverage),'status':'completed_scope_collection' if progress.get('complete') else 'partial_source_gap' if progress.get('quarantined_pages') else 'provisional_collection_in_progress',
      'limitations':['Collection completion does not imply every event has a fresh market quote','Single exchange trade pricing; not a consolidated executable USD price','Market-fresh and oracle-common supports differ; compare within identical support','Point estimates; existing day-bootstrap intervals from other periods/supports cannot be reused']}

def report():
    from .market_prices import build
    OUT.mkdir(parents=True,exist_ok=True);scope=h1_scope()
    if (DATA_NEXT/'kraken.sqlite').exists():build()
    concentration=market_concentration();previous=load(OUT/'source_audit.json',{});h3=load(OUT/'h3/summary.json',{})
    if h3.get('updated_utc','')<load(OUT/'h3/protocol.json',{}).get('created_utc',''):h3={}
    candidates=read(OUT/'h3/model_comparison.csv') if (OUT/'h3/model_comparison.csv').exists() else []
    manifest={'updated_utc':now(),'primary_scope':scope,'market_progress':load(OUT/'market_progress.json',{}),'market_readiness':load(OUT/'market_data_readiness.json',{}),
      'h2':concentration,'activity_controls':load(OUT/'activity_readiness.json',{}),'h3':h3,'h3_models_written':len(candidates),
      'old_outputs_preserved':previous.get('old_outputs_preserved',False),'tests':load(OUT/'tests.json',{}),'source_audit':previous,'source_checks':load(OUT/'source_checks.json',{}),'paid_source_used':False,'account_source_used':False}
    comparison=read(OUT/'h3/common_primary_comparison.csv') if (OUT/'h3/common_primary_comparison.csv').exists() else []
    manifest['same_test_comparison']=load(OUT/'h3/common_primary_comparison_scope.json',{})
    save(OUT/'manifest.json',manifest)
    model_rows='\n'.join(f"| {r['model']} | {r.get('validation_eligible','—')} | {r.get('test_loglik','—')} | {r.get('expected_observed_ratio','—')} |" for r in candidates)
    matched=read(OUT/'h2_market_concentration.csv') if (OUT/'h2_market_concentration.csv').exists() else []
    matched=[r for r in matched if r['window']=='calendar_2024' and r['token'].startswith('0xc02') and r['support']=='market_fresh' and r['metric']=='market_USD' and r['max_age_seconds']=='300']
    h2_rows='\n'.join(f"| {r['protocol']} | {r['priced_or_selected_events']} | {r['entities']} | {float(r['hhi_normalized']):.5f} | {float(r['top1_percent_share']):.2%} |" for r in matched)
    text=f'''# Báo cáo nguồn dữ liệu và nghiên cứu H1/H2/H3 — kỳ chính đến Q1/2026

Cập nhật {now()}. Kết quả mới riêng tại `{OUT}`.

**Theo yêu cầu mới, loại Q2 và Q3/2026 khỏi phạm vi chính.**
H1: {scope['full_snapshots']}/{scope['required_snapshots']} full cuối quý; {scope['status']}.
H3: test 01/07/2025 đến trước 01/04/2026; không phải một holdout mới chưa từng xem.
H2: calendar 2024 là matched comparison chính; extended chỉ đến 31/03/2026.
Kết quả cũ dài hơn giữ nguyên để đối chiếu, không đổi nhãn thành dữ liệu đủ scope mới.

| Phần | Đã thực hiện | Giới hạn hiện tại |
|---|---|---|
| H1 | Xác minh hash và full gate 13 snapshot trong kỳ chính mới | Không còn thiếu snapshot cuối quý trong scope; HF theo phút và kiểm chứng provider độc lập vẫn chưa có |
| Nguồn RPC | 4 public sources bị HTTP403 trong probe; chưa dùng account/paid | Không cần mua nguồn chỉ để bù hai quý đã loại; HF tần suất cao vẫn cần source khác |
| Giá độc lập | Kraken USDC/USD public Trades; checkpoint, cursor/time/order validation, 5s latency giả định | Bulk ZIP bị403; Coin Metrics community không trả mẫu hourly2024; Coinbase thử bị403 |
| H2 | Full count/native, market USD và oracle USD trên common support; max-age60/300/3600s | {concentration.get('status','waiting')}; không peg-impute; một sàn, không phải giá tổng hợp |
| H3 controls | Borrow/Repay/Supply/Withdraw prior24h, 30s availability delay + strictly lagged bins | Counts là hoạt động thực đo, không phải outstanding debt/TVL/HF queue; vẫn có endogeneity |
| H3 model | Hurdle logistic event probability + zero-truncated NB size; market/activity/history controls; validation ridge | {h3.get('status','running_or_pending')}; không phải structural Hawkes branching process |

## H2 coverage

`market_progress.json`: `{manifest['market_progress']}`.
`market_data_readiness.json`: `{manifest['market_readiness']}`.
Chỉ ghép quote đã có trước event theo giả định trade-time+5s; kiểm chứng bao phủ
chuỗi phân trang trước khi chọn last trade. Khoảng không có giao dịch có thể
không có quote đủ tươi. Mẫu giá tập trung ở event không dùng làm controls H3
trên toàn clock; điều đó tránh selection leakage. Historical receipt time thực
chưa xác minh; không quảng bá thành price real-time đã quan sát được chắc chắn.

### Finding mô tả H2 — 01/02–31/12/2024, WETH collateral, USDC debt

Giá market tối đa 300 giây; cùng định nghĩa event/token/kỳ, nhưng chưa đồng nhất
quy mô và cấu trúc người dùng giữa protocol.

| Protocol | Events có giá | Ví | HHI chuẩn hóa | Top1% ví share |
|---|---:|---:|---:|---:|
{h2_rows}

Comet tập trung theo giá trị cao hơn Aave trong mẫu này; không suy rộng thành
mọi token/thời kỳ. Morpho chỉ có 2 events/2 ví, không đủ xếp hạng toàn protocol.
Bootstrap của output cũ khác support không chuyển sang làm khoảng tin cậy cho
bảng giá market mới. Đây là thống kê mô tả, chưa là kết quả nhân quả.

## H3: kết quả trên cùng sample

Model được validation chọn: `{h3.get('selected_by_validation','pending')}`.

| Model | Eligible validation | Test log-score | Expected / observed |
|---|---|---:|---:|
{model_rows}

So frozen fits trên cùng kỳ test: `{manifest['same_test_comparison']}`.
Xem `h3/common_primary_comparison.csv`; các training/availability assumptions
của model cũ và mới khác nhau nên không gán riêng gain cho một biến hoạt động.

Residual diagnostics: `{h3.get('diagnostics','pending')}`.
PIT dùng null iid-uniform Monte Carlo, khác parametric bootstrap của lượt trước;
không so p-value như cùng một procedure. Ước lượng xác suất và positive-size tách
riêng; không ép p-value đạt. Chưa duyệt live forecast, chưa nhận diện nhân quả.

## Bảo toàn và chạy lại

- Old outputs preserved: **{manifest['old_outputs_preserved']}**.
- Test: `{manifest['tests']}`.
- Source audit: `{ {k:v for k,v in manifest['source_audit'].items() if k in ['passed','pages_verified','priced_quotes_verified','quarantined_pages','errors']} }`.
- Nếu `partial_source_gap`: collector đã kết thúc lượt quét; trang có gap được giữ gốc nhưng loại khỏi coverage. Không tự tiếp tục gọi một source đã cho cùng khoảng trống.
- `python -m research_h124.market_prices --minutes 60` chạy tiếp source; API không tài khoản.
- `python -m research_h124.activity_controls` rồi `python -m research_h124.hurdle_model --replications 499`.
- `python -m research_h124.source_analysis` cập nhật coverage và báo cáo.
- Dashboard `/research#sources`; không refit tự động khi đổi bộ lọc.
'''
    (OUT/'BAO_CAO_NGUON_VA_KET_QUA_H1_H2_H3.md').write_text(text,encoding='utf8');return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--watch-minutes',type=float,default=0);a=p.parse_args();deadline=time.monotonic()+a.watch_minutes*60
    while True:
        m=report();print(m['updated_utc'],flush=True)
        if m['market_progress'].get('complete') and m['h3'].get('status')=='completed_exploratory':break
        if time.monotonic()>=deadline:break
        time.sleep(30)
