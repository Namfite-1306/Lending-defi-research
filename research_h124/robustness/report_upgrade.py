"""Audit new results without rewriting the frozen research inputs."""
from .common import *

def main():
    checked={}
    h2=load(OUT/'h2/summary.json')
    checked[str(OLD/'market_event_quotes.csv')]=digest(OLD/'market_event_quotes.csv')==h2['source_sha256']
    for part in ['h1','h2','h3','cascade']:
        summary=load(OUT/part/'summary.json')
        for relative,expected in summary.get('source_hashes',{}).items():
            checked[relative]=digest(ROOT/relative)==expected
    for relative,expected in load(OUT/'h3/protocol.json').get('source_hashes',{}).items():
        checked[relative]=digest(ROOT/relative)==expected
    if not all(checked.values()):raise RuntimeError('Frozen input changed')
    audit=read(OUT/'h1/audit.csv')
    assert len(audit)==13 and all(r[k]=='True' for r in audit for k in ['full_snapshot_verified','HF_reconciled','aggregate_debt_verified','baseline_matches_frozen_curve'])
    h3=load(OUT/'h3/summary.json')
    summary={'updated_utc':now(),'scope':'13 quarters Q1/2023–Q1/2026; old datasets/results retained',
      'frozen_source_hashes_checked':len(checked),'all_hashes_match':True,
      'h1':'Completed quarterly basis sensitivity; intraday basis calibration still sparse',
      'h2':'Completed paired day/block bootstrap; cross-protocol difference sensitive to bootstrap choice',
      'h3':'Validation-only calibration completed; residual diagnostics still fail; new independent holdout required',
      'cascade':'Chronological quote calibration completed; forward 1h windows have no matched-route events; end-to-end validation unavailable',
      'live':'Durable job state, interrupted-job detection, optional bearer API authentication and POST rate limiting implemented; single worker only',
      'paid_or_account_sources_used':False,'production_forecast_ready':False}
    save(OUT/'summary.json',summary)
    text='''# Báo cáo nâng cấp giới hạn — 26/10/2026

Dataset/kết quả cũ được giữ nguyên. Kết quả mới nằm riêng tại `results/limitations_upgrade_20261026`. Kỳ chính là Q1/2023–Q1/2026 (13 quý), không khôi phục Q2/Q3/2026 đã loại theo yêu cầu.

| Phần | Đã thực hiện và kết quả | Giới hạn còn lại / bước tiếp theo |
|---|---|---|
| H1 | Kiểm tra đủ borrower census, HF, tổng nợ và đối chiếu đường stress cũ của cả 13 quý; 65 tổ hợp shock chung 20% và basis. Định giá lại cả phía tài sản thế chấp và nợ. | Basis DEX cùng block chỉ có wstETH/WBTC, chưa có chuỗi intraday phủ toàn thị trường. Cần báo giá/pool state lịch sử trước khi hiệu chỉnh xác suất kịch bản. |
| H2 | Bootstrap theo ngày và moving block 7 ngày, 999 lần; 216 dòng CI, cùng lịch kể cả ngày không có sự kiện; so sánh theo token/kỳ/tuổi giá/thước đo. | WETH/USDC năm 2024, tuổi giá 300s: HHI chuẩn hóa Comet−Aave = 0.2516. CI ngày [-0.0136; 0.6936] chứa 0; CI block 7 ngày [0.0050; 0.7341] không chứa 0. Chênh lệch chưa ổn định theo cách resample, không kết luận quan hệ nhân quả. Morpho mẫu nhỏ không xếp hạng. |
| H3 | Refit train-only, chọn hiệu chỉnh bằng validation, so 6 biến thể; tách hiệu chỉnh xác suất và kích thước sự kiện. | Validation chọn history/two-part: expected/observed=1.4504, PIT KS p=0.018, ACF p=0.002. History/probability-only giảm tỷ lệ còn 1.0318 nhưng ACF p=0.002; không chọn lại dựa trên test. Cả hai chưa đạt residual. Test đã xem trước đây, lần chạy này là robustness thăm dò, cần holdout tương lai độc lập. |
| Cascade | Chỉ dùng ngày trước để fit tác động giá, kiểm tra hai ngày kế tiếp với/không feedback. Sai số quote trung vị 4.87 bps. Bổ sung bảng độ phủ 1/6/24 giờ và danh sách tuyến thiếu. | Hai cửa sổ 1 giờ không có sự kiện khớp tuyến, nên sai số quote không chứng minh cascade đúng. Cửa sổ 24 giờ chỉ phủ khoảng 29–32% sự kiện ở hai ngày đó; cần thêm tuyến và trạng thái trước sự kiện. Snapshot 05/02/2026 còn thiếu 3,358 ví. Chưa chuyển cửa sổ 24 giờ thành backtest đạt chuẩn. |
| Dashboard/backend | Hiển thị kiểm chứng mới riêng bên dưới findings cũ; job ghi SQLite, phân biệt job bị ngắt sau restart; Bearer tùy chọn và giới hạn POST. | Vẫn một worker; chưa có hàng đợi phân tán, SLA, máy chủ public hay real-time độc lập trên Vercel. Vercel không có backend dùng gói lịch sử và ghi rõ trạng thái. |

## Nguồn hiện có và nhu cầu dữ liệu

Đã probe 4 RPC public không tài khoản tại hai mốc lịch sử: cả 8 probe không truy cập được từ máy này (HTTP 403/525). Đây là lỗi khả năng truy cập, không đủ bằng chứng để kết luận node bị pruned. Chưa dùng tài khoản hoặc nguồn trả phí.

Muốn bổ sung snapshot 05/02/2026 cần nguồn hỗ trợ historical `eth_call` cho cấu hình, reserve, e-mode và borrower state tại block trước sự kiện; cần hoàn tất 3,358 ví còn thiếu rồi kiểm tra tổng nợ/HF. Muốn kiểm định cascade cần thêm pool states/quotes và tuyến thực tế cho cặp collateral/debt trong `cascade/missing_routes.csv`, cùng oracle path đúng thời điểm. Trước khi dùng nguồn có tài khoản/trả phí sẽ báo và chờ duyệt.

## Dùng trong bài

H1: trình bày stress có điều kiện và độ nhạy basis; các haircut 2/5/10% là giả định, không phải quan sát hay dự báo. Ví dụ Q1/2026 dưới shock 20%, tỷ lệ eligible tăng từ khoảng 3.08% lên 27.36% khi thêm haircut giả định 5%; không diễn giải là liquidation đã xảy ra.

H2: dùng point estimates kèm CI và độ nhạy bootstrap; tránh tuyên bố chênh lệch giữa giao thức luôn có ý nghĩa thống kê. H3: báo cáo mô hình lịch sử có thông tin dự báo, song calibration/residual chưa đủ cho dự báo vận hành. Cascade: đưa vào phần mô phỏng cơ chế và giới hạn kiểm định, không coi là bằng chứng nhân quả.

## Chạy lại

```powershell
python -m research_h124.robustness.h1_basis
python -m research_h124.robustness.h2_uncertainty
python -m research_h124.robustness.h3_calibration
python -m research_h124.robustness.cascade_forward
python -m research_h124.robustness.report_upgrade
```

`source_probe` là kiểm tra nguồn tùy chọn, không cần chạy lại khi chỉ tái tạo kết quả từ dữ liệu đóng băng. H3 không tự tạo holdout độc lập bằng cách chạy lại cùng dữ liệu.
'''
    (OUT/'BAO_CAO_NANG_CAP.md').write_text(text+'\nSố nguồn cũ đã kiểm tra hash: '+str(len(checked))+'. Tất cả khớp.\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
