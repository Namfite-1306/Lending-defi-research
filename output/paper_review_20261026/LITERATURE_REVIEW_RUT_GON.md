# 2. Tổng quan nghiên cứu và cơ sở lý thuyết

Bản đề xuất thay thế phần 2 của bản thảo. Các trích dẫn cần xuất hiện đầy đủ trong danh mục tài liệu tham khảo; H1–H3 là ba giả thuyết chính, tương ứng RQ1, RQ2 và RQ4. RQ3, RQ5–RQ7 được giữ ở vai trò phân tích bổ sung.

## 2.1. Thế chấp quá mức và độ nhạy của vị thế vay

Cho vay DeFi sử dụng hợp đồng thông minh để quản lý tài sản thế chấp và thực hiện các quy tắc vay, trả nợ và thanh lý. Cơ chế thế chấp quá mức tạo khoảng đệm bảo vệ bên cho vay, nhưng không loại bỏ rủi ro khi giá tài sản thay đổi. Gudgeon và cộng sự (2020) phân tích các giao thức cung cấp vốn và cho thấy thiết kế giao thức có liên hệ với lãi suất, thanh khoản và hiệu quả thị trường. Trong nghiên cứu này, Aave V3 cung cấp dữ liệu vị thế cho stress tĩnh; Compound III và Morpho Blue được bổ sung trong phân tích so sánh thanh lý và exposure.

Đối với Aave, health factor phản ánh tỷ lệ giữa giá trị collateral đã điều chỉnh theo ngưỡng thanh lý và tổng nợ. Khi health factor dưới một, vị thế có thể đủ điều kiện thanh lý. Điều kiện này khác với việc thanh lý đã được thực thi, bởi việc thực thi còn phụ thuộc chi phí và động cơ của bên thanh lý. Các quy tắc của Aave cũng không được áp nguyên cho Compound III hoặc Morpho Blue.

Perez và cộng sự (2021) chỉ ra rằng các vị thế gần ngưỡng thanh lý có thể nhạy cảm với những thay đổi nhỏ của giá. Nếu nhiều khoản nợ cùng nằm gần ngưỡng, một cú sốc bổ sung có thể làm nợ đủ điều kiện thanh lý tăng mạnh. Heimbach và Huang (2024) bổ sung góc nhìn về đòn bẩy và nợ chịu rủi ro trong DeFi. Các nghiên cứu này gợi ý đo phân bố vị thế và độ nhạy theo giá thay vì suy rủi ro chỉ từ tổng dư nợ. Tuy nhiên, không có cơ sở mặc định rằng ngưỡng nhạy cảm giữ nguyên giữa các thời điểm.

Đòn bẩy lặp có thể làm tăng quy mô vị thế thông qua chuỗi vay, chuyển đổi tài sản và gửi lại làm thế chấp. Chiu và Danisman (2026) nghiên cứu hành vi này trên Aave V3; Xiong và cộng sự (2025) xem xét cơ hội và rủi ro của leverage staking với tài sản staking thanh khoản. Trong bài này, motif giao dịch theo thời gian chỉ là dấu hiệu nhận diện sơ bộ, chưa xác minh đầy đủ dòng tiền. Do đó, kết quả RQ3 ở phụ lục được diễn giải như mối liên hệ giữa motif và tính dễ tổn thương, không phải tác động nhân quả của đòn bẩy lặp.

## 2.2. Động cơ thực thi và mức tập trung thanh lý

Cơ chế thanh lý tạo động lực cho tác nhân bên ngoài hoàn trả nợ để nhận collateral cùng phần thưởng. Qin và cộng sự (2021) nghiên cứu các động lực, rủi ro và bất ổn của quá trình này. Quy mô vốn, năng lực sử dụng bot và khả năng tối ưu giao dịch có thể tạo khác biệt giữa các bên tham gia. Cần phân biệt sự tập trung ở phía người vay với sự tập trung ở phía liquidator: một chỉ tiêu phản ánh phân bố rủi ro vị thế, chỉ tiêu kia phản ánh cấu trúc thực thi.

Chi phí gas, độ trễ oracle và thanh khoản có thể khiến vị thế đủ điều kiện chưa được thanh lý ngay. Schuler (2026) phân tích các ma sát thực thi trên Aave V2, trong khi Gadzinski và Liuzzi (2025) nghiên cứu hành vi cho vay sau thanh lý. Những hướng nghiên cứu này cho thấy thanh lý vừa là cơ chế bảo vệ khoản vay, vừa gắn với điều kiện thị trường và phản ứng của người dùng; chúng không tự xác định tác động nhân quả trong mẫu nghiên cứu hiện tại.

So sánh concentration giữa các giao thức đòi hỏi nhất quán về kỳ, token, định giá và đơn vị quan sát. Theo hướng đối chiếu biến động và thanh khoản của Sasi-Brodesky và Kaousar Nassr (2023), bài cố định kỳ và cặp tài sản, đồng thời báo cáo số ví và sự kiện cùng HHI chuẩn hóa và tỷ trọng top 1% ví. Đặc biệt, basePaidOut của Compound III phải được đối chiếu với ngữ nghĩa nợ hấp thụ trước khi so với dữ liệu Aave. Chuẩn hóa chỉ số không khắc phục được mọi khác biệt thiết kế hoặc sai lệch do mẫu nhỏ; địa chỉ ví cũng không đồng nghĩa với một chủ sở hữu kinh tế.

## 2.3. Cụm thanh lý và thông tin dự báo từ lịch sử sự kiện

Lehar và Parlour (2022) phân tích cơ chế bán collateral làm giảm giá và có thể gây thêm thanh lý. Tuy nhiên, các sự kiện gần nhau về thời gian cũng có thể cùng phản ứng với một cú sốc giá chung. Vì vậy, quan sát clustering chưa đủ để kết luận rằng thanh lý trước gây ra thanh lý sau.

Hawkes (1971) cung cấp khung quá trình điểm trong đó lịch sử sự kiện liên quan đến cường độ sự kiện tiếp theo. Cao và Gang (2026) áp dụng Hawkes đa chiều cho thanh lý liên giao thức; đây là nghiên cứu working paper, cần phân biệt phụ thuộc dự báo có hướng với nhận diện nhân quả cấu trúc. Việc kiểm soát giá thị trường và so với mô hình không có self-history là điều kiện cần khi đánh giá thông tin của lịch sử, nhưng không loại trừ toàn bộ nhân tố chung bị bỏ sót.

Phân tích chính của bài sử dụng mô hình hurdle cho số đếm theo bin năm phút, tách xác suất có thanh lý khỏi quy mô số đếm dương. Cách tiếp cận này phù hợp với dữ liệu có nhiều bin bằng không và có đối chứng không dùng lịch sử. Theo Mullahy (1986) và Czado và cộng sự (2009), cần đánh giá đồng thời đặc tả số đếm và chất lượng dự báo. Log-score tốt hơn không bảo đảm số sự kiện được dự báo đúng mức hoặc phần dư đã phù hợp. Vì vậy, bài bổ sung đánh giá calibration và phụ thuộc phần dư, thay vì diễn giải hệ số lịch sử như branching ratio của Hawkes.

## 2.4. Phạm vi đóng góp và các cơ chế bổ sung

Nghiên cứu hiện tại kết nối ba phép đo: nợ đủ điều kiện thanh lý trên snapshot, concentration của thanh lý quan sát và thông tin dự báo từ lịch sử sự kiện. Đóng góp tập trung vào việc đối chiếu các phép đo trong những phạm vi dữ liệu xác định, không phải tuyên bố đã nhận diện trọn vẹn chuỗi lan truyền rủi ro. Stress tĩnh không đo lượng collateral đã bán; concentration không trực tiếp xếp hạng an toàn giao thức; khả năng dự báo không chứng minh nhân quả.

Các phân tích bổ sung làm rõ những cơ chế còn cần kiểm chứng. Elliott và cộng sự (2014) và Tovanich và cộng sự (2023) tạo cơ sở cho cách tiếp cận mạng tài chính, nhưng mạng exposure mẫu ở RQ5 mới cho thấy quan hệ cùng ví hoặc cùng tài sản. Lehar và Parlour (2022), Warmuz và cộng sự (2022) và Tian và Zhu (2025) là cơ sở xem xét phản hồi giá và thiết kế thanh lý ở RQ6–RQ7. Engine của nhóm còn dùng độ sâu và hàm impact giả định, nên kết quả chỉ minh họa đánh đổi có điều kiện, chưa xác định ngưỡng thanh khoản thực tế hoặc tham số chính sách tối ưu.

## 2.5. Phát triển ba giả thuyết nghiên cứu

Từ cơ chế nhiều vị thế cùng vượt ngưỡng khi giá giảm, bài đặt **H1**: Trên các snapshot cuối quý của Aave V3, dư nợ đủ điều kiện thanh lý phản ứng phi tuyến với cú sốc giá ETH/BTC và vị trí thay đổi độ dốc khác nhau giữa các quý. Giả thuyết được đánh giá mô tả bằng đường stress và điểm gãy, không bằng dòng thanh lý thực tế.

Từ sự khác biệt về quy mô vị thế và cấu trúc thực thi, bài đặt **H2**: Trong mẫu khớp cùng kỳ và cặp tài sản, giá trị thanh lý tập trung vào một nhóm nhỏ địa chỉ người vay và mức concentration mô tả khác nhau giữa các giao thức có đủ số quan sát. Không giả định trước thứ hạng giao thức hoặc ý nghĩa thống kê của chênh lệch.

Từ khả năng lịch sử sự kiện chứa thông tin vượt quá các biến quan sát, bài đặt **H3**: Bổ sung lịch sử thanh lý đã lag vào mô hình có điều kiện thị trường và hoạt động giao thức cải thiện log-score dự báo trên cùng tập đánh giá theo thời gian, so với mô hình không có lịch sử. Calibration được đánh giá riêng. Do giả thuyết được hình thành sau các lượt phân tích và tập test đã được xem, kết quả có tính khám phá, chưa phải kiểm định xác nhận độc lập.
