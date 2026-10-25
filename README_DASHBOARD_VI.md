# Hướng dẫn dashboard DeFi local

Mở **http://127.0.0.1:8790/guide** để đọc hướng dẫn ngay trong dashboard.

## Giao diện dễ dùng cập nhật 25/10/2026

Bắt đầu tại **http://127.0.0.1:8790/start**. Trang này giải thích đóng góp và giới hạn
ở cả 5 mục tiêu, đồng thời đọc số snapshot, coverage giá và trạng thái nguồn live.

- **Kết quả nghiên cứu:** chọn tab H1/H2/H3/Cascade. Kho kết quả trước được thu gọn,
  giữ nguyên sample và output cũ. Đổi bộ lọc không refit; Đọc lại kết quả chỉ tải cache.
- **Đặt lại bộ lọc:** về mặc định; H1 về quý cuối đã có output. Ngày cascade chưa đủ
  snapshot được vô hiệu hóa trong dropdown, vẫn hiển thị thiếu trong bảng coverage.
- **Thử kịch bản:** đổi tham số rồi bấm Tính lại kịch bản. Đây là what-if theo giả định.
- **Giám sát nguồn:** đọc block, độ trễ và trạng thái collector; catching-up/stale/error
  chưa được xem là dữ liệu real-time đầy đủ. Research page là lịch sử, không phải live forecast.
- **Kiểm chứng / Hướng dẫn:** đọc coverage và cách diễn giải. CSV giữ tên cột và đơn vị
  gốc; nhãn trên màn hình được diễn đạt lại cho dễ hiểu.

Điều hướng tab hỗ trợ phím trái/phải và Home/End. Bảng có thể cuộn ngang trên
điện thoại; dữ liệu thiếu có giải thích thay vì được xem như zero risk.

## Khởi động / mở lại

Trong PowerShell, mở thư mục `E:\OneDrive\Documents\GitHub\Clone\Lending-defi-research`, chạy:

```powershell
powershell -NoProfile -File scripts/start_stress_local.ps1
```

Giữ cửa sổ đó mở. Nếu server đang chạy, chỉ mở URL; không chạy thêm server cùng cổng.
Ctrl+C tại cửa sổ chạy server để dừng. Script hiện dùng Python venv trên C và
đọc data theo manifest; đây là cấu hình máy hiện tại, không phải bản portable.
Nếu báo cổng đã dùng, quay lại dashboard hiện có; không tắt tùy tiện các Python khác.

## Kỳ chính mới và nguồn bổ sung H1/H2/H3

Mở **http://127.0.0.1:8790/research#sources**. Kỳ chính kết thúc 31/03/2026:
H1 đủ 13/13 snapshot. H2 thêm giá USDC/USD độc lập và common support.
H3 thêm hoạt động giao thức, hurdle model, rolling và residual.
Xem README_SOURCES_H123.md để chạy lại. Research page là kết quả lịch sử;
các mục phía dưới giữ output cũ với kỳ riêng.

## Lượt sửa trước H2/H3

Mở http://127.0.0.1:8790/research#repair. Mục Output mới riêng có full-count,
native USDC upper/lower và USD/priced-count theo policy. Chọn metric trước;
policy giá chỉ có hiệu lực với USD/priced-count. Bảng H3, residual và rolling mới
ở cùng mục. Xem README_REPAIR_H123.md; các bảng bên dưới vẫn là output cũ/V2.

## Chọn đúng trang

| Trang | Dùng để làm gì | Có tính lại không? |
|---|---|---|
| `/research` | Kết quả H1, H3, Concentration; tiến độ và cascade lịch sử mới | Chủ yếu lọc bảng/kịch bản đã tính, không refit Hawkes |
| `/lab` | Xem 7 RQ và thử what-if trên snapshot | Bấm nút tính theo giao diện để chạy scenario; không retrain cả 7 RQ |
| `/validation` | Coverage, quote DEX, bằng chứng stress và giới hạn engine trước đây | Xem/lọc evidence đã lưu; không coi mọi engine ở đây là bản V2 |
| `/` | Giám sát chain và nhóm ví live | Collector chạy nền khi RPC truy cập được |

**Tên mới:** H2 giữ nguyên concentration; H3 = temporal clustering/self-excitation (H4 cũ). RQ4 vẫn là RQ4; module/thư mục `h4*`, JSON keys
và output cũ giữ tên để chạy tương thích. `H1/2025` và `H2/2025` trong ngày tháng
nghĩa là nửa đầu và nửa cuối năm, không phải giả thuyết.

## H1 trên `/research`

1. Xem bảng snapshot: chỉ `Full=true` mới vào phân tích. 13/15 quý hiện hoàn tất.
2. Chọn quý → ETH/BTC/joint shock → mapping. Nhóm factor 1:1 cho derivatives đi
   cùng ETH/BTC; “chỉ WETH/WBTC” giữ token khác cố định, là một sensitivity.
3. Đọc đường eligible-debt share và hai cột khác nhau: share-knot và largest USD jump.
   Mẫu số nợ được định giá lại sau shock; eligible debt không phải tài sản đã bán.
4. Chọn shock 0/10/20/30% ở phần composition để xem ví/token. Đây là exposure,
   không phải tác động nhân quả của token; ví là địa chỉ, chưa gộp beneficial owners.

## H2 — Concentration trên `/research`

1. Chọn 2024 làm cửa sổ chính; extended period là sensitivity có thêm giới hạn.
2. Chọn WETH hoặc WBTC, tuổi giá, count/USD/lower bound và loại ví lớn.
3. **Đọc Coverage trước Concentration.** Ví dụ WETH–Aave 2024, tuổi giá 1h chỉ
   giữ 71/1.105 events; Comet chỉ 4/158. Chưa đủ để xếp hạng chung protocols.
4. So HHI chuẩn hóa, Gini chuẩn hóa và số ví cùng lúc. Cờ N<30 báo mẫu nhỏ.
   N=1 có thể không có HHI chuẩn hóa. Top1% khi ít ví thường chỉ là Top1.
5. Bấm “Tải bảng đang lọc” để tải đúng sensitivity đang chọn. Count ở đây dùng
   cùng priced sample với USD, không phải toàn bộ events. Có thể xem count_all
   ở `/validation`, nhưng đó là phạm vi/định nghĩa khác và phải ghi rõ.

## H3 và V2 trên `/research`

1. Phần “H3 · Dự báo...” phía trên là **kết quả cũ** giữ lại để đối chiếu.
2. Cuộn tới V2. Chọn **Phần kỳ đã xác minh (thiếu kỳ cuối)** để xem kết quả mới:
   27/01/2023 đến trước 02/06/2026 05:05 UTC. Core đủ kỳ và utilization còn chờ.
3. Chọn “Oracle + gas” để so Poisson và Hawkes cùng nhóm biến/common sample;
   NB là robustness hậu kiểm, không được chọn làm model chỉ vì có test score tốt.
4. Log-score lớn hơn/ít âm hơn là tốt hơn **chỉ khi cùng sample và đơn vị**.
   MAE thấp hơn là tốt hơn nhưng chuỗi nhiều zero có thể làm dự báo zero có MAE đẹp.
   Eta không phải phần trăm liquidation do contagion gây ra.
5. Đọc residual KS/ACF: p<0,05 là diagnostic chưa đạt; p≥0,05 không chứng minh
   model đúng. Hiện KS vẫn không đạt; NB dự báo tổng count quá cao.
6. “Tải bảng mô hình” tải các dòng đang lọc. Đổi nhóm biến không fit lại.
   Muốn tính lại model phải chạy lệnh Python trong README_RESEARCH_V2.md.

## Cascade V2

Chọn ngày có full snapshot → shock 10/20/30% → bật/tắt feedback. So repaid USD,
các vòng và bảng có/không feedback, cùng ngày/shock. Actions là preview tối đa
250 dòng, không phải toàn bộ simulation. Nút tải bước xuất rounds, không xuất
toàn bộ actions. Ngày chưa đủ snapshot có thể chưa có kết quả, không phải zero loss.

Actual-path table dùng đường oracle đã thực hiện và cohort/direct routes phù hợp;
đường giá này có thể đã chứa feedback thực tế. Chưa có calibration end-to-end:
không dùng amplification mô phỏng làm amplification thị trường đã quan sát.

## Dùng `/lab` và trang live

Ở `/lab`, chọn snapshot lịch sử hoặc nhóm ví live, chỉnh shock/LT/close factor/
bonus/depth/gas rồi bấm nút tính. Kết quả what-if thuộc engine và snapshot ghi
trên trang; không thay kết quả chính trong bài. Depth/gas/ordering còn là giả định.
Các tab RQ khác có bảng cố định, lọc bảng không huấn luyện lại mô hình.

Trang live: kiểm tra trạng thái RPC, block nguồn, tuổi dữ liệu và số ví trước khi
đọc số liệu. Poll block mặc định 15s, vị thế/mô hình 300s, quote khoảng 900s;
độ trễ thực phụ thuộc nguồn và block xác nhận. 40 ví live và census cuốn chiếu
không phải toàn thị trường đồng bộ một block.

## Khi gặp lỗi / khi trích kết quả

- Dashboard đọc lại research mỗi 30s; refresh giao diện không tự crawl thêm hoặc
  refit model. Timestamp báo cáo không phải timestamp của dữ liệu chain.
- RPC 403/Cloudflare 1010 hiện chặn crawl: cache vẫn xem được nhưng không gọi là
  real-time. Không mặc định mua archive plan sẽ sửa lỗi này.
- Bảng trống nghĩa là chưa có output cho lựa chọn đó; không kết luận không có rủi ro.
- Core/prefix/utilization và các engine cũ/mới có thể khác sample/giả định;
  không so raw likelihood hoặc amplification trực tiếp giữa chúng.
- Khi viết bài, ghi rõ quý/cửa sổ, nguồn snapshot, shock/mapping, token, tuổi giá,
  số events/ví, variant và model. Xem DANH_GIA_FINDINGS_H1_H2_H3.md trước
  khi dùng kết quả để kết luận.
