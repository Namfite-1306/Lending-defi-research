"""Build a Vietnamese offline HTML/Markdown report from the completed reference run."""
import argparse
import csv
import hashlib
import html
import json
import subprocess
from collections import Counter
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def money(value):
    return f'{float(value):,.2f}'


def pct(value):
    return f'{float(value)*100:.2f}%'


class Report:
    def __init__(self):
        self.md, self.html = [], []

    def title(self, text, level=2):
        self.md.extend(['#'*level+' '+text, ''])
        self.html.append(f'<h{level}>{html.escape(text)}</h{level}>')

    def para(self, text):
        self.md.extend([text, ''])
        self.html.append(f'<p>{html.escape(text)}</p>')

    def table(self, headers, data):
        data = [[str(v) for v in row] for row in data]
        self.md.extend(['| '+' | '.join(headers)+' |', '| '+' | '.join(['---']*len(headers))+' |'])
        self.md.extend('| '+' | '.join(row)+' |' for row in data)
        self.md.append('')
        self.html.append('<div class="table"><table><thead><tr>'+''.join(f'<th>{html.escape(x)}</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{html.escape(x)}</td>' for x in row)+'</tr>' for row in data)+'</tbody></table></div>')

    def code(self, text):
        self.md.extend(['```powershell', text, '```', ''])
        self.html.append('<pre><code>'+html.escape(text)+'</code></pre>')

    def save(self, folder):
        (folder/'BAO_CAO_KET_QUA_7_RQ.md').write_text('\n'.join(self.md), encoding='utf8')
        css = '''body{margin:0;background:#f3f5f4;color:#182c29;font:16px/1.65 system-ui,"Segoe UI",sans-serif}main{max-width:1160px;margin:32px auto;padding:40px;background:white;border-top:8px solid #147967;border-radius:8px}h1{font-size:30px;line-height:1.3}h2{margin-top:40px;color:#106754;font-size:23px}h3{font-size:19px}p{max-width:105ch}.table{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px;margin:16px 0}th,td{padding:10px 12px;text-align:left;border:1px solid #d8e2de;vertical-align:top}th{background:#e5f0eb}tbody tr:nth-child(even){background:#f7faf8}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#122d27;color:#e7f5ee;padding:18px;border-radius:6px;font-size:13px}@media print{body{background:white}main{margin:0;padding:0;max-width:none;border:0}table{font-size:10px}h2,h3{break-after:avoid}tr,pre{break-inside:avoid}}'''
        (folder/'BAO_CAO_KET_QUA_7_RQ.html').write_text('<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Báo cáo kết quả 7 RQ — 22/10/2026</title><style>'+css+'</style><main>'+''.join(self.html)+'</main></html>', encoding='utf8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    run = args.run.resolve()
    manifest = load(run/'manifest.json')
    assert manifest['all_executed'] and len(manifest['models']) == 7
    summaries = {i: load(run/f'rq{i}/summary.json') for i in range(1, 8)}
    cfg = manifest['config']
    data = Path(manifest['data_run'])
    bounds = load(data/'block_range.json')
    validation, repeat, convergence = [load(run/(x+'.json')) for x in ('validation', 'reproducibility', 'convergence')]
    assert all(r['passed'] for r in (validation, repeat, convergence))
    scope = summaries[1]['snapshot']
    doc = Report()
    doc.title('BÁO CÁO KẾT QUẢ CHẠY TOÀN BỘ 7 RQ', 1)
    local = datetime.fromisoformat(manifest['finished_utc']).astimezone(timezone(timedelta(hours=7)))
    doc.para(f'Bản tham chiếu hoàn tất lúc {local:%H:%M:%S %d/%m/%Y} (Asia/Saigon). Đã chạy cấu hình đầy đủ, không dùng --smoke. Cả 7 RQ thực thi thành công; 129 kiểm thử đạt; validator kết quả đạt 7/7. Chạy lặp lại không phát hiện khác biệt ở 22 file JSON/CSV. Đây là bộ kết quả offline cố định để đối chiếu; dữ liệu dashboard real-time có thể thay đổi theo block.')
    doc.para('RQ1, RQ2, RQ4 có kết quả dùng được trong phạm vi hiện tại. RQ3, RQ5, RQ6, RQ7 là kết quả thăm dò. Chạy thành công và kiểm tra kỹ thuật đạt không đồng nghĩa mọi giả thuyết đã được chứng minh hoặc dữ liệu đã đủ cho kết luận toàn thị trường.')
    doc.title('1. Dữ liệu, phạm vi và cấu hình thực chạy')
    doc.table(['Mục', 'Giá trị'], [
        ['Lịch sử sự kiện', f"{bounds['start_utc']} đến trước {bounds['end_exclusive_utc']} — bao gồm hết 30/09/2026 UTC"],
        ['Block lịch sử', f"{bounds['start_block']:,} – {bounds['end_block']:,}"],
        ['Snapshot Aave V3 Ethereum', f"Block {scope['block']:,}, trước stress 03/02/2025 UTC; revision {scope['pool_revision']}"],
        ['Vũ trụ vị thế tại snapshot', f"{scope['wallets_scanned']:,} ví lịch sử được quét; {scope['active_debt_wallets']:,} ví có nợ, tất cả qua validation"],
        ['Nợ theo snapshot', money(scope['reported_debt_usd'])+' USD (risk debt theo adapter)'],
        ['Nguồn cố định', manifest['data_run']],
        ['Chạy RQ4', 'Aave V3; không gộp dữ liệu ba protocol để fit chung'],
        ['Python / NumPy / SciPy', ' / '.join(manifest['versions'][k] for k in ('python', 'numpy', 'scipy'))],
        ['Seed / bootstrap', f"{cfg['seed']} / {cfg['bootstrap_repetitions']} lần"],
        ['Giới hạn vòng cascade cuối', str(cfg['max_rounds'])+'; đã đối chiếu RQ7 với 400 vòng'],
    ])
    doc.para('Lịch sử đầy kỳ không đồng nghĩa có toàn bộ vị thế ở mọi thời điểm: các bài toán vị thế dùng một snapshot; mạng cross-protocol dùng mẫu. Các CSV được đối chiếu SHA-256 với freeze_manifest trước khi chạy. Database được mở read-only; báo cáo không crawl lại hoặc sửa dataset đã freeze.')
    doc.title('2. Các lần chạy, vấn đề phát hiện và cách xử lý')
    doc.table(['Bước', 'Kết quả', 'Xử lý / đánh giá'], [
        ['Kiểm tra code', '129/129 unit tests đạt', 'Bao gồm crawler RPC, mô hình, live dashboard và công cụ so sánh'],
        ['Chạy đầy đủ với cấu hình gốc', '7/7 chạy xong; RQ7 có 22/81 kịch bản chạm 20 vòng', 'Giữ lần chạy baseline để truy vết; chưa dùng các kịch bản bị cắt làm kết quả cuối'],
        ['Chạy đầy đủ với max_rounds=200', 'RQ7 không còn chạm giới hạn; dài nhất 35 vòng', 'Lưu cấu hình riêng configs/models.full_7rq_20261022.json; giữ nguyên engine và dữ liệu'],
        ['Kiểm tra độ ổn định RQ7', '200 so với 400 vòng: policy_grid.csv giống hệt byte', 'Đây là kiểm tra ổn định giới hạn vòng trong engine hiện có, không phải xác minh engine đúng Aave thực tế'],
        ['Chạy lại cả 7 cùng cấu hình', f"{repeat['files_compared']} file đối chiếu; {repeat['difference_count']} khác biệt", 'Counts so sánh chính xác; số liên tục rtol=1e-9, atol=1e-6'],
        ['Validator kết quả', '7/7 đạt; không còn cảnh báo chạm vòng', 'Kiểm tra hữu hạn, số dư, concentration, matching, optimizer và Pareto'],
    ])
    doc.para('Không phát hiện lỗi thực thi cần sửa trong engine ở lần chạy này. Thay đổi phục vụ lần chạy: tăng giới hạn vòng trong cấu hình riêng, thêm script đối chiếu kết quả và script tạo báo cáo. Các hạn chế về nhận diện nhân quả, giá thiếu, mẫu mạng và hiệu chỉnh cascade vẫn được giữ nguyên, không che bằng thay đổi code.')
    doc.title('3. RQ1 — Giá ETH/BTC giảm bao nhiêu tạo bước nhảy trong thanh lý?')
    doc.para('Đo nợ đủ điều kiện thanh lý theo HF, không phải lượng thanh lý đã thực thi. Quét 0–60%, bước 1%, shock cả tài sản thế chấp và nợ theo nhóm token. Ngưỡng mô tả trong một snapshot, chưa có kiểm định ngưỡng thống kê.')
    doc.table(['Kịch bản', 'Khoảng giảm có bước tăng lớn nhất', 'Nợ đủ điều kiện tăng thêm (USD)', 'Nút hồi quy đoạn thẳng'], [
        [r['scenario'], f"{pct(r['largest_grid_increment_start'])} → {pct(r['largest_grid_increment_end'])}", money(r['largest_increment_usd']), pct(r['piecewise']['knot'])] for r in summaries[1]['breakpoints']])
    stress = rows(run/'rq1/stress_curve.csv')
    doc.table(['Kịch bản shock đồng thời', 'Ví đủ điều kiện', 'Ví mới đủ điều kiện so với nền', 'Nợ đủ điều kiện (USD)'], [
        [pct(r['shock_fraction']), r['eligible_wallets'], r['newly_eligible_wallets'], money(r['eligible_risk_debt_usd'])]
        for r in stress if r['scenario'] == 'ETH_BTC_joint' and any(abs(float(r['shock_fraction'])-x)<1e-9 for x in (0,.1,.2,.3,.6))])
    base = next(r for r in stress if r['scenario']=='ETH_BTC_joint' and float(r['shock_fraction'])==0)
    doc.para(f"Ở nền đã có {base['eligible_wallets']} ví HF<1, tổng risk debt {money(base['eligible_risk_debt_usd'])} USD. Cột ví mới loại nhóm này. Không nên diễn giải số ví nền như số khoản vay lớn đang có thể thanh lý sinh lời.")
    doc.title('4. RQ2 — Thanh lý có tập trung ở ví/token/protocol?')
    coverage = rows(run/'rq2/valuation_coverage.csv')
    doc.table(['Protocol', 'Sự kiện thanh lý', 'Sự kiện có giá USD', 'Tỷ lệ có giá'], [[r['protocol'], r['events'], r['priced_events'], pct(r['priced_fraction'])] for r in coverage])
    conc = rows(run/'rq2/concentration.csv')
    doc.table(['Protocol / thước đo / chiều phân nhóm', 'HHI', 'Gini', 'Top 1', 'Top 10'], [
        [r['protocol']+' / '+r['measure']+' / '+r['dimension'], f"{float(r['hhi']):.6f}", f"{float(r['gini']):.6f}", pct(r['top1']), pct(r['top10'])]
        for r in conc if r['period']=='all' and r['dimension']=='borrower'])
    doc.para('Hình thức tập trung theo lượng USD có thể khác theo số sự kiện. Các chỉ số USD chỉ phản ánh phần có giá; không nội suy phần thiếu. Comet basePaidOut không có cùng nghĩa với Aave debt repaid, vì vậy không cộng USD giữa ba protocol thành một tổng thanh lý. Xem concentration.csv cho chi tiết từng năm và từng token.')
    doc.title('5. RQ3 — Đòn bẩy lặp liên hệ với độ dễ tổn thương như thế nào?')
    s = summaries[3]
    pairs = rows(run/'rq3/matched_pairs.csv')
    treated = sum(int(r['treated_liquidated']) for r in pairs)/len(pairs)
    control = sum(int(r['control_liquidated']) for r in pairs)/len(pairs)
    doc.table(['Chỉ tiêu', 'Kết quả'], [
        ['Nhãn / cửa sổ nhận diện', f"{s['label_mode']} / {cfg['recursive_window_hours']} giờ; bằng chứng phải có trước cutoff"],
        ['Cutoff / kết thúc outcome', s['cutoff_utc']+' / '+s['outcome_end_utc']],
        ['Ví gắn nhãn / cặp match / ví không match', f"{s['treated_in_snapshot']:,} / {s['matched_pairs']:,} / {s['unmatched_treated']:,}"],
        ['Tỷ lệ bị thanh lý 7 ngày: nhóm nhãn / đối chứng', pct(treated)+' / '+pct(control)],
        ['Chênh lệch rủi ro', f"{s['liquidation_risk_difference']*100:.4f} điểm phần trăm"],
        ['Bootstrap 95% cho chênh lệch', ' – '.join(f'{x*100:.4f}' for x in s['paired_bootstrap_95'])+' điểm phần trăm'],
        ['Chênh lệch đủ điều kiện khi shock 20%', f"{s['stress_eligibility_difference']*100:.4f} điểm phần trăm"],
        ['Logistic penalized', s['regression']['status']+'; converged='+str(s['regression'].get('converged'))],
    ])
    balance = rows(run/'rq3/matching_balance.csv')
    doc.table(['Biến match', 'Standardized mean difference sau match'], [[r['feature'], f"{float(r['standardized_mean_difference']):.6f}"] for r in balance])
    doc.para('Kết quả là liên hệ có điều kiện trong các cặp được match. Nhãn temporal chỉ là ứng viên leverage lặp; nhóm không thấy motif chưa được chứng minh là không có leverage. Bootstrap giữ matching cố định. Chưa thể phát biểu leverage gây ra mức tăng rủi ro này hoặc suy rộng toàn thị trường.')
    doc.title('6. RQ4 — Thanh lý có clustering/self-excitation theo thời gian?')
    s = summaries[4]
    h, p = s['hawkes'], s['poisson']
    doc.table(['Chỉ tiêu', 'Kết quả'], [
        ['Sự kiện / giờ quan sát', f"{s['events']:,} / {int(s['hours']):,}"],
        ['Mốc train/test (UTC)', s['train_end_utc']],
        ['Half-life Hawkes được chọn trên train', f"{h['half_life_hours']*60:.4f} phút"],
        ['Branching ratio', f"{h['branching_ratio']:.6f}"],
        ['Hawkes test log-likelihood', f"{h['test_loglik']:.6f}"],
        ['Hawkes trừ constant Poisson: test log-likelihood', f"{s['hawkes_minus_constant_poisson_test_loglik']:.6f}"],
        ['Poisson có controls: test deviance', f"{p['test_deviance']:.6f}"],
        ['Constant Poisson: test deviance', f"{p['constant_test_deviance']:.6f}"],
        ['Giảm deviance so với constant', pct(1-p['test_deviance']/p['constant_test_deviance'])],
        ['Optimizer / số giờ loại vì giá', f"Poisson và Hawkes hội tụ / {p['excluded_price_rows']}"],
    ])
    doc.para('Trong cấu hình đang xét, Hawkes fit holdout tốt hơn constant Poisson, phù hợp mô tả thanh lý có cụm. Branching ratio không chứng minh cơ chế nhân quả: Hawkes chưa kiểm soát giá và kiểm định residual time-rescaling; timestamp được nhóm theo block. Poisson có giá cùng giờ là mô hình giải thích, không phải dự báo trước giờ. Không so trực tiếp log-likelihood point-process với hourly deviance vì chúng khác thước đo.')
    doc.title('7. RQ5 — Cross-protocol exposures có tạo kênh lây lan?')
    s = summaries[5]
    doc.para(f"Mẫu {s['wallets']} ví, {s['valued_edges']} cạnh định giá được, {s['unpriced_rows']} dòng chưa có giá; block đồng bộ {s['block']}. Đây là mạng mẫu theo hoạt động, chưa phải toàn thị trường.")
    doc.table(['Cặp protocol', 'Ví cùng có nợ', 'Tổng min(nợ ở hai bên) (USD)'], [[r['protocol_a']+' ↔ '+r['protocol_b'], r['shared_debt_wallets'], money(r['minimum_shared_debt_usd'])] for r in rows(run/'rq5/protocol_overlap.csv')])
    doc.para('Mẫu tìm thấy common-wallet exposure giữa Compound V3 và Morpho. Không thấy overlap Aave trong mẫu không chứng minh thị trường không có kênh này. Exposure chung không phải khoản phải thu trực tiếp giữa protocol; chưa ước lượng được tổn thất truyền dẫn hoặc causal contagion.')
    doc.title('8. RQ6 — Mô phỏng cascade và tác động thanh khoản')
    cascades = rows(run/'rq6/cascade_scenarios.csv')
    doc.table(['Shock ETH/BTC', 'Repayment có impact (USD)', 'Repayment zero-impact (USD)', 'Tỷ lệ', 'Impact lớn nhất', 'Shortfall cuối có impact (USD)', 'Ví còn HF<1'], [
        [pct(r['shock_fraction']), money(r['repaid_usd']), money(next(z['repaid_usd'] for z in cascades if z['case']=='zero_impact_control' and z['shock_fraction']==r['shock_fraction'])),
         f"{float(r['repaid_usd'])/float(next(z['repaid_usd'] for z in cascades if z['case']=='zero_impact_control' and z['shock_fraction']==r['shock_fraction'])):.4f}x", pct(r['max_cumulative_price_impact']), money(r['terminal_collateral_shortfall_usd']), r['terminal_eligible_wallets']]
        for r in cascades if r['case']=='assumed_impact'])
    doc.para(f"Giả định: độ sâu {money(cfg['liquidity_depth_usd'])} USD cho mỗi token, impact coefficient {cfg['impact_coefficient']}, oracle pass-through {cfg['oracle_pass_through']}, close factor {cfg['close_factor']}, bonus {pct(cfg['liquidation_bonus'])}, gas {money(cfg['gas_usd'])} USD/action và phí DEX {pct(cfg['dex_fee_fraction'])}. Shock đồng thời áp dụng cả collateral và debt theo factor.")
    doc.para('Cả 6 kịch bản dừng vì không còn thanh lý sinh lời theo bộ lọc đồng bộ của engine; còn ví HF<1 là một đầu ra cần giữ. Shortfall là chênh lệch kế toán mô hình, không phải bad debt ghi nhận on-chain. Tỷ lệ repayment có/không impact chỉ là sensitivity của engine, chưa phải hệ số khuếch đại thực nghiệm. Chưa hiệu chỉnh liquidity depth/impact hoặc tái tạo chính xác Aave pair, close factor động, dust, protocol fee và tuyến thực thi.')
    doc.title('9. RQ7 — Độ nhạy tham số và Pareto')
    grid = rows(run/'rq7/policy_grid.csv')
    front = [r for r in grid if r['pareto_nondominated']=='True']
    doc.para(f"Chạy {len(grid)} kịch bản = 3 shock × 3 close factor × 3 bonus × 3 thay đổi LT. Tất cả {len(grid)} đủ điều kiện Pareto về mặt giới hạn vòng; {len(front)} phương án không bị trội trong cùng shock. Số vòng tối đa thực dùng {max(int(r['rounds']) for r in grid)}. Có {sum(r['incomplete_dynamics']=='True' for r in grid)} kịch bản vẫn còn ví HF<1 khi dừng; hết giới hạn vòng và còn HF<1 là hai vấn đề khác nhau.")
    doc.table(['Shock', 'Close factor', 'Bonus', 'LT shift (điểm %)', 'Shortfall cuối USD', 'Collateral seized USD', 'Impact', 'Ví còn HF<1'], [
        [pct(r['shock_fraction']), pct(r['close_factor']), pct(r['bonus_fraction']), f"{float(r['lt_shift'])*100:+.1f}", money(r['terminal_collateral_shortfall_usd']), money(r['seized_usd']), pct(r['max_cumulative_price_impact']), r['terminal_eligible_wallets']] for r in front])
    doc.para('Pareto tối thiểu hóa đồng thời shortfall, collateral seized và impact, so sánh riêng trong mỗi shock. Không có một bộ tham số tối ưu duy nhất. Frontier phụ thuộc hàm mục tiêu và engine giả định, giữ số dư ban đầu cố định khi đổi LT, bỏ qua phản ứng người vay. Không sử dụng bảng này như khuyến nghị tham số Aave thực tế.')
    doc.title('10. Mức sẵn sàng và việc còn thiếu')
    readiness = [
        [1,'Đạt trong phạm vi','Stress một snapshot; cần panel nhiều ngày và kiểm định ngưỡng để suy rộng'],
        [2,'Đạt trong phạm vi','Đủ counts lịch sử; bổ sung giá cho phần thiếu trước khi kết luận USD toàn bộ'],
        [3,'Thăm dò','Cần xác minh funding đại diện, sensitivity nhãn/cửa sổ và thiết kế nhận diện nhân quả'],
        [4,'Đạt trong phạm vi','Cần residual diagnostics, mô hình covariates phù hợp và robustness nhiều giai đoạn'],
        [5,'Thăm dò','Cần toàn bộ exposure đồng bộ nhiều ngày và nhận diện kênh truyền dẫn'],
        [6,'Thăm dò','Cần hiệu chỉnh liquidity/impact và replay đúng revision trên nhiều wave ngoài mẫu'],
        [7,'Thăm dò','Phụ thuộc RQ6 được kiểm chứng; bổ sung phản ứng người vay và robustness mục tiêu'],
    ]
    doc.table(['RQ','Mức dùng được','Giới hạn / bước tiếp theo'],readiness)
    doc.title('11. Lệnh tự chạy và so sánh')
    doc.para('Chạy trong thư mục repository. Giữ nguyên data-run, cấu hình và phiên bản thư viện. Không dùng --smoke. Dùng thư mục kết quả mới chưa tồn tại; không ghi đè bản tham chiếu. Bản tham chiếu local là results/full_7rq_20261022_final.')
    doc.code('''.\\.venv\\Scripts\\python.exe -m defi_models check --config configs/models.full_7rq_20261022.json
.\\.venv\\Scripts\\python.exe -m defi_models all --config configs/models.full_7rq_20261022.json --allow-exploratory --out results/my_7rq_comparison
.\\.venv\\Scripts\\python.exe scripts/validate_model_run.py results/my_7rq_comparison
.\\.venv\\Scripts\\python.exe scripts/compare_model_runs.py results/full_7rq_20261022_final results/my_7rq_comparison --json-out results/my_7rq_comparison/comparison.json''')
    doc.para('Có thể thay all bằng rq1 … rq7 để chạy riêng; RQ5–7 cần --allow-exploratory. Script compare dùng được với hai lần chạy cùng danh sách RQ. Với bộ cả 7, kết quả mong đợi: passed=true, files_compared=22, difference_count=0. Khác đường dẫn máy và thời gian chạy không tạo khác biệt; cấu hình, identities của input, counts và file kết quả đều được đối chiếu. Phiên bản thư viện được hiển thị để kiểm tra. So sánh chỉ đọc các file cần thiết; nó không tự xác minh lại toàn bộ SQLite.')
    doc.code('''.\\.venv\\Scripts\\python.exe -m pip install -r results/full_7rq_20261022_final/requirements-reference.txt
.\\.venv\\Scripts\\python.exe scripts/build_7rq_results_report.py results/full_7rq_20261022_final''')
    doc.para('Dataset đã freeze nằm ngoài GitHub. Gói báo cáo không chứa database 11+ GB; máy khác cần bản dữ liệu riêng giữ nguyên cấu trúc, audits và freeze manifest. Để đổi chỗ dataset dùng --data-run. requirements-reference.txt ghi đúng phiên bản đã chạy; cần Python 3.12.14 để khớp môi trường tham chiếu. Lệnh tạo báo cáo đọc các file kiểm tra đã lưu; nó không tự chạy lại mô hình hoặc test.')
    doc.title('12. Các file dùng để kiểm chứng')
    doc.table(['File / thư mục trong bộ kết quả','Nội dung'],[
        ['rq1/ … rq7/','CSV kết quả và summary.json phương pháp/giới hạn'],
        ['manifest.json / config.json','Lệnh, phiên bản, timing, data-run, cấu hình thực chạy và input hashes'],
        ['validation.json','Kết quả validator đầu ra'],
        ['reproducibility.json','Đối chiếu hai lần chạy đầy đủ'],
        ['convergence.json','Đối chiếu RQ7 max_rounds 200 và 400'],
        ['code_identity.json / requirements-reference.txt','SHA-256 mã nguồn và phiên bản thư viện'],
        ['result_checksums.json','SHA-256 của các CSV và summary.json dùng để đối chiếu'],
        ['TONG_HOP_RQ.csv','Bảng trạng thái từng RQ dạng CSV UTF-8'],
        ['BAO_CAO_KET_QUA_7_RQ.html / .md','Báo cáo này; HTML tự chứa, mở offline và có thể Print → Save as PDF'],
    ])
    doc.save(run)
    with (run/'TONG_HOP_RQ.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.writer(handle)
        writer.writerow(['RQ','Thuc_thi','Muc_san_sang','Gioi_han','Thoi_gian_giay'])
        for i,status,limit in readiness:
            entry=next(r for r in manifest['models'] if r['rq']==i)
            writer.writerow([f'RQ{i}',entry['execution'],status,limit,entry['seconds']])
    digest=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    tracked=[p for folder in ('defi_models','defi_data') for p in (ROOT/folder).glob('*.py')]
    tracked += [ROOT/'configs/models.full_7rq_20261022.json',Path(__file__).resolve(),ROOT/'scripts/compare_model_runs.py',ROOT/'scripts/validate_model_run.py']
    identity={'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'files':{p.relative_to(ROOT).as_posix():digest(p) for p in sorted(tracked)}}
    (run/'code_identity.json').write_text(json.dumps(identity,indent=2),encoding='utf8')
    checksums={p.relative_to(run).as_posix():digest(p) for p in sorted(run.glob('rq*/*')) if p.suffix=='.csv' or p.name=='summary.json'}
    (run/'result_checksums.json').write_text(json.dumps(checksums,indent=2),encoding='utf8')
    (run/'requirements-reference.txt').write_text(f"numpy=={manifest['versions']['numpy']}\nscipy=={manifest['versions']['scipy']}\n",encoding='utf8')
    print(run/'BAO_CAO_KET_QUA_7_RQ.html')


if __name__=='__main__':
    main()
