# DeFi lending research

Nghiên cứu vị thế vay, thanh lý và rủi ro DeFi lending trên Ethereum. Kỳ chính H1/H2/H3 kết thúc **31/03/2026**; H1 có 13 snapshot cuối quý. Kết quả mô phỏng và residual chưa đạt phải được diễn giải theo giới hạn của từng mô hình.

## Bắt đầu

- [Hướng dẫn dashboard local](docs/dashboard/README_DASHBOARD_VI.md) — mở `http://127.0.0.1:8790/start` khi server chạy.
- [Chạy các mô hình RQ1 đến RQ7](docs/models/README_MODELS.md).
- [Dữ liệu và mô hình H1 H2 H3 mới](docs/research/README_SOURCES_H123.md).
- [Chỉ mục toàn bộ tài liệu](docs/README.md).
- [Giải thích cấu trúc mã nguồn](docs/architecture.md).

```powershell
# Chạy từ thư mục gốc repository
powershell -NoProfile -File scripts/start_stress_local.ps1
python -m defi_models check --data-run data/runs/recovery_20261020
python -m unittest discover -s tests -v
```

Dataset lớn không đi kèm GitHub. Dùng `--data-run` nếu dữ liệu nằm ở thư mục khác. Script dashboard hiện cấu hình cho máy local của nhóm; xem hướng dẫn trước khi dùng máy khác.

## Cấu trúc

```text
defi_data/          Crawler, RPC, tái dựng và kiểm tra dữ liệu
defi_models/        Engine và mô hình dùng chung cho 7 RQ
defi_live/          Backend dashboard và giao diện web
research_h124/     Nghiên cứu H1 H2 H3, chia theo nhóm chức năng
apps/streamlit/    Giao diện Streamlit tùy chọn
scripts/           Lệnh vận hành; tools trong reports, validation, maintenance
configs/           Cấu hình mô hình; cấu hình bàn giao cũ trong members
tests/             Kiểm thử đang sử dụng
docs/              Hướng dẫn, nghiên cứu, kiến trúc và báo cáo review
archive/           Bản bàn giao cũ chỉ giữ để đối chiếu
deliverables/      File Word, template, code bàn giao và evidence đã xuất
data/              Dữ liệu local, không di chuyển trong đợt sắp xếp
results/           Kết quả nghiên cứu, giữ nguyên
output/            Logs, audit, backup và artifact tạm
```

Các tên lệnh/import hiện có vẫn dùng được, ví dụ `python -m research_h124.market_prices --help`, `python scripts/validate_model_run.py --help` và `python -m streamlit run streamlit_app.py`. Không cần sửa pipeline theo tên các folder nhóm mới.
