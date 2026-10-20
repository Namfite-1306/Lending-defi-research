from pathlib import Path
import json,csv,html
from decimal import Decimal as D
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,KeepTogether
from reportlab.lib.pagesizes import A4

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'data/runs/stress_20250203_smoke'
OUT=ROOT/'output/pdf/Bao_cao_ra_soat_du_lieu_DeFi_2026-10-18.pdf'
OUT.parent.mkdir(parents=True,exist_ok=True)
a=json.loads((RUN/'audit/audit_results.json').read_text(encoding='utf-8'))
assert a['all_executed_checks_passed'] and len(a['checks'])==15
pdfmetrics.registerFont(TTFont('ArialVN','C:/Windows/Fonts/arial.ttf'))
pdfmetrics.registerFont(TTFont('ArialVNB','C:/Windows/Fonts/arialbd.ttf'))
pdfmetrics.registerFontFamily('ArialVN',normal='ArialVN',bold='ArialVNB',italic='ArialVN',boldItalic='ArialVNB')
NAVY=colors.HexColor('#17324D'); TEAL=colors.HexColor('#126A73'); GRAY=colors.HexColor('#526477'); LIGHT=colors.HexColor('#F0F4F8')
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyVN',fontName='ArialVN',fontSize=10,leading=15,spaceAfter=7,textColor=NAVY))
styles.add(ParagraphStyle(name='SmallVN',fontName='ArialVN',fontSize=8.3,leading=11.5,textColor=NAVY))
styles.add(ParagraphStyle(name='HeadVN',fontName='ArialVNB',fontSize=18,leading=24,spaceAfter=13,textColor=NAVY))
styles.add(ParagraphStyle(name='SubVN',fontName='ArialVNB',fontSize=11.3,leading=16,spaceBefore=10,spaceAfter=7,textColor=TEAL))
styles.add(ParagraphStyle(name='HeaderVN',fontName='ArialVNB',fontSize=8.5,leading=11.5,textColor=colors.white))
styles.add(ParagraphStyle(name='NoteVN',fontName='ArialVN',fontSize=8.5,leading=12,spaceAfter=7,textColor=GRAY))
story=[]
def p(text,style='BodyVN'):return Paragraph(text,styles[style])
def add(text,style='BodyVN'):story.append(p(text,style))
def title(n,name):add(f'{n:02d} / {name}','HeadVN')
def sub(text):add(text,'SubVN')
def table(headers,rows,widths):
    data=[[p(html.escape(str(c)),'HeaderVN') for c in headers]]
    data += [[p(html.escape(str(c)),'SmallVN') for c in row] for row in rows]
    t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7),
        ('BOTTOMPADDING',(0,0),(-1,-1),7),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,LIGHT]),
        ('LINEBELOW',(0,0),(-1,0),.6,NAVY)]))
    story.append(t);story.append(Spacer(1,8))
def page():story.append(PageBreak())
W=A4[0]-88

title(1,'Kết luận rà soát dữ liệu')
add('DeFi Lending Liquidation Stress Test','SubVN')
add('Ngày rà soát: <b>18/10/2026</b> | Run: <b>stress_20250203_smoke</b>','NoteVN')
add('<b>Kết luận:</b> dữ liệu pilot đạt các kiểm tra kỹ thuật đã thực hiện và dùng được để kiểm tra pipeline, mô tả thanh lý Aave trong cửa sổ quan sát. <b>Chưa đủ để kết luận RQ1-RQ7 cho toàn thị trường.</b>')
table(['Phạm vi','Giá trị đã xác minh'],[
    ['Thời gian dữ liệu','03/02/2025, 00:00-03:00 UTC; tương đương 07:00-10:00 giờ Việt Nam. Khoảng [start, end).'],
    ['Ethereum mainnet','892 block trong khoảng 21.762.265-21.763.156; snapshot tại block 21.762.264.'],
    ['Sự kiện được chọn','4.294 logs; 2.484 giao dịch phân biệt; 715 block có ít nhất một sự kiện được chọn.'],
    ['Vị thế Aave lấy mẫu','5 tài khoản, 14 dòng tài khoản-token; cả 5 đối chiếu đạt.'],
    ['Hồ sơ đã rà soát','14 CSV, SQLite gốc, manifest, cache RPC, định nghĩa hợp đồng và mã xử lý.'],
    ['Kiểm tra','15/15 nhóm kiểm tra dữ liệu đạt; 9/9 unit tests đạt.']
],[135,W-135])
sub('Điểm quan trọng nhất')
add('1. <b>Đã sửa một lỗi thời lượng theo giờ:</b> giờ đầu bị ghi 3.589 giây và partial_hour=True. Sau sửa là 3.600 giây, partial_hour=False, phù hợp khoảng truy vấn đầy đủ. Số sự kiện không đổi.')
add('2. <b>Mẫu vị thế có thiên lệch lựa chọn:</b> 5 ví được chọn từ các sự kiện xảy ra trong cửa sổ sau snapshot, ưu tiên ví bị thanh lý. Không dùng mẫu này để ước lượng xác suất thanh lý của toàn bộ người vay.')
add('3. <b>Đủ cho mô tả, chưa đủ cho suy luận hệ thống:</b> dữ liệu 3 giờ chưa đủ kiểm định Hawkes ổn định; chưa có vòng lặp đòn bẩy xác nhận, mạng exposure, thanh khoản DEX hoặc mô phỏng cascade.')
add('Đây là tự rà soát kỹ thuật của pipeline và dữ liệu, không phải kiểm toán độc lập. Kết quả đạt chỉ áp dụng cho các phép kiểm tra và phạm vi ghi trong báo cáo.','NoteVN')
page()

title(2,'Nguồn và cấu trúc dữ liệu')
add('Các hợp đồng được chọn: Aave V3 Ethereum Core, Compound III Ethereum USDC Comet và Morpho Blue Ethereum. Không bao phủ mọi thị trường hoặc phiên bản cùng thương hiệu.')
meanings={
 'events.csv':'Sự kiện đã chuẩn hóa, có thứ tự thực thi',
 'liquidations.csv':'Logs liên quan thanh lý, nhiều loại đo lường',
 'aave_liquidations_valued.csv':'Nợ Aave được trả, định giá oracle cuối block',
 'aave_reserves.csv':'Metadata và tham số 38 tài sản tại snapshot',
 'positions.csv':'Số dư theo tài khoản-token tại snapshot',
 'position_validation.csv':'Đối chiếu tổng thế chấp, nợ và HF',
 'blocks.csv':'Thời gian/hash các block có sự kiện',
 'hourly_counts.csv':'Panel 3 giao thức x 3 giờ, gồm giá trị 0',
 'oracle_prices_hourly.csv':'4 mốc giá x WETH, WBTC, USDC',
 'account_market_activity.csv':'Hoạt động tài khoản-thị trường; không phải exposure',
 'rq1_sample_stress.csv':'36 kịch bản cú sốc, chỉ áp dụng mẫu đã đạt',
 'rq2_concentration.csv':'Top-1, Top-10 và HHI, bốn chiều nhóm',
 'rq3_borrow_supply_candidates.csv':'Motif vay rồi gửi, chưa xác nhận vòng lặp',
 'token_transfers_sample.csv':'ERC20 transfers trong 20 giao dịch lấy mẫu'}
inv={r['file']:r for r in a['file_inventory']}
table(['File CSV','Dòng','Ý nghĩa'],[[name,f"{inv[name]['rows']:,}",meaning] for name,meaning in meanings.items()],[187,43,W-230])
sub('Quy tắc khóa và đơn vị')
add('Khóa sự kiện: <b>(chain_id, tx_hash, log_index)</b>. Thứ tự thực thi: block_number, transaction_index, log_index. Số nguyên blockchain lưu dạng chuỗi; số tiền quy đổi tính bằng Decimal.')
add('Địa chỉ, market_id và các trường *_raw phải được giữ dạng chuỗi khi nhập Excel/Sheets hoặc pandas. Giá USD là giá oracle theo block, không phải giá khớp lệnh trên DEX. Không cộng số token khác nhau trước quy đổi.')
add('Lưu trữ gốc: raw.sqlite và cache RPC. Manifest giữ SHA-256 cho 14 CSV và 5 file định nghĩa hợp đồng. Hash xác nhận file không đổi; không tự chứng minh nguồn RPC là đúng hoặc đầy đủ.','NoteVN')
page()

title(3,'Kết quả kiểm tra và đối chiếu')
check_labels={
 'file_hashes':('14 CSV khớp SHA-256','Không thấy file bị thay đổi ngoài manifest.'),
 'source_hashes':('5 định nghĩa hợp đồng khớp hash','Kiểm soát bản nguồn lưu cục bộ.'),
 'unique_events':('4.294 khóa sự kiện phân biệt','Không phát hiện logs trùng.'),
 'execution_order':('Thứ tự sự kiện đúng','Theo block, transaction index, log index.'),
 'time_bounds':('Toàn bộ logs trong [00:00,03:00)','Không có dòng ngoài cửa sổ.'),
 'required_identifiers':('Không thiếu khóa bắt buộc','Protocol, contract, block, tx, log, market ID.'),
 'raw_decode_replay':('Giải mã lại 4.294 logs khớp','Đối chiếu bản raw với decoded lưu trong SQLite.'),
 'coverage_ledger':('Coverage liên tục cho 3 hợp đồng','Không có khoảng trống trong sổ crawl đã ghi.'),
 'valuation_arithmetic':('706 dòng định giá tính lại khớp','Đối chiếu lượng, decimals và giá từ cache gốc.'),
 'concentration_recalculation':('Top-k và HHI tính lại khớp','Cả bốn chiều nhóm đều đạt.'),
 'stress_recalculation':('36 kịch bản tính lại khớp','Parse boolean đúng; shock cả thế chấp và nợ.'),
 'hourly_count_reconciliation':('Panel khớp sự kiện thanh lý','706 Aave, 42 Compound, 29 Morpho.'),
 'fresh_rpc_receipts':('6/6 logs mẫu khớp receipt mới','Hai sự kiện mỗi giao thức, đầu/cuối theo thời gian.'),
 'fresh_rpc_window_boundaries':('4 block biên khớp thời gian','Start-1, start, end, end+1.'),
 'fresh_rpc_snapshot_hf':('5/5 HF khớp lần đọc mới','Đọc lại hợp đồng tại cùng block snapshot.')}
table(['Phép kiểm tra','Kết quả / bằng chứng'],[[check_labels[c['check']][0],('Đạt. ' if c['passed'] else 'Không đạt. ')+check_labels[c['check']][1]] for c in a['checks']],[215,W-215])
add('Các lần đọc mới bỏ qua cache, dùng Flashbots/Blast RPC dự phòng. Đây là đối chiếu mẫu qua RPC, không phải kiểm chứng mật mã toàn chuỗi hoặc tái crawl độc lập toàn bộ cửa sổ. Coverage chỉ khẳng định các truy vấn đã hoàn thành theo sổ ghi; không loại trừ tuyệt đối việc nhà cung cấp trả thiếu.','NoteVN')
max_err=max(D(v['max_relative_error']) for v in a['validation'])
add(f'Sai số đối chiếu lớn nhất trong 5 tài khoản: <b>{max_err:.3E}</b>, thấp hơn ngưỡng 1E-4. Đây là sai số chuẩn hóa theo max(giá trị tham chiếu, 1), không phải cam kết chính xác cho tất cả ví/E-mode.','NoteVN')
page()

title(4,'Những gì dữ liệu đang cho thấy')
table(['Giao thức','Logs đã chọn','Sự kiện thanh lý dùng đếm'],[
 ['Aave V3','3.572','706 LiquidationCall'],['Compound III USDC','472','42 AbsorbDebt'],['Morpho Blue','250','29 Liquidate']
],[150,110,W-260])
add('<b>955 dòng</b> trong liquidations.csv bao gồm cả 66 AbsorbCollateral và 112 BuyCollateral của Compound. Không được diễn giải 955 dòng này là 955 khoản vay bị thanh lý hoặc cộng thành một volume chung.')
sub('Thanh lý theo giờ UTC')
table(['Giờ ngày 03/02/2025','Aave','Compound','Morpho'],[
 ['00:00-01:00',22,0,3],['01:00-02:00',351,27,13],['02:00-03:00',333,15,13]
],[W-210,70,70,70])
add('Sự kiện tập trung mạnh hơn ở hai giờ sau. Đây chỉ là mô tả trong một cửa sổ stress; chưa chứng minh self-excitation hoặc giao thức này gây thanh lý ở giao thức khác.')
sub('Giá trị và mức tập trung trên Aave')
add(f"Tổng nợ được trả qua thanh lý: <b>{D(a['total_aave_repaid_usd']):,.2f} USD</b>, từ 706 logs thuộc {a['aave_liquidation_transactions']} giao dịch. Không phải tổn thất người vay, nợ xấu hay giá trị tài sản đã bán trên DEX.")
labels={'borrower':'Ví người vay','liquidator':'Địa chỉ bên thanh lý','collateral_token':'Token thế chấp','debt_token':'Token nợ'}
table(['Chiều nhóm','Số nhóm','Top-1','Top-10','HHI (0-1)'],[
 [labels[r['dimension']],r['categories'],f"{D(r['top_1_share']):.2%}",f"{D(r['top_10_share']):.2%}",f"{D(r['hhi']):.4f}"] for r in a['concentration']
],[157,55,75,75,W-362])
add('Tỷ trọng tính theo nợ USD được trả. Một thực thể có thể dùng nhiều địa chỉ, và một địa chỉ hợp đồng có thể phục vụ nhiều thực thể. Mức tập trung địa chỉ không đồng nghĩa mức tập trung chủ sở hữu.','NoteVN')
add('Giá oracle WETH giảm từ 2.856,23 xuống 2.489,54 USD giữa hai biên lấy mẫu. Chỉ là giá oracle tại các mốc, không mô tả đầy đủ đường giá trong giờ.','NoteVN')
page()

title(5,'Phát hiện, lỗi đã sửa và giới hạn')
sub('Lỗi kỹ thuật đã sửa trong lần rà soát')
add('Chương trình trước đây lấy timestamp block đầu tiên (00:00:11 UTC) làm mốc bắt đầu tính exposure. Điều đó gắn nhầm giờ đầu là thiếu 11 giây, dù truy vấn logs đã bao phủ từ 00:00:00. Đã đổi sang khoảng thời gian người dùng yêu cầu.')
table(['Chỉ tiêu giờ đầu','Trước sửa','Sau sửa'],[
 ['observed_seconds (mỗi giao thức)','3.589','3.600'],['partial_hour','True','False'],['Số sự kiện','22 / 0 / 3','22 / 0 / 3, không đổi']
],[W-200,100,100])
add('Đã thêm 2 kiểm thử hồi quy: cửa sổ đủ giờ và cửa sổ thực sự chỉ có nửa giờ. Tổng cộng 9 kiểm thử đều đạt. Đã lưu manifest và panel trước sửa trong thư mục audit; dữ liệu raw và các CSV còn lại không thay đổi nội dung.')
sub('Giới hạn còn tồn tại')
table(['Mức','Phát hiện và ảnh hưởng'],[
 ['Cao','5 ví từ 1.206 địa chỉ Aave phát hiện qua các hành động được chọn. Mẫu ưu tiên ví bị thanh lý rồi sắp xếp địa chỉ; có selection/look-ahead bias. Không đại diện toàn bộ người vay.'],
 ['Cao','Chỉ 3 giờ và 3 quan sát giờ mỗi giao thức. Không đủ để ước lượng/kiểm định Hawkes đáng tin hoặc đánh giá nhiều chế độ thị trường.'],
 ['Cao','Morpho: 29/29 logs thanh lý chưa nối loanToken/collateralToken. Compound: trường debt_token trống ở 220 logs liên quan; 42 AbsorbDebt không có collateral_token ở cùng dòng theo thiết kế. Chưa thể tổng hợp volume USD xuyên giao thức.'],
 ['Cao','6 motif vay-rồi-gửi chưa được xác nhận là recursive leverage. Chỉ có 87 transfers của 20 giao dịch lấy mẫu; thiếu lịch sử, swaps, traces và đối chứng.'],
 ['Cao','Chưa có exposure theo vị thế Compound/Morpho, thanh khoản DEX, giá thực thi hoặc bộ mô phỏng cascade. Chưa đủ cho RQ5-RQ7.'],
 ['Vừa','Stress chỉ shock WETH/WBTC, giữ giá token khác cố định. E-mode chưa được xử lý; không áp dụng ngầm cho các token phái sinh ETH/BTC.'],
 ['Vừa','Định giá cuối block có thể khác giá trước giao dịch/giá bán. Manifest ghi request của lần chạy lại, không phải toàn bộ crawl; chưa lưu endpoint và commit nguồn theo từng lần lấy.']
],[48,W-48])
page()

title(6,'Mức sẵn sàng và bước tiếp theo')
table(['RQ / người phụ trách','Đã có','Cần bổ sung trước kết luận'],[
 ['RQ1 / Người 2','Snapshot 5 ví đã đối chiếu; 36 stress tĩnh.','Universe borrower tại snapshot độc lập với kết quả tương lai; thêm snapshot và shock tài sản phái sinh.'],
 ['RQ2 / Người 4','Top-k/HHI Aave theo giá trị trong cửa sổ.','Lịch sử rộng hơn; nối token và định giá Compound/Morpho; quy tắc nhóm địa chỉ.'],
 ['RQ3 / Người 3','6 motif ứng viên; 20 receipts, 87 transfers.','Truy vết nguồn vốn, swap và lịch sử vòng lặp; mẫu có/không vòng lặp; kiểm chứng nhãn.'],
 ['RQ4 / Người 2','Panel 9 dòng và 12 điểm giá token.','Chuỗi sự kiện liên tục dài hơn; kiểm soát giá/gas/oracle, chẩn đoán và kiểm định ngoài mẫu.'],
 ['RQ5 / Người 4','1.450 dòng hoạt động ví-thị trường.','Dựng số dư/exposure thật; kênh bán tài sản và đối chứng cú sốc chung.'],
 ['RQ6 / Người 5','Dữ liệu sự kiện và stress tĩnh nền.','Độ sâu DEX, trượt giá, lượng bán, tác động giá, cascade và nợ xấu.'],
 ['RQ7 / Người 6','Tham số Aave tại một snapshot.','Bộ mô phỏng có giới hạn/phần thưởng thanh lý, chi phí và phản ứng bên thanh lý.']
],[104,158,W-262])
sub('Thứ tự xử lý đề xuất')
add('<b>1. Người 1:</b> chốt giai đoạn nghiên cứu, mở rộng lịch sử và dựng borrower universe đúng thời điểm; nối metadata Morpho/Compound. Giữ nguyên dataset pilot làm kiểm thử hồi quy.')
add('<b>2. Người 2-4:</b> thống nhất đơn vị quan sát, quy tắc nhận diện vòng lặp và mạng exposure trước khi chạy mô hình. Không dùng tài khoản phát hiện sau snapshot làm mẫu dự báo nếu chưa điều chỉnh thiết kế.')
add('<b>3. Người 1 cùng Người 5-6:</b> bổ sung thanh khoản và quy tắc thực thi; tách dư nợ đủ điều kiện, nợ thực trả, thế chấp thu giữ, tài sản bán và nợ xấu.')
sub('Hồ sơ và cách tái kiểm tra')
add('Thư mục dữ liệu: <b>defi-research/data/runs/stress_20250203_smoke/</b>. Chi tiết từng phép kiểm tra và các giao dịch đối chiếu nằm trong <b>audit/audit_results.json</b>. Hướng dẫn pipeline nằm trong README.md.','SmallVN')
add('Chạy trong thư mục defi-research:<br/><b>python -m unittest discover -s tests -v</b><br/><b>python -m defi_data.audit_qa --live</b>','SmallVN')
add('Nguồn đối chiếu: SQLite raw, 14 CSV, manifest và cache của cùng run; các định nghĩa IPool.sol, CometMainInterface.sol, EventsLib.sol trong data/sources; lần đọc RPC mới qua rpc.flashbots.net và eth-mainnet.public.blastapi.io. Không sử dụng dữ liệu giả làm kết quả trong báo cáo.','NoteVN')

def footer(canvas,doc):
    canvas.saveState();canvas.setStrokeColor(colors.HexColor('#D7E1EB'));canvas.line(44,43,A4[0]-44,43)
    canvas.setFont('ArialVN',8);canvas.setFillColor(GRAY)
    canvas.drawString(44,29,'CRYPTO FINANCE LAB  |  Rà soát dữ liệu pilot  |  18/10/2026')
    canvas.drawRightString(A4[0]-44,29,str(doc.page));canvas.restoreState()
doc=SimpleDocTemplate(str(OUT),pagesize=A4,leftMargin=44,rightMargin=44,topMargin=43,bottomMargin=57,
    title='Báo cáo rà soát dữ liệu DeFi - 18/10/2026',author='Crypto Finance Lab')
doc.build(story,onFirstPage=footer,onLaterPages=footer)
print(OUT)
