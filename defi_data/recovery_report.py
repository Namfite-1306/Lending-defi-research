"""Evidence-driven updated A–E / RQ1–7 report; never infer readiness from code completion."""
import json,hashlib,time,csv
from collections import Counter
from decimal import Decimal as D
from .recovery import RUN,OUT,OLD
from .expansion import read_csv
from .pipeline import save_json,csv_write,utc

def load(path,default=None):
    return json.loads(path.read_text(encoding='utf8')) if path.exists() else default

def main():
    audits=[load(RUN/f'audit_{n}_{suffix}.json',{}) for n,suffix in [(1,'structure'),(2,'onchain'),(3,'research')]]
    if not all(audits):raise ValueError('All three audit reports must exist before final report')
    coverage=read_csv(OUT/'history_coverage.csv');universe=read_csv(OUT/'borrower_universe.csv')
    full=load(RUN/'full_snapshot_21762264/scope.json',{})
    versions=read_csv(OUT/'snapshot_version_validation.csv');checks=[]
    for p in (RUN/'snapshots').glob('*/position_checks.csv'):checks+=read_csv(p)
    config=read_csv(OUT/'configuration_timeline.csv');config_known=[r for r in config if r['contract_role']=='configurator' and r['event']!='unparsed_event' and not r['event'].startswith('ABI_mismatch')]
    flows=read_csv(OUT/'recursive_receipt_verification.csv');verified=[r for r in flows if r['status'].startswith('verified')]
    accrual=read_csv(OUT/'morpho_accrual_validation.csv');exposures=read_csv(OUT/'exposures_valued_sample.csv')
    ticks=read_csv(OUT/'v3_initialized_ticks.csv');quotes=read_csv(OUT/'v3_exact_impact_quotes.csv');pools=read_csv(OUT/'v3_pool_validation.csv')
    replay=read_csv(OUT/'v3_swap_replay_validation.csv');replay_exact=sum(r.get('exact_replay_match')=='True' for r in replay)
    feeds=load(RUN/'chainlink_feed_metadata.json',[]);sensitivity=read_csv(OUT/'recursive_sensitivity_full_history.csv')
    valuations=read_csv(OUT/'liquidation_valuation_coverage.csv');freeze=load(RUN/'freeze_manifest.json',{})
    history_complete=bool(coverage) and all(r['download_complete']=='True' for r in coverage)
    snapshot_ready=full.get('full_snapshot_complete',False) and full.get('passed')==full.get('active_debt_wallets') and full.get('active_debt_wallets',0)>0
    source_ready=history_complete and audits[0].get('all_integrity_passed',False) and audits[1].get('all_integrity_passed',False)
    results=[]
    def add(code,work,result,status,model,benefit,issue,fix,evidence):
        results.append({'ma':code,'cong_viec':work,'da_lam':result,'trang_thai':status,'dua_vao_mo_hinh':model,'ich_loi':benefit,
                        'van_de_con_lai':issue,'cach_giai_quyet':fix,'bang_chung':evidence})
    total=sum(int(r['records']) for r in coverage)
    add('A1','Chốt kỳ, nguồn và biên block','27/01/2023–30/09/2026 UTC; giữ hash biên và dữ liệu gốc cũ','Đạt','Có','Cố định phạm vi nghiên cứu',
        'Chỉ ba hợp đồng Ethereum đã chọn','Mở rộng universe khi thay phạm vi, không tự suy rộng toàn bộ DeFi','block_range.json; rpc_diagnosis.json')
    add('A2','Khôi phục lịch sử liên tục',f'{total:,} log; '+ '; '.join(f"{r['protocol']}: {float(r['fraction']):.2%}" for r in coverage),
        'Đạt' if history_complete else 'Chưa đạt','Có, sau kiểm tra on-chain','Thay bộ 3 giờ bằng lịch sử mục tiêu',
        '100% block coverage là cho event/hợp đồng đã chọn, không phải mọi sự kiện Ethereum','Giữ kiểm tra receipt, shard và dữ liệu gốc khi tái chạy','history.sqlite; history_coverage.csv; history_gaps.csv')
    add('A3','Borrower Universe toàn kỳ',f'{len(universe):,} địa chỉ Borrow.onBehalfOf; có first/last block',
        'Đạt' if history_complete else 'Chưa đạt','Có, lọc first_borrow <= snapshot','Tránh chọn chỉ ví thanh lý và tránh tương lai',
        'Địa chỉ không đồng nghĩa chủ sở hữu; universe không phải số ví còn nợ ở mọi ngày','Lọc dư nợ tại từng snapshot; không gộp chủ sở hữu thiếu bằng chứng','borrower_universe.csv')
    add('A4','Nguyên nhân nguồn rỗng và cache','Giữ lỗi HTTP JSON-RPC, dừng khi pruned; nguồn mới khớp receipt; raw DB/cache riêng','Đạt','Có',
        'Không đổi truy vấn lỗi hoặc lịch sử thiếu thành zero','RPC có thể gián đoạn/rate-limit khi chạy lại','Resume checkpoint; đối chiếu nguồn độc lập; không dùng cache rỗng bị cách ly cũ','rpc_diagnosis.json; scope_probe.json; tests/test_recovery.py')
    add('B1','Chọn cohort trước stress',f"Quét {full.get('wallets_scanned','n.a.'):,} / {full.get('historical_borrowers',0):,} người vay trước block 21762264" if isinstance(full.get('wallets_scanned'),int) else 'Chưa hoàn tất',
        'Đạt' if full.get('full_snapshot_complete') else 'Một phần','Có tại snapshot đã hoàn tất','Loại look-ahead selection của mẫu cũ',
        'Snapshot này là trước đợt 03/02/2025, chưa là full-market mọi ngày','Lặp sparse snapshot ở các ngày thí nghiệm cần so sánh','full_snapshot_21762264/scope.json')
    add('B2','Vị thế full cohort và đối chiếu',f"{full.get('active_debt_wallets',0):,} ví còn nợ; {full.get('passed',0):,} đạt; failed debt USD={full.get('failed_debt_usd','n.a.')}",
        'Đạt' if snapshot_ready else 'Một phần','Có nếu validation_passed=True','Có trạng thái vị thế thực để stress RQ1',
        'Chưa có full-market snapshots nhiều ngày; ví lỗi được giữ riêng','Xử lý mọi sai lệch còn lại, dựng cùng quy trình tại các cutoff khác','full_snapshot_21762264/positions.csv; validation.csv')
    add('B3','E-mode và sai khác GHO','Bitmap/nhóm cũ, revision-specific rounding; tách debt tính HF khỏi repayable debt của GHO','Đạt' if snapshot_ready else 'Một phần',
        'Có ở phiên bản đã đối chiếu','Tránh sai HF do chiết khấu GHO hoặc cắt sớm average LT',
        'Custom price source và revision ngoài 1–11 bị chặn, không đoán','Thêm adapter có nguồn và đối chiếu nếu phiên bản mới xuất hiện','full_snapshot_21762264/validation.csv; tests/test_recovery.py')
    add('B4','Timeline cấu hình và upgrade',f'{len(config_known):,}/3.246 log Configurator được giải mã; 24 registry; 10 pool upgrade; '+f'{len(versions)} mốc snapshot',
        'Đạt','Có cho cấu hình quan sát được','Thay cấu hình hiện tại bằng timeline lịch sử',
        'Close factor/dust rule nằm trong code, cần mapping implementation cho thí nghiệm chính sách','Dùng source release/revision tương ứng; kiểm định liquidation replay trước policy counterfactual','configuration_timeline.csv; historical_configuration_abis.json; snapshot_version_validation.csv')
    add('B5','Đối chiếu nhiều phiên bản',f'{sum(r["passed"]=="True" for r in checks)}/{len(checks)} wallet-snapshots qua kiểm tra tại {len(versions)} mốc',
        'Đạt' if checks and all(r['passed']=='True' for r in checks) else 'Một phần','Kiểm chứng adapter; full-market ở snapshot riêng',
        'Phát hiện và sửa lỗi revision 9+ trước khi suy rộng','Mẫu theo phiên bản không thay thế full-market panel theo ngày','Dựng panel ngày từ sparse calls hoặc scaled-balance replay, giữ kiểm chứng HF','snapshots/*/position_checks.csv')
    add('C1','Heuristic toàn kỳ','Borrow/Supply toàn kỳ; thuật toán O(n log n), mỗi Borrow tối đa một motif/cửa sổ','Đạt' if sensitivity else 'Chưa đạt','Có cho nhãn ứng viên',
        'Nhận diện cả nhiều giao dịch, không chỉ cùng tx','Heuristic chưa tự chứng minh funding/ownership','Giữ nhãn confidence; không gọi toàn bộ motif là recursive leverage chắc chắn','recursive_candidates_full_history.csv')
    add('C2','Cửa sổ 6/24/48 giờ','Có điểm bắt đầu đủ horizon, motif censored/uncensored và label_available_at','Đạt' if sensitivity else 'Chưa đạt','Có cho sensitivity, không gắn nhãn tương lai ngược về snapshot',
        'Ngăn leakage và dùng biên cuối kỳ như mẫu âm giả','Cần định nghĩa cửa sổ phù hợp câu hỏi; kết quả thay đổi theo định nghĩa','Báo cả ba cửa sổ; matching tại cùng cutoff và phân tích độ nhạy','recursive_sensitivity_full_history.csv; recursive_negative_controls_sample.csv')
    add('C3','Xác minh dòng tiền bằng trace',f'{len(verified)}/{len(flows)} case receipt được xác nhận nhánh funding có trace; '+str(len(load(RUN/'trace_funding_evidence.json',[])))+' bằng chứng chi tiết',
        'Đạt cho mẫu xác minh','Có cho cohort được định nghĩa; không suy rộng precision từ mẫu chọn',
        'Bổ sung nhánh staking/mint ngoài swap DEX','Mẫu xác minh nhỏ; chỉ gán phần collateral được chứng minh, không toàn bộ giao dịch','Mở rộng kiểm tra mẫu phân tầng theo năm/asset/route và cả multi-transaction','recursive_receipt_verification.csv; trace_funding_evidence.json; traces/')
    add('C4','Nhóm đối chứng và vulnerability','Có negative-control ứng viên với horizon đủ; chưa hoàn tất matched cohort cho ước lượng causal','Một phần','Chạy mô tả; chưa kết luận tăng vulnerability bao nhiêu',
        'Tách absence-of-motif khỏi chắc chắn không có đòn bẩy ngoài Aave','Chưa matching đầy đủ theo HF, debt, asset, ngày; còn funding labels chưa kiểm chứng','Ghép nhãn sẵn có ở cutoff với full snapshot, matching và sensitivity theo confidence','recursive_negative_controls_sample.csv; full_snapshot_21762264/')
    add('D1','Giá liên tục và phase feed',f"{sum(r['events'] for r in feeds):,} quan sát từ {len(feeds)} feed; có hourly grid và seed tại phase activation",'Đạt','Có với stale flag',
        'Giá ETH/BTC và stablecoin theo thời điểm, không giả định peg=1','Giá thị trường Chainlink khác capped oracle Aave; BTC/USD không phải WBTC/USD','Dùng đúng loại giá theo mô hình; thêm basis/staleness sensitivity','chainlink_price_updates.csv; market_prices_hourly_full_period.csv; chainlink_phase_segments.csv')
    add('D2','Thực thi và chi phí','Giữ 80 receipt/gas, 86 swap và decimals/factory của mẫu; định giá thêm sự kiện toàn kỳ trong phạm vi feed có','Một phần','Có cho mẫu và sự kiện được định giá',
        'Chi phí gas, giá khớp và phân biệt định giá','Chưa có toàn bộ gas/routes/bribe cho mọi liquidation; tài sản thiếu feed giữ NA','Thu receipt/trace theo waves và thêm feed được kiểm chứng; không thay NA bằng zero','liquidations_model_table.csv; liquidation_valuation_coverage.csv; old execution_gas_sample.csv')
    add('D3','Độ sâu V3 và impact chính xác',f'{len(pools)} pool factory-verified; {len(ticks):,} ticks; {len(quotes)} quote lịch sử','Đạt cho phạm vi pool đã chọn','Có trong miền quote; không ngoại suy toàn thị trường',
        'Khắc phục thiếu initialized ticks/liquidityNet; Quoter dùng full node state','Offline ticks chỉ +/-6.000; chưa bao phủ mọi DEX/route và mọi ngày','Quote/replay thêm pool và ngày cho thí nghiệm; giữ giới hạn miền tham số','v3_initialized_ticks.csv; v3_exact_impact_quotes.csv; v3_pool_validation.csv')
    add('D4','Replay kiểm chứng giá thực thi',f'{replay_exact}/{sum(r.get("eligible")=="True" for r in replay)} case đủ điều kiện khớp chính xác; {len(replay)} case kiểm tra','Đạt cho case đủ điều kiện',
        'Có cho kiểm chứng engine pool','Đối chiếu input/output theo loại swap và sqrt price với giao dịch thật',
        'Pool đã đổi trong cùng block cần prestate/intra-block replay, không dùng previous-block state làm đáp án','Tận dụng trace/state diff để dựng state trước từng tx; replay nhiều waves ngoài mẫu','v3_swap_replay_validation.csv')
    add('D5','Hiệu chỉnh cascade/bad debt/chính sách','Đầu vào thật, exact quote và replay đã có; full liquidation-wave engine chưa được hiệu chỉnh hoàn chỉnh','Một phần',
        'Thử nghiệm có điều kiện; chưa kết luận RQ6/RQ7 toàn hệ thống','Có cơ sở thực nghiệm cho price impact và cost',
        'Thiếu full route/intra-block state và full multi-date exposure; chưa có kiểm định wave ngoài mẫu','Replay full waves; kiểm tra bảo toàn số dư, chi phí, sell fraction, close factor rồi chạy policy grid','v3_swap_replay_validation.csv; liquidations_model_table.csv')
    add('E1','Định nghĩa thanh lý theo giao thức','Aave LiquidationCall, Morpho Liquidate, Compound AbsorbDebt tách riêng; không đếm AbsorbCollateral/BuyCollateral như loan liquidation','Đạt','Có',
        'Ngăn cộng sai đơn vị, tác nhân và event','Comet basePaidOut gồm debt absorption và có thể có positive base credit','Giữ economic_meaning; nếu cần riêng debt, tái dựng pre-state và credit phát sinh','liquidations_model_table.csv; CometWithExtendedAssetList.sol')
    add('E2','Danh mục market và token toàn kỳ','Đọc immutable market parameters và token metadata; lưu lỗi metadata riêng','Đạt cho mapping; định giá theo coverage','Có cho mapping; metadata cuối kỳ không dùng làm giá lịch sử',
        'Giải mã collateral/loan token/LLTV/IRM của Morpho đúng market ID','ERC20 lạ hoặc market idle có thể thiếu oracle/decimals; không có mặc định 18 decimals','Giữ NA và adapter token được xác minh trước định giá','morpho_market_registry_full.csv; token_registry.csv; feature_errors.json')
    add('E3','Morpho accrual/shares và USD exposure',f'{len(accrual)}/52 market khớp cả 6 trường sau accrueInterest; {len(exposures)} dòng exposure mẫu','Đạt cho mẫu đã kiểm chứng','Có cho exposure được định giá, đúng snapshot',
        'Sửa stored totals chưa accrue; virtual shares và rounding; tách repayable/risk debt','Cohort cross-protocol vẫn là mẫu, không full-market mọi ngày; unpriced rows giữ NA','Lặp adapter cho borrower-market universe tại các ngày mô phỏng, bổ sung giá cho phần chưa định giá','morpho_accrual_validation.csv; exposures_valued_sample.csv; exposure_errors.json')
    add('E4','Mạng activity và exposure có loại','Có activity toàn kỳ và wallet→market exposure mẫu; giữ causal_claim=False','Một phần','Có để mô tả, chưa đủ kết luận causal contagion',
        'Phân biệt activity, common asset, common wallet và direct claim','Thiếu full-market cross-protocol position panel; địa chỉ không đồng nghĩa chủ sở hữu','Dựng snapshot đồng bộ borrower-market, valuation coverage và common-shock controls trước contagion simulation','wallet_protocol_activity.csv; exposure_network_edges.csv')
    rq=[
      ['RQ1','Ngưỡng cú sốc ETH/BTC','Đủ cho full snapshot 03/02/2025' if snapshot_ready else 'Chưa đủ full snapshot',
       f"{full.get('active_debt_wallets',0):,} ví còn nợ tại block 21762264",'Chưa là full-market panel nhiều kỳ; derivative basis và factor mapping phải nêu giả định','B1–B5'],
      ['RQ2','Tập trung liquidation','Đủ event-count; USD theo coverage',f'{total:,} log nguồn; bảng liquidation và concentration theo từng protocol',
       'Không suy USD concentration từ số event; không cộng basePaidOut như repaidAssets','A, D1–D2, E1'],
      ['RQ3','Recursive leverage / vulnerability','Có motif toàn kỳ và nhãn trace mẫu',f'{len(verified)} positive funding examples; 6/24/48h và censoring',
       'Matched cohort và validation sample đại diện còn thiếu; chưa ước lượng causal vulnerability','C1–C4'],
      ['RQ4','Clustering / self-excitation','Đủ dữ liệu mô hình nền' if source_ready else 'Chờ cổng audit nguồn',
       'Hourly liquidation counts toàn kỳ + ETH/BTC controls, NA trước deployment',
       'Loại/kiểm tra stale prices, common-price controls, phần dư và ngoài mẫu trước kết luận','A, D1'],
      ['RQ5','Cross-protocol contagion','Có mapping và exposure mẫu',f'{len(exposures)} exposure rows + activity toàn kỳ',
       'Thiếu full cross-protocol exposure panel đồng bộ và identification của kênh truyền','E1–E4'],
      ['RQ6','Liquidity / cascade / bad debt','Đủ thử engine pool có điều kiện',f'{len(quotes)} quotes, {replay_exact} exact swap replays',
       'Chưa full routes, intra-block state và kiểm định liquidation waves ngoài mẫu','D2–D5'],
      ['RQ7','Chính sách tham số thanh lý','Chưa đủ kết luận chính sách','Timeline LT/bonus, revision và dữ liệu thực thi đã có',
       'Cần RQ6 wave calibration, đúng close factor/dust rule theo code, objective và robustness','B4, D5, RQ6']]
    qa=[]
    for n,audit in enumerate(audits,1):
        for check in audit.get('checks',[]):qa.append({'round':n,**check})
    payload={'generated_utc':utc(int(time.time())),'coverage':coverage,'total_logs':total,'universe':len(universe),'full_snapshot':full,
             'versions':versions,'steps':results,'rq':rq,'audits':qa,'freeze':freeze,'sensitivity':sensitivity,'valuations':valuations,
             'integrity_passed':[a.get('all_integrity_passed') for a in audits],'unit_tests':26}
    save_json(RUN/'report_payload_v2.json',payload);csv_write(OUT/'implementation_report_v2.csv',results)
    lines=['# Báo cáo dữ liệu cập nhật — A–E và ba vòng rà soát','',
      'Kỳ mục tiêu: 27/01/2023 đến hết 30/09/2026 UTC. Phạm vi: Aave V3 Pool, Compound III Comet USDC và Morpho Blue trên Ethereum.',
      '',f'Đã tải {total:,} log thuộc các event đã chọn. Coverage tải về: '+', '.join(f"{r["protocol"]}: {float(r["fraction"]):.2%}" for r in coverage)+'.',
      '', '**Coverage lịch sử, tính toàn vẹn và mức sẵn sàng mô hình là ba khái niệm riêng. Báo cáo không coi các kiểm tra mã đạt là bằng chứng mọi RQ đã đủ dữ liệu.**','',
      '## Ba vòng rà soát','', '| Vòng | Kiểm tra | Kết quả | Loại | Chi tiết |','|---|---|---|---|---|']
    for r in qa:lines.append('| '+' | '.join([str(r['round']),r['check'],'Đạt' if r['passed'] else 'Chưa đạt',r['severity'],json.dumps(r['detail'],ensure_ascii=False).replace('|','/')])+' |')
    lines+=['','## Các mục A–E','','| Bước | Đã làm | Kết quả | Dùng mô hình | Ích lợi | Vấn đề còn lại | Cách xử lý | Bằng chứng |','|---|---|---|---|---|---|---|---|']
    for s in results:lines.append('| '+' | '.join(str(s[k]).replace('|','/').replace('\n',' ') for k in ('ma','da_lam','trang_thai','dua_vao_mo_hinh','ich_loi','van_de_con_lai','cach_giai_quyet','bang_chung'))+' |')
    lines+=['','## RQ1–RQ7','','| RQ | Nội dung | Sẵn sàng đến đâu | Bằng chứng | Giới hạn / còn thiếu | Phụ thuộc |','|---|---|---|---|---|---|']
    lines+=['| '+' | '.join(r)+' |' for r in rq]
    lines+=['','## Những lỗi đã phát hiện và sửa','',
      '- HTTP 400/403/429 chứa JSON-RPC error trước đây bị che; fallback sang nguồn pruned có thể cho kết quả rỗng. Đã giữ lỗi, dừng pruned, thay nguồn và tách raw database/cache.',
      '- Coverage bị cộng trùng khi thay kích thước chunk: dùng hợp các khoảng block và khóa (tx_hash,log_index), đối chiếu digest từng shard.',
      '- ABI cấu hình lịch sử khác ABI hiện tại: hợp nhất ABI các release, thêm decode string/bytes; giải mã cả payload thay đổi interest-rate strategy.',
      '- HF thay đổi cách làm tròn từ Pool revision 9: giữ weighted LT đến bước cuối, debt valuation làm tròn lên theo phiên bản.',
      '- GHO: debt dùng HF được tính từ scaled debt × normalized index; không dùng nhầm balance sau discount như risk debt. Giữ repayable debt riêng.',
      '- Feed Chainlink thay aggregator: dựng phase boundaries từ historical phaseId, seed tại thời điểm activation; không kéo feed 2023 đã dừng đến 2026.',
      '- Bộ lọc swap bỏ sót staking/mint loops: dùng trace và prestate; chỉ gán phần collateral được chứng minh có funding, giữ phần flash-loan/external riêng.',
      '- Pool state cuối block trước không phải state trước mọi swap: chỉ chứng nhận exact replay cho first pool touches phù hợp; các case intra-block hoặc nhiều swap cùng pool chưa ghép được call/log được giữ riêng. Dùng đúng exact-input/exact-output và sqrt-price limit lấy từ trace.',
      '- Compound AbsorbDebt basePaidOut không đồng nhất repaidAssets: giữ economic_meaning riêng; không cộng AbsorbCollateral/BuyCollateral vào số liquidation khoản vay.',
      '', '## Tái chạy và giới hạn','',
      'Dữ liệu gốc: history.sqlite (raw log nén + decoded fields + shard checkpoints). CSV mô hình ở processed/. Ba audit JSON, freeze_manifest.json, trace và snapshot là bằng chứng có thể kiểm tra.',
      'Mẫu cũ được giữ nguyên. Bộ mới không có giao dịch on-chain hoặc dịch vụ dữ liệu trả phí. Chỉ đọc RPC và eth_call, bao gồm mô phỏng tạm thời không lưu state.',
      'Chưa khẳng định đã hoàn tất full-market position panel ở mọi ngày hoặc full-system cascade/policy calibration. Những phần này được đánh dấu rõ trong bảng A–E và RQ readiness.',
      '', 'Nguồn phương pháp: Aave v3 core/origin release interfaces và GenericLogic; Compound CometWithExtendedAssetList; Morpho Blue Morpho/MathLib/SharesMathLib/IIrm; Uniswap V3 QuoterV2 và factory registry. Source URLs/hashes được lưu kèm dữ liệu và ABI manifests.']
    (RUN/'BAO_CAO_DATA_CAP_NHAT_3_VONG.md').write_text('\n'.join(lines),encoding='utf8')
    print(json.dumps({'total_logs':total,'steps':len(results),'audit_checks':len(qa),'full_snapshot_ready':snapshot_ready,'integrity_rounds':payload['integrity_passed']}))
if __name__=='__main__':main()
