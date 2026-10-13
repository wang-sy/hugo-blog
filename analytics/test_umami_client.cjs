const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const { ForegroundClock } = require('../assets/js/analytics-core.js');
function setup({host='wangsaiyu.com',cookie='',dnt='0'}={}) {
  const sent=[], scripts=[], listeners={}; let now=0;
  const config={websiteId:'example-id',host:'https://stats.wangsaiyu.com',path:'/posts/example/',track:true,article:false};
  const node={textContent:JSON.stringify(config),dataset:{}};
  const doc={cookie,hidden:false,hasFocus:()=>true,getElementById:id=>id==='blog-analytics-config'?node:null,createElement:()=>({dataset:{}}),head:{appendChild:s=>scripts.push(s)},addEventListener:(k,v)=>listeners[k]=v};
  const window={BlogAnalyticsCore:{ForegroundClock},addEventListener:(k,v)=>listeners[k]=v,umami:{track:async (name,data)=>sent.push(typeof name==='function'?name({url:'/wrong?secret=1',referrer:'https://search.example/private?secret=1'}):{name,data})}};
  const ctx={document:doc,window,location:{hostname:host,origin:'https://'+host},navigator:{userAgent:'Mozilla/5.0 Chrome/140',doNotTrack:dnt},crypto:{randomUUID:()=> '41e482fb-f6e7-4e18-a021-4fdc4d7f943a'},performance:{now:()=>now},setInterval:()=>{},URL,Intl};
  vm.runInNewContext(fs.readFileSync('assets/js/blog-analytics.js','utf8'),ctx);
  return {scripts,sent,window,node,listeners,doc,setTime:n=>now=n};
}
test('one pageview, cumulative reading events, and query/referrer redaction',async()=>{
  const c=setup(); assert.equal(c.scripts.length,1); assert.equal(c.scripts[0].dataset.autoTrack,'false');
  c.scripts[0].onload(); await Promise.resolve();
  assert.equal(c.sent.length,1); assert.equal(c.sent[0].data.active_ms,0);
  const p=c.window.blogBeforeSend('event',{url:'/wrong?q=secret',referrer:'https://search.example/private?q=secret'});
  assert.equal(p.url,'/posts/example/'); assert.equal(p.hostname,'www.wangsaiyu.com'); assert.equal(p.referrer,'https://search.example/');
  c.setTime(1000); c.listeners.blur(); c.doc.hidden=true; c.setTime(20000); c.listeners.visibilitychange();
  assert.equal(c.sent.length,2); assert.equal(c.sent[1].data.active_ms,1000);
  c.listeners.pagehide(); assert.equal(c.sent.length,2);
});
test('opt-out, DNT and local previews never load the analytics tracker',()=>{
  for(const config of [{cookie:'saiyudoc_stats_optout=1'},{dnt:'1'},{host:'localhost'}]) assert.equal(setup(config).scripts.length,0);
});
