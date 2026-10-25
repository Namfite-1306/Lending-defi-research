# Dashboard giả định RQ1/RQ4

Ứng dụng Python + Streamlit đọc các kết quả `available_rq14` hiện có trong `results/`. Dữ liệu lịch sử và kịch bản được ghi rõ; ứng dụng không lấy dữ liệu realtime, không gọi RPC và không sửa dữ liệu nguồn hoặc file audit.

## Cài và chạy

Trong PowerShell, chuyển vào dự án trước khi chạy. Dùng môi trường `.venv` hiện có, không tạo lại:

```powershell
Set-Location -LiteralPath 'D:\Học tập with MC\New folder\Lending-defi-research'
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m pip install -r requirements-dashboard.txt
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

Mở <http://localhost:8501>. Server mặc định chỉ lắng nghe trên máy này (`127.0.0.1`). Nhấn Ctrl+C tại terminal để dừng. Nếu cổng đang dùng, thêm `--server.port 8502` rồi mở cổng tương ứng.

## Các phần theo dõi

- **Tổng quan:** chọn lần chạy RQ1/RQ4 độc lập, xem số mẫu, dư nợ, đường stress đã lưu và các đợt thanh lý.
- **RQ1 · Stress vị thế:** thay mức giảm giá ETH/BTC, dịch LT theo điểm phần trăm và bật/tắt mapping phái sinh. HF, ví đủ điều kiện và dư nợ tính lại từ snapshot mẫu đã đối chiếu. Hash nguồn phải khớp manifest trước khi mô phỏng. Mẫu số của tỷ lệ là tổng dư nợ sau cú sốc. Có bảng từng ví, tải CSV và giả định JSON.
- **RQ4 · Nhịp thanh lý:** lọc thời gian UTC, gộp ngày/tuần/tháng, xem ranh giới train/test và các ứng viên đã fit. Thử half-life, branching ratio và cụm sự kiện ban đầu để minh họa phản ứng kernel thế hệ thứ nhất. Đường này không fit lại dữ liệu, không mô phỏng thế hệ sau và không phải dự báo realtime. Các tham số đã fit hiển thị riêng.
- **Giả định & dữ liệu:** sổ giả định, cấu hình run, nguồn dữ liệu, tình trạng audit và trạng thái lưu của lượt thu thập.

Ứng dụng không thay trạng thái exploratory thành research-ready. Dư nợ HF < 1 không bằng khối lượng thanh lý thực thi; branching ratio không chứng minh quan hệ nhân quả. RQ4 exploratory chưa có biến kiểm soát giá ETH/BTC.

## Đầu vào

Mỗi lần chạy cần có `manifest.json`, `rq1/summary.json` + `stress_curve.csv` + `factor_mapping.csv`, hoặc `rq4/summary.json` + `hourly_counts.csv` + `hawkes_candidates.csv`. Với RQ1 tương tác, bốn file mẫu trong `source_files` phải còn ở đường dẫn trong dự án và giữ nguyên hash. Bản kết quả research runner không có `hourly_counts.csv` chưa được hỗ trợ ở màn hình RQ4 này.

Các thư mục dữ liệu và kết quả không đi kèm Git. Trên máy chưa có kết quả, tạo bằng:

```powershell
.\.venv\Scripts\python.exe -m defi_models.available_rq14 --models 1 --config configs/models.example.json
.\.venv\Scripts\python.exe -m defi_models.available_rq14 --models 4 --config configs/models.example.json
```

RQ4 cần lịch sử và RPC để tạo run; bản thân dashboard chỉ đọc các file đã tạo. Bấm **Đọc lại kết quả** để nhận lần chạy mới. Có thể đặt `DEFI_DASHBOARD_RESULTS` trỏ đến thư mục kết quả khác; mặc định là `results/` cạnh mã nguồn, không phụ thuộc thư mục terminal.

## Kiểm tra

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_dashboard.py -v
```

Kiểm thử dùng fixture tổng hợp, không cần RPC hoặc dataset thật. Nếu chưa cài thư viện dashboard, các test này được bỏ qua trong bộ kiểm thử crawler/model thông thường.
