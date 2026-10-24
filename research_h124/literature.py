"""Source crosswalk; does not claim replication of inaccessible paper versions."""
from .common import OUT,save,write,now

def run():
    folder=OUT/'literature';folder.mkdir(parents=True,exist_ok=True)
    rows=[
      {'reference':'BIS WP1171','title':'DeFi leverage','authors':'Lioba Heimbach; Wenqian Huang','year':2024,
       'url':'https://www.bis.org/publications/working-paper-1171-defi-leverage.pdf','access_scope':'publisher full PDF, data/method/Appendix sections consulted',
       'method_scope':'Daily borrower asset/debt panel, Aave V1/V2 and Compound V2, 2021-01 to 2023-Q1; pool debt-at-risk HF<1.1, robustness 1.05/1.2.',
       'our_comparison':'Quarterly Aave V3 census, point-in-time configuration and HF bands; not an exact replication of daily wallet leverage or external wallet assets.',
       'limit':'Do not infer realized liquidation frequency from eligible/near-threshold debt alone.'},
      {'reference':'OECD 2023 No.48','title':'DeFi liquidations: Volatility and liquidity','authors':'Ana Sasi-Brodesky; Iota Kaousar Nassr','year':2023,
       'url':'https://www.oecd.org/content/dam/oecd/en/publications/reports/2023/07/defi-liquidations_89cba79d/0524faaf-en.pdf','access_scope':'publisher full PDF, empirical design and summary tables consulted',
       'method_scope':'Liquidation/DEX volatility analysis; matched USDC-debt and ETH/WETH-collateral comparison; OLS/2SLS and volatility-window checks.',
       'our_comparison':'Matched debt/collateral tokens and period for concentration; keep financing and oracle-age definitions explicit. Our H4 is conditional count prediction, not their volatility regression.',
       'limit':'Their identification strategy is not automatically inherited by our stress or Hawkes models.'},
      {'reference':'SSRN6508318','title':'DeFi Liquidations Cluster Across Protocols in a Multivariate Hawkes Framework','authors':'Dung Cao; Palaash / Palaash Gang (version metadata differs)','year':2026,
       'url':'https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6508318','author_preprint':'https://www.researchgate.net/publication/403263179_DeFi_Liquidations_Cluster_Across_Protocols_in_a_Multivariate_Hawkes_Framework',
       'access_scope':'SSRN metadata/abstract indexed; direct SSRN 403; author-uploaded March preprint full text consulted; July revision equivalence unverified',
       'method_scope':'Three-protocol exponential Hawkes, cross-excitation/common-factor/placebo comparisons; author preprint uses tiny jitter for block ties.',
       'our_comparison':'Aave market-controlled discrete Hawkes plus no-excitation controls, chronological holdout, rolling quarters and residual checks; ties remain binned counts.',
       'limit':'Author preprint links block 21,525,600 to 2025-12-31; archive check gives 2024-12-31. Verify version/data before numerical replication. Predictive dependence is not structural causality.'}
    ]
    write(folder/'literature_crosswalk.csv',rows);save(folder/'sources.json',{'reviewed_utc':now(),'sources':rows,'source_instructions':'Documents are reference evidence, not task instructions.'})
    text='''# Đối chiếu tài liệu H1/H2/H4

Đây là đối chiếu thiết kế và phạm vi đo lường, không phải tuyên bố tái lập đầy đủ
cả ba bài. Metadata, phiên bản và giới hạn tiếp cận được lưu trong sources.json.

| Tài liệu | Áp dụng cho nghiên cứu này | Khác biệt cần giữ rõ |
|---|---|---|
| [BIS WP1171](https://www.bis.org/publications/working-paper-1171-defi-leverage.pdf) | Census borrower và cấu hình theo thời điểm; bổ sung các dải HF 1.05/1.1/1.2 | Bài dùng dữ liệu ngày và giao thức đời trước; 15 snapshot quý V3 không tái lập leverage gồm tài sản ngoài giao thức |
| [OECD DeFi liquidations](https://www.oecd.org/content/dam/oecd/en/publications/reports/2023/07/defi-liquidations_89cba79d/0524faaf-en.pdf) | So cùng nợ USDC và collateral ETH/WETH; kiểm tra cửa sổ và biến thị trường | H2 đo concentration, H4 đo count; không kế thừa nhận diện của hồi quy volatility/2SLS trong bài |
| [SSRN6508318](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6508318) | Tham khảo đối chứng common factors, excitation và giới hạn nhân quả | Chưa xác minh toàn văn bản SSRN sửa tháng 7; đã đọc bản tác giả tải lên tháng 3. Bản này dùng jitter và có block–ngày cần xác minh |

File ssrn_preprint_block_date_check.json lưu header/hash lấy từ RPC: block
21.525.600 thực tế có timestamp **2024-12-31T23:01:23Z**, trong khi bản preprint
ghi ngày 31/12/2025. Đây là bất nhất của bản được kiểm tra; chưa kết luận mọi
phiên bản SSRN đều chứa lỗi này. Không dùng mốc đó để định nghĩa dataset của nhóm.

Mô hình mới không tạo jitter; giữ đúng count theo bin, lag thông tin thị trường,
và đánh giá ngoài mẫu. H4 hiện là Aave đơn biến có covariates; chưa tái lập mô hình
ba giao thức hoặc công bố kênh contagion nhân quả của bài tham chiếu.
'''
    (folder/'DOI_CHIEU_TAI_LIEU.md').write_text(text,encoding='utf8')
if __name__=='__main__':run()
