# Báo cáo nguồn dữ liệu và nghiên cứu H1/H2/H3 — kỳ chính đến Q1/2026

Cập nhật 2026-10-24T03:20:12.511305+00:00. Kết quả mới riêng tại `C:\Users\HAI NAM\Finance1\defi-research\results\research_h123_sources_20261024`.

**Theo yêu cầu mới, loại Q2 và Q3/2026 khỏi phạm vi chính.**
H1: 13/13 full cuối quý; completed_within_revised_scope.
H3: test 01/07/2025 đến trước 01/04/2026; không phải một holdout mới chưa từng xem.
H2: calendar 2024 là matched comparison chính; extended chỉ đến 31/03/2026.
Kết quả cũ dài hơn giữ nguyên để đối chiếu, không đổi nhãn thành dữ liệu đủ scope mới.

| Phần | Đã thực hiện | Giới hạn hiện tại |
|---|---|---|
| H1 | Xác minh hash và full gate 13 snapshot trong kỳ chính mới | Không còn thiếu snapshot cuối quý trong scope; HF theo phút và kiểm chứng provider độc lập vẫn chưa có |
| Nguồn RPC | 4 public sources bị HTTP403 trong probe; chưa dùng account/paid | Không cần mua nguồn chỉ để bù hai quý đã loại; HF tần suất cao vẫn cần source khác |
| Giá độc lập | Kraken USDC/USD public Trades; checkpoint, cursor/time/order validation, 5s latency giả định | Bulk ZIP bị403; Coin Metrics community không trả mẫu hourly2024; Coinbase thử bị403 |
| H2 | Full count/native, market USD và oracle USD trên common support; max-age60/300/3600s | partial_source_gap; không peg-impute; một sàn, không phải giá tổng hợp |
| H3 controls | Borrow/Repay/Supply/Withdraw prior24h, 30s availability delay + strictly lagged bins | Counts là hoạt động thực đo, không phải outstanding debt/TVL/HF queue; vẫn có endogeneity |
| H3 model | Hurdle logistic event probability + zero-truncated NB size; market/activity/history controls; validation ridge | completed_exploratory; không phải structural Hawkes branching process |

## H2 coverage

`market_progress.json`: `{'updated_utc': '2026-10-24T03:20:12.358962+00:00', 'requests_this_run': 828, 'target_events': 7264, 'target_timestamps': 3639, 'covered_timestamps': 3638, 'complete': False, 'errors': [], 'paid_source_used': False, 'account_source_used': False, 'quarantined_pages': 1, 'status': 'partial_source_gap'}`.
`market_data_readiness.json`: `{'updated_utc': '2026-10-24T03:20:12.302550+00:00', 'source': 'Kraken public USDC/USD trade history', 'scope': '2024-02-01 to 2026-04-01T00:00:00+00:00; matched USDC-debt single-WETH/WBTC-collateral events', 'events': 7264, 'verified_events': 7263, 'fresh_60s_events': 7149, 'fresh_300s_events': 7259, 'fresh_3600s_events': 7262, 'latency_assumption_seconds': 5, 'primary_coverage_lookback_seconds': 300, 'quote_table_sha256': '5053104aac885276ff32de841964bc086aa541cadc04412053f83e4217362f74', 'paid_source_used': False, 'account_source_used': False, 'limitations': ['Single exchange; historical trade time plus assumed 5s latency, not verified receipt time', 'No carry beyond maximum quote age; no USD peg substitution', 'Event-targeted quotes cannot be used as full-clock H3 covariates', 'No trades in a window can leave no fresh quote; coverage is not automatically 100%'], 'quarantined_pages': 1}`.
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
| aave_v3 | 1102 | 519 | 0.09951 | 55.99% |
| compound_v3_usdc | 158 | 151 | 0.35114 | 67.99% |
| morpho_blue | 2 | 2 | 0.70887 | 92.10% |

Comet tập trung theo giá trị cao hơn Aave trong mẫu này; không suy rộng thành
mọi token/thời kỳ. Morpho chỉ có 2 events/2 ví, không đủ xếp hạng toàn protocol.
Bootstrap của output cũ khác support không chuyển sang làm khoảng tin cậy cho
bảng giá market mới. Đây là thống kê mô tả, chưa là kết quả nhân quả.

## H3: kết quả trên cùng sample

Model được validation chọn: `activity_history`.

| Model | Eligible validation | Test log-score | Expected / observed |
|---|---|---:|---:|
| constant | False | -13296.501571476543 | 0.41193996570688346 |
| market | True | -11559.430993094848 | 0.9448855091359349 |
| activity | True | -11352.572455067088 | 1.538048541428411 |
| activity_history | True | -11070.51696413469 | 1.4597650053460185 |

So frozen fits trên cùng kỳ test: `{'primary_end_exclusive': '2026-04-01T00:00:00+00:00', 'same_test_support': True, 'interpretation': 'Descriptive rescoring of frozen fits; earlier training protocols/availability assumptions differ. No test-based reselection and no causal attribution of gain.'}`.
Xem `h3/common_primary_comparison.csv`; các training/availability assumptions
của model cũ và mới khác nhau nên không gán riêng gain cho một biến hoạt động.

Residual diagnostics: `{'activity_history': {'reference': 'Monte Carlo iid-uniform PIT null; fixed training fit, not parametric event bootstrap', 'replications': 499, 'bins': 78643, 'segments': 270, 'KS': 0.0056588137014056406, 'max_within_segment_ACF': 0.016431306549999542, 'uniform_null_KS_p': 0.02, 'uniform_null_ACF_p': 0.002, 'limitations': ['Predictive PIT calibration diagnostic, not parameter uncertainty or causal inference', 'Not numerically identical to earlier fixed-market parametric-bootstrap p-values', 'Data/model choice remains exploratory after earlier test inspection']}, 'activity': {'reference': 'Monte Carlo iid-uniform PIT null; fixed training fit, not parametric event bootstrap', 'replications': 499, 'bins': 78643, 'segments': 270, 'KS': 0.008117436629277441, 'max_within_segment_ACF': 0.01763706140080665, 'uniform_null_KS_p': 0.002, 'uniform_null_ACF_p': 0.002, 'limitations': ['Predictive PIT calibration diagnostic, not parameter uncertainty or causal inference', 'Not numerically identical to earlier fixed-market parametric-bootstrap p-values', 'Data/model choice remains exploratory after earlier test inspection']}}`.
PIT dùng null iid-uniform Monte Carlo, khác parametric bootstrap của lượt trước;
không so p-value như cùng một procedure. Ước lượng xác suất và positive-size tách
riêng; không ép p-value đạt. Chưa duyệt live forecast, chưa nhận diện nhân quả.

## Bảo toàn và chạy lại

- Old outputs preserved: **True**.
- Test: `{'updated_utc': '2026-10-24T03:19:12.483636+00:00', 'run': 249, 'passed': 243, 'skipped': 6, 'failures': 0, 'errors': 0, 'log': 'output/research_h123_sources_20261024/tests_full.log', 'initial_sandbox_attempt': 'Socket restrictions; rerun with local socket access passed'}`.
- Source audit: `{'passed': True, 'errors': [], 'pages_verified': 1249, 'priced_quotes_verified': 7262, 'quarantined_pages': [{'since': '1713068850000000000', 'reason': 'First returned trade is 19525.7556 seconds after requested since; cannot verify initial gap. Raw page retained, excluded from coverage.', 'excluded_from_coverage': True}]}`.
- Nếu `partial_source_gap`: collector đã kết thúc lượt quét; trang có gap được giữ gốc nhưng loại khỏi coverage. Không tự tiếp tục gọi một source đã cho cùng khoảng trống.
- `python -m research_h124.market_prices --minutes 60` chạy tiếp source; API không tài khoản.
- `python -m research_h124.activity_controls` rồi `python -m research_h124.hurdle_model --replications 499`.
- `python -m research_h124.source_analysis` cập nhật coverage và báo cáo.
- Dashboard `/research#sources`; không refit tự động khi đổi bộ lọc.
