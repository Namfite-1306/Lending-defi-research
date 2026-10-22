# Sửa lỗi crawl RPC và chạy kiểm tra

Luồng này dùng khi cần tải dữ liệu Ethereum. Chạy mô hình bằng dataset đã có thì dùng README_MODELS.md; không cần chạy lại crawler.

## Thay đổi

- RPC mặc định thử MEV Blocker, dRPC và Blast; có thể ghi đè bằng `ETH_RPC_URLS`. Không giả định nguồn công khai luôn phục vụ lịch sử hoặc luôn sẵn sàng.
- Trước crawl, kiểm tra chain 1, header hai biên, log lịch sử có thật và receipt tương ứng. Luồng cần đọc trạng thái còn kiểm tra `POOL_REVISION()` tại block mục tiêu. Chỉ giữ nguồn đã qua kiểm tra.
- Các probe có block/tx/log index được lưu trong `data/sources/rpc_history_probes.json`, lấy từ bộ lịch sử đã audit. Probe là kiểm tra mẫu, không thay coverage toàn kỳ và đối chiếu độc lập.
- Không dùng lại cache cũ: cache mới ở `data/rpc_cache/transport_v2/`; `eth_getLogs` trong crawler được truy vấn mới, resume dựa trên checkpoint đã commit.
- Chỉ chia đôi truy vấn khi có lỗi giới hạn khoảng block/kích thước kết quả. Lỗi 4444/pruned, authorization, rate limit hoặc lỗi không phân loại được không tạo cây truy vấn vô hạn.
- Lỗi từng phần trong batch được thử lại riêng qua nguồn dự phòng. Truy vấn thiếu result hoặc lỗi không được cache thành dữ liệu rỗng.
- Log sai địa chỉ/block/topic, bị removed hoặc trùng bị từ chối. Nghi ngờ response cap thì chia nhỏ; nếu một block vẫn chạm cap thì dừng để đổi nguồn.
- Pipeline thất bại không commit checkpoint của chunk lỗi. Crawl dài giữ checkpoint đã thành công, dừng cấp việc mới khi gặp lỗi nghiêm trọng hoặc ba chunk lỗi liên tiếp. Lỗi chunk khiến lệnh trả exit code khác 0.
- `expansion window` phải có sentinel Borrow/Supply của pilot; thiếu đầu vào sẽ dừng thay vì coi sentinel rỗng là kiểm tra đạt.

## Kiểm tra nguồn trước

PowerShell, trong `defi-research` (Python >=3.11; có thể dùng Python đã cài thay đường dẫn `.venv`):

```powershell
.\.venv\Scripts\python.exe -m defi_data.rpc_check --require-state --test-logs
```

Linux / GitHub Codespaces:

```bash
python -m defi_data.rpc_check --require-state --test-logs
```

Mặc định kiểm tra vùng block 21762265–21762300. `--test-logs` chỉ cho tối đa 100 block, không tạo crawl checkpoint. Báo cáo ở `output/rpc_check/rpc_preflight.json`; nguồn được ghi bằng số thứ tự, không ghi URL/API key. Đổi `--start-block`, `--end-block`, `--report` nếu cần. Nếu không có probe dương tại/trước phạm vi, cần bổ sung probe đã xác minh; không tự coi phản hồi rỗng là lịch sử đầy đủ.

## Nếu tất cả nguồn đều không đạt

Thiết lập RPC phục vụ lịch sử bằng biến môi trường; không đưa URL chứa key lên GitHub:

```powershell
$env:ETH_RPC_URLS = 'https://RPC-CUA-BAN,https://RPC-DU-PHONG'
.\.venv\Scripts\python.exe -m defi_data.rpc_check --require-state --test-logs
```

```bash
export ETH_RPC_URLS='https://RPC-CUA-BAN,https://RPC-DU-PHONG'
python -m defi_data.rpc_check --require-state --test-logs
```

Nếu vẫn không đạt, xem `failure_kind`: `history_unavailable`, `authorization`, `rate_limit`, `network`, `incomplete_history` hoặc lỗi RPC khác. Đổi sang nguồn đủ khả năng hoặc dùng dataset đã chia sẻ để chạy mô hình offline. Không lặp crawl toàn kỳ khi preflight đã thất bại.

## Chạy thử pipeline trong run riêng

```powershell
.\.venv\Scripts\python.exe -m defi_data.pipeline --start 2025-02-03T00:00:00Z --end 2025-02-03T00:02:00Z --run-id crawl_test_moi --chunk 20 --receipts 0 --skip-snapshot --skip-valuations
```

Linux dùng cùng các tham số sau `python -m defi_data.pipeline`. Cửa sổ 2 phút chỉ kiểm tra vận hành, không phải dataset đủ cho RQ. Muốn snapshot/valuation thực tế thì bỏ các cờ skip và chọn run-id mới. Manifest phải `status=completed`; kiểm tra thêm `rpc_preflight.json` và các bước thực sự đã bật.

`expansion window` là luồng mở rộng quanh pilot, cần pilot hợp lệ ở `data/runs/stress_20250203_smoke/`. `expansion history` vẫn dùng run mở rộng bị cách ly trước đây: preflight đạt không tự mở cổng verified coverage. `recovery history` cũng dùng preflight/fallback mới và giữ logic checkpoint riêng. Chưa cần tải lại bộ recovery đã đủ lịch sử chỉ để áp dụng bản sửa transport.

Các nguồn công khai có thể lỗi ở lần chạy sau. Khi một nguồn báo pruned giữa chừng, chỉ có thể tiếp tục nếu còn nguồn khác phục vụ yêu cầu; code sẽ báo lỗi nếu không còn nguồn phù hợp.
