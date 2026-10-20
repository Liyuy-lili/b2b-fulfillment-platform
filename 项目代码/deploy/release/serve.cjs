'use strict';
// Dependency-free local release server: static SPA + streaming same-origin API proxy.
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const [port, backendPort, folder] = process.argv.slice(2);
const root = path.resolve(folder);
const types = { '.html':'text/html; charset=utf-8', '.js':'text/javascript; charset=utf-8', '.css':'text/css; charset=utf-8', '.json':'application/json', '.svg':'image/svg+xml', '.png':'image/png', '.jpg':'image/jpeg', '.ico':'image/x-icon', '.woff2':'font/woff2' };
http.createServer((req,res) => {
  res.setHeader('X-Content-Type-Options','nosniff');
  if (req.url.startsWith('/admin-api/') || req.url.startsWith('/app-api/')) {
    const headers = { ...req.headers, host:'127.0.0.1:'+backendPort }; delete headers.connection;
    const upstream=http.request({ hostname:'127.0.0.1', port:Number(backendPort), path:req.url, method:req.method, headers }, response => { res.writeHead(response.statusCode,response.headers); response.pipe(res); });
    upstream.setTimeout(120000,()=>upstream.destroy());
    upstream.on('error',()=>{if(!res.headersSent)res.writeHead(502,{'Content-Type':'text/plain'});res.end('Backend unavailable');});
    req.on('aborted',()=>upstream.destroy());req.pipe(upstream);return;
  }
  if (!['GET','HEAD'].includes(req.method)) {res.writeHead(405);res.end();return;}
  let name;try{name=decodeURIComponent(req.url.split('?')[0]);}catch{res.writeHead(400);res.end();return;}
  if(name.includes('\0') || name.includes('\\') || name.split('/').includes('..')){res.writeHead(400);res.end();return;}
  let file=path.resolve(root,'.'+name);
  if(file!==root && !file.startsWith(root+path.sep)){res.writeHead(403);res.end();return;}
  if(!fs.existsSync(file) || !fs.statSync(file).isFile()){
    if(path.extname(name)){res.writeHead(404);res.end();return;}
    file=path.join(root,'index.html');
  }
  res.setHeader('Content-Type',types[path.extname(file)] || 'application/octet-stream');
  res.setHeader('Cache-Control',path.extname(file)==='.html'?'no-store':'public, max-age=3600');
  if(req.method==='HEAD'){res.end();return;}
  fs.createReadStream(file).on('error',()=>res.destroy()).pipe(res);
}).listen(Number(port),'127.0.0.1',()=>process.stdout.write('RELEASE_WEB_READY '+port+'\n'));
