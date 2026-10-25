# Lượt sửa H1/H2/H3 — 24/10/2026

H1 = price stress; H2 = concentration; H3 = clustering/self-excitation (module h4 cũ).
Mở http://127.0.0.1:8790/research#repair để xem **Output mới riêng**.

## Đầu vào và bảo toàn

- Dùng panel prefix đã kiểm chứng: 27/01/2023 → trước 02/06/2026 05:05 UTC.
- Episodes/legs Comet đã normalize và đối chiếu; không crawl lại hoặc sửa nguồn gốc.
- Output: `results/research_h123_repair_20261024/` tại canonical root đọc từ manifest.
  Trên máy hiện tại canonical root nằm ở C, kể cả khi chạy source từ clone E.
- Bảng kết quả cũ giữ nguyên checksum. Lượt thử đầu của repair H3 được giữ tại
  `h3_initial_attempt/`; bảng chính của lượt sửa nằm tại `h3/`.

## Chạy lại

Trong thư mục repository:

```powershell
$py = 'C:\Users\HAI NAM\Finance1\defi-research\.venv\Scripts\python.exe'
& $py -m research_h124.repair_h1
& $py -m research_h124.repair_h2
& $py -m research_h124.repair_h3 --bootstrap 199
& $py -m research_h124.repair_diagnostics
& $py -m research_h124.repair_report
```

Không chạy trùng cùng worker H3. B=199 tăng độ phân giải residual so với B=49;
có thể dùng B=499 khi kiểm chứng cuối, nhưng không tăng B để tìm p-value đẹp.
Chạy lại sẽ cập nhật output **của lượt sửa này**, không sửa output gốc/V2.
Dashboard chỉ đọc file, không tự huấn luyện. Khởi động như hướng dẫn cũ bằng
`powershell -NoProfile -File scripts/start_stress_local.ps1` khi server chưa chạy.

## H1 còn bị chặn

3 nguồn public đều trả HTTP 403/Cloudflare 1010 trong lần kiểm tra mới nhất.
Q2/2026 đã quét 39.600/82.494 địa chỉ; Q3/2026 chưa hoàn thành census 86.631.
Checkpoint vẫn giữ nguyên. Chưa mua nguồn, chưa dùng tài khoản, chưa tự thay danh tính
client để né chặn. Khi nguồn được phép hoạt động trở lại mới resume `research_h124.h1`.
Nguồn này cần historical `eth_call` và block headers tại các cutoff, không chỉ logs.

Sensitivity H1 offline: 546 dòng trên 13 full quý, mẫu số trước/sau shock và newly
eligible; không thay thế hai quý thiếu. Có bộ chọn shock/factor/mapping trong mục repair.

## H2 mới thêm gì?

- `count_all` = mọi matched events trong cùng scope, không lọc giá USD.
- Native USDC upper/lower = amount token / 10^6, không giả định USDC = USD.
- USD và count-priced giữ cùng support riêng cho mỗi policy 1h/6h/24h/feed-policy.
- Feed-policy là **sensitivity giả định**: USDC tối đa 26h trong trạng thái bình
  thường; tối đa 1h khi đã có prior-block quote lệch peg >0,5% trong 24h trước.
  Không dùng alert tương lai; không khẳng định đây là heartbeat/SLA chính thức.
- Nới tuổi giá không tạo market quote mới. Depeg không quan sát giữa hai round,
  market prices độc lập và beneficial owner identity vẫn chưa giải quyết.
- Metric/drop/window/token có bộ lọc dashboard riêng. Ranking loại ví theo metric
  đang xem; không giả định cùng USD-ranking với bảng cũ.
- Bootstrap 199 lần theo ngày có events cho full-count và native upper, chưa loại ví.
  Ngày không có events và bất định từ đo lường/owner không nằm trong interval này.

Scope vẫn là USDC debt, một collateral leg WETH hoặc WBTC và cùng calendar window.
Không biến coverage 100% trong matched scope thành coverage toàn DeFi.

## H3 đã thay đổi gì?

12 model variants: exp ridge / softplus / softplus + background 7 ngày ×
Poisson/NB × có/không short-term excitation. Background dài hạn dùng lịch sử
count có sẵn trước bin, không phải TVL/HF thực đo. Link softplus tuyến tính ở đuôi
dương, không clipping output. Feature scaling dùng train; penalty/kernel chọn validation.

Validation count-ratio 0.5–2 là screen khóa cho lượt sửa, không phải kiểm định đã
đăng ký trước. Model không qua screen vẫn giữ làm comparator có cờ false, không
được chọn làm model chính. Kết quả trước đây đã xem test nên lượt sửa vẫn exploratory.

Residual cho model validation chọn, đối chứng cùng loại và pair Poisson/background
động; bootstrap mô phỏng lại slow/fast states nếu model sử dụng. Không nối ACF qua
gaps. Rolling ghi `partial_quarter` hoặc `no_scored_bins`, không báo score=0 là đạt.
7-day block resampling giữ fixed fits, không phải causal/parameter inference.

Xem `h3/candidates.csv`, `model_comparison.csv`, `residuals.json`, `extrapolation.csv`,
`rolling_quarter_scores.csv`, `protocol.json` và `BAO_CAO_SUA_H1_H2_H3.md`.
Total count tốt không đủ: residual vẫn không đạt thì chưa dùng live forecasts.
