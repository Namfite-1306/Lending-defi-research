# Rà soát bản thảo DeFi và hướng dẫn hoàn thiện

Nguồn đọc: E:\Downloads\[GPM1] DeFi.docx. Ngày rà soát: 26/10/2026. File gốc được giữ nguyên. Phần đánh giá dưới đây đối chiếu nội dung Word với code và gói evidence local; không phải một lượt tái ước lượng mô hình hoặc xác minh độc lập toàn bộ dữ liệu thô.

## 1. Nội dung đã đủ chưa

**Đủ khung của một bài nghiên cứu thực nghiệm, nhưng chưa nên nộp bản hiện tại.** Bản thảo có Introduction, Literature Review, Data, Method, Findings, Conclusion, năm phụ lục và danh mục tham khảo. Kết quả H1–H3 đã có số liệu, mô tả sensitivity và công bố giới hạn. Điểm cần sửa chủ yếu là sự nhất quán giữa phần đầu với phần đã thực hiện, công thức, trích dẫn và các hình còn trống; không cần chạy thêm cả bảy RQ chỉ để hoàn thiện bản viết này.

### Những phần có thể giữ

- H1 phân biệt eligible-debt stock với thanh lý thực thi; 13 snapshot kết thúc Q1/2026 và không dùng Q2–Q3/2026. Bảng stress ghi rõ mapping, shock và mẫu số.
- H2 cố định kỳ và cặp tài sản, chuẩn hóa concentration và không dùng hai sự kiện Morpho để xếp hạng. Phần hiệu chỉnh ngữ nghĩa basePaidOut của Comet và giới hạn owner/address là cần thiết.
- H3 báo cả cải thiện log-score lẫn dự báo thừa khoảng 46%, PIT chưa đạt, test đã được xem và giới hạn nhân quả. Nên giữ toàn bộ những giới hạn này.
- RQ3, RQ5, RQ6, RQ7 được tách ở phụ lục và có cảnh báo motif, mẫu exposure, cascade giả định và policy grid.

### Những việc cần sửa trước khi nộp

**1. Thống nhất phạm vi 7 RQ và 3 giả thuyết chính.** Phần 1.2 liệt kê bảy RQ khá tham vọng, trong khi Method và Findings tập trung ba phân tích. Nên thêm ngay sau danh sách RQ: “Bài tập trung H1–H3 tương ứng RQ1, RQ2 và RQ4; RQ3 và RQ5–RQ7 là phân tích bổ sung có phạm vi riêng tại phụ lục.” Đồng thời giảm lời hứa ở RQ3 về tổn thất ròng, RQ5 về mức khuếch đại contagion và RQ6–RQ7 về ngưỡng/nợ xấu thực tế: kết quả hiện tại chưa đo đủ các đại lượng đó. Có thể giữ các câu hỏi rộng như chương trình nghiên cứu, nhưng phải nói rõ phần nào chưa trả lời.

**2. Viết lại phần 3 từ kế hoạch thành dữ liệu đã sử dụng.** Các mục 3.1–3.5 còn nhiều câu “cần xác định”, “cần thu thập”, “khi dữ liệu cho phép”. Thay bằng phạm vi thực: Ethereum mainnet; H1 là Aave V3 với 13 snapshot Q1/2023–Q1/2026; H2 ở bảng chính là mẫu WETH/USDC 01/02–31/12/2024, ngưỡng tuổi giá 300 giây; H3 có train/validation/test theo mục 4.4 và common test 78.643 bin, 10.448 sự kiện. Phải phân biệt coverage USDC 7.259/7.264 của sensitivity mở rộng 01/02/2024–31/03/2026 với cỡ mẫu bảng chính H2 năm 2024. Không trình bày depth DEX là đã đo thực khi engine đang giả định 100 triệu USD.

Nên thêm một bảng phạm vi gồm: phân tích, giao thức, chain/market, kỳ, đơn vị quan sát, số quan sát, loại giá và lý do loại quan sát. Bổ sung manifest/block snapshot, deployment/contract và con trỏ evidence để tái lập. Trong trích xuất hiện tại chưa thấy tên bài/trang bìa; nếu bìa nộp riêng thì không cần thêm vào thân bài.

**3. Phát biểu H1–H3 rõ ở cuối Literature Review.** Hiện H1–H3 xuất hiện trong Method, Findings và bảng đánh giá nhưng chưa có một đoạn phát triển giả thuyết độc lập ở phần 2. Bản Literature Review rút gọn đi kèm đã bổ sung mục 2.5. Giữ thông tin giả thuyết được phát biểu sau các lượt phân tích; không đổi thành giả thuyết đăng ký trước.

**4. Sửa các công thức Word, không chỉ kiểm tra bản trích text.** Đã đọc trực tiếp 25 đối tượng công thức OMML; các vấn đề sau tồn tại trong cấu trúc công thức chứ không đơn thuần do Word không xuất được chữ:

- Mục 4.2.4: công thức đoạn tuyến tính đang có thành phần β₂(β₀, s−k), thiếu toán tử max. Dạng đúng phải là y(s) = β₀ + β₁s + β₂ max(0, s−k).
- Mục 4.3: thị phần có tử số w có chỉ số ij dù văn bản định nghĩa trọng số của ví i; cần thống nhất pᵢ = wᵢ / tổng các wⱼ, với j từ 1 đến N. Chỉ số chạy của HHI cũng phải thống nhất: tổng pᵢ² theo i từ 1 đến N, không để chỉ số tổng j nhưng hạng tử là pᵢ. Khi N = 1, HHI thô bằng 1; HHI chuẩn hóa không xác định, cần phân biệt hai chỉ tiêu.
- Mục 4.4: công thức kỳ vọng hiện hiển thị dạng μₜ(1−p₀,ₜ), không phải phân số và thiếu xác suất vượt hurdle πₜ. Trong code `research_h124/temporal/hurdle_model.py`, hàm `predictions` tính `mean = prob * mu / den`. Vì vậy kỳ vọng tổng thể đúng là E(Yₜ | Xₜ) = πₜ μₜ / (1−p₀,ₜ). Kỳ vọng có điều kiện Yₜ > 0 mới bằng μₜ / (1−p₀,ₜ).
- Cũng ở 4.4, logistic và positive-count model phải dùng hai vector hệ số khác nhau, chẳng hạn β cho xác suất và γ cho mean NB chưa cắt: πₜ = logistic(Xₜ′β), μₜ = softplus(Xₜ′γ). Code fit hai vector riêng; không để người đọc hiểu nhóm đang ép chúng bằng nhau.
- Cần định nghĩa đủ likelihood hurdle, logistic và NB cắt tại 0; giải thích p₀,ₜ, r và việc μₜ là mean của NB trước khi cắt, không phải kỳ vọng tổng thể. Công thức HF đang có trong Word, không được kết luận thiếu chỉ vì đoạn trích chữ trống.

**5. Bớt diễn giải mạnh ở kết quả và kết luận.** Câu “ủng hộ cả ba giả thuyết” ở đầu phần 5 và 6 nên đổi thành: “Kết quả phù hợp mô tả với H1–H2 và gợi ý thông tin dự báo bổ sung cho H3; mô hình H3 chưa đạt calibration.” Khoảng knot 14–34% không phải ngưỡng cascade chung. H3 cải thiện log-score không đồng nghĩa đã dùng được để cảnh báo real-time.

**6. Sửa hai câu kết luận kỹ thuật.** Ở 5.2, “phân bố HF quyết định độ nhạy” nên là “kết quả phù hợp với vai trò của phân bố vị thế quanh ngưỡng HF”; chưa có phân rã để khẳng định yếu tố duy nhất quyết định. Ở 5.4, câu “các giả định huấn luyện khác nhau giữa các đặc tả” cần xác định đối tượng. Bốn hurdle mới dùng cùng train/validation/test và common support, nhưng có bộ biến và ridge được chọn riêng; các fit Hawkes/NB cũ mới có thể khác chế độ huấn luyện. Chỉ diễn giải chênh log-score như khác biệt mô tả giữa các đặc tả, không như causal effect của một biến.

**7. Hoàn thiện tài liệu tham khảo và trình bày.** Có ít nhất ba trích dẫn chưa có mục tương ứng: Xiong và cộng sự (2025), Schuler (2026), Cao và Gang (2026). Với nguồn SSRN, tác giả thứ hai là Palaash Gang; nên dùng Cao và Gang, kiểm tra bản PDF cụ thể đang trích. Xóa hoặc quy chiếu rõ ký hiệu “[L6]” ở 5.6 vì bài đang dùng tác giả–năm. Sửa tiểu mục “2.2. Cú sốc giá” thành “4.2.2”; “4.5 Đánh giá giả thuyết” thành “5.5”. Thống nhất tiếng Việt/Anh ở tên phần Data, Method và Findings. Thêm danh mục hình sau khi chèn A1, C1, D1 và cập nhật trường mục lục/danh mục bảng trong Word.

## 2. Đối chiếu các số chính

Đã đối chiếu gói evidence local và cách tính, không chỉ chép lại các con số từ bản thảo:

| Nội dung | Đối chiếu | Kết luận sử dụng |
| --- | --- | --- |
| H1 | `H1_stress_curves.csv`, lọc `scenario=joint`, `mapping=factor_family_1to1`; 13 quý, 61 mức/quý | Dùng cho đồ thị stress mô tả, không phải volume thanh lý thực thi |
| H2 | `H2_concentration_market.csv`, năm 2024, WETH, `market_fresh`, 300 giây, `market_USD` | Khớp cấu hình bảng chính; cần ghi cả support trong chú thích, không dùng mọi dòng cùng token |
| H3 | `H3_models.csv` | Log-score activity_history −11.070,51696; activity −11.352,57246; chênh 282,05549, nên làm tròn cuối cùng thành 282,06; dự báo/quan sát 1,459765 |
| RQ5 | CSV exposure gốc tại block 21.762.264 | 198 dòng, 188 có giá gồm 122 giá trị dương và 66 giá trị bằng 0; 10 chưa định giá; 69 ví |
| RQ6 | `RQ6_stylized_scenarios.csv` | Khớp cột nợ được trả của Bảng D2; phải dùng engine frozen này, không trộn engine pair/route mới |

Trong phần 5.4, “282,05 điểm” là hiệu của hai số log-score đã làm tròn đến 2 chữ số. Nếu tính từ output đầy đủ rồi mới làm tròn, dùng **282,06 điểm** và ghi quy tắc làm tròn nhất quán. Đây là sai khác làm tròn nhỏ, không thay đổi kết luận.

## 3. Abstract và Literature Review

`ABSTRACT.txt` chứa abstract tiếng Việt 151 đơn vị cách nhau bằng khoảng trắng, đáp ứng yêu cầu khoảng 150 từ. Abstract báo kết quả chính và giới hạn calibration, không khẳng định cascade thực hoặc nhân quả.

`LITERATURE_REVIEW_RUT_GON.md` là bản đề xuất thay phần 2, khoảng 1.590 từ theo cùng cách đếm, gồm cả tiêu đề và ghi chú biên tập; phần gốc khoảng 5.580 từ. Mức giảm xấp xỉ 71%. Có thể tăng thêm 200–400 từ cho một bảng đối chiếu nghiên cứu nếu giảng viên yêu cầu sâu hơn về empirical framework; không cần quay lại độ dài hiện tại.

Cách rút gọn: bỏ các đoạn lặp về DeFi so với tài chính truyền thống; giải thích HF/overcollateralization một lần; gom cơ chế thanh lý–giảm giá–thanh lý tiếp; bỏ phần lặp lại nguyên bảy RQ ở cuối mỗi tiểu mục; chuyển tham số mô hình sang Method. Giữ đối chiếu nghiên cứu trước, giới hạn phép đo, khoảng đóng góp và ba giả thuyết có thể đánh giá bằng kết quả hiện có. Phần dẫn ngay dưới tên mục 2 của file rút gọn là ghi chú cho người biên tập, không chép vào bài.

## 4. Lấy ba hình còn trống trong phụ lục

Đã xuất sẵn PNG 300 dpi và SVG trong thư mục `figures` cạnh báo cáo này. Không cần chạy lại mô hình để lấy hình. Các hình dùng nền trắng để phù hợp bài nghiên cứu, không lấy screenshot theme tối của dashboard.

### Hình A1

Chèn `figures/A1_stress_13_quarters.png` vào ô trống trước chú thích Hình A1. Nguồn là `deliverables/writing_materials_20261024/evidence/H1_stress_curves.csv`. Lọc chính xác `mapping=factor_family_1to1` và `scenario=joint`, giữ toàn bộ 13 quý; trục x là shock 0–60%, trục y là `eligible_debt_share × 100`. Mỗi quý có 61 điểm, không trộn dòng direct-token hoặc ETH-only/BTC-only. Không thêm khoảng tin cậy khi chưa có ước lượng tương ứng.

Có thể xem một quý trên Dashboard → Kết quả nghiên cứu → H1, chọn quý, joint và factor-family. Nhưng biểu đồ trang đó chỉ là một quý: ảnh chụp của nó không thay thế hình tổng hợp 13 quý. Muốn tự vẽ bằng Excel, mở `figures/A1_source.csv`, tạo PivotChart hoặc bảng pivot theo shock × quarter rồi vẽ line chart; phải đổi tỷ trọng sang định dạng phần trăm, tránh nhân 100 hai lần.

Chú thích giữ: “Tỷ trọng nợ đủ điều kiện thanh lý theo mức cú sốc joint ETH/BTC, 13 snapshot cuối quý Q1/2023–Q1/2026 (factor-family 1:1, lưới 1 điểm phần trăm). Đây là stress tĩnh, không phải thanh lý đã xảy ra.”

### Hình C1

Chèn `figures/C1_sampled_exposure_network.png`. Nguồn cần thêm ngoài gói evidence là `data/runs/recovery_20261020/processed/exposures_valued_sample.csv`; file summary hoặc bảng overlap một mình không đủ để dựng mạng. Hình gồm 69 nút ví, 3 nút giao thức và 40 nút tài sản có bản ghi định giá. Có 188 dòng priced nhưng chỉ 122 dòng dương được biểu diễn bằng liên kết tổng hợp; 66 dòng bằng 0 không vẽ cạnh và 10 dòng chưa có giá bị loại, không thay missing bằng 0.

Ví có nợ dương ở cả Comet và Morpho được tô cam: `0x00a2913501c4b09b92b825dc8a2937efdad9953b`. Mỗi exposure được biểu diễn qua hai liên kết ví–giao thức và giao thức–tài sản; hai liên kết này không phải hai khoản exposure được cộng với nhau. Độ rộng tăng theo căn bậc hai giá trị USD đã gộp; kích thước nút cố định. Màu phân biệt nợ, collateral và nợ của ví chung; đường nối không biểu diễn chiều lây lan hay dòng tiền nhân quả. Nhãn token lấy từ registry, chỉ dùng để hiển thị, không đưa cấu hình token hiện tại vào định giá lịch sử.

Đổi ghi chú gốc “kích thước nút và cạnh nên ghi rõ đơn vị” thành mô tả đúng encoding trên. Nếu hình đặt ngang trang, SVG cho phép phóng to mà không vỡ. Danh sách địa chỉ và token nằm trong `C1_wallet_labels.csv`, `C1_asset_labels.csv`; hình overview không in toàn bộ 69 địa chỉ dài. Không được đổi caption thành mạng toàn thị trường hoặc bản đồ contagion đã xác nhận.

### Hình D1

Chèn `figures/D1_cascade_stylized.png`. Nguồn là `deliverables/writing_materials_20261024/evidence/RQ6_stylized_scenarios.csv`, cùng snapshot và tham số frozen. So hai `case`: `assumed_impact` và `zero_impact_control`; trục x là shock 10%, 20%, 30%; trục y là `repaid_usd / 1.000.000`. Không lấy cột `seized_usd` hoặc terminal shortfall làm nợ được trả.

Giá trị cột tương ứng có/không có impact: 148,97/77,64; 604,18/385,26; 1.307,04/918,77 triệu USD. Giữ nhãn “mô phỏng cách điệu, chưa hiệu chuẩn”. Đây là kịch bản về nợ được trả, không phải volume quan sát hay nợ xấu on-chain. Có thể tự vẽ column chart từ `figures/D1_source.csv`, chia theo case; không cần refit hoặc crawl.

### Chèn vào Word và chạy lại hình

1. Mở bản sao của Word, bấm vào từng ô `[CHỪA CHỖ CHÈN HÌNH ...]`, xóa đúng dòng placeholder rồi dùng Insert → Pictures → This Device.
2. Chọn PNG tương ứng, để Wrap Text → In Line with Text, giữ tỷ lệ ảnh. Giữ chú thích và nguồn ngay dưới hình. Ưu tiên chiều rộng vùng văn bản; không ép chiều cao khiến hình méo. Với mạng C1, dùng trang phụ lục landscape nếu cần.
3. Dùng References → Insert Caption và Update Field cho danh mục hình/bảng. Nếu Word nén hình, chọn High fidelity hoặc Do not compress images trong tùy chọn lưu ảnh của tài liệu.
4. Script `ve_hinh_phu_luc.py` đọc dữ liệu đã có, kiểm tra cấu hình và SHA-256, xuất PNG/SVG cùng CSV nguồn. Từ thư mục repository chạy:

```powershell
python output/paper_review_20261026/ve_hinh_phu_luc.py
```

Môi trường cần matplotlib. Nếu môi trường hiện tại chưa có, có thể dùng môi trường riêng: `python -m venv .venv-figures`, cài matplotlib trong môi trường đó rồi gọi script bằng Python của `.venv-figures`. Không cần sửa môi trường mô hình chính. Script tự tìm repo từ vị trí của nó, vì vậy giữ nguyên thư mục `output/paper_review_20261026` khi sao chép sang clone.

`figures/figure_provenance.json` ghi nguồn, hash, số quý, số exposure và xác nhận dữ liệu nguồn không bị sửa. Nếu máy khác chỉ có code mà thiếu dataset exposure, riêng C1 sẽ không chạy được; dùng hình đã xuất hoặc cấp đúng CSV, không tự dựng cạnh từ summary.

## 5. Tài liệu tham khảo cần bổ sung

Ba mục sau đã được đối chiếu tại nguồn công bố/tổ chức lưu trữ. Đây là kiểm tra có mục tiêu, chưa phải xác minh toàn bộ bibliographic record của mọi tài liệu trong bản thảo.

- Xiong, X., Wang, Z., Chen, X., Knottenbelt, W., & Huth, M. (2025). *Leverage Staking with Liquid Staking Derivatives (LSDs): Opportunities and Risks*. 2025 IEEE International Conference on Blockchain and Cryptocurrency. DOI: 10.1109/ICBC64466.2025.11114596. Nguồn đại học: https://research.manchester.ac.uk/en/publications/leverage-staking-with-liquid-staking-derivatives-lsds-opportuniti
- Schuler, K. (2026). *Frictions in DeFi Liquidations: Evidence from the Aave V2 Main Market*. SSRN working paper, abstract 6522500. Nguồn: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6522500
- Cao, D., & Gang, P. (2026). *DeFi Liquidations Cluster Across Protocols in a Multivariate Hawkes Framework*. SSRN working paper. DOI: 10.2139/ssrn.6508318. Nguồn: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6508318

BIS WP1171 xác nhận tác giả Lioba Heimbach và Wenqian Huang, phù hợp mục hiện có: https://www.bis.org/publications/working-paper-1171-defi-leverage. Với working paper, ghi đúng phiên bản đã đọc và không gọi là bài đã phản biện nếu chưa có thông tin công bố tương ứng.

## 6. Thứ tự hoàn thiện đề xuất

Sửa công thức và phạm vi dữ liệu trước; sau đó thay abstract và rút gọn Literature Review; thống nhất H1–H3 với RQ1/RQ2/RQ4; chèn ba hình và bổ sung ba tham khảo; cuối cùng rà lại đánh số, caption, source và cách diễn giải “phù hợp mô tả/thông tin dự báo”. Phần Conclusion đang lặp nhiều con số của Findings, có thể rút tiếp còn một đoạn kết quả chính, một đoạn hàm ý và một đoạn giới hạn nếu cần giảm độ dài toàn bài.
