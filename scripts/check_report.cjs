// Check the real explorer against independent raw-fact SQL monthly references.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync(process.argv[2]||'portfolio/dashboard.html','utf8');
const payload=html.match(/<script id="dataset" type="application\/json">([\s\S]*?)<\/script>/)[1];
const data=JSON.parse(payload),code=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
const elements=new Map();
function getElementById(id){
 if(!elements.has(id))elements.set(id,{value:['station','year'].includes(id)?'all':'',checked:false,textContent:id==='dataset'?payload:'',innerHTML:'',options:[],events:{},
 add(option){this.options.push(option);if(!this.value)this.value=option.value;},addEventListener(name,fn){this.events[name]=fn;}});
 return elements.get(id);
}
const context=vm.createContext({document:{getElementById},Option:function(text,value){this.text=text;this.value=value;},console});
vm.runInContext(code,context);
const number=id=>Number(String(getElementById(id).textContent).replaceAll(',',''));
let refs;
if(data.source?.real){
 refs=JSON.parse(fs.readFileSync('portfolio/monthly-reference.json','utf8'));
 assert.equal(number('count'),337560);
 assert.ok(!/portfolio|recruitment|job role|DEW affiliation/i.test(html.split('<script')[0]));
}else{
 const groups=new Map();
 for(const r of data.observations){const key=[r.station_id,r.parameter_code,r.date_key.slice(0,7)].join('|');if(!groups.has(key))groups.set(key,[]);groups.get(key).push(r.value);}
 refs=[...groups].map(([key,v])=>{const [station_id,parameter_code,month]=key.split('|');return {station_id,parameter_code,month,n:v.length,mean:v.reduce((a,b)=>a+b,0)/v.length,min:Math.min(...v),max:Math.max(...v)};});
}
const stations=['all',...new Set(refs.map(r=>r.station_id))],params=[...new Set(refs.map(r=>r.parameter_code))],years=['all',...new Set(refs.map(r=>r.month.slice(0,4)))].sort();
let combinations=0,monthlyChecks=0;
for(const year of years)for(const station of stations)for(const param of params){
 getElementById('year').value=year;getElementById('station').value=station;getElementById('parameter').value=param;getElementById('year').events.change();
 const subset=refs.filter(r=>(station==='all'||r.station_id===station)&&r.parameter_code===param&&(year==='all'||r.month.startsWith(year+'-')));
 assert.equal(number('count'),subset.reduce((a,r)=>a+r.n,0));
 const cells=[...getElementById('monthly').innerHTML.matchAll(/<tr><td>(.*?)<\/td><td>(.*?)<\/td><td>(.*?)<\/td><td>(.*?)<\/td><td>(.*?)<\/td><\/tr>/g)];
 const months=year==='all'?[...new Set(refs.map(r=>r.month))].sort():Array.from({length:12},(_,i)=>`${year}-${String(i+1).padStart(2,'0')}`);
 assert.equal(cells.length,months.length);
 for(let i=0;i<months.length;i++){
  const selected=subset.filter(r=>r.month===months[i]),n=selected.reduce((a,r)=>a+r.n,0);
  assert.equal(Number(cells[i][2]),n);
  if(n){const expected={mean:selected.reduce((a,r)=>a+r.mean*r.n,0)/n,min:Math.min(...selected.map(r=>r.min)),max:Math.max(...selected.map(r=>r.max))};
   for(const [index,key]of [[3,'mean'],[4,'min'],[5,'max']])assert.ok(Math.abs(Number(cells[i][index])-expected[key])<=.00501,`Mismatch ${year}/${station}/${param}/${months[i]}/${key}`);
  }else{assert.equal(cells[i][3],'—');}
  monthlyChecks++;
 }
 combinations++;
}
getElementById('station').value='all';getElementById('year').value='all';getElementById('compare').checked=true;getElementById('compare').events.change();
assert.equal((getElementById('legend').innerHTML.match(/<span>/g)||[]).length,stations.length-1);
getElementById('year').value='2024';getElementById('year').events.change();assert.equal(number('count'),0);assert.equal(number('days'),0);assert.equal(getElementById('latest').textContent,'No readings');
console.log(`Explorer checks passed: ${combinations} filter combinations, ${monthlyChecks} monthly reconciliations, location comparison and empty selection.`);
