# Bàn giao Người 2 — RQ1 và RQ4

Cập nhật 22/10/2026 sau tích hợp commit mô hình từ GitHub. Người 2 phụ trách stress test RQ1 và clustering/self-excitation RQ4; Người 4 duyệt kết quả theo bảng phân công. Baseline đã có trong `defi_models/`; các bước dưới đây là checklist kiểm chứng và mở rộng trước kết luận nghiên cứu, không phải yêu cầu viết lại toàn bộ mô hình.

## Điểm xuất phát thực tế

- `pipeline.stress()` đã có lưới stress tĩnh 36 kịch bản WETH/WBTC trên mẫu vị thế đã đối chiếu. Dư nợ có HF < 1 là eligible debt; chưa phải khối lượng thanh lý thực thi hoặc nợ xấu.
- `normalize()` đã có panel đếm theo giờ; các module recovery có mã xuất lịch sử, giá và snapshot. `defi_models/analyses.py` có RQ1/RQ4, `defi_models/statistics.py` có Poisson/Hawkes và chronological holdout. Hawkes hiện chưa có price covariates; Poisson đang dùng returns cùng giờ nên phải phân biệt mô tả và dự báo.
- Pilot `stress_20250203_smoke` đã chạy hoàn tất: 4.294 sự kiện của ba giao thức, 14 CSV, audit trực tiếp ngày 22/10/2026 đạt 15/15 nhóm. Cửa sổ 3 giờ và mẫu 5 ví phù hợp kiểm thử/mô tả pilot, chưa đủ cho kết luận toàn thị trường hay fit RQ4.
- Bộ mở rộng `expansion_20260930`/`recovery_20261020` cần dữ liệu và audit riêng; chưa được chứng nhận toàn kỳ trong các lần sửa này. Không suy ra hoàn tất từ việc có code, thư mục hoặc báo cáo cũ.
- Sau tích hợp: 108 test đạt trong `.venv` có NumPy/SciPy, gồm các test mô hình; đã kiểm tra trực tiếp pilot và batch E-mode của 3 ví tại block 21762264. Các kiểm tra này chưa chứng nhận coverage toàn kỳ hoặc kết quả nghiên cứu chính thức.

## 1. Chốt đặc tả và chuẩn bị mã khi đang chờ dữ liệu — D1-N2

Dùng `configs/models.example.json` làm mẫu, chốt bản cấu hình riêng cho thí nghiệm của Người 2 và đặc tả đầu vào. Xem [README_MODELS.md](../models/README_MODELS.md) để dùng đúng CLI đã có; chưa cần tạo pipeline RQ1/RQ4 song song trong `defi_data/`.

| Nội dung | RQ1 | RQ4 |
|---|---|---|
| Phạm vi khởi đầu | Aave V3 Ethereum, snapshot trước stress | Từng hợp đồng/giao thức đã chọn; fit riêng trước khi gộp |
| Đại lượng chính | Số/tỷ lệ ví HF < 1; tổng/tỷ lệ dư nợ đủ điều kiện | Số liquidation và mức clustering theo thời gian |
| Kịch bản/độ phân giải | Bắt đầu lưới 0 đến -50%, bước 10%; làm mịn quanh ngưỡng | Baseline panel 1 giờ; kiểm tra độ nhạy 5 phút nếu coverage và số event cho phép |
| Quy tắc thời gian | Cohort và cấu hình chỉ dùng thông tin có tại snapshot | Feature dự báo chỉ có sẵn trước đầu bin cần dự báo |
| Đối chiếu | HF và tổng nợ/thế chấp cùng block | Panel khớp event gốc và coverage; không biến missing thành 0 |

Lưu địa chỉ token, quy tắc mapping ETH/BTC và cách xử lý tài sản phái sinh trong cấu hình. Không chỉ dựa vào symbol. Chốt trước tiêu chí chọn snapshot, định nghĩa ngưỡng stress, train/validation/test theo thời gian và tiêu chí đánh giá; không chọn lại sau khi xem kết quả.

Đầu ra nghiệm thu: hai cấu hình, schema đầu vào, định nghĩa đại lượng và bản đặc tả được Người 4 duyệt. Có thể làm bước này và viết mã với fixture giả ngay; kết quả từ fixture phải ghi rõ là synthetic.

## 2. Nhận dữ liệu có bằng chứng từ Người 1 — trước D2-N2/D3-N2

Yêu cầu Người 1 bàn giao:

1. Run hoàn tất, manifest/hash/coverage và log validation. Pilot chỉ dùng kiểm thử; để fit RQ4, chuẩn bị cửa sổ liên tục tối thiểu 30 ngày làm mốc khởi đầu, có giai đoạn thường và stress. Mốc này là điều kiện vận hành ban đầu, không bảo đảm đủ thông tin để fit Hawkes.
2. Cohort người vay được dựng từ lịch sử trước cutoff; snapshot Aave cùng block cho balances, risk debt, oracle, LT/E-mode và Pool revision. Giữ ví sai đối chiếu riêng, báo số ví và phần dư nợ bị loại.
3. Sự kiện có `(block, transaction_index, log_index)`, UTC và economic meaning. Đếm `LiquidationCall`, `AbsorbDebt`, `Liquidate` riêng; không cộng thêm `AbsorbCollateral`/`BuyCollateral` vào số liquidation khoản vay.
4. Giá schema v2: `stamp` gốc, `available_stamp`, block/transaction/log index và cờ stale; gas/oracle controls nếu có. Không thay missing bằng 0 hoặc mặc định stablecoin luôn bằng 1 USD.
5. Bảng phiên bản dữ liệu ghi run ID, cutoff, phạm vi, nguồn giá, các khoảng thiếu và giới hạn mẫu. Với bộ recovery, kiểm tra cả audit cấu trúc và audit on-chain; trạng thái hoàn tất tải không tự chứng minh chính xác.

Người 2 kiểm tra schema/coverage và ký nhận phạm vi trước khi chạy mô hình. Nếu chưa nhận đủ, tiếp tục chuẩn bị mã với fixture, chưa công bố kết luận thực nghiệm.

## 3. Hoàn thiện baseline RQ1 — D2-N2/D3-N2

Dùng `defi_models.core.Data.snapshot()` và `Portfolio` cùng `defi_models.analyses.rq1()`; các lớp này đã có kiểm tra snapshot, freeze hashes và baseline HF. Schema của `positions.csv` pilot và `full_snapshot_21762264/positions.csv` khác nhau, không truyền thẳng vào nhau. Kiểm chứng adapter đọc đúng decimals, `validation_passed`, effective LT, risk debt và Pool revision; chuỗi CSV `"False"` phải chuyển thành boolean đúng. Mapping mô hình hiện dựa vào symbol cấu hình: Người 2 cần kiểm tra theo địa chỉ và lưu mapping/giả định.

Các việc cần làm theo thứ tự:

1. Tái dựng tổng collateral/debt/HF tại shock 0; đối chiếu với hợp đồng cùng block, dùng tolerance đã chốt 1e-4 và quy tắc làm tròn theo revision. Không dùng repayable debt sau discount thay risk debt khi tính HF.
2. Chạy cú sốc ETH riêng, BTC riêng và đồng thời. Áp cú sốc lên cả collateral lẫn debt có cùng risk factor. Tài sản ngoài mapping giữ cố định và ghi giả định rõ; depeg/basis là sensitivity riêng.
3. Xuất số ví at risk, tỷ lệ trên cohort hợp lệ, eligible debt và tỷ lệ trên tổng nợ hợp lệ. Giữ tổng nợ/cohort làm mẫu số nhất quán trong cùng thí nghiệm.
4. Định nghĩa ngưỡng trước khi tìm: ví dụ cú sốc nhỏ nhất trong lưới khiến tỷ lệ dư nợ at risk vượt mốc đã chốt. Nếu ngưỡng nằm giữa hai điểm lưới, báo khoảng hoặc chạy lưới mịn; không báo độ chính xác vượt độ phân giải.
5. Đối chiếu thủ công một số ví và nhờ Người 4 kiểm tra công thức/đơn vị. Chỉ kiểm tra tính đơn điệu trong kịch bản có điều kiện bảo đảm; khi cả debt và collateral cùng giảm giá, HF không nhất thiết giảm.

Đầu ra hiện có: `stress_curve.csv`, `factor_mapping.csv`, `summary.json`. Bổ sung bảng theo tài khoản/ngưỡng nếu cần cho báo cáo; ghi mẫu số, exclusions, giả định và hashes đầu vào. Điểm gãy mô tả từ lưới/hồi quy hiện tại chưa thay thế kiểm định ngưỡng.

## 4. Dựng baseline RQ4 — D2-N2/D3-N2

Dùng `defi_models.analyses.rq4()` và các estimator trong `defi_models/statistics.py`. Dependency mô hình đã được tách ở `requirements-models.txt` (NumPy/SciPy); runtime dữ liệu vẫn chỉ dùng standard library. Kiểm chứng baseline và bổ sung các phần còn thiếu theo thứ tự sau.

1. Đồng bộ liquidation panel với ETH/BTC returns, độ biến động, gas và các cờ oracle/stale trong phạm vi dữ liệu có thật. Dùng feature trễ cho bài toán dự báo; nếu dùng biến cùng kỳ để mô tả, ghi riêng mục tiêu và không gọi là dự báo ngoài mẫu.
2. Phân biệt giờ chưa deployment/thiếu coverage với giờ đã quan sát đủ nhưng không có event. Với bin quan sát một phần, dùng exposure/offset phù hợp hoặc loại theo quy tắc đã chốt.
3. Mô tả inter-arrival, phân phối count, dispersion, autocorrelation và các wave. Nhiều event cùng block có cùng timestamp: giữ multiplicity, không thêm jitter tùy ý để ép thành event liên tục.
4. Fit Poisson cường độ hằng làm baseline, sau đó Poisson có price/gas controls. Báo residuals và overdispersion; có thể thêm negative binomial làm đối chứng khi cần.
5. Chia train/validation/test theo thứ tự thời gian, giữ lại cửa sổ stress và giai đoạn thường; không random split các giờ. Khi khởi tạo lịch sử ở test, chỉ dùng sự kiện trước thời điểm dự báo.

Đầu ra hiện có: `hawkes_candidates.csv`, `hourly_predictions.csv`, `summary.json`. Bổ sung panel/bảng metrics, hình count/dispersion/residual và split metadata khi nghiệm thu. Cửa sổ pilot 3 giờ chỉ dùng smoke test, chưa đủ fit và đánh giá mô hình.

## 5. Độ nhạy RQ1 và mô hình tự kích thích RQ4 — D4-N2

- RQ1: lặp trên nhiều cutoff độc lập trước stress; so sánh E-mode/không E-mode, mapping phái sinh/depeg, loại ví lỗi và các lưới shock. Không dùng việc ví bị thanh lý sau cutoff để chọn cohort baseline.
- RQ4: so sánh mô hình có self-excitation và price controls với baseline dùng cùng phạm vi/thông tin. Chọn mô hình event-time xử lý được ties hoặc dùng phiên bản đếm theo bin; ghi rõ lựa chọn. Nếu dùng exponential Hawkes, kiểm tra tính dương, ràng buộc ổn định phù hợp và độ nhạy tham số/khởi tạo.
- Kiểm tra khả năng nhận diện tham số, residuals và độ nhạy theo bin/cửa sổ. Không coi clustering quan sát được là bằng chứng tự kích thích hay quan hệ nhân quả.

Nghiệm thu: các mô hình được so sánh bằng cùng bài toán dự báo. Nếu khác biểu diễn event-time/count, dùng dự báo count trên cùng bin hoặc thước đo tương thích; không so trực tiếp hai log-likelihood khác đơn vị. Tham số nằm biên hoặc không ổn định phải được nêu trong kết luận.

## 6. Kiểm định giữ lại và bàn giao — D5-N2 đến D7-N2

1. Khóa code/config/data hashes trước lần chạy chính. Đánh giá trên test chưa dùng chọn mô hình; báo lỗi dự báo, calibration, độ nhạy và khoảng bất định. Nếu bootstrap, lấy block thời gian phù hợp thay vì coi các event phụ thuộc là độc lập.
2. Xuất bảng/hình RQ1 và RQ4 cùng limitations: phạm vi hợp đồng, selection, snapshot, price mapping, timestamp resolution, missing/stale và các giả định mô hình.
3. Người 4 kiểm tra chéo kết quả. Người 2 gửi Người 1 các CSV/hình/config/log để tích hợp dashboard; chưa cần Người 2 làm cascade RQ6 hay tối ưu chính sách RQ7.
4. Viết phần báo cáo, chốt slide và diễn tập. Mỗi kết luận phải truy được về run, cấu hình và bảng kết quả; phân biệt stress tĩnh, mô tả và dự báo.

## Lệnh kiểm tra và các bước chạy lại có sẵn

Chạy trong thư mục dự án với Python >=3.11. Nếu `python` chưa có trên PATH, dùng Python của IDE hoặc interpreter đã kiểm thử trên máy này:

```powershell
$pythonExe = 'C:\Users\Chou Chou\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $pythonExe -m unittest discover -s tests -v
```

Pilot đã có kết quả audit đạt. Nếu cần tạo lại/mở rộng dữ liệu, Người 1 dùng endpoint lịch sử đã kiểm chứng; với pipeline, đặt `ETH_RPC_URLS` trong môi trường rồi chạy:

```powershell
& $pythonExe -m defi_data.pipeline
& $pythonExe -m defi_data.validate_run stress_20250203_smoke
```

Sau khi có pilot hợp lệ, `defi_data.expansion window` mới được phép qua cổng đối chiếu. Với bộ recovery đã có đủ các đầu vào lịch sử/bounds/configuration, chạy lại theo thứ tự:

```powershell
& $pythonExe -m defi_data.recovery_prices
& $pythonExe -m defi_data.recovery_features
& $pythonExe -m defi_data.recovery_trace_funding
```

Các lệnh recovery vẫn có endpoint cố định trong module; không giả định `ETH_RPC_URLS` điều khiển mọi lệnh. Sau khi tạo lại đầu ra, chạy lại các audit tương ứng và khóa manifest mới; không dùng freeze/hash cũ cho CSV đã thay đổi. Đây là hướng dẫn chạy tiếp, chưa được chạy với mạng thật trong lần sửa lỗi này.
