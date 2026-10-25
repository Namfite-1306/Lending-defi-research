# Dashboard tương tác RQ1–RQ7

URL local của bản hiện tại: **http://127.0.0.1:8788/lab**.
Trang `/` vẫn là live monitor; trang `/lab` là Research Lab. Không cần Node/npm để chạy.

## Chạy

Trong repository Lending-defi-research, chọn Python đã cài NumPy/SciPy:

```powershell
$py = 'C:\Users\HAI NAM\Finance1\defi-research\.venv\Scripts\python.exe'
& $py -m defi_live --port 8788 --historical-results results/merged_7rq_20261023_final
```

Hoặc `scripts/run_research_lab.ps1 -Python 'duong-dan-python.exe'`.
Giữ backend và máy chạy để giao diện và live data tiếp tục hoạt động.
Chỉ bind `127.0.0.1`; chưa public ra Internet.

Research Lab cần một research run đủ 7 RQ, `manifest.json`, `config.json`,
CSV/summary và dataset nguyên vẹn tại `data_run` của manifest. Đầu vào được kiểm
tra audit/freeze manifest/HF trước khi tạo snapshot lịch sử trong bộ nhớ.
Không lấy bộ sample5 ví upload cũ làm kết quả full. Đổi máy cần chuyển dataset,
chạy lại để manifest có đường dẫn đúng hoặc cấu hình lại đường dẫn run nguồn.

## Các thao tác

| Tab | Tương tác |
|---|---|
| RQ1 | Chọn ETH/BTC/joint cho đường tham chiếu; xem đường stress, phân trang. What-if bên trái tính lại HF/eligible debt, LT shift và danh sách top100 ví eligible theo dư nợ. |
| RQ2 | Lọc protocol/năm/borrower hoặc token/count hoặc USD; HHI/Gini/Top10 và thanh tỷ trọng cập nhật theo bộ lọc. |
| RQ3 | Tìm ví, lọc outcome của treated/control, phân trang các matched pairs; không chạy lại matching/logistic khi lọc. |
| RQ4 | Chọn khoảng ngày UTC; biểu đồ observed/Poisson và bảng giờ thay đổi. Lọc không fit lại Hawkes/Poisson. |
| RQ5 | Lọc protocol, tìm ví/token, xem exposure và số ví vay chung. Đây vẫn là mạng mẫu. |
| RQ6 | Chọn shock tham chiếu hoặc đổi giả định và bấm tính; so impact/zero-impact, repayment theo vòng, residual HF<1 và cờ hết vòng. |
| RQ7 | Lọc shock và chỉ hiện Pareto không bị trội trên grid đã lưu. What-if hiển thị một cấu hình mới, không tự gán Pareto hoặc chạy lại grid81. |

CSV tải về gồm tất cả dòng khớp bộ lọc, không chỉ trang đang xem. CSV có run,
source mode, block và tham số what-if liên quan. JSON kịch bản có toàn bộ tham số,
provenance, RQ1/RQ6 outputs và trajectories để tái lập.

## Nguồn dữ liệu và what-if

- Các tab lịch sử lấy đúng `--historical-results`; không tự đổi theo block mới.
- Nguồn vị thế what-if chọn **historical** hoặc **live cohort**. Nguồn live phải có
  position_rows đã được collector/model worker kiểm định. Chưa có thì báo lỗi,
  không trả kết quả giả bằng 0. Dữ liệu live giữ scope cohort và block hash.
- Kịch bản dùng `Portfolio.stress` và `defi_models.rq6.cascade` của main.
- Factor ETH-only/BTC-only/joint chỉ áp dụng RQ1. Cascade luôn shock ETH/BTC
  đồng thời theo mức shock đã chọn; điều này ghi trên giao diện và JSON.
- Sửa shock, LT, CF, bonus, depth, impact coefficient, gas và số vòng ở form.
  Các giả định khác giữ config nguồn, gồm phí DEX, oracle pass-through và impact cap.
- Mỗi lần chỉ tính một kịch bản, chạy worker riêng; GET/live collector không bị
  chặn bởi request tính. Giới hạn200 vòng; không có queue không giới hạn.
- Đổi tham số sẽ xóa kết quả what-if trên giao diện và yêu cầu tính lại. Sửa
  tham số lúc đang tính không được gắn kết quả cũ cho lựa chọn mới.
- Không sửa dataset, freeze manifest hoặc kết quả research run. Job what-if
  chỉ ở bộ nhớ (giữ8 job gần nhất), có thể tải về bằng JSON.

Live monitor poll15giây và snapshot/model cập nhật chu kỳ riêng. Bộ số offline
không vì mở dashboard mà trở thành bằng chứng realtime. Mô phỏng chưa hiệu chỉnh,
shortfall không phải bad debt on-chain; RQ3/RQ5–7 giữ nhãn exploratory.

## API

- `GET /api/lab/data`: metadata và kết quả7RQ từ run đã chọn.
- `POST /api/lab/simulate`: JSON source/factor/shock/lt_shift/close_factor/
  liquidation_bonus/liquidity_depth_usd/impact_coefficient/gas_usd/max_rounds.
  Trả202 cùng job ID; tham số số dùng fraction, không phải phần trăm.
- `GET /api/lab/job?id=...`: running/completed/failed, provenance và kết quả.
- API không cho client truyền đường dẫn file. POST giới hạn4096bytes,
  kiểm tra JSON và tham số hữu hạn/range; không nhận POST từ foreign origin.

## Kiểm tra

```powershell
& $py -m unittest discover -s tests -q
# Kiểm tra riêng backend tương tác:
& $py -m unittest discover -s tests -p test_research_lab.py -v
```

Kiểm tra so sánh trực tiếp với shared cascade, không mutate snapshot, nguồn live
thiếu không thành zero, factor riêng/cascade joint, validation và HTTP routes.
Browser QA: bộ lọc RQ2, search RQ3, khoảng96giờ RQ4, protocol exposure RQ5,
what-if RQ6 và Pareto RQ7. JavaScript được kiểm tra syntax bằng Node trong lúc phát triển.
