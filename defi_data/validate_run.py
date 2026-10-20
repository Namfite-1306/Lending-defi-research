"""Offline verification and a concise Vietnamese handover report."""
import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from .pipeline import ROOT,CONTRACTS

def read(path):
    with path.open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))

def validate(run):
    m=json.loads((run/'manifest.json').read_text(encoding='utf-8'))
    if m['status']!='completed': raise ValueError('Run did not complete')
    for name,digest in m['outputs'].items():
        if hashlib.sha256((run/name).read_bytes()).hexdigest()!=digest:
            raise ValueError(f'Output changed since manifest: {name}')
    events=read(run/'processed/events.csv')
    keys={(e['chain_id'],e['tx_hash'],e['log_index']) for e in events}
    if len(keys)!=len(events): raise ValueError('Duplicate event keys')
    order=[(int(e['block_number']),int(e['transaction_index']),int(e['log_index'])) for e in events]
    if order!=sorted(order): raise ValueError('Events are not in transaction execution order')
    with closing(sqlite3.connect(run/'raw.sqlite')) as conn:
        raw_count=conn.execute('SELECT COUNT(*) FROM logs WHERE block BETWEEN ? AND ?',
            (m['start_block'],m['end_block'])).fetchone()[0]
        if raw_count!=len(events): raise ValueError('Raw/processed event counts differ')
        for protocol in CONTRACTS:
            intervals=conn.execute('SELECT start,end FROM coverage WHERE protocol=? ORDER BY start',(protocol,)).fetchall()
            next_block=m['start_block']
            for start,end in intervals:
                if start!=next_block: raise ValueError(f'Gap/overlap in coverage: {protocol}')
                next_block=end+1
            if next_block!=m['end_block']+1: raise ValueError(f'Incomplete coverage: {protocol}')
    summary=Counter(e['protocol'] for e in events)
    validations=read(run/'processed/position_validation.csv') if (run/'processed/position_validation.csv').exists() else []
    valued=read(run/'processed/aave_liquidations_valued.csv') if (run/'processed/aave_liquidations_valued.csv').exists() else []
    if valued and len(valued)!=sum(e['event_type']=='LiquidationCall' for e in events):
        raise ValueError('Missing Aave liquidation valuations')
    for v in validations:
        if v['status']=='passed' and Decimal(v['max_relative_error'])>Decimal(v['relative_tolerance']):
            raise ValueError('Invalid validation status')
    for group in read(run/'processed/rq2_concentration.csv') if (run/'processed/rq2_concentration.csv').exists() else []:
        for field in ('top_1_share','top_10_share','hhi'):
            if group[field] and not 0<=Decimal(group[field])<=1: raise ValueError('Concentration outside [0,1]')
    report=['# Báo cáo kiểm tra dữ liệu', '',
        f"Khoảng thời gian UTC: {m['settings']['start']} đến {m['settings']['end']} (không gồm đầu cuối).",
        f"Khoảng block: {m['start_block']}–{m['end_block']}.", '',
        '| Giao thức / thị trường | Sự kiện đã chọn |','|---|---:|']
    report += [f'| {p} | {summary[p]:,} |' for p in CONTRACTS]
    report += ['',f'Tổng: **{len(events):,} sự kiện**, không có khóa trùng, khớp SQLite gốc, coverage liên tục cho từng hợp đồng.',
        f"Kiểm chứng vị thế Aave: {dict(Counter(v['status'] for v in validations))}.",
        f'Số sự kiện thanh lý Aave được định giá: {len(valued)}.',
        f"Tổng nợ Aave được trả qua thanh lý trong cửa sổ: {sum((Decimal(v['debt_repaid_usd']) for v in valued),Decimal(0)):,.2f} USD (oracle cuối block).",'',
        '## Phạm vi sử dụng',
        '- Đây là dataset pilot và mẫu vị thế, không phải toàn bộ lịch sử hoặc toàn bộ người vay.',
        '- Snapshot chọn ví từ sự kiện sau thời điểm snapshot: không dùng trực tiếp để suy luận dự báo ngoài mẫu.',
        '- RQ1: stress tĩnh chỉ trên mẫu đã kiểm chứng, chưa mô phỏng thanh lý thực thi.',
        '- RQ2: có giá trị thanh lý Aave; chưa tổng hợp volume USD xuyên giao thức.',
        '- RQ3: motif vay–gửi và transfers chỉ là ứng viên, chưa xác nhận recursive leverage.',
        '- RQ4: có panel số sự kiện và giá oracle theo giờ; cần lịch sử dài hơn và mô hình kiểm soát.',
        '- RQ5: có hoạt động ví–thị trường; chưa có mạng exposure đầy đủ hoặc kết luận nhân quả.',
        '- Xem README.md để mở rộng thời gian, chọn ví và hiểu quy tắc dữ liệu.']
    (run/'DATA_REPORT.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    print(json.dumps({'status':'verified','events':len(events),'by_protocol':dict(summary),
        'aave_valued_liquidations':len(valued),'snapshot_validation':dict(Counter(v['status'] for v in validations))},ensure_ascii=True))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('run_id',nargs='?',default='stress_20250203_smoke')
    args=parser.parse_args()
    if not all(c.isalnum() or c in '_-' for c in args.run_id): parser.error('Invalid run id')
    validate(ROOT/'data/runs'/args.run_id)
