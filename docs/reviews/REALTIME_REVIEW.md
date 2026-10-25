# Kiểm tra bản realtime local — 22/10/2026

Phạm vi được triển khai: collector tăng dần của Aave V3, Comet USDC, Morpho Blue; Chainlink; snapshot Aave của nhóm ví; các đầu ra RQ có mức sẵn sàng được ghi riêng. UI/API local, chưa public lên máy chủ và chưa push GitHub.

## Bằng chứng

- 85/85 tests đạt, gồm checkpoint atomic, hash/parent, rollback orphan events/products, deep reorg dừng an toàn, no-cache RPC, snapshot nguồn cũ, source-error freshness, giá trị thiếu không thành zero, và count thanh lý không bị cap recent events.
- Python compile và JavaScript syntax check đạt.
- Chạy live trên RPC thật; cursor tăng từ 26247259 lên 26247306 trong hai lần quan sát lưu tại `output/live_review_20261022/`. Sau đó UI đã hiển thị block 26247323; không phải dữ liệu demo cố định.
- API trả đủ 5 feed Chainlink, events mới, snapshot HF được đối chiếu với Aave revision 11. Trong quá trình kiểm tra có ví E-mode 17 đạt validation.
- RQ1/RQ6/RQ7 đã được tính từ snapshot live và có source block. Exposure cùng nhóm ví được định giá tại snapshot riêng, errors/coverage không bị bỏ qua.
- UI đã kiểm tra trực tiếp trên in-app browser: chọn shock 30%, lọc Morpho Blue, dữ liệu event thay đổi; ảnh `output/live_review_20261022/dashboard.png` lấy từ dữ liệu thật.
- Run QA dùng 2 ví và snapshot interval 30s để kiểm tra nhanh. Cấu hình mặc định cho người dùng là poll 15s, snapshot interval 300s, 2 confirmations, tối đa 10 ví. Thời gian job thực tế cộng thêm vào khoảng chờ, không cam kết SLA.

## Những sửa đổi quan trọng

1. State live được tách khỏi lịch sử đã audit; checkpoint chỉ commit khi đủ ba giao thức và block hashes khớp.
2. Khi reorg, rollback về common ancestor tối đa 64 block; không dùng lại cache state theo block number trên nhánh cũ.
3. Event, oracle round, snapshot, model và exposure có clock/source block riêng. Backend báo lỗi/stale thay vì cập nhật timestamp giả.
4. Đã quan sát độ lệch clock máy/nguồn trong lúc chạy. Độ trễ chain được tính bằng chain head; `clock_offset_seconds` và thông báo UI giữ sự khác biệt này rõ ràng.
5. Snapshot/mô hình và exposure chạy riêng để request phụ chậm không chặn mọi kết quả mới.
6. Không gộp data tail với dataset kết thúc tháng 09/2026 qua khoảng trống chưa thu. Cửa sổ yêu cầu và thời gian quan sát thực được hiển thị riêng.
7. RQ3 chỉ là motif chưa chứng minh funding/causal effect. RQ4 dùng tham số lịch sử cho conditional intensity, có warm-up và chặn tham số huấn luyện tương lai; không tự retrain.
8. RQ5 chỉ exposure nhóm ví/Morpho markets đã phát hiện; không tự suy thành network toàn thị trường hoặc kênh contagion nhân quả. RQ6/RQ7 vẫn là mô phỏng có giả định, không phải liquidation/bad debt đã quan sát.

## Sử dụng và triển khai

Xem README_REALTIME.md. Giữ tiến trình chạy để tiếp tục thu thập. Khi chưa chạy backend, UI không có nguồn realtime. Để giảng viên truy cập từ máy khác cần triển khai backend luôn bật và frontend/API tương ứng; đây chưa phải bản public deployment.
