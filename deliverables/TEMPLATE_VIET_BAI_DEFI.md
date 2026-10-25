# Khung cố định để viết bài nghiên cứu DeFi lending

Khung này là phần bổ sung cho file nguyên liệu, dùng để triển khai một manuscript tập trung H1, H2 và H3. Giữ nguyên năm phần và thứ tự dưới đây. Nội dung trong dấu ngoặc vuông là chỗ cần điền hoặc kiểm tra trước khi nộp. Mẫu câu tiếng Anh là gợi ý diễn đạt, không phải kết quả mới.

H1 là price shock vulnerability theo quý; H2 là liquidation concentration; H3 là conditional temporal clustering, tương ứng RQ4 của dự án. RQ3 về recursive leverage là nội dung khác, có thể đưa vào phụ lục hoặc discussion bổ sung. Các giả thuyết dưới đây đang được diễn đạt sau những lượt phân tích đã thực hiện, không được mô tả là preregistered hypotheses.

## 1 Introduction

**Mục tiêu:** nêu vấn đề, lý do nghiên cứu, câu hỏi, đóng góp và kết quả chính. Chưa đưa toàn bộ phương trình hay tổng quan từng bài vào phần này.

**Đoạn 1 — Bối cảnh và vấn đề kinh tế.** Giới thiệu DeFi lending, collateralization và liquidation như cơ chế bảo vệ khả năng thanh toán. Chỉ ra vì sao cơ chế này có thể tạo vulnerability khi giá giảm hoặc thanh khoản giao dịch hạn chế. Dẫn nguồn cơ chế từ Qin et al.2021 và tài liệu protocol; nếu dùng quy mô thị trường hiện tại, điền số liệu có nguồn và ngày đo, không tái sử dụng một con số TVL đã cũ.

Mẫu mở đoạn: “Collateralized lending protocols rely on rule-based liquidations to manage borrower risk. Their resilience nevertheless depends on the distribution of borrower positions and the conditions under which collateral can be sold.”

**Đoạn 2 — Vấn đề nghiên cứu cụ thể.** Phân biệt ba đại lượng: stock nợ đủ điều kiện thanh lý khi stress; concentration của liquidation events đã quan sát; khả năng dự báo các cụm theo thời gian. Giải thích rằng một đại lượng không tự chứng minh hai đại lượng còn lại.

**Đoạn 3 — Khoảng trống và phạm vi.** Tóm tắt điều literature đã làm rồi nêu phần nhóm bổ sung: borrower snapshots đúng thời điểm, matched cross-protocol measurement và conditional prediction có diagnostics. Dùng “we complement” hoặc “we extend the analysis to [scope]”; chỉ dùng “the first” sau khi có systematic literature review chứng minh.

**Đoạn 4 — Mục tiêu và dữ liệu.** Nêu ba câu hỏi của bài và kỳ nghiên cứu 27/01/2023–31/03/2026; H1 có13 quarter-end snapshots; H2 chính là01/02–31/12/2024 với USDC debt và WETH/WBTC collateral; H3 test01/07/2025–31/03/2026. Không trình bày tất cả phần này như cùng một sample.

**Đoạn 5 — Đóng góp và findings chính.** Điền ba đóng góp đi cùng ba kết quả: [H1 conditional stress finding]; [H2 matched-sample concentration finding]; [H3 predictive improvement và calibration limitation]. Có thể dùng range H1, HHI H2 và log-score H3 từ dossier, nhưng phải giữ điều kiện đo và tránh dồn quá nhiều số vào một câu.

**Đoạn 6 — Cấu trúc bài.** Viết một câu giới thiệu Sections2–5 theo đúng khung cố định. Kết thúc introduction bằng nội dung này, không lặp một abstract thứ hai.

## 2 Literature Review

### 2.1 Theoretical Framework

**Mục tiêu:** giải thích cơ chế kinh tế dẫn tới giả thuyết. Đây là framework lý thuyết khái niệm; nhóm chưa ước lượng một structural equilibrium model của literature.

**Cơ chế cho H1.** Overcollateralization và liquidation thresholds tạo các ranh giới HF theo ví. Khi giá collateral/debt thay đổi, các ví vượt ranh giới khác nhau; sự tập trung quanh ngưỡng có thể tạo bước nhảy trong eligible debt. Đối chiếu HF/debt-at-risk với Heimbach–Huang2024 và cơ chế liquidation với Qin et al.2021.

**Cơ chế cho H2.** Quy mô khoản vay, phân bố borrower exposures và liquidation design có thể dẫn tới lượng thanh lý tập trung theo địa chỉ. Giải thích tại sao USD weights, event counts và native token amounts đo những khía cạnh khác nhau. Không suy ra một protocol rủi ro hơn chỉ từ HHI lớn hơn mà chưa xét support và quy mô.

**Cơ chế cho H3.** Giá chung và điều kiện thị trường có thể làm nhiều ví cùng bị thanh lý. Collateral sales và constraints thực thi có thể tạo feedback, nhưng lịch sử sự kiện dự báo sự kiện tiếp theo cũng có thể do omitted common factors. Phân biệt common-shock clustering với causal self-excitation; dùng Lehar–Parlour2022, Warmuz et al.2022/2023 và Chiu et al.2023 để thảo luận cơ chế.

**Sơ đồ lập luận cần giữ:** borrower exposure và cấu hình → shock giá → liquidation eligibility → execution có điều kiện → khả năng feedback giá. Dự án đo những đoạn khác nhau của chuỗi, chưa nhận diện toàn bộ chuỗi nhân quả.

### 2.2 Empirical Framework

**Mục tiêu:** tổng hợp cách literature đo lường và nhận diện bằng chứng, rồi xác định lựa chọn thực nghiệm của bài. Không biến mục này thành danh sách abstract hoặc chỉ liệt kê tác giả.

**Nhóm bằng chứng 1 — Vị thế và leverage.** So sánh protocol vintage, daily panel với quarterly snapshots, borrower universe, thời điểm cấu hình và HF bands. Dùng BIS WP1171; nếu thảo luận recursive leverage, dùng Chiu–Danisman2026 và phân biệt temporal candidates của nhóm với cash-flow verification của một motif borrow–swap–resupply–borrow.

**Nhóm bằng chứng 2 — Liquidations và liquidity.** So sánh event/episode/transaction, debt absorbed với debt repaid, collateral legs và matched token/time samples. Dùng Qin et al.2021, OECD2023 và Lehar–Parlour2022. Nêu vì sao lựa chọn age gate và pricing support ảnh hưởng concentration; không thừa hưởng IV identification từ một bài chỉ vì dùng cùng dữ liệu on-chain.

**Nhóm bằng chứng 3 — Clustering và prediction.** Trình bày ý tưởng Hawkes từ Hawkes1971; đối chiếu market-controlled comparator, binned timestamps, chronological holdout, rolling và residual. Nguồn SSRN6508318 chỉ đưa vào như literature chính sau khi xác minh đúng authors/version; hiện giữ trạng thái tham khảo cần kiểm tra.

**Đoạn tổng hợp cuối mục.** Viết “[Prior studies establish X using Y; our analysis focuses on Z with the following measurement and validation choices.]” Điền rõ điểm kế thừa, điểm khác, phần chưa replicate. Chuyển sang hypotheses bằng cơ chế và khoảng trống vừa nêu.

### 2.3 Hypothesis Development

**H1 Price shocks and borrower vulnerability.** “Under a fixed borrower snapshot, declines in ETH and BTC prices produce nonlinear changes in liquidation-eligible debt, with the location of large increases varying across quarters.”

Lập luận trước H1: vị thế có thresholds khác nhau và mass quanh ngưỡng thay đổi theo quý. Observable: stress curves, share-knot, largest USD jump và newly eligible debt. Giữ phạm vi “conditional static vulnerability”; chưa phát biểu H1 bằng realized liquidation volume vì mô hình hiện đo stock.

**H2 Liquidation concentration.** “Liquidation debt value is unevenly distributed across borrower addresses, and concentration differs across protocols within matched periods and debt–collateral token samples.”

Lập luận trước H2: heterogeneous position sizes và protocol mechanisms có thể liên quan concentration. Observable: normalized HHI/Gini, Top1% share, N/events và robustness cùng support. H2 hiện chưa gán chiều Aave lớn hơn Comet hoặc ngược lại từ trước khi xem kết quả; nếu muốn kiểm định directional hypothesis, cần lý thuyết và thiết kế xác nhận mới.

**H3 Conditional liquidation clustering.** “Lagged liquidation history contains incremental predictive information for liquidation counts after accounting for observed market conditions and protocol activity.”

Lập luận trước H3: persistent risk conditions và possible feedback có thể tạo temporal dependence. Observable: held-out log-score của no-history/history models trên cùng sample, rolling stability và residual calibration. H3 này là predictive hypothesis; chưa phải tuyên bố causal contagion hay structural branching ratio.

**Cách báo quyết định:** H1/H2 trình bày mức độ phù hợp mô tả với giả thuyết, chưa ghi statistical acceptance khi không có phép kiểm định tương ứng. Với H3, có thể báo predictive evidence đi kèm calibration failure. Không đặt giả thuyết theo chiều đã biết rồi gọi là confirmatory.

## 3 Method

### 3.1 Research Design and Data

Điền [chain/protocols], [deployment/revision], [kỳ], [đơn vị quan sát], [quy tắc inclusion/exclusion] và [nguồn]. Ghi riêng sample H1, H2, H3; trích các con số kiểm chứng trong dossier và bảng scope. Giải thích loại Q2/Q3-2026 theo phạm vi đã duyệt, không impute hai quý này.

Mô tả cách xây borrower universe đúng thời điểm, balances/configuration/e-mode, đối chiếu HF và debt; trình bày nguồn event logs, token decimals, Comet semantics, raw hashes và freeze manifests. Nêu quote latency5s/activity delay30s là giả định, cùng khoảng source gap bị quarantine. Không mô tả timestamp báo cáo như timestamp dữ liệu thị trường.

### 3.2 Variables and Measurement

Định nghĩa HF, collateral/debt value, liquidation eligibility, episode, wallet address, normalized HHI/Gini, price age, activity counts và target count5 phút. Với mỗi biến ghi đơn vị, timestamp khả dụng, mẫu số, treatment of missing data và proxy assumptions. Phân biệt risk debt, repayable debt, observed repaid/absorbed value và simulated shortfall.

### 3.3 H1 Static Stress Design

Trình bày công thức HF từ phần nguyên liệu, shock ETH/BTC/joint0–60%, grid1% và sensitivity2/5%, hai factor mappings. Báo denominator trước/sau shock, already/newly eligible, knot và largest jump. Nêu quarter-end census chưa là minute panel; deterministic grid rows chưa là iid observations để tính p-value.

### 3.4 H2 Matched Concentration Design

Trình bày matched period/token và one-collateral rule, cách gán Comet collateral/debt và uncertainty lower/upper. So count/native full với priced subset; age60/300/3600s; oracle/market common support. Báo N, coverage, normalized metrics, top-wallet exclusions và bootstrap theo support có sẵn. Không tái dùng interval của support cũ cho bảng market mới.

### 3.5 H3 Conditional Prediction Design

Trình bày market/activity/history specifications, no-history comparators và phương trình hurdle; nếu dùng Hawkes cũ phải mô tả riêng family/assumptions. Nêu warm-up, train/validation/test, ridge selection, train-only scaling, rolling refit và common mask. Test mới nhất có78.643bins/10.448events; lịch test đã từng được xem nên analysis vẫn exploratory.

Dùng log-score, expected/observed count, Brier, rolling và randomized PIT KS/ACF. Ghi số replications và null procedure. Không so raw likelihood khác sample; không gán event-targeted quotes cho toàn clock hoặc nội suy quarterly HF thành high-frequency controls.

### 3.6 Robustness and Reproducibility

Liệt kê grid/mapping/denominator sensitivity H1; token/price age/support/large-wallet sensitivity H2; market controls/no-history/rolling/residual H3. Dẫn file code, config, seed, package versions và source/result hashes. Báo rõ kiểm tra nào đã chạy, kiểm tra nào còn thiếu. RQ3/5/6/7 bổ sung ghi scope riêng nếu đưa appendix.

## 4 Findings

### 4.1 Sample and Measurement Quality

Trước khi trình bày hiệu ứng, báo13full snapshots, event/sample counts, price coverage, Comet correction và missing-source windows. Gợi ý Table1 là scope/coverage; dùng N đúng denominator của từng bảng. Giải thích các sample không tương đương thay vì ghép thành một total duy nhất.

### 4.2 H1 Results

Theo thứ tự: [hình stress curves/heatmap] → [knot và USD-jump theo quý] → [joint20% share] → [mapping/denominator/newly-eligible sensitivity]. Con số có sẵn: share-knot14–34%, eligible share ởjoint20% khoảng0,58–7,00% trên13quý. Gắn điều kiện factor-family/grid1% và gọi là mô phỏng tĩnh, không phải realized cascade threshold.

Mẫu đoạn: “Across the thirteen quarter-end snapshots, [metric] ranges from [value] to [value] under [assumptions]. This variation is consistent with differences in borrower exposure and threshold distributions, rather than a single market-wide liquidation threshold.”

### 4.3 H2 Results

Theo thứ tự: [matched coverage] → [count/native vs USD] → [normalized concentration] → [token/age/top-wallet robustness]. Ví dụ WETH/USDC năm2024, market≤300s: Aave normalized HHI≈0,09951; Comet≈0,35114. Ghi N519/151ví và1102/158events; Morpho chỉ2events nên chưa xếp hạng chung. Chỉ viết chênh lệch trong sample được nêu.

Mẫu đoạn: “Within the matched [period/token] sample, [protocol A] exhibits higher value-weighted concentration than [protocol B]. The comparison remains conditional on the observed address population and the pricing support.” Chỉ thêm “robust” hoặc “statistically significant” nếu bảng kiểm tra tương ứng thực sự có.

### 4.4 H3 Results

Theo thứ tự: [validation selection] → [same-test comparison] → [count/probability calibration] → [rolling/residual] → [đánh giá H3]. Mô hình activity_history được validation chọn có log-score≈−11.070,52 so market≈−11.559,43; expected/observed≈1,460; PIT KS p0,02 và ACF p0,002. Điểm log-score tốt hơn chưa đồng nghĩa calibration đạt.

Mẫu đoạn: “Lagged liquidation history improves the exploratory predictive score relative to [comparator] on the same test support. However, the selected model overpredicts aggregate counts and fails residual diagnostics, limiting its use as a calibrated forecasting model.”

### 4.5 Discussion and Hypothesis Assessment

Tổng hợp ba câu trả lời riêng, đối chiếu literature và giải thích measurement sensitivity. Phân biệt result, interpretation và limitation trong mỗi đoạn. RQ3 matching hoặc cascade sensitivity chỉ bổ sung cơ chế dưới các giả định, không dùng để nâng predictive association thành nhân quả. Discussion đặt trong Findings để giữ cấu trúc năm phần.

## 5 Conclusion

**Đoạn 1 — Trả lời câu hỏi nghiên cứu.** Tóm tắt H1 vulnerability thay đổi theo quý; H2 concentration trong matched support; H3 predictive information có điều kiện nhưng calibration chưa đạt. Chỉ nhắc1–2con số quan trọng nếu cần, không lặp nguyên bảng.

**Đoạn 2 — Đóng góp và ý nghĩa.** Nêu đóng góp đo lường borrower risk, comparability và model validation; hàm ý theo dõi exposure, coverage và diagnostics. Không đề xuất optimal protocol parameters hay systemic warning accuracy từ engine chưa calibrated.

**Đoạn 3 — Giới hạn.** Nêu quarter-end frequency, address ownership, semantic/pricing support, omitted high-frequency HF/TVL/DEX variables, exploratory test reuse và residual failure. Giới hạn phải tương ứng trực tiếp với điều bài muốn kết luận.

**Đoạn 4 — Hướng phát triển.** Đề xuất future independent holdout, verified recursive cash flows, synchronized broader exposure sample và end-to-end cascade calibration. Không ghi các việc này là đã hoàn thành.

Mẫu kết đoạn: “The results support a measurement-aware assessment of DeFi lending risk. They do not yet establish causal liquidation contagion or a fully calibrated systemic forecasting model.”

## Quy tắc dùng template

Giữ đúng năm phần; References và phụ lục đặt sau Conclusion, không xem là phần nội dung thứ sáu. Abstract/title/keywords chỉ thêm khi quy định nộp bài yêu cầu. Dùng nhất quán nhãn H1/H2/H3, đơn vị, period và definitions; không đổi nhãn RQ3 thành H3. Trước khi nộp, xóa toàn bộ hướng dẫn và placeholders, kiểm tra lại citations, N, versions và statements theo bảng nguồn.
