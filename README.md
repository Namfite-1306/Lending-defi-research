# DeFi research data pipeline

**Dashboard realtime local:** [README_REALTIME.md](README_REALTIME.md). Chạy `.venv\Scripts\python.exe -m defi_live`, mở http://127.0.0.1:8787. Collector 15 giây; snapshot/mô hình theo chu kỳ riêng, có nhãn scope/stale/error.

**Kiểm tra nguồn và sửa lỗi crawl RPC:** xem [README_CRAWL.md](README_CRAWL.md). Lệnh chẩn đoán: `python -m defi_data.rpc_check --require-state --test-logs`.

**Chạy mô hình RQ1–RQ7:** xem [README_MODELS.md](README_MODELS.md), mã trong `defi_models/`, cấu hình trong `configs/`. Phần bên dưới mô tả crawler/pilot gốc; các giới hạn của pilot không phải trạng thái dữ liệu recovery mới. Dữ liệu đầy kỳ và báo cáo ba vòng audit nằm trong `data/runs/recovery_20261020/` (không đưa lên GitHub).

Pipeline chỉ đọc Ethereum mainnet, không ký hoặc gửi giao dịch. Python >= 3.11, không cần cài thư viện ngoài.

Hướng dẫn công việc tiếp theo cho Người 2: [RQ1 và RQ4](NEXT_STEPS_N2_RQ1_RQ4.md). Ghi chú sửa lỗi và tạo lại dữ liệu giá: [README_EXPANSION.md](README_EXPANSION.md#sửa-lỗi-22102026-và-tạo-lại-đầu-ra).

## Chạy

Trong thư mục này:

```powershell
python -m unittest discover -s tests -v
python -m defi_data.pipeline
python -m defi_data.validate_run stress_20250203_smoke
python -m defi_data.audit_qa --live
```

Lệnh mặc định thu thập cửa sổ **03/02/2025 00:00–03:00 UTC**, chụp tối đa 5 tài khoản Aave tại block ngay trước cửa sổ và lấy receipts của tối đa 20 giao dịch. Đây là chạy thử pipeline bằng dữ liệu thật, chưa phải bộ dữ liệu nghiên cứu đầy đủ.

Đổi thời gian, phạm vi mẫu và tên lần chạy:

```powershell
$env:ETH_RPC_URLS = 'https://eth-mainnet.public.blastapi.io,https://eth.drpc.org,https://rpc.mevblocker.io'
python -m defi_data.pipeline --start 2025-02-02T00:00:00Z --end 2025-02-04T00:00:00Z --run-id stress_20250202_04 --max-wallets 20 --receipts 100
```

Đầu cuối thời gian là **[start, end)**, phải có timezone. Snapshot ở `start_block - 1`. Chỉ hỗ trợ khoảng sau Ethereum Merge. RPC công khai có thể giới hạn batch, log, lịch sử hoặc lưu lượng. Có thể đặt endpoint riêng qua biến môi trường trên, không ghi API key vào mã hay Git.

`--wallet-file wallets.txt` nhận danh sách địa chỉ (mỗi dòng một ví). `--max-wallets 0` lấy tất cả ví **được phát hiện**, không tự biến danh sách đó thành toàn bộ thị trường. `--skip-snapshot` hoặc `--skip-valuations` chỉ dùng khi muốn lấy sự kiện; manifest ghi đúng bước đã chạy. Mỗi cấu hình dùng một `--run-id` khác nhau. Chạy lại cùng cấu hình sẽ dùng cache và coverage, không nhân đôi logs.

## Phạm vi hợp đồng

- Aave V3 Ethereum Core Pool: `0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2`.
- Compound III Ethereum USDC Comet: `0xc3d688b66703497daa19211eedff47f25384cdc3`. Không phải mọi thị trường Compound.
- Morpho Blue Ethereum: `0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb`. Không bao gồm Morpho Optimizer/Midnight.
- Registry Aave: đọc pool, oracle và data provider tại block lịch sử; không dùng data provider hiện tại cho quá khứ.

Định nghĩa event lấy từ nguồn chính thức trong `data/sources/`. Decoder hỗ trợ sự kiện kiểu tĩnh được liệt kê trong mã. Phiên bản/ABI khác phải được kiểm tra trước khi mở rộng thời gian.

## Đầu ra

Mỗi lần chạy nằm tại `data/runs/<run-id>/`:

| File | Nội dung |
|---|---|
| `raw.sqlite` | Logs gốc, decoded fields, coverage theo block và hash |
| `settings.json` | Cấu hình đã khóa cho lần chạy |
| `manifest.json` | Trạng thái, số lượng, hashes file, mức sẵn sàng và hạn chế từng RQ |
| `DATA_REPORT.md` | Báo cáo kiểm tra offline, tạo bằng `python -m defi_data.validate_run <run-id>` |
| `processed/events.csv` | Sự kiện chuẩn hóa có chain, contract, block, tx và log index |
| `processed/liquidations.csv` | Logs liên quan thanh lý, giữ riêng từng loại đo lường |
| `processed/blocks.csv` | Block hash và thời gian UTC để nối dữ liệu |
| `processed/hourly_counts.csv` | Số sự kiện theo giờ, có giờ 0 sự kiện và cờ giờ quan sát thiếu |
| `processed/oracle_prices_hourly.csv` | Giá WETH/WBTC/USDC từ oracle Aave tại các mốc giờ và biên cửa sổ |
| `processed/account_market_activity.csv` | Hoạt động ví–thị trường quan sát được, không phải số dư hoặc exposure trực tiếp |
| `processed/rq3_borrow_supply_candidates.csv` | Motif vay rồi gửi trong cùng giao dịch, cần xác minh luồng tài sản trước khi gắn nhãn vòng lặp |
| `processed/aave_reserves.csv` | Token metadata, giá oracle và cấu hình rủi ro tại snapshot |
| `processed/positions.csv` | Số dư đã tích lũy lãi theo token/tài khoản tại snapshot |
| `processed/position_validation.csv` | Đối chiếu thế chấp, nợ và HF với hợp đồng cùng block |
| `processed/snapshot_scope.json` | Cách chọn ví, số ví phát hiện/lấy mẫu và giới hạn |
| `processed/rq1_sample_stress.csv` | Stress tĩnh chỉ trên mẫu đã qua validation |
| `processed/aave_liquidations_valued.csv` | Quy đổi nợ được thanh lý theo giá oracle cuối block sự kiện |
| `processed/rq2_concentration.csv` | Top-1, Top-10, HHI theo nợ Aave thực tế được trả |
| `processed/token_transfers_sample.csv` | ERC20 transfers trong receipts lấy mẫu, chưa phải vòng lặp đã xác nhận |

CSV dùng UTF-8 BOM để mở tiếng Việt; số nguyên blockchain được lưu dạng chuỗi để không mất độ chính xác. Khi đọc bằng pandas phải chỉ định dtype cho `*_raw`, địa chỉ, tx và market ID. Khi mở Excel/Sheets không dùng chúng làm nơi lưu trữ số nguyên 256-bit chuẩn.

## Các giới hạn phải giữ khi sử dụng

1. **Không coi ví phát hiện trong cửa sổ là toàn thị trường.** Mẫu ưu tiên ví bị thanh lý rồi ví vay. Chọn ví bằng sự kiện tương lai tạo selection/look-ahead bias nếu dùng làm mẫu dự báo quá khứ. Kết quả stress chỉ để kiểm tra pipeline. Muốn RQ1 toàn thị trường phải dựng universe borrower độc lập tại snapshot từ lịch sử đầy đủ/indexer đã kiểm chứng.
2. **E-mode chưa được mô hình hóa.** Export balances nhưng đánh dấu `unsupported_emode`; không đưa các vị thế đó vào stress. Các vị thế khác phải đối chiếu cả tổng thế chấp, nợ và HF với sai số tương đối <= 0,01%.
3. **Cú sốc hiện chỉ ánh xạ WETH/WBTC.** Các token khác giữ giá cố định, kể cả token phái sinh ETH/BTC; không ngầm giả định luôn giữ peg. Cần mở rộng ánh xạ và kịch bản depeg trước nghiên cứu chính thức.
4. `eligible_debt_usd` là dư nợ đủ điều kiện thanh lý, **không phải volume thực thi hoặc nợ xấu**. Chưa có bộ mô phỏng cascade RQ6/RQ7 trong pipeline dữ liệu này.
5. Compound `AbsorbDebt`, `AbsorbCollateral`, `BuyCollateral` là các đối tượng khác nhau, không cộng chung thành volume thanh lý. Panel đếm `AbsorbDebt` theo account, không đếm thêm log collateral.
6. Giá sự kiện là **oracle cuối block**, không phải giá trước giao dịch hay giá bán thực tế. Chưa định giá USD cho Compound/Morpho; không tổng hợp volume USD xuyên giao thức khi chưa bổ sung.
7. RQ3 còn thiếu lịch sử trước cửa sổ, swap giải mã, traces và nhóm đối chứng. ERC20 transfer không tự chứng minh vòng lặp hoặc chủ sở hữu.
8. RQ4 mới có panel số sự kiện; cửa sổ 3 giờ không đủ ước lượng Hawkes đáng tin. Cần lịch sử liên tục dài hơn, giá/lợi suất đồng bộ và kiểm soát gas/oracle.
9. RQ5 mới có sự kiện liên giao thức; chưa có mạng exposure hoặc bằng chứng truyền dẫn nhân quả. Cùng địa chỉ hoặc cùng ETH không chứng minh khoản phải thu trực tiếp.
10. Chỉ chuẩn hóa event đã chọn; không dựng số dư bằng cách cộng trừ events trong cửa sổ. Snapshot đọc trạng thái hợp đồng tại block cố định.

## Kiểm tra và truy nguồn

Rà soát ngày 22/10/2026: **108/108 unit tests đạt** trong `.venv` có NumPy/SciPy sau tích hợp bản mô hình và bản sửa RPC; **15/15 nhóm audit `--live` đạt** trên 4.294 sự kiện và 14 CSV, gồm 6 logs thanh lý, 4 block biên và HF của 5 ví được đọc mới qua RPC. Cài dependency mô hình theo `README_MODELS.md` để các test estimator không bị skip. Chi tiết audit ở `data/runs/stress_20250203_smoke/audit/audit_results.json`. PDF hiện có ở `output/pdf/` là bản ngày 18/10/2026, chưa được tạo lại trong lần sửa này.

`audit_qa --live` dùng chung RPC client với pipeline và nhận cấu hình `ETH_RPC_URLS`; mặc định là Blast, dRPC, MEV Blocker. Các truy vấn trực tiếp luôn bỏ qua cache. Nếu một nhóm không lấy được dữ liệu mới, audit lưu nhóm đó là chưa đạt, giữ các kiểm tra đã thực hiện và trả exit code 1; không chuyển sang cache để báo đạt. Thông báo lỗi giữ mã HTTP/RPC và số thứ tự endpoint để chẩn đoán, không ghi URL/key. Bỏ `--live` chỉ chạy các kiểm tra nội bộ và ghi đè báo cáo bằng kết quả offline có `audit_mode=offline`.

Nếu gặp `Fresh RPC unavailable: HTTPError,HTTPError` từ bản cũ, hàm audit còn dùng hai endpoint cố định và bỏ mất chi tiết lỗi HTTP. Đã thay hàm đó bằng client có fallback/retry và xử lý lỗi theo nhóm kiểm tra. Chạy lại:

```powershell
$env:ETH_RPC_URLS = 'https://eth-mainnet.public.blastapi.io,https://eth.drpc.org,https://rpc.mevblocker.io'
python -m defi_data.audit_qa --live
```

- Kiểm tra chain ID=1; khóa block lịch sử đã cách head 64 block.
- Deduplicate theo `(chain_id, transaction_hash, log_index)`.
- Kiểm tra block hash khi chuẩn hóa logs. Nếu RPC trả reorg mismatch, dừng và dùng run/cache mới sau điều tra.
- Lỗi RPC không được thay bằng 0 hoặc bỏ qua. Một bước lỗi khiến manifest `status=failed`; không diễn giải file tồn tại là pipeline đã hoàn thành.
- Cache là kết quả RPC tại số block cụ thể. Với lịch sử rất gần/reorg cần bộ cache mới; không giả định cache tự reorg-proof.
- Các unit tests dùng dữ liệu giả rõ ràng, tách khỏi `data/runs/`.

## Nguồn chính thức

- https://github.com/aave-dao/aave-address-book/blob/main/src/AaveV3Ethereum.sol
- https://github.com/aave/aave-v3-core/blob/master/contracts/interfaces/IPool.sol
- https://github.com/compound-finance/comet/blob/main/contracts/CometMainInterface.sol
- https://github.com/morpho-org/morpho-blue/blob/main/src/libraries/EventsLib.sol
- https://www.aave.com/docs/aave-v3/smart-contracts/pool
- https://docs.compound.finance/liquidation/
- https://docs.morpho.org/developers/contracts/blue/
