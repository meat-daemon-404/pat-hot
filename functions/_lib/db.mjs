/**
 * D1 schema 与会话/限流数据访问层。
 *
 * 为什么是 D1：业主批准本站从纯静态长出 Pages Functions + D1（契约 §7）。
 * D1 是 Pages 平台内免运维的 SQL 存储；任务书指定的表形状照用，
 * 注册限流落在 rate_buckets（key TEXT PK, n INT, window_start TEXT）。
 *
 * ensureSchema 是幂等探针：DDL 只在 ph_meta.schema_v 落后当前版本时执行，
 * 探针读不到（首启表不存在）就落回跑 DDL。
 *
 * 诚实降级：D1 绑定缺失（fork 没配库、本地 dev 忘了 --d1-binding）时，
 * 抛 DB_UNAVAILABLE，由路由翻译成带原因的可读失败——绝不静默返回
 * "空用户/空快照"，那会让前端把"后端没配"演成"你没有数据"。
 */

import { newSessionHandle } from "./crypto.mjs";

export const SCHEMA_VERSION = "1";
export const SESSION_TTL_MS = 30 * 24 * 3600 * 1000; // 30 天：低频阅读站，别天天逼人重登

/**
 * 建表语句（TEXT/INT 主键，无外键：本站约束走应用层，外键会让
 * "解绑即硬删"的多表顺序变得易错——契约 §1.2 要求两边都是物理删除、
 * 不留软删墓碑）。表名与契约 §8 W2 的清单逐字一致：
 * ph_users / ph_sessions / ph_bindings / profile_snapshots；
 * ph_meta 只存 schema 版本探针；rate_buckets 是注册限流的计数表。
 */
export const DDL = [
  `CREATE TABLE IF NOT EXISTS ph_users (
    id TEXT PRIMARY KEY,
    email_lc TEXT UNIQUE,
    pw_hash TEXT,
    created_at TEXT
  )`,
  `CREATE TABLE IF NOT EXISTS ph_sessions (
    handle TEXT PRIMARY KEY,
    user_id TEXT,
    created_at TEXT,
    expires_at TEXT
  )`,
  `CREATE TABLE IF NOT EXISTS ph_bindings (
    ph_subject TEXT PRIMARY KEY,
    sm_subject TEXT,
    created_at TEXT
  )`,
  `CREATE TABLE IF NOT EXISTS profile_snapshots (
    sm_subject TEXT PRIMARY KEY,
    ph_subject TEXT,
    payload TEXT,
    pushed_at TEXT,
    expires_at TEXT
  )`,
  `CREATE TABLE IF NOT EXISTS rate_buckets (
    key TEXT PRIMARY KEY,
    n INTEGER,
    window_start TEXT
  )`,
  `CREATE TABLE IF NOT EXISTS ph_meta (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT
  )`,
];

export class DbUnavailable extends Error {}

export function requireDb(env) {
  // 绑定名宽容到 Pages 上几种常见写法，但只认这三类键名：
  // D1 绑定在 env 上就是对象（有 prepare），字符串环境变量不算。
  const candidates = ["PAT_HOT_D1", "PH_D1", "DB"];
  for (const k of candidates) {
    const v = env && env[k];
    if (v && typeof v === "object" && typeof v.prepare === "function") return v;
  }
  throw new DbUnavailable("未绑定 D1 数据库：wrangler pages project 需要 d1 bind（命令见 README「部署前一次性」）");
}

function isDb(db) {
  return db && typeof db === "object" && (typeof db.prepare === "function" || typeof db.query === "function");
}

async function firstRow(db, sql, params = []) {
  if (!isDb(db)) throw new DbUnavailable("D1 绑定不可用");
  const stmt = params.length ? db.prepare(sql).bind(...params) : db.prepare(sql);
  return stmt.first();
}

export async function run(db, sql, params = []) {
  if (!isDb(db)) throw new DbUnavailable("D1 绑定不可用");
  const stmt = params.length ? db.prepare(sql).bind(...params) : db.prepare(sql);
  return stmt.run();
}

export async function all(db, sql, params = []) {
  if (!isDb(db)) throw new DbUnavailable("D1 绑定不可用");
  const stmt = params.length ? db.prepare(sql).bind(...params) : db.prepare(sql);
  const res = await stmt.all();
  return (res && res.results) || [];
}

/**
 * 幂等探针（任务书要求）。batch 保证 DDL 与版本写入原子。
 * 返回值只用于日志，不影响请求成败。
 */
export async function ensureSchema(db) {
  let current = null;
  try {
    const row = await firstRow(db, "SELECT value FROM ph_meta WHERE key = ?", ["schema_v"]);
    current = row ? row.value : null;
  } catch (e) {
    current = null; // 首启：ph_meta 还不存在
  }
  if (current === SCHEMA_VERSION) return { created: false };
  const stmts = DDL.map((sql) => db.prepare(sql));
  const marker = db.prepare("INSERT OR REPLACE INTO ph_meta (key, value, updated_at) VALUES (?, ?, ?)")
    .bind("schema_v", SCHEMA_VERSION, new Date().toISOString());
  if (typeof db.batch === "function") {
    await db.batch(stmts.concat([marker]));
  } else {
    for (const s of stmts) await s.run();
    await marker.run();
  }
  return { created: true };
}

// ---------------- 用户 / 会话 ----------------

export async function findUserByEmail(db, emailLc) {
  return firstRow(db, "SELECT id, email_lc, pw_hash, created_at FROM ph_users WHERE email_lc = ?", [emailLc]);
}

export async function findUserById(db, id) {
  return firstRow(db, "SELECT id, email_lc, created_at FROM ph_users WHERE id = ?", [id]);
}

/** 邮箱唯一性靠 ph_users.email_lc UNIQUE；冲突时 D1 抛错，由调用方翻译成可读失败。 */
export async function insertUser(db, user) {
  await run(db,
    "INSERT INTO ph_users (id, email_lc, pw_hash, created_at) VALUES (?, ?, ?, ?)",
    [user.id, user.emailLc, user.pwHash, user.createdAt]);
}

export async function createSession(db, userId, nowMs = Date.now(), ttlMs = SESSION_TTL_MS) {
  const handle = newSessionHandle();
  const createdAt = new Date(nowMs).toISOString();
  const expiresAt = new Date(nowMs + ttlMs).toISOString();
  await run(db,
    "INSERT INTO ph_sessions (handle, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
    [handle, userId, createdAt, expiresAt]);
  return { handle, createdAt, expiresAt, ttlMs };
}

/**
 * 会话 → 用户。句柄形状先粗筛（纯 hex、长度对齐 HANDLE_BYTES），
 * 过期即硬删那一行并返回 null。身份只从 cookie 会话取（契约 §0）。
 */
export async function resolveSession(db, handle, nowMs = Date.now()) {
  if (!handle || !/^[0-9a-f]{32,128}$/i.test(handle)) return null;
  const row = await firstRow(db,
    "SELECT s.handle AS handle, s.user_id AS user_id, s.expires_at AS expires_at, u.email_lc AS email_lc"
    + " FROM ph_sessions s JOIN ph_users u ON u.id = s.user_id WHERE s.handle = ?",
    [handle]);
  if (!row) return null;
  const exp = Date.parse(row.expires_at || "");
  if (!Number.isFinite(exp) || exp <= nowMs) {
    await run(db, "DELETE FROM ph_sessions WHERE handle = ?", [handle]);
    return null;
  }
  return { handle, userId: row.user_id, email: row.email_lc, expiresAt: row.expires_at };
}

export async function deleteSession(db, handle) {
  await run(db, "DELETE FROM ph_sessions WHERE handle = ?", [handle]);
}

export async function deleteAllSessionsForUser(db, userId) {
  await run(db, "DELETE FROM ph_sessions WHERE user_id = ?", [userId]);
}

// ---------------- 绑定 / 快照 ----------------

export const phSubjectOf = (userId) => "ph:" + String(userId || "");
export const userIdOfPh = (phSubject) => String(phSubject || "").replace(/^ph:/, "");

export async function getBinding(db, phSubject) {
  return firstRow(db, "SELECT ph_subject, sm_subject, created_at FROM ph_bindings WHERE ph_subject = ?", [phSubject]);
}

/** upsert：同 ph_subject 重复兑换改绑新 SM 主体（契约 §1.1 弱绑定，可换绑）。 */
export async function upsertBinding(db, phSubject, smSubject, nowIso) {
  await run(db,
    `INSERT INTO ph_bindings (ph_subject, sm_subject, created_at) VALUES (?, ?, ?)
     ON CONFLICT(ph_subject) DO UPDATE SET sm_subject = excluded.sm_subject`,
    [phSubject, smSubject, nowIso]);
}

export async function deleteBinding(db, phSubject) {
  const res = await run(db, "DELETE FROM ph_bindings WHERE ph_subject = ?", [phSubject]);
  return changesOf(res);
}

/**
 * D1 的 run() 把受影响行数放在 meta.changes。删除类接口要用它回真实计数，
 * 不能拿"我执行了几条 DELETE"冒充"我删掉了几行数据"。
 */
function changesOf(res) {
  const meta = res && (res.meta || (res.results && res.results.meta));
  const n = meta && typeof meta.changes === "number" ? meta.changes : 0;
  return n;
}

/** 覆盖式写入：契约 §2「同主体重复推送覆盖旧快照」。 */
export async function putProfile(db, snap, nowIso) {
  await run(db,
    `INSERT INTO profile_snapshots (sm_subject, ph_subject, payload, pushed_at, expires_at) VALUES (?, ?, ?, ?, ?)
     ON CONFLICT(sm_subject) DO UPDATE SET
       ph_subject = excluded.ph_subject, payload = excluded.payload,
       pushed_at = excluded.pushed_at, expires_at = excluded.expires_at`,
    [snap.smSubject, snap.phSubject, JSON.stringify(snap), snap.pushedAt, snap.expiresAt]);
}

/**
 * 当前生效快照。expiresAt 已过的行**当场硬删**并视作无快照——
 * 存储最小化（Q13 才好删），也让"过期"不依赖任何定时任务。
 */
export async function getActiveProfile(db, smSubject, nowMs = Date.now()) {
  const rows = await all(db,
    "SELECT sm_subject, ph_subject, payload, pushed_at, expires_at FROM profile_snapshots WHERE sm_subject = ?",
    [smSubject]);
  const out = [];
  for (const r of rows) {
    const exp = Date.parse(r.expires_at || "");
    if (Number.isFinite(exp) && exp > nowMs) {
      let payload = null;
      try { payload = JSON.parse(r.payload); } catch (e) { payload = null; }
      if (payload) out.push({ smSubject: r.sm_subject, phSubject: r.ph_subject, payload, pushedAt: r.pushed_at, expiresAt: r.expires_at });
      continue;
    }
    await run(db, "DELETE FROM profile_snapshots WHERE sm_subject = ?", [r.sm_subject]);
  }
  return out;
}

export async function selectProfilesByPh(db, phSubject) {
  return all(db, "SELECT sm_subject, ph_subject, expires_at FROM profile_snapshots WHERE ph_subject = ?", [phSubject]);
}

export async function selectProfileBySm(db, smSubject) {
  return firstRow(db, "SELECT sm_subject, ph_subject, expires_at FROM profile_snapshots WHERE sm_subject = ?", [smSubject]);
}

/** 删除返回真实行数（见 changesOf 注释）：调用方要把它如实报给用户。 */
export async function deleteProfilesByPh(db, phSubject) {
  const res = await run(db, "DELETE FROM profile_snapshots WHERE ph_subject = ?", [phSubject]);
  return changesOf(res);
}

export async function deleteProfileBySm(db, smSubject) {
  const res = await run(db, "DELETE FROM profile_snapshots WHERE sm_subject = ?", [smSubject]);
  return changesOf(res);
}

// ---------------- 限流 ----------------

function instantToMs(v) {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  const t = Date.parse(String(v || ""));
  return Number.isFinite(t) ? t : null;
}

/**
 * 定窗计数判定（纯函数，node --test 直接测，不需要 D1）。
 * 窗口按 epoch 对齐（windowMs 整数倍起点），Function 容器冷启动、
 * 跨小时都不会让计数复活。
 * prev.window_start 兼容 epoch 毫秒与 D1 里存的 ISO 字符串（列型 TEXT）。
 *
 * @returns {{allow:boolean, n:number, windowStart:number, retryAfterSec:number}}
 */
export function rateDecision(prev, limit, windowMs, nowMs = Date.now()) {
  const winStart = Math.floor(nowMs / windowMs) * windowMs;
  const prevStart = prev && prev.window_start != null ? instantToMs(prev.window_start) : null;
  const sameWindow = prevStart !== null && prevStart === winStart;
  const n = sameWindow ? (parseInt(prev.n, 10) || 0) + 1 : 1;
  const allow = n <= limit;
  return {
    allow,
    n,
    windowStart: winStart,
    retryAfterSec: allow ? 0 : Math.max(1, Math.ceil((winStart + windowMs - nowMs) / 1000)),
  };
}

export async function readBucket(db, key) {
  return firstRow(db, "SELECT key, n, window_start FROM rate_buckets WHERE key = ?", [key]);
}

export async function writeBucket(db, key, decision) {
  await run(db,
    `INSERT INTO rate_buckets (key, n, window_start) VALUES (?, ?, ?)
     ON CONFLICT(key) DO UPDATE SET n = excluded.n, window_start = excluded.window_start`,
    [key, decision.n, new Date(decision.windowStart).toISOString()]);
}

/**
 * 一次限流：读桶 → 判定 → 写回。
 * 诚实降级（写在这里不藏在文档里）：D1 的读-改-写不是行级原子，
 * 同一 IP 高并发下可能多放行 1–2 次。对"每 IP 每小时 5 次注册"这种
 * 防脚本洪水的阈值够用；真要卡花钱的接口应换 Durable Objects。
 */
export async function consumeRate(db, key, limit, windowMs, nowMs = Date.now()) {
  const prev = await readBucket(db, key);
  const decision = rateDecision(prev, limit, windowMs, nowMs);
  await writeBucket(db, key, decision);
  return decision;
}
