# Stress validation & dashboard local — 24/10/2026

Mở **http://127.0.0.1:8790/validation**. Research Lab: `/lab`; live monitor: `/`.
Đây là bản local, chưa public. Giữ máy và backend chạy để tiếp tục cập nhật.

Bản đang chạy trong phiên triển khai này nằm tại
`C:\Users\HAI NAM\Finance1\defi-research`. Code nâng cấp được đồng bộ sang clone
`E:\OneDrive\Documents\GitHub\Clone\Lending-defi-research`.
Launcher có thể chạy từ clone E vì đọc đường dẫn dataset từ manifest; các lệnh
thu dữ liệu và dựng lại kết quả tương đối bên dưới chạy tại thư mục C để tiếp tục
đúng checkpoint hiện tại. Dữ liệu đã freeze và job đang chạy không được di chuyển.

## Chạy dashboard

Trong thư mục repository:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_stress_local.ps1
```

Script chọn research run đã hợp nhất nếu có, nếu không chọn full run cũ. Dataset
được đọc từ `manifest.json`. Mặc định Python dùng môi trường đã cài trên máy này;
đổi máy thì truyền `-Python 'duong-dan-python.exe'` và cấu hình lại manifest nguồn.
Không chạy hai backend cùng cổng. Khi cần chạy cửa sổ riêng: `-Port 8791`.

| Thành phần | Chu kỳ chờ mặc định | Phạm vi |
|---|---|---|
| Collector | 15 giây; catch-up nhanh hơn | Events ba giao thức đã cấu hình, 2 confirmations |
| Borrow discovery gap | Theo chunk | Chỉ Borrow Aave giữa cuối dataset và đầu live tail |
| Account census | 200 ví/lô, chờ 30 giây | Tất cả ví trong seed + Borrow đã phát hiện |
| Snapshot/model | 300 giây | Tối đa 40 ví cùng block, ưu tiên rủi ro và luân phiên |
| DEX quotes | 900 giây | 2 pool, 2 chiều, 4 size = tối đa 16 báo giá |
| Giao diện coverage | 15 giây | Đọc trạng thái, không tự fit lại mô hình |

Thời gian thực hiện job cộng thêm vào chu kỳ chờ. Các chu kỳ không phải SLA.
Census lưu khác block; `rolling_observed_debt_usd` không phải tổng dư nợ đồng bộ
toàn thị trường. Không gộp các hàng census thành một Portfolio stress.
`discovery_gap_closed` chỉ nói khoảng trống khám phá Borrow, không nói toàn bộ
event history đã nối liền. Cờ `full_market_coverage` vẫn giữ false.

## Tạo lại báo cáo kiểm chứng

```powershell
$py='C:\Users\HAI NAM\Finance1\defi-research\.venv\Scripts\python.exe'
& $py -m defi_models.stress_validation --run data/runs/recovery_20261020 --out results/stress_validation_20261024 --extra-quotes data/stress_backtests_20261024/pre_event_quotes.csv --risk-params data/stress_backtests_20261024/risk_parameters_21762264.json --pair-study
```

- `concentration_by_period.csv`: tháng/quý; borrower/collateral token;
  count toàn bộ, count cùng mẫu có giá, USD cùng mẫu có giá. Giá tối đa 1 giờ tuổi.
- `quote_curve_validation.csv`: lỗi nội suy leave-one-interior-knot-out; mặc định
  chặn nội suy có sai số kiểm tra lớn hơn 10 bps. Đây là ngưỡng kỹ thuật đặt trước,
  không phải mức ý nghĩa thống kê. Điểm quote đúng size nguồn vẫn dùng được.
- `pair_scenarios.csv`, `pair_rounds.csv`: 18 kịch bản, snapshot revision 6;
  shock 10/20/30%, impact 0/0.05, oracle delay 0/1/3 vòng.
- `evidence.json`: nguồn, hash dữ liệu và các gate chưa đạt.

Engine theo cặp trả nợ một reserve, thu một collateral mỗi action; close factor
legacy phụ thuộc HF; bonus reserve/E-mode và phí giao thức được lấy tại block
21.762.264. Liquidity, order, gas, DEX fee và oracle delay còn là giả định. Không
thay RQ6 cũ; các kết quả 7 RQ đã freeze được giữ nguyên.
Delay là vòng mô phỏng, không phải giây, heartbeat hay latency oracle đo thực.
Engine này chặn pool revision khác 6; không áp dụng quy tắc cũ lên live revision mới.
Live what-if vẫn dùng engine chính có nhãn thăm dò, chưa dùng engine mới này.

## Thu dữ liệu trước sự kiện, có checkpoint

```powershell
& $py -m defi_data.event_snapshots --seed data/runs/recovery_20261020/processed/borrower_universe.csv --plan results/stress_validation_20261024/backtest_event_plan.csv --out data/stress_backtests_20261024 --minutes 30 --batch 100 --events 5
& $py -m defi_data.stress_quotes --plan results/stress_validation_20261024/backtest_event_plan.csv --out data/stress_backtests_20261024 --events 5
& $py -m defi_data.stress_risk_parameters --snapshot data/runs/recovery_20261020/full_snapshot_21762264 --out data/stress_backtests_20261024/risk_parameters_21762264.json
```

Không chạy hai snapshot collector trên cùng output cùng lúc. Chạy lại cùng lệnh
sau khi job trước dừng sẽ tiếp tục từ SQLite, bỏ qua ví đã commit. Budget được
kiểm tra giữa các lô nên một lô chậm có thể làm vượt thời gian đặt.
Theo dõi `data/stress_backtests_20261024/<ngay>/progress.json` và dashboard.
Cohort dùng Borrow trước cutoff, không chọn từ danh sách ví bị thanh lý tương lai.
Cutoff là block ngay trước liquidation đầu ngày được chọn, không phải 00:00 UTC.
Các ngày được chọn theo số event cao nhất sau quan sát; chưa phải thiết kế đăng ký
trước hay một tập holdout độc lập. Snapshot đầy đủ chưa đồng nghĩa backtest hoàn tất.

Nguồn mới nằm ngoài dataset đã freeze. Muốn dùng để nghiên cứu chính thức cần
hoàn tất scope, HF reconciliation, audit và freeze riêng, không chèn vào manifest cũ.

## API và giới hạn

- `GET /api/universe`: số ví đã biết/đã quét/còn mới, discovery và lỗi job.
- `GET /api/liquidity`: quotes, block/hash, coverage, freshness, lỗi worker.
- `GET /api/backtests`: tiến độ snapshot và quote collection.
- `GET /api/validation`: bảng kiểm chứng lịch sử, không phải số realtime.
- API what-if cũ tại `/api/lab/simulate` giữ nguyên.

Quote chỉ hợp lệ tại đúng pool/block/chiều token và trong size đã đo; không cộng
phí DEX lần hai, không mặc định token stablecoin bằng 1 USD, không tự đưa quote
live vào cascade lịch sử. Thiếu quote không được thay bằng zero impact.
`QuoteCurve` chặn ngoại suy, sai block, sai chiều và nội suy vượt gate.

## Phần còn lại để hoàn tất mục tiêu nghiên cứu

1. Hoàn tất các snapshot trước sự kiện và định lượng coverage dữ liệu giá.
2. Thu đường đi oracle/DEX trong suốt các cửa sổ, không chỉ block khởi đầu.
3. Adapter thanh lý theo từng revision; kiểm chứng từng giao dịch, rounding,
   collateral/debt selection, E-mode, dust, GHO và chi phí/routing.
4. Hiệu chỉnh trên tập train rồi backtest sự kiện holdout; báo cáo sai số và độ bất định.
5. Đo vận hành nhiều ngày, kiểm tra mất mạng/khôi phục thực tế và độ trễ theo RPC.

Chưa đủ căn cứ kết luận cascade toàn hệ thống đã được kiểm chứng hoặc toàn bộ vị
thế thị trường được cập nhật realtime. Đã có test checkpoint/reorg và lỗi nguồn;
test tự động không thay thế việc quan sát vận hành liên tục nhiều ngày.
