const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const {gunzipSync}=require('node:zlib');
const findings=require('../defi_live/web/findings.js');
const handler=require('../api/index.js');
const research=JSON.parse(gunzipSync(fs.readFileSync('deployment/snapshot/research.json.gz')));
test('New robustness evidence preserves scope and discloses failed readiness gates',()=>{
 assert.equal(research.robustness.summary.production_forecast_ready,false);
 assert.equal(research.robustness.h1_audit.length,13);
 assert.equal(research.robustness.h2_intervals.length,216);
 assert.equal(research.robustness.h3.length,6);
 assert.equal(research.robustness.cascade_window_coverage.length,9);
 assert.match(findings.h3(research).followup,/1,032.*không được chọn/);
 assert.equal(research.robustness.cascade_summary.end_to_end_validated,false);
});
function request(route,options={}){return {url:'/api/'+route,query:{route:route.split('?')[0]},method:'GET',headers:{host:'example.vercel.app'},...options};}
async function invoke(req){const result={};const res={setHeader(k,v){(result.headers??={})[k]=v},end(body){result.body=JSON.parse(body);result.status=this.statusCode}};await handler(req,res);return result;}
test('H1 finding matches all 13 primary snapshots and updates the factor',()=>{
 const original=JSON.stringify(research);
 const f=findings.h1(research,{quarter:'2026Q1',scenario:'joint',mapping:'factor_family_1to1'});
 assert.match(f.headline,/0,58%.*7,00%/);assert.equal(f.metrics[0][1],'13');assert.equal(f.metrics[1][1],'14,00%–34,00%');
 assert.equal(JSON.stringify(research),original);
 assert.notEqual(findings.h1(research,{quarter:'2026Q1',scenario:'BTC_only',mapping:'direct_WETH_WBTC_only'}).headline,f.headline);
 assert.match(findings.h1({},{scenario:'none'}).headline,/Chưa đủ/);
});
test('H2 finding uses selected support/metric, excludes small Morpho ranking',()=>{
 const rows=research.source_stage.concentration.filter(r=>r.window==='calendar_2024'&&r.token==='0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'&&r.metric==='market_USD'&&r.support==='market_fresh'&&r.max_age_seconds==='300');
 const f=findings.h2(research,{rows,scope:'WETH/USDC 2024'});
 assert.match(f.headline,/55,99%–67,99%/);assert.equal(f.metrics.length,2);assert.match(f.limit,/Morpho Blue.*mẫu nhỏ/);
 assert.match(findings.h2(research,{rows:rows.filter(r=>r.protocol==='morpho_blue')}).headline,/Chưa đủ/);
});
test('H3 distinguishes score gain from failed calibration and requires common support',()=>{
 const f=findings.h3(research);assert.match(f.headline,/chưa đạt calibration/);assert.equal(f.metrics[0][1],'+282,06');assert.equal(f.metrics[1][1],'1,460');
 const other=structuredClone(research);other.source_stage.models.find(r=>r.model==='activity').test_bins='1';
 assert.equal(findings.h3(other).metrics[0][1],'Không cùng support');
});
test('Cascade finding uses the selected pair/route scenario and does not claim calibration',()=>{
 const f=findings.cascade(research,{date:'2024-08-05',shock:.1});assert.match(f.headline,/1,087 lần/);assert.match(f.limit,/chưa được hiệu chỉnh/);
 assert.match(findings.cascade(research,{date:'1900-01-01',shock:.1}).headline,/Chưa đủ/);
});
test('Vercel framework/build routes use static payloads rather than Python auto detection',()=>{
 const c=JSON.parse(fs.readFileSync('vercel.json'));assert.equal(c.framework,null);assert.match(c.buildCommand,/build_vercel.mjs/);assert.equal(c.outputDirectory,'public');
 for(const route of ['/api/research','/api/lab/data','/api/validation'])assert.match(c.rewrites.find(r=>r.source===route).destination,/^\/snapshot\//);
 const m=JSON.parse(fs.readFileSync('deployment/snapshot/manifest.json'));assert.equal(m.live_data_included,false);
});
test('Unconfigured Vercel backend never pretends cached research is live',async()=>{
 const old=process.env.DEFI_BACKEND_URL;delete process.env.DEFI_BACKEND_URL;
 try{const s=await invoke(request('status'));assert.equal(s.status,200);assert.equal(s.body.state,'snapshot_only');assert.equal(s.body.cursor,null);assert.equal(s.body.models.state,'unavailable');
 const c=await invoke(request('deployment'));assert.equal(c.body.whatif_enabled,false);
 const p=await invoke(request('lab/simulate',{method:'POST'}));assert.equal(p.status,503);
 assert.equal((await invoke(request('../anything'))).status,404);
 }finally{if(old===undefined)delete process.env.DEFI_BACKEND_URL;else process.env.DEFI_BACKEND_URL=old}
});
test('Proxy accepts only fixed public HTTPS backend configuration',()=>{
 for(const bad of ['http://api.example.com','https://localhost','https://127.0.0.1','https://10.1.2.3','https://user:secret@example.com','https://example.com?key=secret'])assert.throws(()=>handler.backendURL(bad));
 assert.equal(handler.backendURL('https://api.example.com').hostname,'api.example.com');
});
test('Proxy rejects cross-origin POST and oversized parsed bodies before contacting upstream',async()=>{
 const old=process.env.DEFI_BACKEND_URL;process.env.DEFI_BACKEND_URL='https://api.example.com';
 try{
  assert.equal((await invoke(request('lab/simulate',{method:'POST',headers:{host:'example.vercel.app',origin:'https://evil.example','content-type':'application/json'},body:{}}))).status,403);
  assert.equal((await invoke(request('lab/simulate',{method:'POST',headers:{host:'example.vercel.app','content-type':'application/json'},body:{x:'a'.repeat(5000)}}))).status,413);
 }finally{if(old===undefined)delete process.env.DEFI_BACKEND_URL;else process.env.DEFI_BACKEND_URL=old}
});
test('Proxy forwards only allowed paths and server token, never browser cookies',async()=>{
 const old=process.env.DEFI_BACKEND_URL,token=process.env.DEFI_BACKEND_TOKEN,original=global.fetch;
 process.env.DEFI_BACKEND_URL='https://api.example.com';process.env.DEFI_BACKEND_TOKEN='test-only';
 let call;global.fetch=async(url,opts)=>{call={url:String(url),opts};return new Response(JSON.stringify({state:'stale'}),{headers:{'Content-Type':'application/json'}})};
 try{const r=await invoke(request('status?hours=24',{headers:{host:'example.vercel.app',cookie:'private-browser-cookie'}}));assert.equal(r.body.state,'stale');assert.match(call.url,/\/api\/status\?hours=24$/);assert.equal(call.opts.headers.Authorization,'Bearer test-only');assert.equal(call.opts.headers.Cookie,undefined);assert.equal(call.opts.redirect,'error');}
 finally{global.fetch=original;if(old===undefined)delete process.env.DEFI_BACKEND_URL;else process.env.DEFI_BACKEND_URL=old;if(token===undefined)delete process.env.DEFI_BACKEND_TOKEN;else process.env.DEFI_BACKEND_TOKEN=token}
});
test('Frozen cascade query is bounded and validates selectors',async()=>{
 assert.equal((await invoke(request('research/cascade?date=../../secret&shock=0.2&feedback=true'))).status,400);
 const r=await invoke(request('research/cascade?date=2024-08-05&shock=0.1&feedback=true'));assert.equal(r.status,200);assert.equal(r.body.available,true);
});
