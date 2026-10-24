"""Readiness across all five objectives; unfavorable results stay visible."""
from datetime import datetime,timezone,timedelta
import json
from .v2_common import *

def run():
    from .hypotheses import LABELS,current_report_labels
    from .model_quality_v2 import run as quality_report
    quality=quality_report()
    def scopes(root):
        return [load(root/r['quarter']/'scope.json',r) for r in load(root/'quarter_plan.json',[])]
    quarters=scopes(H1_DATA/'h1');events=scopes(DATA/'cascade_snapshots')
    header=load(DATA/'header_progress.json',{});data=load(OUT/'h4_data_readiness.json',{});h4=load(OUT/'h4/summary.json',{});h2=load(OUT/'h2_full_validation/summary.json',load(OUT/'h2/summary.json',{}))
    cascade=load(OUT/'cascade/readiness.json',{});residual={f'{folder}:{name}':row for folder in ['h4','h4_nb','h4_util','h4_util_nb','h4_prefix','h4_prefix_nb'] for name,row in load(OUT/folder/'residuals.json',{}).items()};caps=load(OUT/'source_capabilities.json',{})
    checks=load(OUT/'audit.json',{});tests=load(OUT/'tests.json',{});errors=load(OUT/'worker_status.json',{})
    objectives=[
      {'objective':1,'name':'Reconstruct borrower positions','status':'completed_quarter_census' if len(quarters)==15 and all(r.get('full_snapshot_complete') for r in quarters) else 'in_progress',
       'full':sum(r.get('full_snapshot_complete') is True for r in quarters),'required':15,'remaining':'Pre-event and higher-frequency risk positions are separate coverage requirements'},
      {'objective':2,'name':'HF and thresholds','status':'validated_on_completed_snapshots','remaining':'Unfinished snapshots and exact liquidation transaction behavior remain gated'},
      {'objective':3,'name':'Price shock simulation','status':'available_with_assumptions','remaining':'Derivative basis and non-ETH/BTC prices are sensitivity assumptions'},
      {'objective':4,'name':'Concentration/cascade','status':'partial_not_end_to_end_validated','remaining':'Liquidity routes, execution rules, gas/throughput and independent event backtests'},
      {'objective':5,'name':'Local systemic dashboard','status':'local_interactive_with_coverage_gates','remaining':'Full-market live synchronized snapshot and calibrated cascade are not yet available'}]
    manifest={'updated_utc':now(),'hypothesis_labels':LABELS,'objectives':objectives,'quarter_snapshots':quarters,'event_snapshots':events,'header_progress':header,'h4_data':data,'h4':h4,'h2':h2,
      'h4_nb':load(OUT/'h4_nb/summary.json',{}),'quarterly_context':load(OUT/'h4_quarterly_context.json',{}),'h1_attribution':load(OUT/'h1_attribution/summary.json',{}),
      'h4_util':load(OUT/'h4_util/summary.json',{}),'h4_util_nb':load(OUT/'h4_util_nb/summary.json',{}),'utilization_progress':load(DATA/'utilization_progress.json',{}),
      'model_quality':quality,'h4_prefix':load(OUT/'h4_prefix/summary.json',{}),'h4_prefix_nb':load(OUT/'h4_prefix_nb/summary.json',{}),'h4_prefix_data':load(OUT/'h4_prefix_data_readiness.json',{}),
      'source_access':load(OUT/'source_access.json',{}),'offline_status':load(OUT/'offline_status.json',{}),
      'cascade':cascade,'residual':residual,'source_capabilities':caps,'audit':checks,'tests':tests,'workers':errors,
      'old_outputs_preserved':checks.get('old_outputs_preserved'),'paid_source_used':False,'account_source_used':False}
    save(OUT/'manifest.json',manifest)
    h1_rows='\n'.join(f"| {r['quarter']} | {r.get('wallets_scanned',0):,}/{r['historical_borrowers']:,} | {r.get('status','pending')} | {r.get('full_snapshot_complete',False)} |" for r in quarters)
    event_rows='\n'.join(f"| {r['quarter']} | {r.get('wallets_scanned',0):,}/{r['historical_borrowers']:,} | {r.get('status','pending')} | {r.get('full_snapshot_complete',False)} |" for r in events)
    model_rows=[]
    model_data=[]
    for folder in ['h4','h4_nb','h4_util','h4_util_nb','h4_prefix','h4_prefix_nb']:
        if (OUT/folder/'model_comparison.csv').exists():model_data+=[dict(variant=folder,**r) for r in read(OUT/folder/'model_comparison.csv')]
    for r in model_data:
        model_rows.append(f"| {r['variant']}: {r['model']} | {float(r['test_loglik']):,.2f} | {float(r['test_count_MAE']):.4f} | {float(r['eta']):.4f} |")
    diagnostics='\n'.join(f"- {k}: KS p={v.get('bootstrap_KS_p','—')}, ACF p={v.get('bootstrap_acf_p','—')}, test fraction checked={v.get('fraction_test_bins_checked','—')}" for k,v in residual.items()) or 'Chưa có diagnostic hoàn tất.'
    prefix=manifest['h4_prefix'];prefix_nb=read(OUT/'h4_prefix_nb/model_comparison.csv') if (OUT/'h4_prefix_nb/model_comparison.csv').exists() else []
    findings=(f"Trên phần kỳ đã xác minh, validation chọn **{prefix['selected_spec_by_validation']}**. "
      f"Common coverage={prefix['common_bin_coverage']:.2%}; test có {prefix['test_bins']:,} bins, {prefix['test_events']:,} sự kiện. "
      f"Hawkes cải thiện tổng log-score so với Poisson cùng nhóm biến {prefix['excitation_logscore_gain']:,.2f}; "
      f"khoảng resampling theo ngày={prefix['daily_resampling_95_interval']}. "
      "Đây là bằng chứng dự báo có điều kiện; cần xem NB và residual trước khi kết luận H4. "
      "MAE thấp có thể do dự đoán gần zero trong chuỗi nhiều bins zero, nên không dùng MAE riêng để chọn model.") if prefix.get('status')=='completed_exploratory' else 'H4 phần kỳ chưa hoàn thành kiểm chứng; chưa kết luận từ bảng fit đang chạy.'
    if len(prefix_nb)==2:
        findings+=f" NB: chênh lệch log-score excitation trừ không excitation={float(prefix_nb[1]['test_loglik'])-float(prefix_nb[0]['test_loglik']):,.2f}. Không thay Poisson bằng NB chỉ vì đã nhìn thấy test; đây vẫn là robustness hậu kiểm."
        findings+=f" **NB dự báo tổng {float(prefix_nb[0]['expected_test_events']):,.0f} và {float(prefix_nb[1]['expected_test_events']):,.0f} sự kiện so với {prefix_nb[0]['test_events']} thực tế: sai lệch lớn, chưa dùng dự báo volume/count.**"
    backtest_rows=read(OUT/'cascade/actual_path_backtest.csv') if (OUT/'cascade/actual_path_backtest.csv').exists() else []
    backtest_note='Chưa có actual-path đối chiếu.'
    if backtest_rows:
        first=backtest_rows[0]
        backtest_note=f"Có {len(backtest_rows)} đối chiếu actual-path; ví dụ {first['event_date']}: mô phỏng {first['predicted_covered_route_actions']} actions so với {first['observed_matched_route_events']} sự kiện thuộc cùng cohort/direct routes. Chưa đạt calibration; các ngày hiện có là train, chưa có heldout event snapshot đầy đủ. Zero observed events không phải bằng chứng model đúng."
    text=f'''# Báo cáo nâng cấp dữ liệu, H1/H2/H4, cascade và dashboard — v2

Cập nhật {datetime.now(timezone(timedelta(hours=7))).isoformat(timespec='seconds')}.
Các trạng thái bên dưới là bằng chứng hiện tại; **không đồng nghĩa cả 5 mục tiêu đã hoàn tất**.
Dataset gốc và kết quả v1 giữ nguyên; v2 nằm tại `{OUT}`.

## Từng bước và điều kiện nghiệm thu

| Bước | Đã làm / trạng thái hiện tại | Đã sẵn sàng? / còn thiếu |
|---|---|---|
| Nguồn | Probe header, historical state, receipt và trace trên các RPC cấu hình | Xem source_capabilities.csv; thành công mẫu không chứng minh throughput/toàn kỳ. Không dùng nguồn trả phí/tài khoản |
| H1 census | {sum(r.get('full_snapshot_complete') is True for r in quarters)}/15 full cuối quý; checkpoint, historical E-mode/GHO, HF và aggregate-debt gate | Chỉ quý full được vào mô hình; không dùng mẫu 1–2 ví |
| H2 Comet | {h2.get('passed','—')}/{h2.get('selected','—')} mẫu khớp khoảng; {h2.get('remaining_replay','—')} còn replay; fingerprint {h2.get('fingerprinted_blocks','—')} block | Không coi fingerprint là xác minh semantics; coverage giá và financing definitions giữ nguyên |
| H4 availability | Header {header.get('collected_headers',0):,}/{header.get('required_headers',137824):,}; trạng thái panel={data.get('status','pending')} | Không build panel nếu còn update chưa xác minh block timestamp |
| H4 biến mới | Oracle-implied down returns 5m/1h, last jump, age; sampled base fee + age; stablecoin deviations; upgrade regimes | Giá không phải continuous market ticks; gas không phải median 5 phút; các proxy được đặt tên đúng |
| H4 dữ liệu khó | Có collector context theo quý: non-ETH/BTC collateral basket, Uniswap spot wstETH/ETH và WBTC basis, HF stock và WETH/USDC borrow usage | Chưa đủ tần suất 5 phút; giữ riêng auxiliary, không nội suy hoặc đưa vào fit như đã đủ. DEX depth mới sparse event windows |
| H4 mô hình | {h4.get('status','waiting_for_data')}; 5 nhóm biến × Poisson/Hawkes, cùng bins, validation kernel, rolling và residual | Đây là exploratory upgrade sau khi đã xem test cũ; không phải holdout xác nhận mới |
| H4 utilization hourly | Collector WETH/USDC đọc provider/config từng block, actual/virtual liquidity đúng phiên bản; model mở rộng ở h4_util/h4_util_nb | Chờ đủ target blocks; cùng common bins trong từng variant, không so raw likelihood giữa hai variant khác mẫu |
| Cascade dữ liệu | {sum(r.get('full_snapshot_complete') is True for r in events)}/{len(events)} full trước sự kiện; quote path 0/15/60 phút | Cần đủ snapshot/route; 3 mốc quote là sparse path, không continuous liquidity |
| Cascade engine | Close-factor theo revision, dust, E-mode bonus/fee, deficit, capacity/ordering, có/không feedback | Float economic approximation; grace/sentinel và exact EVM chưa đầy đủ. Không gỡ cờ experimental |
| Cascade calibration | Fit impact theo cặp token trên ngày train; kiểm tra quote ở ngày muộn; actual oracle path khi đủ header; đối chiếu đúng cohort/direct routes | Fit impact không chứng minh end-to-end cascade; đường giá thực có thể chứa feedback, không phải cú sốc ngoại sinh được nhận diện |
| Dashboard | API đọc tiến độ và kết quả riêng; bộ lọc và tải CSV; nhãn historical/live/sensitivity | Không gọi rolling census khác block là full-market synchronized snapshot |

{backtest_note}

## H1 — tiến độ từng quý

| Quý | Đã quét / universe | Trạng thái | Full |
|---|---:|---|---|
{h1_rows}

## Snapshot trước sự kiện — tách khỏi 15 quý

| Ngày | Đã quét / universe | Trạng thái | Full |
|---|---:|---|---|
{event_rows}

Ngày sự kiện được chọn hồi cứu từ đợt thanh lý lớn; borrower được lấy trước cutoff.
Không đánh đồng hai loại selection này hoặc gọi toàn bộ thiết kế là holdout độc lập.

## H4 — cùng mẫu ngoài thời gian huấn luyện

Train trước 2025, validation H1/2025, test H2/2025–Q3/2026. Mọi predictor chỉ có
thông tin trước đầu bin. Dữ liệu thiếu không được dùng giá tương lai để lấp.
Common-bin coverage={h4.get('common_bin_coverage','pending')}; chọn nhóm trên validation={h4.get('selected_spec_by_validation','pending')}.
Variant có utilization dùng common mask riêng; không so trực tiếp raw log-score
với variant core nếu sample khác. Mỗi variant tái fit baseline trên chính sample đó.

| Model | Test log-score | Count MAE | Eta |
|---|---:|---:|---:|
{chr(10).join(model_rows)}

{diagnostics}

Không chọn mô hình bằng test score. Không gọi self-excitation là nhận diện nhân quả.
Residual không đạt vẫn được công bố. Bootstrap kiểm tra mọi segment hợp lệ,
điều kiện trên history quan sát trước mỗi segment; ACF không nối qua khoảng thiếu.
Future-only upgrade dummies không có hệ số được nhận diện: xem fitted_models.json.

## Phần kỳ đã xác minh riêng và truy cập nguồn hiện tại

{findings}

`model_quality.csv/json` tách lỗi calibration khỏi lỗi chạy code. KS/residual
không đạt vẫn được công bố; không clipping dự báo hoặc đổi nhãn để che lỗi.
Chưa có mô hình v2 nào được phê duyệt làm live forecast. Việc sửa calibration
cần mô hình/biến phù hợp hơn và kiểm tra trên kỳ mới, không tối ưu lại theo test cũ.

Trạng thái RPC mới nhất: `{manifest['source_access']}`.
Phần kỳ H4 riêng: `{manifest['h4_prefix_data'].get('source',{})}`;
trạng thái fit: `{manifest['h4_prefix'].get('status','pending')}`.
`h4_prefix` và `h4_prefix_nb` dừng trước update đầu tiên chưa xác minh,
không nối qua khoảng thiếu và **không phải kết quả đủ đến 30/09/2026**.
Mọi variant so sánh trên cùng common bins trong variant; raw likelihood giữa
các variant khác kỳ/mẫu không thể so trực tiếp. Offline stages: `{manifest['offline_status']}`.

## Nguồn hiện tại và khi nào cần trả phí

Nguồn public đã từng cung cấp historical headers/state/receipts; probe trace có kết quả
riêng theo endpoint. Call trace không thay thế state replay. Chưa mua dịch vụ hoặc dùng tài khoản.
Để có HF queue theo ngày toàn kỳ cần khoảng 1.343 census ngày, với số ví biến đổi
theo lịch sử; đây là workload lớn hơn nhiều so với 15 snapshot quý, chưa có SLA.
Để đo median gas mọi block hoặc continuous DEX depth cần workload riêng; sampled
controls hiện tại không được quảng bá thành các chuỗi đó. Nếu cần nguồn khác,
báo trước method, block/time range, lượng call và hạn chế của nguồn hiện tại.

## Audit và tái lập

- Audit: `{OUT/'audit.json'}`; test: {tests.get('total','pending')} tổng,
  {tests.get('passed','pending')} đạt, {tests.get('skipped','pending')} skip,
  failures={tests.get('failures','pending')}, errors={tests.get('errors','pending')}.
- Bảo toàn đầu ra cũ: {checks.get('old_outputs_preserved','pending')}.
- Worker errors được lưu công khai trong worker_status.json; không chuyển lỗi thành completed.
- Dashboard http://127.0.0.1:8790/research; README_RESEARCH_V2.md có lệnh và phạm vi.
'''
    text=current_report_labels(text)
    text+='\nNhãn mới: H2 giữ nguyên là concentration; H3 = clustering/self-excitation (H4 cũ). Tên module, JSON keys, RQ và thư mục cũ không đổi. H1/2025, H2/2025 trong mốc thời gian vẫn là nửa đầu/nửa cuối năm.\n'
    (OUT/'BAO_CAO_NANG_CAP_V2.md').write_text(text,encoding='utf8');return manifest
if __name__=='__main__':run()
