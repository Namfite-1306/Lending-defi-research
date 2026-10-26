# Quy trình khắc phục giới hạn của năm mục tiêu

Ngày rà soát 26/10/2026. Kỳ chính vẫn kết thúc Q1/2026 với 13 quý, không tự đưa lại Q2 và Q3/2026 đã loại. Các bước dưới là kế hoạch nghiên cứu tiếp theo; không đồng nghĩa chúng đã chạy hoặc đã đạt. Dataset và kết quả cũ được giữ nguyên, đầu ra mới phải có run ID và manifest riêng.

## Mục tiêu 1 và 2 Tái dựng vị thế và tính ngưỡng thanh lý

Hiện có 13 full snapshot cuối quý trong kỳ, đã đối chiếu health factor và aggregate debt. Thiếu chuỗi toàn thị trường theo block/phút và kiểm chứng độc lập toàn lịch sử.

Quy trình: xác định borrower universe có hiệu lực trước từng cutoff; đọc reserve indices, số dư, cấu hình collateral, e-mode, oracle và revision hợp đồng đúng block; cập nhật trạng thái bằng event và các chỉ số tích lũy; đối chiếu lại với archive state tại các mốc kiểm tra. Tách adapter theo phiên bản/giao thức, không dùng công thức Aave cho Comet/Morpho. Lưu lỗi, coverage và block hash thay vì gán số dư thiếu bằng 0.

Điều kiện chấp nhận: borrower census khép kín, không dùng người thanh lý trong tương lai để chọn mẫu, không look-ahead, kiểm tra HF/debt đạt tolerance đã công bố, tái hiện được tại block gốc. Kiểm tra đa provider chỉ được ghi đạt sau khi có bằng chứng truy vấn. Nếu public RPC không phục vụ trạng thái cần thiết, báo cụ thể block/method/số request trước khi dùng RPC tài khoản hoặc trả phí.

## Mục tiêu 3 Mô phỏng price shocks

Stress tĩnh đã có và dùng được như phân tích kịch bản. Giới hạn còn lại là mapping tài sản phái sinh 1:1, giữ nguyên hành vi người vay và chưa phản ánh basis/depeg động.

Quy trình: bổ sung chuỗi giá/basis độc lập với oracle theo timestamp, gắn freshness và độ trễ; so direct-token với factor-family và cú sốc basis/depeg; chạy cùng snapshot để tách tác động mapping khỏi thay đổi mẫu. Nếu thêm Monte Carlo, phải công bố cách ước lượng phân phối, tương quan, seed và kiểm tra ngoài mẫu; không coi việc thêm Monte Carlo là tự làm mô hình chính xác hơn.

Điều kiện chấp nhận: stock eligible debt, collateral seized, debt repaid và bad debt được định nghĩa tách biệt; cân đối kế toán và đơn vị giá đúng; không tự nhận phân phối shock hoặc tác động giá là đã hiệu chuẩn.

## Mục tiêu 4 Concentration và cascade

H2 có bằng chứng concentration mô tả trên mẫu khớp; cascade còn cách điệu hoặc economic approximation, chưa end-to-end validated. H3 cho thấy thông tin dự báo nhưng calibration chưa đạt.

**H2:** chạy day-cluster bootstrap trên đúng bảng giá thị trường mới và đúng support/metric/filter, giữ cấu trúc event trong ngày; tính lại concentration cho mỗi lần resample. Báo độ bất định và sensitivity bỏ ví lớn, native/count/USD, tuổi giá và mẫu nhỏ. Không dùng lại khoảng bootstrap của support cũ. Chỉ kiểm định chênh lệch giữa protocol khi thiết kế resampling phản ánh lịch chung và quan sát phụ thuộc; không biến HHI thành xếp hạng causal risk.

**H3:** khóa đặc tả và quy tắc chọn mô hình; đánh giá tách xác suất có sự kiện và số đếm dương; thử độ phân tán thay đổi/đặc tả count khác hoặc Hawkes có controls phù hợp, dùng cùng clock và đối chứng không có lịch sử. Chọn bằng validation, kiểm calibration/PIT/residual và rolling stability. Không chọn vì p-value đẹp trên tập test đã xem. Để gọi xác nhận độc lập cần giai đoạn mới sau khi khóa mô hình và chưa được dùng để chọn; không thể xóa việc test cũ đã bị xem bằng sửa code. Mọi thay đổi phạm vi kỳ phải được xác định riêng, không tự đưa lại quý đã loại.

**Cascade:** thu pre-event full positions, cấu hình rủi ro, oracle, pool/tick/liquidity và route quotes theo đúng thời điểm/amount; xác minh receipts, token decimals và log ordering. Hiệu chuẩn impact bằng dữ liệu thực trên tập train, so với control không phản hồi trên cùng snapshot. Backtest số actions, debt repaid, collateral seized, coverage route và sai số định giá ở các sự kiện chưa dùng hiệu chuẩn; phân tích sensitivity gas, bonus, close factor và phản ứng nạp collateral/trả nợ. Đường oracle thực có thể đã chứa phản hồi nên không tự xem đó là cú sốc ngoại sinh.

Điều kiện chấp nhận: end-to-end gate được công bố trước khi đánh giá, không còn sai cân đối, hỗ trợ đúng rule revision, định giá và route coverage đủ cho kết luận đã nêu, các lỗi lớn được giải thích. Gate chưa đạt thì dashboard giữ nhãn exploratory. Mạng exposure 69 ví chỉ là mô tả; muốn contagion cần mở rộng universe đồng bộ và có giả định default/recovery/propagation được biện minh, không chỉ thêm mũi tên vào hình.

## Mục tiêu 5 Dashboard hệ thống và real-time

Đã sửa phần đóng gói Vercel, route tĩnh, trạng thái snapshot-only, findings theo bộ lọc và lỗi khóa ngày Cascade. Đây là các lỗi phần mềm có thể xử lý ngay. Bản local vẫn có collector và what-if; bản Vercel chưa có backend không được gọi là real-time.

Quy trình triển khai tiếp: chọn worker host chạy liên tục; dùng storage/checkpoint bền vững; cấu hình RPC có năng lực thực; đặt API sau reverse proxy có authentication và rate limit; cấu hình `DEFI_BACKEND_URL`/token trên Vercel; kiểm reorg, resume, upstream failure và nhiều người cùng yêu cầu simulation. Nếu cần scale, thay job trong bộ nhớ bằng queue/job store bền vững trước khi chạy nhiều worker. Lưu metrics cho head, indexed block, snapshot source block, source age và calculation age.

Điều kiện chấp nhận: kiểm tra chu kỳ 15 giây nhưng chỉ gọi fresh khi source và calculation đạt ngưỡng công bố; khi RPC lỗi hoặc backend mất kết nối UI phải báo stale/error, không giữ nhãn fresh; historical findings phải tách khỏi live cohort và khỏi forecast. Đạt chức năng real-time không đồng nghĩa mô hình H3 đã đạt calibration hoặc cascade đã được xác nhận.

## Thứ tự thực hiện

1. Chốt bản deploy và UI hiện tại, smoke test cả local và cloud sau khi push.
2. Hoàn thiện uncertainty H2 trên support mới; mở rộng kiểm chứng state/giá/route bằng nguồn hiện có.
3. Khóa đặc tả H3 và cascade, thu dữ liệu phục vụ validation riêng.
4. Chỉ hiệu chuẩn/so mô hình khi coverage và kiểm tra kế toán đạt; lưu thất bại và các run so sánh.
5. Tích hợp model mới sau khi đạt gate, giữ phiên bản cũ để đối chiếu. Không sửa nhãn giới hạn thành “đã hoàn thành” chỉ vì đã thêm code.

Chưa sử dụng nguồn trả phí hoặc tài khoản mới. Trước khi cần nguồn như vậy phải báo khả năng nguồn hiện tại, thiếu gì, số request/dung lượng, và nhu cầu cụ thể để người dùng duyệt.
