# Cấu trúc mã nguồn sau sắp xếp

Mục tiêu là dễ tìm code, tránh lặp logic và giữ các lệnh cũ hoạt động. Không minify hoặc đổi mô hình chỉ để giảm số dòng. Dữ liệu, output nghiên cứu đã khóa và file bàn giao có checksum được giữ nguyên.

## Các lớp chính

| Folder | Trách nhiệm |
|---|---|
| defi_data | Thu thập, RPC resilience, giải mã events và tái dựng dữ liệu |
| defi_models | Estimators, simulation và shared CLI của RQ1–7 |
| defi_live | Backend local, freshness, what-if jobs và web assets |
| research_h124 | Các lượt nâng cấp nghiên cứu H1/H2/H3 và cascade |
| apps/streamlit | Giao diện Streamlit tùy chọn; root streamlit_app.py chỉ là entry point |

## Nhóm module nghiên cứu

| Folder bên trong research_h124 | Nội dung |
|---|---|
| shared | Đường dẫn canonical, IO/locks, constants và nhãn H |
| positions | H1 snapshots, stress/attribution và context theo quý |
| concentration | H2 Comet/matched concentration và nguồn giá |
| temporal | H3 data, Hawkes/NB/hurdle, diagnostics và rolling |
| cascade_engine | Dữ liệu và engine cascade có route |
| reporting | Audit, tổng hợp kết quả, literature và báo cáo |
| orchestration | Coordinator, offline runner và preflight |

Đây là các folder nhóm implementation, chưa phải API import mới. Public module names vẫn là `research_h124.h1`, `research_h124.h4_data`, `research_h124.source_audit`… Package `__init__.py` khai báo search path tới các folder để Python tìm đúng module, giữ nguyên relative imports, monkeypatch targets và CLI `python -m`. Không có bản sao estimator hay một shim cho từng module.

Không đổi lệnh thành `python -m research_h124.positions.h1`; dùng tên public đã tài liệu hóa. Muốn thêm module, đặt đúng nhóm và giữ tên duy nhất giữa các folder. Kiểm thử compatibility kiểm tra module lookup, repository root và công cụ CLI cũ.

`shared/common.py` xác định repository root theo vị trí mới. Audit provenance duyệt đệ quy để không bỏ sót module sau khi chia folder. Data/results vẫn resolve theo manifest và các đường dẫn canonical cũ.

## Scripts

Implementation nằm ở `scripts/reports`, `scripts/validation`, `scripts/maintenance`. Các `.py` cũ tại `scripts/` chỉ chuyển tiếp qua một dispatcher `_compat.py`; không chứa bản sao logic. Vì vậy lệnh và import sau vẫn giữ nguyên:

```powershell
python scripts/validate_model_run.py results/your_run
python scripts/compare_model_runs.py --help
python -m research_h124.market_prices --help
python -m research_h124.hurdle_model --help
```

PowerShell vận hành vẫn ở `scripts/` để người dùng không phải đổi lệnh khởi động/setup. Nếu muốn chạy implementation Python trực tiếp trong folder con, dùng `python -m scripts.reports.<module>` hoặc `python -m scripts.validation.<module>` từ repository root. Script report có thể ghi artifact; không chạy để kiểm tra import tùy tiện.

## Legacy và bộ bàn giao

README RQ7 từng nằm ở root và các CSV/JSON/test prototype chuyển sang `archive/member_rq7`. Giữ nội dung để đối chiếu; không coi đây là output chính mới. Cấu hình RQ7 chuyển sang `configs/members/rq7_policy.json`. `rq7_policy_sensitivity.py` ở root là entry point nhỏ gọi shared policy_report, giữ cho lệnh cũ/import tests tương thích.

`deliverables/writing_materials_20261024` và ZIP/Word đã bàn giao không sửa để giữ checksum. Dataset trong `data`, kết quả trong `results` không di chuyển. Code hash ở những lần chạy mới có thể khác sau refactor; điều cần đối chiếu cho reproducibility là input/config, số liệu CSV và kết quả kỹ thuật, không phải giả định source hash luôn như cũ.

Nếu backend hoặc worker Python đã khởi chạy trước khi chuyển file, khởi động lại tiến trình đó để nạp package search path mới. Các lệnh khởi động không đổi. Không dùng script migration một lần để khởi động dashboard.
