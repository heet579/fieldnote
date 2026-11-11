'use strict';
const data = JSON.parse(document.getElementById('dataset').textContent);
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const samples = r => r.sample_count ?? 1;
const number = n => n.toLocaleString('en-AU');
const colours = ['#266456','#bd8555','#6389a3'];
const stations = [...new Map(data.observations.map(r => [r.station_id, r.station_name])).entries()].sort();
const parameters = [...new Map(data.observations.map(r => [r.parameter_code, [r.parameter_name, r.canonical_unit]])).entries()].sort();
const years = [...new Set(data.observations.map(r => r.date_key.slice(0,4)))].sort();
const displayNames = {TEMP:'Water temperature',EC:'Electrical conductivity',DO:'Dissolved oxygen',PH:'pH'};
const units = {TEMP:'°C',EC:'µS/cm',DO:'mg/L',PH:'pH'};
const descriptions = {
  TEMP:'How warm was the water? These readings are in degrees Celsius.',
  EC:'How easily did the water conduct electricity? Readings are shown in microsiemens per centimetre, measured at the water temperature.',
  DO:'How much oxygen was measured in the water? Readings are in milligrams per litre.',
  PH:'The acidity or alkalinity of the water, measured in pH units.'
};
stations.forEach(([id,name]) => $('station').add(new Option(name,id)));
parameters.forEach(([id,[name]]) => $('parameter').add(new Option(displayNames[id] || name,id)));
years.forEach(year => $('year').add(new Option(year,year)));
$('parameter').value = parameters.some(([id]) => id === 'TEMP') ? 'TEMP' : parameters[0]?.[0] || '';
$('year').value = 'all';
$('archive-years').textContent = years.length > 1 ? `${years[0]}–${years.at(-1)} records` : `${years[0] || ''} records`;
$('archive-total').textContent = `${number(data.observations.reduce((sum,r)=>sum+samples(r),0))} readings · ${stations.length} locations`;
$('snapshot-date').textContent = `Snapshot ${new Date(data.exported_at).toLocaleDateString('en-AU',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'})}`;

function selectedRows(allLocations=false) {
  return data.observations.filter(r => (allLocations || $('station').value === 'all' || r.station_id === $('station').value)
    && r.parameter_code === $('parameter').value && ($('year').value === 'all' || r.date_key.startsWith($('year').value+'-')));
}
function monthsInView() {
  if ($('year').value !== 'all') return Array.from({length:12},(_,i)=>`${$('year').value}-${String(i+1).padStart(2,'0')}`);
  const dates=data.observations.map(r=>r.date_key).sort();
  if (!dates.length) return [];
  const last=dates.at(-1).slice(0,7), result=[];
  let y=Number(dates[0].slice(0,4)), m=Number(dates[0].slice(5,7));
  while(`${y}-${String(m).padStart(2,'0')}`<=last){result.push(`${y}-${String(m).padStart(2,'0')}`);m++;if(m===13){m=1;y++;}}
  return result;
}
function summarise(rows,month) {
  const part=rows.filter(r=>r.date_key.startsWith(month));
  const n=part.reduce((sum,r)=>sum+samples(r),0);
  return {month,n,mean:n?part.reduce((sum,r)=>sum+r.value*samples(r),0)/n:null,
    min:n?Math.min(...part.map(r=>r.min_value??r.value)):null,
    max:n?Math.max(...part.map(r=>r.max_value??r.value)):null};
}
const monthName = (key,withYear=false) => new Date(`${key}-01T12:00:00Z`).toLocaleDateString('en-AU',{month:'short',...(withYear?{year:'numeric'}:{}),timeZone:'UTC'});
const dateName = key => new Date(`${key}T12:00:00Z`).toLocaleDateString('en-AU',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'});
const decimal = value => value === null ? '—' : value.toFixed(2);

function renderChart(months,series,unit) {
  const points=series.flatMap(s=>s.values.filter(v=>v.mean!==null).map(v=>v.mean));
  if(!points.length){$('chart').innerHTML='<p class="empty">No readings for this selection. Try another year or location.</p>';$('legend').innerHTML='';return;}
  let low=Math.min(...points), high=Math.max(...points);const pad=(high-low||1)*.18;low-=pad;high+=pad;
  const narrow=typeof matchMedia==='function' && matchMedia('(max-width: 600px)').matches;
  const width=narrow?420:1040,left=narrow?43:58,right=narrow?12:24,top=26,bottom=narrow?222:282,height=narrow?262:325;
  const x=i=>left+i*(width-left-right)/Math.max(1,months.length-1);
  const y=value=>bottom-(value-low)/(high-low)*(bottom-top);
  let svg=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Monthly average ${esc($('parameter').value)} in ${esc(unit)}. Exact values follow in the expandable table.">`;
  for(let i=0;i<5;i++){const value=low+(high-low)*i/4;svg+=`<line x1="${left}" x2="${width-right}" y1="${y(value)}" y2="${y(value)}" stroke="#e7ece2"/><text x="${left-12}" y="${y(value)+4}" text-anchor="end" fill="#718075" font-family="system-ui,sans-serif" font-size="12">${value.toFixed(1)}</text>`;}
  const step=months.length>24?(narrow?8:4):months.length>12?(narrow?4:2):(narrow?2:1);
  months.forEach((month,i)=>{
    if(!((i%step===0&&(i===0||months.length-1-i>=step*.65))||i===months.length-1))return;
    const stacked=narrow&&months.length>12;
    const label=stacked?`<tspan x="${x(i)}">${esc(monthName(month))}</tspan><tspan x="${x(i)}" dy="14">${month.slice(0,4)}</tspan>`:esc(monthName(month,months.length>12));
    svg+=`<text x="${x(i)}" y="${height-(stacked?25:12)}" text-anchor="${i===months.length-1?'end':i===0?'start':'middle'}" fill="#718075" font-family="system-ui,sans-serif" font-size="12">${label}</text>`;
  });
  series.forEach(s=>{s.values.forEach((point,i)=>{if(point.mean===null)return;
    if(i&&s.values[i-1].mean!==null)svg+=`<line x1="${x(i-1)}" x2="${x(i)}" y1="${y(s.values[i-1].mean)}" y2="${y(point.mean)}" stroke="${s.colour}" stroke-width="2.8" stroke-linecap="round"/>`;
    svg+=`<circle cx="${x(i)}" cy="${y(point.mean)}" r="${months.length>12?3.5:4.5}" fill="${series.length===1?'#dce8a2':s.colour}" stroke="${s.colour}" stroke-width="1.4"><title>${esc(s.name)} · ${esc(monthName(point.month,true))}: ${decimal(point.mean)} ${esc(unit)} (${number(point.n)} readings)</title></circle>`;
  });});
  $('chart').innerHTML=svg+'</svg>';
  $('legend').innerHTML=series.map(s=>`<span><i style="background:${s.colour}"></i>${esc(s.name)}</span>`).join('');
}

function render() {
  const rows=selectedRows(), param=$('parameter').value, unit=units[param]||parameters.find(([id])=>id===param)?.[1][1]||'';
  const total=rows.reduce((sum,r)=>sum+samples(r),0);
  const dates=rows.map(r=>r.date_key).sort();
  $('count').textContent=number(total);
  $('average-label').textContent=`Average ${param==='TEMP'?'temperature':param==='DO'?'oxygen':param==='EC'?'conductivity':'reading'}`;
  $('average').innerHTML=total?`${(rows.reduce((sum,r)=>sum+r.value*samples(r),0)/total).toFixed(1)} <span class="unit">${esc(unit)}</span>`:'—';
  $('days').textContent=number(new Set(dates).size);
  $('latest').textContent=dates.length?dateName(dates.at(-1)):'No readings';
  $('view-context').textContent=dates.length?`${dateName(dates[0])} – ${dateName(dates.at(-1))} · ${$('station').value==='all'?'All locations':stations.find(([id])=>id===$('station').value)?.[1]}`:'No readings in this selection';
  $('measurement-guide').textContent=descriptions[param]||'Published readings, shown as monthly averages.';
  $('chart-title').textContent=`${displayNames[param]||'The lake'}, month by month`;
  $('chart-caption').textContent=`${unit} · Monthly average of available readings`;
  const months=monthsInView(), summaries=months.map(month=>summarise(rows,month));
  $('monthly').innerHTML=summaries.map(m=>`<tr><td>${esc(monthName(m.month,true))}</td><td>${m.n}</td><td>${decimal(m.mean)}</td><td>${decimal(m.min)}</td><td>${decimal(m.max)}</td></tr>`).join('');
  const compare=$('compare').checked && $('station').value==='all';
  const series=compare?stations.map(([id,name],i)=>({name,colour:colours[i%colours.length],values:months.map(month=>summarise(rows.filter(r=>r.station_id===id),month))})):
    [{name:$('station').value==='all'?'Average across selected locations':stations.find(([id])=>id===$('station').value)?.[1]||'Selected location',colour:colours[0],values:summaries}];
  $('monthly-head').innerHTML=`<tr><th>Month</th>${compare?'<th>Location</th>':''}<th>Readings</th><th>Average</th><th>Lowest</th><th>Highest</th></tr>`;
  if(compare)$('monthly').innerHTML=months.flatMap((month,i)=>series.map(s=>{const m=s.values[i];return `<tr><td>${esc(monthName(month,true))}</td><td>${esc(s.name)}</td><td>${m.n}</td><td>${decimal(m.mean)}</td><td>${decimal(m.min)}</td><td>${decimal(m.max)}</td></tr>`;})).join('');
  renderChart(months,series,unit);
  const locationRows=selectedRows(true);
  $('locations').innerHTML=stations.map(([id,name],i)=>{const part=locationRows.filter(r=>r.station_id===id),n=part.reduce((sum,r)=>sum+samples(r),0),days=new Set(part.map(r=>r.date_key)).size;
    return `<article class="location ${$('station').value===id?'selected':''}"><div class="location-kicker">Location 0${i+1} · ${esc(id)}</div><h3>${esc(name)}</h3><p>${id==='A5041054'?'Near the Adelaide Zoo footbridge.':id==='A5041055'?'Near the Adelaide University footbridge.':id==='A5041056'?'At Torrens Weir.':'Monitoring location.'}</p><p class="location-numbers">${number(n)} readings · ${number(days)} days in this view</p><button type="button" data-station="${esc(id)}">${$('station').value===id?'Viewing this location':'Explore this location'} →</button></article>`;
  }).join('');
}
['station','parameter','year','compare'].forEach(id=>$(id).addEventListener('change',render));
$('locations').addEventListener('click',event=>{const button=event.target.closest('[data-station]');if(button){$('station').value=button.dataset.station;render();$('explore').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});}});
$('download').addEventListener('click',()=>{
  const fields=['station_id','station_name','parameter_code','canonical_unit','date_key','sample_count','daily_mean','lowest_reading','highest_reading'];
  const quote=value=>'"'+String(value??'').replace(/"/g,'""')+'"';
  const csv=[fields,...selectedRows().map(r=>[r.station_id,r.station_name,r.parameter_code,r.canonical_unit,r.date_key,samples(r),r.value,r.min_value??r.value,r.max_value??r.value])].map(row=>row.map(quote).join(',')).join('\r\n');
  const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
  const anchor=document.createElement('a');anchor.href=url;anchor.download=`torrens-lake-${$('parameter').value.toLowerCase()}-${$('year').value}.csv`;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
render();
globalThis.addEventListener?.('resize',render);
