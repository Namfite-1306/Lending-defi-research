import json,time
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
from pathlib import Path

STATIC=Path(__file__).resolve().parent/'web'

def freshness(product,limit,now=None,source_now=None):
    now=time.time() if now is None else now
    if product is None:return {'state':'unavailable','source_age_seconds':None}
    source_now=now if source_now is None else source_now
    age=max(0,source_now-product['source_stamp']);built=max(0,now-product['built_at'])
    return {'state':'fresh' if age<=limit and built<=limit else 'stale','source_age_seconds':round(age,1),'calculation_age_seconds':round(built,1)}

def make_server(store,models,host,port,poll_seconds,snapshot_seconds):
    from .lab import ResearchLab,LabBusy
    lab=ResearchLab(store,models,source_stale_seconds=max(120,snapshot_seconds*2))
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,status,body,mime='application/json; charset=utf-8'):
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_GET(self):
            path=urlparse(self.path);query=parse_qs(path.query)
            if path.path in ['/','/app.js','/style.css','/lab','/lab.js','/lab.css','/validation','/validation.js','/research','/research.js','/guide']:
                name={'/':'index.html','/app.js':'app.js','/style.css':'style.css','/lab':'lab.html','/lab.js':'lab.js','/lab.css':'lab.css','/validation':'validation.html','/validation.js':'validation.js','/research':'research.html','/research.js':'research.js','/guide':'guide.html'}[path.path]
                mime='text/html; charset=utf-8' if name.endswith('.html') else 'text/javascript; charset=utf-8' if name.endswith('.js') else 'text/css; charset=utf-8'
                return self.send(200,(STATIC/name).read_bytes(),mime)
            try:
                if path.path=='/api/research':
                    from .research import research_data
                    return self.send(200,json.dumps(research_data(models.research_results,models.research_data),ensure_ascii=False,allow_nan=False).encode('utf8'))
                if path.path=='/api/research/cascade':
                    from .research import cascade_result
                    raw_feedback=query.get('feedback',['true'])[0]
                    if raw_feedback not in ['true','false']:raise ValueError('Invalid feedback flag')
                    value=cascade_result(models.research_results,models.research_data,query.get('date',[''])[0],float(query.get('shock',['0.2'])[0]),raw_feedback=='true')
                    return self.send(200,json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf8'))
                if path.path=='/api/universe':
                    scanner=getattr(models,'universe',None)
                    return self.send(200,json.dumps(scanner.status() if scanner else {'state':'disabled'},allow_nan=False).encode())
                if path.path=='/api/liquidity':
                    product=store.product('liquidity')
                    if product:
                        head=store.meta('head');now=time.time()
                        source_now=head['stamp']+max(0,now-head['observed_at']) if head else now
                        product['freshness']=freshness(product,1800,now,source_now)
                        job=store.meta('liquidity_job',{})
                        if job.get('state')=='error':product['freshness']['state']='update_error'
                        if store.meta('collector_status',{}).get('state')=='error':product['freshness']['state']='source_error'
                    return self.send(200,json.dumps({'product':product,'job':store.meta('liquidity_job')},allow_nan=False).encode())
                if path.path=='/api/backtests':
                    folder=getattr(models,'backtest_dir',None)
                    records=[];quotes=None
                    if folder:
                        folder=Path(folder)
                        for file in sorted(folder.glob('*/progress.json')):records.append(json.loads(file.read_text(encoding='utf8')))
                        file=folder/'quote_collection.json'
                        if file.exists():quotes=json.loads(file.read_text(encoding='utf8'))
                    return self.send(200,json.dumps({'snapshots':records,'quotes':quotes},ensure_ascii=False,allow_nan=False).encode('utf8'))
                if path.path=='/api/validation':
                    folder=getattr(models,'evidence_dir',None)
                    if not folder:return self.send(503,b'{"error":"evidence_not_configured"}')
                    folder=Path(folder);evidence=json.loads((folder/'evidence.json').read_text(encoding='utf8'))
                    import csv
                    tables={}
                    for name in ['concentration_by_period','quote_curve_validation','backtest_event_plan','pair_scenarios']:
                        file=folder/(name+'.csv')
                        if file.exists():
                            with file.open(encoding='utf-8-sig',newline='') as f:tables[name]=list(csv.DictReader(f))
                    return self.send(200,json.dumps({'evidence':evidence,'tables':tables},ensure_ascii=False,allow_nan=False).encode('utf8'))
                if path.path=='/api/lab/data':return self.send(200,json.dumps(lab.data(),ensure_ascii=False,allow_nan=False).encode('utf8'))
                if path.path=='/api/lab/job':return self.send(200,json.dumps(lab.job(query.get('id',[''])[0]),ensure_ascii=False,allow_nan=False).encode('utf8'))
                cursor=store.meta('cursor');h=store.header(cursor) if cursor is not None else None;now=time.time();head=store.meta('head')
                source_now=head.get('stamp',now)+max(0,now-head['observed_at']) if head else now
                def quality(product,limit,name):
                    result=freshness(product,limit,now,source_now)
                    if product and store.meta('collector_status',{}).get('state')=='error':result['state']='source_error'
                    if product and name=='models' and store.meta('model_job',{}).get('state')=='error':result['state']='update_error'
                    return result
                if path.path=='/api/status':
                    collector=store.meta('collector_status',{'state':'starting'});price=store.product('prices');model=store.product('models')
                    age=max(0,source_now-h['stamp']) if h else None
                    state='starting' if not h else 'error' if collector.get('state')=='error' else 'catching_up' if head and cursor<head['target'] else 'fresh' if age<max(120,poll_seconds*4) and now-collector.get('last_success_at',0)<poll_seconds*3 else 'stale'
                    value={'now':now,'state':state,'head':head,'cursor':cursor,'block_timestamp':h['stamp'] if h else None,'block_hash':h['hash'] if h else None,
                        'event_age_seconds':round(age,1) if age is not None else None,'collector':collector,'poll_seconds':poll_seconds,'snapshot_seconds':snapshot_seconds,
                        'confirmations':store.meta('config',{}).get('confirmations'),'start_block':store.meta('start_block'),'last_reorg':store.meta('last_reorg'),
                        'prices':quality(price,120,'prices'),'models':quality(model,max(120,snapshot_seconds*2),'models'),
                        'clock_offset_seconds':round(head.get('stamp',now)-head['observed_at'],1) if head else None,
                        'price_error':store.meta('price_error'),'model_job':store.meta('model_job'),'exposure_error':store.meta('exposure_error'),
                        'scope':'selected Ethereum contracts, live tail only; not stitched to historical dataset'}
                elif path.path in ['/api/prices','/api/models']:
                    name=path.path.rsplit('/',1)[1];value=store.product(name)
                    if value:value['freshness']=quality(value,120 if name=='prices' else max(120,snapshot_seconds*2),name)
                    if value and name=='models':
                        exposure=store.product('exposures')
                        if exposure:
                            value['payload']['rq5']=exposure['payload'];value['payload']['rq5_source_block']=exposure['block']
                            value['payload']['rq5_freshness']=quality(exposure,max(120,snapshot_seconds*2),'exposures')
                elif path.path=='/api/analytics':
                    window=int(query.get('hours',['24'])[0]);window=max(1,min(window,48));value=models.online_analytics(window*3600)
                elif path.path=='/api/events':
                    limit=max(1,min(int(query.get('limit',['30'])[0]),100));protocol=query.get('protocol',[None])[0]
                    value=store.events(limit=limit,protocol=protocol)
                else:return self.send(404,b'{"error":"not_found"}')
                self.send(200,json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf8'))
            except (ValueError,TypeError) as e:self.send(400,json.dumps({'error':str(e)[:200]}).encode())
            except Exception:self.send(503,b'{"error":"data_not_available_retry"}')
        def do_POST(self):
            if urlparse(self.path).path!='/api/lab/simulate':return self.send(404,b'{"error":"not_found"}')
            origin=self.headers.get('Origin')
            if origin and urlparse(origin).netloc!=self.headers.get('Host'):return self.send(403,b'{"error":"origin_not_allowed"}')
            try:
                require_type=self.headers.get('Content-Type','').split(';')[0]
                if require_type!='application/json':return self.send(415,b'{"error":"application_json_required"}')
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=4096:return self.send(413,b'{"error":"request_too_large_or_empty"}')
                value=json.loads(self.rfile.read(length))
                result=lab.submit(value)
                self.send(202,json.dumps(result).encode('utf8'))
            except LabBusy as exc:self.send(429,json.dumps({'error':str(exc)},ensure_ascii=False).encode('utf8'))
            except (ValueError,TypeError) as exc:self.send(400,json.dumps({'error':str(exc)},ensure_ascii=False).encode('utf8'))
    server=ThreadingHTTPServer((host,port),Handler)
    server.research_lab=lab
    return server
