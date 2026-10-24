"""Independent Kraken USDC/USD trades at event times; no peg imputation.

Contiguous paginated trade coverage is checked before matching. This event-targeted
sample is NOT permitted as a five-minute all-market H3 feature panel.
"""
import argparse,bisect,gzip,json,sqlite3,time,urllib.request,urllib.error,uuid
from decimal import Decimal
from pathlib import Path
from .next_common import *
URL='https://api.kraken.com/0/public/Trades'
LATENCY=5
LOOKBACK=300

def targets():
    legs={}
    for r in read(V1_OUT/'h2/collateral_legs.csv'):legs.setdefault(r['episode'],[]).append(r)
    rows=[r for r in read(V1_OUT/'h2/episodes.csv') if r['debt_token']=='0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48' and '2024-02-01'<=r['date']<PRIMARY_END_UTC[:10] and len(legs[r['episode']])==1 and legs[r['episode']][0]['token'] in ['0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2','0x2260fac5e5542a773aa44fbcfedf7c193bc2c599']]
    for r in rows:r['collateral_token']=legs[r['episode']][0]['token']
    return rows

def connection():
    DATA_NEXT.mkdir(parents=True,exist_ok=True);c=sqlite3.connect(DATA_NEXT/'kraken.sqlite',timeout=30);c.execute('PRAGMA journal_mode=WAL')
    c.execute('CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY,stamp REAL,price TEXT,volume TEXT)')
    c.execute('CREATE INDEX IF NOT EXISTS trade_time ON trades(stamp)')
    c.execute('CREATE TABLE IF NOT EXISTS pages(since TEXT PRIMARY KEY,start REAL,end REAL,cursor TEXT,rows INTEGER,sha256 TEXT)');return c

def intervals(c):
    out=[]
    c.execute('CREATE TABLE IF NOT EXISTS quarantined_pages(since TEXT PRIMARY KEY,reason TEXT)')
    for start,end in c.execute('SELECT start,end FROM pages WHERE since NOT IN (SELECT since FROM quarantined_pages) ORDER BY start'):
        if out and start<=out[-1][1]+.001:out[-1][1]=max(end,out[-1][1])
        else:out.append([start,end])
    return out

def covered(ranges,lo,hi):
    j=bisect.bisect_right([r[0] for r in ranges],lo)-1
    return j>=0 and ranges[j][1]>=hi

def parse_page(payload,since,allow_reviewed_gap=False):
    if payload.get('error'):raise ValueError('Kraken API: '+str(payload['error']))
    result=payload['result'];keys=[k for k in result if k!='last']
    if keys!=['USDCUSD']:raise ValueError('Wrong/missing USDC/USD pair response')
    values=result[keys[0]];cursor=str(result['last']);start=float(Decimal(since)/10**9)
    if not values:raise ValueError('No historical trades; scope cannot be verified')
    if not allow_reviewed_gap and float(values[0][2])-start>3600:raise ValueError('Historical since ignored or trade gap over one hour; requires review, not automatic coverage')
    rows=[];last=start
    for v in values:
        at=float(v[2]);p=Decimal(v[0]);volume=Decimal(v[1]);identifier=int(v[6])
        if p<=0 or volume<0 or at<start-.001 or at<last-.001:raise ValueError('Invalid, unsorted or since-ignoring historical trade response')
        if rows and identifier<=rows[-1][0]:raise ValueError('Non-increasing trade identifiers')
        rows.append((identifier,at,str(p),str(volume)));last=at
    if float(Decimal(cursor)/10**9)<last-.001:raise ValueError('Cursor precedes returned trades')
    return rows,start,last,cursor

def fetch_page(since):
    req=urllib.request.Request(URL+'?pair=USDCUSD&count=1000&since='+since)
    with urllib.request.urlopen(req,timeout=20) as response:
        body=response.read(2_000_001)
        if len(body)>2_000_000:raise ValueError('Unexpected large trade page')
        payload=json.loads(body,parse_float=Decimal)
    return payload

def collect(minutes=60,max_requests=3000):
    with worker_lock(DATA_NEXT/'market.lock'):
        c=connection();ranges=intervals(c);events=targets();stamps=sorted({int(r['stamp']) for r in events});deadline=time.monotonic()+minutes*60;calls=0;errors=[];last_call=0.
        for at in stamps:
            lo=at-LATENCY-LOOKBACK;hi=at-LATENCY
            if covered(ranges,lo,hi):continue
            since=str(lo*10**9)
            while not covered(ranges,lo,hi):
                if time.monotonic()>=deadline or calls>=max_requests:break
                old=c.execute('SELECT cursor,end FROM pages WHERE since=?',(since,)).fetchone()
                if old:
                    if c.execute('SELECT 1 FROM quarantined_pages WHERE since=?',(since,)).fetchone():
                        errors.append({'kind':'quarantined_page','since':since,'message':'Historical page has unverified long gap; source review required'});break
                    if old[0]==since:errors.append({'kind':'stalled_cursor'});break
                    since=old[0];continue
                try:
                    delay=1.05-(time.monotonic()-last_call)
                    if delay>0:time.sleep(delay)
                    last_call=time.monotonic();calls+=1;payload=fetch_page(since);values,start,end,cursor=parse_page(payload,since)
                    if end<=start:raise ValueError('No trade-page progress')
                    folder=DATA_NEXT/'trade_pages';folder.mkdir(exist_ok=True);path=folder/(since+'.json.gz');tmp=path.with_suffix('.'+uuid.uuid4().hex+'.tmp')
                    with gzip.open(tmp,'wt',encoding='utf8') as f:json.dump(payload,f,default=str)
                    tmp.replace(path)
                    with c:
                        for row in values:
                            previous=c.execute('SELECT stamp,price,volume FROM trades WHERE id=?',(row[0],)).fetchone()
                            if previous and previous!=tuple(row[1:]):raise ValueError('Conflicting historical trade id')
                        c.executemany('INSERT OR IGNORE INTO trades VALUES (?,?,?,?)',values)
                        c.execute('INSERT INTO pages VALUES (?,?,?,?,?,?)',(since,start,end,cursor,len(values),digest(path)))
                    since=cursor;ranges=intervals(c)
                except Exception as exc:
                    errors.append({'kind':'http_'+str(exc.code) if isinstance(exc,urllib.error.HTTPError) else type(exc).__name__,'message':str(exc)[:180]});break
                if calls%10==0:
                    complete=sum(covered(ranges,s-LATENCY-LOOKBACK,s-LATENCY) for s in stamps)
                    save(OUT/'market_progress.json',{'updated_utc':now(),'requests_this_run':calls,'target_timestamps':len(stamps),'covered_timestamps':complete,'complete':complete==len(stamps),'errors':errors})
                    print('USDC MARKET',complete,'/',len(stamps),'requests',calls,flush=True)
            if errors or time.monotonic()>=deadline or calls>=max_requests:break
        complete=sum(covered(ranges,s-LATENCY-LOOKBACK,s-LATENCY) for s in stamps)
        save(OUT/'market_progress.json',{'updated_utc':now(),'requests_this_run':calls,'target_events':len(events),'target_timestamps':len(stamps),'covered_timestamps':complete,'complete':complete==len(stamps),'errors':errors,'paid_source_used':False,'account_source_used':False})
        c.close();return build()

def build():
    c=connection();ranges=intervals(c);quarantined=c.execute('SELECT COUNT(*) FROM quarantined_pages').fetchone()[0];trades=list(c.execute('SELECT stamp,price,id FROM trades ORDER BY stamp,id'));c.close();times=[r[0] for r in trades];rows=[]
    for event in targets():
        at=int(event['stamp']);hi=at-LATENCY;verified=covered(ranges,hi-LOOKBACK,hi);j=bisect.bisect_left(times,hi)-1
        price,stamp,identifier=(float(trades[j][1]),trades[j][0],trades[j][2]) if verified and j>=0 else (None,None,None)
        if stamp is not None and hi-stamp>LOOKBACK and not covered(ranges,hi-3600,hi):price,stamp,identifier=None,None,None
        age=at-stamp if stamp is not None else None
        rows.append({'episode':event['episode'],'protocol':event['protocol'],'borrower':event['borrower'],'collateral_token':event['collateral_token'],'stamp':at,'date':event['date'],
          'debt_native_USDC':str(Decimal(event['debt_raw_upper_estimate'])/10**6),'oracle_debt_usd':event['debt_usd_upper'],'oracle_age_seconds':event['debt_price_age_seconds'],
          'market_price_usd':price,'market_trade_stamp':stamp,'market_age_seconds':age,'market_trade_id':identifier,'coverage_verified':verified,
          'market_debt_usd':float(Decimal(event['debt_raw_upper_estimate'])/10**6)*price if price is not None and age<=3600 else None,
          'oracle_minus_market_bps':(float(event['debt_usd_upper'])/(float(Decimal(event['debt_raw_upper_estimate'])/10**6)*price)-1)*10000 if event['debt_usd_upper'] and price and int(event['debt_raw_upper_estimate'])>0 else None})
    write(OUT/'market_event_quotes.csv',rows)
    result={'updated_utc':now(),'source':'Kraken public USDC/USD trade history','scope':'2024-02-01 to '+PRIMARY_END_UTC+'; matched USDC-debt single-WETH/WBTC-collateral events',
      'events':len(rows),'verified_events':sum(r['coverage_verified'] for r in rows),'fresh_60s_events':sum(r['market_age_seconds'] is not None and r['market_age_seconds']<=60 for r in rows),
      'fresh_300s_events':sum(r['market_age_seconds'] is not None and r['market_age_seconds']<=300 for r in rows),'fresh_3600s_events':sum(r['market_debt_usd'] is not None for r in rows),
      'latency_assumption_seconds':LATENCY,'primary_coverage_lookback_seconds':LOOKBACK,'quote_table_sha256':digest(OUT/'market_event_quotes.csv'),'paid_source_used':False,'account_source_used':False,
      'limitations':['Single exchange; historical trade time plus assumed 5s latency, not verified receipt time','No carry beyond maximum quote age; no USD peg substitution',
        'Event-targeted quotes cannot be used as full-clock H3 covariates','No trades in a window can leave no fresh quote; coverage is not automatically 100%']}
    progress=load(OUT/'market_progress.json',{});stamps=sorted({r['stamp'] for r in rows})
    verified=sum(covered(ranges,s-LATENCY-LOOKBACK,s-LATENCY) for s in stamps)
    progress.update(updated_utc=now(),target_events=len(rows),target_timestamps=len(stamps),covered_timestamps=verified,complete=verified==len(stamps),quarantined_pages=quarantined)
    progress['status']='complete' if verified==len(stamps) else 'partial_source_gap' if quarantined else 'in_progress_or_budget_limited'
    save(OUT/'market_progress.json',progress)
    result['quarantined_pages']=quarantined
    save(OUT/'market_data_readiness.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--minutes',type=float,default=60);p.add_argument('--max-requests',type=int,default=3000);p.add_argument('--build-only',action='store_true');a=p.parse_args()
    print(build() if a.build_only else collect(a.minutes,a.max_requests),flush=True)
