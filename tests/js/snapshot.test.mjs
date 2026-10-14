/**
 * 画像快照校验器（线路契约 §2；functions/_lib/snapshot.mjs）。
 *
 * 这是本站"文档承诺 vs 实际执行"的分界：契约 §2 说禁存论文标题 / DOI /
 * arXiv / 摘要 / URL / 阅读历史，只有这里的 FORBIDDEN_KEYS 加值形状闸真的在挡。
 * 所以每条**正向**断言都配一句"把校验条件改宽就会被抓"的变异思路——
 * 说明它不是顺手断言，而是钉住那条边界。FORBIDDEN_KEYS 按要求真跑了构造载荷。
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  validateSnapshotPayload, parseInstant, FORBIDDEN_KEYS,
  CHANNEL_WHITELIST, CATEGORY_WHITELIST, LANG_WHITELIST,
  TOPICS_MAX, TOPIC_TERM_MAX, SNAPSHOT_TTL_MAX_MS,
} from "../../functions/_lib/snapshot.mjs";

const NOW = Date.parse("2026-10-13T05:00:00Z");
const opts = { nowMs: NOW };

/** 契约 §2 示例逐字改成对象（合法基线）。 */
function good(over = {}) {
  return {
    v: 1,
    smSubject: "sm:abc123",
    phSubject: "ph:9f8e7d",
    pushedAt: "2026-10-13T04:00:00Z",
    expiresAt: "2026-11-12T04:00:00Z",
    topics: [{ term: "quantum error correction", weight: 0.42 }],
    categories: ["科研进展"],
    channels: ["physics", "tech"],
    lang: "zh",
    counts: { papers: 38, libs: 3 },
    ...over,
  };
}

test("合法载荷通过，并原样带出各字段", () => {
  const r = validateSnapshotPayload(good(), opts);
  assert.equal(r.ok, true, r.message || "");
  // 变异思路：这条单看会被"weight 上限改成 Infinity"混过去，
  // 所以下面另立了权重越界那一支来钉边界。
  assert.equal(r.value.smSubject, "sm:abc123");
  assert.deepEqual(r.value.topics, [{ term: "quantum error correction", weight: 0.42 }]);
  assert.deepEqual(r.value.channels, ["physics", "tech"]);
  assert.deepEqual(r.value.counts, { papers: 38, libs: 3 },
    "counts.papers / counts.libs 是契约自带的合法键（变异思路：黑名单若在任意位置都拒 papers，这条合法载荷自己先死）");
});

test("时间口径：Z 与 ±HH:MM 都收，裸时间和假日期都拒", () => {
  // 变异思路：parseInstant 若只认 Z，SM 侧按北京时间（+08:00）推送会拿到
  // "需为带时区的 ISO-8601 时刻"这句自相矛盾的报错——载荷明明带了时区。
  const plus = good({ pushedAt: "2026-10-13T12:00:00+08:00", expiresAt: "2026-11-12T12:00:00+08:00" });
  assert.equal(validateSnapshotPayload(plus, opts).ok, true, "+08:00 形状必须收");
  assert.equal(validateSnapshotPayload(good({ pushedAt: "2026-10-13T04:00:00" }), opts).code, "FIELD_INVALID",
    "不带时区的裸时间必须拒（否则同一份载荷在不同时区的服务器上算出不同 TTL）");
  assert.equal(validateSnapshotPayload(good({ pushedAt: "2026-02-30T04:00:00Z" }), opts).code, "FIELD_INVALID",
    "2 月 30 日要拒（变异思路：只 Date.parse 不回读日历字段，Date.UTC 会静默顺延到 3 月 2 日混过去）");
});

test("FORBIDDEN_KEYS 命中：顶层与任意深度都拒，且报的是 FIELD_FORBIDDEN", () => {
  // 这一支按要求真跑：不是读注释，是把带 title 的载荷喂进去看拒没拒。
  const topTitle = validateSnapshotPayload(good({ title: "Observation of ..." }), opts);
  assert.equal(topTitle.ok, false);
  assert.equal(topTitle.code, "FIELD_FORBIDDEN",
    "必须先跑禁存面再跑未知键：写成 FIELD_UNKNOWN 会把「我们在挡阅读历史」这个真实原因藏掉（变异思路：调换两个检查的顺序就被这里抓到）");
  assert.match(topTitle.message, /title/, "message 要带命中的原始键名");

  const nested = validateSnapshotPayload(good({ topics: [{ term: "cw", weight: 0.1, title: "偷偷夹带" }] }), opts);
  assert.equal(nested.code, "FIELD_FORBIDDEN", "topics 项里藏 title 同样要拒");
  assert.match(nested.message, /title/);

  const deep = validateSnapshotPayload(good({ counts: { papers: 1, reading_history: 12 } }), opts);
  assert.equal(deep.code, "FIELD_FORBIDDEN",
    "counts 里塞阅读历史也要拒（变异思路：豁免清单若写成「整个 counts 不查禁存面」就会放过）");

  const alias = validateSnapshotPayload(good({ Read_History: ["a"] }), opts);
  assert.equal(alias.code, "FIELD_FORBIDDEN", "大小写与下划线归一化后仍命中（变异思路：不做 norm 就会被 Read_History 绕过）");

  for (const k of ["title", "doi", "arxiv", "abstract", "url", "summary", "excerpt", "reading_history"]) {
    assert.ok(FORBIDDEN_KEYS.includes(k), k + " 必须在黑名单里（契约 §2 的禁存列举）");
  }
});

test("值形状闸：键名洗成 term 也绕不过（编号/链接形状照样拒）", () => {
  for (const term of [
    "2301.12345", "arxiv:2301.12345", "10.1038/s41586-024-00000-0",
    "https://x.com/a", "www.example.com/paper", "doi:10.1/xyz",
  ]) {
    const r = validateSnapshotPayload(good({ topics: [{ term, weight: 0.3 }] }), opts);
    assert.equal(r.code, "FIELD_FORBIDDEN",
      term + " 是可回推到具体论文/网页的形状（变异思路：只查键名黑名单，把数据塞进合法键 term 就全放行了）");
  }
  assert.equal(validateSnapshotPayload(good({ topics: [{ term: "cooling traps", weight: 0.3 }] }), opts).ok, true,
    "普通主题词不能被误伤（变异思路：正则写宽到匹配任意含数字的词，这支会红）");
});

test("未知键闭集：顶层只允许契约 §2 的 10 个键", () => {
  const r = validateSnapshotPayload(good({ favorite_papers: [] }), opts);
  // favorite_papers 归一化后不含黑名单词，靠"未知键"这层挡——两道闸互补。
  assert.equal(r.code, "FIELD_UNKNOWN");
  assert.equal(validateSnapshotPayload(good({ topics: [{ term: "a", weight: 0.1, url: "u" }] }), opts).code,
    "FIELD_FORBIDDEN", "topics 项里的 url 先撞禁存面");
  assert.equal(validateSnapshotPayload(good({ topics: [{ term: "a", weight: 0.1, rank: 3 }] }), opts).code,
    "FIELD_UNKNOWN", "topics 项只允许 term/weight（变异思路：TOPIC_KEYS 多加一个键就会被这里抓到）");
});

test("权重越界：非 0..1 的有限数拒收", () => {
  for (const w of [-0.1, 1.5, NaN, Infinity, "0.42", null, undefined]) {
    const r = validateSnapshotPayload(good({ topics: [{ term: "qec", weight: w }] }), opts);
    assert.equal(r.ok, false, JSON.stringify(w) + " 必须拒（变异思路：把上界写成 w <= 10，1.5 那支就红了）");
    assert.equal(r.code, "FIELD_INVALID");
  }
  assert.equal(validateSnapshotPayload(good({ topics: [{ term: "qec", weight: 0 }] }), opts).ok, true, "0 合法");
  assert.equal(validateSnapshotPayload(good({ topics: [{ term: "qec", weight: 1 }] }), opts).ok, true,
    "1 合法（变异思路：写成 w < 1 就把边界上的 1 拒了）");
});

test("expiresAt 超 31 天上限 / 落在过去：各有其码", () => {
  assert.equal(validateSnapshotPayload(good({ expiresAt: "2026-12-31T04:00:00Z" }), opts).code, "EXPIRES_TOO_FAR");
  assert.equal(validateSnapshotPayload(good({ expiresAt: "2026-10-13T04:00:00Z" }), opts).code, "EXPIRES_PAST",
    "早于 nowMs 的过期时间要拒（变异思路：把 expiresAt <= nowMs 写成小于号，恰好此刻过期的载荷就能混进来）");
  assert.equal(validateSnapshotPayload(good(), opts).ok, true, "正好 30 天要过");
  assert.equal(SNAPSHOT_TTL_MAX_MS, 31 * 24 * 3600 * 1000, "31 天是契约 §2 的上限（改大改小都算偏离契约）");
  assert.equal(validateSnapshotPayload(good({ expiresAt: "2026-11-13T04:00:00Z" }), opts).ok, true,
    "恰好 31 天必须放行（变异思路：上限写成 30 天，这支会红）");
  assert.equal(validateSnapshotPayload(good({ expiresAt: "2026-11-13T04:00:01Z" }), opts).code, "EXPIRES_TOO_FAR",
    "多一秒就要拒（钉住 31 天的确切位置）");
});

test("channels 白名单外拒收，且白名单与 collector/channels.json 同集合", () => {
  assert.equal(validateSnapshotPayload(good({ channels: ["biology"] }), opts).code, "CHANNEL_NOT_ALLOWED",
    "（变异思路：把 chWl.includes 改成真值判断，任意频道都放行）");
  assert.deepEqual([...CHANNEL_WHITELIST].sort(), ["astro", "physics", "tech"], "三频道就是本站的频道面");
  assert.equal(validateSnapshotPayload(good({ channels: [] }), opts).ok, true, "空数组合法（表示不限频道）");
  assert.ok(CATEGORY_WHITELIST.includes("科研进展") && CATEGORY_WHITELIST.includes("光通信"),
    "分类白名单同时含物理与光电两类");
});

test("topics 超上限 / term 超长 / 重复 term：各有其码", () => {
  const many = Array.from({ length: TOPICS_MAX + 1 }, (_, i) => ({ term: "topic " + i, weight: 0.1 }));
  assert.equal(validateSnapshotPayload(good({ topics: many }), opts).code, "FIELD_TOO_LONG");
  const atMax = Array.from({ length: TOPICS_MAX }, (_, i) => ({ term: "topic " + i, weight: 0.1 }));
  assert.equal(validateSnapshotPayload(good({ topics: atMax }), opts).ok, true,
    "恰好 64 项要放行（变异思路：写成 < TOPICS_MAX 就把边界拒了）");
  assert.equal(validateSnapshotPayload(good({ topics: [{ term: "x".repeat(TOPIC_TERM_MAX + 1), weight: 0.1 }] }), opts).code,
    "FIELD_TOO_LONG");
  assert.equal(validateSnapshotPayload(good({ topics: [{ term: "QEC", weight: 0.1 }, { term: "qec", weight: 0.2 }] }), opts).code,
    "FIELD_INVALID", "大小写不同的同词要判重复（变异思路：dedupe 不做 toLowerCase 就放过）");
  assert.equal(validateSnapshotPayload(good({ topics: [] }), opts).ok, true, "空 topics 合法：只表示暂无兴趣词");
  assert.equal(validateSnapshotPayload(good({ topics: "not-an-array" }), opts).code, "FIELD_INVALID");
});

test("主体前缀：sm:/wx: 与 ph: 各归各位，缺前缀或只有前缀都拒", () => {
  assert.equal(validateSnapshotPayload(good({ smSubject: "abc123" }), opts).code, "FIELD_INVALID");
  assert.equal(validateSnapshotPayload(good({ phSubject: "sm:abc" }), opts).code, "FIELD_INVALID",
    "ph 侧不能收 sm: 前缀（变异思路：把前缀表并成同时接受 sm: 与 ph: 就混了）");
  assert.equal(validateSnapshotPayload(good({ phSubject: "ph:" }), opts).code, "FIELD_INVALID", "只有前缀不算主体");
  assert.equal(validateSnapshotPayload(good({ smSubject: "wx:openid123" }), opts).ok, true,
    "小程序侧 wx: 前缀是契约 §1 认可的 SM 主体");
  assert.equal(validateSnapshotPayload(good({ smSubject: "" }), opts).code, "FIELD_MISSING");
});

test("v 必须恰为 1；lang 与 categories 各有白名单", () => {
  assert.equal(validateSnapshotPayload(good({ v: 2 }), opts).code, "VERSION_UNSUPPORTED");
  assert.equal(validateSnapshotPayload(good({ v: "1" }), opts).code, "VERSION_UNSUPPORTED",
    "字符串形式的 1 不算（变异思路：把严格不等改成宽松比较就会放过它）");
  assert.equal(validateSnapshotPayload(good({ lang: "fr" }), opts).code, "LANG_NOT_ALLOWED");
  assert.ok(LANG_WHITELIST.includes("zh") && LANG_WHITELIST.includes("en"));
  assert.equal(validateSnapshotPayload(good({ categories: ["不存在的分类"] }), opts).code, "CATEGORY_NOT_ALLOWED");
  assert.equal(validateSnapshotPayload(good({ categories: ["科研进展", "科研进展"] }), opts).ok, true, "重复分类去重后放行");
});

test("counts：只收非负整数、键名受限、键数有上限", () => {
  assert.equal(validateSnapshotPayload(good({ counts: { papers: -3 } }), opts).code, "FIELD_INVALID");
  assert.equal(validateSnapshotPayload(good({ counts: { papers: 1.5 } }), opts).code, "FIELD_INVALID");
  assert.equal(validateSnapshotPayload(good({ counts: { "Bad Key": 1 } }), opts).code, "FIELD_INVALID");
  const many = {};
  for (let i = 0; i < 13; i++) many["k" + i] = 1;
  assert.equal(validateSnapshotPayload(good({ counts: many }), opts).code, "FIELD_TOO_LONG");
  assert.equal(validateSnapshotPayload(good({ counts: {} }), opts).ok, true, "空 counts 合法");
});

test("载荷形状：非对象与 __proto__ 都不放行", () => {
  assert.equal(validateSnapshotPayload(null, opts).code, "BAD_BODY");
  assert.equal(validateSnapshotPayload("[]", opts).code, "BAD_BODY");
  assert.equal(validateSnapshotPayload([1, 2], opts).code, "BAD_BODY");
  const proto = validateSnapshotPayload(JSON.parse('{"__proto__":{"x":1},"v":1}'), opts);
  assert.equal(proto.code, "FIELD_FORBIDDEN", "__proto__ 在黑名单里，走禁存面而不是未知键");
});

test("parseInstant 单元面", () => {
  assert.equal(parseInstant("2026-10-13T04:00:00Z"), Date.parse("2026-10-13T04:00:00Z"));
  assert.equal(parseInstant("2026-10-13T04:00:00.062Z"), Date.parse("2026-10-13T04:00:00Z"),
    "带毫秒的要截到秒并仍指向同一时刻（Date.toISOString 就长这样，拒了会把自家注册路径写回的载荷判死）");
  assert.equal(parseInstant("2026-10-13T12:00:00+08:00"), Date.parse("2026-10-13T04:00:00Z"),
    "带偏移的换算成同一时刻");
  assert.equal(parseInstant("2026-10-13T04:00:00"), null, "裸时间拒");
  assert.equal(parseInstant("2026-10-13T04:00:00+0000"), null, "基本格式偏移（无冒号）不在口径里，宁拒不含糊");
  assert.equal(parseInstant("2026-13-01T00:00:00Z"), null);
  assert.equal(parseInstant(12345), null);
});
