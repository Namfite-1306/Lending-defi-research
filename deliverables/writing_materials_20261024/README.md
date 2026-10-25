# Bộ bàn giao để viết bài

1. Đọc **[NGUYEN_LIEU_VIET_BAI.md](NGUYEN_LIEU_VIET_BAI.md)**: câu chuyện bài, mapping RQ–H, findings, methods/phương trình, kết quả, giới hạn và bố cục manuscript.
2. Dùng **[TAI_LIEU_THAM_KHAO.md](TAI_LIEU_THAM_KHAO.md)** và **[references.bib](references.bib)**: tám nguồn literature, Hawkes và protocol/data docs; SSRN được tách riêng vì chưa xác minh đủ phiên bản.
3. **[BANG_KET_QUA_H1.md](BANG_KET_QUA_H1.md)**: bảng 13 quý để dựng bảng/hình bài. Các bảng H2/H3 có ngay trong dossier và CSV evidence.
4. Thư mục **evidence/** chứa 32 bảng/JSON/báo cáo được sao từ output đã chạy, không kèm toàn bộ raw dataset. **provenance.json** ánh xạ nguồn và hash; **checksums.json** kiểm tra toàn pack.
5. **[HUONG_DAN_CHAY.md](HUONG_DAN_CHAY.md)**: chạy ba file dưới đây, dependencies, data paths, config, outputs và khác biệt giữa legacy runner với H2/H3 paper outputs mới.

| File code | Vai trò |
|---|---|
| [code/RQ3.py](code/RQ3.py) | Recursive-leverage candidates, matching và outcome7 ngày |
| [code/RQ6.py](code/RQ6.py) | Cascade stylized với zero-impact controls |
| [code/RQ2_RQ5.py](code/RQ2_RQ5.py) | Generic concentration và mạng exposure mẫu |

Cả ba file đã chạy trên dataset thật; validator đạt và **14 file CSV/JSON đầu ra khớp SHA256 với bộ frozen**. Xem **CODE_VERIFICATION.json**. Điều này kiểm chứng tái lập kỹ thuật, chưa làm mô hình kinh tế được calibrated.

**Ba file cần nằm bên trong repository có `defi_models/` và cần dataset riêng.** RQ2 generic chưa thay thế bảng H2 matched/Comet-corrected mới; RQ6 chưa là engine đã calibrated lịch sử. Các hạn chế này được ghi trong hướng dẫn để tránh dùng sai kết quả.

Kỳ chính bài:27/01/2023–31/03/2026. H1 đủ13/13 quý trong kỳ đã duyệt. Legacy outputs khác kỳ được đánh dấu; H3 residual vẫn chưa đạt. Không có tài khoản/nguồn trả phí hoặc thao tác commit/push trong lượt này.
