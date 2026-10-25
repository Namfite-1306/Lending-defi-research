# Chạy mô hình RQ1–RQ7

## Bộ kết quả tham chiếu ngày 22/10/2026

Đã chạy đầy đủ cả 7 RQ với `configs/models.full_7rq_20261022.json` (không dùng smoke).
Cấu hình này tăng `max_rounds` từ 20 lên 200; RQ7 dùng tối đa 35 vòng và bảng kết quả
không đổi khi thử giới hạn 400 vòng. Hai lần chạy đủ 7 RQ khớp 22 file kết quả.
Bản tham chiếu local: `results/full_7rq_20261022_final/`, gồm báo cáo HTML/Markdown,
CSV, manifest, kiểm tra đầu ra và kiểm tra tái lập. `results/` không nằm trên GitHub.

Chạy lại và so sánh (thư mục đầu ra mới phải chưa tồn tại):

```powershell
.\.venv\Scripts\python.exe -m defi_models all --config configs/models.full_7rq_20261022.json --allow-exploratory --out results/my_7rq_comparison
.\.venv\Scripts\python.exe scripts/validate_model_run.py results/my_7rq_comparison
.\.venv\Scripts\python.exe scripts/compare_model_runs.py results/full_7rq_20261022_final results/my_7rq_comparison
```

Kết quả mong đợi: `passed=true`, `files_compared=22`, `difference_count=0`.
Giữ dataset đã freeze và phiên bản môi trường ghi trong manifest; script so sánh bỏ qua
thời gian chạy, nhưng đối chiếu cấu hình, input identities và kết quả. RQ3, RQ5–7
vẫn là kết quả thăm dò; việc chạy xong không khắc phục các giới hạn nghiên cứu bên dưới.

Code trong `defi_models/` đọc dữ liệu local, không crawl lại, không gọi RPC và không sửa dữ liệu nguồn. Python >= 3.11. Hai thư viện riêng cho mô hình: NumPy và SciPy; crawler gốc vẫn chỉ dùng standard library.

## 1. Cài đặt và kiểm tra

Mở PowerShell trong thư mục `Lending-defi-research`. Khi chưa có `.venv`, tạo và cài thư viện:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-models.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m defi_models check
```

Nếu `python` là phiên bản cũ, thay lệnh đầu bằng `py -3.12 -m venv .venv` hoặc đường dẫn Python >= 3.11. Không cần activate môi trường. Nếu đã có `.venv`, dùng Python trong đó; tránh chạy lại `python -m venv .venv` bằng phiên bản Python khác vì có thể giữ lại thư viện biên dịch không tương thích.

Có thể dùng `scripts/setup_models.ps1 -Python 'duong-dan-python.exe'`. Script tạo môi trường nếu chưa có, cài thư viện, kiểm tra import NumPy/SciPy và kiểm tra data. Tham số `-Python` chỉ dùng khi tạo môi trường mới. Thêm `-SkipDataCheck` nếu chỉ cài thư viện để chạy test, chưa có dataset. Nếu PowerShell chặn script, dùng trực tiếp các lệnh Python bên trên.

Nếu test báo `cannot import name '_ccallback_c'` hoặc SciPy `extension modules cannot be imported`, kiểm tra Python đang dùng và cài lại wheel tương thích trong `.venv`:

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip install --force-reinstall --no-cache-dir --only-binary=:all: -r requirements-models.txt
.\.venv\Scripts\python.exe -c 'import numpy, scipy; from scipy.optimize import minimize; print(numpy.__version__, scipy.__version__)'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Lệnh script tương đương cho bước sửa thư viện: `.\scripts\setup_models.ps1 -Repair -SkipDataCheck`. `pip install` thông thường có thể báo đã cài đủ do metadata cũ, dù file `.pyd` còn thuộc Python khác (ví dụ `cp312` trong môi trường Python 3.14). Các unit test dùng fixture tổng hợp và không yêu cầu dataset nghiên cứu; `defi_models check` kiểm tra dataset riêng sau đó.

Dataset mặc định: `data/runs/recovery_20261020/`. Folder này không nằm trên GitHub. Máy khác phải lấy dữ liệu riêng, giữ cấu trúc và các file audit/freeze manifest. Dùng `--data-run 'D:/du-lieu/recovery_20261020'` khi dữ liệu ở nơi khác.

## 2. Chạy thử toàn bộ

```powershell
.\.venv\Scripts\python.exe -m defi_models all --smoke --allow-exploratory
```

Đây là kiểm tra tích hợp trên dữ liệu thật với lưới kịch bản nhỏ. RQ2–RQ4 vẫn đọc lịch sử cần thiết, không đổi dữ liệu thiếu thành dữ liệu giả. `--smoke` giảm số kịch bản, vòng cascade, số bootstrap và số half-life; kết quả không dùng làm bảng kết luận cuối.

## 3. Chạy từng RQ để lấy kết quả

```powershell
.\.venv\Scripts\python.exe -m defi_models rq1 --config configs/models.example.json
.\.venv\Scripts\python.exe -m defi_models rq2 --config configs/models.example.json
.\.venv\Scripts\python.exe -m defi_models rq3 --config configs/models.example.json
.\.venv\Scripts\python.exe -m defi_models rq4 --config configs/models.example.json
.\.venv\Scripts\python.exe -m defi_models rq5 --config configs/models.example.json --allow-exploratory
.\.venv\Scripts\python.exe -m defi_models rq6 --config configs/models.example.json --allow-exploratory
.\.venv\Scripts\python.exe -m defi_models rq7 --config configs/models.example.json --allow-exploratory
```

Chạy cả bảy với cấu hình đầy đủ:

```powershell
.\.venv\Scripts\python.exe -m defi_models all --config configs/models.example.json --allow-exploratory
```

Wrapper tương đương: `scripts/run_models.ps1 -Model rq1`; thêm `-AllowExploratory` cho RQ5–RQ7. Mỗi lần chạy tự tạo folder `results/<UTC timestamp>/`; màn hình in đường dẫn `OUTPUT`. Có thể đặt `--out results/ten-thi-nghiem`, nhưng folder phải chưa tồn tại để không đè kết quả cũ. `all` tiếp tục chạy các RQ độc lập sau một lỗi, ghi lỗi vào manifest và trả exit code khác 0 nếu bất kỳ RQ nào thất bại.

## 4. Mỗi mô hình làm gì và đọc file nào

| RQ | Cách tính hiện có | File kết quả chính | Giới hạn cần giữ |
|---|---|---|---|
| 1 | Stress ETH, BTC và đồng thời; shock cả collateral và debt; tìm bước nhảy lưới và hồi quy tuyến tính một điểm gãy | `stress_curve.csv`, `factor_mapping.csv`, `summary.json` | Dư nợ đủ điều kiện thanh lý, không phải khối lượng thực thi. Snapshot trước stress 03/02/2025, chưa có panel nhiều ngày. Điểm gãy chỉ mô tả, chưa có kiểm định ngưỡng |
| 2 | HHI, Gini, Top-1/Top-10 và Top-20 theo ví/token, từng năm và toàn kỳ | `concentration.csv`, `top_entities.csv`, `valuation_coverage.csv` | Không cộng ba giao thức thành cùng loại USD volume. USD chỉ trên phần có giá; Comet basePaidOut khác debt repaid |
| 3 | Nhãn có sẵn trước snapshot; nearest-neighbor matching không lặp control theo log debt/HF/ETH share/BTC share; outcome thanh lý 7 ngày; bootstrap chênh lệch cặp, logistic penalized nếu outcome có biến thiên | `matched_pairs.csv`, `matching_balance.csv`, `summary.json` | Mặc định nhãn temporal, chưa phải đòn bẩy lặp đã xác minh toàn bộ. Control chỉ là không thấy motif, chưa chứng minh không dùng leverage. Đây là tương quan có điều kiện, không phải causal effect |
| 4 | Poisson có return controls; Hawkes exponential một biến, beta chọn bằng train likelihood; đánh giá chronological holdout | `hawkes_candidates.csv`, `hourly_predictions.csv`, `summary.json` | Event cùng timestamp block dùng chung pre-group intensity, không jitter. Hawkes chưa có giá làm covariate; branching ratio chưa chứng minh tự kích thích nhân quả. Poisson có return cùng giờ là mô hình giải thích, không forecast trước giờ |
| 5 | Mạng ví–protocol–asset, chồng lấn khoản nợ giữa protocol, sensitivity exposure của các ví cùng vay | `valued_edges.csv`, `protocol_overlap.csv`, `common_wallet_sensitivity.csv` | Exposure mẫu. Chưa phải mô hình default propagation hoặc identification kênh lây lan; không gán default probability giả |
| 6 | Engine thanh lý nhiều vòng có đối chứng zero-impact; giá giảm theo tổng lượng bán, đánh giá lại HF, kiểm tra profitability và số dư | `cascade_scenarios.csv`, `cascade_rounds.csv` | Mô phỏng giả định. Square-root impact và depth do người dùng chọn; chưa hiệu chỉnh bằng liquidation waves. Không tái tạo smart contract Aave chính xác |
| 7 | Grid close factor × bonus × LT shift × shock; Pareto screen theo shortfall, collateral seized và price impact | `policy_grid.csv`, `summary.json` | Chỉ là sensitivity của engine RQ6. Không được diễn giải tham số trên Pareto frontier là khuyến nghị chính sách thực tế |

`summary.json` của từng RQ ghi phương pháp, diagnostics và giới hạn. `manifest.json` ghi cấu hình, phiên bản Python/NumPy/SciPy, execution/readiness, thời gian và SHA-256 file đầu vào đã dùng. Các CSV đầu vào phải khớp `freeze_manifest.json`; thay data phải rà soát và freeze lại trước khi chạy.

Kiểm tra bộ kết quả sau khi chạy (thay đường dẫn bằng `OUTPUT` của lần chạy):

```powershell
.\.venv\Scripts\python.exe scripts/validate_model_run.py results/ten-thi-nghiem
```

Validator kiểm tra execution, kết quả hữu hạn, giới hạn concentration, số dư mô phỏng, control không lặp và optimizer hội tụ. Đây là kiểm tra kỹ thuật, không thay kiểm định giả thuyết hoặc xác minh mô hình kinh tế.

## 5. Đổi cấu hình

Sao chép `configs/models.example.json` thành file cấu hình riêng. Không sửa mặc định trong mã để chạy từng thí nghiệm.

- RQ1: `shock_step` là 0.01 cho mỗi bước 1%; `shock_max` là 0.6 cho tối đa 60%. `eth_symbols`/`btc_symbols` có thể ghi đè bằng danh sách symbol. Các derivative trong cùng factor giả định đồng biến 1:1; không phải ước lượng peg thực nghiệm. Token khác giữ giá cố định. Kiểm tra `factor_mapping.csv`.
- RQ3: `recursive_window_hours` chọn 6/24/48; `recursive_label` chọn `temporal` hoặc `verified`. Verified hiện chỉ có mẫu nhỏ và có thể không đủ cặp/overlap. Đọc số treated không được match, balance và khoảng bootstrap. `match_caliper` là khoảng cách Euclidean trên biến chuẩn hóa; tăng caliper có thể làm balance kém đi. Không dùng nhãn xuất hiện sau cutoff.
- RQ4: `protocol` chọn `aave_v3`, `compound_v3_usdc`, `morpho_blue`; `train_fraction` mặc định 0.8. Giữ holdout theo thời gian. Half-life tính bằng **giờ**, không phải giây. Các hệ số Poisson đi với covariate chuẩn hóa bằng train; center/scale lưu trong summary. Chưa có SE/inference phù hợp cho overdispersion và residual diagnostics Hawkes.
- RQ6: `liquidity_depth_usd`, `impact_coefficient`, `impact_cap`, `oracle_pass_through`, `gas_usd`, `dex_fee_fraction`, `sell_fraction` đều là giả định sensitivity. Không lấy bộ quotes sau snapshot làm thông tin biết trước. Engine hiện không dùng quotes tương lai để ngầm hiệu chỉnh.
- RQ7: `policy_lt_shifts` là thay đổi tuyệt đối LT: 0.03 nghĩa là +3 điểm phần trăm. Bonus 0.05 nghĩa là 5%; close factor 0.5 nghĩa là tối đa 50% nợ ở mỗi wallet action giả định. Đây không phải mapping các quy tắc Aave theo revision.

Engine RQ6/RQ7 giữ token quantities, shock cả debt và collateral, giảm risk debt và repayable debt theo cùng tỷ lệ khi trả, thu collateral lớn nhất của ví và kiểm tra chi phí/gas. GHO discount conversion, liquidation pair, close factor động/dust, protocol fee, liquidator funding và route thực tế chưa được tái tạo. Tính profitability theo batch đồng bộ có thể bảo thủ. `terminal_collateral_shortfall_usd` là chênh lệch kế toán mô hình, không phải bad debt on-chain.

Nếu `reached_round_limit=True`, tăng `max_rounds` rồi kiểm tra độ hội tụ; không coi kết quả bị cắt vòng là cân bằng cuối. `terminal_eligible_wallets>0` có thể do hết vòng, thiếu collateral hoặc không có thanh lý sinh lời. Các dòng Pareto luôn phải đọc kèm các cờ này.

Từ bản 0.2.0, kịch bản hết vòng có `pareto_evaluable=False` và để trống `pareto_nondominated`; không được dùng kịch bản đó để loại các chính sách đã chạy đến điểm dừng. Chỉ so sánh Pareto trong cùng mức shock. Manifest và màn hình giữ cảnh báo riêng với trạng thái chạy.

Engine đã tách giá thị trường khỏi oracle khi `oracle_pass_through<1`; lượng bán dùng cùng đơn vị USD tham chiếu sau shock để không đổi thước đo độ sâu giữa các vòng. Đây vẫn là giả định mô phỏng, chưa thay thế hiệu chỉnh bằng giao dịch thật.

Kiểm tra đầu vào hiện đối chiếu file thực tế/checksum, bảng validation và HF nền của toàn bộ snapshot. Chỉ có ba file audit JSON là chưa đủ để `check` báo đạt. HF của RQ1/RQ3 có làm tròn theo revision và đơn vị cơ sở, gồm vị thế số dư rất nhỏ; cú sốc tương lai vẫn là stress giả định trên giá trị tài sản đã xuất.

## 6. Đọc kết quả và nâng lên nghiên cứu hoàn chỉnh

1. Chạy RQ2, RQ1 và RQ4; kiểm tra coverage, mapping, held-out fit và diagnostics.
2. RQ3: chạy sensitivity các cửa sổ/nhãn, mở rộng xác minh dòng tiền; đánh giá balance và chỉ diễn giải association khi chưa có identification.
3. RQ5: bổ sung full position panel đồng bộ và xác định kênh truyền. Common-wallet exposure không tự là inter-protocol claim.
4. RQ6: thay engine giả định bằng adapter đúng revision và execution route; hiệu chỉnh/replay nhiều liquidation waves ngoài mẫu.
5. RQ7: sau khi RQ6 được kiểm chứng mới dùng policy grid cho kết luận chính thức, có borrower responses, mục tiêu và robustness phù hợp.

Mã chạy được không đồng nghĩa mọi RQ đã đủ dữ liệu hoặc đã tạo kết luận thực nghiệm. Bộ này cung cấp kết quả nền và các thí nghiệm có phạm vi rõ ràng để nhóm tiếp tục nghiên cứu.
