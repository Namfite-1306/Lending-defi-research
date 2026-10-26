/** Vercel request adapter. No crawler, SQLite writer, daemon or in-memory jobs. */
const fs=require('node:fs');
const path=require('node:path');
const {gunzipSync}=require('node:zlib');
const GET_ROUTES=new Set(['status','prices','models','analytics','events','universe','liquidity','backtests','lab/job']);
const MAX_BYTES=4_000_000;
let frozenCascade;
function reply(res,status,value){res.setHeader('Cache-Control','no-store');res.setHeader('Content-Type','application/json; charset=utf-8');res.setHeader('X-Content-Type-Options','nosniff');res.statusCode=status;res.end(JSON.stringify(value));}
function backendURL(raw){
  if(!raw)return null;
  const u=new URL(raw);
  if(u.protocol!=='https:'||u.username||u.password||u.search||u.hash)throw Error('Invalid backend configuration');
  if(u.hostname==='localhost'||u.hostname.endsWith('.localhost')||/^(127\.|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.|0\.)/.test(u.hostname)||u.hostname.includes(':'))throw Error('Backend must have a public HTTPS hostname');
  return u;
}
function snapshotStatus(){
  const quality={state:'unavailable',source_age_seconds:null};
  return {state:'snapshot_only',message:'Bản Vercel đang hiển thị kết quả lịch sử. Chưa cấu hình backend chạy liên tục cho live và what-if.',now:Date.now()/1000,
    cursor:null,head:null,event_age_seconds:null,poll_seconds:15,snapshot_seconds:300,collector:{state:'not_configured'},prices:quality,models:quality,
    capabilities:{live:false,whatif:false},scope:'Frozen historical evidence; no live data is published as fresh.'};
}
function routeFrom(req){
  const url=new URL(req.url,'https://dashboard.invalid');
  const raw=req.query?.route??url.searchParams.get('route')??url.pathname.replace(/^\/api\//,'');
  const route=Array.isArray(raw)?raw.join('/'):raw;
  return {route,url};
}
async function handler(req,res){
  const {route,url}=routeFrom(req),method=req.method||'GET';
  try{
    if(method==='GET'&&route==='research/cascade'){
      const date=url.searchParams.get('date'),shock=url.searchParams.get('shock'),feedback=url.searchParams.get('feedback');
      if(!/^\d{4}-\d{2}-\d{2}$/.test(date||'')||!['0.1','0.2','0.3'].includes(shock)||!['true','false'].includes(feedback))return reply(res,400,{error:'invalid_scenario'});
      if(!frozenCascade)frozenCascade=JSON.parse(gunzipSync(fs.readFileSync(path.join(process.cwd(),'deployment/snapshot/cascade.json.gz'))));
      const result=frozenCascade[`${date}|${shock}|${feedback}`];
      return result?reply(res,200,result):reply(res,404,{error:'scenario_not_in_frozen_snapshot'});
    }
    const base=backendURL(process.env.DEFI_BACKEND_URL);
    if(method==='GET'&&route==='deployment')return reply(res,200,{mode:'vercel',historical_mode:'frozen_historical',live_enabled:!!base,whatif_enabled:!!base,backend_configured:!!base,
      note:base?'Backend đã cấu hình; freshness phải đọc từ /api/status.':'Kết quả lịch sử; cần backend HTTPS chạy liên tục để bật live và what-if.'});
    if(!(method==='GET'&&GET_ROUTES.has(route))&&!(method==='POST'&&route==='lab/simulate'))return reply(res,404,{error:'not_found'});
    if(!base){
      if(route==='status')return reply(res,200,snapshotStatus());
      if(['prices','models'].includes(route))return reply(res,200,null);
      if(route==='events')return reply(res,200,[]);
      if(route==='analytics')return reply(res,200,{state:'unavailable'});
      if(route==='liquidity')return reply(res,200,{product:null,job:null});
      if(route==='backtests')return reply(res,200,{snapshots:[],quotes:null});
      if(route==='universe')return reply(res,200,{state:'not_configured'});
      return reply(res,503,{error:'Chưa cấu hình backend live/what-if. Các kết quả lịch sử vẫn xem và lọc được.'});
    }
    const headers={'Accept':'application/json'};
    if(process.env.DEFI_BACKEND_TOKEN)headers.Authorization='Bearer '+process.env.DEFI_BACKEND_TOKEN;
    const options={method,headers,redirect:'error',signal:AbortSignal.timeout(22000)};
    if(method==='POST'){
      const origin=req.headers?.origin;
      if(origin&&new URL(origin).host!==req.headers.host)return reply(res,403,{error:'origin_not_allowed'});
      if((req.headers?.['content-type']||'').split(';')[0]!=='application/json')return reply(res,415,{error:'application_json_required'});
      if(Number(req.headers?.['content-length']||0)>4096)return reply(res,413,{error:'request_too_large'});
      let body=req.body;
      if(body===undefined){const chunks=[];let length=0;for await(const chunk of req){length+=chunk.length;if(length>4096)return reply(res,413,{error:'request_too_large'});chunks.push(chunk)}body=Buffer.concat(chunks).toString('utf8');}
      if(Buffer.isBuffer(body))body=body.toString('utf8');
      const parsed=typeof body==='string'?JSON.parse(body):body;
      if(!parsed||Array.isArray(parsed)||typeof parsed!=='object')return reply(res,400,{error:'json_object_required'});
      options.body=JSON.stringify(parsed);
      if(Buffer.byteLength(options.body)>4096)return reply(res,413,{error:'request_too_large'});
      headers['Content-Type']='application/json';headers.Origin=base.origin;
    }
    const dest=new URL(base.href.replace(/\/$/,'')+'/api/'+route);
    for(const [k,v] of url.searchParams)if(k!=='route')dest.searchParams.append(k,v);
    const upstream=await fetch(dest,options);
    if(!upstream.headers.get('content-type')?.includes('application/json'))return reply(res,502,{error:'backend_invalid_response'});
    const reader=upstream.body.getReader();let length=0;const chunks=[];
    for(;;){const {done,value}=await reader.read();if(done)break;length+=value.length;if(length>MAX_BYTES){await reader.cancel();return reply(res,502,{error:'backend_response_too_large'})}chunks.push(Buffer.from(value));}
    const value=JSON.parse(Buffer.concat(chunks).toString('utf8'));
    return reply(res,upstream.status,value);
  }catch(error){
    if(error instanceof SyntaxError)return reply(res,400,{error:'invalid_json'});
    return reply(res,502,{error:'backend_unavailable_or_configuration_invalid'});
  }
}
module.exports=handler;
module.exports.backendURL=backendURL;
module.exports.snapshotStatus=snapshotStatus;
