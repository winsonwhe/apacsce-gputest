'use strict';
const state = {nodes: [], runs: [], catalog: null, current: null, timer: null};
const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}
function notice(message) { const t=$('toast'); t.textContent=message; t.classList.add('show'); setTimeout(()=>t.classList.remove('show'),4000); }
function view(name) { document.querySelectorAll('.view').forEach(el=>el.classList.toggle('active-view',el.id===`view-${name}`)); document.querySelectorAll('.nav-item').forEach(el=>el.classList.toggle('active',el.dataset.view===name)); $('page-title').textContent=({overview:'Overview',nodes:'GPU nodes','new-run':'New test run',history:'Run history'})[name]; }
function renderNodes() {
  $('node-input').value=state.nodes.map(n=>`${n.user ? n.user+'@' : ''}${n.host}${n.port!==22 ? ':'+n.port : ''}`).join('\n');
  $('node-grid').innerHTML=state.nodes.map(n=>`<article class="panel node-card"><div class="node-card-header"><div class="node-card-title"><span class="node-avatar">G</span><div><h3>${escapeHtml(n.host)}</h3><p>${escapeHtml(n.user || 'Default SSH user')} · port ${n.port}</p></div></div><span class="status-pill skip">Configured</span></div></article>`).join('') || '<p class="help">No nodes configured yet.</p>';
  $('node-select-list').innerHTML=state.nodes.map(n=>`<label class="node-checkbox"><input type="checkbox" value="${escapeHtml(n.host)}" checked> ${escapeHtml(n.host)}</label>`).join('') || '<p class="help">Configure nodes first.</p>';
}
function renderChecks() {
  const level = $('level').value;
  const selected = new Set(state.catalog.levels[`${$('sku').value}_${level}`] || state.catalog.levels[level] || []);
  $('checks-list').innerHTML=state.catalog.checks.map(c=>`<label class="check-row"><input type="checkbox" value="${escapeHtml(c.name)}" ${selected.has(c.name)?'checked':''}><div><strong>${escapeHtml(c.name)}</strong><small>${c.multi_host?'Multi-host · ':''}${escapeHtml(c.skus ? c.skus.join(', ') : 'All SKUs')}</small></div><span class="check-category">${escapeHtml(c.category)}</span></label>`).join('');
  updateCount();
}
function updateCount(){ $('check-count').textContent=document.querySelectorAll('#checks-list input:checked').length; }
function renderRuns(){
  const rows=state.runs.map(r=>`<tr><td><button class="text-button" data-run="${escapeHtml(r.id)}">${escapeHtml(r.id.slice(0,12))}</button></td><td>${new Date(r.created_at*1000).toLocaleString()}</td><td>${escapeHtml(r.sku)} / ${escapeHtml(r.level)}</td><td>${r.nodes.length}</td><td>${escapeHtml(r.status)}</td></tr>`).join('');
  const table=`<table><thead><tr><th>Run</th><th>Created</th><th>Profile</th><th>Nodes</th><th>Job status</th></tr></thead><tbody>${rows}</tbody></table>`;
  $('history-table').innerHTML=state.runs.length?table:'<p class="empty">No runs yet.</p>';
  $('recent-runs').innerHTML=state.runs.length?table:'<p class="empty">No runs yet. Configure a node and start a dry run.</p>';
  $('stats').innerHTML=[['Configured nodes',state.nodes.length],['Total runs',state.runs.length],['Running',state.runs.filter(r=>['created','running'].includes(r.status)).length],['Completed jobs',state.runs.filter(r=>r.status==='completed').length]].map(([label,value])=>`<article class="stat-card"><div class="stat-label">${label}</div><div class="stat-value">${value}</div></article>`).join('');
}
async function refresh(){ const [n,r]=await Promise.all([api('/api/nodes'),api('/api/runs')]); state.nodes=n.nodes; state.runs=r.runs; renderNodes(); renderRuns(); }
async function details(id){
  state.current=id; const data=await api(`/api/runs/${id}`); const job=data.job; view('history'); $('run-detail').hidden=false; $('detail-title').textContent=`Run ${id.slice(0,12)}`; $('detail-status').textContent=`${job.status} · ${job.sku} / ${job.level}${job.dry_run?' · Dry run':job.mock?' · Mock':''}`; $('run-log').textContent=data.log || 'Waiting for output…'; $('report-link').href=`/api/runs/${id}/markdown`; $('report-link').hidden=!data.result;
  const checks=data.result?.checks || []; const counts=['PASS','WARN','FAIL','SKIP'].map(s=>`${s}: ${checks.filter(c=>c.status===s).length}`); $('result-summary').textContent=checks.length?`${checks.length} checks · ${counts.join(' · ')}`:'No completed results yet.';
  $('result-checks').innerHTML=checks.map(c=>`<details class="result-check"><summary><span class="status-pill ${escapeHtml(c.status.toLowerCase())}">${escapeHtml(c.status)}</span> ${escapeHtml(c.name)} — ${escapeHtml(c.message)}</summary><pre>${escapeHtml(JSON.stringify({metrics:c.metrics,thresholds:c.thresholds,hints:c.hints},null,2))}</pre>${c.raw_output_file?`<a class="text-button" target="_blank" rel="noopener" href="/api/runs/${id}/raw?file=${encodeURIComponent(c.raw_output_file)}">Open raw command and output →</a>`:''}</details>`).join('');
  clearTimeout(state.timer); if(['created','running'].includes(job.status)) state.timer=setTimeout(()=>details(id).catch(e=>notice(e.message)),2000);
}
function parseNodes(text){return text.split(/\n/).map(x=>x.trim()).filter(Boolean).map(line=>{const m=line.match(/^(?:([A-Za-z0-9_][A-Za-z0-9_.-]*)@)?([A-Za-z0-9_][A-Za-z0-9_.-]*)(?::(\d+))?$/); if(!m)throw new Error(`Invalid target: ${line}`); return {host:m[2],user:m[1]||'',port:m[3]?Number(m[3]):22};});}
document.addEventListener('click',async e=>{try{const nav=e.target.closest('[data-view]');if(nav){view(nav.dataset.view);return}const run=e.target.closest('[data-run]');if(run){await details(run.dataset.run);return}if(e.target.id==='save-nodes'){await api('/api/nodes',{nodes:parseNodes($('node-input').value)});await refresh();notice('Nodes saved.')}if(e.target.id==='upload-key'){const file=$('ssh-key').files[0];if(!file)throw new Error('Choose a private key file first.');await api('/api/ssh-key',{private_key:await file.text()});$('ssh-key').value='';notice('Private key stored on controller.')}if(e.target.id==='start-run'){const nodes=[...document.querySelectorAll('#node-select-list input:checked')].map(x=>x.value),tests=[...document.querySelectorAll('#checks-list input:checked')].map(x=>x.value),mode=$('mode').value;if(mode==='real'&&!confirm('Start real GPU tests on the selected nodes?'))return;const result=await api('/api/runs',{sku:$('sku').value,level:$('level').value,network_mode:$('network').value,nodes,tests,dry_run:mode==='dry_run',mock:mode==='mock'});await refresh();await details(result.job.id)}}catch(error){notice(error.message)}});
document.addEventListener('change',e=>{if(e.target.id==='level'||e.target.id==='sku')renderChecks();if(e.target.closest('#checks-list'))updateCount();});
(async()=>{try{state.catalog=await api('/api/checks');$('sku').innerHTML=state.catalog.skus.map(s=>`<option value="${escapeHtml(s)}" ${s==='gb300'?'selected':''}>${escapeHtml(s)}</option>`).join('');$('level').innerHTML=['basic','standard','extended'].filter(l=>state.catalog.levels[l]).map(l=>`<option value="${l}" ${l==='standard'?'selected':''}>${l}</option>`).join('');renderChecks();await refresh();$('connection-status').textContent='Connected';}catch(error){$('connection-status').textContent='Unavailable';notice(`Controller unavailable: ${error.message}`)}})();
