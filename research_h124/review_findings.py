"""Evidence-based reassessment; never edits the historical model outputs."""
import statistics
import numpy as np
from .v2_common import *

def run():
    h1=load(V1_OUT/'h1/summary.json',{})
    breaks=[r for r in read(V1_OUT/'h1/breakpoints.csv') if r['mapping']=='factor_family_1to1' and r['scenario']=='joint' and r['grid_step_percent']=='1']
    knots=[float(r['share_knot']) for r in breaks if r['share_knot']]
    curves=[r for r in read(V1_OUT/'h1/stress_curves.csv') if r['mapping']=='factor_family_1to1' and r['scenario']=='joint' and abs(float(r['shock'])-.2)<1e-8]
    shares=[float(r['eligible_debt_share']) for r in curves]
    coverage=[r for r in read(V1_OUT/'h2/matched_coverage.csv') if r['window']=='common_calendar_2024' and r['max_price_age']=='3600']
    table='\n'.join(f"| {'WETH' if r['token'].startswith('0xc02') else 'WBTC'} | {r['protocol']} | {r['priced_episodes']}/{r['matched_episodes']} | {float(r['event_price_coverage'])*100:.2f}% |" for r in coverage)
    temporal=load(OUT/'h4_prefix/summary.json',{});quality=load(OUT/'model_quality.json',{});core=[r for r in quality.get('models',[]) if r['variant']=='h4_prefix' and r['model']=='oracle_gas_hawkes'][0]
    nb=[r for r in quality.get('models',[]) if r['variant']=='h4_prefix_nb'];comet=load(OUT/'h2_full_validation/summary.json',{})
    with np.load(DATA/'h4_prefix_panel_5min.npz') as a:
        common=a['old_valid']&np.isfinite(a['X']).all(axis=1);te=a['t']>=1751328000
        event_coverage=float(a['y'][te&common].sum()/a['y'][te].sum())
    nb_rows='\n'.join(f"| {r['model']} | {r['expected_events']:,.0f} | {r['expected_observed_ratio']:.2f} lần | {r['residual_KS_p']} / {r['residual_ACF_p']} |" for r in nb)
    text=f'''# Tự đánh giá findings và ưu tiên cải thiện

Cập nhật {now()}. **H2 giữ nguyên: concentration; H3 = H4 cũ (clustering/self-excitation)**.
Các số RQ, module và thư mục không đổi.
Đây là đánh giá lại bằng dữ liệu local, không phải một lần kiểm chứng độc lập mới.
Không sửa dataset hoặc bảng kết quả cũ.

| Phát hiện | Đánh giá hiện tại | Có thể viết bài đến mức nào? |
|---|---|---|
| H1: đường stress và điểm gãy thay đổi theo thời điểm | Bằng chứng mô phỏng mô tả trên {h1['full_snapshots']}/15 full census | Có thể trình bày kết quả có điều kiện và phạm vi rõ; chưa tuyên bố một ngưỡng giảm giá chung cho thị trường |
| H3: lịch sử liquidation cải thiện dự báo sau khi có controls | Có tín hiệu ngoài mẫu; calibration còn bị bác bỏ, test đã được xem | Exploratory predictive evidence; chưa xác nhận nhân quả hay dự báo production |
| H2: sửa định nghĩa nợ Comet | {comet['passed']}/{comet['selected']} episode khớp khoảng; không phải kiểm chứng mọi bytecode implementation | Đủ làm đóng góp đo lường, mô tả phương pháp và appendix kiểm chứng |
| H2: giao thức nào tập trung hơn | Coverage và N thay đổi lớn theo tuổi giá | Chưa đủ xếp hạng chung hay kết luận về toàn bộ borrowers/protocols |
| Cascade: feedback làm tăng thanh lý mô phỏng | Nhạy với route, capacity, gas, bonus và đường giá; actual-path chưa khớp | Chỉ viết như scenario/sensitivity; chưa gọi là hệ số khuếch đại quan sát thực |
| Dashboard | Đã có tương tác và scope/quality gates | Là sản phẩm nghiên cứu; không chứng minh model đã được validation |

## H1 — kết luận nào vững, kết luận nào cần thu hẹp?

Với joint shock, factor-family 1:1 và lưới 1 điểm %, share-knot dao động
**{min(knots)*100:.0f}–{max(knots)*100:.0f}%**, median {statistics.median(knots)*100:.0f}% trên {len(knots)} quý.
Đây là knot của hồi quy phân đoạn trên đường stress tĩnh, không phải một ngưỡng
liquidation cascade đã quan sát. Largest USD jump là đại lượng khác share-knot.
Tại joint shock 20%, eligible-debt share dao động **{min(shares)*100:.2f}–{max(shares)*100:.2f}%**.
Mẫu số là tổng nợ USD **sau shock**, có thể thay đổi khi debt token giảm giá;
đây không phải tỷ lệ tài sản bị bán hay bad debt. Giả định factor-family khiến
LST/WBTC đi cùng ETH/BTC, chưa đo đầy đủ depeg/basis.

Cần hoàn tất Q2/Q3-2026; đối chiếu breakpoint với ngưỡng HF/liquidation của ví;
thêm sensitivity mẫu số nợ trước shock, loại khoản đã HF<1 từ đầu và tách shocks
theo collateral/debt/basis. Báo cáo từng quý và leave-one-quarter-out; không coi
61 điểm shock/quý là 61 quan sát độc lập để suy ra p-value. Quý có vị thế lớn
cần giải thích bằng exposure thay vì chỉ đưa một hệ số hồi quy tổng hợp.

## H3 — tín hiệu dự báo có thật nhưng model chưa calibrated

Phần kỳ: **{temporal['scope']['start']} → trước {temporal['scope']['end_exclusive']}**.
Train trước 2025, validation nửa đầu 2025; test từ 01/07/2025.
Common bins coverage {temporal['common_bin_coverage']:.2%}; coverage số sự kiện trong
test {event_coverage:.2%}. Hai tỷ lệ khác nhau, không dùng coverage bins thay cho coverage events.
Test có {temporal['test_bins']:,} bins, {temporal['test_events']:,} events.
Validation chọn oracle + sampled gas; Hawkes cải thiện log-score so với Poisson
cùng biến **{temporal['excitation_logscore_gain']:,.2f}**; khoảng resampling theo ngày
{temporal['daily_resampling_95_interval']}. Khoảng này cố định fit, không phải
khoảng tin cậy nhân quả hoặc kết quả confirmatory đã đăng ký trước.
Tổng count oracle+gas Hawkes bằng {core['expected_observed_ratio']:.3f} lần quan sát,
nhưng KS p={core['residual_KS_p']}, ACF p={core['residual_ACF_p']} vẫn không đạt ở 5%.
Với 49 replications, p nhỏ nhất khoảng 0.02; cần nhiều bootstrap hơn cho kết luận cuối.

| Negative Binomial | Tổng count dự báo | Dự báo / thực tế | KS p / ACF p |
|---|---:|---:|---:|
{nb_rows}

NB có likelihood tốt hơn nhưng mean count bị lệch nghiêm trọng. Đây là thất bại
calibration/phân phối dự báo; chưa đủ bằng chứng nói do crawler sai hay do bug fit.
Không clipping kết quả để che sai lệch. Cần kiểm tra extrapolation của features,
độ nhạy hệ số và link function; thử regularization, time-varying baseline,
NB/hurdle hoặc marked/multivariate kernels theo protocol/token **như ứng viên**,
chọn bằng train/validation. Chỉ thêm độ phức tạp nếu rolling validation cải thiện.

Ưu tiên biến mới theo thứ tự: returns/volatility theo thị trường với timestamp
đúng thời điểm → utilization/lãi vay → HF queue và collateral composition/basis
→ DEX depth/execution controls. Không nội suy HF theo quý thành dữ liệu 5 phút.
Lập kiểm tra ngoài miền train và count calibration trên validation trước.
Dùng rolling mean/baseline thay đổi theo thời gian làm đối chứng; kiểm tra cửa sổ
5/15/60 phút, nhiều kernel và negative controls. Event timestamp tập trung theo
block/oracle có thể tạo clustering mà chưa chứng minh contagion tự thân.

Giữ kỳ mới chưa dùng làm kiểm chứng cuối khi có đủ dữ liệu. Q3/2026 chưa có bins
trong prefix; log-score 0 ở dòng rolling có bins=0 là **không có đánh giá**, không
phải score tốt. Q2/2026 chỉ đến 02/06, không phải nguyên quý. Self-excitation là
dự báo có điều kiện, không phải nhận diện nhân quả hoàn toàn.

## H2 — Concentration — vấn đề lớn nhất là sample selection

So cùng calendar 2024, USDC debt, đúng một collateral; tuổi giá tối đa 1 giờ:

| Collateral | Protocol | Events có giá / matched | Coverage |
|---|---|---:|---:|
{table}

Filter này chủ yếu sàng theo tuổi giá nợ USDC, không đồng nghĩa events thiếu
trong chain. Nới lên 24 giờ giữ 100% matched events của các nhóm này nhưng tăng
giả định về độ cũ giá; không tự động biến thành giá market tươi. Cần threshold
theo feed/heartbeat và thời kỳ depeg, nguồn giá độc lập nếu có, so event counts
không cần giá và concentration theo native USDC units bên cạnh USD. USD và count
trên cùng priced sample vẫn cần giữ để so đồng nhất; full-count là sensitivity riêng.

Một địa chỉ không chắc là một beneficial owner. Top1% ở mẫu ít ví có thể chỉ là
Top1; không dùng Top10 share để so trực tiếp N=4 với N=67. Giữ normalized HHI,
Gini, effective-entity fraction, bootstrap theo ngày/episode block và sensitivity
loại ví lớn. Morpho WETH năm 2024 chỉ 2 matched events, không đủ làm xếp hạng.
Credit correction chiếm {comet['credit_fraction_of_basePaidOut']:.2%} tổng basePaidOut:
đây là chênh lệch đo lường, không phải tỷ lệ giảm rủi ro hay mức tập trung.

## Cascade và dashboard

Đã có 420 quotes, 3/5 pre-event full snapshots, impact fit trên 3 ngày train và
168 quote observations ở 2 ngày muộn. Sai số quote median không kiểm chứng cả
cascade; các quotes cùng pool/ngày/size phụ thuộc nhau. Hai heldout ngày còn thiếu
full snapshots. Ví dụ 05/08/2024 actual-path, không feedback: 436 actions mô phỏng
so 91 sự kiện matching; chưa dùng engine để dự báo liquidation volume thực.
Đường giá realized có thể chứa feedback thực tế, không phải shock ngoại sinh.
Cần đủ route, execution eligibility/grace/sentinel, gas/capacity/ordering và
so count/debt/price impact theo cùng cohort, cửa sổ và đơn vị. Hiệu chỉnh trên
train, khóa tham số rồi đánh giá ngày heldout; tránh chọn ngày sau khi xem sai số.

Dashboard đọc lại bảng nghiên cứu mỗi 30 giây, không tự thu đủ dữ liệu hay refit
models. Live poll 15 giây chỉ hữu ích khi nguồn RPC truy cập được; không coi
cache cũ là real-time. Live 40 ví và rolling census khác block không phải full
market synchronized snapshot. Nhãn H3 không đổi số RQ4 hoặc tên module h4.

## Việc nên làm tiếp theo

1. Khôi phục truy cập nguồn được phép, hoàn tất 2 quý, 2 event snapshots và 5.224 headers còn thiếu theo checkpoint hiện tại; không mua RPC trước khi xác minh nhu cầu.
2. Sửa bias do tuổi giá trong concentration bằng native-unit/full-count sensitivity và chính sách freshness theo feed, giữ USD comparisons cũ riêng.
3. Chẩn đoán count calibration và extrapolation NB; thêm đối chứng baseline thay đổi theo thời gian, thu controls tần suất phù hợp; chọn bằng validation.
4. Hoàn tất event backtest cascade trước khi trình bày amplification như bằng chứng thực nghiệm.
5. Viết H1 dạng static-stress findings, H3 dạng exploratory predictive evidence; trình bày đo lường Comet và các negative results rõ ràng.

Nguồn số liệu: h1/breakpoints.csv, stress_curves.csv, h2/matched_coverage.csv ở
results/research_h124_20261024; h4_prefix*, h2_full_validation, model_quality và
cascade/actual_path_backtest.csv ở results/research_h124_v2_20261024.
'''
    path=OUT/'DANH_GIA_FINDINGS_H1_H2_H3.md';path.write_text(text,encoding='utf8');return path

if __name__=='__main__':print(run())
