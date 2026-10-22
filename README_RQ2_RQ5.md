## 1. RQ2 — mức độ tập trung thanh lý

### Dữ liệu cần

- Ethereum mainnet logs từ ba protocol được hỗ trợ trong code: Aave V3 (`LiquidationCall`), Compound III USDC (`AbsorbDebt`) và Morpho Blue (`Liquidate`).
- Protocol, block, timestamp, transaction hash, log index; borrower/liquidator; debt/collateral token hoặc market; raw event amounts.
- Token decimals/symbol, lịch sử giá oracle phù hợp với thời điểm event, trạng thái định giá và tuổi giá.
- Coverage theo protocol/block, gaps, log lỗi, kiểm tra uniqueness và audit. Khoảng block phải khớp chính xác với khoảng UTC nêu trên.

### Chỉ số

Tính Top-k và HHI theo số sự kiện cho borrower, liquidator, debt token và collateral token. Chỉ tính concentration theo USD trên các event định giá hợp lệ, đồng thời báo cáo số event được định giá/không định giá và coverage. Không gộp `basePaidOut` của Compound với debt repaid của protocol khác như thể cùng một đại lượng kinh tế.

## 2. RQ5 — mạng exposure liên giao thức

Cần snapshot số dư vị thế **được định giá và đồng bộ tại cùng block** cho wallet–protocol–asset, gồm debt/collateral, token, giá, decimals và bằng chứng kiểm tra on-chain. Cần các bảng market/configuration cho Morpho và Compound, cùng cohort/vị thế Aave.

**Quan trọng:** lịch sử sự kiện không phải snapshot exposure. Mã RQ5 hiện dùng một exposure sample kiểm định, không phải toàn bộ thị trường; kết quả chỉ là exploratory shared-wallet exposure screen. Không thể kết luận nhân quả lan truyền contagion hoặc khẳng định hai ví cùng chủ sở hữu chỉ vì chúng tương tác với cùng giao thức.

## 3. Chạy crawl lịch sử

Yêu cầu Python 3.11+ và RPC Ethereum có khả năng đọc lịch sử. Trên Windows PowerShell, tại thư mục dự án:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-models.txt
.\scripts\collect_rq2_rq5_full_period.ps1
```

Trước khi chạy full crawl, làm theo mục **Kiểm tra nguồn trước** trong `README_CRAWL.md`:

```powershell
.\.venv\Scripts\python.exe -m defi_data.rpc_check --require-state --test-logs
```

Nếu preflight thất bại, đừng chạy full crawl. Cấu hình endpoint archive/historical RPC có quyền sử dụng qua biến môi trường `ETH_RPC_URLS`; không commit URL chứa API key. Script sẽ dừng khi bước bắt buộc thất bại và lưu log ở `output/rq2_rq5_full_period/`.

## 4. Script và các giai đoạn

` scripts/collect_rq2_rq5_full_period.ps1 ` thực hiện:

1. Crawl lịch sử event cho Aave V3, Compound III USDC và Morpho Blue trong cửa sổ ngày đã yêu cầu.
2. Tải lịch sử giá Chainlink ETH/USD và BTC/USD theo pipeline có sẵn.
3. Tạo bảng feature/liquidation, bao gồm coverage và trạng thái định giá.
4. Chạy audit cấu trúc và audit on-chain, sau đó chạy research audit ở phạm vi RQ2 בלבד.
5. Chạy kiểm tra đầu vào và mô hình RQ2 khi các audit bắt buộc đạt.
6. Kiểm tra các file tiền điều kiện RQ5; chỉ chạy dựng exposure nếu cohort nguồn cần thiết đã có. Nếu thiếu, script ghi cảnh báo rõ ràng thay vì tạo file giả. Bộ code hiện tại chưa hỗ trợ scoped research audit riêng cho RQ5, nên không được xem RQ5 là đã qua gate chỉ từ các audit RQ2.

Repository có cổng audit dùng chung và phần audit RQ5 chưa được tách riêng. Nếu RQ2 gate lỗi, hãy đọc đúng log và JSON audit để xác định bước thất bại. Không chỉnh audit JSON thủ công để ép mô hình chạy. RQ5 cần bổ sung audit theo phạm vi RQ5 và dữ liệu cohort đã kiểm định trước khi có thể được coi là chạy chính thức.

## 5. Các đầu ra cần giữ

- `data/runs/recovery_20261020/history.sqlite`
- `data/runs/recovery_20261020/block_range.json`
- `data/runs/recovery_20261020/processed/history_coverage.csv`
- `data/runs/recovery_20261020/processed/history_gaps.csv`
- `data/runs/recovery_20261020/processed/liquidations_model_table.csv`
- `data/runs/recovery_20261020/processed/liquidation_valuation_coverage.csv`
- `data/runs/recovery_20261020/audit_1_structure.json`, `audit_2_onchain.json`, `audit_3_research.json`
- `results/` — kết quả mô hình chỉ khi gate đầu vào được thông qua
- `output/rq2_rq5_full_period/` — stdout/stderr theo từng bước

## 6. Chạy mô hình thủ công sau khi đủ dữ liệu

```powershell
.\.venv\Scripts\python.exe -m defi_models check --data-run data/runs/recovery_20261020 --check-models 2 --config configs/models.example.json
.\.venv\Scripts\python.exe -m defi_models rq2 --data-run data/runs/recovery_20261020 --config configs/models.example.json
```


```powershell
.\.venv\Scripts\python.exe -m defi_models check --data-run data/runs/recovery_20261020 --check-models 5 --config configs/models.example.json
.\.venv\Scripts\python.exe -m defi_models rq5 --data-run data/runs/recovery_20261020 --config configs/models.example.json --allow-exploratory
```

Nếu `check` báo thiếu file, audit không phủ model 5, snapshot không đồng bộ block hoặc exposure không được freeze trong manifest, hãy dừng để xử lý đầu vào. `--allow-exploratory` không bỏ qua các điều kiện dữ liệu; nó chỉ cho phép chạy mô hình có cảnh báo exploratory.

## 7. Cách xác nhận crawl thành công

Không chỉ dựa vào thông báo cuối cùng. Kiểm tra:

- `block_range.json` có đúng `start_utc` và `end_exclusive_utc`;
- mọi protocol được chọn có `download_complete=True` và không có khoảng trống ngoài dự kiến;
- `history_gaps.csv` rỗng đối với coverage được tuyên bố đầy đủ;
- bảng liquidation có event keys duy nhất và timestamp nằm trong khoảng nghiên cứu;
- audit JSON và `manifest.json` ghi nhận đúng đầu vào, hash và trạng thái;
- `summary.json` mô hình nêu rõ coverage định giá, cảnh báo và giới hạn diễn giải.

