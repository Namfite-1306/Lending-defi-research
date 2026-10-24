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
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,status,body,mime='application/json; charset=utf-8'):
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_GET(self):
            path=urlparse(self.path);query=parse_qs(path.query)
            if path.path in ['/','/app.js','/style.css']:
                name={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[path.path]
                mime={'index.html':'text/html; charset=utf-8','app.js':'text/javascript; charset=utf-8','style.css':'text/css; charset=utf-8'}[name]
                return self.send(200,(STATIC/name).read_bytes(),mime)
            try:
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
    return ThreadingHTTPServer((host,port),Handler)
