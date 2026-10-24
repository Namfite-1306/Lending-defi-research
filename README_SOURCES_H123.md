# H1/H2/H3 — kỳ chính đến 31/03/2026

Theo quyết định của nhóm, bỏ Q2 và Q3/2026 khỏi phân tích chính. H1 có **13/13 full snapshot** từ Q1/2023 đến Q1/2026, kiểm tra borrower universe tại thời điểm, full gate và hash. Kết quả cũ vẫn giữ nguyên.

Kết quả mới: `results/research_h123_sources_20261024/`. Cache nguồn: `data/research_h123_sources_20261024/`. Trên máy hiện tại, canonical data/results nằm ở `C:\Users\HAI NAM\Finance1\defi-research`; clone E dùng chung dữ liệu này. Source chưa phải bản portable kèm toàn bộ dataset.

## Đã bổ sung

- **H1:** `h1_primary_scope.json` kiểm tra 13 quý. Snapshot cuối quý chưa thay thế lịch sử health factor theo phút.
- **H2:** Kraken public USDC/USD Trades; lưu trang gốc/hash, kiểm tra cursor/thời gian/ID. Ghép trade trước event với độ trễ giả định 5 giây; so full count/native USDC với USD trên mẫu giá 60/300/3.600 giây và oracle-market common support. Không thay giá thiếu bằng 1 USD. Nguồn một sàn, thời gian nhận giá thực chưa xác minh. Native USDC lượt mới dùng nợ upper estimate; sensitivity upper/lower Comet nằm ở output repair trước.
- **H3:** Borrow/Repay/Supply/Withdraw 24 giờ trước, tỷ lệ borrow/repay; độ trễ khả dụng giả định 30 giây. Đây là số giao dịch hoạt động, chưa phải TVL/nợ tồn/HF. Hurdle logistic + zero-truncated negative binomial tách xác suất có thanh lý và quy mô khi có sự kiện; so constant/market/activity/activity+history. Ridge chọn bằng validation; test 01/07/2025–31/03/2026, rolling từng quý và PIT/residual.

H3 mới là kiểm chứng dự báo bổ sung, chưa phải structural Hawkes. Test đã được xem ở các lượt trước, cần dữ liệu tương lai độc lập trước khi duyệt forecast. Residual hiện vẫn bác bỏ mô hình; chưa nhận diện nhân quả.

## Chạy lại

Trong thư mục repository, dùng venv đã cài dependencies. PowerShell trên máy hiện tại:

```powershell
$py = 'C:\Users\HAI NAM\Finance1\defi-research\.venv\Scripts\python.exe'
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
& $py -m research_h124.market_prices --minutes 60 --max-requests 3000
& $py -m research_h124.activity_controls
& $py -m research_h124.hurdle_model --replications 499
& $py -m research_h124.hurdle_rolling
& $py -m research_h124.primary_comparison
& $py -m research_h124.source_audit
& $py -m research_h124.source_analysis
& $py -m unittest discover -s tests -v
```

Nếu báo `partial_source_gap`, lượt quét đã kết thúc với trang nguồn có khoảng trống chưa xác minh; raw page vẫn giữ nhưng không tính coverage. Không gọi lặp vô hạn cùng khoảng trống.

Collector có checkpoint và khóa; chạy lại để tiếp tục, không chạy hai collector cùng lúc. HTTP403/timeout/hết ngân sách được ghi là thiếu, không tự dùng nguồn trả phí. `market_progress.json` cho biết đã quét đủ cửa sổ chưa; `market_data_readiness.json` cho biết số events có giá đủ tươi.

Lệnh model ghi đè **output mới của lượt này** khi chạy lại. Muốn giữ thêm một lần chạy để đối chiếu, sao lưu thư mục kết quả lượt này trước khi refit. Các bộ cũ `research_h124_*`, `research_h123_repair_*` được giữ riêng.

## Dashboard

Chạy `powershell -NoProfile -File scripts/start_stress_local.ps1`, mở **http://127.0.0.1:8790/research#sources**.

1. Đọc kỳ chính và tiến độ nguồn trước khi xem kết quả.
2. H2: chọn kỳ/token/metric. Count/native toàn mẫu không cần tuổi giá. USD/priced-count dùng mẫu có giá. Chỉ so cùng kỳ/token/support/metric; ít ví có thể cho concentration bất ổn.
3. H3: xem expected/observed, log-score, residual, rolling và bảng cùng kỳ test. Đổi bộ lọc không refit.
4. Các mục V2/repair bên dưới giữ output cũ và kỳ riêng. Research page là lịch sử cập nhật cache, chưa phải forecast real-time.

Báo cáo: `BAO_CAO_NGUON_VA_KET_QUA_H1_H2_H3.md`. Audit: `source_audit.json`, `tests.json`. Chưa dùng nguồn có tài khoản hoặc trả phí.
