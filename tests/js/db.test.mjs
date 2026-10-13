/**
 * D1 数据访问层（functions/_lib/db.mjs）——用按 SQL 形状分派的内存 fake 跑，
 * 不打网络、不需要 wrangler。fake 见 helpers/fakeD1.mjs。
 *
 * 盯三件事：限流定窗真的按小时对齐；过期会话与过期快照会被**当场硬删**
 * （存储最小化，Q13 才好删）；表名与契约 §8 的清单逐字一致。
 */
import test from "node:test";
import assert from "node:assert/strict";

import { makeFakeD1 } from "./helpers/fakeD1.mjs";
import {
  DDL, SCHEMA_VERSION, SESSION_TTL_MS, ensureSchema, requireDb, DbUnavailable,
  insertUser, findUserByEmail, createSession, resolveSession, deleteSession,
  upsertBinding, getBinding, deleteBinding,
  putProfile, getActiveProfile, selectProfilesByPh, deleteProfilesByPh, deleteProfileBySm,
  phSubjectOf, userIdOfPh, rateDecision, consumeRate,
} from "../../functions/_lib/db.mjs";

const HOUR = 3600 * 1000;

test("DDL 表名与契约 §8 W2 清单逐字一致", () => {
  const names = DDL.map((s) => /CREATE TABLE IF NOT EXISTS (\w+)/.exec(s)[1]);
  assert.deepEqual(names.sort(), ["ph_bindings", "ph_meta", "ph_sessions", "ph_users", "profile_snapshots", "rate_buckets"]);
  // 变异思路：把 profile_snapshots 改回 ph_profiles（上一版的写法），
  // 这条和 helpers/fakeD1 的形状分派会一起红——契约写的是 profile_snapshots。
  assert.ok(!DDL.some((s) => /ph_profiles/.test(s)), "不许出现契约外的表名");
});

test("requireDb：只认有 prepare 的绑定对象；缺失抛 DbUnavailable 带可操作提示", () => {
  const db = makeFakeD1();
  for (const k of ["PAT_HOT_D1", "PH_D1", "DB"]) {
    assert.equal(requireDb({ [k]: db }), db, k + " 都算合法绑定名");
  }
  assert.throws(() => requireDb({ DB: "postgres://not-a-binding" }), DbUnavailable,
    "字符串环境变量不算 D1 绑定（变异思路：只判 truthy 会把 DB=任意串 当成可用库，报错点漂到第一条 SQL）");
  assert.throws(() => requireDb({}), DbUnavailable);
  try { requireDb({}); } catch (e) { assert.match(e.message, /README/, "报错要指路 README 的 bind 命令"); }
});

test("ensureSchema 幂等：第二次不再跑 DDL", async () => {
  const db = makeFakeD1();
  const r1 = await ensureSchema(db);
  assert.equal(r1.created, true);
  const ddlCount = db.log.filter((x) => /^CREATE TABLE/.test(x.sql)).length;
  assert.equal(ddlCount, DDL.length, "首轮要建全部 " + DDL.length + " 张表");
  const r2 = await ensureSchema(db);
  assert.equal(r2.created, false);
  assert.equal(db.log.filter((x) => /^CREATE TABLE/.test(x.sql)).length, ddlCount,
    "版本探针命中后不许重跑 DDL（变异思路：探针读不到就建表，ph_meta 写入没落盘的话这里会红）");
  assert.equal(db.tables.ph_meta[0].value, SCHEMA_VERSION);
});

test("限流定窗：桶按小时对齐，跨窗口复活，超限拒绝并给 retryAfter", () => {
  const winStart = Math.floor(5 * HOUR / HOUR) * HOUR;
  assert.deepEqual(rateDecision(null, 5, HOUR, 5 * HOUR), { allow: true, n: 1, windowStart: winStart, retryAfterSec: 0 },
    "无历史桶计 1");
  const same = rateDecision({ n: 5, window_start: winStart }, 5, HOUR, 5 * HOUR + 60_000);
  assert.equal(same.allow, false, "同窗口第 6 次必须拒（变异思路：n 从 0 起算或判定写成 n < limit，第 6 次就放行了）");
  assert.equal(same.n, 6);
  assert.ok(same.retryAfterSec > 0 && same.retryAfterSec <= 3600, "拒绝要给人一个等的秒数");
  const next = rateDecision({ n: 5, window_start: winStart }, 5, HOUR, 6 * HOUR + 1);
  assert.equal(next.allow, true, "换窗口即复活（定窗语义，不是滑动）");
  assert.equal(next.n, 1);
  const iso = rateDecision({ n: 5, window_start: new Date(winStart).toISOString() }, 5, HOUR, winStart + 60_000);
  assert.equal(iso.allow, false, "D1 存的是 ISO 字符串（列型 TEXT），判定要认（变异思路：只认数字 epoch，重启后读回全部复活）");
});

test("consumeRate 走真 SQL：同 IP 连打 6 次，第 6 次拒", async () => {
  const db = makeFakeD1();
  const results = [];
  for (let i = 0; i < 6; i++) results.push(await consumeRate(db, "register:1.2.3.4", 5, HOUR, 5 * HOUR + i * 1000));
  assert.deepEqual(results.map((r) => r.allow), [true, true, true, true, true, false]);
  // 换一个 key 互不影响
  const other = await consumeRate(db, "register:5.6.7.8", 5, HOUR, 5 * HOUR);
  assert.equal(other.allow, true);
});

test("会话：创建→解析→登出硬删；过期当场删掉并返回 null", async () => {
  const db = makeFakeD1();
  await insertUser(db, { id: "u1", emailLc: "a@b.c", pwHash: "h", createdAt: "2026-10-13T00:00:00Z" });
  const now = Date.parse("2026-10-13T05:00:00Z");
  const sess = await createSession(db, "u1", now);
  const got = await resolveSession(db, sess.handle, now);
  assert.equal(got.userId, "u1");
  assert.equal(got.email, "a@b.c", "JOIN 回来的列名是 email_lc，必须映射成 email（上一版 publicUser 读 u.email 拿到 undefined，注册后前端根本显示不了当前账号）");
  assert.equal(Date.parse(got.expiresAt) - now, SESSION_TTL_MS, "30 天 TTL");

  const expired = await resolveSession(db, sess.handle, now + SESSION_TTL_MS + 1);
  assert.equal(expired, null, "过期会话不认");
  assert.equal(db.tables.ph_sessions.length, 0,
    "过期要当场硬删这一行，不等定时任务（变异思路：只 return null 不 DELETE，过期行会永远躺在库里）");

  const s2 = await createSession(db, "u1", now);
  await deleteSession(db, s2.handle);
  assert.equal(await resolveSession(db, s2.handle, now), null, "登出后句柄立即失效");
  assert.equal(await resolveSession(db, "zzzz-not-hex!!", now), null, "形状不对的句柄不查库直接拒");
});

test("绑定：upsert 换绑覆盖，delete 返回真实行数", async () => {
  const db = makeFakeD1();
  await upsertBinding(db, "ph:u1", "sm:a", "2026-10-13T05:00:00Z");
  assert.equal((await getBinding(db, "ph:u1")).sm_subject, "sm:a");
  await upsertBinding(db, "ph:u1", "sm:b", "2026-10-13T06:00:00Z");
  assert.equal((await getBinding(db, "ph:u1")).sm_subject, "sm:b", "重复兑换改绑新 SM 主体（契约 §1.1 弱绑定）");
  assert.equal(db.tables.ph_bindings.length, 1, "upsert 不许插出第二行（变异思路：ON CONFLICT 列写错就变双行）");
  assert.equal(await deleteBinding(db, "ph:u1"), 1, "删除返回真实计数");
  assert.equal(await deleteBinding(db, "ph:u1"), 0, "再删不存在的不冒充删掉一行");
  assert.deepEqual([phSubjectOf("u1"), userIdOfPh("ph:u1")], ["ph:u1", "u1"]);
});

test("快照：覆盖写、过期行当场硬删、按 ph/sm 两个方向都能物理删净", async () => {
  const db = makeFakeD1();
  const now = Date.parse("2026-10-13T05:00:00Z");
  const snap = { smSubject: "sm:a", phSubject: "ph:u1", topics: [], pushedAt: new Date(now).toISOString(), expiresAt: new Date(now + 30 * HOUR).toISOString() };
  await putProfile(db, { ...snap, topics: [{ term: "old", weight: 0.1 }] }, new Date(now).toISOString());
  await putProfile(db, { ...snap, topics: [{ term: "new", weight: 0.2 }] }, new Date(now + HOUR).toISOString());
  assert.equal(db.tables.profile_snapshots.length, 1, "同主体重复推送覆盖旧快照（契约 §2）");
  const active = await getActiveProfile(db, "sm:a", now + 2 * HOUR);
  assert.equal(active.length, 1);
  assert.equal(active[0].payload.topics[0].term, "new");

  // 过期：查询即硬删
  const gone = await getActiveProfile(db, "sm:a", now + 31 * HOUR);
  assert.equal(gone.length, 0);
  assert.equal(db.tables.profile_snapshots.length, 0, "过期行当场删掉——存储最小化，不依赖任何定时任务");

  await putProfile(db, snap, new Date(now).toISOString());
  assert.equal((await selectProfilesByPh(db, "ph:u1")).length, 1);
  assert.equal(await deleteProfilesByPh(db, "ph:u1"), 1);
  await putProfile(db, snap, new Date(now).toISOString());
  assert.equal(await deleteProfileBySm(db, "sm:a"), 1);
});
