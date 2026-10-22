# Dashboard realtime local

## Chạy

Trong thư mục `defi-research`, dùng Python >=3.11:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-models.txt
.\.venv\Scripts\python.exe -m defi_live
```

Nếu `.venv` đã có, bỏ qua hai lệnh đầu. Mở **http://127.0.0.1:8787**. Giữ terminal và máy chạy: đóng chương trình sẽ ngừng cập nhật. Đây là server local, không phải website đã public cho giảng viên. Không cần Node/npm để chạy dashboard.

GitHub Codespaces/Linux: `python -m defi_live`; dùng cơ chế port forwarding của Codespaces để mở port 8787. Server mặc định bind loopback; public deployment cần thiết kế hosting/backend riêng. Không tự công khai máy local.

### Lệnh thường dùng

```powershell
# Theo dõi 10 ví; block mỗi 15s, snapshot/mô hình sau mỗi lần hoàn tất + 300s
.\.venv\Scripts\python.exe -m defi_live --wallet-limit 10 --poll-seconds 15 --snapshot-seconds 300

# Danh sách ví cụ thể, một địa chỉ mỗi dòng
.\.venv\Scripts\python.exe -m defi_live --wallet-file wallets.txt --wallet-limit 20

# Tách run/state thử nghiệm
.\.venv\Scripts\python.exe -m defi_live --state-dir data/live/thu_nghiem --port 8788
```

Nếu không có `--wallet-file`, chọn các ví Borrow Aave gần đây trong phần lịch sử live đã thu. Đây là nhóm quan sát thay đổi theo thời gian, **không phải universe toàn thị trường và không phải cohort dùng cho suy luận causal**. `--wallet-limit 0` lấy toàn danh sách đã phát hiện, có thể rất tốn RPC/thời gian; không tự biến nó thành full-market coverage.

RPC lấy từ `ETH_RPC_URLS` nếu được đặt, hoặc các endpoint công khai mặc định. Không ghi URL có key vào Git. Xem README_CRAWL.md nếu nguồn không đáp ứng lịch sử/quota. Mô hình và collector chạy riêng: RPC chậm có thể làm chu kỳ dài hơn mức đặt, không có bảo đảm SLA từ nguồn miễn phí.

## Đúng nghĩa realtime đến đâu?

| Thành phần | Chu kỳ / nguồn | Diễn giải |
|---|---|---|
| Event ba giao thức | Poll mỗi 15 giây, lấy tới head trừ 2 block xác nhận | Tải tăng dần, checkpoint sau khi cả ba giao thức và headers khớp; không phải finalized consensus |
| Giá | Đọc Chainlink tại block đã thu; cập nhật theo chu kỳ collector | Không giả định oracle có round mới mỗi 15 giây; hiển thị riêng tuổi oracle round và tuổi block dữ liệu |
| Vị thế | Mặc định 300 giây sau lần tính trước hoàn tất | Snapshot cùng block của nhóm ví; đọc config/E-mode/debt index hiện tại và đối chiếu HF với Aave |
| RQ1 | Tính lại từ snapshot live đã đạt validation | Stress giả định, không phải volume thực thi |
| RQ2 | Count/HHI thanh lý từ SQLite trong cửa sổ đã quan sát | Số event, không tổng USD. Không bị giới hạn bởi cap danh sách recent events |
| RQ3 | Motif Borrow→Supply→Borrow trong tối đa 48h live | Nhãn temporal chưa xác minh funding; có warm-up/cap và không phải matched causal effect realtime |
| RQ4 | Conditional Hawkes intensity từ event mới và tham số huấn luyện đã có | Không tự retrain, không biến branching ratio thành causal claim. Warming-up khi thiếu context. Default tìm `results/review_20261022_full/rq4/summary.json`; đổi bằng `--historical-results` |
| RQ5 | Activity graph live, exposure đồng bộ của cohort trong product mô hình | Aave + Comet USDC; Morpho chỉ các market quan sát liên quan cohort, tối đa 20. Lỗi/coverage được giữ rõ, không phải network toàn thị trường/ước lượng causal contagion |
| RQ6/RQ7 | Tính lại mỗi snapshot hợp lệ | Vẫn là engine giả định; giữ tham số depth/bonus/gas và cờ không hội tụ/Pareto |

Thời gian thực của **dữ liệu đầu vào**, **kết quả mô phỏng** và **tham số được huấn luyện lại** là các khái niệm khác nhau. Dashboard hiển thị rõ từng loại. Không thể quan sát ngay outcome thanh lý tương lai của RQ3 tại thời điểm dự báo.

## Giới hạn lịch sử, đồng hồ và chất lượng

- Mặc định bắt đầu ở khoảng 120 block trước confirmed head, không tự nối vào dataset kết thúc 30/09/2026. API ghi `history_contiguous_with_research=false`. Khoảng yêu cầu 24h chưa thu đủ thì hiển thị số phút/giờ thực có, không xem phần thiếu là zero.
- `--start-block` cho tải bù từ block chỉ định, có thể mất lâu; không tự chứng nhận continuity/coverage nghiên cứu. Dùng state-dir mới nếu đổi chain/confirmations/start argument. Khởi động lại cùng state-dir sẽ resume từ checkpoint.
- Data live ở `data/live/`, tách khỏi `data/runs/recovery_20261020/` và bị gitignore. Không sửa freeze manifest của bộ nghiên cứu để giả thành data live.
- Không cache `eth_call`/headers theo block number trong luồng live: reorg không được dùng lại state cũ. Hash/parent liên tục, log hash phải khớp header. Phát hiện reorg thì tìm common ancestor tối đa 64 block, rollback event và sản phẩm bị orphan. Không tìm được ancestor thì báo lỗi và giữ trạng thái chưa xác minh.
- Lỗi RPC/ABI/validation không thành zero. Giữ sản phẩm hợp lệ gần nhất kèm thời điểm, báo error/stale thay vì làm mới timestamp. Revision Aave ngoài 1–11 bị chặn cho tới khi có adapter được kiểm chứng.
- Độ trễ nguồn đo theo timestamp chain head cộng thời gian quan sát đã trôi; tuổi lần tính đo bằng clock backend. API có `clock_offset_seconds` để thấy lệch đồng hồ máy/nguồn, tránh gắn tuổi bằng 0 khi block timestamp đang đi trước clock máy.
- Phân tích motif/activity giới hạn 20.000 event gần nhất cho mỗi lần gọi, có cờ cap. Count thanh lý RQ2 vẫn truy vấn đủ cửa sổ SQLite. Exposure chọn mẫu và market membership chưa đủ thì không suy ra không có exposure ở phần chưa đọc.
- Mỗi component có block/time riêng. Một model job lỗi có thể khiến snapshot cũ vẫn được xem, nhưng không được coi là vừa tính mới. `completed` không bằng research-ready.

## API để chỉnh hoặc thay frontend

| Endpoint GET | Nội dung |
|---|---|
| `/api/status` | Head, cursor, độ trễ, job/error, reorg, trạng thái từng component |
| `/api/prices` | Chainlink price/round/updatedAt và block snapshot |
| `/api/events?limit=30&protocol=aave_v3` | Recent events; limit tối đa 100, protocol có thể bỏ |
| `/api/analytics?hours=24` | RQ2, motif RQ3, conditional RQ4, activity graph RQ5 |
| `/api/models` | Snapshot scope/positions, RQ1/RQ6/RQ7 tables, exposure RQ5 và assumptions |

Exposure RQ5 chạy ở worker riêng để RPC chậm của Compound/Morpho không chặn RQ1/RQ6/RQ7. API ghi riêng `rq5_source_block` và `rq5_freshness`; không giả định nó cùng block với mọi mô hình khác. Chưa có snapshot exposure thì UI ghi chưa có dữ liệu, không thay bằng số 0.

Frontend ở `defi_live/web/index.html`, `style.css`, `app.js`. API same-origin, read-only, không trả RPC key. Dashboard phân biệt live/stale/error/catching-up; nút chọn shock, cửa sổ và giao thức hoạt động với dữ liệu thực.

## Kiểm tra

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
# Một chu kỳ thật, không khởi động web server và không tiếp tục chạy nền:
.\.venv\Scripts\python.exe -m defi_live --once --state-dir data/live/one_shot --lookback-blocks 30 --chunk 30 --wallet-limit 2
```

One-shot có thể chưa thấy Borrow mới/active wallets; khi đó phần model chưa có đầu vào và sẽ báo rõ. Chế độ server tiếp tục poll để chờ dữ liệu, không bịa vị thế.
