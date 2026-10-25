# Research v2 — H1/H2/H3, cascade và dashboard local

H2 giữ nguyên là concentration; H3 = clustering/self-excitation (H4 cũ). Tên module/thư mục và số RQ giữ nguyên. Hướng dẫn: README_DASHBOARD_VI.md hoặc http://127.0.0.1:8790/guide.

Kết quả v1/dataset gốc được giữ nguyên. Source chạy tại project C và đồng bộ
sang clone E; không commit/push. Chỉ dùng nguồn public, chưa dùng tài khoản/trả phí.

- Dashboard: http://127.0.0.1:8790/research
- Báo cáo: `C:\Users\HAI NAM\Finance1\defi-research\results\research_h124_v2_20261024\BAO_CAO_NANG_CAP_V2.md`
- Kết quả mới: cùng thư mục `research_h124_v2_20261024`.
- Dữ liệu/checkpoint: `C:\Users\HAI NAM\Finance1\defi-research\data\research_h124_v2_20261024`.
- Log/PID: `output/research_h124_v2_20261024` trong project C.

## Chạy lại hoặc tiếp tục

Chạy tại `C:\Users\HAI NAM\Finance1\defi-research`, hoặc clone E trên máy này
với manifest vẫn trỏ về dataset C. Không chạy thêm worker khi worker cũ đang hoạt động.
H1/header/cascade snapshot dùng khóa hệ điều hành để chống chạy trùng.

```powershell
$py='C:\Users\HAI NAM\Finance1\defi-research\.venv\Scripts\python.exe'
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:TEMP=Join-Path (Get-Location) 'tmp'
$env:TMP=$env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
```

Thu tiếp 15 snapshot quý, giữ checkpoint của lần trước:

```powershell
& $py -m research_h124.h1 --minutes 360 --batch 400
```

Kiểm tra khả năng nguồn và Comet theo thứ tự borrower:

```powershell
& $py -m research_h124.source_audit
& $py -m research_h124.h2_v2
& $py -m research_h124.h2_v2 --all-episodes
```

H3 — header availability, gas và oracle panel:

```powershell
& $py -m research_h124.h4_data --minutes 180 --batch 20
& $py -m research_h124.h4_extended
& $py -m research_h124.h4_extended_nb
# Variant bổ sung utilization/lãi vay hourly, giữ riêng kết quả core:
& $py -m research_h124.h4_utilization --wait-minutes 120 --minutes 180
& $py -m research_h124.h4_extended --with-utilization
& $py -m research_h124.h4_extended_nb --with-utilization
```

Collector header có tối đa hai requests đồng thời, SQLite commit tuần tự và
checkpoint sau mỗi batch. Hết budget hoặc RPC lỗi thì chạy lại để tiếp tục.
Panel bị chặn nếu bất kỳ block availability của oracle update nào còn thiếu.
Các lệnh estimate phải đợi data readiness đạt gate; không dùng panel thiếu làm kết quả full.

Các biến đã triển khai: oracle-implied down returns ETH/BTC 5m/1h, độ lớn lần
update gần nhất, tuổi oracle; base fee tại ETH-oracle block gần nhất kèm tuổi
header; positive/negative stablecoin deviations; Pool Upgraded regimes; volatility
24h và chu kỳ giờ. Mọi update chỉ dùng khi block timestamp **nhỏ hơn** đầu bin.

Gas này là sampled gas, không phải median toàn bộ block trong 5 phút. Tuổi tối
đa: ETH/BTC 2h, gas 1h, stablecoin 36h; xem coverage. Không giả rằng oracle price
không đổi đồng nghĩa giá thị trường không đổi. Không mặc định stablecoin =1 USD.
Context riêng theo quý có non-ETH/BTC oracle collateral basket, HF stock,
WETH/USDC borrow usage và Uniswap spot basis wstETH/ETH, WBTC. Basis wstETH đã
điều chỉnh stEthPerToken; chọn pool có active liquidity cao nhất trong bốn fee
tiers của cùng cặp. Đây là spot tại quý, không TWAP hay toàn thị trường.
Không nội suy những quan sát này thành 5 phút. Full-frequency collateral basket,
basis, DEX depth và HF queue chưa đủ không được điền giả để đưa vào fit.

Collector reserve hourly dùng Multicall tách theo đúng block; đọc provider/config,
actual hoặc virtual liquidity đúng phiên bản. Không thay utilization bằng debt/supply.
WETH/USDC có borrow usage, borrow APR và tuổi nguồn, tối đa 2h. Variant `h4_util`
thêm nhóm biến này, tái fit mọi baseline trên cùng sample trong variant. Không
so raw likelihood core/utilization nếu common bins khác nhau. Coordinator tự
chạy variant và NB sau khi chuỗi reserve hoàn tất.

H3 extended: 5 nhóm biến × Poisson/Hawkes trên **cùng common bins**. Chọn kernel
và nhóm theo validation, refit train+validation, báo cáo test và rolling quarters.
NB dùng cùng nhóm được chọn và cùng bins. Residual bootstrap dùng mọi segment
hợp lệ, điều kiện trên history trước segment; ACF không nối qua khoảng thiếu.
Đây là nâng cấp exploratory sau khi
đã xem test cũ, không phải holdout xác nhận mới. Dummies chỉ xuất hiện trong test
không có hệ số được nhận diện. Residual giữ nguyên kết quả thất bại nếu có.

Cascade — dữ liệu trước sự kiện, quotes và sensitivity:

```powershell
& $py -m research_h124.cascade_data --minutes 360
& $py -m research_h124.cascade
```

Năm ngày được chọn hồi cứu theo thanh lý lớn. Borrower vẫn dùng universe trước
cutoff, không chỉ những ví bị thanh lý sau đó. Snapshot full cần qua HF/aggregate
debt/freeze checks. Quotes đo ở pre-event, +15m, +60m, hai pool và bảy sizes/hai chiều;
đây là sparse path, không phải full continuous liquidity. Collector đợt mới không
chạm dữ liệu `data/stress_backtests_20261024` cũ.

Engine mới phân biệt close factor trước/sau revision 7, dust, E-mode bonus,
protocol fee, deficit và giới hạn capacity/ordering. Core rules tham chiếu mã
[Aave v3.3](https://raw.githubusercontent.com/aave-dao/aave-v3-origin/v3.3.0/src/contracts/protocol/libraries/logic/LiquidationLogic.sol).
Đây là float economic approximation: grace-period/sentinel, exact EVM và mọi
quy tắc token chưa được replay đầy đủ. Fitted square-root impact là sensitivity,
không phải báo giá có thể thực thi ở block khác. Gas/fee/capacity/ordering vẫn là
giả định; direct-route fee lấy từ pool. Chỉ nhận cặp collateral/debt có route
được đo hoặc cùng token không cần swap; thiếu route bị loại, không thay zero impact.

Impact fit dùng các ngày train, quotes các ngày muộn giữ riêng. Có/không feedback
được so theo cùng snapshot và shock. Actual oracle path được dựng khi headers
đủ; đối chiếu cùng active borrower cohort và direct routes. Đường giá thực đã có
thể chứa feedback của thanh lý, nên là conditional-path diagnostic, không phải
nhận diện cú sốc ngoại sinh/nhân quả. `historically_calibrated` và `end_to_end_backtest_passed` vẫn false
cho đến khi mọi gate thực sự đạt, không tự đổi nhãn vì script đã chạy xong.

Coordinator tự tính khi dữ liệu đủ, cập nhật báo cáo tối đa 6 giờ:

```powershell
& $py -m research_h124.runner_v2 --minutes 360
```

Nó không chạy lại mô hình mỗi lần bấm filter; failed stages được lưu trong
`worker_status.json`. Nếu estimator lỗi, sửa nguyên nhân rồi chạy lại module
tương ứng hoặc khởi động lại coordinator. Không coi exception là completed.

Audit ba phần và kiểm thử:

```powershell
& $py -m research_h124.audit_v2 --network
& $py -m research_h124.report_v2
& $py -m unittest discover -s tests -v
```

Audit gồm cấu trúc/header chain, spot check RPC và hợp đồng dữ liệu nghiên cứu,
kèm hash đầu ra cũ. Đạt audit kỹ thuật không đồng nghĩa residual hay cascade
đã đạt calibration. `tests.json` ghi số test chạy thực tế khi nghiệm thu.

## Dashboard và giới hạn real-time

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_stress_local.ps1
```

Tái sử dụng server cũ, không mở thêm cùng cổng. Trang `/research` đọc lại 30s;
live market collector vẫn có chu kỳ riêng. Bộ lọc V2 và cascade đọc kịch bản đã
tính, có CSV download và metadata. Giao diện không biến historical results thành
live forecasts. Live cohort 40 ví và rolling census khác block vẫn không phải
snapshot đồng bộ toàn thị trường.

Nếu cần dừng worker trên Windows, kiểm tra PID và command line rồi dừng cả child
Python thuộc launcher đó; không dừng mọi `python.exe` trên máy. Khởi động helper
ở cửa sổ ẩn khi chạy nền. Lỗi chia sẻ file Windows được retry rename có giới hạn;
không truncate dữ liệu đã công bố để né file lock.

Chỉ đề xuất nguồn trả phí/tài khoản sau khi ghi method, block/time range,
workload, khả năng public đã kiểm tra và phần kết quả vẫn thiếu. Probe thành công
một mẫu không phải cam kết toàn kỳ hoặc tốc độ thu.

## Khi nguồn RPC trả 403

Đợt kiểm tra mới nhất nằm trong `results/research_h124_v2_20261024/source_access.json`.
Cả ba nguồn cấu hình trả Cloudflare 1010 cho `eth_chainId`; chưa có bằng chứng
đổi sang gói archive trả phí giải quyết được lỗi truy cập này. Không đổi danh tính
client hoặc né chặn. Các checkpoint vẫn giữ nguyên; khởi chạy lại collector khi
quyền truy cập nguồn đã khôi phục. Collector dừng gửi thêm batch sau 3 lỗi network
liên tiếp; authorization/rate limit dừng ngay, tối đa 2 request đang chạy.

Có thể kiểm chứng phần kỳ liên tục đã xác minh bằng:

```powershell
python -m research_h124.offline_v2
```

Lệnh không gọi RPC. Panel `h4_prefix_panel_5min.npz`, model `h4_prefix/` và
`h4_prefix_nb/` là output riêng; dừng trước update đầu tiên thiếu header và bỏ
bin chưa kết thúc. Không coi đây là kết quả đủ tới 30/09/2026. Dashboard có bộ
chọn phần kỳ với ngày kết thúc. Không so raw likelihood với variant khác sample.
