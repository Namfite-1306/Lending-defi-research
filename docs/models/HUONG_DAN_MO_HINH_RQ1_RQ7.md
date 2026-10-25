# Mô hình RQ1–RQ7 và hướng dẫn chạy bộ code đã hợp nhất

Ngày cập nhật: 23/10/2026. Repository chính dùng cho đợt tích hợp:
`E:/OneDrive/Documents/GitHub/Clone/Lending-defi-research`.

## 1. Ba file giao cho thành viên và kiến trúc thống nhất

| File | Phần tính toán thật | Lệnh module |
|---|---|---|
| `defi_models/rq6.py` | Engine cascade nhiều vòng, profitability, market/oracle impact, đối chứng zero-impact | `python -m defi_models.rq6` |
| `defi_models/rq3.py` | Nhãn leverage, matching, outcome 7 ngày, bootstrap và logistic | `python -m defi_models.rq3` |
| `defi_models/rq2_rq5.py` | Concentration RQ2 và mạng exposure RQ5 | `python -m defi_models.rq2_rq5` |

Đây là ba module có thuật toán, không chỉ là wrapper gọi chương trình khác. Chúng dùng chung các thành phần `core.py`, `statistics.py`, `member_cli.py` và `__main__.py`. Chạy từng file, module hoặc bộ all đều đi qua cùng gate dữ liệu, cấu hình và cơ chế ghi manifest. Các import cũ từ `analyses.py`/`simulation.py` vẫn hoạt động, gồm cả live dashboard.

Ba file phải nằm trong package `defi_models` của repository hoặc gói ZIP bàn giao. Không chép riêng một file sang máy khác rồi kỳ vọng nó tự có các module chung và dữ liệu. Gói bàn giao kèm code dùng chung, cấu hình và requirements; database nghiên cứu được chuyển riêng.

Không viết thuật toán lần hai trong file xuất để tránh lệch kết quả khi sửa main. File `rq6.py` cũng là engine RQ7 đang gọi. File `rq3.py` và `rq2_rq5.py` chính là các hàm registry all đang gọi.

## 2. Các lỗi thành viên đã được sửa

1. `rq7_policy_sensitivity.py` không còn xác định ROOT lệch lên thư mục cha. Nó gọi exporter trong package chính và bắt buộc truyền `--run`.
2. Không tự chọn `policy_grid.csv` mới nhất theo modification time. Exporter đọc đúng run, đối chiếu config/manifest/grid và kiểm tra run đã hoàn tất.
3. Bỏ các số nhận xét ghi cứng và khuyến nghị tham số Aave chưa được chứng minh. Số trong bảng và nhận xét tối thiểu shortfall được tính từ CSV hiện tại.
4. Giữ các cờ `reached_round_limit`, `pareto_evaluable`, `pareto_nondominated`, `incomplete_dynamics` và ví còn HF<1. Pareto để trống do hết vòng không bị đổi thành kết luận “bị trội”.
5. Báo rõ số ví và block snapshot; dữ liệu mẫu không được trình bày như full-market. Mẫu 5 ví upload cũ được giữ nguyên để truy vết, không dùng làm bộ kết quả mới.
6. Tăng LT được mô tả đúng chiều HF; collateral seized không gọi là mất mát ròng; shortfall không gọi là bad debt on-chain.
7. Test RQ7 dùng fixture tạm độc lập, được chạy trong `tests/`. Entry test cũ ở root trỏ tới cùng test mới, không cần output tạo trước.
8. Thêm cấu hình tham chiếu `configs/models.reference.json`, giữ `max_rounds=200`. Không đổi nội dung data freeze hoặc ép audit thành đạt.

Sau khi chạy RQ7 thành công bằng main, báo cáo tự được xuất tại `RUN/rq7/policy_report/`. Chạy lại exporter phải chọn output mới, tránh ghi đè.

## 3. Dữ liệu và các khái niệm chung

Lịch sử hiện dùng: từ 27/01/2023 đến hết 30/09/2026 UTC. Dataset đầy đủ trên máy hiện tại:

```text
C:/Users/HAI NAM/Finance1/defi-research/data/runs/recovery_20261020
```

Clone ở E: không kèm dataset này. Chạy phải truyền `--data-run` hoặc chuyển riêng cả folder giữ nguyên cấu trúc. Không có data thì gate phải báo thiếu, không tự sinh dữ liệu thay thế.

Snapshot vị thế dùng cho RQ1/RQ3/RQ6/RQ7: block 21762264, trước stress 03/02/2025. Đã quét 32.847 ví borrower lịch sử, có 17.084 ví còn nợ, tất cả qua validation. Nợ theo adapter khoảng 11,114 tỷ USD. Snapshot đầy đủ tại một block không có nghĩa có panel toàn bộ thị trường tại mọi ngày.

Health factor cơ bản:

```text
HF_i = tổng_j(collateral_value_ij × effective_LT_ij) / tổng_j(risk_debt_value_ij)
```

LT là liquidation threshold theo token/chế độ E-mode ở thời điểm snapshot. HF<1 chỉ là điều kiện rủi ro; chưa bảo đảm thanh lý sinh lời hoặc đã thực thi. Model nền giữ quy tắc làm tròn theo revision để đối chiếu HF. Stress/cascade vẫn không phải bản sao giao dịch Solidity.

Risk debt là dư nợ theo quy đổi quản trị rủi ro; repayable debt là lượng nợ cần trả theo adapter. Hai đại lượng được lưu riêng vì một số tài sản/cơ chế có thể có cách quy đổi khác nhau. Không hoán đổi tùy ý.

## 4. RQ1 — Mức giảm ETH/BTC nào tạo bước nhảy mạnh?

**Đầu vào:** `full_snapshot_21762264/positions.csv`, `validation.csv`, `scope.json`; mapping nhóm ETH/BTC trong config.

**Mô hình 1: stress tĩnh có xét hai phía bảng cân đối.** Quét mức giảm giá từ 0% đến 60%, bước 1%. Chạy ETH-only, BTC-only và ETH+BTC. Các derivative trong cùng nhóm giả định biến động 1:1 với factor; không phải ước lượng depeg. Token không thuộc hai nhóm giữ giá. Cả giá trị thế chấp lẫn nợ cùng nhóm đều thay đổi. Vì vậy ví vừa vay vừa thế chấp ETH không giống ví thế chấp ETH vay stablecoin.

Mỗi mức shock tính HF, số ví HF<1, số ví mới HF<1 so với nền và risk debt đủ điều kiện. Nợ đủ điều kiện có thể giảm về USD khi giá debt token giảm; không áp đặt đường stress phải tăng đơn điệu.

**Mô hình 2: nhận diện điểm thay đổi mô tả.** Đầu tiên lấy khoảng lưới có mức tăng eligible debt lớn nhất. Sau đó fit hồi quy liên tục một điểm gãy:

```text
y(s) = a + b × s + c × max(s − k, 0)
```

Thử các nút k nội bộ và chọn SSE nhỏ nhất. Khoảng bước nhảy lớn nhất và nút hồi quy là hai tiêu chí khác nhau; không gọi chúng là cùng một ngưỡng thống kê. Chưa có kiểm định ngưỡng hay khoảng tin cậy của k.

**Đầu ra:** `stress_curve.csv`, `factor_mapping.csv`, `summary.json`. Trong bản tham chiếu, khoảng tăng lớn nhất là ETH 41–42%, BTC 47–48%, shock chung 41–42%; chỉ áp dụng cho snapshot và mapping hiện tại.

## 5. RQ2 — Thanh lý tập trung ở đâu?

**Đầu vào:** `processed/liquidations_model_table.csv`. Mỗi dòng là event log thanh lý, không phải khoản vay duy nhất. Ba protocol có semantics khác nhau nên được tính riêng.

Nhóm theo protocol, toàn kỳ/từng năm, borrower/debt token/collateral token. Code hiện chưa tính concentration theo liquidator; không đưa chỉ số này vào kết luận khi chưa bổ sung schema và tính toán tương ứng.

Chạy hai thước đo: số event và giá trị USD trên phần có giá hợp lệ. Giá phải là last-known, tuổi giá đạt chính sách; không đổi giá thiếu thành 0. USD Aave debt repaid và Comet basePaidOut không được cộng thành cùng một đại lượng thanh lý toàn hệ thống.

**Chỉ số:**

```text
share_i = weight_i / tổng weight
HHI = tổng share_i²
Gini = tổng_i tổng_j |weight_i − weight_j| / (2 × N × tổng weight)
Top1 / Top10 = tổng share của 1 / 10 thực thể lớn nhất
```

HHI/Gini/Top shares cao cho thấy tập trung hơn theo thước đo đang dùng. Gini dựa trên các thực thể xuất hiện, không bao gồm mọi ví chưa từng bị thanh lý. Code xuất danh sách Top20 để kiểm tra thực thể chi phối, giữ bucket UNKNOWN khi thiếu định danh.

**Đầu ra:** `concentration.csv`, `top_entities.csv`, `valuation_coverage.csv`, `summary.json`. USD coverage tham chiếu: Aave 85,50%, Comet 100%, Morpho 57,74%. Khi thiếu giá, kết luận USD chỉ dành cho priced subset.

## 6. RQ3 — Recursive leverage liên hệ với vulnerability thế nào?

**Đầu vào:** snapshot, bảng liquidation, lịch sử SQLite để xác định cutoff, `block_range.json`, cùng bảng nhãn leverage.

**Bước 1 — nhận diện nhóm.** `recursive_label=temporal` dùng ứng viên Borrow→Supply→Borrow trong cửa sổ 6/24/48 giờ. Chỉ sử dụng nhãn đã có `label_available_at` không muộn hơn cutoff snapshot. Không dùng sự kiện xảy ra sau đó để nhận diện nhóm trước stress. `verified` chỉ dùng nhãn verification có trước snapshot; mẫu này có thể quá nhỏ nên runner phải dừng nếu thiếu overlap.

Nhãn temporal chưa chứng minh vốn vay thực sự tài trợ collateral. Nhóm không thấy motif cũng chưa chứng minh là không dùng leverage.

**Bước 2 — nearest-neighbor matching không lặp đối chứng.** Biến match: log(1+debt), HF capped tại 10, tỷ trọng ETH collateral, tỷ trọng BTC collateral. Chuẩn hóa bằng độ lệch chuẩn của snapshot. KD-tree tìm tối đa 30 đối chứng gần nhất; greedy chọn treated có khoảng cách nhỏ trước, giới hạn caliper 0,75, mỗi control dùng một lần. Đây không phải propensity-score matching.

**Bước 3 — outcome.** `y=1` nếu ví có liquidation Aave sau snapshot trong 7 ngày. Kiểm tra data bao phủ hết horizon. So sánh trung bình chênh lệch y của từng cặp và sự khác biệt tỷ lệ đủ điều kiện sau shock chung 20%.

**Bước 4 — độ bất định và association.** Bootstrap các chênh lệch theo cặp 300 lần, seed42, lấy quantile 2,5%/97,5%. Giữ matching cố định, chưa bao gồm bất định của bước chọn nhãn/matching. Nếu outcome có hai lớp, fit logistic penalized với intercept, treated và các covariate chuẩn hóa; ridge=0,001. Hệ số là conditional association, không phải causal effect.

**Đầu ra:** `matched_pairs.csv`, `matching_balance.csv`, `summary.json`. Xem số treated không match và standardized mean difference. Tham chiếu: 3.656 cặp; risk difference khoảng +1,532 điểm phần trăm, bootstrap95% khoảng +0,697 đến +2,477 điểm. Không gọi là leverage “gây ra” mức tăng này.

## 7. RQ4 — Clustering và self-excitation theo thời gian

**Đầu vào:** liquidation table, hourly count panel và hourly ETH/BTC prices. Event timestamps phải đối chiếu đúng tổng theo giờ; không điền các khoảng coverage thiếu bằng số 0. Mặc định fit Aave V3 riêng.

**Mô hình 1 — Poisson GLM có controls.**

```text
N_hour ~ Poisson(mu_hour)
log(mu_hour) = intercept + beta × standardized_covariates
```

Covariates: absolute return ETH/BTC, phần return âm ETH/BTC, sin/cos của giờ UTC. Chia thời gian train80%/test20%; center/scale chỉ tính trên train. Optimize likelihood với ridge nhỏ, đánh giá test deviance so với constant-rate Poisson. Return cùng giờ là thông tin giải thích, không phải dự báo trước giờ.

**Mô hình 2 — Hawkes đơn biến exponential.**

```text
lambda(t) = mu + eta × beta × tổng_{t_i<t} exp[−beta × (t−t_i)]
beta = log(2) / half_life
```

mu là baseline events/giờ; eta là branching ratio; half-life thử 1 phút, 5 phút, 30 phút, 2 giờ, 6 giờ. Chọn ứng viên hội tụ có train likelihood lớn nhất rồi đánh giá chronological holdout, giữ tác động lịch sử train vào test. Event cùng timestamp block dùng cùng pre-group intensity, không jitter hoặc tự kích thích nhau trong block giả tạo.

Hawkes chưa có giá làm covariate và chưa có residual time-rescaling diagnostics. Eta cao không chứng minh contagion nhân quả. Không so trực tiếp point-process log-likelihood với hourly deviance.

**Đầu ra:** `hawkes_candidates.csv`, `hourly_predictions.csv`, `summary.json`. Bản full có 27.578 sự kiện, 32.232 giờ, half-life5 phút, eta≈0,822687. Luồng `available_rq14` vẫn giữ riêng, gắn exploratory: sử dụng mẫu/khoảng đã tải và constant Poisson không có price controls. Không xem kết quả đó là full.

## 8. RQ5 — Mạng exposure và kênh lây lan tiềm năng

**Đầu vào:** `processed/exposures_valued_sample.csv`, gồm wallet, protocol, market, asset, kind debt/collateral, value và block. Mọi dòng phải cùng block, không trùng wallet–protocol–market–asset–kind. Giá không có được đếm riêng; không giả là 0.

**Mô hình 1 — mạng exposure nhiều lớp.** Tạo cạnh wallet→protocol→market/asset, trọng số USD. Cộng debt/collateral của từng ví theo protocol. Mẫu chọn theo hoạt động, không phải mạng đầy đủ.

**Mô hình 2 — overlap và accounting sensitivity.** Với mỗi cặp protocol, đếm ví cùng có debt và tổng min(debt_A, debt_B). Với mỗi protocol nguồn, đánh dấu các ví có nợ tại đó rồi cộng nợ của chính các ví đó tại protocol đích. Đây là upper-bound exposure screen; chưa gắn probability of default, recovery rate hay hệ số truyền dẫn giả định.

**Đầu ra:** `valued_edges.csv`, `protocol_overlap.csv`, `common_wallet_sensitivity.csv`, `summary.json`. Mẫu tham chiếu có 69 ví, 188 cạnh có giá, 10 dòng chưa có giá. Có chung borrower không chứng minh protocol trực tiếp nợ nhau hoặc đã xảy ra contagion. Không thấy overlap trong mẫu không chứng minh không có ngoài thị trường.

## 9. RQ6 — Cascade thanh lý qua nhiều vòng

**Đầu vào:** snapshot cùng block và cấu hình shock/liquidity/cost. Giá trị ban đầu là balances quy đổi USD tại snapshot; engine giữ số dư tham chiếu và cập nhật theo factor giá.

**Chu trình mỗi vòng:**

1. Shock ETH/BTC theo config, cả collateral và debt; tính giá oracle sau tác động tích lũy.
2. Tính HF; chọn ví HF<1 và repayable debt còn đáng kể.
3. Chọn collateral đang có giá trị lớn nhất của ví. Amount tối đa là min(close_factor × tổng repayable debt, collateral khả dụng/(1+bonus)). Trả theo tỷ lệ basket debt, không chọn đúng debt/collateral pair như giao dịch Aave thật.
4. Tính tentative sales, phí DEX và gas. Chỉ thực thi khi profit>0. Bộ lọc profitability là batch đồng bộ nên có thể bảo thủ.
5. Giảm collateral và cả risk/repayable debt theo tỷ lệ; kiểm tra số dư không âm và nợ không tăng.
6. Cập nhật impact và quay lại đánh giá HF; dừng nếu không có eligible, không có liquidation sinh lời, hoặc hết vòng.

**Hàm tác động giá:**

```text
impact_token = min(impact_cap,
                   impact_coefficient × sqrt(cumulative_sale_reference_USD / liquidity_depth_USD))
market_factor = shock_factor × (1 − impact)
oracle_factor = shock_factor × (1 − oracle_pass_through × impact)
```

Sales dùng cùng numeraire USD tham chiếu sau initial shock, không tự đổi đơn vị depth mỗi vòng. Proceeds xét impact trung bình giữa trước/sau batch. Khi pass-through<1, giá oracle và giá thực thi không giống nhau.

Mỗi shock có một đối chứng impact_coefficient=0, giữ các giả định còn lại. Default reference: shock10/20/30%, depth100 triệu USD/token, coefficient0,05, cap80%, pass-through1, CF50%, bonus5%, gas20USD/action, fee0,3%, max200vòng.

**Đầu ra:** `cascade_scenarios.csv`, `cascade_rounds.csv`, `summary.json`. Đọc repayment, seized, profit, impact, terminal shortfall, residual eligible và stop reason. `executed_wallet_actions` không phải số giao dịch on-chain. Shortfall không phải bad debt đã ghi nhận. Engine chưa hiệu chỉnh depth/impact từ waves, chưa mô phỏng route/MEV/flash funding, fee/dust/close factor động và GHO chính xác.

## 10. RQ7 — Sensitivity và Pareto của tham số

RQ7 gọi đúng engine RQ6. Grid: shock10/20/30% × CF25/50/100% × bonus3/5/8% × LT shift−3/0/+3 điểm phần trăm =81 tổ hợp.

Trong cùng shock, A trội B nếu không lớn hơn B ở cả ba mục tiêu shortfall, seized collateral và impact, đồng thời nhỏ hơn ít nhất một mục tiêu. Các điểm không bị trội được giữ trên frontier. Không gộp shock10% với shock30% thành cùng một bảng tối ưu.

Kịch bản chạm giới hạn vòng bị loại khỏi tập đánh giá Pareto, giữ giá trị chưa đánh giá. Kịch bản hết thanh lý sinh lời nhưng còn HF<1 vẫn giữ cờ incomplete_dynamics. Chưa phản ánh phản ứng borrower khi đổi LT, chưa có validated policy replay; không khuyến nghị chính sách Aave từ frontier này.

**Đầu ra:** `policy_grid.csv`, `summary.json` và `policy_report/` gồm scenarios, sensitivity, báo cáo và export manifest. Exporter đọc đúng một run đã chọn, lưu hash nguồn, input identities, scope, code identities và cảnh báo.

## 11. Chạy trên máy hiện tại

PowerShell, trong repository E:. Dùng môi trường đã kiểm chứng ở C: để không cài lại phụ thuộc:

```powershell
Set-Location -LiteralPath 'E:\OneDrive\Documents\GitHub\Clone\Lending-defi-research'
$py = 'C:\Users\HAI NAM\Finance1\defi-research\.venv\Scripts\python.exe'
$data = 'C:\Users\HAI NAM\Finance1\defi-research\data\runs\recovery_20261020'
$cfg = 'configs/models.reference.json'
& $py -m defi_models check --data-run $data --config $cfg
& $py -m unittest discover -s tests -q
```

Ba file thành viên (mỗi output phải là folder mới chưa tồn tại):

```powershell
& $py -m defi_models.rq6 --data-run $data --config $cfg --allow-exploratory --out results/member_rq6
& $py -m defi_models.rq3 --data-run $data --config $cfg --out results/member_rq3
& $py -m defi_models.rq2_rq5 --data-run $data --config $cfg --allow-exploratory --out results/member_rq2_rq5
```

Muốn chạy file trực tiếp có thể thay `-m defi_models.rq6` bằng `defi_models/rq6.py`; tương tự hai file còn lại. Cả hai cách đều gọi registry/gate chung. File RQ2+RQ5 có `--only 2` hoặc `--only 5` để chạy một RQ. RQ3 vẫn được ghi exploratory dù CLI không bắt buộc cờ như RQ5–7.

Chạy riêng từng RQ bằng main, hoặc chạy all:

```powershell
& $py -m defi_models rq1 --data-run $data --config $cfg --out results/new_rq1
& $py -m defi_models rq4 --data-run $data --config $cfg --out results/new_rq4
& $py -m defi_models rq7 --data-run $data --config $cfg --allow-exploratory --out results/new_rq7
& $py -m defi_models all --data-run $data --config $cfg --allow-exploratory --out results/my_7rq
& $py scripts/validate_model_run.py results/my_7rq
```

Main cũng có `all --models 2 5` để chọn subset. `check --check-models 2 5` kiểm tra gate cùng subset. Cờ exploratory không bỏ qua checksum hoặc audit. Khi bị thiếu file/audit không phủ RQ, xử lý dữ liệu thực; không sửa JSON audit thủ công.

Export lại báo cáo RQ7 từ một run có sẵn:

```powershell
& $py rq7_policy_sensitivity.py --run results/my_7rq --out output/rq7_export_moi
& $py -m unittest test_rq7_policy_sensitivity -q
```

Không dùng lại output cũ. RQ7 đã tự xuất report trong run thì không cần export lại trừ khi muốn bản sao ở thư mục khác.

## 12. So sánh với kết quả tham chiếu

```powershell
& $py scripts/compare_model_runs.py 'C:\Users\HAI NAM\Finance1\defi-research\results\full_7rq_20261022_final' results/my_7rq --json-out results/my_7rq/comparison.json
```

Với cùng data/config: kỳ vọng passed=true, 22 CSV/summary so sánh, difference_count=0. Thư mục báo cáo con không làm thay đổi file khoa học dùng để so sánh. Thời gian chạy/đường dẫn máy không cần giống; counts so chính xác, ước lượng số thực có rtol1e−9/atol1e−6. So hai run phải cùng danh sách RQ và config. So subset thì tạo reference subset tương ứng hoặc so các CSV/summary của RQ đó.

Không thay data/config giữa chừng. Seed, bootstrap, train split, mapping, horizon, label window và số vòng đều ảnh hưởng kết quả. Dataset full và mẫu5 ví không thể so như cùng một thí nghiệm.

## 13. Chạy trên máy thành viên khác và dashboard

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-models.txt
# Muốn khớp môi trường đã kiểm chứng:
.\.venv\Scripts\python.exe -m pip install numpy==2.5.4 scipy==1.18.1
```

Đặt `$py` thành `.\.venv\Scripts\python.exe`, `$data` thành vị trí dataset trên máy đó. Không cần RPC/API key khi chạy mô hình offline. Nếu cài từ ZIP, giữ package cùng cấu trúc, không chỉ lấy ba file.

Dashboard realtime (`python -m defi_live`) dùng data/live và cohort đang quan sát; kết quả sẽ đổi theo block nên không kỳ vọng bằng snapshot offline. Để dùng tham số Hawkes của run đã hợp nhất:

```powershell
& $py -m defi_live --historical-results results/merged_7rq_20261023
```

Dashboard Streamlit thành viên (`streamlit_app.py`) hiện dành cho available_rq14 và không phải realtime; giữ nhãn phạm vi của nó. Không đổi partial runner thành full chỉ bằng giao diện.
