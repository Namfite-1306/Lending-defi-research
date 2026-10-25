# Rà soát dashboard local ngày 25 tháng 10 năm 2026

Mở **http://127.0.0.1:8790/start**. Dashboard thêm phần giới thiệu 5 mục tiêu, điều hướng thống nhất và cách đọc kết quả theo từng chủ đề. Dữ liệu và kết quả mô hình cũ được giữ nguyên; không công khai website hoặc sử dụng nguồn trả phí.

## Những vấn đề đã sửa

| Trước rà soát | Thay đổi và lợi ích |
|---|---|
| Trang nghiên cứu xếp nhiều phiên bản và hàng chục bảng liên tiếp | Tách tab H1/H2/H3/Cascade; kết quả trước thu gọn trong details, vẫn giữ đầy đủ để đối chiếu |
| Chưa có lối bắt đầu và giới thiệu kết quả theo mục tiêu | Trang Tổng quan có 5 thẻ chức năng, trạng thái bằng chứng, phần còn thiếu và liên kết đi đúng trang |
| Điều hướng khác nhau giữa các trang | Menu chung: Tổng quan, Kết quả nghiên cứu, Thử kịch bản, Giám sát nguồn, Kiểm chứng, Hướng dẫn |
| Nhãn protocol/model/support khó đọc | Hiển thị tên thân thiện trên bảng mới; CSV vẫn giữ tên cột và mã gốc để tái lập |
| Bộ lọc khó khôi phục | Thêm Đặt lại bộ lọc; H1 về quý cuối có output, các điều kiện H2 về mặc định |
| Bảng rỗng thiếu giải thích | Hiện thông báo thiếu output và gợi ý kiểm tra bộ lọc/coverage; không suy diễn zero risk |
| Ngày cascade lỗi vẫn có thể chọn | Vô hiệu hóa các ngày chưa đủ snapshot trong dropdown; bảng coverage vẫn thể hiện thiếu |
| Cảnh báo thời kỳ và freshness khó phân biệt | Tách kỳ nghiên cứu đến31/03/2026, timestamp tính kết quả, nguồn live và source gap |
| Bảng khó đọc trên màn hình hẹp | Tăng kích thước chữ/control, vùng chạm, cuộn bảng có giới hạn; trang không tràn ngang ở390px |
| Điều hướng bàn phím chưa rõ | ARIA tab/panel, phím trái/phải/Home/End, focus-visible và skip-to-main |
| Font live tải từ Google | Bỏ import font bên ngoài, dùng font hệ thống để dashboard local không phụ thuộc nguồn font mạng |

## Đóng góp vào 5 mục tiêu

| Mục tiêu | Dashboard đã thể hiện và hỗ trợ | Phần còn giới hạn |
|---|---|---|
| 1 Reconstruct borrower risk positions | 13/13 full quarter-end snapshots Q1/2023–Q1/2026, borrower universe và active debt wallets tại thời điểm | Chưa phải risk positions theo phút; live wallet sample chưa là full-market census đồng bộ |
| 2 HF và liquidation thresholds | Hiển thị gate HF/debt và stress dựa trên historical configuration/e-mode; phân biệt eligible và executed | Chưa exact execution replay mọi implementation; kiểm chứng độc lập provider toàn kỳ còn thiếu |
| 3 Price shocks | Lọc ETH/BTC/joint và mapping, so eligible debt; what-if chạy với input người dùng | Derivative mapping và các execution assumptions vẫn là sensitivity |
| 4 Concentration và cascade | H2 matched sample/price age/common support; các vòng cascade và so feedback; H3 có model/residual diagnostics | Cascade chưa calibrated end-to-end; H3 residual chưa đạt; chưa nhận diện causal contagion |
| 5 Systemic stress dashboard | Giao diện local tương tác, tải CSV, mô tả nguồn/time/lag, kết quả cũ được tách riêng | Full-system live forecast chưa được duyệt; cập nhật chain phụ thuộc RPC và trạng thái collector |

Đạt giao diện tương tác chưa đồng nghĩa hoàn thành scientific validation của mục tiêu4/5. Những giới hạn được giữ trong nội dung trang, không đổi thành badge “đã hoàn thành” toàn hệ thống.

## Kiểm tra đã thực hiện

- Desktop và màn hình390×844; DOM không tràn ngang toàn trang, bảng cuộn trong vùng riêng.
- H2 đổi token/metric/tuổi giá; đặt lại về WETH/full-count; tải CSV thành công.
- Tab bằng chuột và ArrowRight; mở kho kết quả trước, đổi H1/H2/H3/Cascade.
- What-if lịch sử hoàn tất tại block21.762.264 cho17.084 ví; không ghi đè frozen model outputs.
- Các route /start, /research, /lab, /validation, /guide và assets dùng chung hoạt động. Test HTTP kiểm tra trang mới, JS/CSS và source endpoints.
- Full suite249tests:243đạt,6skip; JavaScript syntax check đạt. Test đầu phát hiện thiếu id objective-5, đã thêm id và chạy lại đạt.
- 40file kết quả nghiên cứu đã khóa giữ nguyên SHA256. Chi tiết trong output/ux_20261025/integrity.json.
- Không dùng tính năng giả lập offline trong browser để khẳng định đã kiểm chứng mọi lỗi mạng. Frontend có thông báo lỗi/giữ dữ liệu cũ; collector có trạng thái bắt kịp/old/error riêng.

## Cách sử dụng ngắn

1. Vào Tổng quan để đọc scope và mức hoàn thành có điều kiện.
2. Vào Kết quả nghiên cứu, chọn một tab và bộ lọc; mở phần chi tiết khi cần. Đọc lại kết quả tải output hiện có, chưa refit mô hình.
3. Vào Thử kịch bản để tính what-if mới; xem Kiểm chứng trước khi diễn giải amplification.
4. Xem Giám sát nguồn để biết chain có cập nhật không. Research page vẫn là lịch sử khi nguồn live đang lỗi hoặc đang bắt kịp.

Chưa commit/push; giao diện được đồng bộ vào clone E sau kiểm tra hash để tránh ghi đè thay đổi đồng thời.
