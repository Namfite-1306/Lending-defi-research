# Tích hợp code thành viên — 23/10/2026

Code được tích hợp trên nhánh main local của repository Lending-defi-research.
Không thay dataset đã freeze tại repository Finance1/defi-research.

## Thay đổi

- Tách thuật toán RQ3, RQ6 và RQ2+RQ5 thành ba module có CLI; main và live dùng cùng các hàm qua compatibility imports.
- Giữ nguyên thuật toán RQ1/RQ4 và engine khoa học; available_rq14 vẫn là luồng exploratory riêng, không được tự coi là kết quả full.
- Sửa exporter RQ7: explicit run, kiểm tra config/grid, không ghi đè, không hardcode kết luận, giữ trạng thái hội tụ/Pareto và scope nguồn.
- Main tự tạo báo cáo RQ7 sau khi mô hình chạy thành công.
- Thêm config tham chiếu 200 vòng, subset CLI và manifest SHA-256 source code.
- Sửa test RQ7, tài liệu và claims về liquidator concentration chưa có trong code.

## Kiểm chứng

- `unittest discover -s tests -q`: 164 tests, 0 failures/errors, 6 skipped do phụ thuộc dashboard chưa cài (158 không skip).
- Entry test RQ7 tại root: 8 tests đạt, không cần tạo output trước.
- Chạy thực tế 7 RQ tại `results/merged_7rq_20261023_final` trên dataset đầy đủ và cấu hình reference.
- Validator đầu ra đạt 7/7. Đối chiếu với `C:/Users/HAI NAM/Finance1/defi-research/results/full_7rq_20261022_final`: 22 file, 0 khác biệt với rtol1e-9/atol1e-6.
- Chạy trực tiếp cả ba file mới trên dữ liệu thật: RQ3, RQ6 và RQ2+5 đều thành công; CSV/summary khớp đầu ra tương ứng của main.
- Chạy CLI exporter RQ7 độc lập thành công, báo đúng 17.084 ví, không lấy bộ mẫu5 ví upload cũ.

RQ3 và RQ5–RQ7 vẫn exploratory. Tái lập số liệu không phải xác minh nhân quả hay hiệu chỉnh mô hình kinh tế.

## File bàn giao

- Ba file thuật toán: `defi_models/rq6.py`, `defi_models/rq3.py`, `defi_models/rq2_rq5.py`.
- Hướng dẫn mô hình, công thức và lệnh chạy: `HUONG_DAN_MO_HINH_RQ1_RQ7.md`.
- Bằng chứng, bản sao ba file và gói ZIP: `output/ban_giao_20261023/` trên máy hiện tại.
- Gói ZIP không chứa database nghiên cứu; cần chuyển dataset riêng hoặc truyền `--data-run`.

Các file `summary_validation.json`, `policy_grid_81_scenarios.csv`, `sensitivity_results.csv` và `policy_scenarios.csv` ở root là artifact mẫu cũ từ thành viên, được giữ để truy vết. Không dùng chúng thay kết quả full mới. Exporter mới không tự tìm hoặc chọn các file này.

Không push remote trong đợt này.
