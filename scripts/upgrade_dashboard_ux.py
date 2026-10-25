"""Reorganize existing views without dropping model controls or result identifiers."""
from pathlib import Path
import re
root=Path(__file__).resolve().parents[1];web=root/'defi_live/web'
p=web/'research.html';s=p.read_text(encoding='utf8')
if 'data-research-tab=' in s:raise SystemExit('Research UX already organized; do not apply twice')
sections=re.findall(r'<section\b.*?</section>',s,re.S)
assert len(sections)==9
prefix=s[:s.index(sections[0])]+sections[0];suffix=s[s.index(sections[-1])+len(sections[-1]):]
source=sections[1];cut=source.index('<h3>H3 ·')
h2=source[:cut]+'</section>'
h2=h2.replace('<h2>Kỳ chính mới · Hết Q1/2026</h2>','<h2>H2 · Mức tập trung thanh lý theo ví</h2><p class="ux-explainer">Chọn cùng kỳ và collateral trước khi so protocol. Coverage cho biết bao nhiêu sự kiện có giá đủ mới; HHI chuẩn hóa cao hơn nghĩa là giá trị tập trung hơn trong mẫu đang chọn.</p>')
h3='<section id="conditional"><h2>H3 · Nhịp thanh lý có dự báo được không?</h2><p class="ux-explainer">So các mô hình trên cùng mẫu test. Log-score ít âm hơn là tốt hơn; expected/observed gần 1 là cân bằng tổng count. Residual chưa đạt nghĩa là mô hình chưa được duyệt làm forecast.</p>'+source[cut:]
toolbar='<div class="panel-toolbar"><a href="/start">← Xem 5 mục tiêu</a><button class="ux-button" id="research-reload">Đọc lại kết quả</button></div>'
tabs='<nav class="research-tabs" role="tablist" aria-label="Nội dung nghiên cứu">'
for key,label in [('h1','H1 · Stress vị thế'),('h2','H2 · Tập trung'),('h3','H3 · Nhịp thanh lý'),('cascade','Cascade'),('archive','Kết quả trước')]:
    tabs+=f'<button role="tab" id="tab-{key}" data-research-tab="{key}" aria-controls="panel-{key}" aria-selected="false" tabindex="-1">{label}</button>'
tabs+='</nav>'
def panel(key,body):return f'<div role="tabpanel" id="panel-{key}" aria-labelledby="tab-{key}" hidden>{body}</div>'
reset=lambda key:f'<button class="ux-button" data-reset-panel="panel-{key}">Đặt lại bộ lọc</button>'
h1=sections[3].replace('<h2>H1 · Snapshot cuối quý trong kỳ chính</h2>','<h2>H1 · Vị thế vay phản ứng thế nào khi giá giảm?</h2><p class="ux-explainer">Bắt đầu bằng quý, chọn ETH/BTC và mapping. Đồ thị cho biết nợ đủ điều kiện thanh lý theo shock, chưa phải lượng thanh lý đã thực thi.</p>'+reset('h1'))
h2=h2.replace('<p id="sources-status"',reset('h2')+'<p id="sources-status"',1)
legacy=''
for index,title in [(2,'Lượt sửa trước · sensitivity và matching'),(4,'Concentration theo cách đo cũ'),(5,'Clustering và negative binomial trước nâng cấp'),(6,'V2 · coverage và context theo quý'),(8,'Tài liệu tham khảo và kiểm tra phiên bản')]:
    legacy+=f'<details class="ux-archive"><summary>{title}</summary>{sections[index]}</details>'
legacy='<p class="ux-explainer">Các kết quả này giữ nguyên để đối chiếu. Một số bảng dùng kỳ dài hơn đến Q3/2026 và phương pháp trước nâng cấp. Không so trực tiếp với kỳ chính đến Q1/2026 nếu khác sample.</p>'+legacy
cascade=sections[6] if 'Cascade · Snapshot' in sections[6] else sections[7]
# Literature is the last section; identify cascade rather than relying on incidental order.
cascade=next(x for x in sections if '<h2>Cascade · Snapshot' in x)
cascade=cascade.replace('<h2>Cascade · Snapshot trước sự kiện và phản hồi giá</h2>','<h2>Cascade · Điều gì xảy ra sau các vòng thanh lý?</h2><p class="ux-explainer">Chọn ngày có snapshot đầy đủ, mức shock và phản hồi giá. So có/không feedback trên cùng ngày và giả định. Các bảng dưới là mô phỏng đã tính, chưa phải cascade được hiệu chỉnh toàn bộ.</p>'+reset('cascade'))
prefix=prefix.replace('Nghiên cứu H1 · H2 · H3.','Khám phá rủi ro DeFi lending')
glossary='<details class="ux-glossary"><summary>Chưa quen thuật ngữ? Xem cách đọc nhanh</summary><dl><dt>Eligible debt</dt><dd>Nợ ở vị thế đủ điều kiện thanh lý theo kịch bản, chưa phải nợ đã thanh lý.</dd><dt>Common support</dt><dd>Cùng một tập sự kiện hợp lệ dùng để so các cách đo hoặc mô hình.</dd><dt>HHI chuẩn hóa</dt><dd>Chỉ số tập trung theo share, có điều chỉnh N. Vẫn phải xem cỡ mẫu và coverage.</dd><dt>Residual chưa đạt</dt><dd>Mô hình còn sai lệch hoặc phụ thuộc chưa giải thích; không đồng nghĩa có causal contagion.</dd></dl></details>'
s=prefix+toolbar+tabs+panel('h1',h1)+panel('h2',h2)+panel('h3',h3)+panel('cascade',cascade)+panel('archive',legacy)+glossary+suffix
# All existing result targets and filters must remain unique and present.
before_ids=re.findall(r'\bid="([^"]+)"',p.read_text(encoding='utf8'));after_ids=re.findall(r'\bid="([^"]+)"',s)
assert set(before_ids)<=set(after_ids),(set(before_ids)-set(after_ids))
assert len(after_ids)==len(set(after_ids)),[x for x in after_ids if after_ids.count(x)>1]
p.write_text(s,encoding='utf8')
for name in ['research.html','lab.html','index.html','validation.html','guide.html']:
    p=web/name;s=p.read_text(encoding='utf8')
    s=s.replace('</head>','<link rel="stylesheet" href="/ux.css"></head>',1)
    s=s.replace('</body>','<script src="/ux.js"></script></body>',1)
    p.write_text(s,encoding='utf8')
print('Reorganized research tabs; preserved',len(before_ids),'existing result/control IDs')
