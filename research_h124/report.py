"""Refreshable research readiness report, including unfavorable diagnostics."""
import argparse,json,time
from pathlib import Path
from datetime import datetime,timezone,timedelta
from .common import SOURCE,DATA,OUT,CANONICAL,read,save,digest,now
from .h1 import summary as h1_progress

def load(path,default=None):
    return json.loads(Path(path).read_text(encoding='utf8')) if Path(path).exists() else default

def preserve_old():
    checked=[];errors=[]
    for name in ['full_7rq_20261022_final','merged_7rq_20261023_final']:
        folder=CANONICAL/'results'/name;file=folder/'result_checksums.json'
        if not file.exists():continue
        for rel,expected in load(file,{}).items():
            checked.append(str(folder/rel))
            if not (folder/rel).is_file() or digest(folder/rel)!=expected:errors.append(str(folder/rel))
    result={'checked_utc':now(),'checked_files':len(checked),'mismatches':errors,'unchanged':bool(checked) and not errors}
    save(OUT/'old_results_integrity.json',result);return result

def run(analyze=True):
    OUT.mkdir(parents=True,exist_ok=True)
    if analyze:
        from .h1_analysis import run as h1_analysis
        h1_analysis()
    snapshots=h1_progress() if (DATA/'h1/quarter_plan.json').exists() else []
    h1=load(OUT/'h1/summary.json',{'full_snapshots':0,'required':15,'status':'pending'})
    h2=load(OUT/'h2/summary.json',{});h4=load(OUT/'h4/summary.json',{});validation=load(OUT/'h2/archive_state_validation.json',{})
    preservation=load(OUT/'old_results_integrity.json') or preserve_old()
    residual=load(OUT/'h4/residuals.json',{});scores=read(OUT/'h4/model_comparison.csv') if (OUT/'h4/model_comparison.csv').exists() else []
    nb=read(OUT/'h4_nb/model_comparison.csv') if (OUT/'h4_nb/model_comparison.csv').exists() else []
    nb_residual=load(OUT/'h4_nb/residuals.json',{})
    tests=load(OUT/'tests.json',{})
    canaries=load(DATA/'h1/canary_report.json',[])
    episodes=read(OUT/'h2/episodes.csv') if (OUT/'h2/episodes.csv').exists() else []
    comet=[r for r in episodes if r['protocol']=='compound_v3_usdc'];paid=sum(int(r['base_paid_out_raw']) for r in comet);credit=sum(int(r['supply_credit_raw']) for r in comet)
    manifest={'updated_utc':now(),'data_source':str(SOURCE),'data_directory':str(DATA),'results_directory':str(OUT),'old_results_integrity':preservation,
      'h1':h1,'snapshot_progress':snapshots,'h1_revision_canaries':canaries,'h2':h2,'h2_state_validation':validation,'h4':h4,
      'h4_residual_bootstrap_passed':bool(residual) and all(r.get('bootstrap_KS_p',0)>=.05 and r.get('bootstrap_acf_p',0)>=.05 for r in residual.values()),
      'h4_nb_residuals':nb_residual,
      'tests':tests,'limitations':['Partial quarter snapshots never enter H1 results','H2 debt intervals and protocol financing semantics remain explicit',
        'Residual rejection is a model limitation, not a passing validation','SSRN July revision equivalence remains unverified']}
    save(OUT/'manifest.json',manifest)
    rows=[]
    for s in snapshots:rows.append(f"| {s['quarter']} | {s['block']} | {s.get('wallets_scanned',0):,}/{s['historical_borrowers']:,} | {s.get('active_debt_wallets','—')} | {s.get('passed','—')} | {s.get('status','pending')} | {s.get('full_snapshot_complete',False)} |")
    model_rows=[f"| {r['model']} | {float(r['test_loglik']):,.2f} | {float(r['test_count_MAE']):.4f} | {float(r['expected_test_events']):,.1f} | {r['eta']} |" for r in scores]
    nb_rows=[f"| {r['model']} | {float(r['test_loglik']):,.2f} | {float(r['test_MAE']):.4f} | {r['eta']} | {r['dispersion_r']} |" for r in nb]
    nb_diagnostics='; '.join(f"{name}: KS p={r['bootstrap_KS_p']}, ACF p={r['bootstrap_acf_p']}" for name,r in nb_residual.items()) if nb_residual else 'Bootstrap NB đang chạy/chưa có đầu ra đầy đủ.'
    text=f'''# Báo cáo nâng cấp nghiên cứu H1/H2/H4 — local

Cập nhật: {datetime.now(timezone(timedelta(hours=7))).isoformat(timespec='seconds')}.
Đây là báo cáo tiến độ có cập nhật; kết quả cũ được kiểm tra SHA256:
**{preservation['checked_files']} file, unchanged={preservation['unchanged']}**.

## Trạng thái nghiệm thu

| Phần | Đã thực hiện | Còn thiếu / giới hạn |
|---|---|---|
| H1 | Chốt 15 block cuối quý; census borrower trước cutoff; đọc config/E-mode/implementation tại block; HF và aggregate-debt gate; hiện {h1.get('full_snapshots',0)}/15 snapshot đã phân tích | Cần hoàn tất mọi quý; không gán snapshot mẫu 1–2 ví thành full |
| H2 | Nối {h2.get('comet_collateral_legs','—')} collateral legs vào {h2.get('comet_episodes','—')} Comet episodes; {h2.get('comet_missing_collateral_episodes','—')} episode thiếu collateral; credit correction và debt rounding interval; sensitivity matched-token/time/price/large-wallet | Chưa trace hết mọi implementation; absorption khác cash repayment; Aave extra deficit writeoffs chưa đủ cho broad-period equivalence |
| H4 | Bốn mô hình có/không market và self-excitation; train/validation/test; 5 quý rolling; bootstrap residual; NB và bin-size sensitivity riêng | Residual Poisson-family chưa đạt; không tuyên bố model fully calibrated hoặc causal |
| Tài liệu | Đối chiếu BIS1171/OECD và full text preprint tác giả liên quan SSRN6508318 | Chưa xác minh trùng bản SSRN tháng 7; đã phát hiện khác biệt block–ngày trong bản preprint |

## H1: từng quý

| Quý | Block | Borrower đã quét / trước cutoff | Active debt | HF đạt | Trạng thái | Full |
|---|---:|---:|---:|---:|---|---|
{chr(10).join(rows)}

Mỗi full snapshot có freeze_manifest riêng, positions, validation, raw reserve
configuration, E-mode bitmap và implementation fingerprint. `full_snapshot_complete`
chỉ true khi quét đủ, đối chiếu HF/model HF và tổng dư nợ qua gate. Với GHO,
totalSupply không trừ discount người dùng: đối chiếu bằng undiscounted indexed debt,
không dùng tổng repayable debt để rồi nới tolerance. Từ Pool revision 7 (v3.3),
HF dùng balanceOf GHO có discount; revision cũ dùng indexed debt. Adapter giữ riêng
HF debt, repayable debt và indexed debt; đã đối chiếu lại 400 ví đầu Q1/2025.
Nguồn thay đổi GHO: [audit v3.3, cập nhật 31/01/2025](https://github.com/aave-dao/aave-v3-origin/blob/main/audits/2024-10-22_StErMi_Aave-v3.3.md),
commit 786635f71327f0a500926742aec962b8897df3ed. Sai lệch được sửa theo semantics,
không nới tolerance để cho qua gate.

Đã kiểm tra ABI/HF mẫu sớm ở {sum(c.get('status')=='passed' for c in canaries)}/{len(canaries)}
quý 2025–2026, 64 ví/quý, gồm borrower cũ và mới. Đây chỉ là kiểm tra adapter,
**không tính thêm bất kỳ full snapshot nào**. Trạng thái error của lần thu trước
giữ lại cho đến khi quý được chạy lại; partial_checkpoint là dữ liệu đã lưu từ
worker bị gián đoạn. Báo cáo không suy canary đạt thành census đạt.

Stress dùng các quý full đã qua gate: shock 0–60%, ETH/BTC/joint; sensitivity bước
1/2/5 điểm %, factor-family 1:1 so với chỉ WETH/WBTC trực tiếp. Điểm gãy tỷ lệ nợ
eligible tách riêng bước tăng USD lớn nhất. Leave-one-quarter-out chỉ đo độ ổn định,
không tạo p-value từ các điểm shock phụ thuộc. Dải HF 1.05/1.1/1.2 đối chiếu BIS.

## H2: thay đổi đo lường đáng chú ý

- `basePaidOut` tổng cộng {paid/1e6:,.6f} **USDC**, phần supply-credit mint là
  {credit/1e6:,.6f} **USDC**; debt upper estimate sau hiệu chỉnh là
  {(paid-credit)/1e6:,.6f} **USDC**. Không mặc định 1 USDC = 1 USD.
- {h2.get('comet_credit_corrections','—')} episodes có credit; {h2.get('comet_rounding_bounded','—')} episodes có rounding interval.
- Archive-state spot check: {validation.get('passed','—')} khớp khoảng / {validation.get('selected','—')} mẫu;
  {validation.get('requires_intra_block','—')} cần intra-block replay; {validation.get('mismatches','—')} mismatch,
  {validation.get('errors','—')} lỗi. Không suy từ mẫu này thành trace verification toàn bộ.
- So sánh chính: 01/02–31/12/2024, USDC debt, **đúng một collateral WETH hoặc WBTC**.
  Mẫu extended đến hết Q3/2026 là sensitivity, có hạn chế về deficit semantics.
- {h2.get('sensitivity_rows','—')} dòng sensitivity: tuổi giá 15 phút/1h/6h/24h; bỏ Top1/5/10/1%;
  HHI/Gini chuẩn hóa theo N, effective entity fraction và Top1% share. Count/USD
  cùng mẫu có giá; N=1 chuẩn hóa là NA, N nhỏ được gắn cờ.
- Giá Chainlink có trước block event; không dùng cập nhật ở cuối cùng block để
  định giá ngược thời gian. WBTC/BTC basis chưa đo. Không xếp chung gross collateral
  USD khi Aave event có thể đã trừ protocol fee.

## H4: kết quả ngoài mẫu chính, bin 5 phút

Train trước 01/01/2025; validation H1/2025; test từ 01/07/2025 đến trước
01/10/2026. Covariates có sẵn tại đầu bin, chuẩn hóa trên train; kernel được chọn
trên validation rồi refit train+validation. Dự báo có điều kiện một bin, dùng event
quá khứ thực đã quan sát, không phải forecast mở nhiều bước.

| Mô hình | Test log-likelihood | Count MAE | Expected test events | Eta |
|---|---:|---:|---:|---:|
{chr(10).join(model_rows)}

Hawkes có thể cải thiện log score nhưng không đồng nghĩa tốt hơn ở mọi metric:
phải xem MAE, tổng count và hiệu chỉnh dự báo riêng. Không so trực tiếp likelihood
thô giữa bin 5 và 15 phút vì đơn vị outcome khác nhau.

Bootstrap PIT/KS và max ACF lag1–12 dùng 49 lượt, market path/parameters cố định.
Các mô hình Poisson-family hiện có diagnostic p-value 0.02: **chưa qua residual
validation**. Đây là giới hạn mô hình; không chỉnh dữ liệu/jitter để làm p-value đẹp.

Sensitivity negative-binomial để kiểm tra overdispersion:

| Mô hình | Test log-likelihood | Count MAE | Eta | Dispersion r |
|---|---:|---:|---:|---:|
{chr(10).join(nb_rows)}

NB có likelihood cao hơn đáng kể, cho thấy lựa chọn phân phối count ảnh hưởng
kết luận về mức excitation. Residual NB: {nb_diagnostics}
NB được bổ sung sau khi xem residual của mô hình chính: đây là sensitivity hậu kiểm,
không phải một kiểm định confirmatory mới trên tập test chưa từng được nhìn.
Không gọi eta là tỷ lệ thanh lý được gây ra một cách nhân quả.

## Các bước cần tiếp tục

1. Để worker H1 hoàn tất 15 quý; xem scope/error theo quý, không thay bằng mẫu nhỏ.
2. Trace 10 mẫu Comet có prior activity cùng block; xác minh implementation
   semantics toàn kỳ và bổ sung deficit events nếu muốn broad-period debt equivalence.
3. Thu nguồn giá/basis phù hợp nếu sensitivity tuổi giá khiến mẫu quá nhỏ;
   không tự mua nguồn dữ liệu hoặc nội suy giá tương lai.
4. Dùng chẩn đoán NB và bin-size để chọn hướng cải thiện market/kernel/regime;
   cần tập holdout mới cho lựa chọn model class hậu kiểm nếu muốn confirmatory.
   Kết quả dự báo hiện không xác nhận structural causality.
5. Xác minh full text phiên bản SSRN sửa tháng 7 trước khi tuyên bố tái lập bài đó.

## Đầu ra và tái lập

- `h1/`: baseline quý, stress curves, breakpoints, leave-one-quarter-out.
- `h2/`: episodes, collateral legs, matched concentration/coverage, state checks.
- `h4/`: candidates, heldout predictions, rolling quarters, residuals, summary.
- `h4_nb/`, `h4_15min/`: sensitivity giữ riêng.
- `literature/`: crosswalk, URLs và block/date verification.
- `manifest.json`: trạng thái máy đọc được; `old_results_integrity.json`: kiểm tra bảo toàn.
- Kiểm thử: {tests.get('total','pending')} test cases; {tests.get('passed','pending')} đạt,
  {tests.get('skipped','pending')} bỏ qua; failures={tests.get('failures','pending')}, errors={tests.get('errors','pending')}.

Các số H1 chưa đủ 15 quý là kết quả trung gian, không đại diện đầy đủ toàn kỳ.
Xem README_RESEARCH_H124.md để chạy tiếp và mở dashboard `/research`.
'''
    (OUT/'BAO_CAO_H1_H2_H4_LOCAL.md').write_text(text,encoding='utf8');return manifest

def main():
    p=argparse.ArgumentParser();p.add_argument('--watch-minutes',type=float,default=0);p.add_argument('--interval',type=float,default=60);a=p.parse_args()
    preserve_old();deadline=time.monotonic()+a.watch_minutes*60
    while True:
        try:
            result=run();print(now(),'H1 full analyzed',result['h1'].get('full_snapshots',0),flush=True)
            if result['h1'].get('full_snapshots')==15 or time.monotonic()>=deadline:break
        except Exception as exc:
            save(OUT/'report_error.json',{'at':now(),'error':str(exc)[:400]});print('REPORT ERROR',str(exc),flush=True)
            if time.monotonic()>=deadline:raise
        time.sleep(max(10,a.interval))
if __name__=='__main__':main()
