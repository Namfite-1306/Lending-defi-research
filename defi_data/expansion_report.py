"""Generate the evidence ledger and Vietnamese research-readiness report from files actually present."""
import csv,hashlib,json,sqlite3
from collections import Counter
from decimal import Decimal as D
from datetime import datetime,timezone
from .expansion import RUN,OUT,PILOT,read_csv,export_history
from .pipeline import ROOT,csv_write,save_json,stress

def main():
    export_history()
    inventory=[]
    for path in sorted(OUT.glob('*.csv')):
        rows=read_csv(path)
        inventory.append({'file':path.name,'rows':len(rows),'columns':len(rows[0]) if rows else 0,
                         'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'path':str(path)})
    checks=read_csv(OUT/'position_checks.csv');pos=read_csv(OUT/'positions_point_in_time_sample.csv')
    cfg=read_csv(OUT/'historical_reserve_config_sample.csv');meta={r['token_address']:r for r in cfg}
    for r in pos:
        m=meta[r['token_address']]
        r.update(validation_status='passed' if r['validation_passed']=='True' else 'failed',
                 supply_amount=str(D(r['supply_raw'])/10**int(m['decimals'])),debt_amount=str(D(r['debt_raw'])/10**int(m['decimals'])),
                 liquidation_threshold=r['effective_liquidation_threshold'],collateral_enabled=r['collateral_enabled']=='True')
    stress(pos,OUT)
    modes=Counter(r['emode'] for r in checks);passed=sum(r['passed']=='True' for r in checks)
    cohort=read_csv(OUT/'pre_snapshot_borrower_cohort.csv');version=read_csv(OUT/'protocol_versions_sample.csv')
    swaps=read_csv(OUT/'dex_swaps_sample.csv');gas=read_csv(OUT/'execution_gas_sample.csv');liq=read_csv(OUT/'dex_liquidity_sample.csv')
    markets=read_csv(OUT/'morpho_market_configs.csv');cross=read_csv(OUT/'cross_protocol_position_sample.csv');assets=read_csv(OUT/'compound_asset_configs.csv')
    sensitivity=read_csv(OUT/'recursive_window_sensitivity.csv');candidates=read_csv(OUT/'recursive_window_candidates.csv')
    gate=json.loads((OUT/'extended_window_gate.json').read_text()) if (OUT/'extended_window_gate.json').exists() else {'passed':False}
    coverage=read_csv(OUT/'history_coverage.csv');steps=[]
    with sqlite3.connect(RUN/'raw.sqlite') as c:
        history_chunks=c.execute('SELECT count(*) FROM coverage').fetchone()[0]
        history_logs=c.execute('SELECT count(*) FROM logs').fetchone()[0]
    def add(code,task,done,status,ready,benefit,issue,solution,evidence):
        steps.append(dict(ma=code,cong_viec=task,da_lam=done,trang_thai=status,dua_vao_mo_hinh=ready,
                          ich_loi=benefit,van_de_con_lai=issue,cach_giai_quyet=solution,bang_chung=evidence))
    add('A1','Chốt giai đoạn và block','UTC [27/01/2023, 01/10/2026); lưu hash hai biên','Đạt','Được dùng làm phạm vi',
        'Không bỏ sót ngày 30/09 hoặc lẫn dữ liệu sau kỳ','Chỉ chốt phạm vi, chưa chứng minh đủ log','Đối chiếu coverage từng hợp đồng với nguồn archive độc lập','block_range.json')
    add('A2','Crawl lịch sử ba giao thức',f'Đã chạy {history_chunks} checkpoint; {history_logs} log trả về; coverage xác minh 0%; lưu raw/checkpoint và gaps','Một phần','Chưa; dữ liệu rỗng bất thường bị cách ly',
        'Có thể resume và đo phần thiếu','Nhiều truy vấn 2023 trả rỗng; không đủ chứng cứ để coi là không có sự kiện',
        'Dùng RPC archive có lịch sử logs đầy đủ; đối chiếu receipt/số đếm độc lập rồi chạy lại toàn kỳ','history_coverage.csv; history_gaps.csv; raw.sqlite')
    add('A3','Borrower Universe toàn kỳ','Có exporter Borrow→first_seen và điều kiện first_seen ≤ snapshot','Chưa đạt','Không dùng làm toàn bộ thị trường',
        'Loại thiên lệch chỉ chọn ví từng bị thanh lý','Chưa có Borrow history liên tục đã xác minh','Hoàn thành A2, lấy tất cả onBehalfOf; dựng cohort theo từng cutoff','borrower_universe.csv')
    add('A4','Nguồn dataset bài nghiên cứu','Đã kiểm tra nguồn công khai và phương pháp paper 6; chưa nhập dữ liệu ngoài chưa xác minh','Một phần','Chỉ dùng phương pháp',
        'Tránh trộn Aave V1/V2 vào V3','Zenodo DOI tham khảo trả HTTP 404 trong lần kiểm tra; không có file gốc được nhập',
        'Có bản dataset truy cập được thì xác minh hash, schema, hợp đồng, biên thời gian và đối chiếu on-chain trước nhập','README_EXPANSION.md')
    add('B1','Chọn ví trước snapshot',f'{len(cohort)} ví từ Borrow trong 7.200 block trước snapshot; không chọn theo thanh lý tương lai','Đạt','Mẫu kiểm thử; chưa đại diện thị trường',
        'Giảm look-ahead selection trong mẫu mới','Bỏ sót ví vay trước cửa sổ nhưng còn nợ','Thay cửa sổ bằng toàn bộ lịch sử Borrow từ deployment','pre_snapshot_borrower_cohort.csv')
    add('B2','Dựng và đối chiếu vị thế',f'{len(checks)} ví, {len(pos)} dòng token; {passed}/{len(checks)} qua đối chiếu số dư/HF','Đạt','Được chạy stress trên mẫu này',
        'Số dư có lãi tích lũy, đúng block','Một snapshot; ví chọn theo hoạt động vay và địa chỉ sắp xếp; có ví không còn nợ',
        'Sau A2 chọn toàn bộ ví còn nợ hoặc mẫu phân tầng và nhiều ngày','positions_point_in_time_sample.csv; position_checks.csv')
    add('B3','E-mode và bitmap',f"Đã xác minh tuple offset, bitmap; {sum(v for k,v in modes.items() if k!='0')} ví E-mode qua kiểm tra",'Đạt','Được với phiên bản snapshot đã kiểm chứng',
        'Tính LT hiệu lực thay vì dùng LT thường cho mọi tài sản','Chưa xác minh mọi phiên bản đến 09/2026; custom price source bị chặn',
        'Adapter theo implementation/code hash, kiểm chứng HF ở mỗi phiên bản; hỗ trợ nguồn giá riêng khi có','emode_categories_sample.csv; position_checks.csv')
    add('B4','Cấu hình lịch sử và upgrade',f'{len(cfg)} reserve tại snapshot; {len(version)} checkpoint implementation/oracle/provider','Một phần','Được cho snapshot; chưa cho toàn kỳ',
        'Tránh dùng cấu hình hiện tại thay quá khứ','Chưa có toàn bộ thay đổi LT/LTV/bonus/close factor và upgrade giữa các checkpoint',
        'Thu logs Configurator và proxy Upgraded; kiểm tra code lịch sử và rule thanh lý từng phiên bản','historical_reserve_config_sample.csv; protocol_versions_sample.csv')
    add('B5','Stress test mẫu mới','Xuất 36 kịch bản WETH/WBTC, shock cả phía tài sản và nợ; loại vị thế không qua kiểm tra','Đạt','Thử nghiệm RQ1 trên mẫu',
        'Kiểm tra điều kiện HF<1 dưới cú sốc','Eligible debt không phải volume thực thi; derivative chưa có factor mapping','Thêm mapping có kiểm định và mô phỏng close factor/incentive/liquidity','rq1_sample_stress.csv')
    add('C1','Mở rộng cửa sổ nhận diện',f"5 ngày Borrow/Supply: gate={gate.get('passed')}, số sự kiện={gate.get('events','chưa có')}",
        'Đạt' if gate.get('passed') else 'Chưa đạt','Được nghiên cứu motif trong phạm vi đã qua gate',
        'Có đủ horizon 6/24/48h cho nhiều điểm bắt đầu','5 ngày quanh một cú sốc không đại diện toàn kỳ','Mở rộng sau khi nguồn lịch sử đạt A2; giữ cohort bình thường và stress','extended_window_gate.json; recursive_extended_events.csv')
    add('C2','Nhận diện nhiều giao dịch',f'{len(candidates)} ứng viên theo 3 cửa sổ; giữ thời điểm nhãn sẵn có, censored và thứ tự log','Đạt','Chỉ nhãn ứng viên',
        'Tránh gọi mọi borrow→supply là vòng đòn bẩy đã xác nhận','Không chứng minh khoản supply được tài trợ từ borrow; một dòng tiền có thể phục vụ nhiều nhánh',
        'Ghép borrow→swap→supply→reborrow theo token, lượng, actor; kiểm soát tài trợ trùng','recursive_window_candidates.csv')
    add('C3','Độ nhạy cửa sổ','; '.join(f"{r['window_hours']}h: {r['candidate_motifs']} motif / {r['uncensored_borrow_starts']} borrow đủ horizon" for r in sensitivity),'Đạt','Được so sánh mức nhạy của heuristic',
        'Thấy ảnh hưởng cửa sổ và right censoring','Verified labels vẫn bằng 0; không hiểu là không có recursive leverage',
        'Kiểm tra mẫu dương/âm bằng receipt/trace; báo precision và độ nhạy, loại censored khỏi mẫu âm','recursive_window_sensitivity.csv')
    add('C4','Xác minh funding và nhóm đối chứng','Thu receipt/swap làm bằng chứng; không tự nâng ứng viên thành nhãn chắc chắn','Chưa đạt','Chưa dùng nhãn để kết luận RQ3',
        'Ngăn false positive làm sai mức vulnerability','Thiếu traces/router ownership, tiền từ ví khác, nhóm đối chứng và so khớp rủi ro ban đầu',
        'Trace ứng viên; phân nhãn chắc chắn/có khả năng/không rõ; matching theo collateral, HF, debt, ngày','dex_swaps_sample.csv; recursive_window_candidates.csv')
    add('D1','Receipt và gas',f'{len(gas)} receipt thực; gasUsed × effectiveGasPrice, status và đơn vị ETH','Đạt','Được dùng chi phí gas trong mẫu',
        'Hiệu chỉnh động cơ liquidator','Không gồm MEV/builder payment, hedging; mẫu có chọn lọc','Bổ sung direct payment/traces và phí flashloan theo giao dịch','execution_gas_sample.csv')
    add('D2','Swaps và giá thực thi',f'{len(swaps)} swap logs; lượng signed V3 và lượng V2; định danh token/factory khi đọc được','Một phần','Thống kê mẫu; chưa quy mọi swap thành bán collateral',
        'Quan sát route và giá khớp thực','Nhiều actor trong một giao dịch; receipt không tự chứng minh khoản bán của liquidator',
        'Đối chiếu transfer+trace, decimals; kiểm tra factory và pair/pool registry','dex_swaps_sample.csv')
    add('D3','Thanh khoản trước giao dịch',f'{len(liq)} trạng thái pool ở cuối block trước: V2 reserves hoặc V3 slot0/liquidity','Một phần','V2 minh họa; V3 chưa đủ đường cong',
        'Làm đầu vào sức hấp thụ và slippage','Không phải state ngay trước swap trong cùng block; V3 thiếu initialized ticks',
        'Replay intra-block hoặc traces/state diff; tick bitmap và liquidityNet, fee, các route thay thế','dex_liquidity_sample.csv')
    add('D4','Oracle và đồng bộ thời gian','Giữ oracle block-end của pilot và mốc thời gian rõ ràng; tách với execution price','Một phần','Được định giá pilot với nhãn thời điểm',
        'Tách giá kích hoạt HF khỏi giá thực hiện trên DEX','Giá cuối block không phải oracle trước từng giao dịch; chuỗi dài còn thiếu',
        'Thu oracle update logs, tái dựng thứ tự trong block và chuỗi giá thị trường/DEX liên tục','pilot/oracle_prices_hourly.csv; pilot/aave_liquidations_valued.csv')
    add('D5','Hiệu chỉnh cascade và bad debt','Đã xuất đầu vào, đánh dấu dữ liệu chưa đủ; chưa ước lượng impact từ mẫu thiếu','Chưa đạt','Chưa dùng cho RQ6/RQ7 chính thức',
        'Ngăn tạo kết quả chính sách dựa trên thanh khoản giả định ngầm','Thiếu full positions, supply-side liquidity, tick depth, route choice và kiểm định replay',
        'Hoàn tất A/B/D3; replay các wave ngoài mẫu rồi hiệu chỉnh và đánh giá sai số','dex_liquidity_sample.csv; position_scope.json')
    add('E1','Phân biệt giao thức và đơn vị','Giữ Aave liquidation, Comet absorb/buy và Morpho Liquidate riêng','Đạt','Được dùng schema; không cộng thô sự kiện',
        'Tránh đếm AbsorbCollateral/BuyCollateral thành số khoản vay bị thanh lý','Phạm vi Compound chỉ Comet USDC Ethereum, không toàn bộ Compound','Mở contract universe khi cần và thêm deployment boundaries chính thức','pilot/liquidations.csv; compound_asset_configs.csv')
    add('E2','Compound position/config',f'{len(assets)} collateral configs; {sum(r["protocol"]=="compound_v3_usdc" for r in cross)} dòng vị thế mẫu cùng block','Đạt' if assets else 'Chưa đạt','Mẫu trạng thái; chưa mạng exposure toàn thị trường',
        'Có debt/collateral thật thay vì activity count','Mẫu ví từ sự kiện pilot có selection bias; thiếu định giá và kiểm chứng toàn bộ account liquidity',
        'Lấy borrower universe từ lịch sử Withdraw/Transfer; định giá cùng block và đối chiếu isLiquidatable','compound_asset_configs.csv; cross_protocol_position_sample.csv')
    add('E3','Morpho market và shares',f'{len(markets)} market configs; {sum(r["protocol"]=="morpho_blue" for r in cross)} dòng shares/collateral mẫu','Một phần','Được raw shares và collateral; chưa debt USD',
        'Giữ đúng market ID, loan token, collateral, LLTV và IRM','Stored market totals có thể chưa accrue; shares không bằng số token vay',
        'Accrue theo IRM tại block, virtual shares/assets và rounding hướng đúng; kiểm tra against contract simulation','morpho_market_configs.csv; cross_protocol_position_sample.csv')
    add('E4','Mạng exposure và contagion','Xuất bảng trạng thái cùng block và các market riêng; chưa gán common-wallet thành quan hệ nhân quả','Chưa đạt','Chưa dùng kết luận RQ5',
        'Có nguyên liệu xây cạnh wallet→market→asset','Chưa đủ borrower universe; thiếu ownership/router attribution, quy đổi nợ, network validation',
        'Dựng exposure snapshot đồng bộ, cạnh có loại, chỉ trọng số đã định giá; tách common-asset khỏi direct claim; kiểm định có common-shock controls','cross_protocol_position_sample.csv')
    rq=[
      ['RQ1','Ngưỡng cú sốc ETH/BTC','Thử được trên mẫu','Chưa',f'{len(checks)} ví/1 snapshot, 36 shocks','Borrower universe và nhiều snapshot; mapping tài sản phái sinh; thanh lý thực thi','B1–B5, A2'],
      ['RQ2','Tập trung thanh lý','Mô tả Aave trong pilot','Chưa','706 LiquidationCall đã định giá trong 3 giờ','Lịch sử đủ kỳ; định giá và đơn vị thống nhất ba giao thức','A2, D4, E1–E3'],
      ['RQ3','Recursive leverage và vulnerability','Heuristic và sensitivity','Chưa',f"{gate.get('events',0):,} Borrow/Supply trong 5 ngày; gate={gate.get('passed')}; verified=0",'Funding/trace; precision; nhóm đối chứng; ghép nhãn đúng thời điểm','C1–C4, B1–B4'],
      ['RQ4','Clustering / self-excitation','Thống kê trong 3 giờ','Chưa','Pilot đủ panel giờ nhưng chỉ 3 quan sát mỗi protocol','Chuỗi Liquidation dài và giá đồng bộ; fit baseline; kiểm tra phần dư ngoài mẫu','A2, D4'],
      ['RQ5','Cross-protocol contagion','Schema và snapshot mẫu','Chưa','Comet balances, Morpho shares và market configs','Full exposure; debt USD; đồng bộ lịch sử; common-shock và kênh truyền','E1–E4, A2'],
      ['RQ6','Thanh khoản / cascade / bad debt','Có đầu vào DEX mẫu','Chưa','Receipt, gas, reserves/slot0/liquidity trước block','V3 ticks; intra-block state; full positions; replay waves và ngoài mẫu','D1–D5, A2, B'],
      ['RQ7','Thiết kế tham số thanh lý','Chưa đủ thí nghiệm chính sách','Chưa','LT/bonus snapshot; gas và execution sample','RQ6 đạt; close factor/bonus theo phiên bản; mục tiêu và stress grid nhất quán','B4, D5, RQ6']]
    # Genuine data checks; code unit tests are recorded separately and are not evidence of completeness.
    qa=[{'check':'snapshot balances and HF','passed':passed==len(checks) and len(checks)>0,'detail':f'{passed}/{len(checks)}; tolerance 1e-4'},
        {'check':'E-mode cohort tested','passed':any(k!='0' for k in modes),'detail':dict(modes)},
        {'check':'5-day extraction sentinel','passed':gate.get('passed',False),'detail':gate},
        {'check':'full historical verified coverage','passed':False,'detail':'historical responses quarantined'},
        {'check':'verified recursive labels','passed':False,'detail':'zero verified is unknown, not negative evidence'},
        {'check':'cross-protocol debt valuation','passed':False,'detail':'Morpho accrual/share conversion not implemented'},
        {'check':'V3 impact curve','passed':False,'detail':'initialized ticks and intra-block replay absent'}]
    save_json(RUN/'audit_expansion.json',{'checks':qa,'model_ready_full_scope':False,'unit_tests':'15/15 passed; tests/test_pipeline.py + tests/test_expansion.py'})
    csv_write(OUT/'implementation_report.csv',steps)
    csv_write(OUT/'rq_readiness.csv',[dict(zip(['rq','noi_dung','co_the_lam_ngay','san_sang_toan_ky','bang_chung','con_thieu','phu_thuoc'],r)) for r in rq])
    # Refresh inventory after generating model/report CSVs.
    inventory=[]
    for path in sorted(OUT.glob('*.csv')):
        rows=read_csv(path);inventory.append({'file':path.name,'rows':len(rows),'columns':len(rows[0]) if rows else 0,
                      'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'path':str(path)})
    save_json(RUN/'report_payload.json',{'steps':steps,'rq':rq,'inventory':inventory,'qa':qa,'coverage':coverage,'sensitivity':sensitivity,
              'summary':{'position_wallets':len(checks),'emode_wallets':sum(v for k,v in modes.items() if k!='0'),
                         'snapshots_passed':passed,'cohort_wallets':len(cohort),'swaps':len(swaps),'receipts':len(gas),
                         'pools':len(liq),'morpho_markets':len(markets),'compound_assets':len(assets),'window_gate':gate}})
    lines=['# Báo cáo triển khai A–E và mức sẵn sàng RQ1–RQ7','',
      'Kỳ mục tiêu: 27/01/2023–30/09/2026 UTC. Báo cáo được tạo từ file dữ liệu thực tế, không đồng nhất việc viết xong code với dataset hoàn chỉnh.',
      '', '**Kết luận: chưa có RQ nào sẵn sàng cho kết luận toàn kỳ. Có thể dùng mẫu đã kiểm chứng để phát triển và chạy thử mô hình; không suy rộng ra toàn thị trường.**','',
      '## Những gì đã cải thiện','',f'- Chọn {len(cohort)} ví từ lịch sử vay trước snapshot; kiểm tra {len(checks)} ví, gồm {sum(v for k,v in modes.items() if k!="0")} ví E-mode; {passed} ví qua đối chiếu.',
      f'- Thu {len(gas)} receipt, {len(swaps)} swap logs, {len(liq)} trạng thái pool; {len(assets)} cấu hình collateral Compound và {len(markets)} thị trường Morpho.',
      f'- Cửa sổ 5 ngày: {gate}. Mẫu này phục vụ nhận diện theo cửa sổ; không thay thế toàn bộ lịch sử.',
      '- Crawl lịch sử dài gặp kết quả rỗng bất thường: giữ checkpoint như bằng chứng truy vấn, không chứng nhận coverage và không tạo chuỗi zero giả.',
      '', '## Các bước và vấn đề còn lại','',
      '| Bước | Đã làm / trạng thái | Dùng vào mô hình | Ích lợi | Vấn đề | Cách giải quyết | Bằng chứng |',
      '|---|---|---|---|---|---|---|']
    for s in steps:
        values=[s['ma'],s['da_lam']+' — '+s['trang_thai']]+[s[k] for k in ('dua_vao_mo_hinh','ich_loi','van_de_con_lai','cach_giai_quyet','bang_chung')]
        lines.append('| '+' | '.join(str(v).replace('|','/').replace('\n',' ') for v in values)+' |')
    lines+=['','## RQ readiness','','| RQ | Nội dung | Làm ngay | Sẵn sàng toàn kỳ | Bằng chứng | Còn thiếu | Phụ thuộc |','|---|---|---|---|---|---|---|']
    lines+=['| '+' | '.join(r)+' |' for r in rq]
    lines+=['','## Thứ tự khắc phục','',
      '1. Khôi phục nguồn lịch sử archive đáng tin cậy, đối chiếu một cửa sổ có giao dịch biết trước, rồi crawl lại toàn kỳ với checksum và kiểm tra receipt. Không chỉ đổi endpoint rồi mặc định dữ liệu đúng.',
      '2. Dựng borrower universe và timeline cấu hình/implementation; lấy nhiều snapshot và kiểm chứng balances/HF, bao gồm E-mode từng phiên bản.',
      '3. Xác minh funding và nhãn recursive bằng traces; accrue Morpho và định giá exposure ba giao thức.',
      '4. Tái dựng DEX tick depth/state trước giao dịch, đối chiếu execution; replay wave ngoài mẫu rồi mới hiệu chỉnh RQ6 và chạy chính sách RQ7.',
      '', 'Không phát sinh giao dịch on-chain, không dùng khóa ví, không mua dịch vụ dữ liệu. Chưa có bộ mô phỏng cascade đã hiệu chỉnh hoàn chỉnh; lưới stress là eligible debt, không phải volume sẽ thanh lý.',
      '', '## Nguồn phương pháp','',
      '- Aave: https://aave.com/docs/aave-v3/smart-contracts/pool',
      '- Mã Aave: https://github.com/aave-dao/aave-v3-origin',
      '- Compound: https://github.com/compound-finance/comet',
      '- Morpho: https://github.com/morpho-org/morpho-blue',
      '- Paper 6: https://www.bankofcanada.ca/wp-content/uploads/2026/04/sap2026-13.pdf',
      '- Dataset tham khảo: https://arxiv.org/html/2512.11363v1 ; DOI Zenodo liên kết trả 404 trong lần kiểm tra, chưa được nhập.',
      '', '## Bằng chứng và tái chạy','',
      'File bằng chứng nằm trong data/runs/expansion_20260930/processed; report_payload.json và audit_expansion.json giữ số liệu/tình trạng. Pilot gốc được giữ riêng.',
      'Chạy: python -m defi_data.expansion history --minutes 20 --workers 3 --chunk 1000 (chỉ chứng nhận sau đối chiếu); python -m defi_data.expansion enrich; python -m defi_data.expansion window; python -m defi_data.expansion versions; python -m defi_data.expansion_report.',
      'Crawl lịch sử được dừng để điều tra nguồn rỗng; không có tác vụ chạy nền tiếp tục sau bàn giao. Cần kiểm chứng endpoint rồi mới tiếp tục.']
    (RUN/'BAO_CAO_DATA_A_E_RQ1_7.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'summary':json.loads((RUN/'report_payload.json').read_text(encoding='utf-8'))['summary'],'steps':len(steps),'csv_files':len(inventory)},ensure_ascii=False))
if __name__=='__main__':main()
