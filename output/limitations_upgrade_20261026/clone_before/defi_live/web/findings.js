/* Pure summaries of the loaded evidence. No hardcoded empirical result values. */
(function(root){'use strict';
const num=v=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v))?Number(v):null;
const fmt=(v,d=2)=>num(v)===null?'—':Number(v).toLocaleString('vi-VN',{minimumFractionDigits:d,maximumFractionDigits:d});
const pct=v=>num(v)===null?'—':fmt(Number(v)*100)+'%';
const range=xs=>{const a=xs.map(num).filter(x=>x!==null);return a.length?[Math.min(...a),Math.max(...a)]:null};
const labels={aave_v3:'Aave V3',compound_v3_usdc:'Compound III',morpho_blue:'Morpho Blue'};
const missing=()=>({headline:'Chưa đủ dữ liệu để tóm tắt finding ở lựa chọn này.',metrics:[],scope:'Đổi bộ lọc hoặc kiểm tra coverage.',limit:'Bảng trống không đồng nghĩa không có rủi ro.'});
function h1(data,o={}){
  const cutoff=data.source_stage?.manifest?.primary_scope?.last_quarter;
  const match=r=>r.scenario===o.scenario&&r.mapping===o.mapping&&(!cutoff||r.quarter<=cutoff);
  const rows=(data.tables?.h1_curves||[]).filter(match),at20=rows.filter(r=>Math.abs(Number(r.shock)-.2)<1e-9);
  const knots=(data.tables?.h1_breakpoints||[]).filter(r=>match(r)&&Number(r.grid_step_percent)===1),spread=range(at20.map(r=>r.eligible_debt_share));
  if(!spread)return missing();
  const k=range(knots.map(r=>r.share_knot));
  const selected=at20.find(r=>r.quarter===o.quarter);
  return {headline:'Cùng cú sốc 20%, tỷ trọng nợ đủ điều kiện thanh lý thay đổi từ '+pct(spread[0])+' đến '+pct(spread[1])+' giữa các quý.',
    metrics:[['Quý được đối chiếu',String(new Set(at20.map(r=>r.quarter)).size)],['Khoảng share-knot',k?pct(k[0])+'–'+pct(k[1]):'—'],[o.quarter+' · shock 20%',pct(selected?.eligible_debt_share)]],
    scope:'Tổng hợp các quý trong kỳ chính · '+o.scenario+' · '+o.mapping+'. Thẻ tổng hợp nhiều quý; bảng dưới giữ quý đang chọn.',
    limit:'Knot là điểm gãy mô tả trên lưới stress; eligible debt là dư nợ có thể bị thanh lý, không phải volume thực thi hoặc một ngưỡng cascade chung.'};
}
function h2(data,o={}){
  const rows=o.rows||[],large=rows.filter(r=>Number(r.entities)>=30&&num(r.top1_percent_share)!==null);
  if(!large.length)return {...missing(),scope:'Lựa chọn hiện tại chưa có protocol với ít nhất 30 ví; không xếp hạng mẫu nhỏ.'};
  const spread=range(large.map(r=>r.top1_percent_share));
  const small=rows.filter(r=>Number(r.entities)<30).map(r=>labels[r.protocol]||r.protocol);
  return {headline:'Top 1% ví chiếm '+pct(spread[0])+'–'+pct(spread[1])+' tổng trọng số trong các protocol có ít nhất 30 ví.',
    metrics:large.map(r=>[labels[r.protocol]||r.protocol,'Top 1%: '+pct(r.top1_percent_share)+' · HHI*: '+fmt(r.hhi_normalized,3)]),
    scope:o.scope+' · '+large.map(r=>(labels[r.protocol]||r.protocol)+': '+r.entities+' ví / '+r.priced_or_selected_events+' sự kiện').join('; ')+'.',
    limit:(small.length?small.join(', ')+' có mẫu nhỏ, không dùng để xếp hạng. ':'')+'Trọng số theo đúng bộ lọc đang chọn; count khác USD. Địa chỉ không đồng nghĩa chủ sở hữu. Chênh lệch concentration chưa chứng minh tác động nhân quả của thiết kế giao thức.'};
}
function h3(data){
  const s=data.source_stage||{},name=s.manifest?.h3?.selected_by_validation;
  const selected=(s.models||[]).find(r=>r.model===name),base=(s.models||[]).find(r=>r.model==='activity');
  if(!selected)return missing();
  const same=base&&Number(base.test_bins)===Number(selected.test_bins)&&Number(base.test_events)===Number(selected.test_events);
  const gain=same?Number(selected.test_loglik)-Number(base.test_loglik):null;
  const residual=s.residuals?.[name]||{},ks=num(residual.uniform_null_KS_p),acf=num(residual.uniform_null_ACF_p);
  const failed=(ks!==null&&ks<.05)||(acf!==null&&acf<.05);
  const ratio=num(selected.expected_observed_ratio);
  return {headline:(gain!==null&&gain>0?'Lịch sử thanh lý cải thiện log-score ngoài mẫu':'Đọc thông tin dự báo trên cùng mẫu test')+(failed?', nhưng mô hình chưa đạt calibration.':'.'),
    metrics:[['Log-score so với activity',gain===null?'Không cùng support':(gain>=0?'+':'')+fmt(gain)],['Kỳ vọng / quan sát',fmt(ratio,3)],['PIT KS / ACF p',fmt(ks,3)+' / '+fmt(acf,3)]],
    scope:'Validation chọn '+name+' · '+fmt(selected.test_bins,0)+' bin / '+fmt(selected.test_events,0)+' sự kiện test. '+(ratio!==null?'Tổng count dự báo '+(ratio>=1?'cao hơn ':'thấp hơn ')+fmt(Math.abs(ratio-1)*100,1)+'% so với quan sát.':''),
    limit:'Kết quả có tính khám phá vì test đã được xem. Hurdle không phải structural Hawkes; thông tin dự báo không chứng minh “thanh lý gây ra thanh lý”. Chưa dùng như dự báo real-time đã được kiểm chứng.'};
}
function cascade(data,o={}){
  const r=(data.v2?.cascade_scenarios||[]).find(r=>r.event_date===o.date&&Math.abs(Number(r.shock)-Number(o.shock))<1e-9);
  if(!r)return missing();
  return {headline:'Trong mô phỏng đã chọn, nợ được trả khi có phản hồi giá bằng '+fmt(r.amplification,3)+' lần đối chứng không phản hồi.',
    metrics:[['Có phản hồi giá',fmt(Number(r.with_feedback_repaid)/1e6)+' triệu USD'],['Không phản hồi giá',fmt(Number(r.without_feedback_repaid)/1e6)+' triệu USD'],['Chênh lệch',fmt((Number(r.with_feedback_repaid)-Number(r.without_feedback_repaid))/1e6)+' triệu USD']],
    scope:'Snapshot sự kiện '+o.date+' · shock joint '+pct(o.shock)+' · engine pair/route. Hai trường hợp cùng snapshot và giả định tài chính.',
    limit:'Mô phỏng chưa được hiệu chỉnh và kiểm chứng đầu cuối. Đây là nợ được trả trong engine, không phải nợ xấu quan sát. Không ghép tỷ số với engine stylized RQ6 ở trang 7 RQ.'};
}
const api={h1,h2,h3,cascade,missing};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.ResearchFindings=api;
})(typeof window==='undefined'?this:window);
