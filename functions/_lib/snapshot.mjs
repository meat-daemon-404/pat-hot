/**
 * 画像快照校验器（线路契约 §2 的代码化）。纯函数，无 env、无 D1：
 * Pages Function 与 `node --test tests/js` 跑的是**这同一份实现**。
 *
 * 闭集策略：顶层只允许契约 §2 的 10 个键，topics 项只允许 term/weight，
 * 其余键一律拒收——"多一个键"正是阅读历史混进来的通道。
 *
 * 🔴 禁存面两道闸：
 *  1) 键名黑名单：title/doi/arxiv/abstract/url 这类键出现在**任意深度**都
 *     整条拒收 400 FIELD_FORBIDDEN。先跑它再跑未知键检查，否则带 title 的
 *     载荷会拿到 FIELD_UNKNOWN——把"我们在挡阅读历史"的真实原因藏掉了。
 *  2) 值形状：term 里出现 URL / DOI / 裸 arXiv 编号形状同样 FIELD_FORBIDDEN。
 *     键名改成 "t" 也绕不过第二道。
 * 文档里的禁存面只是承诺，这里才是执行。
 */

export const SNAPSHOT_V = 1;
export const TOPIC_TERM_MAX = 80;
export const TOPICS_MAX = 64;
export const CATEGORIES_MAX = 32;
export const CHANNELS_MAX = 8;
export const COUNTS_KEYS_MAX = 12;
export const SNAPSHOT_TTL_MAX_MS = 31 * 24 * 3600 * 1000; // 契约：expiresAt ≤ pushed + 31d

/** 分类白名单：collector/channels.json 三频道 categories 的并集（24 项）。
 *  tests/test_identity.py 逐字对拍：改 channels.json 不加这里会被测红。 */
export const CATEGORY_WHITELIST = [
  "产业与资本", "光伏与新能源", "光传感与激光雷达", "光学元件与成像", "光电芯片与半导体",
  "光通信", "其他", "凝聚态物理", "原子分子与光物理", "太阳与空间物理", "引力波",
  "恒星与星际介质", "星系与宇宙学", "显示与面板", "深空探测", "激光", "生物物理",
  "科研进展", "等离子体", "系外行星", "统计物理与软物质", "通信与算力",
  "量子信息与计算", "高能与粒子物理",
];

/** 频道白名单：collector/channels.json 的 order。 */
export const CHANNEL_WHITELIST = ["physics", "astro", "tech"];

export const LANG_WHITELIST = ["zh", "en"];

const TOP_KEYS = new Set([
  "v", "smSubject", "phSubject", "pushedAt", "expiresAt", "topics", "categories", "channels", "lang", "counts",
]);
const TOPIC_KEYS = new Set(["term", "weight"]);

const norm = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]/g, "");

/**
 * 禁存键名黑名单（比较前抹平大小写与 -/_/空格，写成归一化形式）。
 * 这份清单同时被 tests/test_identity.py 拿去和契约文档 §2 的禁存列举对拍，
 * 文档新增一个禁存字段而代码没跟进 → 测红。
 */
export const FORBIDDEN_KEYS = [
  "title", "titles", "headline", "name", "names",
  "doi", "dois", "arxiv", "arxiv_id", "arxivids", "pmid", "pmcid", "issn", "isbn", "istc",
  "url", "urls", "uri", "uris", "link", "links", "href", "hrefs", "pdf", "pdf_url",
  "abstract", "abstracts", "summary", "summaries", "excerpt", "excerpts", "snippet", "snippets",
  "quote", "quotes", "passage", "passages", "fragment", "fragments", "fulltext", "full_text", "body",
  "content", "contents", "text", "content_hash",
  "id", "ids", "paper_id", "paper_ids", "paper_list", "read_papers", "item_id", "item_ids",
  "reading_history", "read_history", "view_history", "history", "viewed", "browsed", "papers_read",
  "clicked", "favorites", "favorites_list", "bookmarks", "bookmark",
  "__proto__", "constructor", "prototype",
];
const FORBIDDEN_SET = new Set(FORBIDDEN_KEYS.map(norm));

// counts 的直接子键里，契约 §2 示例自带的 papers/libs 允许出现（它们只是
// 数量，不是清单）。黑名单对 counts 的其他子键照常生效：counts.urls 一样拒。
const COUNTS_EXCEPTION = new Set(["papers", "libs", "paperscount", "libscount"]);

// 值形状闸：term 命中这些模式 = 可回推到具体论文/网页，禁存。
const IDENTIFIER_VALUE_RE = /^\s*(?:\d{4}\.\d{4,5}(?:v\d+)?|10\.\d{4,5}\/\S+|arxiv:\S+|doi:\S+)\s*$/i;
const URLISH_VALUE_RE = /(?:\/\/|\bwww\.)|(?:\.com\/)|(?:\.org\/)|(?:\.io\/)|(?:\.dev\/)/i;

function isPlainObject(v) {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

/**
 * ISO-8601 时刻解析：必须显式带时区（Z 或 ±HH:MM），且日历字段真实
 * （拒绝 2026-13-45 这类 Date.UTC 会静默顺延的写法）。
 *
 * 为什么要收 +08:00 而不只收 Z：SM 侧的推送时间按本仓时间口径生成，
 * 中文信源带北京时偏移是正常形状（线路契约 §2 的示例恰好是 Z，但那是
 * 示例不是约束）。只认 Z 会把合法载荷判成"需为带时区的 ISO-8601 时刻"，
 * 一句自相矛盾的报错——载荷明明带了时区。
 * 校验方式：按声明的偏移换算出 UTC epoch，再回读同一偏移下的日历字段，
 * 保证 2026-02-30 这种不存在的日子不会靠 Date.UTC 的顺延混进来。
 */
export function parseInstant(s) {
  if (typeof s !== "string") return null;
  const m = s.match(
    /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.\d{1,9})?(Z|[+-]\d{2}:\d{2})$/
  );
  if (!m) return null;
  const [, ys, mos, ds, hs, mis, ss, zone] = m;
  const y = +ys, mo = +mos, d = +ds, h = +hs, mi = +mis, se = +ss;
  if (mo < 1 || mo > 12 || d < 1 || d > 31 || h > 23 || mi > 59 || se > 59) return null;
  let offMin = 0;
  if (zone !== "Z") {
    const sign = zone[0];
    const ohs = +zone.slice(1, 3);
    const oms = +zone.slice(4, 6);
    if (ohs > 23 || oms > 59) return null;
    offMin = sign === "-" ? -(ohs * 60 + oms) : ohs * 60 + oms;
  }
  const t = Date.UTC(y, mo - 1, d, h, mi, se) - offMin * 60000;
  if (!Number.isFinite(t)) return null;
  // 回读校验：把 epoch 还原成"声明时区里的墙上时间"，必须与输入逐字段相同。
  const local = new Date(t + offMin * 60000);
  if (
    local.getUTCFullYear() !== y || local.getUTCMonth() + 1 !== mo || local.getUTCDate() !== d ||
    local.getUTCHours() !== h || local.getUTCMinutes() !== mi || local.getUTCSeconds() !== se
  ) return null;
  return t;
}

function subjectError(label, value, prefixes) {
  const s = String(value == null ? "" : value);
  if (!s) return { code: "FIELD_MISSING", message: label + " 缺失" };
  if (s.length > 128) return { code: "FIELD_TOO_LONG", message: label + " 超过 128 字符" };
  if (!/^[A-Za-z0-9_.:-]+$/.test(s)) return { code: "FIELD_INVALID", message: label + " 含非法字符" };
  if (!prefixes.some((p) => s.startsWith(p))) {
    return { code: "FIELD_INVALID", message: label + " 需以 " + prefixes.join(" 或 ") + " 开头（契约 §1 主体命名空间）" };
  }
  if (s.length <= prefixes[0].length) return { code: "FIELD_INVALID", message: label + " 前缀后需有主体 id" };
  return null;
}

/** 递归找禁存键；返回命中的原始键名。深度 >12 视为畸形载荷（防爆栈）。 */
function findForbidden(obj, depth, parentKey) {
  if (depth > 12) return { tooDeep: true };
  if (Array.isArray(obj)) {
    for (const v of obj) {
      const hit = findForbidden(v, depth + 1, parentKey);
      if (hit) return hit;
    }
    return null;
  }
  if (!isPlainObject(obj)) return null;
  for (const k of Object.keys(obj)) {
    const nk = norm(k);
    const exempt = parentKey === "counts" && COUNTS_EXCEPTION.has(nk);
    if (FORBIDDEN_SET.has(nk) && !exempt) return { key: k };
    const hit = findForbidden(obj[k], depth + 1, k);
    if (hit) return hit;
  }
  return null;
}

function bad(code, message) { return { ok: false, code, message }; }

/**
 * @returns {{ok:true, value:NormalizedSnapshot} | {ok:false, code, message}}
 * opts.nowMs / opts.ttlMaxMs / 白名单可注入，便于测试钉边界；缺省即线上口径。
 */
export function validateSnapshotPayload(raw, opts = {}) {
  const nowMs = typeof opts.nowMs === "number" ? opts.nowMs : Date.now();
  const ttlMax = typeof opts.ttlMaxMs === "number" ? opts.ttlMaxMs : SNAPSHOT_TTL_MAX_MS;
  const catWl = Array.isArray(opts.categoriesWhitelist) ? opts.categoriesWhitelist : CATEGORY_WHITELIST;
  const chWl = Array.isArray(opts.channelsWhitelist) ? opts.channelsWhitelist : CHANNEL_WHITELIST;

  if (!isPlainObject(raw)) return bad("BAD_BODY", "载荷需为 JSON 对象");

  const forbidden = findForbidden(raw, 0, null);
  if (forbidden && forbidden.tooDeep) return bad("FIELD_INVALID", "载荷嵌套过深（>12 层）");
  if (forbidden) {
    return bad("FIELD_FORBIDDEN", "字段 " + forbidden.key + " 属禁存面：快照只答「关心什么」，"
      + "绝不存「读过什么」（标题/DOI/arXiv/摘要/URL/阅读历史一律拒收，线路契约 §2）");
  }

  for (const k of Object.keys(raw)) {
    if (!TOP_KEYS.has(k)) {
      return bad("FIELD_UNKNOWN", "未知字段 " + k + "：快照顶层只允许契约 §2 的 10 个键");
    }
  }

  if (raw.v !== SNAPSHOT_V) {
    return bad("VERSION_UNSUPPORTED", "v 必须恰为 " + SNAPSHOT_V + "，收到 " + JSON.stringify(raw.v));
  }

  const smErr = subjectError("smSubject", raw.smSubject, ["sm:", "wx:"]);
  if (smErr) return smErr;
  const phErr = subjectError("phSubject", raw.phSubject, ["ph:"]);
  if (phErr) return phErr;

  const pushedAt = parseInstant(raw.pushedAt);
  if (pushedAt === null) return bad("FIELD_INVALID", "pushedAt 需为带时区的 ISO-8601 时刻");
  const expiresAt = parseInstant(raw.expiresAt);
  if (expiresAt === null) return bad("FIELD_INVALID", "expiresAt 需为带时区的 ISO-8601 时刻");
  if (expiresAt <= nowMs) return bad("EXPIRES_PAST", "expiresAt 必须是未来时刻（收到 " + raw.expiresAt + "）");
  if (expiresAt > pushedAt + ttlMax) {
    return bad("EXPIRES_TOO_FAR", "expiresAt 超出 pushedAt + " + Math.round(ttlMax / 86400000)
      + " 天上限（" + raw.pushedAt + " → " + raw.expiresAt + "）");
  }

  if (!Array.isArray(raw.topics)) return bad("FIELD_INVALID", "topics 必须是数组");
  if (raw.topics.length > TOPICS_MAX) return bad("FIELD_TOO_LONG", "topics 最多 " + TOPICS_MAX + " 项");
  const topics = [];
  const seenTerm = new Set();
  for (let i = 0; i < raw.topics.length; i++) {
    const t = raw.topics[i];
    const where = "topics[" + i + "]";
    if (!isPlainObject(t)) return bad("FIELD_INVALID", where + " 必须是对象");
    for (const k of Object.keys(t)) {
      if (!TOPIC_KEYS.has(k)) return bad("FIELD_UNKNOWN", where + " 只允许 term/weight，收到 " + k);
    }
    if (typeof t.term !== "string" || !t.term.trim()) {
      return bad("FIELD_INVALID", where + ".term 必须是非空字符串");
    }
    const term = t.term.trim().replace(/\s+/g, " ");
    if (term.length > TOPIC_TERM_MAX) return bad("FIELD_TOO_LONG", where + ".term 超过 " + TOPIC_TERM_MAX + " 字符");
    // 值形状闸排在字符白名单之前：两者都会拒，但"这是个编号/链接"才是真原因。
    // （上一版把字符白名单写在前面，term="arxiv:2301.12345" 拿到的是
    //   "含非法字符"——报错了病因，正是本文件开头说要避免的那种藏原因。）
    if (IDENTIFIER_VALUE_RE.test(term) || URLISH_VALUE_RE.test(term)) {
      return bad("FIELD_FORBIDDEN", where + ".term 是可回推到具体论文/网页的编号或链接形状，属禁存面（契约 §2）");
    }
    if (!/^[A-Za-z0-9\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff .,_()\-/·]*$/.test(term)) {
      return bad("FIELD_INVALID", where + ".term 含非法字符");
    }
    if (typeof t.weight !== "number" || !Number.isFinite(t.weight) || t.weight < 0 || t.weight > 1) {
      return bad("FIELD_INVALID", where + ".weight 必须是 0..1 的有限数，收到 " + JSON.stringify(t.weight));
    }
    const dedupe = term.toLowerCase();
    if (seenTerm.has(dedupe)) return bad("FIELD_INVALID", where + ".term 与前面重复（" + term + "）");
    seenTerm.add(dedupe);
    topics.push({ term, weight: t.weight });
  }

  if (!Array.isArray(raw.categories) || raw.categories.length > CATEGORIES_MAX) {
    return bad("FIELD_INVALID", "categories 必须是数组且 ≤" + CATEGORIES_MAX + " 项");
  }
  const categoriesOut = [];
  for (const c of raw.categories) {
    if (typeof c !== "string" || !catWl.includes(c)) {
      return bad("CATEGORY_NOT_ALLOWED", "category 值不在白名单：" + JSON.stringify(c));
    }
    if (!categoriesOut.includes(c)) categoriesOut.push(c);
  }

  if (!Array.isArray(raw.channels) || raw.channels.length > CHANNELS_MAX) {
    return bad("FIELD_INVALID", "channels 必须是数组且 ≤" + CHANNELS_MAX + " 项");
  }
  const channelsOut = [];
  for (const c of raw.channels) {
    if (typeof c !== "string" || !chWl.includes(c)) {
      return bad("CHANNEL_NOT_ALLOWED", "channel 值不在白名单：" + JSON.stringify(c));
    }
    if (!channelsOut.includes(c)) channelsOut.push(c);
  }

  if (typeof raw.lang !== "string" || !LANG_WHITELIST.includes(raw.lang)) {
    return bad("LANG_NOT_ALLOWED", "lang 只允许 " + LANG_WHITELIST.join("/") + "，收到 " + JSON.stringify(raw.lang));
  }

  if (!isPlainObject(raw.counts)) return bad("FIELD_INVALID", "counts 必须是对象");
  const countKeys = Object.keys(raw.counts);
  if (countKeys.length > COUNTS_KEYS_MAX) return bad("FIELD_TOO_LONG", "counts 最多 " + COUNTS_KEYS_MAX + " 个键");
  const counts = {};
  for (const k of countKeys) {
    if (!/^[a-z][a-z0-9_]{0,23}$/.test(k)) return bad("FIELD_INVALID", "counts 键名需为小写标识符：" + k);
    const v = raw.counts[k];
    if (typeof v !== "number" || !Number.isInteger(v) || v < 0) {
      return bad("FIELD_INVALID", "counts." + k + " 必须是 ≥0 的整数，收到 " + JSON.stringify(v));
    }
    counts[k] = v;
  }

  return {
    ok: true,
    value: {
      v: SNAPSHOT_V,
      smSubject: raw.smSubject,
      phSubject: raw.phSubject,
      pushedAt: raw.pushedAt,
      expiresAt: raw.expiresAt,
      topics,
      categories: categoriesOut,
      channels: channelsOut,
      lang: raw.lang,
      counts,
    },
  };
}
