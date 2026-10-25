# Tài liệu tham khảo và cách sử dụng

Đối chiếu nguồn công khai ngày **24/10/2026**. Metadata đã đối chiếu không đồng nghĩa mọi bài đã được đọc lại toàn văn ở lượt này. Phân biệt kết quả của tài liệu với finding của dự án. Không có tuyên bố đã replicate hoàn toàn một bài chỉ vì dùng cùng protocol hoặc mô hình.

## A. Literature cốt lõi

**[L1] Gudgeon, L., Werner, S. M., Perez, D., & Knottenbelt, W. J. (2020). _DeFi Protocols for Loanable Funds: Interest Rates, Liquidity and Market Efficiency_. arXiv:2006.13922v3.** [Bản gốc](https://arxiv.org/abs/2006.13922v3). Metadata/abstract v3 đối chiếu lại; bài nền cho lending, liquidity và interest-rate mechanisms. Dự án không chạy VECM/UIP của bài này. Không lấy mẫu 2020 của họ làm dữ liệu Aave V3.

**[L2] Qin, K., Zhou, L., Gamito, P., Jovanovic, P., & Gervais, A. (2021). _An Empirical Study of DeFi Liquidations: Incentives, Risks, and Instabilities_. arXiv:2106.06389.** [Bản tác giả](https://arxiv.org/abs/2106.06389). Metadata/abstract đối chiếu lại. Dùng cho cơ chế/incentives và cách phân biệt liquidation mechanisms; liên quan RQ1/2/6. Các thống kê mẫu của họ không phải thống kê dataset hiện tại. Nếu trích phiên bản IMC, cần lấy đúng metadata proceedings thay vì gán DOI chưa kiểm tra.

**[L3] Warmuz, J., Chaudhary, A., & Pinna, D. (2022; revised 2023). _Toxic Liquidation Spirals_. arXiv:2212.07306.** [Bản gốc và lịch sử phiên bản](https://arxiv.org/abs/2212.07306). Metadata/abstract đối chiếu lại. Đặt cơ chế liquidation incentives và toxic spirals trong background RQ6/7; chưa chứng minh engine của nhóm tái tạo chính xác sự kiện CRV2022 hoặc chính sách đề xuất của tác giả.

**[L4] Lehar, A., & Parlour, C. A. (2022). _Systemic fragility in decentralised markets_. BIS Working Papers No.1062.** [Trang xuất bản](https://www.bis.org/publications/working-paper-1062-systemic-fragility-decentralised-markets), [PDF](https://www.bis.org/publ/work1062.pdf). Nguồn chính thức đối chiếu lại; liên quan thanh lý, collateral risk và market feedback. Dùng motivation H3/RQ6; không thừa hưởng identification hay con số amplification từ bài để coi là kết quả dự án.

**[L5] Chiu, J., Ozdenoren, E., Yuan, K., & Zhang, S. (2023). _On the Fragility of DeFi Lending_. Bank of Canada Staff Working Paper2023-14. DOI:10.34989/swp-2023-14.** [Trang gốc](https://www.bankofcanada.ca/2023/02/staff-working-paper-2023-14/). Authors/abstract đối chiếu lại. Mô hình động về contract rigidity/information friction, hỗ trợ phần cơ chế kinh tế; không phải historical dataset để ghép trực tiếp vào mẫu Aave V3. Nhóm chưa ước lượng mô hình cân bằng động của bài.

**[L6] Chiu, J., & Danisman, F. (2026). _DeFi Lending: Returns, Leverage, and Liquidation Risk_. Bank of Canada Staff Analytical Paper2026-13. DOI:10.34989/sap-2026-13.** [PDF chính thức, cập nhật02/04/2026](https://www.bankofcanada.ca/wp-content/uploads/2026/04/sap2026-13.pdf). Đã đối chiếu phần Identification of Margin Trading. Đây là **Staff Analytical Paper**, không gán thành Staff Working Paper. Motif bài gồm borrow→swap sang collateral trong một ngày→dùng collateral để borrow thêm trong ngày tiếp theo; là nhận diện xấp xỉ. RQ3 temporal của nhóm chưa xác minh cùng cash-flow path, nên chưa gọi là replication đầy đủ. Cần đối chiếu data-section/table footnotes khi lấy kỳ mẫu: không khẳng định mọi phần trong PDF dùng một cutoff giống nhau. Số22B/20,46% của tác giả không phải finding nhóm.

**[L7] Heimbach, L., & Huang, W. (2024). _DeFi leverage_. BIS Working Papers No.1171.** [Trang gốc](https://www.bis.org/publications/working-paper-1171-defi-leverage), [PDF](https://www.bis.org/publ/work1171.pdf). Nhóm đã tham khảo full PDF ở lượt nghiên cứu trước; metadata đối chiếu lại. Dùng đối chiếu borrower leverage/debt-at-risk và HF bands. Quarter-end Aave V3 của nhóm khác daily borrower panel và protocol vintage của họ; chưa đo toàn bộ external wallet assets hoặc leverage giống bài.

**[L8] Sasi-Brodesky, A., & Kaousar Nassr, I. (2023). _DeFi liquidations: Volatility and liquidity_. OECD Working Papers on Finance, Insurance and Private Pensions, No.48. DOI:10.1787/0524faaf-en.** [Trang chính thức](https://www.oecd.org/en/publications/defi-liquidations_0524faaf-en.html). Full PDF đã tham khảo trong lượt trước; metadata/abstract đối chiếu lại. Dùng matched token/time design và mối liên hệ volatility/liquidity. H2 concentration của nhóm chưa là OLS/2SLS replication; predictive association của H3 chưa tự có identification như một mô hình instrumental variables.

## B. Tài liệu cần xác minh phiên bản trước khi cite như nguồn chính

**[P1] _DeFi Liquidations Cluster Across Protocols in a Multivariate Hawkes Framework_. SSRN abstract6508318.** [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6508318), [bản tác giả từng tham khảo](https://www.researchgate.net/publication/403263179_DeFi_Liquidations_Cluster_Across_Protocols_in_a_Multivariate_Hawkes_Framework).

Direct SSRN vẫn trả403 ở lượt này. Hồ sơ cũ ghi Dung Cao và Palaash/Palaash Gang nhưng author/version metadata chưa đồng nhất; **chưa đưa vào BibTeX chính thức với authors/year đã chốt**. Nhóm đã đọc bản preprint tác giả ở lượt trước; chưa xác minh tương đương bản SSRN sửa tháng7. Bản đó gắn block21.525.600 với31/12/2025 trong khi kiểm tra archive của nhóm cho31/12/2024. Phải đối chiếu bản PDF chính thức trước khi replicate numerical results. Không suy luận tác giả sai ở mọi phiên bản từ một bản preprint.

## C. Tài liệu phương pháp

**[M1] Hawkes, A. G. (1971). _Spectra of some self-exciting and mutually exciting point processes_. Biometrika,58(1),83–90. DOI:10.1093/biomet/58.1.83.** [Publisher metadata](https://academic.oup.com/biomet/article-abstract/58/1/83/224809?login=false). Metadata đối chiếu; cơ sở Hawkes. Hurdle model bổ sung của nhóm chưa phải một structural Hawkes process. Không dùng tên Hawkes để diễn giải mọi biến lagged count thành causal excitation.

Hurdle logistic + zero-truncated NB trong lượt mới được mô tả bằng phương trình và implementation của nhóm; phần inference sử dụng randomized PIT iid-uniform Monte Carlo, khác event-path bootstrap cũ. Trước bản nộp cần bổ sung tài liệu gốc về hurdle/count calibration phù hợp quy định tạp chí; chưa giả vờ đã đọc toàn văn một nguồn có paywall.

## D. Protocol và nguồn dữ liệu

**[D1] Aave. _Pool smart-contract documentation_.** [Docs](https://www.aave.com/docs/aave-v3/smart-contracts/pool). Quy tắc debtToCover/collateral và HF; đây là tài liệu hiện hành. Historical research phải theo deployment/revision/cấu hình đúng block, không mặc định docs hiện tại mô tả mọi quý2023–2026.

**[D2] Compound. _Compound III: Liquidation_.** [Docs](https://docs.compound.finance/liquidation/), [Comet specification](https://github.com/compound-finance/comet/blob/main/SPEC.md). Dùng phân biệt absorption và buyCollateral; thanh toán bằng reserves khác Aave liquidator repayment. Bản main hiện hành không thay kiểm chứng implementation lịch sử.

**[D3] Morpho. _Liquidation on Morpho_.** [Docs](https://docs.morpho.org/learn/concepts/liquidation/). LLTV và liquidation eligibility theo market; không áp nguyên health-factor implementation Aave cho Morpho.

**[D4] Kraken. _Get Recent Trades_.** [API docs](https://docs.kraken.com/api-reference/market-data/get-recent-trades). Nguồn trade USDC/USD; nhóm lưu raw/hash/cursor, kiểm chứng since và quarantine gap. Một venue, trade timestamps + assumed latency chưa phải receipt-time measured, consolidated price hoặc DEX execution quote.

Ngày truy cập các docs:24/10/2026. Khi viết bài, tách bibliography học thuật với Data/Software Availability. Có thể dẫn các source above bằng mã[Lx]/[Dx] trong dossier rồi thay bằng format của tạp chí.
