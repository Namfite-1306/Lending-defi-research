/** Dependency-free static build. Never crawls, refits, or reads a local data run. */
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {gunzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const source=path.join(root,'deployment/snapshot'), target=path.join(root,'public');
const manifest=JSON.parse(fs.readFileSync(path.join(source,'manifest.json'),'utf8'));
if(manifest.mode!=='frozen_historical'||manifest.live_data_included!==false)throw Error('Invalid deployment snapshot');
fs.mkdirSync(path.join(target,'snapshot'),{recursive:true});
for(const name of fs.readdirSync(path.join(root,'defi_live/web'))){
  if(!/\.(html|css|js)$/.test(name))continue;
  fs.copyFileSync(path.join(root,'defi_live/web',name),path.join(target,name==='overview.html'?'start.html':name));
}
for(const name of ['research','lab','validation']){
  const compressed=fs.readFileSync(path.join(source,name+'.json.gz'));
  const sha=createHash('sha256').update(compressed).digest('hex');
  if(sha!==manifest.files[name+'.json.gz']?.sha256)throw Error('Snapshot checksum mismatch: '+name);
  const raw=gunzipSync(compressed),value=JSON.parse(raw);
  if(value.deployment?.mode!=='frozen_historical')throw Error('Missing historical provenance');
  fs.writeFileSync(path.join(target,'snapshot',name+'.json'),raw);
}
const cascades=fs.readFileSync(path.join(source,'cascade.json.gz'));
if(createHash('sha256').update(cascades).digest('hex')!==manifest.files['cascade.json.gz']?.sha256)throw Error('Cascade checksum mismatch');
JSON.parse(gunzipSync(cascades));
fs.writeFileSync(path.join(target,'snapshot','manifest.json'),JSON.stringify(manifest));
console.log('Static dashboard built: public/; historical evidence verified. Live requires DEFI_BACKEND_URL.');
