const S = __SNAPSHOT__;
const META = S.meta || {channels:[], default:"tech"};
const $ = (sel, root=document) => root.querySelector(sel);
const $$ = (sel, root=document) => [...root.querySelectorAll(sel)];
const esc = s => String(s==null?"":s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
// ---- 主题 ----
// 首屏前的内联脚本已把 data-theme 落到 <html> 上，这里只接管切换。
function themeNow(){ return document.documentElement.getAttribute("data-theme")==="dark"?"dark":"light"; }
function setTheme(t){ try{ localStorage.setItem("pat-theme",t); }catch(e){}
  document.documentElement.setAttribute("data-theme",t);
  const b=$("#theme"); if(b) b.textContent = t==="dark"?"☀":"◐"; }
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
    allPage:"全部动态", hotPage:"热点榜", topics:"主题", data:"数据", agent:"Agent 接入",
    search:"搜索", catAll:"全部", sortScore:"按推荐分", sortTime:"按时间",
    thresholdNote:"精选门槛：官方信源 ≥ {o} 分 · 媒体信源 ≥ {m} 分（可在 collector/config.json 调整）",
    hotNow:"当前热点", fullRank:"完整榜单 →", unreadOnly:"只看未读", sciOnly:"只看科研", today:"今天", daySel:"条精选", noMatch:"没有匹配的条目",
    heatVal:"热度", sources:"信源", signals:"信号",
    mvNew:"新", mvRise:"升温", mvSurge:"多家跟进", mvDown:"回落",
    digestLabel:"事件概览 | ",
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
    favPage:"收藏", favSub:"点过的星标都在这里（只存在本浏览器）", noFav:"还没有收藏：点卡片右上角的 ★ 收藏一条", favCount:"{n} 条收藏",
    bakNote:"已读 / 收藏 / 主题 / 语言 / 频道只存在这台浏览器，清缓存就会丢——导出备份换设备也能带走。",
    bakExport:"导出备份", bakImport:"导入备份", bakDone:"已导入 {n} 项设置，页面即将刷新", bakFail:"读写失败，请重试", badFile:"这不是 PAT-HOT 备份文件，未做任何改动",
    extNote:"原文·需外网", readOrig:"阅读原文 ↗（需外网）", importSM:"📥 导入学术星轨", loadMore:"加载更多", aiGen:"生成中文摘要", aiLoading:"生成中…", aiFail:"生成失败，点击重试",
    footer:"PAT-HOT · 物理·天文·光电热点统计（AIHOT 方法论）· 数据来自公开网络，仅供参考，不构成投资建议 · GitHub 开源" },
  en: { feed:"Selected", all:"All", hot:"Hot", daily:"Daily", trends:"Trends", more:"More",
    allPage:"All Items", hotPage:"Hot Ranking", topics:"Topics", data:"Data", agent:"Agent API",
    search:"Search", catAll:"All", sortScore:"By score", sortTime:"By time",
    thresholdNote:"Selection bar: official sources ≥ {o} · media sources ≥ {m} (tune in collector/config.json)",
    hotNow:"Trending Now", fullRank:"Full ranking →", unreadOnly:"Unread only", sciOnly:"Research only", today:"Today", daySel:"selected", noMatch:"No matching items",
    heatVal:"heat", sources:"sources", signals:"signals",
    mvNew:"new", mvRise:"rising", mvSurge:"surge", mvDown:"cooling",
    digestLabel:"In brief | ",
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
    favPage:"Saved", favSub:"Your stars live in this browser only", noFav:"Nothing saved yet — tap ★ on a card to save it", favCount:"{n} saved",
    bakNote:"Read / saved / theme / language / channel live in this browser only — export a backup before clearing data or switching devices.",
    bakExport:"Export backup", bakImport:"Import backup", bakDone:"Restored {n} settings; reloading", bakFail:"Read/write failed, please retry", badFile:"Not a PAT-HOT backup — nothing changed",
    extNote:"orig.·needs internet", readOrig:"Read original ↗ (needs internet)", importSM:"📥 Import to ScholarMatrix", loadMore:"Load more", aiGen:"Generate Chinese summary", aiLoading:"Generating…", aiFail:"Failed, tap to retry",
    footer:"PAT-HOT · physics / astronomy / photonics hot-topic stats (AIHOT methodology) · public data, for reference only · open source on GitHub" }
};
let LANG = "zh";
try { LANG = localStorage.getItem("pat-lang") || "zh"; } catch(e){}
const T = I18N[LANG] || I18N.zh;
function chn(){ return LANG==="en" ? C.name.en : C.name.zh; }
function feedSub(){ return LANG==="en" ? chn()+" timeline ranked by score" : "按推荐分排序的"+chn()+"时间线"; }
// 新鲜度说明：数据更新时间 vs 最新文章发布时间，直接回应「数据是昨天的」误会
function freshNote(){
  const gen=C.generatedAt||""; let genTxt="";
  if(gen){ const d=new Date(gen); const b=new Date(d.getTime()+8*3600*1000);
    const today=todayCN(); const gd=b.toISOString().slice(0,10);
    const hm=String(b.getUTCHours()).padStart(2,"0")+":"+String(b.getUTCMinutes()).padStart(2,"0");
    genTxt=(gd===today?(LANG==="en"?"today ":"今天 "):fmtDay(gd)+" ")+hm; }
  let latest=""; for(const it of (C.items||[])){ const p=it.published_at||""; if(p>latest) latest=p; }
  let latTxt=""; if(latest){ const lp=latest.slice(0,10);
    latTxt=(lp===todayCN()?(LANG==="en"?"today ":"今天 "):fmtDay(lp)+" ")+latest.slice(11,16); }
  if(LANG==="en") return "📡 Data updated "+genTxt+" · Newest article "+latTxt;
  return "📡 数据 "+genTxt+" 更新 · 最新文章 "+latTxt+" 发布";
}
function hotPage(){ return chn()+(LANG==="en"?" Hot Ranking":"热点榜"); }
function hotSub(){ return LANG==="en" ? "Event-level heat: each independent source counts once per 48h" : "事件级热度：48 小时内每独立来源只计一次"; }
function dailyPage(){ return chn()+(LANG==="en"?" Daily":"日报"); }
function dailySub(){ return LANG==="en" ? "Auto-generated daily (with archive)" : "自动生成 · 每日一篇（含历史归档）"; }
function searchPh(){ return T.search+chn()+(LANG==="en"?" news…":"资讯 / 关键词…"); }
const state = { q:"", cat:"全部", sort:"score", dailyDate:"", hotSort:"heat", unreadOnly:false, collapsed:{} };
// 非科研分类：采集端 category_weights 降权的对象；前端「只看科研」开关过滤的对象。两处保持一致。
const NON_SCI_CATS = ["其他","产业与资本"];
const SCI_KEY = "pat-sci-only";
function sciOnly(){ try{ return localStorage.getItem(SCI_KEY)==="1"; }catch(e){ return false; } }
function setSciOnly(v){ try{ localStorage.setItem(SCI_KEY, v?"1":"0"); }catch(e){} }
function sciFilter(items){ return sciOnly()?items.filter(i=>NON_SCI_CATS.indexOf(i.category)<0):items; }
function lsGet(k){ try{ return JSON.parse(localStorage.getItem(k)||"{}"); }catch(e){ return {}; } }
function lsSet(k,v){ try{ localStorage.setItem(k, JSON.stringify(v)); }catch(e){} }
let READ = lsGet("pat-read"), FAV = lsGet("pat-fav");
function markRead(u){ if(!u||READ[u]) return; READ[u]=1; const ks=Object.keys(READ); if(ks.length>800) ks.slice(0,300).forEach(k=>delete READ[k]); lsSet("pat-read",READ); applyReadToDom(u); if(state.unreadOnly) removeCardNodeOrInvalidate("feed", u, "read"); }
// 删掉"某一条"（读掉/取消收藏）时，可见视图只删那一个节点，别整页重画：
// innerHTML 重建会销毁滚动锚点，实测只看未读时读掉视口上方的卡，scrollY 不变
// 但视口中心的内容跳了约一张卡（anchorKept:false）——点开文章回来列表已经跳位，
// 正是录屏最后"往回滑找位置"的机制。节点级删除浏览器 scroll anchoring 认得，
// 会自动补偿上方高度；隐藏视图没有滚动位置可言，照常 invalidate 即可。
// 选择器一律不用（URL 塞进属性选择器还得转义），直接比 dataset。
function removeCardNodeOrInvalidate(v, u, attr){
  if(v!==LAST_VIEW){ invalidate(v); return; }
  const root=$("#view-"+v); if(!root){ invalidate(v); return; }
  $$("["+ (attr==="read"?"data-read":"data-fav") +"]", root).forEach(el=>{
    if(el.dataset[attr==="read"?"read":"fav"]!==u) return;
    const c=el.closest(".icard"); if(!c) return;
    const day=c.closest(".day");
    c.remove();
    if(!day) return;
    if(!day.querySelectorAll(".icard").length){ day.remove(); return; } // 整天读完别留空标题
    const ce=day.querySelector(".day-h .c");
    const n=ce?parseInt(ce.textContent,10):NaN;   // "20 条精选"跟着减一，不然计数说谎
    if(ce && !isNaN(n)) ce.textContent=(n-1)+" "+T.daySel;
  });
  // 删空了要补空态：节点级删除绕过了 renderer，不补就是一屏空白，看着像坏了
  if(!root.querySelector(".icard")){
    root.insertAdjacentHTML("beforeend", v==="fav"
      ? '<div class="card empty">'+T.noFav+'</div>'
      : '<div class="empty">'+T.noMatch+'</div>');
  }
}
// 已读/收藏是"某一张卡片"的状态，而卡片可能同时存在于多个常驻视图里。
// 视图现在带缓存，重进不会重画，所以这类状态必须就地写回 DOM，
// 而不是靠重绘传播——否则切回来会看到别的视图还是旧样子。
function applyReadToDom(u){
  $$('[data-read]').forEach(a=>{ if(a.dataset.read===u){ const c=a.closest(".icard"); if(c) c.classList.add("read"); } });
}
function toggleFav(u){ if(FAV[u]) delete FAV[u]; else FAV[u]=1; lsSet("pat-fav",FAV); applyFavToDom(u); removeCardNodeOrInvalidate("fav", u, "fav"); invalidate("more"); }
function applyFavToDom(u){
  $$('[data-fav]').forEach(b=>{ if(b.dataset.fav===u) b.classList.toggle("on", !!FAV[u]); });
}
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
// 每条都可展开。展开区里要么已有中文（zh_full / llm_summary），要么有「✨生成中文摘要」按钮
// （!zh_full 时渲染），要么至少是「阅读原文」——旧门槛 it.zh_full||llm_summary||summary>160
// 恰好把摘要为空的条目挡在门外，而那正是最需要按需生成中文的一类（按需通道的存在意义）。
function expandable(){ return true; }
function expandBtn(it){ if(!expandable(it)) return ""; const open=EXPANDED.has(it.id); return '<button class="xbtn'+(open?" open":"")+'" data-x="'+it.id+'"><span>'+(open?T.collapse:T.expand)+'</span><span class="xa">▼</span></button>'; }
// ---- 导入学术星轨（生态打通 · 闭环1） ----
// 学术星轨 deep-link 导入协议：?add=<base64url(JSON.stringify(descriptors[]))>
// descriptor: {title?, authors?, year?, journal?, doi?, arxiv?, url?, abstract?, kind?}
function b64url(s){ const b=btoa(unescape(encodeURIComponent(s))); return b.replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/,""); }
function smImportUrl(it){
  const d={ title:it.title||"", url:it.url||"", abstract:it.zh_full||it.llm_summary||it.summary||"", journal:it.source||"", kind:"news" };
  return "https://scholarmatrix.pages.dev/?add="+b64url(JSON.stringify([d]));
}
function smImportBtn(it){ if(!it.url) return ""; return '<a class="smbtn" href="'+smImportUrl(it)+'" target="_blank" rel="noopener">'+T.importSM+'</a>'; }
function expandBody(it){ if(!expandable(it)) return ""; const open=EXPANDED.has(it.id);
  const zf=it.zh_full?'<div class="xsec">'+T.aiSum+'</div><div class="xt">'+esc(it.zh_full)+'</div>':"";
  const ai=!it.zh_full&&it.llm_summary?'<div class="xsec">'+T.aiSum+'</div><div class="xt">'+esc(it.llm_summary)+'</div>':"";
  const rs=it.summary?'<div class="xsec">'+T.srcSum+'</div><div class="xt">'+esc(it.summary)+'</div>':"";
  const src=it.url?'<div class="xsrc"><a href="'+esc(it.url)+'" target="_blank" rel="noopener">'+T.readOrig+'</a>'+smImportBtn(it)+'</div>':"";
  // 按需 AI 中文摘要：没有 zh_full 时显示按钮
  const od=!it.zh_full?'<div class="xod" id="xod-'+it.id+'"><button class="obtn" data-od="'+esc(it.url)+'">✨ '+T.aiGen+'</button><div class="otxt" style="display:none"></div></div>':"";
  return '<div class="xbody'+(open?" open":"")+'" id="xb-'+it.id+'"><div class="xbody-in">'+zf+ai+rs+od+src+'</div></div>'; }
function toggleExpand(btn){ const id=btn.dataset.x;
  // CSS.escape 是给选择器用的，不是给 getElementById 用的：id 以数字开头时它会返回
  // "\35 91a…"，而 DOM 里写的是原始 id="xb-591a…"，于是查不到、按钮点了正文永远不展开。
  // 全站 577 条里有 364 条（63%）的 id 是纯十六进制、以数字开头，全都中招。
  const body=document.getElementById("xb-"+id);
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
    const WORKER_URL=window.PAT_LLM_WORKER||(/(^|\.)pages\.dev$/i.test(location.hostname)?"/api/summarize":"https://pat-hot.pages.dev/api/summarize");
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
  state.dailyDate=""; state.cat="全部"; state.q=""; state.allShown=ALL_PAGE; state.collapsed={}; const q=$("#q"); if(q) q.value="";
  // 换频道等于换了全部数据，九个常驻视图的缓存一起作废
  invalidateAll();
  try{ localStorage.setItem("pat-channel",id); }catch(e){}
  renderChSeg(); tr(); router(); }
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
let LAST_VIEW = "";
// RENDERED：DOM 已经画好、且内容仍然有效的视图。<section> 是常驻的，切 tab 只是
// display:none，所以 DOM 本来就还在——重进时不该再画一遍，也不该丢掉阅读位置。
// 只有数据/筛选真的变了才 invalidate，让 router 重画。
const RENDERED = new Set();
const SCROLL = {};
let RENDERING = "";
function invalidate(v){
  RENDERED.delete(v);
  // 作废的恰好是屏幕上这个视图时，必须立刻重画。否则用户会看到过期内容：
  // 在收藏页把某条取消星标，它还留在列表里，要切走再切回才消失。
  if(v===LAST_VIEW && !RENDERING){
    RENDERING=v;
    // 重画成功后必须标回 RENDERED：刚画好的视图就是"已渲染且有效"。
    // 漏了这一步，之后用户滚动的位置在切走时不会被记录（router 的
    // RENDERED.has 条件不成立），切回时被当成首访重画+弹回顶部，
    // 位置缓存对"筛选过的视图"静默失效。渲染抛错则不标（下次会重试）。
    try{ (renderers[v]||renderers.feed)(); RENDERED.add(v); } finally{ RENDERING=""; }
  }
}
function invalidateAll(){ RENDERED.clear(); for (const k in SCROLL) delete SCROLL[k]; }
// 列表内容被整体替换（排序/分类/搜索/日期/未读筛选）后，旧滚动位置不再对应任何
// 内容：留在原地=落在新列表的中段，滚得深了还会被钳到新列表底部。必须回顶部，
// 且缓存位置要一起清零——否则切走再切回，router 会把旧 y 恢复到换掉后的列表上。
// 注意与"删掉一条"（取消星标）区分：那种保持位置，交给浏览器 scroll anchoring。
function contentReset(v){ SCROLL[v]=0; invalidate(v); if(v===LAST_VIEW) window.scrollTo(0,0); }
// 只看科研是持久开关，同时决定精选页和全部页的列表内容。视图带缓存后，只 reset
// 当前视图会让另一个视图留着上一个筛选条件的列表 + 旧滚动位置，切过去才看到过期
// 内容（位置还会被错误恢复）。两个视图一起重置。
function sciToggle(){ setSciOnly(!sciOnly()); state.allShown=ALL_PAGE; contentReset("feed"); contentReset("all"); }
function setNav(v){ $$("#tabbar a").forEach(a=>a.classList.toggle("on",a.dataset.v===v)); $$("#dnav a").forEach(a=>a.classList.toggle("on",a.dataset.v===v)); $$(".seg a").forEach(a=>a.classList.toggle("on",a.dataset.seg===v)); }
function router(){
  const h=(location.hash||"#/").replace("#",""); const name=h.split("?")[0]||"/";
  const map={"/":"feed","/all":"all","/hot":"hot","/daily":"daily","/topics":"topics","/trends":"trends","/data":"data","/fav":"fav","/agent":"agent","/more":"more"};
  const v=map[name]||"feed";
  // 先记下旧视图的位置：下面一改 class，旧视图就 display:none，文档高度塌了，
  // scrollY 会被浏览器钳到 0，那时候再读已经来不及。
  if(LAST_VIEW && RENDERED.has(LAST_VIEW)) SCROLL[LAST_VIEW]=Math.round(window.scrollY);
  const retap=(v===LAST_VIEW);
  LAST_VIEW=v;
  setNav(v);
  $$(".view").forEach(x=>x.classList.remove("on"));
  const el=$("#view-"+v); if(!el) return;
  el.classList.add("on");
  if(!RENDERED.has(v)){ (renderers[v]||renderers.feed)(); RENDERED.add(v); window.scrollTo(0,0); }
  else if(retap){ window.scrollTo(0,0); }              // 再点当前 tab：回顶部，和原生 app 一致
  else { window.scrollTo(0, SCROLL[v]||0); }           // 切回来：回到读过的地方
}
function renderFeed(){
  const root=$("#view-feed");
  const top=(C.topics||[]).slice(0,3);
  let hot='<div class="card hottop"><div class="hottop-h"><span class="pulse"></span>'+T.hotNow+'<a href="#/hot">'+T.fullRank+'</a></div>'
  +top.map((t,i)=>{ const up=trendOf(t)==="up"; const arrow=up?'<span class="up">▲</span>':"—";
    const rurl=esc((t.representative||{}).url||"#/hot");
    return '<div class="hr3"><span class="rk r'+(i+1)+'">'+(i+1)+'</span><span class="ht"><a href="'+rurl+'" target="_blank" rel="noopener">'+esc(t.title)+'</a></span><span class="hn mono">'+Math.round(t.heat||t.score)+' <small>'+T.heatVal+'</small> '+arrow+'</span></div>'; }).join("")+'</div>';
  let items=C.items.slice();
  if(state.unreadOnly) items=items.filter(i=>!READ[i.url]);
  items=sciFilter(items);
  const groups={}; for(const it of items){ const d=effDate(it); (groups[d]=groups[d]||[]).push(it); }
  const days=Object.keys(groups).sort().reverse().slice(0,7);
  let tl='<div class="urow"><button class="upill'+(state.unreadOnly?" on":"")+'" id="unreadBtn"><span class="dot"></span>'+T.unreadOnly+'</button><button class="upill'+(sciOnly()?" on":"")+'" id="sciBtn"><span class="dot"></span>🔬 '+T.sciOnly+'</button></div>';
  if(!days.length) tl+='<div class="empty">'+T.noMatch+'</div>';
  for(const d of days){ const its=groups[d].slice().sort((a,b)=>b.score-a.score).slice(0,20);
    const closed=state.collapsed[d]?" closed":"";
    tl+='<div class="day'+closed+'"><div class="day-h" data-dayh="'+d+'"><h2>'+(isToday(d)?T.today+" ":"")+fmtDay(d)+'</h2><span class="w">'+wdCN(d)+'</span><span class="c">'+its.length+' '+T.daySel+'</span><span class="arr">'+(state.collapsed[d]?"▶":"▼")+'</span></div><div class="day-b">'+its.map(itemCard).join("")+'</div></div>'; }
  root.innerHTML='<div class="card ph"><h1>'+T.feed+'</h1><span class="sub">'+esc(feedSub())+'</span><div class="note">'+esc(freshNote())+'</div><div class="note">'+esc(threshNote())+'</div></div>'+hot+tl;
  const ub=$("#unreadBtn"); if(ub) ub.onclick=()=>{ state.unreadOnly=!state.unreadOnly; contentReset("feed"); };
  const sb=$("#sciBtn"); if(sb) sb.onclick=sciToggle;
}
const ALL_PAGE=30;
let allObserver=null;
// allCtx 保存"当前这一张列表"：its=过滤排序后的全集，rendered=已经插进 DOM 的条数。
// 只有筛选/排序/搜索/换频道才整页重建；无限滚动一律往后追加，绝不重写已有卡片。
let allCtx=null;
function allQuery(){
  let its=sciFilter(C.items.slice());
  if(state.q){ const q=state.q.toLowerCase(); its=its.filter(i=>(i.title+" "+(i.zh_full||i.llm_summary||i.summary||"")+" "+i.source).toLowerCase().includes(q)); }
  if(state.cat!=="全部") its=its.filter(i=>i.category===state.cat);
  if(state.sort==="score") its.sort((a,b)=>b.score-a.score); else its.sort((a,b)=>b.discovered_at.localeCompare(a.discovered_at));
  return its;
}
function moreLabel(shown,total){ return T.loadMore+' ('+shown+'/'+total+')'; }
function observeMore(){
  if(allObserver) allObserver.disconnect();
  const more=$("#all-more"); if(!more) return;
  more.onclick=appendAllPage;
  allObserver=new IntersectionObserver(es=>{ if(es.some(e=>e.isIntersecting)) appendAllPage(); },{rootMargin:"800px"});
  allObserver.observe(more);
}
// 追加下一页。这里刻意不碰已渲染的 DOM：整页 innerHTML 重建会让浏览器把
// 已有卡片全部作废重排，实测一次 180~280ms，正好落在用户手指还在滑的那一帧。
function appendAllPage(){
  if(!allCtx) return;
  const its=allCtx.its, from=allCtx.rendered;
  if(from>=its.length) return;
  const to=Math.min(from+ALL_PAGE, its.length);
  const list=$("#all-list"); if(!list) return;
  if(allObserver) allObserver.disconnect();          // 先摘哨兵，避免这一帧连发两次
  list.insertAdjacentHTML("beforeend", its.slice(from,to).map(itemCard).join(""));
  allCtx.rendered=to; state.allShown=to;
  const more=$("#all-more");
  if(to>=its.length){ if(more) more.remove(); }
  else if(more){ more.textContent=moreLabel(to,its.length); observeMore(); }
}
function renderAll(){
  const root=$("#view-all"); const its=allQuery();
  const shown=Math.min(state.allShown||ALL_PAGE, its.length);
  allCtx={its,rendered:shown};
  const hasMore=shown<its.length;
  const isSearch=!!(state.q&&state.q.trim());
  const title=isSearch?('🔍 "'+state.q.trim()+'"') : T.allPage;
  const sub=isSearch?((LANG==="en"?"Search results · ":"搜索结果 · ")+its.length+(LANG==="en"?"":" 篇")) : (''+its.length);
  root.innerHTML='<div class="card ph"><h1>'+esc(title)+'</h1><span class="sub">'+esc(sub)+'</span><button class="upill'+(sciOnly()?" on":"")+'" id="sciBtnAll" style="margin-left:8px"><span class="dot"></span>🔬 '+T.sciOnly+'</button><span class="hsort" style="margin-left:auto"><select id="all-cat" aria-label="cat"><option value="全部">'+T.catAll+'</option></select><select id="all-sort" aria-label="sort"><option value="score">'+T.sortScore+'</option><option value="time">'+T.sortTime+'</option></select></span><div class="note">'+esc(threshNote())+'</div></div><div id="all-list">'+(its.length?its.slice(0,shown).map(itemCard).join(""):'<div class="empty">'+T.noMatch+'</div>')+'</div>'+(hasMore?'<div id="all-more" class="card" style="text-align:center;padding:14px;cursor:pointer;color:var(--acd);font-weight:600">'+moreLabel(shown,its.length)+'</div>':"");
  const cats=[...new Set(C.items.map(i=>i.category))];
  const sel=$("#all-cat"); for(const c of cats){ const o=document.createElement("option"); o.value=c; o.textContent=catName(c); if(c===state.cat) o.selected=true; sel.appendChild(o); }
  $("#all-sort").value=state.sort;
  sel.onchange=e=>{ state.cat=e.target.value; state.allShown=ALL_PAGE; contentReset("all"); };
  const sba=$("#sciBtnAll"); if(sba) sba.onclick=sciToggle;
  $("#all-sort").onchange=e=>{ state.sort=e.target.value; state.allShown=ALL_PAGE; contentReset("all"); };
  observeMore();
}
function hotExpand(t){ const rep=t.representative||{}; const it={id:"t-"+t.id, zh_full:rep.zh_full, llm_summary:rep.llm_summary, summary:rep.summary, url:rep.url||((t.links||[])[0]||{}).url};
  if(!expandable(it)) return ""; return expandBtn(it)+expandBody(it); }
// 运动徽标（与上一轮相比；collect.py compute_movement 产出，旧数据无字段时静默不显示）
function movementFlag(t){
  const b=t.badges||[]; const p=(typeof t.trendPct==="number")?Math.round(t.trendPct):null;
  const out=[];
  if(b.indexOf("surge")>=0) out.push('<span class="flag b-surge">'+T.mvSurge+(p!==null?" +"+p+"%":"")+'</span>');
  else if(b.indexOf("rising")>=0) out.push('<span class="flag b-rise">'+T.mvRise+(p!==null?" +"+p+"%":"")+'</span>');
  if(b.indexOf("new")>=0) out.push('<span class="flag b-new">'+T.mvNew+'</span>');
  if(t.trend==="down"&&p!==null) out.push('<span class="flag b-down">'+T.mvDown+' '+p+'%</span>');
  return out.join(" ");
}
function renderHot(){
  const root=$("#view-hot"); let ts=(C.topics||[]).slice();
  if(state.hotSort==="sources") ts.sort((a,b)=>b.source_count-a.source_count);
  const maxHeat=Math.max(...ts.map(t=>t.heat||t.score||0),1);
  const head='<div class="card ph"><h1>'+esc(hotPage())+'</h1><span class="sub">'+esc(hotSub())+'</span><span class="hsort"><button data-hs="heat" class="'+(state.hotSort==="heat"?"on":"")+'">'+T.heatVal+'</button><button data-hs="sources" class="'+(state.hotSort==="sources"?"on":"")+'">'+T.sources+'</button></span></div>';
  root.innerHTML=head+'<div class="card">'+ts.map((t,i)=>{
    const s=t.status; const flag=s==="爆"?'<span class="flag f-hot">'+statusName(s)+'</span>':(s==="发酵中"?'<span class="flag f-warm">'+statusName(s)+'</span>':'<span class="flag f-watch">'+statusName(s)+'</span>');
    const mflag=movementFlag(t);
    const rep=t.representative||{}; const rurl=rep.url||((t.links||[])[0]||{}).url||"";
    const reason=rep.llm_reason?'<div class="ireason"><b>'+T.reason+'：</b>'+esc(rep.llm_reason)+'</div>':"";
    const rsum=rep.llm_summary||rep.summary;
    // 事件综述优先（AIHOT story-digest）：多源事件只贴代表稿一句摘要是以偏概全，
    // 有综述就不再显示单篇摘要。综述标题概括整个事件，替代单篇标题展示。
    const shownTitle=t.digestTitle||t.title;
    const dg=t.digest?'<div class="hdigest"><b>'+esc(T.digestLabel)+'</b>'+esc(t.digest)+'</div>':"";
    const chips=((t.top_terms||[]).map(x=>'<span class="chip term">'+esc(x)+'</span>').join(""))+((t.sources||[]).map(x=>'<span class="chip">'+esc(x)+'</span>').join(""));
    const flinks=(t.links||[]).map(l=>'<a href="'+esc(l.url)+'" target="_blank" rel="noopener">'+esc(l.title)+'<span class="fs">'+esc(l.source)+'</span></a>').join("");
    const fold=(t.folded_count>0&&flinks)?'<details class="fold"><summary><span>'+T.repMore.replace("{n}",t.folded_count)+'</span><span>›</span></summary><div class="fl">'+flinks+'</div></details>':"";
    const bar='<div class="hbar"><i style="width:'+Math.max(4,Math.round((t.heat||t.score)/maxHeat*100))+'%"></i></div>';
    return '<div class="hrow r'+(i+1)+'"><div class="hrank">'+(i+1)+'</div><div class="hmain"><div class="htitle"><a href="'+esc(rurl)+'" target="_blank" rel="noopener" data-read="'+esc(rurl)+'">'+esc(shownTitle)+'</a> '+flag+mflag+'</div>'
      +'<div class="hmeta"><span>'+esc(rep.source||((t.sources||[])[0]||""))+'</span><span>'+fmtRel(t.latest_at)+'</span><span>'+t.source_count+' '+T.sources+' · '+t.signal_count+' '+T.signals+'</span><span class="mono" style="font-weight:700;color:var(--acd)">'+Math.round(t.heat||t.score)+'</span></div>'
      +reason+(t.image?'<img class="himg" src="'+esc(t.image)+'" alt="" loading="lazy">':"")+(dg||(rsum?'<div class="isum">'+esc(rsum.length>200?rsum.slice(0,200)+"…":rsum)+'</div>':""))+hotExpand(t)+bar+'<div class="chips">'+chips+'</div>'+fold+'</div></div>';
  }).join("")+'</div>';
  $$("[data-hs]",root).forEach(b=>b.onclick=()=>{ state.hotSort=b.dataset.hs; contentReset("hot"); });
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
    side+='<div class="dday'+(x===d?" on":"")+'" data-d="'+x+'"><span>'+x+'</span><span>'+wdCN(x)+'</span></div>'; }
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
  $$(".dday", root).forEach(el=>el.onclick=()=>{ state.dailyDate=el.dataset.d; contentReset("daily"); });
  // 月份折叠只是收起归档列表，正文没换，位置必须保持——不能走 contentReset
  $$(".amonth", root).forEach(el=>el.onclick=()=>{ const m=el.dataset.m; col[m]=mOpen(m); renderDaily(); });
}
function renderTopics(){
  const root=$("#view-topics"); const rows=(C.daily&&C.daily.byCategory)||[];
  root.innerHTML='<div class="card ph"><h1>'+T.topics+'</h1><span class="sub">'+esc(chn()+T.topicsSub)+'</span></div><div class="tgrid">'+rows.map(r=>'<div class="tcard" data-cat="'+esc(r.category)+'"><div class="n">'+esc(catName(r.category))+'<span class="bdg b-cat">'+r.total+'</span></div><div class="nums"><span>24h <b>'+r.last24h+'</b></span><span>7d <b>'+r.last7d+'</b></span></div></div>').join("")+'</div>';
  $$(".tcard", root).forEach(el=>el.onclick=()=>{ state.cat=el.dataset.cat; state.allShown=ALL_PAGE; contentReset("all"); location.hash="#/all"; });
}
function renderTrends(){
  const root=$("#view-trends"); const tr=C.trends||{};
  const weekStart=tr.weekStart||"";
  const trendSub=(LANG==="en"?"This week vs last week":"本周 vs 上周")+(weekStart?(LANG==="en"?" · week starting ":" · 本周自")+fmtDay(weekStart)+(LANG==="en"?"":"起"):"");
  let html='<div class="card ph"><h1>'+esc(chn()+(LANG==="en"?" Trends":"趋势"))+'</h1><span class="sub">'+esc(trendSub)+'</span></div>';
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
  const rows=(dl.bySource||[]).map(s=>'<tr><td>'+esc(s.source)+'</td><td class="nw">'+s.count+'</td><td class="nw">'+fmtRel(s.latestAt)+'</td></tr>').join("");
  root.innerHTML='<div class="card ph"><h1>'+T.dataPage+'</h1><span class="sub">'+T.dataSub+'</span></div>'
    +'<div class="stats"><div class="stat"><div class="num">'+dl.total+'</div><div class="lbl">'+T.total+'</div></div><div class="stat"><div class="num">'+dl.last24h+'</div><div class="lbl">'+T.h24+'</div></div><div class="stat"><div class="num">'+dl.last7d+'</div><div class="lbl">'+T.h7+'</div></div><div class="stat"><div class="num">'+dl.topicCount+'</div><div class="lbl">'+T.hotTopic+'</div></div></div>'
    +'<div class="card" style="padding:16px 18px"><h3 style="font-size:14px;margin-bottom:6px">'+T.trend+'</h3>'+chart+'</div>'
    +'<div class="card" style="padding:16px 18px;margin-top:14px"><h3 style="font-size:14px;margin-bottom:6px">'+T.srcTable+'</h3><div class="tw"><table><thead><tr><th>'+T.srcTable+'</th><th class="nw">'+T.total+'</th><th class="nw">'+T.latest+'</th></tr></thead><tbody>'+rows+'</tbody></table></div></div>'
    +'<div class="dlrow"><a class="btn" href="data/'+CHID+'/report.csv" download>'+T.dlCSV+'</a><a class="btn" href="data/'+CHID+'/items.json" target="_blank">'+T.dlItems+'</a><a class="btn" href="data/'+CHID+'/hot-topics.json" target="_blank">'+T.dlHot+'</a><a class="btn" href="data/'+CHID+'/dailies.json" target="_blank">'+T.dlDaily+'</a></div>';
}
// ---- 本地数据备份（AIHOT：收藏与阅读设置只存本机，但要能导出/导回来）----
// 清浏览器数据 = 已读、收藏、主题、语言、频道全丢。导出是一个可读的 JSON
// 文件（用户自己能打开看），导入前解析校验，坏文件只提示不改现场。
const LS_KEYS = ["pat-read", "pat-fav", "pat-theme", "pat-lang", "pat-channel"];
function backupPayload(){
  const out = {app:"PAT-HOT", version:1, exportedAt:new Date().toISOString(), data:{}};
  LS_KEYS.forEach(function(k){
    try{ const v = localStorage.getItem(k); if(v !== null) out.data[k] = JSON.parse(v); }
    catch(e){ try{ const v = localStorage.getItem(k); if(v !== null) out.data[k] = v; }catch(e2){} }
  });
  return out;
}
function downloadBackup(){
  try{
    const blob = new Blob([JSON.stringify(backupPayload(), null, 2)], {type:"application/json"});
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "pat-hot-backup-" + new Date().toISOString().slice(0,10) + ".json";
    document.body.appendChild(a); a.click();
    setTimeout(function(){ URL.revokeObjectURL(a.href); a.remove(); }, 0);
  }catch(e){ alert(T.bakFail); }
}
function applyBackup(text){
  let o;
  try{ o = JSON.parse(text); }catch(e){ alert(T.badFile); return false; }
  if(!o || o.app !== "PAT-HOT" || typeof o.data !== "object"){ alert(T.badFile); return false; }
  let n = 0;
  Object.keys(o.data).forEach(function(k){
    if(LS_KEYS.indexOf(k) < 0) return;
    try{
      const v = o.data[k];
      localStorage.setItem(k, typeof v === "string" ? v : JSON.stringify(v)); n++;
    }catch(e){}
  });
  READ = lsGet("pat-read"); FAV = lsGet("pat-fav");
  try{ if(o.data["pat-theme"]) setTheme(o.data["pat-theme"]); }catch(e){}
  alert(T.bakDone.replace("{n}", n));
  // 语言/频道键也可能被导入改变，最干净的重建方式是整页刷新——localStorage 已落盘。
  // 绝不能用 File.remove() 之类碰用户的原始备份文件（那会删磁盘上的真文件）。
  location.reload();
  return true;
}
function pickBackupFile(){
  const inp = document.createElement("input");
  inp.type = "file"; inp.accept = ".json,application/json";
  inp.style.display = "none";
  inp.onchange = function(){
    const f = inp.files && inp.files[0];
    inp.remove();   // 只移除临时 <input> 元素，绝不碰用户磁盘上的备份文件
    if(!f) return;
    const rd = new FileReader();
    rd.onload = function(){ applyBackup(String(rd.result || "")); };
    rd.onerror = function(){ alert(T.bakFail); };
    rd.readAsText(f);
  };
  document.body.appendChild(inp);
  inp.click();
}
function renderFav(){
  const root=$("#view-fav");
  const its=C.items.filter(i=>FAV[i.url]).sort((a,b)=>b.score-a.score);
  const tools='<div class="card bakrow"><span class="sub">'+esc(T.bakNote)+'</span>'
    +'<span class="bakbtns"><button class="btn" id="bexport">'+T.bakExport+'</button>'
    +'<button class="btn" id="bimport">'+T.bakImport+'</button></span></div>';
  root.innerHTML='<div class="card ph"><h1>'+T.favPage+'</h1><span class="sub">'+esc(T.favSub)+'</span></div>'
    +tools
    +(its.length?its.map(itemCard).join(""):'<div class="card empty">'+T.noFav+'</div>');
  const be=$("#bexport"), bi=$("#bimport");
  if(be) be.onclick=downloadBackup;
  if(bi) bi.onclick=pickBackupFile;
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
    +'<div class="card" style="padding:16px 18px"><h3 style="font-size:15px;margin-bottom:4px">🤖 '+T.apiTitle+'</h3><p class="anote">'+T.apiDesc+'</p><p class="anote">'+T.base+'：<span class="mono">'+esc(base)+'</span></p><div class="tw wide"><table style="margin-top:10px"><thead><tr><th>'+T.endpoint+'</th><th>'+T.desc+'</th><th></th></tr></thead><tbody>'+rows+moreRows+'</tbody></table></div></div>'
    +'<div class="card" style="padding:16px 18px;margin-top:14px"><h3 style="font-size:15px;margin-bottom:4px">RSS</h3><div class="tw wide"><table style="margin-top:8px"><tbody>'+feedRows+'</tbody></table></div></div>'
    +'<div class="card" style="padding:16px 18px;margin-top:14px"><h3 style="font-size:15px;margin-bottom:4px">'+T.curl+'</h3><pre>'+esc(curl)+'</pre><p class="anote">'+T.llmsNote+'</p></div>';
}
function renderMore(){
  const root=$("#view-more");
  const nFav=Object.keys(FAV).filter(u=>C.items.some(i=>i.url===u)).length;
  const favSub=T.favCount.replace("{n}",nFav);
  const rows=[["#/all","allPage","menuAllSub","☰"],["#/fav","favPage",favSub,"★"],["#/topics","topics","menuTopicsSub","◈"],["#/data","data","menuDataSub","◉"],["#/agent","agent","menuAgentSub","🤖"]];
  root.innerHTML='<div class="card ph"><h1>'+T.more+'</h1></div><div class="card">'+rows.map(r=>'<a class="mrow" href="'+r[0]+'"><span style="font-size:18px">'+r[3]+'</span><span>'+T[r[1]]+'<small>'+(T[r[2]]||r[2])+'</small></span><span class="go">›</span></a>').join("")+'</div>';
}
function BRAND(){ return "PAT-HOT"; }
renderers.feed=renderFeed; renderers.all=renderAll; renderers.hot=renderHot; renderers.daily=renderDaily; renderers.topics=renderTopics; renderers.data=renderData; renderers.trends=renderTrends; renderers.fav=renderFav; renderers.agent=renderAgent; renderers.more=renderMore;
function bind(){
  const q=$("#q");
  let qTimer=null;
  // 搜索框此前只在 #/all 路由下有反应：在精选/热点/日报页打字看起来"没反应"。
  // 现在输入即时跳转全部页，回车也跳（窄屏键盘用户）。
  // 换查询词=结果集整体替换，落点必须回顶部（contentReset 同时清缓存位置）。
  const gotoAll=()=>{ state.allShown=ALL_PAGE; contentReset("all"); if(!/#\/all/.test(location.hash)) location.hash="#/all"; };
  q.addEventListener("input",e=>{ state.q=e.target.value; clearTimeout(qTimer); qTimer=setTimeout(gotoAll,250); });
  q.addEventListener("keydown",e=>{ if(e.key==="Enter"){ clearTimeout(qTimer); gotoAll(); } });
  $("#sbtn").onclick=()=>{ const w=$("#swrap"); w.classList.toggle("open"); if(w.classList.contains("open")) q.focus(); };
  $("#theme").onclick=()=>{ setTheme(themeNow()==="dark"?"light":"dark"); };
  $("#lang").onclick=()=>{ LANG=LANG==="zh"?"en":"zh"; try{localStorage.setItem("pat-lang",LANG);}catch(e){} location.reload(); };
  document.addEventListener("click",e=>{
    const f=e.target.closest("[data-fav]");
    if(f){ e.preventDefault(); toggleFav(f.dataset.fav); return; }   // 类名由 applyFavToDom 统一写，别在这里再翻一次
    const xf=e.target.closest("[data-x]");
    if(xf){ e.preventDefault(); toggleExpand(xf); return; }
    const dh=e.target.closest("[data-dayh]");
    if(dh){ const d=dh.dataset.dayh; state.collapsed[d]=!state.collapsed[d]; dh.closest(".day").classList.toggle("closed"); dh.querySelector(".arr").textContent=state.collapsed[d]?"▶":"▼"; return; }
    const r=e.target.closest("[data-read]");
    if(r){ markRead(r.dataset.read); }
  });
  window.addEventListener("hashchange",router);
  // 再点当前 tab 不会改 hash，也就不会触发 hashchange —— router 根本不会被调用。
  // 位置缓存必须配一个"回到顶部"的出口，否则用户只能手动往上滚。
  document.addEventListener("click",e=>{
    const a=e.target.closest('a[href^="#/"],a[href="#/"]');
    if(a && a.getAttribute("href")===location.hash) router();
  });
  document.addEventListener("keydown",e=>{ if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==="k"){ e.preventDefault(); $("#swrap").classList.add("open"); q.focus(); } });
  renderChSeg(); setTheme(themeNow()); tr(); router();
}
document.addEventListener("DOMContentLoaded", bind);
