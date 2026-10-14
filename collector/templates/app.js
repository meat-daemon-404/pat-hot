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
    calPage:"日历", calSub:"按北京日期归档 · 点某天跳回精选时间线", winVs:"近 {n} 天 vs 再前 {n} 天", backLatest:"回到最新",
    heatVal:"热度", sources:"信源", signals:"信号",
    mvNew:"新", mvRise:"升温", mvSurge:"多家跟进", mvDown:"回落",
    digestLabel:"事件概览 | ",
    repMore:"另有 {n} 家信源报道", repOne:"1 家信源报道",
    toc:"今日看点", archive:"日报归档",
    headlineK:"头 条", picksK:"今日看点", flashK:"快 讯", moreK:"分栏目浏览",
    topicsSub:"分类统计，点击进入筛选",
    dataPage:"数据", dataSub:"统计与导出", total:"收录总数", h24:"24 小时新增", h7:"7 天新增", hotTopic:"热点话题", trend:"每日收录趋势（近 14 天）",
    srcTable:"数据来源", latest:"最新收录", dlCSV:"下载 CSV", dlItems:"查看 items.json", dlHot:"查看 hot-topics.json", dlDaily:"查看 dailies.json",
    dlPapers:"论文编号锚点（DOI/arXiv，只收有编号的条目）",
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
    extNote:"原文·需外网", readOrig:"阅读原文 ↗（需外网）", importSM:"📥 导入学术星轨", smBind:"🔗 关联 ScholarMatrix", loadMore:"加载更多", aiGen:"生成中文摘要", aiLoading:"生成中…", aiFail:"生成失败，点击重试",
    smDeep:"🔬 在 ScholarMatrix 深读", smTip:"带论文编号跳 ScholarMatrix 建真文献",
    importTip:"存为资讯条目（该事件没有可复核的论文编号）",
    accountPage:"账号", accountSub:"登录后可绑定 ScholarMatrix：按你的研究兴趣重排、一键深读。",
    menuAccountSub:"注册 / 登录 · 绑定 ScholarMatrix · 清除我的数据",
    signIn:"登录", signUp:"注册", emailPh:"邮箱", passwordPh:"密码",
    accLoggedIn:"已登录", accNoEmail:"邮箱未返回", bindOk:"已关联 ScholarMatrix", accNoBind:"尚未关联 ScholarMatrix", accBindUnknown:"绑定状态未知（画像接口未返回）",
    accSnapYes:"画像快照：{n} 个主题词生效中", accSnapNo:"画像快照：无生效快照",
    viewTopics:"查看生效主题词", clearData:"清除我的数据", clearOk:"我的数据已清除", logout:"登出",
    bindWaiting:"正在关联 ScholarMatrix…", bindFail:"关联失败", bindHint:"检测到 ScholarMatrix 关联码：登录后自动完成关联。",
    needBoth:"邮箱和密码都要填", accWorking:"提交中…", probing:"正在检查登录状态…", netFail:"网络故障：请求没发出去或没回音（不是「暂无数据」）",
    rankPill:"按你的研究兴趣排序", rankView:"查看", rankClear:"清除", rankTerms:"生效主题词", rankCats:"关注分类", rankChs:"关注频道", rankNone:"快照没有主题词（仅按分类/频道命中）",
    // 页面外壳（head / 页头 / 页脚）：EN 下漏一处就是整页中英混排，所以一律进词典，
    // 由 tr() 在启动时统一落盘，而不是散在模板里。
    genAt:"生成于 {t} · 北京时间", pageTitle:"PAT-HOT · 物理·天文·光电热点",
    pageDesc:"PAT-HOT：物理 / 天文 / 光电三频道资讯热点统计。自动采集公开信源，去重聚类打分，每天 6:00 与 18:00（北京时间）更新，单文件可离线打开，并提供免鉴权 JSON API。",
    ogTitle:"PAT-HOT · 物理·天文·光电热点统计", ogDesc:"三频道资讯热点榜、日报与趋势，AIHOT 方法论，开源可离线。",
    channelAria:"频道", themeTitle:"主题 / Theme", langTitle:"语言 / Language", llmsEntry:"LLM 友好入口",
    aiScore:"AI 双打分均值",
    colon:"：",
    footer:"PAT-HOT · 物理·天文·光电热点统计（AIHOT 方法论）· 数据来自公开网络，仅供参考，不构成投资建议 · GitHub 开源" },
  en: { feed:"Selected", all:"All", hot:"Hot", daily:"Daily", trends:"Trends", more:"More",
    allPage:"All Items", hotPage:"Hot Ranking", topics:"Topics", data:"Data", agent:"Agent API",
    search:"Search", catAll:"All", sortScore:"By score", sortTime:"By time",
    thresholdNote:"Selection bar: official sources ≥ {o} · media sources ≥ {m} (tune in collector/config.json)",
    hotNow:"Trending Now", fullRank:"Full ranking →", unreadOnly:"Unread only", sciOnly:"Research only", today:"Today", daySel:"selected", noMatch:"No matching items",
    calPage:"Calendar", calSub:"Archived by Beijing date — tap a day to jump to the timeline", winVs:"Last {n}d vs previous {n}d", backLatest:"Back to latest",
    heatVal:"heat", sources:"sources", signals:"signals",
    mvNew:"new", mvRise:"rising", mvSurge:"surge", mvDown:"cooling",
    digestLabel:"In brief | ",
    repMore:"{n} more sources", repOne:"1 source",
    toc:"Today's picks", archive:"Archive",
    headlineK:"HEADLINE", picksK:"Today's picks", flashK:"Flash", moreK:"Browse by category",
    topicsSub:"Category stats — click to filter",
    dataPage:"Data", dataSub:"Stats & export", total:"Total items", h24:"24h new", h7:"7d new", hotTopic:"Hot topics", trend:"Daily trend (14 days)",
    srcTable:"Sources", latest:"Latest", dlCSV:"Download CSV", dlItems:"items.json", dlHot:"hot-topics.json", dlDaily:"dailies.json",
    dlPapers:"Paper identifier anchors (DOI/arXiv; only entries that have one)",
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
    extNote:"orig.·needs internet", readOrig:"Read original ↗ (needs internet)", importSM:"📥 Import to ScholarMatrix", smBind:"🔗 Link ScholarMatrix", loadMore:"Load more", aiGen:"Generate Chinese summary", aiLoading:"Generating…", aiFail:"Failed, tap to retry",
    smDeep:"🔬 Open in ScholarMatrix", smTip:"Carries the paper identifier so ScholarMatrix creates a real entry",
    importTip:"Saved as a news item (this event has no verifiable paper identifier)",
    accountPage:"Account", accountSub:"Sign in to link ScholarMatrix: rank by your research interests, one-click deep read.",
    menuAccountSub:"Sign up / log in · link ScholarMatrix · erase my data",
    signIn:"Log in", signUp:"Sign up", emailPh:"Email", passwordPh:"Password",
    accLoggedIn:"Signed in", accNoEmail:"email not returned", bindOk:"Linked to ScholarMatrix", accNoBind:"Not linked to ScholarMatrix yet", accBindUnknown:"Link status unknown (profile API did not answer)",
    accSnapYes:"Profile snapshot: {n} topic terms in effect", accSnapNo:"Profile snapshot: no active snapshot",
    viewTopics:"View topic terms", clearData:"Erase my data", clearOk:"My data has been erased", logout:"Log out",
    bindWaiting:"Linking to ScholarMatrix…", bindFail:"Link failed", bindHint:"ScholarMatrix link code detected: it will be redeemed once you sign in.",
    needBoth:"Email and password are both required", accWorking:"Working…", probing:"Checking sign-in state…", netFail:"Network failure: the request never got an answer (this is not \"no data\")",
    rankPill:"Ranked by your research interests", rankView:"view", rankClear:"clear", rankTerms:"Active topic terms", rankCats:"Followed categories", rankChs:"Followed channels", rankNone:"Snapshot has no topic terms (matched on category / channel only)",
    genAt:"Generated {t} · Beijing time", pageTitle:"PAT-HOT · physics / astronomy / photonics",
    pageDesc:"PAT-HOT: hot-topic stats across three channels — physics / astronomy / photonics. Public sources are collected, deduped, clustered and scored; refreshed at 6:00 and 18:00 Beijing time; one offline-capable file with a keyless JSON API.",
    ogTitle:"PAT-HOT · physics / astronomy / photonics hot-topic stats", ogDesc:"Hot rankings, daily digests and trends across three channels — AIHOT methodology, open source, offline-capable.",
    channelAria:"Channel", themeTitle:"Theme / 主题", langTitle:"Language / 语言", llmsEntry:"LLM-friendly entry point",
    aiScore:"AI double-score mean",
    colon:": ",
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
  // 最新文章时间必须按北京时间显示：published_at 是 UTC 瞬时，直接切片会把
  // 北京 10-13 早上的文章写成「10-12 23:20 发布」，和「数据 今天 更新」自相矛盾。
  let latTxt=""; if(latest){ const lb=new Date(new Date(latest).getTime()+8*3600*1000);
    const lp=lb.toISOString().slice(0,10);
    const hm=String(lb.getUTCHours()).padStart(2,"0")+":"+String(lb.getUTCMinutes()).padStart(2,"0");
    latTxt=(lp===todayCN()?(LANG==="en"?"today ":"今天 "):fmtDay(lp)+" ")+hm; }
  if(LANG==="en") return "📡 Data updated "+genTxt+" · Newest article "+latTxt;
  return "📡 数据 "+genTxt+" 更新 · 最新文章 "+latTxt+" 发布";
}
function hotPage(){ return chn()+(LANG==="en"?" Hot Ranking":"热点榜"); }
function hotSub(){ return LANG==="en" ? "Event-level heat: each independent source counts once per 48h" : "事件级热度：48 小时内每独立来源只计一次"; }
function dailyPage(){ return chn()+(LANG==="en"?" Daily":"日报"); }
function dailySub(){ return LANG==="en" ? "Auto-generated per collection day (with archive)" : "按采集日自动生成（含历史归档）"; }
function searchPh(){ return T.search+chn()+(LANG==="en"?" news…":"资讯 / 关键词…"); }
const state = { q:"", cat:"全部", sort:"score", dailyDate:"", hotSort:"heat", unreadOnly:false, calMonth:"", feedDay:"", calJumpDay:"" };
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
// 页面外壳本地化：<html lang>、标签页标题、meta、频道 aria、按钮 title、页脚生成时间。
// 这些文案不在 data-i18n 上（在 <head> 里或属性上），所以 tr() 得单独收口——
// 漏掉任何一处，EN 页面就会在标签页/无障碍标签/页脚里混出中文。
function tr(){
  $$("[data-i18n]").forEach(el=>{ const k=el.dataset.i18n; if(T[k]) el.textContent = T[k]; });
  $("#lang").textContent = LANG==="zh"?"EN":"中";
  $("#q").placeholder = searchPh();
  document.documentElement.lang = LANG==="en"?"en":"zh-CN";
  document.title = T.pageTitle;
  const md=document.querySelector('meta[name="description"]'); if(md) md.content = T.pageDesc;
  const ogt=document.querySelector('meta[property="og:title"]'); if(ogt) ogt.content = T.ogTitle;
  const ogd=document.querySelector('meta[property="og:description"]'); if(ogd) ogd.content = T.ogDesc;
  const cs=$("#chseg"); if(cs) cs.setAttribute("aria-label", T.channelAria);
  const thb=$("#theme"); if(thb) thb.title = T.themeTitle;
  const lgb=$("#lang"); if(lgb) lgb.title = T.langTitle;
  const g=$(".gen"); if(g) g.textContent = T.genAt.replace("{t}", g.dataset.gen||"");
}
// 相对时间：EN 下此前恒返回「刚刚 / N 分钟前」，卡片元信息行与数据页都在漏中文。
function fmtRel(iso){ if(!iso) return ""; const t=new Date(iso); const d=(Date.now()-t.getTime())/1000;
  if(LANG==="en"){
    if(d<60) return "just now"; if(d<3600) return Math.floor(d/60)+" min ago";
    if(d<86400) return Math.floor(d/3600)+" h ago"; return Math.floor(d/86400)+" d ago"; }
  if(d<60) return "刚刚"; if(d<3600) return Math.floor(d/60)+" 分钟前"; if(d<86400) return Math.floor(d/3600)+" 小时前"; return Math.floor(d/86400)+" 天前"; }
// 条目的「北京日期」：published_at 是 UTC 瞬时，直接切前 10 位会把北京凌晨的
// 文章归到前一天（27/86 条错位），页面上也永远出不来「今天」这一组。
// 月级/日级精度没有时刻可换算，原样保留。
function cnDayOf(p){ if(!p||p.length<19) return p?p.slice(0,10):""; const d=new Date(p); if(isNaN(d.getTime())) return p.slice(0,10); return new Date(d.getTime()+8*3600*1000).toISOString().slice(0,10); }
function effDate(it){ const p=it.published_at; if(p&&p.length>=10) return cnDayOf(p); const d=new Date(it.discovered_at); return new Date(d.getTime()+8*3600*1000).toISOString().slice(0,10); }
function fmtDay(dstr){ const parts=dstr.split("-"); if(LANG==="en") return dstr; return parts[0]+"年"+Number(parts[1])+"月"+Number(parts[2])+"日"; }
function wdCN(dstr){ const d=new Date(dstr+"T00:00:00+08:00").getDay(); return LANG==="en"?["Sun","Mon","Tue","Wed","Thu","Fri","Sat"][d]:["周日","周一","周二","周三","周四","周五","周六"][d]; }
function todayCN(){ return new Date(Date.now()+8*3600*1000).toISOString().slice(0,10); }
// 北京日期串平移 n 天（日历/趋势窗口回推用）；非法输入原样返回。
function shiftDay(dstr,n){ const d=new Date(dstr+"T00:00:00+08:00"); if(isNaN(d.getTime())) return dstr; return new Date(d.getTime()+n*86400*1000).toISOString().slice(0,10); }
function isToday(d){ return d===todayCN(); }
function scoreCls(s){ return s>=75?"s-hi":(s>=50?"s-mid":"s-lo"); }
// 发布/收录标签：EN 下同样必须换词，否则卡片元信息行半中半英。
// 时刻按北京时间显示（与分组日期同源），UTC 原样切片会让卡片时间比真实晚 8 小时。
function pubLabel(it){
  if(it.published_at){ const p=it.published_at;
    if(p.length===7) return LANG==="en" ? p+" (monthly)" : p+"（月级）发布";
    if(p.length===10) return LANG==="en" ? "published "+p : p+" 发布";
    const b=new Date(p); const ok=!isNaN(b.getTime());
    const bb=ok?new Date(b.getTime()+8*3600*1000):null;
    const stamp=bb?bb.toISOString().slice(5,16).replace("T"," "):p.replace("T"," ").slice(5,16);
    return LANG==="en" ? "published "+stamp : stamp+" 发布"; }
  return LANG==="en" ? "added "+fmtRel(it.discovered_at) : "收录 "+fmtRel(it.discovered_at); }
function catName(c){ return LANG==="en" ? (CAT_EN[c]||c) : c; }
function statusName(s){ return LANG==="en" ? (STATUS_EN[s]||s) : s; }
function densName(d){ return LANG==="en" ? (DENS_EN[d]||d) : d; }
function catBadge(c){ return '<span class="bdg b-cat">'+esc(catName(c))+'</span>'; }
function pickBadge(){ return '<span class="bdg b-pick">'+T.pick+'</span>'; }
function tierBadge(t){ return t==="official"?'<span class="bdg b-tier">'+T.official+'</span>':""; }
function densBadge(d){ if(!d) return ""; const cls=d==="高"?"b-dh":(d==="中"?"b-dm":"b-dl"); return '<span class="bdg '+cls+'" title="'+T.density+'">'+esc(densName(d))+'</span>'; }
function scoreEl(s,llm){ const ai=llm?'<span class="iai">AI</span>':""; return '<span class="iscore mono '+scoreCls(s)+'" title="'+(llm?T.aiScore:"score")+' / 100">'+Math.round(s)+'</span>'+ai; }
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
// 无锚条目降级为资讯条目（契约 §4：不发假论文链接，也不假装它是论文）。
// 两类描述符共用 smOutHref 这一条拼串路径：多出第二条路＝多一条没过门的出链。
function smNewsDesc(it){ if(!it.url) return "";
  const d={ title:String(it.title||"").slice(0,300), url:it.url, abstract:it.zh_full||it.llm_summary||it.summary||"", journal:it.source||"", kind:"news" };
  if(!d.title&&!d.url) return "";
  return JSON.stringify([d]);
}
function smOutHref(it){ const j=smDesc(it)||smNewsDesc(it); if(!j) return ""; return SM_BASE+"?add="+b64url(j); }
// 出链按钮。图标只写在词典值里（见 smDeep / importSM 两键），函数体里一个图标字符都不许
// 出现——在这里再拼一次就是线上实测到的图标重复缺陷（两个下载箭头并排）。
// test_button_icon_lives_in_dict 钉住这条不变量。
function smDeepBtn(it){ const h=smOutHref(it); if(!h) return "";
  const paper=!!smDesc(it); // 有 verified 锚＝深读建真文献，否则＝存一条资讯
  return '<div class="ism"><a class="smbtn" href="'+esc(h)+'" target="_blank" rel="noopener" title="'+esc(paper?T.smTip:T.importTip)+'">'+esc(paper?T.smDeep:T.importSM)+'</a></div>'; }
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
// 导入学术星轨的出链不在这里：统一走 smOutHref（见文件上方受门控的单一路径）。
function expandBody(it){ if(!expandable(it)) return ""; const open=EXPANDED.has(it.id);
  const zf=it.zh_full?'<div class="xsec">'+T.aiSum+'</div><div class="xt">'+esc(it.zh_full)+'</div>':"";
  const ai=!it.zh_full&&it.llm_summary?'<div class="xsec">'+T.aiSum+'</div><div class="xt">'+esc(it.llm_summary)+'</div>':"";
  const rs=it.summary?'<div class="xsec">'+T.srcSum+'</div><div class="xt">'+esc(it.summary)+'</div>':"";
  const src=it.url?'<div class="xsrc"><a href="'+esc(it.url)+'" target="_blank" rel="noopener">'+T.readOrig+'</a></div>':"";
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
  state.dailyDate=""; state.cat="全部"; state.q=""; state.allShown=ALL_PAGE; state.feedDay=""; state.calMonth=""; const q=$("#q"); if(q) q.value="";
  // 换频道等于换了全部数据，九个常驻视图的缓存一起作废
  invalidateAll();
  try{ localStorage.setItem("pat-channel",id); }catch(e){}
  renderChSeg(); tr(); router(); }
function itemCard(it){
  const rd=READ[it.url]?" read":"", fv=FAV[it.url]?" on":"";
  const src=it.source||"", av=esc((src.trim().charAt(0)||chn()).charAt(0));
  const s=(it.llm_score!=null?it.llm_score:it.score);
  const reason=it.llm_reason?'<div class="ireason"><b>'+T.reason+T.colon+'</b>'+esc(it.llm_reason)+'</div>':"";
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
  const map={"/":"feed","/all":"all","/hot":"hot","/daily":"daily","/cal":"cal","/topics":"topics","/trends":"trends","/data":"data","/fav":"fav","/agent":"agent","/more":"more","/account":"account"};
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
    // 文字与链接必须同源：后端已把 t.title 定为代表报道的标题（finalize_topic），
    // 所以链接直接取 representative.url；有事件综述时显示综述标题，链接仍是该事件
    // 的代表报道。旧实现文字用 max(score) 那条、链接用 representative，文不对题。
    const shown=t.digestTitle||t.title;
    const rurl=esc((t.representative||{}).url||"#/hot");
    return '<div class="hr3"><span class="rk r'+(i+1)+'">'+(i+1)+'</span><span class="ht"><a href="'+rurl+'" target="_blank" rel="noopener">'+esc(shown)+'</a></span><span class="hn mono">'+Math.round(t.heat||t.score)+' <small>'+T.heatVal+'</small> '+arrow+'</span></div>'; }).join("")+'</div>';
  // 精选页只放过了门槛的条目：旧实现不过滤 selected，「精选」页内容等于全部动态，
  // 没过门槛的诺奖稿（62.8 分 < 媒体门槛 65）也顶着「精选」标题出现。
  let items=C.items.filter(i=>i.selected);
  if(state.unreadOnly) items=items.filter(i=>!READ[i.url]);
  items=sciFilter(items);
  const groups={}; for(const it of items){ const d=effDate(it); (groups[d]=groups[d]||[]).push(it); }
  const days=Object.keys(groups).sort().reverse();
  const win=state.feedDay?days.filter(d=>d<=state.feedDay).slice(0,7):days.slice(0,7);
  let tl='<div class="urow">'+(state.feedDay?'<button class="upill on" id="backLatest"><span class="dot"></span>'+T.backLatest+'</button>':"")+'<button class="upill'+(state.unreadOnly?" on":"")+'" id="unreadBtn"><span class="dot"></span>'+T.unreadOnly+'</button><button class="upill'+(sciOnly()?" on":"")+'" id="sciBtn"><span class="dot"></span>🔬 '+T.sciOnly+'</button><a class="upill" href="#/cal" id="calBtn">📅 '+T.calPage+'</a></div>';
  if(!win.length) tl+='<div class="empty">'+T.noMatch+'</div>';
  // 组不再折叠（折叠交互已移到独立日历页 #/cal）：组头只作日期分隔与计数。
  // 计数 = 该天真实精选条数，不再用渲染条数（旧实现 slice(0,20) 后写 its.length，
  // 34 条精选的一天显示「20 条精选」，0 条精选的一天也显示「20 条精选」）。
  // 组内排序用 rankKey（W2 画像重排）：绑定快照生效后按兴趣重排，未登录恒等原分数序。
  for(const d of win){ const its=groups[d].slice().sort((a,b)=>rankKey(b)-rankKey(a));
    tl+='<div class="day" id="day-'+d+'"><div class="day-h"><h2>'+(isToday(d)?T.today+" ":"")+fmtDay(d)+'</h2><span class="w">'+wdCN(d)+'</span><span class="c">'+its.length+' '+T.daySel+'</span></div><div class="day-b">'+its.map(itemCard).join("")+'</div></div>'; }
  root.innerHTML=rankPillHtml()+'<div class="card ph"><h1>'+T.feed+'</h1><span class="sub">'+esc(feedSub())+'</span><div class="note">'+esc(freshNote())+'</div><div class="note">'+esc(threshNote())+'</div></div>'+hot+tl;
  const ub=$("#unreadBtn"); if(ub) ub.onclick=()=>{ state.unreadOnly=!state.unreadOnly; contentReset("feed"); };
  const sb=$("#sciBtn"); if(sb) sb.onclick=sciToggle;
  const bl=$("#backLatest"); if(bl) bl.onclick=()=>{ state.feedDay=""; contentReset("feed"); };
  bindRankClear();
  // 日历页跳过来的落点在这里做：此刻分组刚画进 DOM，router 之后不会再
  // scrollTo（RENDERED 已置位），顺序是确定的。block:"start" 会把组头
  // 顶到视口 0 处、压在吸顶 header 下，所以按 header 实测高度留白。
  if(state.calJumpDay){
    const day=state.calJumpDay; state.calJumpDay="";
    requestAnimationFrame(()=>{
      const g=document.getElementById("day-"+day); if(!g) return;
      const hd=document.querySelector(".top");
      const off=hd?Math.ceil(hd.getBoundingClientRect().height):0;
      window.scrollTo(0, Math.max(0, g.getBoundingClientRect().top+window.scrollY-off-2));
    });
  }
}
// ---- 日历页：精选时间线的日期导航（替代旧的内联折叠）----
// 只列真有精选条目的日期（北京日），点某天跳回精选页并滚到该天分组。
function calDays(){
  const groups={}; for(const it of C.items){ if(!it.selected) continue; const d=effDate(it); (groups[d]=groups[d]||[]).push(it); }
  return groups;
}
function renderCal(){
  const root=$("#view-cal"); const groups=calDays();
  const days=Object.keys(groups).sort().reverse();
  const cur=state.calMonth||(days[0]||todayCN()).slice(0,7);
  state.calMonth=cur;
  const months=[...new Set(days.map(d=>d.slice(0,7)))].sort().reverse();
  const mi=months.indexOf(cur);
  const byDay={}; days.forEach(d=>{ byDay[d]=groups[d].length; });
  // 月历格子：周一开头，七天一行；有精选的日期可点，其余置灰。
  const first=new Date(cur+"-01T00:00:00+08:00");
  const lead=(first.getDay()+6)%7;
  const dim=new Date(Date.UTC(+cur.slice(0,4), +cur.slice(5,7), 1)).getUTCDate();
  let cells="";
  for(let i=0;i<lead;i++) cells+='<span class="cal-c off"></span>';
  for(let dd=1;dd<=dim;dd++){
    const key=cur+"-"+String(dd).padStart(2,"0");
    const n=byDay[key]||0;
    cells+='<a class="cal-c'+(n?"":" off")+(key===todayCN()?" today":"")+'"'+(n?' href="#/" data-calday="'+key+'"':'')+'><span class="cal-d">'+dd+'</span>'+(n?'<span class="cal-n">'+n+'</span>':"")+'</a>';
  }
  // 星期表头随语言切换：格子只有 ~35px 宽，英文用两字母（M/S 会撞车）。
  const wk=(LANG==="en"?["Mo","Tu","We","Th","Fr","Sa","Su"]:["一","二","三","四","五","六","日"])
    .map(t=>'<span class="cal-w">'+t+'</span>').join("");
  const grid='<div class="cal-grid">'+wk+cells+'</div>';
  const nav='<div class="cal-nav"><button class="upill" id="calPrev"'+(mi<=0?" disabled":"")+'>‹</button><span class="cal-m">'+cur+'</span><button class="upill" id="calNext"'+(mi<0||mi>=months.length-1?" disabled":"")+'>›</button></div>';
  const list='<div class="cal-list">'+days.slice(0,14).map(d=>'<a class="cal-row" href="#/" data-calday="'+d+'"><span>'+fmtDay(d)+'</span><span class="w">'+wdCN(d)+'</span><span class="c">'+byDay[d]+' '+T.daySel+'</span></a>').join("")+'</div>';
  root.innerHTML='<div class="card ph"><h1>'+T.calPage+'</h1><span class="sub">'+esc(T.calSub)+'</span></div><div class="card" style="padding:14px 16px">'+nav+grid+'</div><div class="card" style="padding:6px 16px 12px"><h3 style="font-size:13px;color:var(--ink3);margin:8px 0 4px">'+T.archive+'</h3>'+list+'</div>';
  const pv=$("#calPrev"), nx=$("#calNext");
  if(pv) pv.onclick=()=>{ state.calMonth=months[mi-1]; contentReset("cal"); };
  if(nx) nx.onclick=()=>{ state.calMonth=months[mi+1]; contentReset("cal"); };
}
// ---- 日历页：精选时间线的日期导航（替代旧的内联折叠）----
// 只列真有精选条目的日期（北京日），点某天跳回精选页并滚到该天分组。
function calDays(){
  const groups={}; for(const it of C.items){ if(!it.selected) continue; const d=effDate(it); (groups[d]=groups[d]||[]).push(it); }
  return groups;
}
function renderCal(){
  const root=$("#view-cal"); const groups=calDays();
  const days=Object.keys(groups).sort().reverse();
  const cur=state.calMonth||(days[0]||todayCN()).slice(0,7);
  state.calMonth=cur;
  const months=[...new Set(days.map(d=>d.slice(0,7)))].sort().reverse();
  const mi=months.indexOf(cur);
  const byDay={}; days.forEach(d=>{ byDay[d]=groups[d].length; });
  // 月历格子：周一开头，七天一行；有精选的日期可点，其余置灰。
  const first=new Date(cur+"-01T00:00:00+08:00");
  const lead=(first.getDay()+6)%7;
  const dim=new Date(Date.UTC(+cur.slice(0,4), +cur.slice(5,7), 1)).getUTCDate();
  let cells="";
  for(let i=0;i<lead;i++) cells+='<span class="cal-c off"></span>';
  for(let dd=1;dd<=dim;dd++){
    const key=cur+"-"+String(dd).padStart(2,"0");
    const n=byDay[key]||0;
    cells+='<a class="cal-c'+(n?"":" off")+(key===todayCN()?" today":"")+'"'+(n?' href="#/" data-calday="'+key+'"':'')+'><span class="cal-d">'+dd+'</span>'+(n?'<span class="cal-n">'+n+'</span>':"")+'</a>';
  }
  const grid='<div class="cal-grid"><span class="cal-w">一</span><span class="cal-w">二</span><span class="cal-w">三</span><span class="cal-w">四</span><span class="cal-w">五</span><span class="cal-w">六</span><span class="cal-w">日</span>'+cells+'</div>';
  const nav='<div class="cal-nav"><button class="upill" id="calPrev"'+(mi<=0?" disabled":"")+'>‹</button><span class="cal-m">'+cur+'</span><button class="upill" id="calNext"'+(mi<0||mi>=months.length-1?" disabled":"")+'>›</button></div>';
  const list='<div class="cal-list">'+days.slice(0,14).map(d=>'<a class="cal-row" href="#/" data-calday="'+d+'"><span>'+fmtDay(d)+'</span><span class="w">'+wdCN(d)+'</span><span class="c">'+byDay[d]+' '+T.daySel+'</span></a>').join("")+'</div>';
  root.innerHTML='<div class="card ph"><h1>'+T.calPage+'</h1><span class="sub">'+esc(T.calSub)+'</span></div><div class="card" style="padding:14px 16px">'+nav+grid+'</div><div class="card" style="padding:6px 16px 12px"><h3 style="font-size:13px;color:var(--ink3);margin:8px 0 4px">'+T.archive+'</h3>'+list+'</div>';
  const pv=$("#calPrev"), nx=$("#calNext");
  if(pv) pv.onclick=()=>{ state.calMonth=months[mi-1]; contentReset("cal"); };
  if(nx) nx.onclick=()=>{ state.calMonth=months[mi+1]; contentReset("cal"); };
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
  // 只重排、绝不改写：无快照不重排（上游原序＝今天的序）；有快照按
  // heat×(1+命中权重和) 重排。排名序号 i+1 跟着新序走，热度徽标数字不动。
  else if(PROFILE.snap) ts.sort((a,b)=>topicKey(b)-topicKey(a));
  const maxHeat=Math.max(...ts.map(t=>t.heat||t.score||0),1);
  const head='<div class="card ph"><h1>'+esc(hotPage())+'</h1><span class="sub">'+esc(hotSub())+'</span><span class="hsort"><button data-hs="heat" class="'+(state.hotSort==="heat"?"on":"")+'">'+T.heatVal+'</button><button data-hs="sources" class="'+(state.hotSort==="sources"?"on":"")+'">'+T.sources+'</button></span></div>';
  root.innerHTML=rankPillHtml()+head+'<div class="card">'+ts.map((t,i)=>{
    const s=t.status; const flag=s==="爆"?'<span class="flag f-hot">'+statusName(s)+'</span>':(s==="发酵中"?'<span class="flag f-warm">'+statusName(s)+'</span>':'<span class="flag f-watch">'+statusName(s)+'</span>');
    const mflag=movementFlag(t);
    const rep=t.representative||{}; const rurl=rep.url||((t.links||[])[0]||{}).url||"";
    const reason=rep.llm_reason?'<div class="ireason"><b>'+T.reason+T.colon+'</b>'+esc(rep.llm_reason)+'</div>':"";
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
  bindRankClear();
}
function dailyArticle(a){
  const reason=a.reason?'<div class="ireason"><b>'+T.reason+T.colon+'</b>'+esc(a.reason)+'</div>':"";
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
    // rep.label / rep.weekday 是采集端写死的中文（"2026年10月13日" / "周二"），
    // EN 下必须由前端按 date 重排，否则日报页标题永远是中文。
    const dLabel=LANG==="en" ? (rep.date||"") : (rep.label||rep.date||"");
    const dWeek=LANG==="en" ? (rep.date?wdCN(rep.date):"") : (rep.weekday||(rep.date?wdCN(rep.date):""));
    body+='<div class="deye">'+BRAND()+' DAILY · '+esc(chn().toUpperCase())+'</div><div class="dtitle">'+esc(dLabel)+' · '+esc(dWeek)+'</div>';
    const hl=rep.headline||(((rep.sections||[])[0]||{}).articles||[])[0];
    if(hl){ body+='<div class="hero"><div class="k">'+T.headlineK+'</div><div class="t"><a href="'+esc(hl.url)+'" target="_blank" rel="noopener" data-read="'+esc(hl.url)+'">'+esc(hl.title)+'</a></div><div class="m"><span>'+esc(hl.source)+'</span><span>'+esc(pubLabel(hl))+'</span>'+densBadge(hl.density)+'</div>'+(hl.image?'<img class="himg" src="'+esc(hl.image)+'" alt="" loading="lazy">':"")+(hl.reason?'<div class="ireason"><b>'+T.reason+T.colon+'</b>'+esc(hl.reason)+'</div>':"")+(hl.summary?'<div class="isum">'+esc(hl.summary)+'</div>':"")+'</div>'; }
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
  // 滚动窗口文案：旧文案「本周 vs 上周 · 本周自 X 起」在周二时拿 2 天对 7 天，
  // 百分比全是半截周的假象。新数据带 windowDays/windowStart/windowEnd；
  // 旧产物没有这些字段时按今天回推，保证文案与数据口径一致而不是谎称自然周。
  const win=tr.windowDays||7;
  const we=tr.windowEnd||todayCN();
  const ws=tr.windowStart||shiftDay(we,-(win-1));
  let trendSub=T.winVs.replace(/\{n\}/g,String(win));
  const hasRange=we&&we!==ws;
  trendSub+=LANG==="en" ? " · "+ws+(hasRange?" → "+we:"") : " · "+ws+(hasRange?" 至 "+we:" 起");
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
  const eps=[["items",T.dlItems],["hot-topics",T.dlHot],["dailies",T.dlDaily],["daily","daily.json"],["stories","stories.json"],["trends","trends.json"],["papers-index",T.dlPapers]];
  const rows=eps.map(([k,d])=>'<tr><td class="mono">api/v1/'+CHID+'/'+k+'.json</td><td>'+d+'</td><td><a href="'+base+'api/v1/'+CHID+'/'+k+'.json" target="_blank" rel="noopener">'+T.open+' ↗</a></td></tr>').join("");
  const curl=eps.map(([k])=>'curl '+base+'api/v1/'+CHID+'/'+k+'.json').join("\n");
  const catFeeds=Object.entries(CAT_CLS).map(([cat,slug])=>["feed/"+CHID+"/category/"+slug+".xml",cat]);
  const feedRows=['<tr><td class="mono">feed.xml</td><td>'+(LANG==="en"?"RSS (main feed, T photonics)":"RSS（T 光电主 feed）")+'</td><td><a href="'+base+'feed.xml" target="_blank" rel="noopener">'+T.open+' ↗</a></td></tr>']
    .concat(catFeeds.map(([f,cat])=>'<tr><td class="mono">'+f+'</td><td>'+esc(catName(cat))+'</td><td><a href="'+base+f+'" target="_blank" rel="noopener">'+T.open+' ↗</a></td></tr>')).join("");
  const moreRows='<tr><td class="mono">api/v1/openapi.json</td><td>OpenAPI 3.1</td><td><a href="'+base+'api/v1/openapi.json" target="_blank" rel="noopener">'+T.open+' ↗</a></td></tr><tr><td class="mono">llms.txt</td><td>'+T.llmsEntry+'</td><td><a href="'+base+'llms.txt" target="_blank" rel="noopener">'+T.open+' ↗</a></td></tr>';
  root.innerHTML='<div class="card ph"><h1>'+T.agentPage+'</h1><span class="sub">'+T.agentSub+'</span></div>'
    +'<div class="card" style="padding:16px 18px"><h3 style="font-size:15px;margin-bottom:4px">🤖 '+T.apiTitle+'</h3><p class="anote">'+T.apiDesc+'</p><p class="anote">'+T.base+T.colon+'<span class="mono">'+esc(base)+'</span></p><div class="tw wide"><table style="margin-top:10px"><thead><tr><th>'+T.endpoint+'</th><th>'+T.desc+'</th><th></th></tr></thead><tbody>'+rows+moreRows+'</tbody></table></div></div>'
    +'<div class="card" style="padding:16px 18px;margin-top:14px"><h3 style="font-size:15px;margin-bottom:4px">RSS</h3><div class="tw wide"><table style="margin-top:8px"><tbody>'+feedRows+'</tbody></table></div></div>'
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
renderers.feed=renderFeed; renderers.all=renderAll; renderers.hot=renderHot; renderers.daily=renderDaily; renderers.cal=renderCal; renderers.topics=renderTopics; renderers.data=renderData; renderers.trends=renderTrends; renderers.fav=renderFav; renderers.agent=renderAgent; renderers.more=renderMore; renderers.account=renderAccount;
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
    // 日历页点某天：跳回精选页、把窗口锚到该天并滚到对应分组。
    // 旧的"点组头折叠"已删除——录屏（2026-10-13）里折叠会把下方内容整体顶走
    // （单帧 +31px / +164px 的跳位），用户明确要"单独做一个界面，以日历形式，点击跳转"。
    const cd=e.target.closest("[data-calday]");
    if(cd){ e.preventDefault(); state.feedDay=cd.dataset.calday; state.unreadOnly=false;
      // 跳转的滚动不能在这里做：hashchange→router 重画精选是异步任务，
      // rAF 可能跑在它前面（目标分组还不存在），也可能跑在它后面被
      // router 的 scrollTo(0,0) 顶掉（320px 实测 y 停在 0）。把落点交给
      // renderFeed：DOM 画好后自己排帧，顺序才确定。
      state.calJumpDay=cd.dataset.calday;
      location.hash="#/"; contentReset("feed");
      return; }
    const r=e.target.closest("[data-read]");
    if(r){ markRead(r.dataset.read); }
  });
  window.addEventListener("hashchange",router);
  // 再点当前 tab 不会改 hash，也就不会触发 hashchange —— router 根本不会被调用。
  // 位置缓存必须配一个"回到顶部"的出口，否则用户只能手动往上滚。
  document.addEventListener("click",e=>{
    // 日历格子是 a[href="#/"]：data-calday 处理器已 preventDefault 并同步
    // 改好 hash，这里若再按"再点当前 tab"走一遍，dispatch 中 router 会被
    // 多调一次，随后 hashchange 判成 retap 归零，把 renderFeed 排好的
    // 落点顶回 0（trace 实测 scrollTo(507) 之后紧跟 scrollTo(0,0)）。
    // 被拦截的点击不再二次处理。
    if(e.defaultPrevented) return;
    const a=e.target.closest('a[href^="#/"],a[href="#/"]');
    if(a && a.getAttribute("href")===location.hash) router();
  });
  document.addEventListener("keydown",e=>{ if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==="k"){ e.preventDefault(); $("#swrap").classList.add("open"); q.focus(); } });
  renderChSeg(); setTheme(themeNow()); tr(); router();
  maybeProbe();   // 兴趣重排的探测启动点：门在函数体内（localStorage ph_logged_in=1 才发请求）
}
document.addEventListener("DOMContentLoaded", bind);
