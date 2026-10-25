/* Single source for the seven full research questions and interpretation guides. */
const RQ_GUIDES=Object.freeze({
  1:{question:'Mức giảm giá ETH/BTC bao nhiêu sẽ tạo bước nhảy mạnh trong khối lượng thanh lý?',
    model:'Mô hình đang hiển thị: stress tĩnh trên snapshot vay, định giá lại collateral và debt rồi tính health factor.',
    steps:[
      'Đọc nguồn snapshot, factor ETH/BTC hoặc joint shock và giả định mapping trước khi đọc đường stress. Trục ngang là mức giảm giá; trục dọc là nợ ở các vị thế đủ điều kiện thanh lý.',
      'Ví HF < 1 ở nền là các vị thế đã thiếu an toàn trước shock. Ví mới đủ điều kiện là các ví chuyển qua ngưỡng so với nền; không cộng nhầm hai nhóm.',
      'Đường stress tăng mạnh ở một đoạn cho biết nhiều nợ cùng vượt ngưỡng trong đoạn đó. Grid tham chiếu 1% và đường what-if 5% có độ phân giải khác nhau; điểm gãy phụ thuộc snapshot và giả định.',
      'Khi đã tính what-if, đọc block nguồn, shock, LT và bảng ví theo kết quả vừa tính. Bảng ví chỉ preview nhóm nợ lớn theo giới hạn ghi trên trang.'
    ],limit:'RQ1 đặt câu hỏi về volume thanh lý, nhưng mô hình hiện đo eligible-debt stock. Chưa được diễn giải đường stress là volume thực thi, bad debt hoặc một ngưỡng cascade chung cho thị trường.'},
  2:{question:'Thanh lý có tập trung ở một số ví, token hoặc giao thức hay không?',
    model:'Mô hình đang hiển thị: thống kê concentration bằng HHI, Gini và tỷ trọng Top 10 theo nhóm thực thể.',
    steps:[
      'Chọn giao thức, thời kỳ, loại thực thể và thước đo trước. Số sự kiện và USD trên priced subset là hai cách cân trọng số khác nhau; không so như cùng một mẫu.',
      'HHI càng lớn cho thấy trọng số tập trung vào ít thực thể hơn. Gini càng gần 1 thể hiện phân bố càng lệch; Top 10 share là phần tổng trọng số thuộc mười thực thể lớn nhất, không phải Top 10%.',
      'Đối chiếu biểu đồ top entities với tổng events, tỷ lệ có giá và cỡ mẫu. Các thẻ coverage phía trên mô tả toàn bộ tập tham chiếu theo protocol, không tự đổi thành coverage của mọi bộ lọc bên dưới.',
      'Trang 7 RQ này dùng generic HHI/Gini và cách đo event của bộ cũ. Để so liên giao thức cùng token/kỳ và normalized concentration với Comet correction, mở kết quả H2 nâng cấp.'
    ],limit:'Không cộng USD của Comet absorption và Aave repayment thành cùng một khái niệm. Một địa chỉ chưa chắc là một chủ sở hữu. HHI cao trong mẫu ít thực thể chưa đủ kết luận một protocol tập trung hơn toàn thị trường.',link:'/research#sources',linkLabel:'Xem H2 matched sample và kiểm tra tuổi giá'},
  3:{question:'Đòn bẩy lặp (recursive leverage) làm mức độ dễ bị tổn thương tăng thêm bao nhiêu?',
    model:'Mô hình đang hiển thị: nhận diện nhãn trước snapshot, nearest-neighbor matching và so outcome thanh lý trong 7 ngày; logistic penalized là phân tích bổ sung trong summary.',
    steps:[
      'Đọc loại nhãn và cutoff trước: temporal là ứng viên có motif theo thời gian; verified là tập bằng chứng nhỏ đã được kiểm tra. Control là không thấy motif, chưa chắc không dùng leverage.',
      'Số cặp match và số treated không match cho biết phân tích bao phủ bao nhiêu đối tượng. Khoảng cách match nhỏ hơn thể hiện các biến ghép cặp gần nhau hơn; cần đọc thêm matching balance trước khi suy rộng.',
      'Chênh lệch rủi ro là xác suất thanh lý 7 ngày của treated trừ control, tính bằng điểm phần trăm. Ví dụ +1,5 điểm % là chênh lệch tuyệt đối, không phải rủi ro tăng 1,5% tương đối.',
      'Bootstrap 95% thể hiện độ bất định khi lấy mẫu lại trên các cặp cố định. Khoảng qua 0 chưa cho dấu chênh lệch ổn định; khoảng không qua 0 vẫn chưa nhận diện causal effect hoặc toàn bộ bất định của matching.',
      'Bảng cặp có cờ 0/1 cho từng outcome. Tìm ví/lọc outcome chỉ thay bảng xem, không fit lại matching, bootstrap hoặc logistic. Nếu đọc hệ số logistic trong summary, đó là log-odds có điều kiện và regularization, không phải chênh lệch xác suất hay tác động nhân quả.'
    ],limit:'Đây là observational association trong mẫu đã ghép. Nhãn ứng viên, unmatched treated và các biến chưa quan sát có thể làm lệch kết quả; không gọi là phần tăng rủi ro do leverage gây ra đã được xác định.'},
  4:{question:'Các sự kiện thanh lý có hình thành cụm và tự kích thích theo thời gian hay không?',
    model:'Mô hình ở trang này: Hawkes một biến trên lịch sử sự kiện và Poisson với price controls cùng giờ. RQ4 tương ứng H3 trong bài nghiên cứu, khác RQ3 về leverage.',
    steps:[
      'Hawkes half-life là thời gian để phần kích thích suy giảm một nửa theo kernel đã fit. Half-life dài hơn mô tả persistence dài hơn trong mô hình, không tự chứng minh có contagion.',
      'Branching ratio là tham số excitation của Hawkes theo giả định của mô hình; không đọc thành tỷ lệ phần trăm thanh lý do lây lan gây ra hoặc xác suất xảy ra một cascade.',
      'Đồ thị so tổng observed với Poisson prediction theo ngày từ dữ liệu từng giờ. Đường prediction là Poisson, không phải đường dự báo Hawkes. Tổng prediction bỏ qua giờ thiếu giá nên cần kiểm tra valid_prices và sample trong CSV.',
      'Các biến giá Poisson là cùng giờ, nên đây là mô tả có điều kiện, không phải forecast trước giờ. Đổi khoảng ngày chỉ đổi bảng và đồ thị, không chọn lại half-life hoặc huấn luyện lại mô hình.',
      'Để đánh giá bản nâng cấp có market/activity/history controls, đối chứng, rolling và residual, mở H3 mới. Trên cùng test sample, log-score ít âm hơn tốt hơn; expected/observed gần 1 cân bằng tổng count. Residual KS/ACF chưa đạt vẫn phải công bố.'
    ],limit:'Clustering có thể đến từ cú sốc thị trường chung và biến bị bỏ sót. Kết quả hiện tại chưa nhận diện causal self-excitation; H3 nâng cấp vẫn chưa đạt residual calibration.',link:'/research#h3',linkLabel:'Xem H3 có controls và kiểm định ngoài mẫu'},
  5:{question:'Exposure chéo giữa các giao thức có thể tạo kênh lây lan rủi ro hay không?',
    model:'Mô hình đang hiển thị: mạng exposure ví–giao thức–tài sản trên mẫu đồng bộ một block và thống kê shared borrowing.',
    steps:[
      'Đọc số ví, cạnh định giá được và dòng chưa có giá trước. Đây là một mẫu exposure tại block ghi trên trang; missing prices không được thay bằng 0.',
      'Một cạnh trong bảng thể hiện debt hoặc collateral của một ví tại một protocol/market. Exposure USD là giá trị vị thế, không phải khoản lỗ đã phát sinh hay khoản phải thu trực tiếp giữa hai giao thức.',
      'Shared-debt wallets là số địa chỉ cùng có nợ ở hai protocol trong mẫu. Min-exposure cộng giá trị nhỏ hơn của hai khoản nợ cho từng ví chung; đây là thước đo overlap, không phải số tiền sẽ lây lan khi có default.',
      'Chọn protocol hoặc tìm địa chỉ chỉ lọc bảng cạnh. Các thẻ tổng mẫu và bảng overlap vẫn mô tả toàn sample đã lưu; chúng không tự được ước lượng lại theo bảng đang lọc.',
      'Nếu dùng common-wallet sensitivity từ output RQ5, đọc đó là khoản nợ đồng phơi nhiễm của nhóm ví giả định gặp khó khăn. Không gán xác suất default hoặc recovery rate khi chưa có mô hình và bằng chứng tương ứng.'
    ],limit:'Overlap là dấu hiệu một kênh có thể tồn tại, chưa chứng minh contagion thực tế hoặc causal transmission. Không thấy ví chung trong mẫu chưa chứng minh hai protocol không liên thông trên toàn thị trường.'},
  6:{question:'Phản hồi giữa thanh lý và tác động giá khuếch đại quy mô thanh lý và thiếu hụt tài sản bảo đảm đến mức nào?',
    model:'Mô hình đang hiển thị: cascade stylized nhiều vòng, so cùng snapshot/giả định giữa có price impact và zero-impact control.',
    steps:[
      'Nếu chưa tính what-if, chọn shock tham chiếu để xem kết quả đã lưu. Nếu vừa tính, đọc block nguồn và tham số đã gửi; hai ô so sánh lúc này thuộc kịch bản của bạn.',
      'Repaid USD là nợ được trả trong mô phỏng; seized collateral là tài sản thế chấp bị lấy theo cơ chế giả định. So có/không impact trên cùng shock và financial assumptions, không trộn hai snapshot hoặc độ sâu thanh khoản khác nhau.',
      'Đọc biểu đồ repayment từng vòng cùng eligible trước vòng, wallet actions và cumulative impact. Một ví có thể có action ở nhiều vòng; tổng actions không phải số ví duy nhất.',
      'Đọc stop reason và số ví còn HF < 1. Hết vòng do không còn profitable liquidations vẫn có thể để lại ví chưa an toàn; reached round limit nghĩa là mô phỏng chưa tìm được trạng thái kết thúc.',
      'Tỷ số repaid có impact/zero-impact, nếu mẫu số dương, chỉ là amplification theo giả định. Shortfall cuối là thiếu hụt collateral trong accounting của mô hình, không phải bad debt on-chain.'
    ],limit:'Depth, square-root impact, pass-through, gas, bonus và cách chọn debt/collateral còn là giả định. Engine này chưa calibrated end-to-end và khác engine pair/route ở trang nghiên cứu Cascade.',link:'/research#cascade',linkLabel:'Đọc đối chiếu cascade theo sự kiện và route'},
  7:{question:'Thay đổi close factor, liquidation bonus và liquidation threshold tạo ra đánh đổi gì giữa giảm nợ, tổn thất người vay và rủi ro giao thức?',
    model:'Mô hình đang hiển thị: grid tham số policy trên engine RQ6 và Pareto screen có điều kiện theo từng mức shock.',
    steps:[
      'Chọn cùng shock của grid rồi so close factor, bonus và LT shift. LT shift ghi theo điểm phần trăm, khác phần trăm thay đổi tương đối của threshold.',
      'Đọc đồng thời terminal shortfall, collateral seized, price impact và số ví còn HF < 1. Chỉ số thấp ở một chiều có thể đi kèm đánh đổi ở chiều khác; collateral seized chưa phải thước đo đầy đủ phúc lợi hoặc tổn thất người vay.',
      'Pareto không bị trội nghĩa là không có cấu hình khác trong cùng grid/shock tốt hơn hoặc bằng ở mọi mục tiêu được xét (shortfall, collateral seized, price impact) và tốt hơn ít nhất một mục tiêu. Đây không phải một cấu hình tối ưu duy nhất.',
      'Kịch bản chạm round limit không được xếp Pareto như một kết quả kết thúc. Bộ lọc Chỉ hiện Pareto chỉ đổi các dòng đang xem; các thẻ tổng grid phía trên vẫn là thống kê của toàn grid tham chiếu.',
      'Sau khi tính một cấu hình tự chọn, phần thông báo cho biết kết quả mới nhưng grid lịch sử vẫn giữ nguyên. Cấu hình mới chưa được tự gán Pareto hay dùng để tái ước lượng toàn grid.'
    ],limit:'Đây là policy sensitivity trong simulator chưa hiệu chỉnh toàn bộ, giữ balances ban đầu và chưa có borrower response. Không suy ra khuyến nghị tham số thực tế hoặc chính sách tối ưu cho Aave.'}
});
