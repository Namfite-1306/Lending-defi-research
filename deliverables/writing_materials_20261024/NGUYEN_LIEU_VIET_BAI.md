# Bộ nguyên liệu viết bài DeFi lending

Ngày chốt: **24/10/2026, giờ Việt Nam**. Mọi số liệu dưới đây lấy từ output local, không suy từ hình minh họa. Chưa phải bài đã phản biện. Chưa khẳng định tính mới tuyệt đối so với toàn bộ literature.

## 1. Phạm vi và cách đặt bài

Tên đề xuất: **Borrower Vulnerability, Liquidation Concentration, and Conditional Clustering in DeFi Lending**.

Câu chuyện chính: rủi ro có ba chiều — vị thế dễ tổn thương khi giá giảm, sự tập trung theo ví của thanh lý, và khả năng dự báo cụm sự kiện. Các chiều liên quan nhau nhưng chưa xác định được chuỗi nhân quả hoàn chỉnh.

Kỳ chính: **27/01/2023–31/03/2026**. H1: 13 snapshot cuối quý Q1/2023–Q1/2026. Q2/Q3-2026 đã được nhóm loại khỏi phạm vi; không còn gọi là hai quý thiếu trong kỳ chính, cũng không tuyên bố có 15 full snapshots.

H2 primary matched comparison: **01/02–31/12/2024**, USDC debt và đúng một collateral WETH hoặc WBTC. Extended sensitivity mới: 01/02/2024–31/03/2026. H3 có target clock 5 phút cho kỳ chính, nhưng test/common support là một tập con có biến hợp lệ.

**H1/H2/H3 là ba giả thuyết của bài; số RQ1–RQ7 vẫn giữ nguyên. H3 tương ứng RQ4, trước đây từng gọi H4. RQ3 về recursive leverage hoàn toàn khác H3.**

| RQ dự án | Nội dung | Vai trò trong bài đề xuất |
|---|---|---|
| RQ1 | ETH/BTC shock và bước nhảy rủi ro | H1, kết quả chính về static stress |
| RQ2 | Concentration ví/token/protocol | H2, kết quả chính trên matched sample |
| RQ3 | Recursive leverage và vulnerability | Phân tích bổ sung; temporal labels |
| RQ4 | Clustering/self-excitation theo thời gian | H3, kết quả dự báo có điều kiện |
| RQ5 | Cross-protocol exposure | Phụ lục mạng mẫu; chưa xác định contagion |
| RQ6 | Cascade và phản hồi giá nhiều vòng | Phụ lục sensitivity/mô phỏng |
| RQ7 | Close factor/bonus/LT và policy sensitivity | Phụ lục; không khuyến nghị policy tối ưu |

## 2. Ba giả thuyết và quyết định diễn giải

**H1:** Khi ETH/BTC giảm giá, mức nợ đủ điều kiện thanh lý tăng theo dạng phi tuyến; vị trí bước nhảy thay đổi theo phân bố vị thế cuối quý. Bằng chứng hiện tại là mô phỏng tĩnh có điều kiện, chưa là kiểm định ngưỡng thị trường bằng liquidation flow.

**H2:** Giá trị thanh lý tập trung ở một nhóm nhỏ địa chỉ và mức tập trung khác nhau giữa các protocol trong cùng kỳ/token/định nghĩa đo lường. Có bằng chứng mô tả trong mẫu; chưa có kết luận xếp hạng toàn hệ thống hay causal effect của thiết kế protocol.

**H3:** Lịch sử thanh lý có thêm thông tin dự báo sau khi kiểm soát biến thị trường và hoạt động giao thức. Có tín hiệu log-score ngoài mẫu trong lượt thăm dò; residual và mean-count calibration chưa đạt. Chưa chấp nhận giả thuyết cấu trúc “thanh lý gây ra thanh lý” bằng kết quả này.

Literature chính và nguồn gốc ý tưởng: Heimbach–Huang2024 [L7] cho borrower risk; OECD2023 [L8] cho matched liquidation comparisons; Qin2021 [L2] cho mechanisms; Hawkes1971 [M1] cho excitation framework. Xem TAI_LIEU_THAM_KHAO.md để lấy link và phân biệt phần đã đọc với metadata.

## 3. Data và đơn vị quan sát

- Ethereum event history + historical contract state/cấu hình; giữ snapshot borrower universe đúng thời điểm, chỉ nhận full gate, kiểm tra HF và aggregate debt.
- Episode thanh lý được phân biệt với event log, transaction, loan, wallet và collateral leg. Một địa chỉ chưa chắc là một chủ sở hữu.
- Episode trong kho H2 trước 01/04/2026: **30,141**, theo protocol: `{'aave_v3': 24300, 'compound_v3_usdc': 1335, 'morpho_blue': 4506}`. Đây là toàn episode trong scope thời gian của kho, khác matched USDC/WETH-WBTC và khác target Aave của H3.
- H3: **334.080 bins 5 phút** trên clock; target tổng **24.300 events**. Test common support **78.643 bins / 10.448 events**, không dùng tổng clock làm N test.
- Activity controls kỳ chính: Borrow 734.504; Repay 580.318; Supply 1.263.666; Withdraw 1.001.219. Counts hoạt động chưa phải outstanding debt, TVL hay HF queue.
- Kraken USDC/USD: **7,264 matched events** trong sensitivity mở rộng, 7,149 giá ≤60s, 7,259 ≤300s, 7,262 định giá được ≤3.600s. Một trang gap giữ raw nhưng quarantine khỏi coverage; còn 3.638/3.639 timestamp windows đã xác minh. Không peg-impute.
- Độ trễ giá 5s và hoạt động 30s là giả định khả dụng, chưa phải receipt timestamps đo thực. Quote event-targeted không được đưa vào H3 như toàn clock.
- Giữ dữ liệu/kết quả cũ riêng. Các bảng legacy RQ2/4/7 có thể dùng kỳ dài hơn; không ghép chúng vào bài như cùng primary sample.

## 4. Method H1: borrower risk và static stress

Với ví i tại quý q: `HF_i = sum_j(C_ij × P_j × LT_ij) / risk_debt_i`. Giá, số dư và LT/e-mode lấy theo snapshot. Risk debt có thể khác repayable debt trong accounting; giữ định nghĩa của implementation, không thay tùy ý.

Áp shock s cho ETH-only, BTC-only hoặc joint. Cả collateral và debt thuộc factor đều được định giá lại. Hai mapping: factor-family 1:1 và chỉ WETH/WBTC trực tiếp; mapping derivative là sensitivity, chưa phải basis/depeg đo thực.

Đầu ra: số ví HF<1, eligible risk debt USD và `eligible_debt_after_shock / total_debt_after_shock`. Bổ sung mẫu số tổng nợ trước shock, newly eligible loại ví đã HF<1 ban đầu. Nợ eligible là stock có thể bị thanh lý, chưa phải USD đã bán, realized volume hoặc bad debt.

Shock 0–60%, bước chính 1 điểm %, sensitivity 2/5 điểm %. Piecewise linear knot mô tả đường stress; largest-USD-jump là chênh lệch hai điểm grid kế nhau, khác knot. Leave-one-quarter-out chỉ đo độ ổn định; các grid points phụ thuộc nhau, không đem làm quan sát iid để tính p-value.

**Finding:** joint/factor-family/1% grid có share-knot từ **14% đến 34%**. Tại shock20%, eligible-debt share từ **0.58% đến 7.00%** trên 13 quý. Không có một ngưỡng liquidation cascade chung được xác định từ những con số này.

## 5. Method và kết quả H2: đo concentration đúng support

Nối Comet absorption với collateral legs, xử lý credit correction/principal rounding bằng khoảng lower/upper của nợ hấp thụ. Bộ trước có 1.381/1.381 Comet episodes khớp state interval và 2.115 collateral legs, không còn missing collateral trong episode; đây không phải exact trace mọi implementation upgrade.

`basePaidOut` chưa đồng nghĩa debt repaid của Aave. Credit correction khoảng 6,24% tổng basePaidOut là chênh lệch đo lường, chưa là giảm rủi ro. Ràng buộc một collateral giúp tránh nhân đôi nợ khi có nhiều legs; không cộng USD giữa protocol nếu khái niệm khác nhau. Aave mới còn giới hạn extra deficit writeoffs.

Với trọng số w_i, share p_i=w_i/sum w, `HHI=sum p_i²`; chuẩn hóa `(HHI-1/N)/(1-1/N)` khi N>1. N=1 giữ NA. Báo thêm Gini chuẩn hóa, effective-entity fraction, Top1% share, N ví/events và giá trị. Native USDC không giả định peg; USD/count-priced phải cùng support. So count full, native full và priced subset để thấy selection.

Giá market ghép strictly-as-of theo độ trễ giả định; sensitivity 60/300/3.600s. Oracle-market common support dùng cả hai loại giá trên cùng event; oracle age gate vẫn phải khai báo (26h cho bảng common mới). Nới age gate không biến oracle cũ thành thị trường mới. 199 day-cluster bootstrap và loại top ví có trong output repair; **không chuyển khoảng bootstrap của support cũ sang bảng market mới**.

Kết quả **01/02–31/12/2024, WETH collateral/USDC debt, market age≤300s**:

| Protocol | Events có giá | Ví | HHI chuẩn hóa | Top1% ví share theo USD |
|---|---:|---:|---:|---:|
| aave_v3 | 1102 | 519 | 0.09951 | 55.99% |
| compound_v3_usdc | 158 | 151 | 0.35114 | 67.99% |
| morpho_blue | 2 | 2 | 0.70887 | 92.10% |

Comet có concentration theo giá trị cao hơn Aave trong mẫu này. Morpho chỉ 2 events/2 ví nên không dùng xếp hạng toàn protocol. Chưa có kiểm định suy luận mới cho chênh lệch HHI giữa protocol.

## 6. Method và kết quả H3: dự báo cụm, không nhận diện nhân quả

Lượt Hawkes trước: baseline + market controls và self-history so đối chứng cùng covariates/common bins. Giữ block ties bằng binned counts; không jitter để tạo thứ tự giả. Mean-count explosion của exponential NB được lưu như model failure, không che bằng clipping.

Lượt mới dùng **hurdle** bổ sung: `q_t=logistic(X_t beta)`, positive count theo `NB(mu_t,r)` truncate tại zero, `mu_t=softplus(X_t gamma)`. `P(Y=0)=1-q`, `P(Y=k>0)=q NB(k)/(1-NB(0))`; `E[Y]=q mu/(1-NB(0))`. Đây chưa phải structural Hawkes, không có branching ratio để diễn giải từ fit này.

So bốn spec: constant; oracle+sampled gas; thêm 5 activity controls prior24h; thêm liquidation history strictly-lagged với half-life 0,25h/2h/168h. Gas là quan sát ở block nguồn, chưa phải median gas từng bin. Khoảng missing giữ mask, ACF không nối qua gap. Quarterly HF không nội suy thành minute features.

Train trước 2025 (warm-up7 ngày), validation 01–06/2025; ridge 0,0001/0,001/0,01 chọn bằng validation log-score và count-ratio screen0,5–2. Refit train+validation; test 01/07/2025–31/03/2026. Model rejected ở validation vẫn hiển thị để đối chứng. Rolling refit trước từng quý Q3/2025, Q4/2025, Q1/2026. Test đã từng được xem, không gọi là untouched confirmatory holdout.

| Spec | Test log-score | Expected/observed | Event Brier |
|---|---:|---:|---:|
| constant | -13296.50 | 0.412 | 0.02425 |
| market | -11559.43 | 0.945 | 0.02284 |
| activity | -11352.57 | 1.538 | 0.02267 |
| activity_history | -11070.52 | 1.460 | 0.02252 |

Validation chọn **activity_history**. Log-score tốt hơn market-only trong cùng family/common support nhưng expected count cao hơn quan sát khoảng46%. PIT randomized kiểm tra uniformity và within-segment ACF bằng 499 iid-uniform Monte Carlo: **KS p=0,02; ACF p=0,002**, vẫn bác bỏ calibration ở5%. Procedure khác bootstrap model trước nên không so p-value như cùng phép kiểm định. So sánh frozen fits trên cùng test nằm ở H3_common_test.csv; training assumptions khác nhau nên chưa gán gain riêng cho một covariate.

Thông điệp phù hợp: “Recent liquidation history retains predictive information in exploratory conditional models, while residual dependence and count miscalibration remain.” Chưa được viết “we identify causal liquidation contagion” hoặc “model forecasts systemic crashes accurately”.

## 7. Các RQ bổ sung: phương pháp và số liệu có thể đưa appendix

### RQ3 — recursive leverage

Đối chiếu định nghĩa margin trading của Chiu–Danisman2026 [L6]. Temporal motif 24h có evidence available trước snapshot 02/02/2025 23:59:47 UTC; verified mode riêng cho receipt-based evidence. Nearest-neighbor matching không lặp control trên log1p debt, HF capped10, ETH/BTC collateral shares; caliper0,75 trên standardized distance; outcome liquidated trong7 ngày. Penalized logistic là association; paired bootstrap300 giữ matching cố định. Temporal motif chưa chứng minh cash flow mượn→swap→gửi lại, chưa là exact replication của Chiu–Danisman2026.

Treated trong snapshot **3,863**, **3,656 cặp**, unmatched207. Chênh risk thanh lý7 ngày **1.532 điểm phần trăm**, bootstrap95% **[0.697; 2.477] điểm phần trăm**. Stress eligibility difference khoảng2,352 điểm phần trăm ở joint20%. |SMD| bốn biến sau matching <0,014. Chưa là causal treatment effect; controls không thấy motif chưa chứng minh không có leverage; còn confounding, selection và fixed-match uncertainty.

### RQ5 — mạng exposure mẫu

Snapshot đồng bộ block21.762.264; **69 ví,188 valued edges,10 unpriced rows**. Mạng ví–protocol–asset, shared borrowing và co-exposure sensitivity; chưa đặt default/recovery rate giả. Mẫu có 1 ví nợ chung Comet–Morpho, minimum shared debt khoảng12,56 triệuUSD; Aave pairs không thấy shared debt trong mẫu. Zero ở mạng mẫu chưa chứng minh không có kênh lây lan trên toàn thị trường. Không gọi overlap là direct inter-protocol claim.

### RQ6 — cascade sensitivity

Đối chiếu cơ chế feedback với Warmuz2022/2023 [L3], Lehar–Parlour2022 [L4] và Chiu et al.2023 [L5]; nhóm chưa replicate identification/structural model của các bài. Engine stylized cập nhật collateral/debt/HF nhiều vòng, chọn collateral lớn nhất và repay proportional debt basket; closefactor0,5,bonus5%,gas20USD,DEXfee0,3%,depth100triệuUSD,impact coefficient0,05,cap0,8,pass-through1,sellfraction1,max200rounds. Impact là `min(cap, coefficient sqrt(cumulative_sale/depth))`. Chỉ thực thi action có lợi nhuận dương, kiểm tra số dư không âm và debt không tăng. Dừng khi hết eligible, hết profitable hoặc round limit; dừng vì profitability chưa là cân bằng hệ thống.

So zero-impact cùng snapshot/financial assumptions:

| Joint shock | Repaid có impact, triệuUSD | Zero-impact, triệuUSD | Tỷ số |
|---|---:|---:|---:|
| 10% | 148.97 | 77.64 | 1.919 |
| 20% | 604.18 | 385.26 | 1.568 |
| 30% | 1307.04 | 918.77 | 1.423 |

Đây là amplification của kịch bản giả định, chưa phải hệ số quan sát. Terminal collateral shortfall chưa đồng nghĩa bad debt on-chain. Engine pair/route mới trong research_h124/cascade dùng giả định và tập dữ liệu khác; không ghép bảng hai engine. Actual-path diagnostic đã có nhưng end_to_end_validated=false; đường oracle thực có thể chứa feedback. Chưa calibrated cả cascade.

### RQ7 — policy grid

81 scenarios:3 shocks ×3 closefactors ×3 bonuses ×3LTshifts. Pareto screen giữ mục tiêu shortfall/seized/impact có điều kiện trên engine. Chưa được viết “tìm tham số tối ưu cho Aave thực tế”; thiếu borrower response, exact contract execution và external validation.

## 8. Đóng góp có thể trình bày

1. Đo vulnerability trên 13 quarter-end borrower censuses cùng cấu hình thời điểm và đối chiếu HF/debt; không phải daily panel của toàn lịch sử.
2. Chỉ ra so concentration cần debt semantics, matched token/time, age/coverage và N; nguồn USDC độc lập cải thiện priced coverage thay vì chỉ nới oracle freshness.
3. Đánh giá predictive dependence bằng no-history comparators, chronological/rolling tests và công bố residual failures. Technical validity chưa bảo đảm model adequacy.
4. Dashboard tương tác hỗ trợ đọc scope, sensitivity và evidence; chưa là validated systemic early-warning system real-time.

## 9. Bố cục manuscript và bộ bảng/hình

| Phần bài | Nguyên liệu |
|---|---|
| Abstract | 13 quarters; matched H2; test10.448 events; findings có điều kiện; residual chưa đạt |
| Introduction | Vị thế→eligible debt→execution→price feedback; ba thứ đo khác nhau; nghiên cứu không nhận diện toàn chuỗi |
| Literature | Đọc TAI_LIEU_THAM_KHAO.md; phân biệt empirical, theoretical, protocol docs |
| Data | Protocol/deployment, kỳ/token, event/episode/leg/wallet/bin, universe/cấu hình, masks, source access |
| Methods | HF/stress; normalized concentration; Hawkes comparator/hurdle; tests và sensitivity |
| Results | Bảng1 scope; bảng2 H1 theoquý; bảng3 H2 matched; bảng4 H3/common-test; bảng5 residual/rolling |
| Discussion | Stock vs flow; selective freshness; address ownership; confounding; post-selection; failed calibration |
| Appendix | RQ3 matching; RQ5 sampled network; RQ6/7 scenarios; source quarantine; hash/audit |

Hình đề xuất: (1)13 đường H1 share-vs-shock hoặc heatmap quý×shock; (2)H2 concentration cạnh coverage/N cho từng token, không chỉ raw HHI; (3)H3 probability reliability chart và rolling log-score, thêm expected/observed; (4)cascade có/không feedback với nhãn stylized. CSV đã xuất trong evidence/; chưa tạo interval/error bars chưa có trong output.

## 10. Checklist trước khi nộp

- Không trộn primary endQ1/2026 với legacy endQ3/2026. Ghi rõ denominator, debt semantics, price/support và N ở mỗi bảng.
- Không dùng snapshot1–2ví như full; không coi13quarter snapshots là minute risk history.
- Không tuyên bố universal shock threshold, verified recursive leverage toàn bộ, causal contagion hoặc calibrated forecast.
- Không dùng p-value/CI của support hoặc procedure khác; H2 market bảng mới chưa có interval bootstrap riêng.
- Nếu muốn bài confirmatory mạnh hơn: future independent holdout, high-frequency HF/TVL/DEX series, validated cash-flow motifs và end-to-end execution backtest là phần còn cần. Không tự bịa chúng để hoàn thiện bản thảo.
- Đối chiếu citations và phiên bản SSRN; không dùng con số tác giả khác như kết quả dự án. Các sources dùng tài khoản/trả phí chưa được sử dụng.

## 11. Tái lập và truy vết

`evidence/` chứa bản sao bảng/JSON được dùng, `provenance.json` chỉ đến source và SHA256. `HUONG_DAN_CHAY.md` hướng dẫn3file. `checksums.json` bảo vệ toàn bộ pack. Audit mới xác minh40file legacy đã khóa; giữ dữ liệu/kết quả mô hình cũ. Source package chưa chứa toàn bộ raw dataset; dataset phải cấp riêng theo đường dẫn cấu hình.
