const S = __SNAPSHOT__;
const META = S.meta || {channels:[], default:"tech"};
const $ = (sel, root=document) => root.querySelector(sel);
const $$ = (sel, root=document) => [...root.querySelectorAll(sel)];
const esc = s => String(s==null?"":s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
// ---- 频道 ----
let CHID = "";
try { CHID = localStorage.getItem("pat-channel") || ""; } catch(e){}
if (!S.channels[CHID]) CHID = META.default || "tech";
if (!S.channels[CHID]) CHID = Object.keys(S.channels)[0];
let C = S.channels[CHID];
let CAT_CLS = C.catCls || {};
let CAT_EN = C.catEn || {};
let TREND_TITLES = null;
const STATUS_EN = {"爆":"Hot","发酵中":"Trending","关注中":"Watch"};
const DENS_EN = {"高":"High","中":"Medium","低":"Low"};
const I18N = {
  zh: { feed:"精选", all:"全部", hot:"热点", daily:"日报", trends:"趋势", more:"更多",
    allPage:"全部动态", topics:"主题", data:"数据", agent:"Agent 接入",
    search:"搜索", catAll:"全部", sortScore:"按推荐分", sortTime:"按时间",
    thresholdNote:"精选门槛：官方信源 ≥ {o} 分 · 媒体信源 ≥ {m} 分（可在 collector/config.json 调整）",
    hotNow:"当前热点", fullRank:"完整榜单 →", unreadOnly:"只看未读", today:"今天", daySel:"条精选", noMatch:"没有匹配的条目",
    heatVal:"热度", sources:"信源", signals:"信号",
    repMore:"另有 {n} 家信源报道", repOne:"1 家信源报道",
    toc:"今日看点", archive:"日报归档",
    headlineK:"头 条", picksK:"今日看点", flashK:"快 讯", moreK:"分栏目浏览",
    topicsSub:"分类统计，点击进入筛选",
    dataPage:"数据", dataSub:"统计与导出", total:"收录总数", h24:"24 小时新增", h7:"7 天新增", hotTopic:"热点话题", trend:"每日收录趋势（近 14 天）",
    srcTable:"数据来源", latest:"最新收录", dlCSV:"下载 CSV", dlItems:"查看 items.json", dlHot:"查看 hot-topics.json", dlDaily:"查看 dailies.json",
    agentPage:"Agent 接入", agentSub:"面向 AI / LLM / 智能体的数据接口（免鉴权，静态 JSON）", apiTitle:"数据 API（v1）",
    apiDesc:"数据每天 6:00 / 18:00 自动更新，接口免鉴权，AI 智能体 / 脚本可直接消费。", endpoint:"接口", desc:"说明", open:"打开",
    curl:"用法示例（curl）", llmsNote:"站点根目录提供 llms.txt（LLM 友好入口），Agent 可先读取它再按需拉取接口。", base:"接口基地址（本页 URL 去掉 index.html）",
    reason:"推荐理由", density:"信息密度", official:"官方", pick:"精选",
    catDelta:"分类热度变化", newTopics:"新上榜事件", sustained:"持续发酵", noTrend:"本周暂无趋势数据（需要至少两周的日报归档）",
    menuAllSub:"全部资讯 · 搜索 / 分类 / 排序", menuTopicsSub:"分类统计，点击进入筛选", menuDataSub:"统计与导出", menuAgentSub:"开放 JSON 接口，免鉴权",
    expand:"展开阅读", collapse:"收起", aiSum:"AI 内容概要", srcSum:"来源摘要",
    extNote:"原文·需外网", readOrig:"阅读原文 ↗（需外网）", loadMore:"加载更多", aiGen:"生成中文摘要", aiLoading:"生成中…", aiFail:"生成失败，点击重试",
    footer:"PAT-HOT · 物理·天文·光电热点统计（AIHOT 方法论）· 数据来自公开网络，仅供参考，不构成投资建议 · GitHub 开源" },
  en: { feed:"Selected", all:"All", hot:"Hot", daily:"Daily", trends:"Trends", more:"More",
    allPage:"All Items", topics:"Topics", data:"Data", agent:"Agent API",
    search:"Search", catAll:"All", sortScore:"By score", sortTime:"By time",
    thresholdNote:"Selection bar: official sources ≥ {o} · media sources ≥ {m} (tune in collector/config.json)",
    hotNow:"Trending Now", fullRank:"Full ranking →", unreadOnly:"Unread only", today:"Today", daySel:"selected", noMatch:"No matching items",
    heatVal:"heat", sources:"sources", signals:"signals",
    repMore:"{n} more sources", repOne:"1 source",
    toc:"Today's picks", archive:"Archive",
    headlineK:"HEADLINE", picksK:"Today's picks", flashK:"Flash", moreK:"Browse by category",
    topicsSub:"Category stats — click to filter",
    dataPage:"Data", dataSub:"Stats & export", total:"Total items", h24:"24h new", h7:"7d new", hotTopic:"Hot topics", trend:"Daily trend (14 days)",
    srcTable:"Sources", latest:"Latest", dlCSV:"Download CSV", dlItems:"items.json", dlHot:"hot-topics.json", dlDaily:"dailies.json",
    agentPage:"Agent API", agentSub:"Open JSON APIs for AI / LLM agents (no auth)", apiTitle:"Data API (v1)",
    apiDesc:"Data refreshes at 6:00 / 18:00 daily. Endpoints need no auth and are agent/script friendly.", endpoint:"Endpoint", desc:"Description", open:"Open",
    curl:"Examples (curl)", llmsNote:"llms.txt at site root is an LLM-friendly entry point.", base:"Base URL (this page URL minus index.html)",
    reason:"Why it matters", density:"Info density", official:"Official", pick:"Pick",
    catDelta:"Category heat change", newTopics:"New events", sustained:"Sustained events", noTrend:"No trend data yet (needs 2+ weeks of daily archive)",
    menuAllSub:"All items · search / filter / sort", menuTopicsSub:"Category stats — click to filter", menuDataSub:"Stats & export", menuAgentSub:"Open JSON APIs, no auth",
    expand:"Read more", collapse:"Collapse", aiSum:"AI Summary", srcSum:"Source abstract",
    extNote:"orig.·needs internet", readOrig:"Read original ↗ (needs internet)", loadMore:"Load more", aiGen:"Generate Chinese summary", aiLoading:"Generating…", aiFail:"Failed, tap to retry",
    footer:"PAT-HOT · physics / astronomy / photonics hot-topic stats (AIHOT methodology) · public data, for reference only · open source on GitHub" }
};
let LANG = "zh";
try { LANG = localStorage.getItem("pat-lang") || "zh"; } catch(e){}
const T = I18N[LANG] || I18N.zh;
function chn(){ return LANG==="en" ? C.name.en : C.name.zh; }
function feedSub(){ return LANG==="en" ? chn()+" timeline ranked by score" : "按推荐分排序的"+chn()+"时间线"; }
function hotPage(){ return chn()+(LANG==="en"?" Hot Ranking":"热点榜"); }
function hotSub(){ return LANG==="en" ? "Event-level heat: each independent source counts once per 48h" : "事件级热度：48 小时内每独立来源只计一次"; }
function dailyPage(){ return chn()+(LANG==="en"?" Daily":"日报"); }
function dailySub(){ return LANG==="en" ? "Auto-generated daily (with archive)" : "自动生成 · 每日一篇（含历史归档）"; }
function searchPh(){ return T.search+chn()+(LANG==="en"?" news…":"资讯 / 关键词…"); }
const state = { q:"", cat:"全部", sort:"score", dailyDate:"", hotSort:"heat", unreadOnly:false, collapsed:{} };
function lsGet(k){ try{ return JSON.parse(localStorage.getItem(k)||"{}"); }catch(e){ return {}; } }
function lsSet(k,v){ try{ localStorage.setItem(k, JSON.stringify(v)); }catch(e){} }
let READ = lsGet("pat-read"), FAV = lsGet("pat-fav");
function markRead(u){ if(!u||READ[u]) return; READ[u]=1; const ks=Object.keys(READ); if(ks.length>800) ks.slice(0,300).forEach(k=>delete READ[k]); lsSet("pat-read",READ); }
function toggleFav(u){ if(FAV[u]) delete FAV[u]; else FAV[u]=1; lsSet("pat-fav",FAV); }
function avaColor(s){ let h=0; for(const c of String(s)) h=(h*31+c.charCodeAt(0))>>>0; return "hsl("+(h%360)+",40%,46%)"; }
function tr(){ $$("[data-i18n]").forEach(el=>{ const k=el.dataset.i18n; if(T[k]) el.textContent = T[k]; }); $("#lang").textContent = LANG==="zh"?"EN":"中"; $("#q").placeholder = searchPh(); }
function fmtRel(iso){ if(!iso) return ""; const t=new Date(iso); const d=(Date.now()-t.getTime())/1000; if(d<60) return "刚刚"; if(d<3600) return Math.floor(d/60)+" 分钟前"; if(d<86400) return Math.floor(d/3600)+" 小时前"; return Math.floor(d/86400)+" 天前"; }
function effDate(it){ const p=it.published_at; if(p&&p.length>=10) return p.slice(0,10); const d=new Date(it.discovered_at); return new Date(d.getTime()+8*3600*1000).toISOString().slice(0,10); }
function fmtDay(dstr){ const parts=dstr.split("-"); if(LANG==="en") return dstr; return parts[0]+"年"+Number(parts[1])+"月"+Number(parts[2])+"日"; }
function wdCN(dstr){ const d=new Date(dstr+"T00:00:00+08:00").getDay(); return LANG==="en"?["Sun","Mon","Tue","Wed","Thu","Fri","Sat"][d]:["周日","周一","周二","周三","周四","周五","周六"][d]; }
function todayCN(){ return new Date(Date.now()+8*3600*1000).toISOString().slice(0,10); }
function isToday(d){ return d===todayCN(); }
function scoreCls(s){ return s>=75?"s-hi":(s>=50?"s-mid":"s-lo"); }
function pubLabel(it){ if(it.published_at){ const p=it.published_at; if(p.length===7) return p+"（月级）发布"; if(p.length===10) return p+" 发布"; return p.replace("T"," ").slice(5,16)+" 发布"; } return "收录 "+fmtRel(it.discovered_at); }
function catName(c){ return LANG==="en" ? (CAT_EN[c]||c) : c; }
function statusName(s){ return LANG==="en" ? (STATUS_EN[s]||s) : s; }
function densName(d){ return LANG==="en" ? (DENS_EN[d]||d) : d; }
function catBadge(c){ return '<span class="bdg b-cat">'+esc(catName(c))+'</span>'; }
function pickBadge(){ return '<span class="bdg b-pick">'+T.pick+'</span>'; }
function tierBadge(t){ return t==="official"?'<span class="bdg b-tier">'+T.official+'</span>':""; }
function densBadge(d){ if(!d) return ""; const cls=d==="高"?"b-dh":(d==="中"?"b-dm":"b-dl"); return '<span class="bdg '+cls+'" title="'+T.density+'">'+esc(densName(d))+'</span>'; }
function scoreEl(s,llm){ const ai=llm?'<span class="iai">AI</span>':""; return '<span class="iscore mono '+scoreCls(s)+'" title="'+(llm?"AI 双打分均值":"score")+' / 100">'+Math.round(s)+'</span>'+ai; }
function summaryOf(it){ return it.zh_full || it.llm_summary || it.summary || ""; }
function cardSummary(it){ const s=summaryOf(it); if(it.zh_full || it.llm_summary) return s.length>160 ? s.slice(0,160)+"…" : s; return s.length>160 ? s.slice(0,160)+"…" : s; }
function trendSet(){ const tt=C.trends||{}; return new Set([...(tt.newTopics||[]),...(tt.sustainedTopics||[])].map(x=>x.title)); }
function trendOf(t){ if(!TREND_TITLES) TREND_TITLES = trendSet(); return TREND_TITLES.has(t.title) ? "up" : "flat"; }
// ---- 站内展开阅读 ----
const EXPANDED = new Set();
function expandable(it){ const s=it.summary||""; return !!(it.zh_full || it.llm_summary || s.length>160); }
function expandBtn(it){ if(!expandable(it)) return ""; const open=EXPANDED.has(it.id); return '<button class="xbtn'+(open?" open":"")+'" data-x="'+it.id+'"><span>'+(open?T.collapse:T.expand)+'</span><span class="xa">▼</span></button>'; }
function expandBody(it){ if(!expandable(it)) return ""; const open=EXPANDED.has(it.id);
  const zf=it.zh_full?'<div class="xsec">'+T.aiSum+'</div><div class="xt">'+esc(it.zh_full)+'</div>':"";
  const ai=!it.zh_full&&it.llm_summary?'<div class="xsec">'+T.aiSum+'</div><div class="xt">'+esc(it.llm_summary)+'</div>':"";
  const rs=it.summary?'<div class="xsec">'+T.srcSum+'</div><div class="xt">'+esc(it.summary)+'</div>':"";
  const src=it.url?'<div class="xsrc"><a href="'+esc(it.url)+'" target="_blank" rel="noopener">'+T.readOrig+'</a></div>':"";
  // 按需 AI 中文摘要：没有 zh_full 时显示按钮
  const od=!it.zh_full?'<div class="xod" id="xod-'+it.id+'"><button class="obtn" data-od="'+esc(it.url)+'">✨ '+T.aiGen+'</button><div class="otxt" style="display:none"></div></div>':"";
  return '<div class="xbody'+(open?" open":"")+'" id="xb-'+it.id+'"><div class="xbody-in">'+zf+ai+rs+od+src+'</div></div>'; }
function toggleExpand(btn){ const id=btn.dataset.x; const body=document.getElementById("xb-"+CSS.escape(id));
  const open=EXPANDED.has(id); if(open) EXPANDED.delete(id); else EXPANDED.add(id);
  btn.classList.toggle("open",!open); btn.querySelector("span").textContent=!open?T.collapse:T.expand;
  if(body) body.classList.toggle("open",!open); }
// ---- 按需 AI 中文摘要 ----
const OD_CACHE_KEY="pat-od-cache";
function odGet(url){ try{ const c=JSON.parse(localStorage.getItem(OD_CACHE_KEY)||"{}"); return c[url]||null; }catch(e){ return null; } }
function odSet(url, data){ try{ const c=JSON.parse(localStorage.getItem(OD_CACHE_KEY)||"{}"); c[url]=data; const ks=Object.keys(c); if(ks.length>200) ks.slice(0,ks.length-200).forEach(k=>delete c[k]); localStorage.setItem(OD_CACHE_KEY, JSON.stringify(c)); }catch(e){} }
async function odGenerate(btn){
  const url=btn.dataset.od;
  if(!url || btn.disabled) return;
  // 先查缓存
  const cached=odGet(url);
  const box=btn.parentElement;
  const txt=box.querySelector(".otxt");
  if(cached){
    txt.innerHTML='<div class="xsec">'+T.aiSum+'</div><div class="xt">'+esc(cached.zh_full||cached.summary||"")+'</div>';
    txt.style.display="block"; btn.style.display="none";
    return;
  }
  // 找到文章数据
  let item=null;
  for(const ch of Object.values(S.channels)){
    const f=(ch.items||[]).find(i=>i.url===url);
    if(f){ item=f; break; }
  }
  if(!item) return;
  btn.disabled=true; btn.textContent="✨ "+T.aiLoading;
  try{
    const domain=(C&&C.domain&&C.domain.zh)||chn()||"科学";
    // 同站 Pages Function 为默认；非 pages.dev 镜像（如 GitHub Pages）自动回指 CF 端点。
    // window.PAT_LLM_WORKER 仅作显式覆盖（如改用独立 Worker）。
    const WORKER_URL=window.PAT_LLM_WORKER||(/^([a-z0-9-]+\.)?pages\.dev$/i.test(location.hostname)?"/api/summarize":"https://pat-hot.pages.dev/api/summarize");
    const resp=await fetch(WORKER_URL,{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({title:item.title, source:item.source, summary:item.summary||"", domain})
    });
    const data=await resp.json();
    if(data.error) throw new Error(data.error);
    odSet(url, data);
    // 写回当前频道数据，下次展开直接显示
    item.zh_full=data.zh_full; item.llm_summary=data.summary;
    txt.innerHTML='<div class="xsec">'+T.aiSum+'</div><div class="xt">'+esc(data.zh_full||data.summary||"")+'</div>';
    txt.style.display="block"; btn.style.display="none";
  }catch(e){
    btn.disabled=false; btn.textContent="✨ "+T.aiFail;
  }
}
document.addEventListener("click", e=>{
  const b=e.target.closest("[data-od]");
  if(b) odGenerate(b);
});
// ---- 频道切换 ----
function renderChSeg(){ const el=$("#chseg"); if(!el) return;
  el.innerHTML=META.channels.map(c=>'<a data-ch="'+c.id+'" class="'+(c.id===CHID?"on":"")+'"><span class="cl">'+c.letter+'</span><span class="cn">'+esc(LANG==="en"?c.name.en:c.name.zh)+'</span></a>').join("");
  el.querySelectorAll("a").forEach(a=>{ a.onclick=()=>setChannel(a.dataset.ch); }); }
function setChannel(id){ if(id===CHID||!S.channels[id]) return;
  CHID=id; C=S.channels[id]; CAT_CLS=C.catCls||{}; CAT_EN=C.catEn||{}; TREND_TITLES=null; EXPANDED.clear();
  state.dailyDate=""; state.cat="全部"; state.q=""; state.allShown=ALL_PAGE; const q=$("#q"); if(q) q.value="";
  try{ localStorage.setItem("pat-channel",id); }catch(e){}
  renderChSeg(); tr(); router(); window.scrollTo(0,0); }
function itemCard(it){
  const rd=READ[it.url]?" read":"", fv=FAV[it.url]?" on":"";
  const src=it.source||"", av=esc((src.trim().charAt(0)||chn()).charAt(0));
  const s=(it.llm_score!=null?it.llm_score:it.score);
  const reason=it.llm_reason?'<div class="ireason"><b>'+T.reason+'：</b>'+esc(it.llm_reason)+'</div>':"";
  const ev=it.event?'<div class="iev">⚡ '+esc(it.event)+'</div>':"";
  const ents=(it.entities&&it.entities.length)?'<div class="ient">'+it.entities.map(e=>'<span class="itag">'+esc(e)+'</span>').join("")+((it.tags||[]).map(t=>'<span class="itag">'+esc(t)+'</span>').join(""))+'</div>':"";
  const sum=cardSummary(it);
  return '<article class="icard'+rd+'"><div class="irow"><span class="ava" style="background:'+avaColor(src)+'">'+av+'</span><span class="isrc">'+esc(src)+'</span><span class="itime">'+esc(pubLabel(it))+'</span><span class="isp">'+scoreEl(s,it.llm_score!=null)+'<button class="fav'+fv+'" data-fav="'+esc(it.url)+'" aria-label="fav">★</button></span></div>'
  +'<div class="ibadges">'+catBadge(it.category)+tierBadge(it.tier)+(it.selected?pickBadge():"")+densBadge(it.density)+'</div>'
  +'<div class="ititle"><a href="'+esc(it.url)+'" target="_blank" rel="noopener" data-read="'+esc(it.url)+'" title="'+T.readOrig+'">'+esc(it.title)+'</a> <span class="ext-tag">'+T.extNote+'</span></div>'
  +reason+ev+ents+(sum?'<div class="isum">'+esc(sum)+'</div>':"")+expandBtn(it)+expandBody(it)+'</article>';
}
function threshNote(){ const th=C.thresholds||{official:55,media:65}; return T.thresholdNote.replace("{o}",th.official).replace("{m}",th.media); }
const renderers = {};
function setNav(v){ $$("#tabbar a").forEach(a=>a.classList.toggle("on",a.dataset.v===v)); $$("#dnav a").forEach(a=>a.classList.toggle("on",a.dataset.v===v)); $$(".seg a").forEach(a=>a.classList.toggle("on",a.dataset.seg===v)); }
function router(){ const h=(location.hash||"#/").replace("#",""); const name=h.split("?")[0]||"/"; const map={"/":"feed","/all":"all","/hot":"hot","/daily":"daily","/topics":"topics","/trends":"trends","/data":"data","/agent":"agent","/more":"more"}; const v=map[name]||"feed"; setNav(v); $$(".view").forEach(x=>x.classList.remove("on")); $("#view-"+v).classList.add("on"); (renderers[v]||renderers.feed)(); window.scrollTo(0,0); }
function renderFeed(){
  const root=$("#view-feed");
  const top=(C.topics||[]).slice(0,3);
  let hot='<div class="card hottop"><div class="hottop-h"><span class="pulse"></span>'+T.hotNow+'<a href="#/hot">'+T.fullRank+'</a></div>'
  +top.map((t,i)=>{ const up=trendOf(t)==="up"; const arrow=up?'<span class="up">▲</span>':"—";
    const rurl=esc((t.representative||{}).url||"#/hot");
    return '<div class="hr3"><span class="rk r'+(i+1)+'">'+(i+1)+'</span><span class="ht"><a href="'+rurl+'" target="_blank" rel="noopener">'+esc(t.title)+'</a></span><span class="hn mono">'+Math.round(t.heat||t.score)+' <small>'+T.heatVal+'</small> '+arrow+'</span></div>'; }).join("")+'</div>';
  let items=C.items.slice();
  if(state.unreadOnly) items=items.filter(i=>!READ[i.url]);
  const groups={}; for(const it of items){ const d=effDate(it); (groups[d]=groups[d]||[]).push(it); }
  const days=Object.keys(groups).sort().reverse().slice(0,7);
  let tl='<div class="urow"><button class="upill'+(state.unreadOnly?" on":"")+'" id="unreadBtn"><span class="dot"></span>'+T.unreadOnly+'</button></div>';
  if(!days.length) tl+='<div class="empty">'+T.noMatch+'</div>';
  for(const d of days){ const its=groups[d].slice().sort((a,b)=>b.score-a.score).slice(0,20);
    const closed=state.collapsed[d]?" closed":"";
    tl+='<div class="day'+closed+'"><div class="day-h" data-dayh="'+d+'"><h2>'+(isToday(d)?T.today+" ":"")+fmtDay(d)+'</h2><span class="w">'+wdCN(d)+'</span><span class="c">'+its.length+' '+T.daySel+'</span><span class="arr">'+(state.collapsed[d]?"▶":"▼")+'</span></div><div class="day-b">'+its.map(itemCard).join("")+'</div></div>'; }
  root.innerHTML='<div class="card ph"><h1>'+T.feed+'</h1><span class="sub">'+esc(feedSub())+'</span><div class="note">'+esc(threshNote())+'</div></div>'+hot+tl;
  const ub=$("#unreadBtn"); if(ub) ub.onclick=()=>{ state.unreadOnly=!state.unreadOnly; renderFeed(); };
}
const ALL_PAGE=30;
let allObserver=null;
function renderAll(){
  const root=$("#view-all"); let its=C.items.slice();
  if(state.q){ const q=state.q.toLowerCase(); its=its.filter(i=>(i.title+" "+(i.zh_full||i.llm_summary||i.summary||"")+" "+i.source).toLowerCase().includes(q)); }
  if(state.cat!=="全部") its=its.filter(i=>i.category===state.cat);
  if(state.sort==="score") its.sort((a,b)=>b.score-a.score); else its.sort((a,b)=>b.discovered_at.localeCompare(a.discovered_at));
  const shown=Math.min(state.allShown||ALL_PAGE, its.length);
  const hasMore=shown<its.length;
  root.innerHTML='<div class="card ph"><h1>'+T.allPage+'</h1><span class="sub">'+its.length+'</span><span class="hsort" style="margin-left:auto"><select id="all-cat" aria-label="cat"><option value="全部">'+T.catAll+'</option></select><select id="all-sort" aria-label="sort"><option value="score">'+T.sortScore+'</option><option value="time">'+T.sortTime+'</option></select></span><div class="note">'+esc(threshNote())+'</div></div><div id="all-list">'+(its.length?its.slice(0,shown).map(itemCard).join(""):'<div class="empty">'+T.noMatch+'</div>')+'</div>'+(hasMore?'<div id="all-more" class="card" style="text-align:center;padding:14px;cursor:pointer;color:var(--acd);font-weight:600">'+T.loadMore+' ('+shown+'/'+its.length+')</div>':"");
  const cats=[...new Set(C.items.map(i=>i.category))];
  const sel=$("#all-cat"); for(const c of cats){ const o=document.createElement("option"); o.value=c; o.textContent=catName(c); if(c===state.cat) o.selected=true; sel.appendChild(o); }
  $("#all-sort").value=state.sort;
  sel.onchange=e=>{ state.cat=e.target.value; state.allShown=ALL_PAGE; renderAll(); };
  $("#all-sort").onchange=e=>{ state.sort=e.target.value; state.allShown=ALL_PAGE; renderAll(); };
  if(allObserver) allObserver.disconnect();
  const more=$("#all-more");
  if(more){
    more.onclick=()=>{ state.allShown=(state.allShown||ALL_PAGE)+ALL_PAGE; renderAll(); window.scrollBy({top:-60}); };
    allObserver=new IntersectionObserver(es=>{ if(es[0].isIntersecting){ state.allShown=(state.allShown||ALL_PAGE)+ALL_PAGE; renderAll(); } },{rootMargin:"600px"});
    allObserver.observe(more);
  }
}
function hotExpand(t){ const rep=t.representative||{}; const it={id:"t-"+t.id, zh_full:rep.zh_full, llm_summary:rep.llm_summary, summary:rep.summary, url:rep.url||((t.links||[])[0]||{}).url};
  if(!expandable(it)) return ""; return expandBtn(it)+expandBody(it); }
function renderHot(){
  const root=$("#view-hot"); let ts=(C.topics||[]).slice();
  if(state.hotSort==="sources") ts.sort((a,b)=>b.source_count-a.source_count);
  const maxHeat=Math.max(...ts.map(t=>t.heat||t.score||0),1);
  const head='<div class="card ph"><h1>'+esc(hotPage())+'</h1><span class="sub">'+esc(hotSub())+'</span><span class="hsort"><button data-hs="heat" class="'+(state.hotSort==="heat"?"on":"")+'">'+T.heatVal+'</button><button data-hs="sources" class="'+(state.hotSort==="sources"?"on":"")+'">'+T.sources+'</button></span></div>';
  root.innerHTML=head+'<div class="card">'+ts.map((t,i)=>{
    const s=t.status; const flag=s==="爆"?'<span class="flag f-hot">'+statusName(s)+'</span>':(s==="发酵中"?'<span class="flag f-warm">'+statusName(s)+'</span>':'<span class="flag f-watch">'+statusName(s)+'</span>');
    const rep=t.representative||{}; const rurl=rep.url||((t.links||[])[0]||{}).url||"";
    const reason=rep.llm_reason?'<div class="ireason"><b>'+T.reason+'：</b>'+esc(rep.llm_reason)+'</div>':"";
    const rsum=rep.llm_summary||rep.summary;
    const chips=((t.top_terms||[]).map(x=>'<span class="chip term">'+esc(x)+'</span>').join(""))+((t.sources||[]).map(x=>'<span class="chip">'+esc(x)+'</span>').join(""));
    const flinks=(t.links||[]).map(l=>'<a href="'+esc(l.url)+'" target="_blank" rel="noopener">'+esc(l.title)+'<span class="fs">'+esc(l.source)+'</span></a>').join("");
    const fold=(t.folded_count>0&&flinks)?'<details class="fold"><summary><span>'+T.repMore.replace("{n}",t.folded_count)+'</span><span>›</span></summary><div class="fl">'+flinks+'</div></details>':"";
    const bar='<div class="hbar"><i style="width:'+Math.max(4,Math.round((t.heat||t.score)/maxHeat*100))+'%"></i></div>';
    return '<div class="hrow r'+(i+1)+'"><div class="hrank">'+(i+1)+'</div><div class="hmain"><div class="htitle"><a href="'+esc(rurl)+'" target="_blank" rel="noopener" data-read="'+esc(rurl)+'">'+esc(t.title)+'</a> '+flag+'</div>'
      +'<div class="hmeta"><span>'+esc(rep.source||((t.sources||[])[0]||""))+'</span><span>'+fmtRel(t.latest_at)+'</span><span>'+t.source_count+' '+T.sources+' · '+t.signal_count+' '+T.signals+'</span><span class="mono" style="font-weight:700;color:var(--acd)">'+Math.round(t.heat||t.score)+'</span></div>'
      +reason+(t.image?'<img class="himg" src="'+esc(t.image)+'" alt="" loading="lazy">':"")+(rsum?'<div class="isum">'+esc(rsum.length>200?rsum.slice(0,200)+"…":rsum)+'</div>':"")+hotExpand(t)+bar+'<div class="chips">'+chips+'</div>'+fold+'</div></div>';
  }).join("")+'</div>';
  $$("[data-hs]",root).forEach(b=>b.onclick=()=>{ state.hotSort=b.dataset.hs; renderHot(); });
}
function dailyArticle(a){
  const reason=a.reason?'<div class="ireason"><b>'+T.reason+'：</b>'+esc(a.reason)+'</div>':"";
  const it={id:"d-"+(a.topic_id||a.url||a.title).replace(/[^a-zA-Z0-9]/g,"").slice(0,16), zh_full:a.zh_full, llm_summary:a.llm_summary, summary:a.summary, url:a.url};
  return '<div class="dpick"><div class="t"><a href="'+esc(a.url)+'" target="_blank" rel="noopener" data-read="'+esc(a.url)+'">'+esc(a.title)+'</a></div>'
    +'<div class="m"><span>'+esc(a.source)+'</span><span>'+esc(pubLabel(a))+'</span>'+densBadge(a.density)+'</div>'+reason+(a.summary?'<div class="isum">'+esc(a.summary.length>160?a.summary.slice(0,160)+"…":a.summary)+'</div>':"")+expandBtn(it)+expandBody(it)+'</div>';
}
function renderDaily(){
  const root=$("#view-daily"); const dates=Object.keys(C.dailies||{}).sort().reverse();
  const d=state.dailyDate&&C.dailies[state.dailyDate]?state.dailyDate:(dates[0]||todayCN()); state.dailyDate=d;
  const rep=C.dailies[d];
  let side='<aside class="dside"><div class="card"><h3>'+T.archive+'（'+dates.length+'）</h3>';
  const latestM=(dates[0]||"").slice(0,7), col=state.arcCollapsed||(state.arcCollapsed={});
  const mcount={}; dates.forEach(x=>{const k=x.slice(0,7); mcount[k]=(mcount[k]||0)+1;});
  const mOpen=m=>(m in col)?!col[m]:(m===latestM);
  let cm=""; for(const x of dates){ const m=x.slice(0,7);
    if(m!==cm){ if(cm) side+='</div>'; cm=m; const op=mOpen(m);
      side+='<div class="amonth'+(op?' open':'')+'" data-m="'+m+'"><span>'+m+' <span class="mcount">'+mcount[m]+'</span></span><span class="chev">'+(op?'▾':'▸')+'</span></div><div class="adays'+(op?'':' hide')+'">'; }
    side+='<div class="dday'+(x===d?" on":"")+'" data-d="'+x+'"><span>'+x.slice(5)+'</span><span>'+wdCN(x)+'</span></div>'; }
  if(cm) side+='</div>';
  side+='</div></aside>';
  let body='<div class="dbody">';
  if(rep){
    body+='<div class="deye">'+BRAND()+' DAILY · '+esc(chn().toUpperCase())+'</div><div class="dtitle">'+esc(rep.label)+' · '+esc(rep.weekday)+'</div>';
    const hl=rep.headline||(((rep.sections||[])[0]||{}).articles||[])[0];
    if(hl){ body+='<div class="hero"><div class="k">'+T.headlineK+'</div><div class="t"><a href="'+esc(hl.url)+'" target="_blank" rel="noopener" data-read="'+esc(hl.url)+'">'+esc(hl.title)+'</a></div><div class="m"><span>'+esc(hl.source)+'</span><span>'+esc(pubLabel(hl))+'</span>'+densBadge(hl.density)+'</div>'+(hl.image?'<img class="himg" src="'+esc(hl.image)+'" alt="" loading="lazy">':"")+(hl.reason?'<div class="ireason"><b>'+T.reason+'：</b>'+esc(hl.reason)+'</div>':"")+(hl.summary?'<div class="isum">'+esc(hl.summary)+'</div>':"")+'</div>'; }
    const picks=rep.picks||[];
    if(picks.length){ body+='<div class="dsec-t">'+T.picksK+'</div><div class="dpicks">'+picks.map(a=>dailyArticle(a)).join("")+'</div>'; }
    const flash=rep.flash||[];
    if(flash.length){ body+='<div class="dsec-t">'+T.flashK+'</div><ul class="flash">'+flash.map(a=>'<li><span class="dot">•</span><span><a href="'+esc(a.url)+'" target="_blank" rel="noopener" data-read="'+esc(a.url)+'">'+esc(a.title)+'</a> <span style="color:var(--ink4);font-size:12px">'+esc(a.source)+'</span></span></li>').join("")+'</ul>'; }
    const secs=(rep.sections||[]).filter(s=>s.articles&&s.articles.length);
    if(secs.length){ body+='<div class="dsec-t">'+T.moreK+'</div>'+secs.map(s=>'<div class="dpick"><div class="t" style="font-size:13.5px;color:var(--acd)">'+esc(catName(s.category))+' · '+s.articles.length+'</div>'+s.articles.slice(0,5).map(a=>'<div style="font-size:13px;padding:3px 0"><a href="'+esc(a.url)+'" target="_blank" rel="noopener" data-read="'+esc(a.url)+'">'+esc(a.title)+'</a></div>').join("")+'</div>').join(""); }
  } else { body+='<div class="empty">-</div>'; }
  body+='</div>';
  root.innerHTML='<div class="card ph"><h1>'+esc(dailyPage())+'</h1><span class="sub">'+esc(dailySub())+'</span></div><div class="dshell">'+side+body+'</div>';
  $$(".dday", root).forEach(el=>el.onclick=()=>{ state.dailyDate=el.dataset.d; renderDaily(); });
  $$(".amonth", root).forEach(el=>el.onclick=()=>{ const m=el.dataset.m; col[m]=mOpen(m); renderDaily(); });
}
function renderTopics(){
  const root=$("#view-topics"); const rows=(C.daily&&C.daily.byCategory)||[];
  root.innerHTML='<div class="card ph"><h1>'+T.topics+'</h1><span class="sub">'+esc(chn()+T.topicsSub)+'</span></div><div class="tgrid">'+rows.map(r=>'<div class="tcard" data-cat="'+esc(r.category)+'"><div class="n">'+esc(catName(r.category))+'<span class="bdg b-cat">'+r.total+'</span></div><div class="nums"><span>24h <b>'+r.last24h+'</b></span><span>7d <b>'+r.last7d+'</b></span></div></div>').join("")+'</div>';
  $$(".tcard", root).forEach(el=>el.onclick=()=>{ state.cat=el.dataset.cat; location.hash="#/all"; });
}
function renderTrends(){
  const root=$("#view-trends"); const tr=C.trends||{};
  const weekStart=tr.weekStart||"";
  let html='<div class="card ph"><h1>'+esc(chn()+(LANG==="en"?" Trends":"趋势"))+'</h1><span class="sub">'+esc((LANG==="en"?"This week vs last week":"本周 vs 上周")+(weekStart?' · '+fmtDay(weekStart):""))+'</span></div>';
  const deltas=tr.categoryDelta||[];
  if(!deltas.length){ root.innerHTML=html+'<div class="card"><p class="anote" style="padding:16px 18px">'+T.noTrend+'</p></div>'; return; }
  const maxV=Math.max(...deltas.map(x=>x.thisWeek),1);
  const bars=deltas.map(x=>{
    const pct=x.deltaPct; const cls=pct>5?"tup":(pct<-5?"tdown":"tflat");
    const arrow=pct>5?"▲":(pct<-5?"▼":"—");
    const w=Math.max(2,x.thisWeek/maxV*100).toFixed(1);
    return '<div class="tbar-row"><span class="tbar-name">'+esc(catName(x.category))+'</span><div class="tbar-track"><div class="tbar-fill" style="width:'+w+'%"></div></div><span class="tbar-val mono">'+x.thisWeek.toFixed(0)+' <span class="'+cls+'">'+arrow+' '+Math.abs(pct)+'%</span></span></div>';
  }).join("");
  html+='<div class="tsec-title">'+T.catDelta+'</div><div class="tcard" style="cursor:default">'+bars+'</div>';
  const mkList=(arr)=>arr.map(t=>'<div class="tcard" style="cursor:default"><div style="font-weight:650;font-size:14px">'+esc(t.title)+'</div><div style="font-size:12px;color:var(--ink3);margin-top:4px">🔥 '+Math.round(t.score)+' · '+(t.days!=null?t.days+(LANG==="en"?" days":" 天"):"")+'</div></div>').join("");
  if((tr.newTopics||[]).length) html+='<div class="tsec-title">🆕 '+T.newTopics+'</div>'+mkList(tr.newTopics);
  if((tr.sustainedTopics||[]).length) html+='<div class="tsec-title">♨️ '+T.sustained+'</div>'+mkList(tr.sustainedTopics);
  root.innerHTML=html;
}
function renderData(){
  const root=$("#view-data"); const dl=C.daily||{byDay:[],bySource:[]};
  const maxDay=Math.max(...dl.byDay.map(x=>x.count),1);
  const chart='<div class="chart">'+dl.byDay.map(x=>'<div class="bcol"><div class="bar" title="'+x.date+': '+x.count+'" style="height:'+Math.max(2,x.count/maxDay*100).toFixed(1)+'%"></div><span class="dl">'+x.date.slice(5)+'</span></div>').join("")+'</div>';
  const rows=(dl.bySource||[]).map(s=>'<tr><td>'+esc(s.source)+'</td><td>'+s.count+'</td><td>'+fmtRel(s.latestAt)+'</td></tr>').join("");
  root.innerHTML='<div class="card ph"><h1>'+T.dataPage+'</h1><span class="sub">'+T.dataSub+'</span></div>'
    +'<div class="stats"><div class="stat"><div class="num">'+dl.total+'</div><div class="lbl">'+T.total+'</div></div><div class="stat"><div class="num">'+dl.last24h+'</div><div class="lbl">'+T.h24+'</div></div><div class="stat"><div class="num">'+dl.last7d+'</div><div class="lbl">'+T.h7+'</div></div><div class="stat"><div class="num">'+dl.topicCount+'</div><div class="lbl">'+T.hotTopic+'</div></div></div>'
    +'<div class="card" style="padding:16px 18px"><h3 style="font-size:14px;margin-bottom:6px">'+T.trend+'</h3>'+chart+'</div>'
    +'<div class="card" style="padding:16px 18px;margin-top:14px"><h3 style="font-size:14px;margin-bottom:6px">'+T.srcTable+'</h3><table><thead><tr><th>'+T.srcTable+'</th><th>'+T.total+'</th><th>'+T.latest+'</th></tr></thead><tbody>'+rows+'</tbody></table></div>'
    +'<div class="dlrow"><a class="btn" href="data/'+CHID+'/report.csv" download>'+T.dlCSV+'</a><a class="btn" href="data/'+CHID+'/items.json" target="_blank">'+T.dlItems+'</a><a class="btn" href="data/'+CHID+'/hot-topics.json" target="_blank">'+T.dlHot+'</a><a class="btn" href="data/'+CHID+'/dailies.json" target="_blank">'+T.dlDaily+'</a></div>';
}
function renderAgent(){
  const root=$("#view-agent");
  const base=location.href.split("?")[0].split("#")[0].replace(/index\.html$/,"");
  const eps=[["items",T.dlItems],["hot-topics",T.dlHot],["dailies",T.dlDaily],["daily","daily.json"],["stories","stories.json"],["trends","trends.json"]];
  const rows=eps.map(([k,d])=>'<tr><td class="mono">api/v1/'+CHID+'/'+k+'.json</td><td>'+d+'</td><td><a href="'+base+'api/v1/'+CHID+'/'+k+'.json" target="_blank" rel="noopener">'+T.open+' ↗</a></td></tr>').join("");
  const curl=eps.map(([k])=>'curl '+base+'api/v1/'+CHID+'/'+k+'.json').join("\n");
  const catFeeds=Object.entries(CAT_CLS).map(([cat,slug])=>["feed/"+CHID+"/category/"+slug+".xml",cat]);
  const feedRows=['<tr><td class="mono">feed.xml</td><td>RSS（T 光电主 feed）</td><td><a href="'+base+'feed.xml" target="_blank" rel="noopener">'+T.open+' ↗</a></td></tr>']
    .concat(catFeeds.map(([f,cat])=>'<tr><td class="mono">'+f+'</td><td>'+esc(catName(cat))+'</td><td><a href="'+base+f+'" target="_blank" rel="noopener">'+T.open+' ↗</a></td></tr>')).join("");
  const moreRows='<tr><td class="mono">api/v1/openapi.json</td><td>OpenAPI 3.1</td><td><a href="'+base+'api/v1/openapi.json" target="_blank" rel="noopener">'+T.open+' ↗</a></td></tr><tr><td class="mono">llms.txt</td><td>LLM 友好入口</td><td><a href="'+base+'llms.txt" target="_blank" rel="noopener">'+T.open+' ↗</a></td></tr>';
  root.innerHTML='<div class="card ph"><h1>'+T.agentPage+'</h1><span class="sub">'+T.agentSub+'</span></div>'
    +'<div class="card" style="padding:16px 18px"><h3 style="font-size:15px;margin-bottom:4px">🤖 '+T.apiTitle+'</h3><p class="anote">'+T.apiDesc+'</p><p class="anote">'+T.base+'：<span class="mono">'+esc(base)+'</span></p><table style="margin-top:10px"><thead><tr><th>'+T.endpoint+'</th><th>'+T.desc+'</th><th></th></tr></thead><tbody>'+rows+moreRows+'</tbody></table></div>'
    +'<div class="card" style="padding:16px 18px;margin-top:14px"><h3 style="font-size:15px;margin-bottom:4px">RSS</h3><table style="margin-top:8px"><tbody>'+feedRows+'</tbody></table></div>'
    +'<div class="card" style="padding:16px 18px;margin-top:14px"><h3 style="font-size:15px;margin-bottom:4px">'+T.curl+'</h3><pre>'+esc(curl)+'</pre><p class="anote">'+T.llmsNote+'</p></div>';
}
function renderMore(){
  const root=$("#view-more");
  const rows=[["#/all","allPage","menuAllSub","☰"],["#/topics","topics","menuTopicsSub","◈"],["#/data","data","menuDataSub","◉"],["#/agent","agent","menuAgentSub","🤖"]];
  root.innerHTML='<div class="card ph"><h1>'+T.more+'</h1></div><div class="card">'+rows.map(r=>'<a class="mrow" href="'+r[0]+'"><span style="font-size:18px">'+r[3]+'</span><span>'+T[r[1]]+'<small>'+T[r[2]]+'</small></span><span class="go">›</span></a>').join("")+'</div>';
}
function BRAND(){ return "PAT-HOT"; }
renderers.feed=renderFeed; renderers.all=renderAll; renderers.hot=renderHot; renderers.daily=renderDaily; renderers.topics=renderTopics; renderers.data=renderData; renderers.trends=renderTrends; renderers.agent=renderAgent; renderers.more=renderMore;
function bind(){
  const q=$("#q");
  let qTimer=null; q.addEventListener("input",e=>{ state.q=e.target.value; clearTimeout(qTimer); qTimer=setTimeout(()=>{ if(/#\/all/.test(location.hash)){ state.allShown=ALL_PAGE; renderAll(); } },250); });
  $("#sbtn").onclick=()=>{ const w=$("#swrap"); w.classList.toggle("open"); if(w.classList.contains("open")) q.focus(); };
  $("#lang").onclick=()=>{ LANG=LANG==="zh"?"en":"zh"; try{localStorage.setItem("pat-lang",LANG);}catch(e){} location.reload(); };
  document.addEventListener("click",e=>{
    const f=e.target.closest("[data-fav]");
    if(f){ e.preventDefault(); toggleFav(f.dataset.fav); f.classList.toggle("on"); return; }
    const xf=e.target.closest("[data-x]");
    if(xf){ e.preventDefault(); toggleExpand(xf); return; }
    const dh=e.target.closest("[data-dayh]");
    if(dh){ const d=dh.dataset.dayh; state.collapsed[d]=!state.collapsed[d]; dh.closest(".day").classList.toggle("closed"); dh.querySelector(".arr").textContent=state.collapsed[d]?"▶":"▼"; return; }
    const r=e.target.closest("[data-read]");
    if(r){ markRead(r.dataset.read); const c=r.closest(".icard"); if(c) c.classList.add("read"); }
  });
  window.addEventListener("hashchange",router);
  document.addEventListener("keydown",e=>{ if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==="k"){ e.preventDefault(); $("#swrap").classList.add("open"); q.focus(); } });
  renderChSeg(); tr(); router();
}
document.addEventListener("DOMContentLoaded", bind);
