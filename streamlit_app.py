"""Local research dashboard. Run with: python -m streamlit run streamlit_app.py."""
from datetime import datetime,timezone
from pathlib import Path
import json

import altair as alt
import pandas as pd
import streamlit as st

from defi_models.core import ROOT
from defi_models.dashboard_data import (
    aggregate_counts,audit_status,decay_response,discover_runs,fingerprint,
    read_json,read_run,stress_curves,stress_view,validated_portfolio,
)

st.set_page_config(page_title='DeFi · Giả định & rủi ro',page_icon=':material/query_stats:',layout='wide')

COLORS=['#087F8C','#4268AE','#D28A36']
SECTIONS=['Tổng quan','RQ1 · Stress vị thế','RQ4 · Nhịp thanh lý','Giả định & dữ liệu']


@st.cache_data(ttl=300,max_entries=20,show_spinner=False)
def cached_run(path,rq,signature):
    return read_run(Path(path),rq)


@st.cache_data(ttl=300,max_entries=20,show_spinner=False)
def cached_curves(path,derivatives,shift,signature):
    p,_=validated_portfolio(Path(path),derivatives)
    return stress_curves(p,shift)


def load_selected(path,rq):
    files=[path/'manifest.json',path/f'rq{rq}/summary.json']
    names=['stress_curve.csv','factor_mapping.csv'] if rq==1 else ['hourly_counts.csv','hawkes_candidates.csv']
    files.extend(path/f'rq{rq}'/name for name in names)
    return cached_run(str(path),rq,fingerprint(files))


def curve_chart(frame):
    return alt.Chart(frame).mark_line(strokeWidth=3,interpolate='step-after').encode(
        x=alt.X('Giảm giá (%):Q',title='Mức giảm giá (%)',scale=alt.Scale(domain=[0,60])),
        y=alt.Y('Dư nợ đủ điều kiện (USD):Q',title='Dư nợ có HF < 1 (USD)',axis=alt.Axis(format='~s')),
        color=alt.Color('Kịch bản:N',scale=alt.Scale(range=COLORS),legend=alt.Legend(orient='top',title=None)),
        tooltip=['Kịch bản',alt.Tooltip('Giảm giá (%):Q',format='.0f'),alt.Tooltip('Dư nợ đủ điều kiện (USD):Q',format=',.2f')],
    ).properties(height=300).interactive()


def historical_curves(data):
    frame=data['stress_curve'].rename(columns={'shock_fraction':'Giảm giá (%)','scenario':'Kịch bản','eligible_risk_debt_usd':'Dư nợ đủ điều kiện (USD)'}).copy()
    frame['Giảm giá (%)']*=100
    frame['Kịch bản']=frame['Kịch bản'].replace({'ETH_only':'ETH','BTC_only':'BTC','ETH_BTC_joint':'ETH + BTC'})
    return frame


def count_chart(frame,train_end=None):
    base=alt.Chart(frame).mark_bar(color=COLORS[0],opacity=.85).encode(
        x=alt.X('Thời gian UTC:T',title='Thời gian (UTC)'),y=alt.Y('Số thanh lý:Q',title='Số sự kiện thanh lý'),
        tooltip=[alt.Tooltip('Thời gian UTC:T'),alt.Tooltip('Số thanh lý:Q',format=','),'Giờ quan sát:Q'],
    )
    if train_end:
        rule=alt.Chart(pd.DataFrame({'split':[pd.Timestamp(train_end)]})).mark_rule(color='#D28A36',strokeDash=[5,4]).encode(x='split:T')
        base=base+rule
    return base.properties(height=300).interactive()


def money(value):return f'${value:,.2f}'


def metrics(items):
    with st.container(horizontal=True):
        for label,value in items:st.metric(label,value,border=True)


with st.sidebar:
    st.header(':material/hub: DeFi research')
    st.caption('LENDING RISK LAB · RQ1 / RQ4')
    st.divider()
    st.subheader('Nguồn kết quả')
    import os
    results_root=Path(os.getenv('DEFI_DASHBOARD_RESULTS',str(ROOT/'results')))
    runs=discover_runs(results_root)
    selections={}
    for rq in [1,4]:
        if runs[rq]:
            selections[rq]=st.selectbox(f'Lần chạy RQ{rq}',runs[rq],format_func=lambda p:p.name,key=f'run_{rq}')
        else:st.caption(f'Chưa có kết quả RQ{rq} tương thích.')
    st.caption('Mặc định chọn lần chạy mới nhất có đầu ra hoàn tất.')
    if st.button('Đọc lại kết quả',icon=':material/refresh:',width='stretch'):
        st.cache_data.clear();st.rerun()
    st.divider()
    st.badge('Dữ liệu lịch sử',icon=':material/history:',color='blue')
    st.caption('Không tự crawl hoặc gọi RPC. Thay đổi thanh trượt chỉ tính kịch bản tại máy này.')

st.caption('NGHIÊN CỨU DEFI  /  AAVE V3 · ETHEREUM')
st.title('Giả định thay đổi. Rủi ro thay đổi thế nào?')
st.markdown('Khám phá sức chịu sốc của vị thế vay và nhịp xuất hiện các đợt thanh lý, với phạm vi dữ liệu luôn hiển thị.')
st.badge('Exploratory · chưa kết luận toàn thị trường',color='orange',icon=':material/science:')

section=st.segmented_control('Nội dung',SECTIONS,default=SECTIONS[0],selection_mode='single',key='section',width='stretch') or SECTIONS[0]
st.space('small')

data={}
for rq,path in selections.items():
    try:data[rq]=load_selected(path,rq)
    except (OSError,ValueError,KeyError,TypeError) as exc:st.error(f'Không đọc được RQ{rq}: {exc}')

if not data:
    st.info('Chưa có kết quả trong thư mục results/. Chạy các lệnh sau từ thư mục dự án rồi bấm Đọc lại kết quả.')
    st.code('.\\.venv\\Scripts\\python.exe -m defi_models.available_rq14 --models 1 4 --config configs/models.example.json',language='powershell')
    st.stop()

if section==SECTIONS[0]:
    one=data.get(1);four=data.get(4)
    metrics([
        ('Ví RQ1 có dư nợ',str(one['summary'].get('sample_wallets','—')) if one else '—'),
        ('Dư nợ RQ1 ban đầu',money(one['summary'].get('baseline_total_risk_debt_usd',0)) if one else '—'),
        ('Sự kiện RQ4',f"{four['summary']['events']:,}" if four else '—'),
        ('Giờ RQ4 quan sát',f"{four['summary']['hours']:,}" if four else '—'),
    ])
    left,right=st.columns(2,gap='large')
    with left,st.container(border=True):
        st.subheader('RQ1 · Độ nhạy với giá')
        st.caption('Kết quả đã lưu · ba kịch bản giảm giá, ngưỡng HF < 1')
        if one:st.altair_chart(curve_chart(historical_curves(one)),width='stretch',alt='Dư nợ đủ điều kiện thanh lý theo cú sốc ETH, BTC và đồng thời')
        else:st.info('Chưa có đầu ra RQ1.')
    with right,st.container(border=True):
        st.subheader('RQ4 · Các đợt thanh lý')
        st.caption('Số sự kiện theo tháng · đường vàng đánh dấu bắt đầu tập test')
        if four:
            panel=four['hourly_counts']
            counts=aggregate_counts(panel,panel.hour_utc.min().date(),panel.hour_utc.max().date(),'MS')
            st.altair_chart(count_chart(counts,four['summary']['train_end_utc']),width='stretch',alt='Số thanh lý Aave theo tháng và ranh giới train test')
        else:st.info('Chưa có đầu ra RQ4.')
    with st.container(border=True):
        st.subheader('Đọc kết quả đúng phạm vi')
        st.markdown('**RQ1:** số ví và dư nợ có HF < 1 là khả năng đủ điều kiện thanh lý theo kịch bản. **RQ4:** mức tập trung theo thời gian chưa chứng minh thanh lý gây ra thanh lý tiếp theo.')
        st.caption('Dữ liệu thật trong quá khứ. Kịch bản giá và đường cường độ trên dashboard là giả định mô hình, không phải luồng realtime.')

elif section==SECTIONS[1]:
    st.header('RQ1 · Thử sức chịu sốc')
    if 1 not in data:st.info('Cần kết quả RQ1 để mở phần này.');st.stop()
    one=data[1];scope=one['summary']['snapshot']
    st.caption(f"Snapshot block {scope['block']} · {one['summary'].get('sample_wallets','—')} ví có dư nợ · HF nền đã đối chiếu")
    controls,output=st.columns([1,3],gap='large')
    with controls,st.container(border=True):
        st.subheader('Giả định kịch bản')
        eth=st.slider('ETH giảm (%)',0,60,40,key='eth_shock',persist_state='session')/100
        btc=st.slider('BTC giảm (%)',0,60,0,key='btc_shock',persist_state='session')/100
        lt=st.slider('Dịch LT (điểm phần trăm)',-10,10,0,key='lt_shift',persist_state='session')/100
        derivatives=st.toggle('Ánh xạ tài sản phái sinh',value=True,key='derivatives',persist_state='session',help='Bật: dùng mapping ETH/BTC của lần chạy. Tắt: chỉ WETH thuộc ETH và WBTC thuộc BTC; tài sản khác giữ giá.')
        st.caption('Giảm giá áp dụng đồng thời lên thế chấp và nợ cùng yếu tố. LT được giới hạn trong [0, 1].')
    try:
        portfolio,scope=validated_portfolio(Path(one['path']),derivatives)
        current=stress_view(portfolio,eth,btc,lt)
        # Include current source metadata in the cache key; hashes are checked above on every rerun.
        source_paths=[Path(r['path']) for r in one['manifest']['source_files']]
        curves=cached_curves(one['path'],derivatives,lt,fingerprint(source_paths))
    except (ValueError,OSError,KeyError,TypeError) as exc:
        st.error(f'Chưa thể mô phỏng trên nguồn này: {exc}');st.stop()
    with output:
        metrics([('Ví có HF < 1',f"{current['eligible_wallets']}/{len(portfolio.accounts)}"),
                 ('Dư nợ đủ điều kiện',money(current['eligible_debt'])),('Tỷ lệ dư nợ kịch bản',f"{current['debt_share']:.2%}")])
        with st.container(border=True):
            st.subheader('Đường stress theo giả định đang chọn')
            st.caption('Các đường quét riêng ETH, BTC và đồng thời; dùng cùng dịch LT và mapping. Thẻ số phía trên dùng hai mức giảm giá bạn chọn độc lập.')
            st.altair_chart(curve_chart(curves),width='stretch',alt='Đường stress được tính lại theo dịch LT và ánh xạ tài sản đang chọn')
        st.caption(f"Dư nợ sau cú sốc: {money(current['total_debt'])}. Tỷ lệ dùng dư nợ sau cú sốc làm mẫu số; dư nợ ban đầu: {money(float(portfolio.d.sum()))}.")
    st.subheader('Đối chiếu từng ví')
    table=current['wallets'].sort_values('HF kịch bản')
    st.dataframe(table,hide_index=True,width='stretch',alt='HF và dư nợ từng ví trước và sau cú sốc',column_config={
        'HF ban đầu':st.column_config.NumberColumn(format='%.4f'),
        'HF kịch bản':st.column_config.NumberColumn(format='%.4f'),
        'Dư nợ kịch bản (USD)':st.column_config.NumberColumn(format='$ %.2f'),
    })
    export={'type':'what_if_rq1','created_utc':datetime.now(timezone.utc).isoformat(),'source_run':one['path'],
            'source_files':one['manifest']['source_files'],'eth_drop':eth,'btc_drop':btc,'lt_shift':lt,
            'derivatives_follow_factors':derivatives,'eligible_wallets':current['eligible_wallets'],
            'eligible_debt_usd':current['eligible_debt'],'full_research_ready':False}
    with st.container(horizontal=True):
        st.download_button('Tải bảng từng ví',table.to_csv(index=False).encode('utf-8-sig'),'rq1_what_if.csv','text/csv',icon=':material/download:')
        st.download_button('Tải giả định JSON',json.dumps(export,ensure_ascii=False,indent=2).encode('utf8'),'rq1_assumptions.json','application/json')
    with st.expander('Mapping và công thức'):
        st.latex(r'HF = \frac{\sum_i C_i\,P_i\,LT_i}{\sum_j D_j\,P_j}')
        st.caption('Minh họa công thức; engine có làm tròn theo Pool revision. Dịch LT là sensitivity giả định, không phải thay đổi tham số giao thức thực tế.')
        st.dataframe(pd.DataFrame(portfolio.mapping()),hide_index=True,alt='Mapping token theo yếu tố ETH BTC hoặc giữ cố định')

elif section==SECTIONS[2]:
    st.header('RQ4 · Thanh lý tập trung như thế nào?')
    if 4 not in data:st.info('Cần kết quả RQ4 để mở phần này.');st.stop()
    four=data[4];s=four['summary'];panel=four['hourly_counts']
    st.caption(f"{s['observation_start_utc']} → trước {s['observation_end_exclusive_utc']} · UTC · Aave V3")
    metrics([('Thanh lý',f"{s['events']:,}"),('Half-life đã fit',f"{s['hawkes']['half_life_hours']*60:g} phút"),
             ('Branching ratio đã fit',f"{s['hawkes']['branching_ratio']:.4f}"),('Tách train / test',f"{four['manifest']['config'].get('train_fraction',.8):.0%} / {1-four['manifest']['config'].get('train_fraction',.8):.0%}")])
    with st.container(border=True):
        dates,bin_control=st.columns([3,1])
        with dates:
            interval=st.date_input('Khoảng quan sát (UTC)',value=(panel.hour_utc.min().date(),panel.hour_utc.max().date()),
                                   min_value=panel.hour_utc.min().date(),max_value=panel.hour_utc.max().date(),key=f'dates_{Path(four["path"]).name}')
        with bin_control:
            bin_name=st.selectbox('Gộp số đếm',['Ngày','Tuần','Tháng'],index=2,key='count_bin')
        if len(interval)==2:
            counts=aggregate_counts(panel,*interval,{'Ngày':'D','Tuần':'W-MON','Tháng':'MS'}[bin_name])
            st.altair_chart(count_chart(counts,s['train_end_utc']),width='stretch',alt='Số thanh lý trong khoảng và độ phân giải được chọn')
            st.caption(f"{int(counts['Số thanh lý'].sum()):,} sự kiện / {int(counts['Giờ quan sát'].sum()):,} giờ trong bộ lọc. Đổi bin chỉ đổi cách hiển thị, không fit lại mô hình. Đường vàng: bắt đầu tập test.")
        else:st.info('Chọn thêm ngày kết thúc để hiển thị biểu đồ.')
    controls,plot=st.columns([1,3],gap='large')
    with controls,st.container(border=True):
        st.subheader('Thử giả định Hawkes')
        half=st.number_input('Half-life giả định (phút)',min_value=.1,max_value=360.,value=round(s['hawkes']['half_life_hours']*60,4),step=1.,key=f'half_{Path(four["path"]).name}')
        branching=st.slider('Branching ratio giả định',0.,.99,round(s['hawkes']['branching_ratio'],2),.01,key=f'branch_{Path(four["path"]).name}')
        burst=st.slider('Số sự kiện trong cụm ban đầu',1,50,5,key='burst')
        horizon=st.selectbox('Khoảng theo dõi (phút)',[30,120,360,720],index=1,key='horizon')
    with plot,st.container(border=True):
        st.subheader('Phản ứng cường độ có điều kiện')
        response=decay_response(s['hawkes']['baseline_per_hour'],branching,half,burst,horizon)
        long=response.melt(id_vars='Phút sau cụm sự kiện',var_name='Thành phần',value_name='Sự kiện/giờ')
        chart=alt.Chart(long).mark_line(strokeWidth=2.5).encode(
            x=alt.X('Phút sau cụm sự kiện:Q'),y=alt.Y('Sự kiện/giờ:Q'),
            color=alt.Color('Thành phần:N',scale=alt.Scale(range=COLORS),legend=alt.Legend(orient='bottom',title=None)),
            tooltip=['Phút sau cụm sự kiện:Q',alt.Tooltip('Sự kiện/giờ:Q',format='.3f'),'Thành phần:N'],
        ).properties(height=255)
        st.altair_chart(chart,width='stretch',alt='Cường độ suy giảm theo half life và branching ratio giả định so với nền')
        st.caption('Minh họa kernel thế hệ thứ nhất sau một cụm sự kiện. Giữ nguyên cường độ nền đã fit; không fit lại, không mô phỏng các thế hệ sau và không phải dự báo realtime.')
    with st.expander('Tham số các mô hình đã fit và giới hạn'):
        st.dataframe(four['hawkes_candidates'],hide_index=True,alt='Các ứng viên Hawkes đã fit với train và test likelihood')
        st.caption('Ứng viên được chọn theo train likelihood. Giá trị test dùng đánh giá; không dùng để chọn lại tham số. Poisson đối chứng của run exploratory là cường độ hằng, chưa có giá ETH/BTC làm biến kiểm soát.')
        st.caption('Không suy ra quan hệ nhân quả từ branching ratio hoặc clustering. Likelihood chỉ so sánh trong cùng cách biểu diễn sự kiện và cùng cửa sổ.')
    assumptions={'type':'what_if_hawkes_first_generation','source_run':four['path'],'half_life_minutes':half,
                 'branching_ratio':branching,'burst':burst,'baseline_per_hour':s['hawkes']['baseline_per_hour'],
                 'horizon_minutes':horizon,'refitted':False,'causal_claim':False,'full_research_ready':False}
    st.download_button('Tải giả định Hawkes',json.dumps(assumptions,ensure_ascii=False,indent=2).encode('utf8'),'rq4_assumptions.json','application/json',icon=':material/download:')

else:
    st.header('Sổ giả định & chất lượng dữ liệu')
    st.markdown('Theo dõi điều gì được cố định, điều gì đang thử và điều gì còn thiếu trước khi diễn giải kết quả.')
    registry=[
        ('RQ1','Cohort','Mẫu người vay tại một block; không phải toàn bộ thị trường','Giới hạn dữ liệu'),
        ('RQ1','HF và nợ','Đối chiếu cùng block, tolerance 1e-4; dùng risk debt','Kiểm tra trước khi tính'),
        ('RQ1','Giá phái sinh','Độ nhạy một-một theo factor khi bật mapping; không mô hình depeg/basis','Giả định sensitivity'),
        ('RQ1','Ngưỡng thanh lý','HF < 1; eligible debt không bằng lượng thanh lý thực thi','Định nghĩa mô hình'),
        ('RQ1','Dịch LT','Cộng điểm phần trăm và clip [0,1]; không đổi cấu hình on-chain','Điều chỉnh trên giao diện'),
        ('RQ4','Thời gian','UTC; giữ số đếm và multiplicity của sự kiện cùng timestamp','Quy tắc đo lường'),
        ('RQ4','Tách dữ liệu','Theo thời gian, tỷ lệ từ config lần chạy; đổi bin không đổi split','Cố định theo run'),
        ('RQ4','Biến kiểm soát','Run exploratory chưa có ETH/BTC price controls','Còn thiếu'),
        ('RQ4','Đường cường độ','Kernel thế hệ thứ nhất có điều kiện; không fit lại và không phải quan hệ nhân quả','Giả định minh họa'),
        ('Cả hai','Tính cập nhật','Kết quả lịch sử trên đĩa; không có nguồn realtime trong dashboard này','Cố định phạm vi'),
    ]
    st.dataframe(pd.DataFrame(registry,columns=['RQ','Giả định','Diễn giải','Trạng thái']),hide_index=True,width='stretch',alt='Sổ giả định và giới hạn RQ1 RQ4')
    left,right=st.columns(2)
    with left,st.container(border=True):
        st.subheader('Audit của bộ recovery')
        st.dataframe(pd.DataFrame(audit_status()),hide_index=True,alt='Tình trạng audit của dữ liệu recovery')
        st.caption('Bảng này phản ánh bộ recovery trên máy; không tự chứng nhận các run exploratory được chọn.')
    with right,st.container(border=True):
        st.subheader('Tiến độ thu thập')
        status_path=ROOT/'output/rq1_rq4_acquisition/collection_status.json'
        if status_path.exists():
            try:
                status=read_json(status_path)
                st.markdown(f"**Trạng thái gần nhất:** `{status.get('status','unknown')}` · bước `{status.get('phase','unknown')}`")
                st.caption(f"Ghi nhận lúc {status.get('updated_utc','—')} (UTC). Trạng thái lưu trên đĩa, chưa kiểm tra tiến trình còn sống.")
            except (ValueError,OSError):st.info('Chưa đọc được trạng thái thu thập.')
        else:st.info('Chưa có trạng thái thu thập trên máy này.')
        st.caption('Ứng dụng chỉ đọc trạng thái và dữ liệu. Không tạo audit hoặc sửa checkpoint.')
    for rq,obj in data.items():
        with st.expander(f'RQ{rq} · nguồn, cấu hình và giới hạn đã lưu'):
            st.code(obj['path'],language=None)
            st.json({'config':obj['manifest'].get('config',{}),'summary':obj['summary'],'source_files':obj['manifest'].get('source_files',[])},expanded=False)

st.divider()
st.caption('Lending DeFi research · Chỉ đọc dữ liệu nguồn · Kết quả exploratory · Thời gian biểu đồ: UTC')
