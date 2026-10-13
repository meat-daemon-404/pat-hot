/**
 * 内存版 D1 fake：只按 **SQL 形状**分派，不真跑 SQLite。
 * 路子照 SM 仓 frontend/src/lib/workerRateLimitMany.test.js 里那个 fake：
 * prepare(sql) 记下语句，bind(...args) 记下参数，first/all/run 时按语句
 * 形状匹配到对应的内存表操作。
 *
 * 为什么要按形状而不是"随便返回个空对象"：本仓 db.mjs 的每一条 SQL 都
 * 带着它要动的表和键，形状匹配能让"写了错误的表名 / 漏了 WHERE /
 * ON CONFLICT 写错列"这类事故在这里就撞上 ` unmatched SQL ` 抛错。
 * 上一版把快照表写成 ph_profiles（契约 §8 的清单是 profile_snapshots），
 * 就是靠这条抛错 + 一条逐字对拍测试钉住的。
 *
 * 覆盖范围＝functions/_lib/db.mjs 实际发出的语句集合；多一个都不写，
 * 免得 fake 比生产代码还宽松（那会让测试绿得没有意义）。
 */

const norm = (sql) => String(sql).replace(/\s+/g, " ").trim();

/** 一条 UPDATE/INSERT/DELETE 都不许在没有 WHERE 的情况下落到 fake 上。 */
export function makeFakeD1(seed = {}) {
  const tables = {
    ph_users: [],
    ph_sessions: [],
    ph_bindings: [],
    profile_snapshots: [],
    rate_buckets: [],
    ph_meta: [],
  };
  for (const k of Object.keys(seed)) {
    if (!(k in tables)) throw new Error("FAKE D1: 未知种子表 " + k);
    tables[k] = seed[k].map((r) => ({ ...r }));
  }
  const log = [];

  function matches(sql, re) { return re.exec(norm(sql)); }

  function exec(sql, args) {
    const s = norm(sql);
    log.push({ sql: s, args });
    let m;

    // ---- 探针 / DDL（ensureSchema）----
    if ((m = matches(s, /^SELECT value FROM ph_meta WHERE key = \?$/))) {
      const row = tables.ph_meta.find((r) => r.key === args[0]);
      return row ? { value: row.value } : null;
    }
    if ((m = matches(s, /^INSERT OR REPLACE INTO ph_meta \(key, value, updated_at\) VALUES \(\?, \?, \?\)$/))) {
      tables.ph_meta = tables.ph_meta.filter((r) => r.key !== args[0]);
      tables.ph_meta.push({ key: args[0], value: args[1], updated_at: args[2] });
      return { meta: { changes: 1 } };
    }
    if ((m = matches(s, /^CREATE TABLE IF NOT EXISTS (\w+) /))) {
      tables[m[1]] = tables[m[1]] || [];   // 幂等建表：已存在不重置数据
      return { meta: { changes: 0 } };
    }

    // ---- ph_users ----
    if (matches(s, /^SELECT id, email_lc, pw_hash, created_at FROM ph_users WHERE email_lc = \?$/)) {
      return tables.ph_users.find((u) => u.email_lc === args[0]) || null;
    }
    if (matches(s, /^SELECT id, email_lc, created_at FROM ph_users WHERE id = \?$/)) {
      return tables.ph_users.find((u) => u.id === args[0]) || null;
    }
    if (matches(s, /^INSERT INTO ph_users \(id, email_lc, pw_hash, created_at\) VALUES \(\?, \?, \?, \?\)$/)) {
      if (tables.ph_users.some((u) => u.email_lc === args[1])) {
        // 真 D1 撞 UNIQUE 就是这个形状的错误文本；注册路径靠它兜并发。
        throw new Error("UNIQUE constraint failed: ph_users.email_lc");
      }
      tables.ph_users.push({ id: args[0], email_lc: args[1], pw_hash: args[2], created_at: args[3] });
      return { meta: { changes: 1 } };
    }

    // ---- ph_sessions ----
    if (matches(s, /^INSERT INTO ph_sessions \(handle, user_id, created_at, expires_at\) VALUES \(\?, \?, \?, \?\)$/)) {
      tables.ph_sessions.push({ handle: args[0], user_id: args[1], created_at: args[2], expires_at: args[3] });
      return { meta: { changes: 1 } };
    }
    if (matches(s, /^SELECT s\.handle AS handle, s\.user_id AS user_id, s\.expires_at AS expires_at, u\.email_lc AS email_lc FROM ph_sessions s JOIN ph_users u ON u\.id = s\.user_id WHERE s\.handle = \?$/)) {
      const sess = tables.ph_sessions.find((x) => x.handle === args[0]);
      if (!sess) return null;
      const u = tables.ph_users.find((x) => x.id === sess.user_id) || {};
      return { handle: sess.handle, user_id: sess.user_id, expires_at: sess.expires_at, email_lc: u.email_lc };
    }
    if (matches(s, /^DELETE FROM ph_sessions WHERE handle = \?$/)) {
      const before = tables.ph_sessions.length;
      tables.ph_sessions = tables.ph_sessions.filter((x) => x.handle !== args[0]);
      return { meta: { changes: before - tables.ph_sessions.length } };
    }
    if (matches(s, /^DELETE FROM ph_sessions WHERE user_id = \?$/)) {
      const before = tables.ph_sessions.length;
      tables.ph_sessions = tables.ph_sessions.filter((x) => x.user_id !== args[0]);
      return { meta: { changes: before - tables.ph_sessions.length } };
    }

    // ---- ph_bindings ----
    if (matches(s, /^SELECT ph_subject, sm_subject, created_at FROM ph_bindings WHERE ph_subject = \?$/)) {
      return tables.ph_bindings.find((b) => b.ph_subject === args[0]) || null;
    }
    if (matches(s, /^INSERT INTO ph_bindings \(ph_subject, sm_subject, created_at\) VALUES \(\?, \?, \?\) ON CONFLICT\(ph_subject\) DO UPDATE SET sm_subject = excluded\.sm_subject$/)) {
      const ex = tables.ph_bindings.find((b) => b.ph_subject === args[0]);
      if (ex) ex.sm_subject = args[1];
      else tables.ph_bindings.push({ ph_subject: args[0], sm_subject: args[1], created_at: args[2] });
      return { meta: { changes: 1 } };
    }
    if (matches(s, /^DELETE FROM ph_bindings WHERE ph_subject = \?$/)) {
      const before = tables.ph_bindings.length;
      tables.ph_bindings = tables.ph_bindings.filter((b) => b.ph_subject !== args[0]);
      return { meta: { changes: before - tables.ph_bindings.length } };
    }

    // ---- profile_snapshots ----
    if (matches(s, /^INSERT INTO profile_snapshots \(sm_subject, ph_subject, payload, pushed_at, expires_at\) VALUES \(\?, \?, \?, \?, \?\) ON CONFLICT\(sm_subject\) DO UPDATE SET ph_subject = excluded\.ph_subject, payload = excluded\.payload, pushed_at = excluded\.pushed_at, expires_at = excluded\.expires_at$/)) {
      const ex = tables.profile_snapshots.find((r) => r.sm_subject === args[0]);
      const row = { sm_subject: args[0], ph_subject: args[1], payload: args[2], pushed_at: args[3], expires_at: args[4] };
      if (ex) Object.assign(ex, row);
      else tables.profile_snapshots.push(row);
      return { meta: { changes: 1 } };
    }
    if (matches(s, /^SELECT sm_subject, ph_subject, payload, pushed_at, expires_at FROM profile_snapshots WHERE sm_subject = \?$/)) {
      return tables.profile_snapshots.filter((r) => r.sm_subject === args[0]);
    }
    if (matches(s, /^SELECT sm_subject, ph_subject, expires_at FROM profile_snapshots WHERE ph_subject = \?$/)) {
      return tables.profile_snapshots.filter((r) => r.ph_subject === args[0]);
    }
    if (matches(s, /^SELECT sm_subject, ph_subject, expires_at FROM profile_snapshots WHERE sm_subject = \?$/)) {
      return tables.profile_snapshots.find((r) => r.sm_subject === args[0]) || null;
    }
    if (matches(s, /^DELETE FROM profile_snapshots WHERE ph_subject = \?$/)) {
      const before = tables.profile_snapshots.length;
      tables.profile_snapshots = tables.profile_snapshots.filter((r) => r.ph_subject !== args[0]);
      return { meta: { changes: before - tables.profile_snapshots.length } };
    }
    if (matches(s, /^DELETE FROM profile_snapshots WHERE sm_subject = \?$/)) {
      const before = tables.profile_snapshots.length;
      tables.profile_snapshots = tables.profile_snapshots.filter((r) => r.sm_subject !== args[0]);
      return { meta: { changes: before - tables.profile_snapshots.length } };
    }

    // ---- rate_buckets ----
    if (matches(s, /^SELECT key, n, window_start FROM rate_buckets WHERE key = \?$/)) {
      return tables.rate_buckets.find((r) => r.key === args[0]) || null;
    }
    if (matches(s, /^INSERT INTO rate_buckets \(key, n, window_start\) VALUES \(\?, \?, \?\) ON CONFLICT\(key\) DO UPDATE SET n = excluded\.n, window_start = excluded\.window_start$/)) {
      const ex = tables.rate_buckets.find((r) => r.key === args[0]);
      if (ex) { ex.n = args[1]; ex.window_start = args[2]; }
      else tables.rate_buckets.push({ key: args[0], n: args[1], window_start: args[2] });
      return { meta: { changes: 1 } };
    }

    throw new Error("FAKE D1: unmatched SQL ->\n  " + s + "\n  args=" + JSON.stringify(args));
  }

  const db = {
    tables,
    log,
    prepare(sql) {
      const self = {
        bind(...args) { self.__args = args; return self; },
        async first() {
          const r = exec(sql, self.__args || []);
          return r === null || Array.isArray(r) ? (r && r[0]) || null : r;
        },
        async all() {
          const r = exec(sql, self.__args || []);
          return { results: r === null ? [] : (Array.isArray(r) ? r : [r]) };
        },
        async run() { return exec(sql, self.__args || []); },
      };
      return self;
    },
    async batch(stmts) {
      const out = [];
      for (const s of stmts) out.push(await s.run());
      return out;
    },
  };
  return db;
}
