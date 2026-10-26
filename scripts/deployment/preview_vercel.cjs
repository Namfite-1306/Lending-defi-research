/** Local preview of the static files + API adapter, not a Vercel cloud deployment. */
const http=require('node:http'),fs=require('node:fs'),path=require('node:path');
const handler=require('../../api/index.js');
const root=path.resolve(__dirname,'../../public');
const port=Number(process.env.PREVIEW_PORT||8791);
http.createServer(async(req,res)=>{
 const u=new URL(req.url,'http://127.0.0.1');
 const jsonRoutes={'/api/research':'research','/api/lab/data':'lab','/api/validation':'validation'};
 let file;
 if(jsonRoutes[u.pathname])file=path.join(root,'snapshot',jsonRoutes[u.pathname]+'.json');
 else if(u.pathname.startsWith('/api/')){req.query=Object.fromEntries(u.searchParams);req.query.route=u.pathname.slice(5);return handler(req,res)}
 else{let rel=u.pathname==='/'?'index.html':u.pathname.slice(1);if(!path.extname(rel))rel+='.html';file=path.resolve(root,rel);}
 if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);return res.end('Not found')}
 const ext=path.extname(file),mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json'}[ext]||'application/octet-stream';
 res.writeHead(200,{'Content-Type':mime+'; charset=utf-8','Cache-Control':'no-store'});fs.createReadStream(file).pipe(res);
}).listen(port,'127.0.0.1',()=>console.log('Local Vercel adapter preview: http://127.0.0.1:'+port));
