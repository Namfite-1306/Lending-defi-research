# Tài liệu và output cũ

`member_rq7/` giữ nguyên bản bàn giao RQ7 trước khi hợp nhất. README trong đó là tài liệu lịch sử, có đường dẫn và số liệu theo bản cũ. Không dùng thay README dự án hoặc kết quả nghiên cứu mới.

CSV/JSON/test prototype ở đây được giữ để đối chiếu, chưa được gán lại là dữ liệu mới. Bộ test đang dùng nằm trong `tests/`; test prototype không tự chạy trong regression suite vì cần các output riêng của bản bàn giao cũ.

Chạy RQ7 hiện tại bằng `python -m defi_models rq7 ... --allow-exploratory`, hoặc dùng root entry point `rq7_policy_sensitivity.py --run <audited-run>`. Cấu hình legacy nằm ở `configs/members/rq7_policy.json`.
