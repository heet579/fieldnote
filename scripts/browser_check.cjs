// Native Node.js + Edge DevTools QA. Only an isolated, task-owned browser is used.
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {spawn} = require('node:child_process');
const assert = require('node:assert/strict');
const markup=fs.readFileSync('site/index.html','utf8');
const dataset=JSON.parse(markup.match(/<script id="dataset" type="application\/json">([\s\S]*?)<\/script>/)[1]);
const defaultCount=dataset.observations.filter(r=>r.parameter_code==='TEMP').reduce((sum,r)=>sum+r.sample_count,0).toLocaleString('en-AU');
const sleep = ms => new Promise(resolve=>setTimeout(resolve,ms));
const profile = path.resolve('runtime','edge-qa-'+Date.now());
fs.mkdirSync(profile,{recursive:true});
const child = spawn('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
 ['--headless=new','--disable-gpu','--disable-extensions','--no-first-run',
  '--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],
 {windowsHide:true,stdio:'ignore'});
let socket;
(async()=>{
 for(let i=0;i<150&&!fs.existsSync(path.join(profile,'DevToolsActivePort'));i++) await sleep(100);
 const port=fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0];
 const target=await(await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'})).json();
 socket=new WebSocket(target.webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
 let sequence=0; const pending=new Map(),exceptions=[];
 socket.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.id){const entry=pending.get(message.id);if(entry){pending.delete(message.id);message.error?entry.reject(new Error(JSON.stringify(message.error))):entry.resolve(message.result);}}else if(message.method==='Runtime.exceptionThrown')exceptions.push(message.params);});
 const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
 const evaluate=async(expression)=>{const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true,userGesture:true});if(result.exceptionDetails)throw new Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
 await send('Page.enable'); await send('Runtime.enable');
 const checks=[];
 for(const [width,height,name] of [[1440,1800,'dashboard-preview.png'],[390,1800,'dashboard-mobile.png']]){
  await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:width<500});
  await send('Page.navigate',{url:pathToFileURL(path.resolve('site/index.html')).href});
  for(let i=0;i<100;i++){if(await evaluate(`document.readyState==='complete' && document.getElementById('count')?.textContent===${JSON.stringify(defaultCount)}`))break;await sleep(100);}
  const state=await evaluate("({width:innerWidth,scroll:document.documentElement.scrollWidth,count:document.getElementById('count').textContent,body:document.body.scrollWidth})");
  assert.equal(state.count,defaultCount);
  assert.ok(state.scroll<=width,`Horizontal overflow at ${width}px: ${JSON.stringify(state)}`);
  assert.equal(await evaluate("/portfolio|job role|DEW affiliation|recruitment/i.test(document.body.innerText)"),false);
  const screenshot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  fs.writeFileSync(path.resolve('portfolio',name),Buffer.from(screenshot.data,'base64'));
  await evaluate("document.getElementById('station').value='A5041055';document.getElementById('parameter').value='DO';document.getElementById('year').value='2017';document.getElementById('parameter').dispatchEvent(new Event('change'));");
  assert.equal(await evaluate("document.getElementById('count').textContent"),'34,368');
  await evaluate("document.querySelector('#monitoring details').open=true;");
  assert.equal(await evaluate("document.getElementById('monthly').children.length"),12);
  await evaluate("document.getElementById('station').value='all';document.getElementById('year').value='all';document.getElementById('compare').checked=true;document.getElementById('compare').dispatchEvent(new Event('change'));");
  assert.equal(await evaluate("document.getElementById('legend').children.length"),3);
  assert.equal(await evaluate("document.getElementById('monthly').children.length"),120);
  assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),'All-years chart overflow');
  await evaluate("document.querySelector('[data-station=\"A5041054\"]').click()");
  assert.equal(await evaluate("document.getElementById('station').value"),'A5041054');
  checks.push({viewport:width,overflow:false,default_count:state.count,filtered_count:'34,368',all_years_months:40,comparison_table_rows:120,comparison_series:3,location_card_works:true,retired_branding:false});
 }
 const downloads=path.resolve(profile,'downloads');fs.mkdirSync(downloads,{recursive:true});
 await send('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:downloads});
 await evaluate("document.getElementById('station').value='A5041055';document.getElementById('parameter').value='DO';document.getElementById('year').value='2017';document.getElementById('year').dispatchEvent(new Event('change'));document.getElementById('download').click();");
 const filename=path.join(downloads,'torrens-lake-do-2017.csv');
 for(let i=0;i<100&&!fs.existsSync(filename);i++)await sleep(100);
 assert.ok(fs.existsSync(filename),'Filtered CSV did not download');
 const csv=fs.readFileSync(filename,'utf8').trim().split(/\r?\n/);
 assert.equal(csv.length,359);
 assert.equal(csv.slice(1).reduce((sum,line)=>sum+Number(line.split(',')[5].replaceAll('"','')),0),34368);
 await send('Page.navigate',{url:pathToFileURL(path.resolve('site/about.html')).href});
 for(let i=0;i<100;i++){if(await evaluate("document.readyState==='complete' && document.title.includes('About the data')"))break;await sleep(100);}
 assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),'About page overflow');
 assert.equal(await evaluate("/portfolio|job role|DEW affiliation|recruitment/i.test(document.body.innerText)"),false);
 assert.equal(exceptions.length,0,JSON.stringify(exceptions));
 fs.writeFileSync('portfolio/browser-verification.json',JSON.stringify({browser:'Microsoft Edge headless / DevTools device metrics',checks,about_page_mobile_overflow:false,filtered_csv_rows:358,filtered_csv_readings:34368,javascript_exceptions:exceptions.length},null,2));
 console.log(JSON.stringify({status:'passed',checks,about_page_mobile_overflow:false,filtered_csv_rows:358,javascript_exceptions:exceptions.length},null,2));
 await send('Browser.close').catch(()=>{});
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>{socket?.close();child.kill();});
