# Chạy ba file code

Ba file chứa implementation của RQ tương ứng, không phải notebook minh họa. CLI gắn implementation trong file xuất vào shared runner để audit/config/manifest vẫn thống nhất. Các estimator được kiểm tra AST giống source main tại lúc xuất. Chúng cần package `defi_models/`, NumPy/SciPy và dataset; chưa phải ba script độc lập không dependency.

Trên máy hiện tại, mở PowerShell tại `C:\Users\HAI NAM\Finance1\defi-research`:

```powershell
$py = 'C:\Users\HAI NAM\Finance1\defi-research\.venv\Scripts\python.exe'
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$pack='deliverables/writing_materials_20261024'
$data='C:\Users\HAI NAM\Finance1\defi-research\data\runs\recovery_20261020'
& $py "$pack/code/RQ3.py" --data-run $data --config "$pack/models_config.json" --out results/my_rq3_run01
& $py "$pack/code/RQ6.py" --data-run $data --config "$pack/models_config.json" --allow-exploratory --out results/my_rq6_run01
& $py "$pack/code/RQ2_RQ5.py" --data-run $data --config "$pack/models_config.json" --allow-exploratory --out results/my_rq25_run01
```

Output directory phải chưa tồn tại; đổi tên lần chạy sau. Tách RQ2 hoặc5 bằng `--only 2` / `--only 5`; RQ2 riêng không cần exploratory flag. `--help` chỉ kiểm tra CLI, chưa là chạy model. Seed42, bootstrap300 và maxrounds200 trong config để so với bộ legacy full7RQ.

Nếu dùng clone E, pack cần nằm bên trong repository để tìm `defi_models/`; giữ `$data` trỏ tới canonical dataset C. Máy khác cần cài `requirements-models.txt`, mang đủ dataset/freeze manifests rồi thay `$py/$data`. Chưa có dataset thì không thể chỉ tải ba file và tái lập kết quả.

| File | Đầu vào | Đầu ra |
|---|---|---|
| RQ3.py | Full snapshot, temporal candidates/verified receipts, history.sqlite, event table và horizon | rq3/matched_pairs.csv, matching_balance.csv, summary.json |
| RQ6.py | Full snapshot + cascade config | rq6/cascade_scenarios.csv, cascade_rounds.csv, summary.json |
| RQ2_RQ5.py | Legacy event table + synchronized exposures_valued_sample.csv | rq2/concentration.csv, top_entities.csv, valuation_coverage.csv; rq5/valued_edges.csv, protocol_overlap.csv, common_wallet_sensitivity.csv |

**RQ2 trong file bàn giao là legacy generic runner**, có cảnh báo Comet basePaidOut và unknown collateral. Để lấy bảng H2 sửa semantics/matched/new market dùng `research_h124.h2`, `repair_h2`, `market_prices`, `source_analysis` theo README_SOURCES_H123.md. Không dùng generic RQ2 USD để thay bảng H2 chính của bài. Legacy RQ2 có thể đọc kỳ đến09/2026, trong khi H2 chính mới đã cắt31/03/2026. Scope này ghi rõ trong dossier.

RQ6 bàn giao là engine stylized, khác engine pair/route nghiên cứu mới; chưa calibrated lịch sử. RQ3 mặc định temporal labels, chưa phải cash-flow verified leverage. RQ5 là mạng mẫu.

Muốn chỉnh cửa sổ leverage6/24/48h, verified mode, caliper, shocks/depth/gas hoặc closefactor/bonus: sao chép config trước, giữ cả file config và manifest khi so kết quả. Không sửa raw dataset để làm model chạy qua gate.

Tái lập H1/H2/H3 mới: xem `README_SOURCES_H123.md` trong repository. Các lệnh đó có output directory cố định cho lượt nghiên cứu mới; sao lưu trước refit nếu muốn giữ cả lượt cũ. Dashboard: http://127.0.0.1:8790/research#sources.
