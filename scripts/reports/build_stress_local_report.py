"""Capture actual local API evidence and write an implementation status report."""
import csv,json,sys,urllib.request,hashlib
from pathlib import Path
from datetime import datetime,timezone,timedelta

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'results/stress_validation_20261024'

def main():
    captured={}
    for name in ['status','universe','liquidity','backtests','models']:
        try:
            with urllib.request.urlopen('http://127.0.0.1:8790/api/'+name,timeout=30) as response:captured[name]=json.load(response)
        except Exception as exc:captured[name]={'capture_error':type(exc).__name__}
    evidence=json.loads((OUT/'evidence.json').read_text(encoding='utf8'))
    capture_path=OUT/'runtime_verification.json';capture_path.write_text(json.dumps(captured,ensure_ascii=False,indent=2),encoding='utf8')
    u=captured['universe'];s=captured['status'];l=captured['liquidity'].get('product') or {};m=captured['models'] or {}
    with (OUT/'concentration_by_period.csv').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    coverage=[]
    for protocol in sorted({r['protocol'] for r in rows}):
        sample=[r for r in rows if r['protocol']==protocol and r['frequency']=='month' and r['entity']=='borrower' and r['metric']=='count_all']
        total=sum(int(r['all_events']) for r in sample);priced=sum(int(r['priced_events']) for r in sample)
        coverage.append(f'| {protocol} | {total:,} | {priced:,} | {priced/total:.2%} |')
    backfill=[]
    for p in captured['backtests'].get('snapshots',[]):
        backfill.append(f"| {p['date']} | {p['wallets_scanned']:,}/{p['historical_borrowers']:,} | {p['passed']}/{p['active_debt_wallets']} | {p['status']} |")
    now=datetime.now(timezone(timedelta(hours=7))).isoformat(timespec='seconds')
    tests=json.loads((OUT/'test_verification.json').read_text(encoding='utf8'))
    text=f'''# Báo cáo mục tiêu 4 và 5 — bản local

Thời điểm ghi nhận: {now} (UTC+7). Số live sẽ thay đổi sau thời điểm này.

## Kết luận về mức hoàn thành

- **Mục tiêu 4:** đã mở rộng concentration theo thời gian, thu dữ liệu thanh khoản
  thật bổ sung, chạy engine theo cặp với risk parameters lịch sử. **Chưa hoàn thành
  kiểm chứng cascade toàn chuỗi**; không gán trạng thái validated cho mô hình này.
- **Mục tiêu 5:** dashboard local hoạt động và tương tác được; collector/census/
  snapshot/model/quotes chạy ở worker riêng, có scope và thời điểm nguồn. **Chưa
  đạt snapshot đồng bộ toàn thị trường hoặc bằng chứng vận hành liên tục nhiều ngày.**

Dashboard: http://127.0.0.1:8790/validation; Research Lab: /lab; live monitor: /.

## Đã làm gì và bằng chứng

| Phần việc | Đã triển khai/chạy | Trạng thái |
|---|---|---|
| Concentration theo kỳ | {evidence['concentration']['rows']} dòng; tháng/quý; ví/token; count toàn bộ và count/USD cùng mẫu có giá ≤1 giờ | Đạt trong mẫu và bộ lọc đã ghi |
| Quote thị trường | 155 quote cũ + {evidence['additional_quote_input']['rows']} quote mới trước sự kiện, hai pool Uniswap V3 | Đã thu thật, nguồn mới có hash riêng |
| Kiểm tra đường cong | {evidence['dex']['usable_curves']} pool/block/direction curves; {evidence['dex']['interpolation_passed_curves']} đạt gate lỗi nội suy ≤10 bps | Chặn ngoại suy, sai block/chiều và nội suy không đạt |
| Replay swap | 37/37 ca đủ điều kiện khớp; loại 15/52 ca | Bằng chứng đã thu từ trước; không phải replay cascade mới |
| Pair cascade | 18 kịch bản trên 17.084 ví tại block 21.762.264; trả một debt reserve/thu một collateral | Đã chạy; vẫn thăm dò |
| Risk parameters | 38 reserves, 4 E-mode categories; bonus, bitmap collateral, phí giao thức tại đúng block | Đã đọc on-chain; không dùng category legacy thay bitmap |
| Oracle/DEX | Giá oracle tách khỏi giá thực thi; delay 0/1/3 vòng và control không impact | Đạt sensitivity; delay chưa đo bằng thời gian thực |
| Snapshot trước sự kiện | Collector chọn ví từ Borrow trước cutoff, checkpoint SQLite theo lô và đối chiếu HF | Đang backfill, chưa full cohort |
| Borrower census live | Seed 86.631 ví; bổ sung live Borrow và worker thu bù khoảng trống discovery | Đang quét; lưu tiến độ qua restart |
| Snapshot stress live | Tối đa 40 ví, cùng block, HF được kiểm định; ưu tiên rủi ro và luân phiên | Đã chạy, scope cohort |
| Thanh khoản live | Worker lấy tối đa 16 quote/chu kỳ cho hai pool | Đã chạy; không tự áp vào snapshot lịch sử |
| Dashboard/API | Bộ lọc, CSV, so kịch bản, coverage, freshness và tiến độ backfill | Đã kiểm tra trên trình duyệt/API |
| Kiểm thử tự động | {tests['total']} test cases: {tests['passed']} đạt, {tests['skipped']} bỏ qua; không failure/error | Có log và JSON, không thay thế validation thực nghiệm |

## Quan sát runtime thực tế

- Collector: **{s.get('state')}**, cursor **{s.get('cursor')}**.
- Census: **{u.get('scanned_wallets'):,}/{u.get('known_wallets'):,} ví đã biết**;
  còn mới ≤1 giờ: **{u.get('fresh_wallets'):,}**. Đây không phải coverage USD.
- Borrow discovery: **{u.get('discovery',{}).get('state')}**;
  block tiếp **{u.get('discovery',{}).get('next_block')}**, target **{u.get('discovery',{}).get('target')}**.
- Model snapshot: block **{m.get('block')}**, cohort
  **{m.get('payload',{}).get('scope',{}).get('monitored_wallets')} ví**.
- Live liquidity: block **{l.get('block')}**, **{len(l.get('payload',{}).get('quotes',[]))}/16 quotes**;
  freshness **{l.get('freshness',{}).get('state')}**.
- Restart backend đã giữ lại census/checkpoint; việc này chưa thay thế stress test
  mất mạng/reorg thực tế hoặc đánh giá uptime nhiều ngày.

## Coverage giá khi giới hạn tuổi 1 giờ

| Protocol | Tất cả liquidation events | Events có giá hợp lệ | Tỷ lệ theo số events |
|---|---:|---:|---:|
{chr(10).join(coverage)}

Coverage thấp ở một số kỳ làm suy yếu kết luận về concentration USD. Count toàn bộ
vẫn dùng đủ events; count dùng để đối chiếu USD chỉ lấy đúng mẫu có giá. Không coi
giá thiếu là 0. Đây là phân tích sensitivity với bộ lọc chặt hơn bài draft trước;
không tráo các số mới vào bài mà bỏ qua sự thay đổi mẫu. USD giữa các protocol có
ý nghĩa kinh tế khác nhau, do đó báo cáo tách riêng.

## Tiến độ snapshot trước sự kiện

| Ngày UTC | Đã quét / cohort trước cutoff | HF đạt / active debt | Trạng thái |
|---|---:|---:|---|
{chr(10).join(backfill)}

Job tiếp tục từ checkpoint với budget khoảng 30 phút, batch 100, tối đa năm ngày
được chọn. Một lô chậm có thể vượt thời gian đặt; budget này không bảo đảm đủ full
snapshot. Log/PID ở `output/upgrade_20261024/`. Không chạy hai collector cùng output.
Snapshot mới chỉ được export thành full khi quét đủ cohort và mọi ví còn nợ qua
HF reconciliation; vẫn cần audit/freeze độc lập trước khi đưa vào research run.

## Chưa đạt và cách hoàn tất

1. **Backtest cascade:** thiếu full pre-event snapshots, đường đi giá oracle/DEX
   trong suốt cửa sổ, adapter thanh lý theo revision và kiểm chứng giao dịch. Tiếp
   tục backfill, thu đường đi giá/quote, dựng execution replay rồi chia train/holdout
   theo thời gian. Năm ngày hiện được chọn ex post, chưa là tập holdout độc lập.
2. **Hiệu chỉnh liquidity:** quote mới chỉ ở hai pool và block đầu; {evidence['dex']['usable_curves']-evidence['dex']['interpolation_passed_curves']}/{evidence['dex']['usable_curves']} curves
   chưa qua gate nội suy 10 bps. Thu grid dày thích ứng hoặc gọi Quoter trực tiếp
   ở đúng size/block; chưa dùng một curve cho token/pool/giờ khác.
3. **Thanh lý chính xác:** engine thử nghiệm chỉ hỗ trợ revision 6, còn float
   arithmetic, lựa chọn cặp lớn nhất, order/gas/routing giả định và hạn chế chuyển
   đổi GHO. Không dùng quy tắc này cho revision live mới. Cần fork/EVM transaction
   replay, integer rounding và adapter từng revision trước khi tuyên bố tương đương.
4. **Toàn thị trường realtime:** 40 ví là coherent cohort, census cuốn chiếu khác
   block. Cần đo throughput RPC, quét đủ universe và chọn chính sách snapshot đồng
   bộ phù hợp nguồn lực. Không suy rằng quét hết một vòng đồng nghĩa mọi ví còn mới.
5. **Vận hành:** cần chạy nhiều ngày, ghi uptime/latency/coverage, diễn tập mất
   kết nối và khôi phục. Bản local chưa triển khai public theo phạm vi yêu cầu.

Kết quả 7 RQ và dataset đã freeze được giữ nguyên. Kết quả mới nằm ở
`results/stress_validation_20261024`; dữ liệu mới ở `data/stress_backtests_20261024`.
Các bảng thăm dò này chưa đủ để kết luận contagion nhân quả hay bad debt on-chain.

## Tái lập và nguồn kỹ thuật

Xem `README_STRESS_LOCAL.md` để chạy backend, thu dữ liệu, tạo lại mô phỏng và
đọc các API. `runtime_verification.json` lưu payload API tại thời điểm báo cáo;
`evidence.json` lưu hash nguồn và gate nghiên cứu.

- [Aave legacy LiquidationLogic](https://github.com/aave/aave-v3-core/blob/master/contracts/protocol/libraries/logic/LiquidationLogic.sol): tham chiếu close factor và thanh lý theo cặp; chưa phải chứng minh bytecode của snapshot tương đương hoàn toàn.
- [Uniswap IQuoterV2](https://github.com/Uniswap/swap-router-contracts/blob/main/contracts/interfaces/IQuoterV2.sol): giao diện quote theo pool/token/size qua eth_call.
'''
    (OUT/'BAO_CAO_MUC_TIEU_4_5_LOCAL_20261024.md').write_text(text,encoding='utf8')
    print(json.dumps({'report':str(OUT/'BAO_CAO_MUC_TIEU_4_5_LOCAL_20261024.md'),'cursor':s.get('cursor'),'scanned':u.get('scanned_wallets'),'quotes':len(l.get('payload',{}).get('quotes',[]))}))

if __name__=='__main__':main()
