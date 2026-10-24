"""Repair report and preservation audit; unfinished stages remain explicit."""
from pathlib import Path
from .repair_common import *

def run():
    OUT.mkdir(parents=True,exist_ok=True);baseline=OUT/'protected_outputs.json'
    if not baseline.exists():
        paths=[]
        for folder in ['h4_prefix','h4_prefix_nb']:
            paths += [p for p in (V2_OUT/folder).glob('*') if p.is_file()]
        paths += [DATA/'h4_prefix_panel_5min.npz',V1_OUT/'h2/episodes.csv',V1_OUT/'h2/collateral_legs.csv']
        save(baseline,{str(p):digest(p) for p in paths})
    expected=load(baseline,{});mismatches=[name for name,value in expected.items() if not Path(name).is_file() or digest(name)!=value]
    from .audit_v2 import audit
    old=audit();h2=load(OUT/'h2/summary.json',{});h3=load(OUT/'h3/summary.json',{});rows=read(OUT/'h3/model_comparison.csv') if (OUT/'h3/model_comparison.csv').exists() else []
    if h3.get('updated_utc','')<load(OUT/'h3/protocol.json',{}).get('created_utc',''):h3={}
    checks={}
    if (OUT/'h1/denominator_sensitivity.csv').exists():
        old_curves={(r['quarter'],r['mapping'],r['scenario'],round(float(r['shock']),6)):float(r['eligible_debt_share']) for r in read(V1_OUT/'h1/stress_curves.csv')}
        repaired=read(OUT/'h1/denominator_sensitivity.csv')
        checks['h1_existing_post_denominator_reproduced']=all(abs(float(r['eligible_post_debt_over_post_total'])-old_curves[(r['quarter'],r['mapping'],r['scenario'],round(float(r['shock']),6))])<1e-9 for r in repaired)
        checks['h1_zero_shock_newly_eligible_zero']=all(int(r['newly_eligible_wallets'])==0 for r in repaired if float(r['shock'])==0)
    completed=[r for r in rows if r['status']=='completed_exploratory']
    if completed:checks['h3_all_models_same_test_support']=len({(r['test_bins'],r['test_events']) for r in completed})==1
    if (OUT/'h3/rolling_quarter_scores.csv').exists():checks['empty_rolling_scores_are_NA']=all(r['loglik']=='' and r['status']=='no_scored_bins' for r in read(OUT/'h3/rolling_quarter_scores.csv') if int(r['bins'])==0)
    quarters=[]
    for q in load(H1_DATA/'h1/quarter_plan.json',[]):
        s=load(H1_DATA/'h1'/q['quarter']/'scope.json',q);quarters.append(s)
    result={'updated_utc':now(),'hypotheses':{'H1':'quarterly price stress','H2':'liquidation concentration','H3':'clustering/self-excitation'},
      'h1_full_quarters':sum(r.get('full_snapshot_complete') is True for r in quarters),'h1_missing':[r for r in quarters if not r.get('full_snapshot_complete')],
      'source_access':load(OUT/'source_access.json',{}),'h2':h2,'h3':h3,'h3_models_written':len(rows),'h3_status':'completed_exploratory' if h3 else 'running_or_not_started',
      'h1_sensitivity':load(OUT/'h1/summary.json',{}),'explosive_bin_diagnosis':load(OUT/'h3/explosive_bin_diagnosis.json',{}),'checks':checks,
      'tests':load(OUT/'tests.json',{}),'protected_repair_inputs':len(expected),'protected_input_mismatches':mismatches,'old_outputs_preserved':not mismatches and old['old_outputs_preserved'],
      'paid_source_used':False,'account_source_used':False}
    save(OUT/'manifest.json',result)
    model_rows='\n'.join(f"| {r['model']} | {r['status']} | {r.get('validation_loglik','—')} | {r.get('test_loglik','—')} | {r.get('expected_observed_ratio','—')} |" for r in rows)
    residuals='\n'.join(f"- {n}: KS p={d['bootstrap_KS_p']}, ACF p={d['bootstrap_acf_p']}, B={d['replications']}" for n,d in h3.get('diagnostics',{}).items()) or 'Chưa hoàn tất residual; không coi là đạt.'
    missing='\n'.join(f"- {r['quarter']}: {r.get('wallets_scanned',0) or 0}/{r['historical_borrowers']} địa chỉ, {r.get('status','pending')}." for r in result['h1_missing'])
    text=f'''# Báo cáo sửa dữ liệu và mô hình H1/H2/H3

Cập nhật {now()}. Tất cả output mới ở `{OUT}`. Không ghi đè các model/data cũ.

| Phần | Đã thực hiện | Đã đạt / còn thiếu |
|---|---|---|
| H1 | Kiểm tra lại 3 RPC, giữ checkpoint; {result['h1_full_quarters']}/15 full quý | RPC vẫn 403/Cloudflare 1010; không chạy hàng loạt lệnh chắc chắn thất bại, chưa hoàn thành 2 quý |
| H1 sensitivity | {result['h1_sensitivity'].get('rows','pending')} dòng mẫu số trước/sau shock và newly eligible, chỉ full snapshots | Không thay 2 quý thiếu; giữ nguyên giả định factor-family/direct-only |
| H2 full count/native | {h2.get('rows','pending')} dòng, count toàn matched events, native USDC upper/lower, so USD cùng sample riêng | Không cần giả định peg để tính native units; không mở rộng thành toàn lending ngoài scope |
| H2 freshness | 1h/6h/24h và policy USDC 26h bình thường, 1h khi biết alert depeg trong 24h trước; prior-block quotes | Policy giả định để sensitivity, chưa xác minh SLA/heartbeat chính thức; depeg giữa round và market prices độc lập còn thiếu |
| H2 uncertainty | 199 bootstrap theo ngày có events, normalized HHI/Gini, N và loại ví lớn | Không nhận diện beneficial owner; bootstrap ngày không bao hàm uncertainty về nguồn/definition |
| H3 extrapolation | Domain train/test riêng, max prediction và Top10-bin share; giữ báo cáo cũ | Không dùng số test để chọn penalty/architecture; kỳ test đã từng xem nên vẫn exploratory |
| H3 link/regularization | Exponential ridge và softplus; không clipping output; penalty và kernel chọn trên validation | Đánh giá dự báo và residual riêng; optimizer hội tụ không đồng nghĩa calibration đạt |
| H3 baseline | Softplus với background 7 ngày có sẵn trước bin, đối chứng bỏ short-term excitation | Background là proxy từ count history, không phải TVL/HF thực đo; comparator vẫn dùng slow history |
| H3 validation/test | Train trước 2025, validation nửa đầu 2025, test từ 01/07/2025 đến trước 02/06/2026 05:05 UTC | Chưa đủ kỳ Q3/2026; không tạo holdout mới bằng đổi tên |
| H3 residual/rolling | {result['h3_status']}; bootstrap mô phỏng cả slow/fast state; reset ở gaps; rolling gắn cờ partial/no bins | Residual p và calibration quyết định giới hạn kết luận; không có live forecast được duyệt |

## H1 checkpoint

{missing}

Nguồn mới nhất: `{result['source_access']}`. Chưa mua RPC hoặc dùng tài khoản.
Chỉ chạy tiếp khi nguồn được phép truy cập; lỗi access không chứng minh archive data không tồn tại.

## H2 — sử dụng mẫu nào?

- `no_USD_price_filter + count` dùng mọi matched event trong scope đã xác định.
- Native USDC upper/lower dùng đơn vị token, không giả định 1 USDC = 1 USD.
- USD/count-priced vẫn dùng cùng sample trong từng policy. So full-count với priced-count phải ghi rõ khác support.
- Chính sách depeg chỉ dùng các round ở block trước event, không nhìn tương lai.
- Nới freshness không làm giá cũ thành giá market mới. Giá độc lập ngoài oracle chưa được thu.
- Scope: cùng kỳ, USDC debt và đúng một collateral WETH/WBTC; các semantics absorption/repayment và deficit vẫn giữ cảnh báo.
- Top-wallet ranking theo metric đang xem; đây là influence sensitivity, không phải can thiệp nhân quả.

## H3 — kết quả mới

Chọn bằng validation: `{h3.get('selected_by_validation','pending')}`.
Chẩn đoán bin bùng nổ: `{result['explosive_bin_diagnosis'].get('largest_old_prediction','pending')}`.
Một dự báo mean không cần bằng đúng count thực trong mỗi bin; residual là kiểm tra
phân phối tổng thể, vẫn chưa đạt thì không gọi model calibrated.
Đối chứng không qua validation count-ratio vẫn được giữ với `validation_eligible=false`:
chọn penalty bằng validation để mô tả comparator, không đưa vào lựa chọn model chính.
Background proxy có half-life 7 ngày, dùng counts trễ; Hawkes short kernel được chọn riêng.
Softplus thay đổi link function thành tuyến tính ở đuôi dương, không cắt dự báo sau fit.
Validation dùng count-ratio screen 0.5–2 đã khóa trước lượt sửa này; đây là tiêu chí
chẩn đoán hậu kiểm, không phải kiểm định đã đăng ký trước. Mọi ứng viên thất bại vẫn lưu candidates.csv.

| Model | Trạng thái | Validation log-score | Test log-score | Expected / observed count |
|---|---|---:|---:|---:|
{model_rows}

{residuals}

So sánh pair và resampling block 7 ngày: `{h3.get('pair_comparison','pending')}`.
Không chọn lại model bằng test; không gọi self-excitation là nhận diện nhân quả.
Bootstrap giữ tham số và market path cố định nhưng mô phỏng lại cả slow/fast event
history. Không nối ACF qua gaps. Quý không có bins có score NA, không phải 0 tốt;
Q2/2026 là partial. Kỳ kiểm chứng độc lập mới vẫn cần thiết.

## Audit và tái lập

- Đầu ra cũ giữ nguyên: **{result['old_outputs_preserved']}**; {len(expected)} repair inputs có checksum, mismatches={mismatches}.
- Test: `{result['tests']}`.
- Kiểm tra output thực: `{checks}`.
- Dashboard `/research#repair`: bộ lọc riêng full/native/priced; bảng H3 và residual mới riêng V2.
- Chạy `python -m research_h124.repair_h2`, `python -m research_h124.repair_h3 --bootstrap 199`, rồi `python -m research_h124.repair_report`.
- Model chạy lại mất thời gian; dashboard chỉ đọc lại file, không tự refit.
'''
    (OUT/'BAO_CAO_SUA_H1_H2_H3.md').write_text(text,encoding='utf8');return result

if __name__=='__main__':print(run()['h3_status'])
