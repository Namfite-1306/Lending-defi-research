# Rà soát code mô hình

Ngày kiểm tra: 20/10/2026. Dataset: `recovery_20261020`. Mã chạy offline trong môi trường `.venv` Python 3.12, NumPy 2.5.4, SciPy 1.18.1. Không thay đổi CSV/SQLite nguồn.

## Kiểm tra đã thực hiện

| Kiểm tra | Kết quả | Bằng chứng local |
|---|---|---|
| Unit tests crawler + models | 42/42 đạt | `python -m unittest discover -s tests -q` |
| Kiểm tra data gate | Ba audit integrity đạt | `python -m defi_models check` |
| Tích hợp RQ1–RQ7 trên dữ liệu thật | 7/7 hoàn tất ở smoke mode, validator đạt | `results/code_review_smoke_final/` |
| RQ4 trên Compound USDC và Morpho | Cả hai hoàn tất ở smoke mode | `results/code_review_rq4_compound/`, `results/code_review_rq4_morpho/` |
| RQ7 lưới cấu hình đầy đủ | 81 tổ hợp hoàn tất, validator đạt | `results/code_review_policy_grid/` |
| PowerShell wrapper | `-Model check` chạy thành công | `scripts/run_models.ps1` |
| Dependency compatibility | `pip check` không báo dependency lỗi | `.venv` local |
| Chặn diễn giải RQ5–RQ7 như mô hình đủ dữ liệu | Chạy thiếu `--allow-exploratory` bị từ chối trước khi tạo output | CLI guard |

Unit tests dùng fixture tổng hợp và tách khỏi dữ liệu thật. Các run kiểm tra nằm trong `results/`, bị loại khỏi Git để tránh nhầm với kết quả nghiên cứu đã duyệt. Lệnh chạy trong bảng phải dùng Python của `.venv` như README_MODELS.

## Các điều kiện đã kiểm tra trong code

- Shock cả tài sản thế chấp và khoản nợ; ETH debt không bị giữ giá cố định khi shock ETH.
- Khóa snapshot hoàn tất/validation, kiểm tra block đồng nhất và không lặp wallet-token.
- Hash CSV phải khớp dữ liệu đã freeze; không sửa nguồn khi mô hình chạy, SQLite mở read-only.
- RQ3 chỉ dùng nhãn sẵn có trước cutoff; outcome ở tương lai có horizon đủ; control ghép không lặp. Không dùng tên nhãn verified cho heuristic temporal.
- RQ4 đối chiếu histogram timestamp với panel giờ; chuẩn hóa covariate bằng train, tách holdout theo thời gian, chọn half-life bằng train. Không tự jitter các event cùng block timestamp.
- Engine kiểm tra nonnegative balances, repayment không làm tăng debt, giá không âm và profitability; giữ cờ chưa hội tụ/hết vòng.
- Output có cấu hình, phiên bản thư viện, execution/readiness, diagnostics và checksum. Lỗi không bị thay bằng kết quả 0.

## Phần chưa được chứng minh bởi kiểm tra kỹ thuật

- RQ1: static eligible debt và điểm gãy mô tả tại một snapshot, không phải actual liquidation volume.
- RQ3: matching/logistic cho association; nhãn đầy đủ/identification và mẫu kiểm chứng đại diện còn thiếu.
- RQ4: Poisson giải thích có giá cùng giờ; Hawkes một biến và block-time coarsening, chưa có residual diagnostics hoặc kiểm định causal self-excitation.
- RQ5: mạng exposure mẫu và common-wallet sensitivity; chưa phải mô hình default propagation được hiệu chỉnh.
- RQ6/RQ7: engine stylized và các giả định thanh khoản, không tái tạo smart contract/route Aave chính xác. 81 tổ hợp chạy thành công không chứng minh chính sách tối ưu hoặc mô hình đã hội tụ ở mọi tổ hợp. Phải đọc cờ `reached_round_limit`, `terminal_eligible_wallets`, `incomplete_dynamics`.

Những giới hạn này được giữ trong summary của từng mô hình và trong README; không chuyển chúng thành trạng thái nghiên cứu hoàn chỉnh chỉ vì code chạy thành công.
