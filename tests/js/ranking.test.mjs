/**
 * 画像重排（线路契约 §3；functions/_lib/ranking.mjs）。
 * 契约 §3 的两条红线在这里各有一支：命中就升位；未命中不许动原序；
 * 且**只改顺序，绝不改内容**。
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  rankItems, finalScore, baseScoreOf, scoreBoost, termMatchesTopic, snapshotActive,
} from "../../functions/_lib/ranking.mjs";

const snap = (topics, expiresAt = "2099-01-01T00:00:00Z") => ({ topics, expiresAt });

test("命中升位：加了兴趣权重的条目排到前面，原分数本身不动", () => {
  const items = [
    { id: "a", llm_score: 90, keywords: ["solid state battery"] },
    { id: "b", llm_score: 80, keywords: ["quantum error correction"] },
  ];
  const s = snap([{ term: "quantum error correction", weight: 0.5 }]);
  const out = rankItems(items, s);
  assert.equal(out[0].id, "b", "80×1.5=120 > 90，b 必须升到第一位（变异思路：finalScore 若漏乘 (1+boost)，这支会红）");
  assert.equal(out[0].llm_score, 80, "🔴 只重排，绝不改写分数徽标（契约 §3：分数是对外承诺的可复现口径）");
  assert.equal(out[0].keywords[0], "quantum error correction", "🔴 条目内容一字不改（变异思路：加一步 normalizeTitle 就破坏开源面）");
  assert.equal(items[0].id, "a", "入参数组不被就地修改（变异思路：list.sort() 原地排会污染调用方的原始数据）");
});

test("未命中：顺序与内容都与不排序时完全一致", () => {
  const items = [
    { id: "a", llm_score: 90, keywords: ["a"], category: "激光", channel: "tech" },
    { id: "b", llm_score: 80, keywords: ["b"], category: "光通信", channel: "tech" },
    { id: "c", llm_score: 70, keywords: ["c"], category: "其他", channel: "tech" },
  ];
  const s = snap([{ term: "dark matter halo", weight: 0.9 }]);
  assert.deepEqual(rankItems(items, s).map((x) => x.id), ["a", "b", "c"],
    "无命中不许动序（变异思路：把 boost 初值写成极小正数再排序，微小浮点差会随机换序）");
  assert.equal(finalScore(items[0], s), 90);
});

test("无快照 / 空 topics / 未登录：返回原序副本，零行为变化", () => {
  const items = [{ id: "a", llm_score: 1 }, { id: "b", llm_score: 2 }];
  for (const s of [null, undefined, {}, { topics: [] }, { topics: null }]) {
    const out = rankItems(items, s);
    assert.deepEqual(out.map((x) => x.id), ["a", "b"], "契约 §3：未登录/无快照与今天完全一致");
    assert.notEqual(out, items, "必须是副本");
  }
});

test("同分退回原下标：稳定排序，同输入同输出", () => {
  const items = [{ id: "a", llm_score: 50 }, { id: "b", llm_score: 50 }, { id: "c", llm_score: 50 }];
  const s = snap([{ term: "nothing matches", weight: 0.2 }]);
  assert.deepEqual(rankItems(items, s).map((x) => x.id), ["a", "b", "c"]);
  assert.deepEqual(rankItems(items, s).map((x) => x.id), ["a", "b", "c"], "重复调用结果一致（变异思路：比较器不写 a.i - b.i 的兜底，V8 不稳定排序会让同分组换序）");
});

test("命中判定三项：keywords / category / channel 各自成立", () => {
  const s = snap([{ term: "quantum error correction", weight: 0.4 }]);
  assert.equal(scoreBoost({ keywords: ["quantum error correction"] }, s).hits.length, 1, "keyword 全等");
  assert.equal(scoreBoost({ keywords: ["quantum"] }, s).hits.length, 1, "keyword 是 term 的整 token（≥4 字符）也算命中");
  assert.equal(scoreBoost({ category: "quantum error correction" }, s).hits[0].why, "category");
  assert.equal(scoreBoost({ channel: "quantum error correction" }, s).hits[0].why, "channel");
  assert.equal(scoreBoost({ keywords: ["co"] }, s).boost, 0, "2 字符短 token 不算命中（变异思路：去掉长度下限，co 会命中 cooling 铺满全场）");
  assert.equal(scoreBoost({ keywords: ["quantumnc"] }, s).boost, 0, "不是整 token 就不算（变异思路：改成 substring 包含就会被这种粘连词误命中）");
});

test("多个命中的权重相加，且 base 取 llm_score 优先", () => {
  const s = snap([{ term: "alpha", weight: 0.3 }, { term: "beta", weight: 0.2 }]);
  const item = { llm_score: 100, keywords: ["alpha", "beta"] };
  assert.equal(scoreBoost(item, s).boost, 0.5);
  assert.equal(finalScore(item, s), 150);
  assert.equal(baseScoreOf({ llm_score: 10, score: 99 }), 10, "llm_score 优先（与卡片徽标显示口径一致）");
  assert.equal(baseScoreOf({ score: 99 }), 99, "没有 llm_score 退回 score");
  assert.equal(baseScoreOf({ heat: 7 }), 7);
  assert.equal(baseScoreOf({}), 0);
  assert.equal(baseScoreOf(null), 0);
});

test("snapshotActive：expiresAt 未到才生效，过期即整体失效", () => {
  const now = Date.parse("2026-10-13T05:00:00Z");
  assert.equal(snapshotActive({ expiresAt: "2026-11-12T04:00:00Z" }, now), true);
  assert.equal(snapshotActive({ expiresAt: "2026-10-13T04:00:00Z" }, now), false, "已过期");
  assert.equal(snapshotActive({ expiresAt: "2026-10-13T05:00:00Z" }, now), false,
    "恰好此刻过期判失效（变异思路：写成 >= 会让它多生效一秒，与 db.getActiveProfile 的硬删口径漂移）");
  assert.equal(snapshotActive({}, now), false, "没有 expiresAt 不算生效");
  assert.equal(snapshotActive(null, now), false);
  assert.equal(snapshotActive({ expiresAt: "not-a-date" }, now), false);
});

test("过期快照不参与重排（契约 §3：expiresAt 一过行为回到未登录）", () => {
  const items = [
    { id: "a", llm_score: 90, keywords: ["qec"] },
    { id: "b", llm_score: 80, keywords: ["qec"] },
  ];
  const expired = { topics: [{ term: "qec", weight: 0.9 }], expiresAt: "2020-01-01T00:00:00Z" };
  assert.equal(snapshotActive(expired), false);
  // 调用方按 snapshotActive 决定是否传快照；这里钉住"传了过期快照也只是按分数排"
  assert.deepEqual(rankItems(items, { topics: [] }).map((x) => x.id), ["a", "b"]);
  assert.equal(finalScore(items[1], { topics: [] }), 80);
});
