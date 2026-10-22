# Thu thập dữ liệu RQ1 và RQ4

Phạm vi đã chọn: Ethereum mainnet, lịch sử 27/01/2023 đến trước 01/10/2026; RQ1 snapshot Aave V3 tại block 21762264. RQ4 cấu hình `aave_v3`. Script thu lịch sử Aave V3 bằng `recovery history --protocols aave_v3`, giữ nguyên toàn bộ thời gian đã chọn. Dữ liệu giao thức khác đã có trong SQLite được giữ lại, nhưng không đưa vào bảng thanh lý/panel đã kiểm định cho RQ4. Các audit `--models 1 4` chỉ chứng nhận RQ1/RQ4.

## Dữ liệu còn thiếu khi bắt đầu

| RQ | Dữ liệu cần có | Tình trạng ban đầu và nguồn |
|---|---|---|
| RQ1 | Toàn bộ Borrow trước block 21762264 để xác định cohort | Chưa có lịch sử đầy đủ. Lấy event từ Aave V3 Ethereum qua RPC lịch sử; không chọn cohort theo liquidation sau cutoff |
| RQ1 | Balances, risk debt, oracle, LT/E-mode, revision cùng block | Chỉ có mẫu: 59 dòng vị thế/20 ví trong run stress và 29 dòng trong run expansion; chưa phải snapshot toàn bộ cohort |
| RQ1 | `full_snapshot_21762264/positions.csv`, `validation.csv`, `scope.json` | Thu bằng `recovery_positions`; phải đối chiếu HF/debt và quét hết cohort trước khi đánh dấu snapshot hoàn tất |
| RQ4 | `processed/liquidations_model_table.csv` và `liquidations_hourly_full_period.csv` | Chưa có. Thu log và block timestamps, kiểm tra coverage trước khi xuất bảng; giờ thiếu dữ liệu không được tính là 0 |
| RQ4 | `processed/market_prices_hourly_full_period.csv` | Chưa có. Script lấy lịch sử Chainlink ETH/USD và BTC/USD, giữ source time/availability/stale. Giá stablecoin không được thu trong luồng này; feature định giá khoản nợ không có feed được giữ unpriced |
| Cả hai | Ba audit JSON và `freeze_manifest.json` | Chỉ tạo và đánh dấu đạt sau khi kiểm tra thực tế; không dùng file rỗng hay sửa cờ passed thủ công |

## Chạy quy trình

Chạy từ thư mục gốc dự án. Cấu hình RPC thu thập qua `ETH_RPC_URLS`. Cấu hình nguồn đối chiếu qua `ETH_AUDIT_RPC_URLS`; mặc định audit thử Blast. Hai endpoint phải khác nhau; hai URL khác nhau vẫn chưa chứng minh hạ tầng độc lập. Kết quả probe mẫu không bảo đảm nguồn phục vụ được toàn kỳ.

```powershell
.\scripts\collect_rq1_rq4.ps1
```

Để tự chạy và validate cả hai mô hình sau khi dữ liệu/audit đạt, dùng `.\scripts\collect_rq1_rq4.ps1 -RunModels`. Hai lần chạy có thư mục riêng trong `results/rq14_full_.../`; chỉ khi thành công mới tạo `output/rq1_rq4_acquisition/historical_results.json` chứa đường dẫn có thể truyền cho `defi_live --historical-results`.

Script chạy lần lượt: history -> prices -> features -> snapshot -> audit 1/2/3 cho RQ1/RQ4 -> model input check. History tự resume checkpoint đã commit; không tạo coverage cho chunk lỗi. Script dừng ở bước lỗi và ghi trạng thái `failed`; `completed` chỉ khi cả audit và model preflight đạt. Không chạy hai tiến trình thu thập đồng thời.

Lượt history dùng chunk 10.000 block theo giới hạn RPC đã quan sát. Các checkpoint 50.000 block trước đó vẫn được tận dụng; chương trình bỏ qua chunk con nếu toàn bộ chunk đã nằm trong phạm vi đã tải. Lỗi giới hạn kích thước được chia nhỏ; chữ số trong địa chỉ/block hex không được coi là mã HTTP 403/429.

## Theo dõi

```powershell
Get-Content '.\output\rq1_rq4_acquisition\collection_status.json' -Raw
Get-Content '.\data\runs\recovery_20261020\progress.json' -Raw
Get-Content '.\output\rq1_rq4_acquisition\history.stdout.log' -Tail 15
```

Mỗi bước có `<bước>.stdout.log` và `<bước>.stderr.log`. Nếu script đang chờ lượt history đã khởi động trước đó, xem `output/rq1_rq4_acquisition/history.log`. Thư mục recovery đã tồn tại hoặc có SQLite không đồng nghĩa dữ liệu đã đầy đủ.

## Kiểm tra và chạy mô hình khi đã có dữ liệu

Nếu `defi_models rq4` báo `Source integrity gate failed: Missing audit_1_structure.json; ...; Missing freeze_manifest.json`, bộ dữ liệu chưa hoàn thành các vòng kiểm định. Đây là bước chặn trước khi ước lượng, nên lệnh đó chưa tạo kết quả RQ4 mới. `configs/models.example.json` cấu hình mô hình; nó không tải dữ liệu hay tạo audit.

Kiểm tra `collection_status.json` và log của bước được ghi trong trường `phase`. Lượt thu thập ngày 22/10/2026 đã hoàn thành coverage Aave 9.599.302 block, nhưng dừng tại `prices` do RPC trả `-32603 service temporarily unavailable`; vì vậy chưa đến audit. Coverage tải đủ vẫn cần được đối chiếu ở các vòng audit. Bản sửa cho phép retry lỗi dịch vụ tạm thời và chia truy vấn giá thành tối đa 10.000 block; nếu vẫn thất bại, bước giá tiếp tục báo lỗi thay vì coi khoảng thiếu là không có sự kiện.

Sau khi lượt trước đã dừng, chạy lại quy trình từ thư mục dự án; checkpoint lịch sử được tận dụng:

```powershell
$env:ETH_RPC_URLS = 'https://rpc.mevblocker.io'
$env:ETH_AUDIT_RPC_URLS = 'https://eth.drpc.org'
.\scripts\collect_rq1_rq4.ps1 -RunModels
```

Đây là các endpoint đã dùng trong lượt thu thập, không bảo đảm luôn khả dụng. Nếu nguồn lỗi kéo dài, thay bằng RPC mainnet hỗ trợ log và state lịch sử trong cùng phạm vi; nguồn audit phải khác nguồn thu thập. Không chạy thêm script nếu `collection_status.json` đang báo `running` và tiến trình đó còn hoạt động.

Chỉ khi quy trình báo `completed` mới chạy mô hình chính thức bằng các lệnh bên dưới. Không tự tạo bốn file JSON, sửa cờ audit thành đạt hoặc dùng kết quả `exploratory` thay cho dữ liệu đã freeze.

```powershell
.\.venv\Scripts\python.exe -m defi_models check --check-models 1 4
.\.venv\Scripts\python.exe -m defi_models rq1 --config configs/models.example.json
.\.venv\Scripts\python.exe -m defi_models rq4 --config configs/models.example.json
```

Ba audit có trường `models: [1, 4]` không được dùng để chứng nhận RQ2/RQ3/RQ5/RQ6/RQ7. `defi_models check` không thêm `--check-models` vẫn kiểm tra cả bảy RQ.

## Kết quả tạm thời từ dữ liệu đang có

```powershell
.\.venv\Scripts\python.exe -m defi_models.available_rq14 --config configs/models.example.json
```

Lệnh này đọc snapshot mẫu expansion cùng metadata token và validation tại cùng block để tái dựng HF; không coi mẫu là toàn bộ người vay. RQ4 chỉ dùng đoạn đầu liên tục của coverage Aave, loại giờ đầu/cuối chưa quan sát đủ, giữ nguyên sự kiện cùng timestamp và chia train/test theo thời gian. Nó so sánh Hawkes một biến với Poisson hằng; không thay cho Poisson có ETH/BTC controls hoặc phân tích toàn kỳ. Các file được xuất riêng, có manifest/hash và trạng thái `exploratory`; SQLite gốc được mở chỉ đọc. Không đưa kết quả này vào nhóm đã qua audit toàn kỳ.
