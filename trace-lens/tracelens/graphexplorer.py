"""Single-file graph explorer: clone, run, SEE THE GRAPH.

Consumes one or more ``graphexport.py`` JSON files (live Cypher read-back of
persisted Relate stores) and renders a self-contained HTML file. Judges can:

  * switch between the single-scenario provenance graph and the 8-package
    batch scan graph;
  * click any node to inspect EVERY property stored on it, plus its in/out
    edges — proof that this is a real graph, not a diagram;
  * highlight the exact multi-hop paths Q6 / Q7 / Q8 returned in this run;
  * read the hop-level wall-clock audit (which hop was already stale);
  * audit the export's own consistency checks.

Zero external resources: all CSS, JS, data and SVG are inline. No CDN, no
fonts, no images, no network calls. Safe to open offline by double-click.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

LABEL_COLORS: dict[str, str] = {
    "Run": "#1a5fb4", "Answer": "#6d3fb5", "Span": "#0f766e",
    "Source": "#b45309", "Claim": "#a32d2d", "PkgVersion": "#2563eb",
    "Advisory": "#be123c", "Lockfile": "#475569",
}
DEFAULT_COLOR = "#5b6475"

_STYLE = """
:root{color-scheme:light;--ink:#1d2330;--muted:#5b6475;--line:#e2e6ee;
      --bg:#f7f8fa;--blue:#1a5fb4;--green:#17693a;--red:#a32d2d;--amber:#b45309;}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:0;padding:24px 28px 48px;
     background:var(--bg);color:var(--ink);line-height:1.5}
h1{font-size:22px;font-weight:650;margin:0 0 4px}
h2{font-size:15px;font-weight:650;margin:0 0 10px}
.sub{color:var(--muted);font-size:13px;margin:3px 0 0}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px 18px;margin-bottom:14px}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
button{font:inherit;font-size:12px;padding:6px 12px;border:1px solid var(--line);
       background:#fff;border-radius:6px;cursor:pointer;color:var(--ink)}
button:hover{background:#f1f3f7}
button.active{background:#eef3fb;border-color:#cbdcf5;color:var(--blue)}
button.mode.active{background:#fdf1e8;border-color:#eecfa8;color:var(--amber)}
.layout{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:14px;align-items:start}
.canvas{background:#fff;border:1px solid var(--line);border-radius:10px;
        overflow:auto;max-height:76vh;position:relative}
svg{display:block;font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
.edge{stroke:#cbd3e0;stroke-width:1.3;fill:none}
.edge.hl{stroke-width:2.6}
.node{cursor:pointer}
.node circle{stroke:#fff;stroke-width:2}
.node text{font-size:10px;fill:#39414f;pointer-events:none}
.node.dim{opacity:.16}
.edge.dim{opacity:.09}
.node.hit circle{stroke:#101828;stroke-width:3}
.side{display:flex;flex-direction:column;gap:14px}
table{border-collapse:collapse;width:100%;font-size:12px}
th,td{text-align:left;padding:5px 7px;border-bottom:1px solid #edf0f5;vertical-align:top;
      word-break:break-word}
th{color:var(--muted);font-weight:600;white-space:nowrap}
code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px;
     background:#f1f3f7;border-radius:4px;padding:1px 4px}
.badge{display:inline-block;font-size:11px;font-weight:650;padding:2px 8px;border-radius:999px}
.pass{background:#e6f4ea;color:var(--green)}
.fail{background:#fce8e6;color:var(--red)}
.tag{display:inline-block;background:#eef3fb;border:1px solid #cbdcf5;color:var(--blue);
     border-radius:5px;padding:1px 6px;font-size:10px;margin:2px 4px 2px 0;font-weight:600}
.legend span{display:inline-block;margin:0 12px 6px 0;font-size:12px;color:var(--muted)}
.legend i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px}
.chip{display:inline-block;font-family:ui-monospace,monospace;font-size:11px;
      background:#f1f3f7;border-radius:5px;padding:2px 6px;margin:2px}
.arrow{color:#8a93a5;margin:0 4px}
.hop{border-left:3px solid var(--line);padding:4px 0 8px 10px;margin:6px 0;font-size:12px}
.hop.stale{border-left-color:var(--red)}
.hop.fresh{border-left-color:var(--green)}
.muted{color:var(--muted);font-size:11px}
.callout{border-left:4px solid var(--blue);background:#f4f8ff;border-radius:6px;
         padding:9px 13px;font-size:12px;margin:9px 0}
input[type=search]{font:inherit;font-size:12px;padding:6px 10px;border:1px solid var(--line);
                   border-radius:6px;width:230px;color:var(--ink);background:#fff}
input[type=text]{font:inherit;font-size:12px;padding:6px 10px;border:1px solid var(--line);
                 border-radius:6px;width:250px;color:var(--ink);background:#fff}
.lg-results{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.lg-hit{font-size:11px;padding:4px 8px}
.lg-jump{cursor:pointer}
.lg-toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px}
[hidden]{display:none!important}
"""

_JS = """
const GRAPHS = __GRAPHS__;
let active = 0;
const $ = (s, r=document) => r.querySelector(s);
const $$ = (s, r=document) => Array.from(r.querySelectorAll(s));
const LARGE = 1500;
const isLarge = i => GRAPHS[i].counts.nodes > LARGE;
const lgAdj = {};

function esc(v){return String(v==null?'':v).replace(/[&<>"']/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}

function nodePanel(id){
  const g = GRAPHS[active];
  const n = g.nodes.find(x=>x.id===id);
  if(!n) return '<p class="muted">点击任意节点查看其属性。</p>';
  const ins = g.edges.filter(e=>e.target===id), outs = g.edges.filter(e=>e.source===id);
  let h = '<h2>节点属性</h2><p class="muted"><code>'+esc(n.id)+'</code></p>';
  h += '<table><tr><th>label</th><td>'+esc(n.label)+'</td></tr>';
  for(const [k,v] of Object.entries(n.props)){
    h += '<tr><th>'+esc(k)+'</th><td><code>'+esc(typeof v==='object'?JSON.stringify(v):v)+'</code></td></tr>';
  }
  h += '</table><h2 style="margin-top:14px">连接关系</h2>';
  if(!ins.length && !outs.length) h += '<p class="muted">无连接</p>';
  for(const e of outs.slice(0,40)) h += '<div class="chip">→ '+esc(e.type)+' → '+esc(e.target)+'</div>';
  for(const e of ins.slice(0,40)) h += '<div class="chip">← '+esc(e.type)+' ← '+esc(e.source)+'</div>';
  if(ins.length+outs.length>80) h += '<p class="muted">…共 '+esc(ins.length+outs.length)+' 条，仅列前 80。</p>';
  return h;
}

function highlightPanel(mode){
  const g = GRAPHS[active], H = g.highlights;
  let h = '';
  if(mode==='Q6'){
    h = '<h2>Q6 · 多跳溯源路径</h2>';
    if(!H.Q6_provenance.length) h += '<p class="muted">该 store 本轮无 Q6 路径明细。</p>';
    for(const p of H.Q6_provenance){
      h += '<div class="callout">'+esc(p.claim_text||'')+'<br><span class="muted">'+
           esc(p.advisory_id||'')+' · '+esc(p.hops)+' hops · 路径节点全部来自导出图：'+
           (p.resolved?'是':'否')+'</span></div>';
      h += '<div>'+p.nodes.map((n,i)=>'<span class="chip">'+esc(n)+'</span>'+
           (p.rels[i]?'<span class="arrow">'+esc(p.rels[i])+'→</span>':'')).join('')+'</div>';
    }
  } else if(mode==='Q7'){
    h = '<h2>Q7 · 逐跳时间审计</h2>';
    if(!H.Q7_hop_audit.length) h += '<p class="muted">该 store 本轮无 Q7 跳级审计明细。</p>';
    for(const a of H.Q7_hop_audit){
      h += '<div class="callout">'+esc(a.advisory_id||'')+' · 判定 '+
           esc(a.verdict||'')+'</div>';
      a.nodes.forEach((n,i)=>{
        const d = a.stale_days[i];
        const cls = d==null?'':(d>0?'stale':'fresh');
        h += '<div class="hop '+cls+'"><b>'+esc(a.labels[i]||'')+' '+esc(n)+'</b><br>'+
             '<span class="muted">墙钟 '+esc(a.at_iso[i]||'无')+'</span><br>'+
             (d==null?'<span class="muted">该跳无时间属性</span>':
              '漏洞已公开 <b>'+esc(d)+'</b> 天'+(d>0?' · 该跳时已过期':' · 当时尚未公开'))+'</div>';
      });
    }
  } else if(mode==='Q8'){
    h = '<h2>Q8 · 声明漂移 / SCA 对照</h2>';
    if(!H.Q8_declaration_drift.length && !H.merge_actions.length)
      h += '<p class="muted">该 store 本轮无 Q8 明细。</p>';
    for(const d of H.Q8_declaration_drift){
      h += '<div class="callout"><b>'+esc(d.claim_text||'')+'</b><br>'+
           '文本声明 <code>'+esc(d.cited_version)+'</code> ↔ lockfile 实钉 <code>'+
           esc(d.pinned_version)+'</code><br><span class="muted">'+
           esc(d.advisory_id||'')+' · 只读取 manifest 的扫描器报告 clean，'+
           '而过期声明仍会进入下一个 agent 的上下文。</span></div>';
      h += '<div>'+d.claim_chain.map(n=>'<span class="chip">'+esc(n)+'</span>').join('<span class="arrow">→</span>')+'</div>';
      h += '<div class="muted" style="margin-top:6px">lockfile 侧：'+
           d.lockfile_chain.map(n=>'<span class="chip">'+esc(n)+'</span>').join('<span class="arrow">→</span>')+
           '</div>';
    }
    for(const a of H.merge_actions.slice(0,12)){
      h += '<div class="hop stale">BLOCK_MERGE_TEXT · '+esc(a.reject_text||'')+
           '（文本 '+esc(a.cited_version)+' / 实钉 '+esc(a.pinned_version)+'）</div>';
    }
  } else if(mode==='Q9'){
    h = '<h2>Q9 · 跨模型收敛（同一风险版本）</h2>';
    if(!(H.Q9_convergence||[]).length) h += '<p class="muted">该 store 本轮无 Q9 明细。</p>';
    for(const c of (H.Q9_convergence||[])){
      h += '<div class="callout"><b>'+esc(c.package)+' '+esc(c.version)+'</b> · '+
           esc(c.n_models)+' 个模型 / '+esc(c.n_answers)+' 条答案收敛于此<br>'+
           '<span class="muted">'+esc(c.advisory_id)+' · fixed '+esc(c.fixed)+
           ' · 模型：'+esc((c.models||[]).join(', '))+'</span></div>';
      h += '<div>'+c.nodes.map(n=>'<span class="chip lg-jump" data-id="'+esc(n)+'">'+esc(n)+'</span>').join('')+'</div>';
    }
  } else if(mode==='Q10'){
    h = '<h2>Q10 · advisory 爆炸半径</h2>';
    if(!(H.Q10_blast_radius||[]).length) h += '<p class="muted">该 store 本轮无 Q10 明细。</p>';
    for(const b of (H.Q10_blast_radius||[])){
      h += '<div class="callout"><b>'+esc(b.advisory_id)+'</b> · 一条公告波及 '+
           esc(b.n_answers)+' 条答案 / '+esc(b.n_models)+' 个模型<br>'+
           '<span class="muted">'+esc(b.package)+' · fixed '+esc(b.fixed)+
           ' ·  published '+esc(b.published)+' · 版本：'+esc((b.versions||[]).join(', '))+'</span></div>';
      h += '<div>'+b.nodes.slice(0,14).map(n=>'<span class="chip lg-jump" data-id="'+esc(n)+'">'+esc(n)+'</span>').join('')+'</div>';
    }
  } else {
    h = '<h2>导出自检</h2><table>';
    for(const [k,v] of Object.entries(g.checks))
      h += '<tr><th>'+esc(k)+'</th><td><span class="badge '+(v?'pass':'fail')+'">'+
           (v?'PASS':'FAIL')+'</span></td></tr>';
    h += '</table><div class="callout" style="margin-top:12px">本页每个节点、属性、关系'+
         '均由 Cypher 从持久化 <code>.rl</code> store 读回；不是手绘示意图。'+
         '<br>导出快照 sha256: <code>'+esc(g.store_sha256)+'</code>';
    if(g.store_hash_matches_disk===true){
      h += '<br><span class="badge pass">渲染时磁盘 store 一致</span>';
    } else if(g.store_hash_matches_disk===false){
      h += '<br><span class="badge fail">STALE：磁盘 store 已变化</span>'+
           '<br>渲染时磁盘 sha256: <code>'+esc(g.disk_sha256_at_render)+'</code>'+
           '<br><span class="muted">重新运行一键复验后刷新本页。</span>';
    }
    h += '</div>';
  }
  $('#highlight').innerHTML = h;
}

function applyMode(mode){
  const g = GRAPHS[active];
  if(isLarge(active)){ highlightPanel(mode);
    $$('button.mode').forEach(b=>b.classList.toggle('active', b.dataset.mode===mode));
    return; }
  let keep = null;
  if(mode==='Q6') keep = new Set(g.highlights.Q6_provenance.flatMap(p=>p.nodes));
  if(mode==='Q7') keep = new Set(g.highlights.Q7_hop_audit.flatMap(a=>a.nodes));
  if(mode==='Q8') keep = new Set(g.highlights.Q8_declaration_drift.flatMap(
      d=>d.claim_chain.concat(d.lockfile_chain, d.advisory_chain)));
  if(mode==='Q9') keep = new Set((g.highlights.Q9_convergence||[]).flatMap(c=>c.nodes));
  if(mode==='Q10') keep = new Set((g.highlights.Q10_blast_radius||[]).flatMap(b=>b.nodes));
  $$('.canvas[data-i="'+active+'"] .node').forEach(el=>{
    el.classList.toggle('dim', !!keep && !keep.has(el.dataset.id));
    el.classList.remove('hit');
  });
  $$('.canvas[data-i="'+active+'"] .edge').forEach(el=>{
    el.classList.toggle('dim', !!keep && !(keep.has(el.dataset.s) && keep.has(el.dataset.t)));
    el.classList.remove('hl');
    if(keep && keep.has(el.dataset.s) && keep.has(el.dataset.t)) el.classList.add('hl');
  });
  $$('button.mode').forEach(b=>b.classList.toggle('active', b.dataset.mode===mode));
  highlightPanel(mode);
}

function search(q){
  q = q.trim().toLowerCase();
  if(isLarge(active)){ lgSearch(q); return; }
  $$('.canvas[data-i="'+active+'"] .node').forEach(el=>{
    const n = GRAPHS[active].nodes.find(x=>x.id===el.dataset.id);
    const hay = (n.id+' '+n.label+' '+JSON.stringify(n.props)).toLowerCase();
    el.classList.toggle('hit', !!q && hay.includes(q));
  });
}

/* ---- large-graph interactive mode: neighborhood walk + path query ---- */
function adj(i){
  if(lgAdj[i]) return lgAdj[i];
  const out={}, inn={};
  for(const e of GRAPHS[i].edges){
    (out[e.source]=out[e.source]||[]).push(e);
    (inn[e.target]=inn[e.target]||[]).push(e);
  }
  lgAdj[i]={out,inn};
  return lgAdj[i];
}
function lgSearch(q){
  const box = $('.canvas[data-i="'+active+'"] .lg-results');
  if(!box) return;
  if(!q){ box.innerHTML=''; return; }
  const hits=[];
  for(const n of GRAPHS[active].nodes){
    const hay=(n.id+' '+n.label+' '+JSON.stringify(n.props)).toLowerCase();
    if(hay.includes(q)){ hits.push(n); if(hits.length>=60) break; }
  }
  box.innerHTML = hits.length
    ? hits.map(n=>'<button class="lg-hit" data-id="'+esc(n.id)+'">'+esc(n.label)+' · '+esc(n.id)+'</button>').join('')
    : '<span class="muted">无匹配（最多列 60 条）</span>';
}
function selectNode(id){
  const g=GRAPHS[active];
  const n=g.nodes.find(x=>x.id===id);
  if(!n) return;
  $('#nodepanel').innerHTML=nodePanel(id);
  const {out,inn}=adj(active);
  const es=[...(out[id]||[]),...(inn[id]||[])];
  const nbrs=[]; const seen=new Set([id]);
  for(const e of es){
    const other = e.source===id? e.target : e.source;
    if(!seen.has(other)){ seen.add(other); nbrs.push(other); }
    if(nbrs.length>=28) break;
  }
  const W=860,H=620,cx=W/2,cy=H/2,R=240;
  const pos={[id]:[cx,cy]};
  nbrs.forEach((nid,k)=>{
    const ang=2*Math.PI*k/Math.max(nbrs.length,1)-Math.PI/2;
    pos[nid]=[cx+R*Math.cos(ang), cy+R*Math.sin(ang)];
  });
  let s='<svg viewBox="0 0 '+W+' '+H+'" width="'+W+'" height="'+H+'" xmlns="http://www.w3.org/2000/svg">';
  s+='<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#aab4c4"/></marker></defs>';
  s+='<rect width="100%" height="100%" fill="#ffffff"/>';
  const drawn=new Set();
  for(const e of es){
    if(!pos[e.source]||!pos[e.target]) continue;
    const k=e.source+'|'+e.target+'|'+e.type;
    if(drawn.has(k)) continue; drawn.add(k);
    const [x1,y1]=pos[e.source],[x2,y2]=pos[e.target];
    s+='<line class="edge" x1="'+x1+'" y1="'+y1+'" x2="'+x2+'" y2="'+y2+'" marker-end="url(#ar)"><title>'+esc(e.type)+'</title></line>';
  }
  for(const nid of [id,...nbrs]){
    const nn=g.nodes.find(x=>x.id===nid); if(!nn) continue;
    const [x,y]=pos[nid];
    const color=(window.LABEL_COLORS&&window.LABEL_COLORS[nn.label])||'#5b6475';
    let label=nn.id; if(label.length>30) label=label.slice(0,28)+'..';
    const r = nid===id?16:11;
    s+='<g class="node" data-id="'+esc(nid)+'"><circle cx="'+x+'" cy="'+y+'" r="'+r+'" fill="'+color+'"><title>'+esc(nn.id)+'</title></circle>'+
       '<text x="'+x+'" y="'+(y+r+15)+'" text-anchor="middle">'+esc(label)+'</text></g>';
  }
  s+='</svg>';
  const svgBox=$('.canvas[data-i="'+active+'"] .lg-svg');
  if(svgBox) svgBox.innerHTML='<p class="muted">邻域视图：中心 <code>'+esc(id)+'</code> · '+esc(es.length)+' 条关联边（最多画 28 个邻居）。点击邻居继续游走。</p>'+s;
}
function bfs(start,end){
  const {out,inn}=adj(active);
  const undirected={};
  const add=(a,b,e)=>{(undirected[a]=undirected[a]||[]).push([b,e]);};
  for(const e of GRAPHS[active].edges){ add(e.source,e.target,e); add(e.target,e.source,e); }
  const prev={[start]:null}; const q=[start]; let depth=0;
  while(q.length && depth<8){
    const level=q.splice(0,q.length); depth++;
    for(const cur of level){
      for(const [nxt,e] of (undirected[cur]||[])){
        if(nxt in prev) continue;
        prev[nxt]=[cur,e];
        if(nxt===end){
          const path=[]; let node=end;
          while(node!==start){ const [p,ee]=prev[node]; path.unshift({from:p,to:node,type:ee.type}); node=p; }
          return path;
        }
        q.push(nxt);
      }
    }
  }
  return null;
}
function renderPath(){
  const a=$('#lg-from').value.trim(), b=$('#lg-to').value.trim();
  const box=$('.canvas[data-i="'+active+'"] .lg-svg');
  if(!a||!b){ return; }
  if(a===b){ box.innerHTML='<p class="muted">起点与终点是同一节点：<code>'+esc(a)+'</code>（0 跳）。</p>'; return; }
  const path=bfs(a,b);
  if(!path){ box.innerHTML='<p class="muted">8 跳内未找到 <code>'+esc(a)+'</code> → <code>'+esc(b)+'</code> 的路径。</p>'; return; }
  const W=860, step=Math.min(150, (W-80)/Math.max(path.length,1)), H=160;
  let s='<svg viewBox="0 0 '+W+' '+H+'" width="'+W+'" height="'+H+'" xmlns="http://www.w3.org/2000/svg">';
  s+='<defs><marker id="ar2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#aab4c4"/></marker></defs><rect width="100%" height="100%" fill="#ffffff"/>';
  const nodes=[a,...path.map(p=>p.to)];
  nodes.forEach((nid,k)=>{
    const x=50+k*step, y=70;
    const nn=GRAPHS[active].nodes.find(x=>x.id===nid);
    const color=(window.LABEL_COLORS&&window.LABEL_COLORS[nn?nn.label:''])||'#5b6475';
    if(k>0){ const px=50+(k-1)*step;
      s+='<line class="edge" x1="'+(px+14)+'" y1="'+y+'" x2="'+(x-16)+'" y2="'+y+'" marker-end="url(#ar2)"><title>'+esc(path[k-1].type)+'</title></line>'+
         '<text x="'+((px+x)/2)+'" y="'+(y-12)+'" text-anchor="middle" font-size="9" fill="#5b6475">'+esc(path[k-1].type)+'</text>'; }
    let label=nid; if(label.length>22) label=label.slice(0,20)+'..';
    s+='<g class="node" data-id="'+esc(nid)+'"><circle cx="'+x+'" cy="'+y+'" r="12" fill="'+color+'"><title>'+esc(nid)+'</title></circle>'+
       '<text x="'+x+'" y="'+(y+27)+'" text-anchor="middle">'+esc(label)+'</text></g>';
  });
  s+='</svg>';
  box.innerHTML='<p class="muted">路径查询（无向 BFS，≤8 跳）：<code>'+esc(a)+'</code> → <code>'+esc(b)+'</code> · '+esc(path.length)+' 跳</p>'+s;
}

function showTab(i){
  active = i;
  $$('.canvas').forEach(c=>c.hidden = c.dataset.i!==String(i));
  $$('button.tab').forEach(b=>b.classList.toggle('active', b.dataset.i===String(i)));
  const g = GRAPHS[i];
  $('#meta').innerHTML = '<b>'+esc(g.title)+'</b> · 节点 <b>'+esc(g.counts.nodes)+
    '</b> · 关系 <b>'+esc(g.counts.relationships)+'</b> · '+
    '<span class="badge '+(g.verdict==='PASS'?'pass':'fail')+'">'+esc(g.verdict)+'</span>'+
    '<div class="muted" style="margin-top:5px">源：'+esc(g.source)+
    ' · store <code>'+esc(g.store)+'</code> · '+esc(g.store_bytes)+' bytes</div>';
  $('#nodepanel').innerHTML = '<h2>节点属性</h2><p class="muted">点击任意节点查看其属性。</p>';
  $('#legend').innerHTML = Object.entries(g.counts.labels).map(([k,v])=>
    '<span><i style="background:'+(window.LABEL_COLORS&&window.LABEL_COLORS[k]||'#5b6475')+
    '"></i>'+esc(k)+' '+esc(v)+'</span>').join('');
  $('#reltypes').innerHTML = Object.entries(g.counts.rel_types).map(([k,v])=>
    '<span class="tag">'+esc(k)+' '+esc(v)+'</span>').join('');
  if(isLarge(i)){
    const first=(g.nodes.find(n=>n.label==='Advisory'||n.label==='Vuln')||g.nodes[0]);
    if(first) selectNode(first.id);
  }
  applyMode('ALL');
}

window.addEventListener('DOMContentLoaded',()=>{
  window.LABEL_COLORS = __COLORS__;
  $$('button.tab').forEach(b=>b.addEventListener('click',()=>showTab(+b.dataset.i)));
  $$('button.mode').forEach(b=>b.addEventListener('click',()=>applyMode(b.dataset.mode)));
  $('#search').addEventListener('input',e=>search(e.target.value));
  document.addEventListener('click',e=>{
    const jump=e.target.closest('.lg-jump');
    if(jump){ const id=jump.dataset.id;
      if(isLarge(active)){ selectNode(id); } else { $('#nodepanel').innerHTML=nodePanel(id); }
      return; }
    const hit=e.target.closest('.lg-hit');
    if(hit){ selectNode(hit.dataset.id); return; }
    const n = e.target.closest('.node');
    if(n){ $('#nodepanel').innerHTML = nodePanel(n.dataset.id);
      if(isLarge(active)) selectNode(n.dataset.id); }
    if(e.target.closest('#lg-path-btn')) renderPath();
  });
  showTab(0);
});
"""


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _json_for_script(data: Any) -> str:
    text = json.dumps(data, ensure_ascii=False, default=str)
    return (text.replace("&", "\\u0026").replace("<", "\\u003c")
            .replace(">", "\\u003e").replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029"))


def _layout(nodes: list[dict[str, Any]],
            edges: list[dict[str, str]]) -> tuple[dict[str, tuple[float, float]], int, int]:
    """Deterministic longest-path layering; no external layout library."""
    layer = {n["id"]: 0 for n in nodes}
    for _ in range(len(nodes)):
        changed = False
        for e in edges:
            s, t = e["source"], e["target"]
            if s in layer and t in layer and layer[s] + 1 > layer[t]:
                layer[t] = layer[s] + 1
                changed = True
        if not changed:
            break
    # Guard against cyclic graphs inflating the depth.
    max_layer = min(max(layer.values(), default=0), 8)
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for n in nodes:
        groups[min(layer[n["id"]], max_layer)].append(n)
    for group in groups.values():
        group.sort(key=lambda n: (n["label"], n["id"]))

    gap, x_gap = 52, 250
    height = max(420, (max((len(v) for v in groups.values()), default=1) + 1) * gap)
    width = max(760, (max_layer + 2) * x_gap)
    pos: dict[str, tuple[float, float]] = {}
    for k, group in groups.items():
        span = height - 80
        step = span / max(len(group), 1)
        for i, n in enumerate(group):
            pos[n["id"]] = (70 + k * x_gap + 26, 46 + step * (i + 0.5))
    return pos, width, height


def _svg(doc: dict[str, Any]) -> str:
    pos, width, height = _layout(doc["nodes"], doc["edges"])
    parts = [
        '<svg viewBox="0 0 %d %d" width="%d" height="%d" '
        'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Relate graph">' %
        (width, height, width, height),
        ('<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" '
         'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
         '<path d="M 0 0 L 10 5 L 0 10 z" fill="#aab4c4"/></marker></defs>'),
        '<rect width="100%" height="100%" fill="#ffffff"/>',
    ]
    for e in doc["edges"]:
        s, t = pos.get(e["source"]), pos.get(e["target"])
        if not s or not t:
            continue
        x1, y1, x2, y2 = s[0] + 14, s[1], t[0] - 16, t[1]
        parts.append(
            '<line class="edge" data-s="%s" data-t="%s" x1="%.1f" y1="%.1f" '
            'x2="%.1f" y2="%.1f" marker-end="url(#ar)"><title>%s</title></line>' %
            (_esc(e["source"]), _esc(e["target"]), x1, y1, x2, y2,
             _esc("%s -[%s]-> %s" % (e["source"], e["type"], e["target"])))
        )
    for n in doc["nodes"]:
        x, y = pos[n["id"]]
        color = LABEL_COLORS.get(n["label"], DEFAULT_COLOR)
        label = n["id"]
        if len(label) > 26:
            label = label[:24] + ".."
        parts.append(
            '<g class="node" data-id="%s"><circle cx="%.1f" cy="%.1f" r="12" '
            'fill="%s"><title>%s (%s)</title></circle>'
            '<text x="%.1f" y="%.1f" text-anchor="middle">%s</text></g>' %
            (_esc(n["id"]), x, y, color, _esc(n["id"]), _esc(n["label"]),
             x, y + 27, _esc(label))
        )
    parts.append('</svg>')
    return "".join(parts)


def _canvas(i: int, g: dict[str, Any]) -> str:
    if g["counts"]["nodes"] > 1500:
        return (
            '<div class="canvas" data-i="%d" hidden>'
            '<div class="lg-toolbar">'
            '<input type="text" id="lg-from" placeholder="路径起点 node_id">'
            '<input type="text" id="lg-to" placeholder="路径终点 node_id">'
            '<button id="lg-path-btn">查找路径（≤8 跳）</button>'
            '<span class="muted">大图交互模式：搜索节点 → 点击邻域游走 → 任意两点查路径</span>'
            '</div><div class="lg-results"></div><div class="lg-svg"></div></div>' % i
        )
    return '<div class="canvas" data-i="%d" hidden>%s</div>' % (i, _svg(g))


def render(graphs: list[dict[str, Any]]) -> str:
    tabs = "".join(
        '<button class="tab" data-i="%d">%s</button>' % (i, _esc(g["title"]))
        for i, g in enumerate(graphs)
    )
    canvases = "".join(_canvas(i, g) for i, g in enumerate(graphs))
    css = _STYLE
    js = (_JS.replace("__GRAPHS__", _json_for_script(graphs))
             .replace("__COLORS__", _json_for_script(LABEL_COLORS)))
    return """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TraceLens · See the graph</title>
<style>%s</style></head><body>
<h1>TraceLens · See the graph</h1>
<p class="sub">Relate 持久化图的只读浏览器。点击节点查看完整属性与连接；高亮按钮展示本轮 Cypher 真正返回的路径。大图（OSV 全量）支持搜索、邻域游走与任意两点路径查询。</p>
<div class="tabs">%s</div>
<div class="card" id="meta"></div>
<div class="card legend" id="legend"></div>
<div class="card"><h2>关系类型</h2><div id="reltypes"></div></div>
<div class="card"><div class="tabs" style="margin:0 0 10px">
<button class="mode" data-mode="ALL">全部 / 导出自检</button>
<button class="mode" data-mode="Q6">Q6 多跳溯源路径</button>
<button class="mode" data-mode="Q7">Q7 逐跳时间审计</button>
<button class="mode" data-mode="Q8">Q8 声明漂移</button>
<button class="mode" data-mode="Q9">Q9 跨模型收敛</button>
<button class="mode" data-mode="Q10">Q10 爆炸半径</button>
<input type="search" id="search" placeholder="搜索节点 / 属性"></div>
<p class="muted">高亮集合来自同一次运行的查询结果，不是人工选择；其余节点自动淡化。</p></div>
<div class="layout">
  %s
  <div class="side">
    <div class="card" id="nodepanel"><h2>节点属性</h2><p class="muted">点击任意节点查看其属性。</p></div>
    <div class="card" id="highlight"></div>
    <div class="card"><h2>为什么这必须是图</h2>
      <p class="muted">Q6/Q7 沿变长 <code>PARENT_OF</code> →
      <code>RETRIEVED_FROM</code> → <code>MENTIONS</code> 路径逐跳走，
      并对 <code>nodes(path)</code> 施加墙钟 <code>ALL()</code> 谓词；
      Q8 把答案里的自然语言声明、lockfile 实钉版本与 advisory 时间轴连在同一张图里；
      Q9/Q10 跨答案聚合：多个模型收敛到同一风险版本（fan-in），
      一条 advisory 波及多少答案（fan-out）。
      只读取 manifest 的扫描器既看不到声明链，也没有跨答案视图。</p>
    </div>
  </div>
</div>
<p class="muted" style="margin-top:18px">单文件离线页面：CSS / JS / 数据 / SVG 全部内联，
无 CDN、无字体、无图片、无网络请求。节点与边均由 Cypher 从 <code>.rl</code> store 读回。</p>
<script>%s</script></body></html>
""" % (css, tabs, canvases, js)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m tracelens.graphexplorer")
    p.add_argument("--graph", action="append", required=True,
                   help="graphexport JSON (repeatable)")
    p.add_argument("--out", default=str(ROOT / "docs/graph-explorer.html"))
    args = p.parse_args(argv)
    graphs = [json.loads(Path(g).read_text(encoding="utf-8")) for g in args.graph]
    # Re-hash the CURRENT store on disk at render time. Export snapshots go
    # stale whenever a later command rebuilds the .rl file; showing only the
    # old hash and calling it "the store" is a verifiable falsehood. Mark it.
    for g in graphs:
        store_path = Path(g["store"])
        if store_path.exists():
            disk_hash = hashlib.sha256(store_path.read_bytes()).hexdigest()
            g["disk_sha256_at_render"] = disk_hash
            g["store_hash_matches_disk"] = (disk_hash == g.get("store_sha256"))
        else:
            g["disk_sha256_at_render"] = "STORE MISSING"
            g["store_hash_matches_disk"] = False
    # Validate BEFORE writing: a rejected export must not leave a viewable HTML
    # file behind, otherwise a judge may open a STALE page and miss the exit 1.
    if any(g["verdict"] != "PASS" for g in graphs):
        raise SystemExit("refusing to render a graph whose export checks failed")
    if any(not g["store_hash_matches_disk"] for g in graphs):
        raise SystemExit(
            "STALE EXPORT: a graph export no longer matches its .rl store on disk. "
            "Re-run graphexport (or the full award-verify.sh) before rendering."
        )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(graphs), encoding="utf-8")
    # Also emit a standalone SVG per small graph so the README can embed a
    # real, regenerable first-screen picture of the actual store (not a
    # screenshot that goes stale).
    svg_files = []
    for g in graphs:
        if g["counts"]["nodes"] <= 1500:
            svg_path = out.parent / (Path(g["store"]).stem + ".svg")
            svg_path.write_text(_svg(g), encoding="utf-8")
            svg_files.append(str(svg_path))
    print(json.dumps({
        "out": str(out), "graphs": len(graphs),
        "nodes": [g["counts"]["nodes"] for g in graphs],
        "relationships": [g["counts"]["relationships"] for g in graphs],
        "verdicts": [g["verdict"] for g in graphs],
        "store_hash_matches_disk": [g["store_hash_matches_disk"] for g in graphs],
        "svg_files": svg_files,
        "bytes": out.stat().st_size,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
