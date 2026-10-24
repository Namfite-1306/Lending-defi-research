# Nâng cấp nghiên cứu H1/H2/H3 — local 24/10/2026

Nhãn mới: H2 giữ nguyên là concentration; H3 = clustering/self-excitation (H4 cũ). Tên module, thư mục và số RQ giữ nguyên.

Kết quả mới giữ riêng; không ghi đè các lần chạy 7 RQ cũ. Dữ liệu thực nghiệm
được chốt đến hết 30/09/2026 UTC. Trang nghiên cứu đọc tiến độ mỗi 30 giây;
đây là kết quả lịch sử có cửa sổ cố định, không đổi nhãn thành dữ liệu thị trường live.

## Mở kết quả

- Dashboard tương tác: http://127.0.0.1:8790/research
- Stress validation: http://127.0.0.1:8790/validation
- Báo cáo: `C:\Users\HAI NAM\Finance1\defi-research\results\research_h124_20261024\BAO_CAO_H1_H2_H4_LOCAL.md`
- Trạng thái: cùng thư mục, `manifest.json` và `tests.json`.
- Snapshot/checkpoint: `C:\Users\HAI NAM\Finance1\defi-research\data\research_h124_20261024\h1`.
- Log/PID: `C:\Users\HAI NAM\Finance1\defi-research\output\research_h124_20261024`.

Code được đồng bộ sang `E:\OneDrive\Documents\GitHub\Clone\Lending-defi-research`.
Manifest của dataset trỏ về bản dữ liệu đang chạy trên ổ C, nên các lệnh chạy từ
clone E trên máy này vẫn đọc/ghi đầu ra nghiên cứu tại C. Không có dữ liệu lớn
hoặc khóa RPC được đưa vào Git. Chưa commit/push.

## Chuẩn bị và chạy lại

PowerShell, tại thư mục project C hoặc clone E:

```powershell
$py = 'C:\Users\HAI NAM\Finance1\defi-research\.venv\Scripts\python.exe'
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:TEMP = Join-Path (Get-Location) 'tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
```

Nếu cần đổi nguồn RPC, cấu hình `ETH_RPC_URLS` theo README_CRAWL.md; không ghi
API key vào code. Các thao tác này chỉ đọc blockchain.

H1: **không chạy trùng worker** nếu PID/log hiện tại vẫn tiến triển. Lệnh dưới
tiếp tục checkpoint, bỏ qua snapshot full đã xác minh hash, không thu lại từ đầu:

```powershell
& $py -m research_h124.h1 --minutes 360 --batch 400
```

Giới hạn 360 phút là ngân sách một lần chạy, không phải cam kết hoàn thành.
Nếu hết thời gian hoặc RPC lỗi, xem `scope.json` của quý tương ứng rồi chạy
lại lệnh. Quý chưa đủ luôn giữ trạng thái partial/error và bị loại khỏi phân tích.
Không xóa checkpoint. Xem tiến độ ngay cả khi report chưa kịp phân tích:

```powershell
Get-Content 'C:\Users\HAI NAM\Finance1\defi-research\output\research_h124_20261024\h1_final.stdout.log' -Tail 10
```

Collector có khóa hệ điều hành để chặn chạy trùng trên cùng checkpoint directory.
Kiểm tra nhanh adapter các phiên bản muộn (64 ví/quý, **không phải full**):

```powershell
& $py -m research_h124.preflight
```

H2: tái dựng episode/collateral và concentration; kiểm tra archive-state mẫu riêng:

```powershell
& $py -m research_h124.h2
& $py -m research_h124.h2_validate
```

H3: mô hình chính và sensitivity ở thư mục riêng:

```powershell
& $py -m research_h124.h4 --bin-minutes 5 --bootstrap 49
& $py -m research_h124.h4 --bin-minutes 15 --bootstrap 49 --no-rolling
& $py -m research_h124.h4_nb
```

Tổng hợp H1 đã full, báo cáo và kiểm tra bảo toàn kết quả cũ:

```powershell
& $py -m research_h124.report
# Hoặc theo dõi tối đa 6 giờ, tự kết thúc khi phân tích đủ 15 quý:
& $py -m research_h124.report --watch-minutes 360 --interval 60
& $py -m unittest discover -s tests -v
```

Nếu dashboard chưa chạy:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_stress_local.ps1
```

Không mở thêm server cùng port 8790. `dashboard.pid` nằm trong
`output/upgrade_20261024`; kiểm tra command line trước khi dừng đúng tiến trình.

## Mô hình và giới hạn diễn giải

**H1.** 15 cutoff cuối quý từ Q1/2023 đến Q3/2026, UTC. Universe gồm tất cả
ví đã Borrow trước cutoff, không chọn theo thanh lý tương lai. Đọc reserve,
oracle, E-mode, implementation đúng block. Đối chiếu collateral/debt/HF từng ví,
tổng dư nợ từng token, và HF trong bộ mô phỏng. Chỉ `full_snapshot_complete=true`
mới được đưa vào bảng. GHO giữ riêng repayable debt và undiscounted indexed debt;
từ Pool revision 7, HF dùng balanceOf đã áp discount, theo thay đổi GenericLogic v3.3.
Stress ETH/BTC/joint 0–60%; mapping nhóm token cùng factor 1:1 có sensitivity
chỉ WETH/WBTC. Điểm gãy/tăng USD phụ thuộc lưới shock; không coi lưới là mẫu độc lập.
Eligible debt là dư nợ có thể bị thanh lý, không phải volume bán đã xảy ra hay cascade thực thi.

**H2.** Một AbsorbDebt Comet là một episode; ghép tất cả collateral legs của
cùng borrower/transaction. Trừ credit mint ra khỏi basePaidOut, lưu khoảng do
rounding index. Định giá bằng Chainlink có trước block; không dùng peg 1 USD.
Primary: cùng kỳ 01/02–31/12/2024, USDC debt, đúng một collateral WETH/WBTC.
Extended đến Q3/2026 chỉ sensitivity do khác biệt deficit semantics. Count/USD
cùng mẫu có giá và cùng ví còn lại sau bỏ ví lớn. Chuẩn hóa HHI/Gini theo số ví;
N=1 là NA. Tuổi giá 15 phút/1h/6h/24h thay đổi coverage; phải đọc bảng coverage
cùng concentration. Spot check không thay thế replay trong từng transaction.

**H3.** Conditional binned Hawkes, không jitter timestamp on-chain. Baseline
Poisson có/không biến thị trường và Hawkes có/không biến thị trường. Train trước
2025, chọn kernel trên H1/2025, test H2/2025–Q3/2026. Market covariates dùng
thông tin có sẵn đầu bin. Dự báo một bin có điều kiện event trước đó, không phải
multi-step forecast. Có rolling-quarter refit, PIT/KS/ACF bootstrap và bin 15 phút.
Negative-binomial được bổ sung sau khi nhìn residual, nên là hậu kiểm; cần
holdout mới nếu muốn xác nhận lựa chọn model class. Bootstrap 49 lượt có độ
phân giải p-value 0.02, cố định tham số/market path. Log score tốt hơn không
đảm bảo MAE hoặc calibration tốt hơn. Không suy eta thành tỷ lệ thanh lý gây ra
theo nhân quả. Không so raw likelihood giữa bin 5 và 15 phút.

## Tài liệu

Đối chiếu BIS WP1171 và OECD No.48 bằng full text từ đơn vị xuất bản. SSRN6508318:
đã đọc metadata và bản preprint công khai do tác giả tải lên; chưa xác minh bản
sửa tháng 7 giống preprint. Xem `literature/DOI_CHIEU_TAI_LIEU.md` và kiểm tra
block/date; không khẳng định đã tái lập toàn bộ bài SSRN.

Mọi kết quả trung gian, giới hạn nguồn giá/trace/configuration và trạng thái
chưa đủ 15 quý được ghi trong báo cáo. Không được trích kết quả partial như
kết luận toàn kỳ hoặc gọi số ví mẫu nhỏ là full snapshot.
