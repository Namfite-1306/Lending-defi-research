# Sắp xếp mã nguồn ngày 26 tháng 10 năm 2026

Đã sắp xếp80file vào folder theo chức năng, viết lại README tổng quan và thêm chỉ mục docs. Bản local còn7file ở root, clone E còn8file do có requirements-reference.txt riêng; crawler/models/dashboard vẫn giữ các package public đang sử dụng.

## Những phần đã làm

- Nhóm42module nghiên cứu vào shared, positions, concentration, temporal, cascade_engine, reporting và orchestration.40file implementation giữ nguyên byte;2file khác chỉ sửa repository-root resolution và source inventory cho cấu trúc mới.
- Giữ tên import/CLI cũ bằng package search path, không sao chép estimator thành nhiều phiên bản. Tên module được yêu cầu duy nhất giữa các nhóm.
- Nhóm9công cụ Python vào scripts/reports, scripts/validation, scripts/maintenance. Lệnh cũ đi qua dispatcher chung; PowerShell vận hành không đổi chỗ.
- Tách implementation Streamlit vào apps/streamlit/dashboard.py; root entry point vẫn hoạt động. Backend dashboard chính vẫn là defi_live.
- Gom hướng dẫn vào docs/data, docs/models, docs/dashboard, docs/research, docs/reviews; lưu bản RQ7 cũ trong archive/member_rq7. Không gọi README RQ7 cũ là README chung của cả dự án.
- Chuyển cấu hình bàn giao cũ vào configs/members. File Word/ZIP/code bàn giao đã có checksum không sửa.
- Bỏ các bước gán/kiểm tra trùng trong preflight model runner; không thay đổi thuật toán, parameters, seed hoặc định nghĩa biến.
- Bổ sung ignore cho tmp, log và audit refactor mới. Ignore không tự untrack những log đã được Git theo dõi từ trước; đợt này không sửa index hoặc commit/push.

## Kiểm tra

- Trước thay đổi:249tests,243đạt,6skip.
- Sau thay đổi:253tests,247đạt,6skip; thêm4kiểm tra import/CLI/provenance compatibility.
- Chạy thật RQ2/RQ3/RQ5/RQ6; validator đạt.14CSV/JSON đầu ra khớp SHA256 với bộ frozen cũ.
- Chạy trực tiếp tại clone E:253tests,247đạt,6skip; bổ sung file test comparison trước đó clone còn thiếu. RQ2/3/5/6 tại clone E cũng xuất14CSV/JSON khớp SHA256 với bộ frozen.
- 40file kết quả nghiên cứu đã khóa không đổi hash; data/results không di chuyển.
- Log và manifest refactor trong output/restructure_20261026. Mỗi file chuyển chỗ có bản backup; đồng bộ clone E giữ các nội dung khác biệt có sẵn của nhóm thay vì chép đè từ C.

Đây là refactor cấu trúc và loại bỏ phần lặp, chưa phải tối ưu tốc độ ước lượng hay thay scientific methods. Residual và những giới hạn dữ liệu/mô hình vẫn như trước. Cách dùng mới bắt đầu ở README.md và docs/README.md; các lệnh chạy trước đây vẫn giữ.

Bảng tra đường dẫn trước và sau: [file_migration.json](../file_migration.json).

Ba tài liệu chỉ có ở clone E cũng được chuyển vào nhóm docs phù hợp và giữ bản sao tại local. Không bỏ cấu hình dependency requirements-reference.txt riêng của clone.
