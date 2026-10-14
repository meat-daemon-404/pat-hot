/**
 * 画像重排（线路契约 §3）：score_final = score × (1 + Σ 命中权重)。
 *
 * 纯函数、无 DOM、无 fetch。它是**双端共用**的实现：
 *  - 前端 collector/templates/app.js 把 rankItems/finalScore 同口径复刻进渲染路径；
 *  - `node --test tests/js` 直接 import 本文件断言行为；
 *  - tests/test_identity.py 再把本文件与 app.js 里内联的那段做逐字骨架对拍，
 *    防止"后端测绿了、前端排序却是另一套"。
 *
 * 🔴 红线：只产出顺序，绝不接触 title / summary / 分数徽标（分数是对外承诺
 * 的可复现口径，改显示值等于篡改承诺）。
 * 命中判定三项：keywords（token 级包含，不做 fuzzy）、category、channel。
 */

function normTerm(s) {
  return String(s == null ? "" : s).toLowerCase().trim();
}

function tokenize(s) {
  return s.split(/[^a-z0-9\u4e00-\u9fff]+/).filter(Boolean);
}

/**
 * token 级包含匹配（明确不是 fuzzy）：
 *  - 完全相等 → 命中；
 *  - 一侧的某个 token（长度 ≥4）整 token 出现在另一侧的 token 序列里 → 命中。
 * 例：term "quantum error correction" 命中 keyword "quantum"？——不命中，
 * 那是 keyword 侧的短 token "quantum"(7≥4) 出现在 term 里，反向成立：
 * keyword 是 term 的整 token 子串算命中，所以 "quantum" 作为 keyword 会命中。
 * 整 token 约束防 "co" 命中 "cooling" 这类子串误伤；≥4 下限防 "nano"/"spin"
 * 之类短词反向铺满全场。
 */
export function termMatchesTopic(term, keyword) {
  const a = normTerm(term), b = normTerm(keyword);
  if (!a || !b) return false;
  if (a === b) return true;
  const at = tokenize(a), bt = tokenize(b);
  const hit = (needles, hay) => needles.some((n) => n.length >= 4 && hay.indexOf(n) >= 0);
  if (hit(at, bt)) return true;
  return hit(bt, at);
}

/**
 * @param item 条目或热点 topic（keywords/top_terms/category/channel 缺省宽容）
 * @param snapshot 校验过的画像快照（validateSnapshotPayload 的 value 形状）
 * @returns {{boost:number, hits:Array<{term:string,weight:number,why:string}>}}
 */
export function scoreBoost(item, snapshot) {
  if (!item || !snapshot || !Array.isArray(snapshot.topics)) return { boost: 0, hits: [] };
  const pool = (Array.isArray(item.keywords) ? item.keywords : [])
    .concat(Array.isArray(item.top_terms) ? item.top_terms : []);
  let boost = 0;
  const hits = [];
  for (const t of snapshot.topics) {
    if (!t || typeof t.term !== "string") continue;
    const w = typeof t.weight === "number" && Number.isFinite(t.weight) ? Math.min(Math.max(t.weight, 0), 1) : 0;
    if (w <= 0) continue;
    let why = "";
    if (pool.some((k) => termMatchesTopic(t.term, k))) why = "keywords";
    else if (normTerm(item.category) && normTerm(t.term) === normTerm(item.category)) why = "category";
    else if (normTerm(item.channel) && normTerm(t.term) === normTerm(item.channel)) why = "channel";
    if (!why) continue;
    boost += w;
    hits.push({ term: t.term, weight: w, why });
  }
  return { boost, hits };
}

/** 条目的"原分数"：与卡片徽标显示口径一致（llm_score 优先），重排不改它。 */
export function baseScoreOf(item) {
  if (!item) return 0;
  const s = typeof item.llm_score === "number" ? item.llm_score
    : (typeof item.score === "number" ? item.score : (typeof item.heat === "number" ? item.heat : 0));
  return Number.isFinite(s) ? s : 0;
}

export function finalScore(item, snapshot) {
  return baseScoreOf(item) * (1 + scoreBoost(item, snapshot).boost);
}

/**
 * 稳定重排：按 score_final 降序，同分退回原下标 → 同输入同输出。
 * snapshot 无效（未登录 / 未绑定 / 无快照 / topics 为空）时返回原序副本，
 * 这是"未登录路径零行为变化"的实现层保证。
 */
export function rankItems(items, snapshot) {
  const list = Array.isArray(items) ? items : [];
  if (!snapshot || !Array.isArray(snapshot.topics) || snapshot.topics.length === 0) {
    return list.slice();
  }
  return list
    .map((it, i) => ({ it, i, f: finalScore(it, snapshot) }))
    .sort((a, b) => (b.f - a.f) || (a.i - b.i))
    .map((x) => x.it);
}

/** 快照是否仍在生效期（expiresAt 未到）。 */
export function snapshotActive(snapshot, nowMs = Date.now()) {
  if (!snapshot || !snapshot.expiresAt) return false;
  const t = Date.parse(snapshot.expiresAt);
  return Number.isFinite(t) && t > nowMs;
}
