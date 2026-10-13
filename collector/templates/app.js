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
    favPage:"收藏", favSub:"点过的星标都在这里（只存在本浏览器）", noFav:"还没有收藏：点卡片右上角的 ★ 收藏一条", favCount:"{n} 条收藏",
    extNote:"原文·需外网", readOrig:"阅读原文 ↗（需外网）", loadMore:"加载更多", aiGen:"生成中文摘要", aiLoading:"生成中…", aiFail:"生成失败，点击重试",
    smDeep:"在 ScholarMatrix 深读", smTip:"带论文编号跳 ScholarMatrix 建真文献",
    accountPage:"账号", accountSub:"登录后可绑定 ScholarMatrix：按你的研究兴趣重排、一键深读。",
    menuAccountSub:"注册 / 登录 · 绑定 ScholarMatrix · 清除我的数据",
    signIn:"登录", signUp:"注册", emailPh:"邮箱", passwordPh:"密码",
    accLoggedIn:"已登录", accNoEmail:"邮箱未返回", bindOk:"已关联 ScholarMatrix", accNoBind:"尚未关联 ScholarMatrix", accBindUnknown:"绑定状态未知（画像接口未返回）",
    accSnapYes:"画像快照：{n} 个主题词生效中", accSnapNo:"画像快照：无生效快照",
    viewTopics:"查看生效主题词", clearData:"清除我的数据", clearOk:"我的数据已清除", logout:"登出",
    bindWaiting:"正在关联 ScholarMatrix…", bindFail:"关联失败", bindHint:"检测到 ScholarMatrix 关联码：登录后自动完成关联。",
    needBoth:"邮箱和密码都要填", accWorking:"提交中…", probing:"正在检查登录状态…", netFail:"网络故障：请求没发出去或没回音（不是「暂无数据」）",
    rankPill:"按你的研究兴趣排序", rankView:"查看", rankClear:"清除", rankTerms:"生效主题词", rankCats:"关注分类", rankChs:"关注频道", rankNone:"快照没有主题词（仅按分类/频道命中）",
    footer:"PAT-HOT · 物理·天文·光电热点统计（AIHOT 方法论）· 数据来自公开网络，仅供参考，不构成投资建议 · GitHub 开源" },
  en: { feed:"Selected", all:"All", hot:"Hot", daily:"Daily", trends:"Trends", more:"More",
    allPage:"All Items", hotPage:"Hot Ranking", topics:"Topics", data:"Data", agent:"Agent API",
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
    favPage:"Saved", favSub:"Your stars live in this browser only", noFav:"Nothing saved yet — tap ★ on a card to save it", favCount:"{n} saved",
    extNote:"orig.·needs internet", readOrig:"Read original ↗ (needs internet)", loadMore:"Load more", aiGen:"Generate Chinese summary", aiLoading:"Generating…", aiFail:"Failed, tap to retry",
    smDeep:"Open in ScholarMatrix", smTip:"Carries the paper identifier so ScholarMatrix creates a real entry",
    accountPage:"Account", accountSub:"Sign in to link ScholarMatrix: rank by your research interests, one-click deep read.",
    menuAccountSub:"Sign up / log in · link ScholarMatrix · erase my data",
    signIn:"Log in", signUp:"Sign up", emailPh:"Email", passwordPh:"Password",
    accLoggedIn:"Signed in", accNoEmail:"email not returned", bindOk:"Linked to ScholarMatrix", accNoBind:"Not linked to ScholarMatrix yet", accBindUnknown:"Link status unknown (profile API did not answer)",
    accSnapYes:"Profile snapshot: {n} topic terms in effect", accSnapNo:"Profile snapshot: no active snapshot",
    viewTopics:"View topic terms", clearData:"Erase my data", clearOk:"My data has been erased", logout:"Log out",
    bindWaiting:"Linking to ScholarMatrix…", bindFail:"Link failed", bindHint:"ScholarMatrix link code detected: it will be redeemed once you sign in.",
    needBoth:"Email and password are both required", accWorking:"Working…", probing:"Checking sign-in state…", netFail:"Network failure: the request never got an answer (this is not \"no data\")",
    rankPill:"Ranked by your research interests", rankView:"view", rankClear:"clear", rankTerms:"Active topic terms", rankCats:"Followed categories", rankChs:"Followed channels", rankNone:"Snapshot has no topic terms (matched on category / channel only)",
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
// ---- ScholarMatrix 出站深链（契约 §5；W2 前端半最重要的一笔）----
// 只有条目 refs 里带 verified 的 doi/arxiv 才给出链；无锚点＝不放按钮，宁缺毋假。
// b64url 与 SM 侧 frontend/src/lib/patJourney.js 的 b64url 严格同形
// （btoa(unescape(encodeURIComponent(s))) 再 +→- /→_ 去尾 =），descriptor 键序也照
// 它那边 title/kind/source→doi/arxiv/url 的插入序构造，同输入两端逐字节互译。
function b64url(s){ const b=btoa(unescape(encodeURIComponent(String(s)))); return b.replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/,""); }
const SM_BASE="https://scholarmatrix.pages.dev/";
function smDesc(it){
  const r=it?it.refs:null;
  if(!r||!(r.doi||r.arxiv)) return "";   // 门：refs 且 (doi || arxiv)
  if(r.confidence!=="verified") return ""; // suspect 不是深读入口（契约 §0：只有 verified 建真论文）
  const d={title:String(it.title||"").slice(0,300),kind:"paper",source:"pat-hot"};
  if(r.doi) d.doi=r.doi; if(r.arxiv) d.arxiv=r.arxiv; if(it.url) d.url=it.url;
  if(!d.title&&!d.doi&&!d.arxiv) return "";
  return JSON.stringify([d]);
}
function smOutHref(it){ const j=smDesc(it); if(!j) return ""; return SM_BASE+"?add="+b64url(j); }
function smDeepBtn(it){ const h=smOutHref(it); if(!h) return "";
  return '<div class="ism"><a class="smbtn" href="'+esc(h)+'" target="_blank" rel="noopener" title="'+esc(T.smTip)+'">🔬 '+esc(T.smDeep)+'</a></div>'; }
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
  +reason+ev+ents+(sum?'<div class="isum">'+esc(sum)+'</div>':"")+smDeepBtn(it)+expandBtn(it)+expandBody(it)+'</article>';
}
function threshNote(){ const th=C.thresholds||{official:55,media:65}; return T.thresholdNote.replace("{o}",th.official).replace("{m}",th.media); }
const renderers = {};
let LAST_VIEW = "";
function setNav(v){ $$("#tabbar a").forEach(a=>a.classList.toggle("on",a.dataset.v===v)); $$("#dnav a").forEach(a=>a.classList.toggle("on",a.dataset.v===v)); $$(".seg a").forEach(a=>a.classList.toggle("on",a.dataset.seg===v)); }
function router(){ const h=(location.hash||"#/").replace("#",""); const name=h.split("?")[0]||"/"; const map={"/":"feed","/all":"all","/hot":"hot","/daily":"daily","/topics":"topics","/trends":"trends","/data":"data","/fav":"fav","/agent":"agent","/more":"more","/account":"account"}; const v=map[name]||"feed"; if(v==="all"&&LAST_VIEW!=="all") state.allShown=ALL_PAGE; LAST_VIEW=v; setNav(v); $$(".view").forEach(x=>x.classList.remove("on")); $("#view-"+v).classList.add("on"); (renderers[v]||renderers.feed)(); window.scrollTo(0,0); }
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
  for(const d of days){ const its=groups[d].slice().sort((a,b)=>rankKey(b)-rankKey(a)).slice(0,20);
    const closed=state.collapsed[d]?" closed":"";
    tl+='<div class="day'+closed+'"><div class="day-h" data-dayh="'+d+'"><h2>'+(isToday(d)?T.today+" ":"")+fmtDay(d)+'</h2><span class="w">'+wdCN(d)+'</span><span class="c">'+its.length+' '+T.daySel+'</span><span class="arr">'+(state.collapsed[d]?"▶":"▼")+'</span></div><div class="day-b">'+its.map(itemCard).join("")+'</div></div>'; }
  root.innerHTML=rankPillHtml()+'<div class="card ph"><h1>'+T.feed+'</h1><span class="sub">'+esc(feedSub())+'</span><div class="note">'+esc(threshNote())+'</div></div>'+hot+tl;
  const ub=$("#unreadBtn"); if(ub) ub.onclick=()=>{ state.unreadOnly=!state.unreadOnly; renderFeed(); };
  bindRankClear();
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
  // 只重排、绝不改写：无快照不重排（上游原序＝今天的序）；有快照按
  // heat×(1+命中权重和) 重排。排名序号 i+1 跟着新序走，热度徽标数字不动。
  else if(PROFILE.snap) ts.sort((a,b)=>topicKey(b)-topicKey(a));
  const maxHeat=Math.max(...ts.map(t=>t.heat||t.score||0),1);
  const head='<div class="card ph"><h1>'+esc(hotPage())+'</h1><span class="sub">'+esc(hotSub())+'</span><span class="hsort"><button data-hs="heat" class="'+(state.hotSort==="heat"?"on":"")+'">'+T.heatVal+'</button><button data-hs="sources" class="'+(state.hotSort==="sources"?"on":"")+'">'+T.sources+'</button></span></div>';
  root.innerHTML=rankPillHtml()+head+'<div class="card">'+ts.map((t,i)=>{
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
  bindRankClear();
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
function renderFav(){
  const root=$("#view-fav");
  const its=C.items.filter(i=>FAV[i.url]).sort((a,b)=>b.score-a.score);
  root.innerHTML='<div class="card ph"><h1>'+T.favPage+'</h1><span class="sub">'+esc(T.favSub)+'</span></div>'
    +(its.length?its.map(itemCard).join(""):'<div class="card empty">'+T.noFav+'</div>');
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
  const nFav=Object.keys(FAV).filter(u=>C.items.some(i=>i.url===u)).length;
  const favSub=T.favCount.replace("{n}",nFav);
  const rows=[["#/all","allPage","menuAllSub","☰"],["#/fav","favPage",favSub,"★"],["#/topics","topics","menuTopicsSub","◈"],["#/data","data","menuDataSub","◉"],["#/agent","agent","menuAgentSub","🤖"],["#/account","accountPage","menuAccountSub","◑"]];
  root.innerHTML='<div class="card ph"><h1>'+T.more+'</h1></div><div class="card">'+rows.map(r=>'<a class="mrow" href="'+r[0]+'"><span style="font-size:18px">'+r[3]+'</span><span>'+T[r[1]]+'<small>'+(T[r[2]]||r[2])+'</small></span><span class="go">›</span></a>').join("")+'</div>';
}
// ============================================================================
// ---- 账号面板 + ScholarMatrix 绑定 + 兴趣重排（W2 前端半，契约 §1/§2/§3）----
// 纪律：
// · 探测只以 localStorage 的 ph_logged_in==="1" 为门 —— fork 的静态用户零额外
//   请求，开源面（未登录路径）与今天逐字节一致。
// · 失败要说真原因（契约 §0）：网络故障 / 未登录 / 存储关闭，各报各的，
//   服务端回的 error+机器码原样展示，绝不笼统「操作失败」。
// · 重排只改顺序：score_final = score × (1 + Σ 命中权重) 只进比较器，
//   分数徽标 scoreEl / 标题 / 摘要的渲染行一字不动。
//   主题命中用快照 topics 的 weight；分类/频道命中没有随行权重，
//   用常量 CAT_HIT_W / CH_HIT_W（契约 §3 未给数值，取保守 0.2，见回报偏差项）。
// ============================================================================
const PH_LOGIN_KEY="ph_logged_in";       // 探测门标记：登录成功置 "1"，登出清除
const CAT_HIT_W=0.2, CH_HIT_W=0.2;       // 分类/频道命中的固定权重（快照未携带时的口径）
const PROFILE={probed:false,known:false,logged:false,email:"",bound:false,snap:null,topics:[],cats:[],chs:[],expires:"",apiMsg:""};
const ACC={busy:false,msg:"",msgKind:"",bindTried:""};
function setLoggedIn(v){ try{ if(v) localStorage.setItem(PH_LOGIN_KEY,"1"); else localStorage.removeItem(PH_LOGIN_KEY); }catch(e){} }
async function apiCall(method,url,body){
  try{
    const r=await fetch(url,{method,credentials:"include",headers:body?{"Content-Type":"application/json"}:{},body:body?JSON.stringify(body):undefined});
    const t=await r.text(); let j=null; try{ j=t?JSON.parse(t):null; }catch(e){}
    return {status:r.status,ok:r.ok,json:j,text:t};
  }catch(e){ return {status:0,ok:false,json:null,text:"",err:String((e&&e.message)||e)}; }
}
// 真原因 + 机器码：HTTP 0=网络层失败（请求根本没走完）；其余取 body 的
// error/reason/message 原文，机器码取 code/machine 键——两端排查都靠它。
function realError(res,fallback){
  if(!res) return fallback;
  if(res.status===0) return T.netFail+(res.err?" · "+res.err:"");
  const j=res.json||{};
  const why=j.error||j.reason||j.message||fallback;
  const code=j.code||j.machine||j.err_code||"";
  return why+(code?"（"+code+"）":"")+" · HTTP "+res.status;
}
function normalizeSnap(p){
  const s=(p&&(p.snapshot||p.profile))||p||{};
  const topics=(s.topics||[]).map(x=>typeof x==="string"?{t:String(x).toLowerCase(),w:0.2}:{t:String((x&&x.term)||"").toLowerCase(),w:Number(x&&x.weight)||0}).filter(x=>x.t);
  return {topics:topics,
    cats:(s.categories||[]).map(x=>String(x).toLowerCase()),
    chs:(s.channels||[]).map(String),
    expires:String(s.expiresAt||""),
    has:topics.length||(s.categories||[]).length||(s.channels||[]).length};
}
async function fetchProfile(){
  const res=await apiCall("GET","/api/profile");
  if(res.status===0){ PROFILE.apiMsg=T.netFail; PROFILE.snap=null; return; }
  if(!res.ok){ PROFILE.apiMsg=realError(res,"/api/profile"); PROFILE.snap=null; PROFILE.bound=false; return; }
  const p=res.json||{}; PROFILE.apiMsg="";
  PROFILE.bound=typeof p.bound==="boolean"?p.bound:!!(p.smSubject||(p.snapshot||p.profile||{}).smSubject);
  const s=normalizeSnap(p);
  const alive=!s.expires||new Date(s.expires).getTime()>Date.now();
  PROFILE.topics=s.topics; PROFILE.cats=s.cats; PROFILE.chs=s.chs; PROFILE.expires=s.expires;
  PROFILE.snap=(s.has&&alive)?s:null;
  if(PROFILE.snap&&(LAST_VIEW==="feed"||LAST_VIEW==="hot")) rerankCurrentView();
}
async function probeAccount(){
  // 探测门（双重）：localStorage 的 ph_logged_in 必须是 "1"，本函数体自己也要再查一遍——
  // fork 的静态用户零额外请求，未登录路径与今天逐字节一致。
  let mark=""; try{ mark=localStorage.getItem(PH_LOGIN_KEY)||""; }catch(e){}
  if(mark!=="1"){ PROFILE.probed=true; PROFILE.known=true; PROFILE.logged=false; return; }
  const me=await apiCall("GET","/api/account/me");
  PROFILE.probed=true;
  if(me.status===0){ PROFILE.known=false; PROFILE.logged=true; PROFILE.apiMsg=T.netFail; return; } // 会话未知：说网络故障，不装未登录
  if(me.ok){ PROFILE.known=true; PROFILE.logged=true;
    const j=me.json||{}; PROFILE.email=j.email||(j.user&&j.user.email)||(j.account&&j.account.email)||"";
    await fetchProfile();
  } else if(me.status===401||me.status===403){ PROFILE.known=true; PROFILE.logged=false; setLoggedIn(false); }
  else { PROFILE.known=false; PROFILE.logged=true; PROFILE.apiMsg=realError(me,"/api/account/me"); }
}
function bindCodeFromHash(){ const m=String(location.hash||"").match(/[?&]bind=([^&]+)/); return m?decodeURIComponent(m[1]):""; }
async function redeemBind(force){
  const code=bindCodeFromHash();
  if(!code||!PROFILE.logged) return;
  if(!force&&ACC.bindTried===code) return;   // 一次性码：同一页面会话只兑一次，第二次必 410
  ACC.bindTried=code; ACC.busy=true; ACC.msg=T.bindWaiting; ACC.msgKind="wait";
  if(LAST_VIEW==="account") renderAccount();
  const res=await apiCall("POST","/api/bind/verify",{code:code});
  ACC.busy=false;
  if(res.ok&&res.json&&res.json.ok===true){
    ACC.msg=T.bindOk; ACC.msgKind="ok";
    try{ history.replaceState(null,"",location.pathname+"#/account"); }catch(e){} // 一次性码：兑成功即从 URL 摘掉，刷新不再重兑
    await fetchProfile();
  }
  // 失败：bindTried 保留本码，页面存活期间不再自动重兑（一次性码第二次必 410；
  // 网络故障时用户刷新或重进链接自然重试）。展示服务端回的真原因+机器码。
  else { ACC.msg=realError(res,T.bindFail); ACC.msgKind="fail"; }
  if(LAST_VIEW==="account") renderAccount();
}
async function accSubmit(kind,btn){
  const root=btn.closest(".aform"); if(!root||ACC.busy) return;
  const email=(root.querySelector("[data-acc=email]").value||"").trim();
  const password=root.querySelector("[data-acc=password]").value||"";
  if(!email||!password){ ACC.msg=T.needBoth; ACC.msgKind="fail"; renderAccount(); return; }
  ACC.busy=true; ACC.msg=T.accWorking; ACC.msgKind="wait"; renderAccount();
  const res=await apiCall("POST","/api/account/"+kind,{email:email,password:password});
  ACC.busy=false;
  if(res.ok&&(!res.json||res.json.ok!==false)){
    setLoggedIn(true); PROFILE.probed=true; PROFILE.known=true; PROFILE.logged=true; PROFILE.email=email; ACC.msg=""; ACC.msgKind="";
    await fetchProfile(); await redeemBind(false);
  } else { ACC.msg=realError(res,T[kind==="login"?"signIn":"signUp"]); ACC.msgKind="fail"; }
  renderAccount();
}
async function accClearData(btn){
  if(ACC.busy) return; ACC.busy=true; ACC.msg=T.accWorking; ACC.msgKind="wait"; renderAccount();
  const res=await apiCall("DELETE","/api/profile-snapshot");
  ACC.busy=false;
  if(res.ok&&(!res.json||res.json.ok!==false)){ PROFILE.snap=null; PROFILE.topics=[]; PROFILE.cats=[]; PROFILE.chs=[];
    // 清除快照 ≠ 解绑（契约 §1.2）：绑定状态留给服务端口径，这里不列假状态。
    ACC.msg=T.clearOk; ACC.msgKind="ok"; if(LAST_VIEW==="feed"||LAST_VIEW==="hot") rerankCurrentView(); }
  else { ACC.msg=realError(res,T.clearData); ACC.msgKind="fail"; }
  renderAccount();
}
async function accLogout(){
  await apiCall("POST","/api/account/logout");
  setLoggedIn(false);
  PROFILE.known=true; PROFILE.logged=false; PROFILE.email=""; PROFILE.bound=false;
  PROFILE.snap=null; PROFILE.topics=[]; PROFILE.cats=[]; PROFILE.chs=[]; PROFILE.apiMsg="";
  if(LAST_VIEW==="feed"||LAST_VIEW==="hot") rerankCurrentView();
  renderAccount();
}
// ---- 命中与重排（只进比较器，不动任何显示值）----
function hitWeight(kws,cat,chan){
  const s=PROFILE.snap; if(!s) return 0;
  let sum=0; const hitTopic=new Set();
  for(const kw of kws||[]){
    const k=String(kw).toLowerCase(); if(!k) continue;
    s.topics.forEach((tp,ti)=>{
      if(hitTopic.has(ti)) return;
      const exact=(k===tp.t);
      const contain=(k.length>=4||tp.t.length>=4)&&(k.indexOf(tp.t)>=0||tp.t.indexOf(k)>=0);
      if(exact||contain){ hitTopic.add(ti); sum+=tp.w; }
    });
  }
  if(cat&&s.cats.indexOf(String(cat).toLowerCase())>=0) sum+=CAT_HIT_W;
  if(chan&&s.chs.indexOf(String(chan))>=0) sum+=CH_HIT_W;
  return sum;
}
function rankKey(it){ return ((it.score)||0)*(1+hitWeight(it.keywords,it.category,CHID)); }
function topicKey(t){ return ((t.heat||t.score)||0)*(1+hitWeight((t.top_terms||[]).concat(t.terms||[]),t.category,CHID)); }
function rerankCurrentView(){ if(LAST_VIEW==="feed") renderFeed(); else if(LAST_VIEW==="hot") renderHot(); }
function rankPillHtml(){
  if(!PROFILE.snap) return "";
  // 胶囊在 feed/hot 两个常驻 section 各渲染一份，清除钮按类取（id 会撞）。
  return '<div class="rankpill card"><span class="rp-t">◆ '+esc(T.rankPill)+'</span>'
    +'<a class="rp-a" href="#/account">'+esc(T.rankView)+'</a>'
    +'<button class="rp-b">'+esc(T.rankClear)+'</button></div>';
}
function bindRankClear(){ $$(".rankpill .rp-b").forEach(b=>{ b.onclick=()=>accClearData(b); }); }
// ---- 账号视图 #/account ----
let PROBE_SENT=false;
function maybeProbe(){
  // 探测门（唯一入口）：localStorage 的 ph_logged_in 标记不在，一个请求都不发。
  // fork 的静态用户、以及从没登录过的访客，网络面与今天逐字节一致。
  if(PROBE_SENT||PROFILE.probed) return;
  let mark=""; try{ mark=localStorage.getItem(PH_LOGIN_KEY)||""; }catch(e){}
  if(mark!=="1"){ PROFILE.probed=true; PROFILE.known=true; PROFILE.logged=false; return; }
  PROBE_SENT=true;
  probeAccount().then(()=>{ if(LAST_VIEW==="account") renderAccount(); });
}
function renderAccount(){
  const root=$("#view-account"); if(!root) return;
  maybeProbe();
  let html='<div class="card ph"><h1>'+esc(T.accountPage)+'</h1><span class="sub">'+esc(T.accountSub)+'</span></div>';
  if(bindCodeFromHash()&&!PROFILE.logged) html+='<div class="card abind">'+esc(T.bindHint)+'</div>';
  if(ACC.msg) html+='<div class="card amsg a-'+ACC.msgKind+'">'+esc(ACC.msg)+'</div>';
  if(PROFILE.apiMsg&&!ACC.msg) html+='<div class="card amsg a-fail">'+esc(PROFILE.apiMsg)+'</div>';
  if(!PROFILE.probed){ html+='<div class="card amsg a-wait">'+esc(T.probing)+'</div>'; root.innerHTML=html; return; }
  if(PROFILE.logged){
    html+='<div class="card ainfo"><div class="ai-row"><b>'+esc(T.accLoggedIn)+'</b><span class="mono">'+esc(PROFILE.email||T.accNoEmail)+'</span></div>'
      +'<div class="ai-row">'+esc(PROFILE.bound?T.bindOk:(PROFILE.apiMsg?T.accBindUnknown:T.accNoBind))+'</div>'
      +'<div class="ai-row">'+esc(PROFILE.snap?T.accSnapYes.replace("{n}",PROFILE.snap.topics.length):T.accSnapNo)+'</div>';
    if(PROFILE.snap){
      const terms=PROFILE.snap.topics.map(x=>'<span class="chip term">'+esc(x.t)+' · '+x.w+'</span>').join("");
      const cats=PROFILE.snap.cats.map(x=>'<span class="chip">'+esc(x)+'</span>').join("");
      const chs=PROFILE.snap.chs.map(x=>'<span class="chip">'+esc(x)+'</span>').join("");
      html+='<details class="fold"><summary><span>'+esc(T.viewTopics)+'</span><span>›</span></summary><div class="fl aterms">'
        +(terms?'<div class="xsec">'+esc(T.rankTerms)+'</div><div class="chips">'+terms+'</div>':'<div class="anote">'+esc(T.rankNone)+'</div>')
        +(cats?'<div class="xsec">'+esc(T.rankCats)+'</div><div class="chips">'+cats+'</div>':"")
        +(chs?'<div class="xsec">'+esc(T.rankChs)+'</div><div class="chips">'+chs+'</div>':"")
        +'</div></details>';
    }
    html+='<div class="dlrow"><button class="btn" id="acc-clear">'+esc(T.clearData)+'</button><button class="btn" id="acc-logout">'+esc(T.logout)+'</button></div></div>';
  } else {
    const form=(kind)=>'<form class="aform" data-form="'+kind+'"><div class="arow"><input data-acc=email type="email" autocomplete="email" placeholder="'+esc(T.emailPh)+'"><input data-acc=password type="password" autocomplete="'+(kind==="login"?"current-password":"new-password")+'" placeholder="'+esc(T.passwordPh)+'"></div><button class="btn a-go" type="submit">'+esc(T[kind==="login"?"signIn":"signUp"])+'</button></form>';
    html+='<div class="card abody">'+form("register")+'<div class="asplit"></div>'+form("login")+'</div>';
  }
  root.innerHTML=html;
  $$(".aform",root).forEach(f=>f.onsubmit=e=>{ e.preventDefault(); accSubmit(f.dataset.form,e.submitter||f.querySelector(".a-go")); });
  const cb=$("#acc-clear",root); if(cb) cb.onclick=accClearData;
  const lb=$("#acc-logout",root); if(lb) lb.onclick=accLogout;
  if(bindCodeFromHash()&&PROFILE.logged&&ACC.bindTried!==bindCodeFromHash()) redeemBind(false);
}
function BRAND(){ return "PAT-HOT"; }
renderers.feed=renderFeed; renderers.all=renderAll; renderers.hot=renderHot; renderers.daily=renderDaily; renderers.topics=renderTopics; renderers.data=renderData; renderers.trends=renderTrends; renderers.fav=renderFav; renderers.agent=renderAgent; renderers.more=renderMore; renderers.account=renderAccount;
function bind(){
  const q=$("#q");
  let qTimer=null;
  // 搜索框此前只在 #/all 路由下有反应：在精选/热点/日报页打字看起来"没反应"。
  // 现在输入即时跳转全部页，回车也跳（窄屏键盘用户）。
  const gotoAll=()=>{ state.allShown=ALL_PAGE; if(/#\/all/.test(location.hash)) renderAll(); else location.hash="#/all"; };
  q.addEventListener("input",e=>{ state.q=e.target.value; clearTimeout(qTimer); qTimer=setTimeout(gotoAll,250); });
  q.addEventListener("keydown",e=>{ if(e.key==="Enter"){ clearTimeout(qTimer); gotoAll(); } });
  $("#sbtn").onclick=()=>{ const w=$("#swrap"); w.classList.toggle("open"); if(w.classList.contains("open")) q.focus(); };
  $("#theme").onclick=()=>{ setTheme(themeNow()==="dark"?"light":"dark"); };
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
  renderChSeg(); setTheme(themeNow()); tr(); router();
  maybeProbe();   // 兴趣重排的探测启动点：门在函数体内（localStorage ph_logged_in=1 才发请求）
}
document.addEventListener("DOMContentLoaded", bind);
