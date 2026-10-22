# Bàn giao Người 4 — RQ2 và RQ5 (kèm đường chạy RQ1/RQ2)

**Khoảng thời gian yêu cầu:** `[2023-01-27 00:00:00 UTC, 2026-10-01 00:00:00 UTC)` trên Ethereum mainnet. Mốc kết thúc là exclusive: không lấy dữ liệu từ 01/10/2026 trở đi.

> **Trạng thái gói này:** mã nguồn và hướng dẫn đã được bổ sung; dữ liệu lịch sử chưa được crawl trong môi trường tạo gói vì môi trường này không phân giải được DNS/kết nối RPC. Không có CSV lịch sử hay kết quả nghiên cứu mới nào được giả làm dữ liệu thật. Chạy collector trên máy có mạng và RPC lịch sử mới tạo dataset. `unittest` có 2 lỗi do thư mục ZIP không có metadata Git (`git rev-parse HEAD`), không phải lỗi phân tích RQ2/RQ5; xem phần kiểm thử.

## 1. Phạm vi và dữ liệu phải thu

### RQ2 — tập trung thanh lý

Cần event thanh lý và metadata để đo **Top-k/HHI theo số sự kiện**, cùng Top-k/HHI theo giá trị USD chỉ trên tập được định giá hợp lệ:

- **Aave V3 Ethereum:** `LiquidationCall`: borrower, liquidator, debt asset, collateral asset, debtToCover, collateral amount, block/tx/log index, block timestamp.
- **Compound III USDC Ethereum:** `AbsorbDebt` và các event liên quan. `basePaidOut` không tự động đồng nghĩa với “debt repaid”; giữ nhãn economic meaning riêng.
- **Morpho Blue Ethereum:** `Liquidate`, market ID và `repaidAssets`; ánh xạ market ID sang loan/collateral token.
- **Định giá:** token decimals/symbol và lịch sử Chainlink ETH/USD, BTC/USD theo logic hiện có; không có feed hợp lệ thì giữ unpriced/NA, không đổi thành 0.
- **Kiểm tra coverage:** coverage block liên tục, giờ thiếu dữ liệu không được coi là giờ có 0 thanh lý; xác minh nguồn và các vòng audit trước khi freeze.

### RQ5 — mạng exposure và lan truyền

Lịch sử event chỉ cho biết **hoạt động**, không phải số dư vị thế. Cần thêm snapshot vị thế đồng bộ theo block cho borrower–protocol–asset, giá USD và validation on-chain. Mã hiện có xuất mạng mẫu và common-wallet overlap; nó **không** xác định được quan hệ chủ sở hữu giữa các ví, khoản nợ trực tiếp giữa hai giao thức hay cơ chế truyền nhiễm nhân quả. Không được gọi exposure mẫu là mạng toàn thị trường.

### RQ1 (được yêu cầu chạy cùng RQ2)

Cần toàn bộ borrower cohort có Borrow trước block snapshot `21762264`, positions cùng block, risk debt, collateral enablement, oracle/price, liquidation threshold/E-mode và validation so với `getUserAccountData`. Chỉ chạy RQ1 khi snapshot báo `full_snapshot_complete=true` và toàn bộ vị thế được validation đạt.

## 2. Chạy thu thập dữ liệu trên Windows

Yêu cầu Python 3.11+ và PowerShell. Giải nén ZIP, mở PowerShell tại thư mục `Lending-defi-research-main`, rồi chạy:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-models.txt
.\scripts\collect_rq1_rq2_full_period.ps1
```

Script chạy tuần tự: full history cho ba giao thức → Chainlink prices → feature/model tables → snapshot Aave → audit 1/2/3 dành cho RQ1/RQ2 → preflight → mô hình RQ1/RQ2. Crawl dài có checkpoint; nếu RPC lỗi, script dừng ở bước lỗi và không ghi nhận chunk thất bại là coverage rỗng. Có thể chạy lại sau khi xử lý nguồn RPC. Không chạy hai collector đồng thời.

### RPC

README_CRAWL.md mô tả endpoint công khai và preflight. Endpoint công khai có thể bị rate-limit, prune hoặc không hỗ trợ state lịch sử. Nếu preflight thất bại, hãy thiết lập các endpoint archive/historical RPC mà bạn có quyền dùng trong `ETH_RPC_URLS`; không đưa URL chứa API key lên GitHub. Không chạy full crawl trước khi preflight đạt.

## 3. Đầu ra và chạy lại mô hình

Dữ liệu được lưu ở `data/runs/recovery_20261020/`, bảng đã chuẩn hóa ở `data/runs/recovery_20261020/processed/`, kết quả mô hình ở `results/`. Các đầu ra quan trọng:

- `history.sqlite`, `block_range.json`, `history_coverage.csv`, `history_gaps.csv` — dữ liệu gốc và coverage.
- `processed/liquidations_model_table.csv`, `processed/concentration_full_period_event_counts.csv`, `processed/liquidation_valuation_coverage.csv` — đầu vào/bảng RQ2.
- `full_snapshot_21762264/positions.csv`, `validation.csv`, `scope.json` — snapshot RQ1.
- `audit_1_structure.json`, `audit_2_onchain.json`, `audit_3_research.json`, `freeze_manifest.json` — bằng chứng audit/freeze.

Khi collector báo `completed`, có thể chạy thủ công:

```powershell
.\.venv\Scripts\python.exe -m defi_models check --data-run data/runs/recovery_20261020 --check-models 1 2 --config configs/models.example.json
.\.venv\Scripts\python.exe -m defi_models rq1 --data-run data/runs/recovery_20261020 --config configs/models.example.json
.\.venv\Scripts\python.exe -m defi_models rq2 --data-run data/runs/recovery_20261020 --config configs/models.example.json
```

Mỗi lần chạy sinh thư mục kết quả mới. Không sửa cờ audit bằng tay, không tự tạo file rỗng để vượt preflight.

## 4. RQ5 — chạy có điều kiện, không được phóng đại kết quả

Mô hình RQ5 đọc `processed/exposures_valued_sample.csv` và yêu cầu file này nằm trong freeze manifest. Sau khi dữ liệu exposure đã được dựng và kiểm định theo hướng dẫn trong `README_MODELS.md`/`defi_data/recovery.py`, chạy:

```powershell
.\.venv\Scripts\python.exe -m defi_models check --data-run data/runs/recovery_20261020 --check-models 5 --config configs/models.example.json
.\.venv\Scripts\python.exe -m defi_models rq5 --data-run data/runs/recovery_20261020 --config configs/models.example.json --allow-exploratory
```

Nếu thiếu `exposures_valued_sample.csv`, snapshot không đồng bộ block, không có exposure đã định giá hoặc audit không chứng nhận RQ5, **dừng và sửa dữ liệu**. Không dùng hoạt động ví theo lịch sử làm proxy cho exposure. Kết quả RQ5 hiện chỉ là exploratory shared-wallet exposure screen; chưa đủ để tuyên bố causal contagion.

## 5. Cách diễn giải kết quả RQ2

- `event_count`: số event; có thể tính Top-1/Top-10/Top-20 và HHI trên borrower, liquidator, debt token, collateral token.
- `reported_amount_market_usd_priced_subset`: chỉ tổng trên event được định giá và qua điều kiện độ mới của giá. Báo cáo đồng thời `priced_events`, `unpriced_events`, coverage ratio.
- Không so sánh hoặc cộng thẳng giá trị `basePaidOut` Compound với debt repaid của Aave/Morpho.
- Kết quả chạy được không đồng nghĩa dữ liệu đã được audit hoặc nhận diện nhân quả. Đọc `summary.json`, `manifest.json`, coverage, gaps và audit JSON trước khi viết kết luận.

## 6. Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Bộ test trong mã nguồn dùng fixture tổng hợp và không thay cho crawl. Khi giải nén ZIP không có thư mục `.git`, hai test của `available_rq14.py` hiện có thể lỗi tại `git rev-parse HEAD`; điều đó không phải bằng chứng dữ liệu đã crawl thành công hay thất bại. Cần chạy test lại trong bản clone Git đầy đủ để xác nhận toàn bộ test.
