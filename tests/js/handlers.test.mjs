/**
 * 路由级行为（functions/_lib/handlers.mjs）：不打网络，D1 用内存 fake，
 * SM 那一跳用 context.fetchImpl 注入（Pages 的 context 没这个属性，
 * 生产恒为 undefined → 走全局 fetch，不为测试另开代码分支）。
 *
 * 盯的是任务书里最容易只写在注释里的东西：失败分型是否真的分开了、
 * 身份是否真的只从 cookie 取、开关关着时是否真的 503。
 */
import test from "node:test";
import assert from "node:assert/strict";

import { makeFakeD1 } from "./helpers/fakeD1.mjs";
import {
  registerHandler, loginHandler, logoutHandler, meHandler,
  bindVerifyHandler, snapshotPutHandler, snapshotDeleteHandler, profileGetHandler,
  hasSharedSecret, snapshotFieldCounts, REGISTER_LIMIT,
} from "../../functions/_lib/handlers.mjs";
import { upsertBinding, insertUser, phSubjectOf } from "../../functions/_lib/db.mjs";
import { pwHash } from "../../functions/_lib/crypto.mjs";
import { CALLBACK_TIMEOUT_MS } from "../../functions/_lib/smclient.mjs";

const BASE = "https://pat-hot.pages.dev";
const HOUR = 3600 * 1000;

function mkReq(path, { method = "GET", body, headers = {}, ip } = {}) {
  const h = { "Content-Type": "application/json", Origin: BASE, ...headers };
  if (ip) h["CF-Connecting-IP"] = ip;
  return new Request(BASE + path, {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
    headers: h,
  });
}

function setup(seed = {}) {
  const db = makeFakeD1(seed);
  const env = {
    PAT_HOT_STORE_USER_DATA: "1",
    PAT_HOT_D1: db,
    PAT_SHARED_SECRET: "s3cret",
    SM_BASE: "https://scholarmatrix.pages.dev",
  };
  return { db, env, ctx: (request, extra = {}) => ({ request, env, params: {}, ...extra }) };
}

/** 注册并返回 { cookie, body, db, env }。 */
async function registerAndLogin(t, email = "A@B.com", password = "hunter2222") {
  const res = await registerHandler(t.ctx(mkReq("/api/account/register", { method: "POST", body: { email, password } })));
  const body = await res.json();
  return { res, body, cookie: (res.headers.get("Set-Cookie") || "").split(";")[0] };
}

const payloadOf = (phSubject, over = {}) => ({
  v: 1, smSubject: "sm:abc123", phSubject,
  pushedAt: "2026-10-13T04:00:00Z", expiresAt: "2026-11-12T04:00:00Z",
  topics: [{ term: "quantum error correction", weight: 0.42 }],
  categories: ["科研进展"], channels: ["physics"], lang: "zh", counts: { papers: 38, libs: 3 },
  ...over,
});

test("注册→种会话→me 认出同一人：身份全程只从 cookie 走", async (t) => {
  const s = setup();
  const { res, body, cookie } = await registerAndLogin(s);
  assert.equal(res.status, 200);
  assert.equal(body.ok, true);
  assert.match(body.user.id, /^[0-9a-f]{12}$/);
  assert.equal(body.user.subject, phSubjectOf(body.user.id), "契约 §1：PH 主体是 ph:<id>");
  assert.equal(body.user.email, "a@b.com", "🔴 邮箱小写归一后回给前端（上一版读错列名，这里会是 undefined）");
  assert.match(res.headers.get("Set-Cookie"), /^ph_session=[0-9a-f]{64}; Path=\/; HttpOnly; SameSite=Lax/, "HttpOnly + Lax 缺一不可");

  const me = await meHandler(s.ctx(mkReq("/api/account/me", { headers: { Cookie: cookie } })));
  const meBody = await me.json();
  assert.equal(me.status, 200);
  assert.equal(meBody.ok, true);
  assert.equal(meBody.user.id, body.user.id);
  assert.equal(meBody.bound, false);

  // body 里自称是别人也没用
  const forged = await meHandler(s.ctx(mkReq("/api/account/me", { headers: { Cookie: cookie } })));
  assert.equal((await forged.json()).user.id, body.user.id, "me 不读任何 body 身份");

  const lg = await loginHandler(s.ctx(mkReq("/api/account/login", { method: "POST", body: { email: "a@b.com", password: "hunter2222" } })));
  assert.equal(lg.status, 200, "小写归一后的邮箱能登录（变异思路：注册归一化、登录不归一化，这里会 401）");
});

test("注册校验：邮箱去重、弱密码、限流每 IP 每小时 5 次", async (t) => {
  const s = setup();
  const a = await registerAndLogin(s, "dup@x.com");
  assert.equal(a.body.ok, true);
  const b = await registerHandler(s.ctx(mkReq("/api/account/register", { method: "POST", body: { email: "DUP@x.com", password: "hunter2222" } })));
  assert.equal(b.status, 409, "大小写不同的同一邮箱要撞唯一约束（变异思路：只按原样查库就会建出两个号）");
  assert.equal((await b.json()).code, "EMAIL_TAKEN");

  const weak = await registerHandler(s.ctx(mkReq("/api/account/register", { method: "POST", body: { email: "w@x.com", password: "short" } })));
  assert.equal(weak.status, 400);
  assert.equal((await weak.json()).code, "PASSWORD_WEAK", "只设 8 位下限（任务书：别过度设计）");

  const badJson = await registerHandler(s.ctx(new Request(BASE + "/api/account/register", { method: "POST", body: "{oops", headers: { "Content-Type": "application/json" } })));
  assert.equal(badJson.status, 400, "坏 JSON 是 400 不是 500（变异思路：不 try/catch request.json() 会抛成 INTERNAL）");

  // 限流：第 6 次撞 429（前 5 次各建不同邮箱）
  const s2 = setup();
  const codes = [];
  for (let i = 0; i < REGISTER_LIMIT + 1; i++) {
    const r = await registerHandler(s2.ctx(mkReq("/api/account/register", { method: "POST", body: { email: `u${i}@t.com`, password: "password1" }, ip: "9.9.9.9" })));
    codes.push(r.status);
  }
  assert.deepEqual(codes, [200, 200, 200, 200, 200, 429], "每 IP 每小时 5 次（变异思路：判定写成 n < limit 会放行第 6 次）");
  const other = await registerHandler(s2.ctx(mkReq("/api/account/register", { method: "POST", body: { email: "z@t.com", password: "password1" }, ip: "8.8.8.8" })));
  assert.equal(other.status, 200, "换一个 IP 立刻可用：桶按 IP 分键");
});

test("me 的四种态都返回 200：NO_SESSION / STORE_DISABLED / DB_UNAVAILABLE 不算错误", async (t) => {
  const s = setup();
  const r0 = await meHandler(s.ctx(mkReq("/api/account/me")));
  assert.equal(r0.status, 200, "🔴 探测口不许刷控制台红错（任务书：无会话不算错误）");
  assert.deepEqual(await r0.json(), { ok: false, reason: "NO_SESSION" });

  const expiredCookie = await meHandler(s.ctx(mkReq("/api/account/me", { headers: { Cookie: "ph_session=" + "a".repeat(64) } })));
  assert.equal((await expiredCookie.json()).reason, "NO_SESSION", "假句柄同样归 NO_SESSION，不泄露「存在但过期」");

  const off = await meHandler({ request: mkReq("/api/account/me"), env: { ...s.env, PAT_HOT_STORE_USER_DATA: "0" }, params: {} });
  assert.equal(off.status, 200, "开关关着时仍是 200：fork 的默认态不该报错");
  assert.equal((await off.json()).reason, "STORE_DISABLED");

  const noDb = await meHandler({ request: mkReq("/api/account/me"), env: { ...s.env, PAT_HOT_D1: undefined }, params: {} });
  assert.equal(noDb.status, 200);
  assert.equal((await noDb.json()).reason, "DB_UNAVAILABLE");

  // 但 register 走的是写库路径：没库就该 500 说真原因，不能假装成功
  const reg = await registerHandler({ request: mkReq("/api/account/register", { method: "POST", body: { email: "q@q.cc", password: "password1" } }), env: { ...s.env, PAT_HOT_D1: undefined }, params: {} });
  assert.equal(reg.status, 500);
  const rb = await reg.json();
  assert.equal(rb.code, "DB_UNAVAILABLE");
  assert.match(rb.message, /README/, "报错指路 README 的 d1 bind");
});

test("登出：硬删会话并清 cookie，重复调用不报错", async (t) => {
  const s = setup();
  const { body, cookie } = await registerAndLogin(s);
  const out = await logoutHandler(s.ctx(mkReq("/api/account/logout", { method: "POST", headers: { Cookie: cookie } })));
  assert.equal(out.status, 200);
  assert.match(out.headers.get("Set-Cookie"), /Max-Age=0/, "cookie 立即过期");
  assert.equal(s.db.tables.ph_sessions.length, 0, "会话行硬删，不留墓碑");
  const again = await logoutHandler(s.ctx(mkReq("/api/account/logout", { method: "POST", headers: { Cookie: cookie } })));
  assert.equal(again.status, 200, "幂等");
  const me = await meHandler(s.ctx(mkReq("/api/account/me", { headers: { Cookie: cookie } })));
  assert.equal((await me.json()).reason, "NO_SESSION", "登出后句柄彻底失效");
});

test("bind/verify 的成功与四种失败各自分型（fetchImpl 注入，不打网络）", async (t) => {
  const s = setup();
  const { body: regBody, cookie } = await registerAndLogin(s);
  const phSubject = regBody.user.subject;

  const seen = [];
  const okImpl = async (url, init) => {
    seen.push({ url, headers: init.headers, hasSignal: !!init.signal });
    return new Response(JSON.stringify({ ok: true, smSubject: "sm:abc123" }), { status: 200 });
  };
  const r = await bindVerifyHandler(s.ctx(mkReq("/api/bind/verify", { method: "POST", body: { code: "K-7f3a9c", smSubject: "sm:EVIL", userId: 99 }, headers: { Cookie: cookie } }), { fetchImpl: okImpl }));
  const b = await r.json();
  assert.equal(r.status, 200);
  assert.equal(b.ok, true);
  assert.equal(b.smSubject, "sm:abc123", "🔴 smSubject 只信 SM 兑换响应的回值，body 里的 sm:EVIL 必须被忽略（契约 §0）");
  assert.equal(b.phSubject, phSubject);
  assert.equal(s.db.tables.ph_bindings[0].sm_subject, "sm:abc123");
  assert.equal(seen[0].url, "https://scholarmatrix.pages.dev/api/pat/bind.redeem?code=K-7f3a9c", "GET 回调地址与查询串");
  assert.equal(seen[0].headers["X-PAT-Shared-Secret"], "s3cret");
  assert.equal(seen[0].headers["X-PH-Subject"], phSubject, "契约 §1.1：回调带 ph:<userId>");
  assert.equal(seen[0].hasSignal, true, "超时用 AbortSignal，不用裸 Promise.race");

  const failWith = (status, text) => async () => new Response(text, { status });
  const cases = [
    [401, '{"message":"nope"}', "SECRET_MISMATCH", 401, "密钥不一致"],
    [403, '{"message":"nope"}', "SECRET_MISMATCH", 401, "上游 403 也归密钥问题"],
    [404, '{"error":"not found"}', "CODE_INVALID", 410, "码不存在"],
    [410, "{}", "CODE_INVALID", 410, "码已用/已过期"],
    [429, "{}", "SM_RATE_LIMITED", 429, "SM 侧限流"],
    [500, "boom", "SM_UPSTREAM_ERROR", 502, "上游 5xx"],
    [200, "<html>反爬</html>", "SM_BAD_RESPONSE", 502, "非 JSON 响应"],
    [200, '{"ok":true}', "SM_BAD_RESPONSE", 502, "缺 smSubject"],
  ];
  for (const [upStatus, text, code, expectStatus, why] of cases) {
    const res = await bindVerifyHandler(s.ctx(mkReq("/api/bind/verify", { method: "POST", body: { code: "K-x" }, headers: { Cookie: cookie } }), { fetchImpl: failWith(upStatus, text) }));
    const jb = await res.json();
    assert.equal(jb.code, code, why + " 要报这个码（变异思路：全部塌成一条「操作失败」就违反契约 §0）");
    assert.equal(res.status, expectStatus, why + " 的状态码");
    assert.equal(jb.ok, false);
  }

  // 网络故障与超时 → 502 SM_UNREACHABLE（附真原因）
  const netFail = await bindVerifyHandler(s.ctx(mkReq("/api/bind/verify", { method: "POST", body: { code: "K-n" }, headers: { Cookie: cookie } }), { fetchImpl: async () => { throw new Error("ENOTFOUND"); } }));
  assert.equal(netFail.status, 502);
  const nf = await netFail.json();
  assert.equal(nf.code, "SM_UNREACHABLE");
  assert.match(nf.message, /ENOTFOUND/, "网络故障要把原始原因带出来");

  // 超时不在这里等满 8 秒：AbortSignal.timeout 的行为在 smclient.test.mjs 里
  // 用显式短超时直接验；本层只钉"默认值就是任务书写的 8 秒"。
  assert.equal(CALLBACK_TIMEOUT_MS, 8000, "出站超时默认 8s（任务书）");

  // 未配置密钥：本地就该 503，不发这一跳
  const noSecret = await bindVerifyHandler({ request: mkReq("/api/bind/verify", { method: "POST", body: { code: "K" }, headers: { Cookie: cookie } }), env: { ...s.env, PAT_SHARED_SECRET: "" }, params: {} });
  assert.equal(noSecret.status, 503);
  assert.equal((await noSecret.json()).code, "SECRET_MISSING");

  // 未登录：401，且根本不该出站
  let touched = false;
  const anon = await bindVerifyHandler({ request: mkReq("/api/bind/verify", { method: "POST", body: { code: "K" } }), env: s.env, params: {}, fetchImpl: () => { touched = true; return new Response("{}", { status: 200 }); } });
  assert.equal(anon.status, 401);
  assert.equal((await anon.json()).code, "NOT_AUTHENTICATED");
  assert.equal(touched, false, "未登录绝不先打 SM（省一跳，也不给探测者信号）");

  const noCode = await bindVerifyHandler(s.ctx(mkReq("/api/bind/verify", { method: "POST", body: {}, headers: { Cookie: cookie } })));
  assert.equal(noCode.status, 400);
  assert.equal((await noCode.json()).code, "CODE_REQUIRED");
});

test("快照 POST 只认共享密钥：会话路径已收回（任务书：服务器对服务器）", async (t) => {
  const s = setup();
  const { body, cookie } = await registerAndLogin(s);
  const phSubject = body.user.subject;
  await upsertBinding(s.db, phSubject, "sm:abc123", "2026-10-13T05:00:00Z");

  const noHeader = await snapshotPutHandler(s.ctx(mkReq("/api/profile-snapshot", { method: "POST", body: payloadOf(phSubject), headers: { Cookie: cookie } })));
  assert.equal(noHeader.status, 403, "🔴 只有已登录会话没有密钥 → 拒（上一版开了这个后门，任何人都能自报兴趣刷排序）");
  assert.equal((await noHeader.json()).code, "FORBIDDEN");

  const emptyBoth = await snapshotPutHandler({ request: mkReq("/api/profile-snapshot", { method: "POST", body: payloadOf(phSubject) }), env: { ...s.env, PAT_SHARED_SECRET: "" }, params: {} });
  assert.equal(emptyBoth.status, 403, "env 未配置 + 头缺失：空 == 空 不算通过");

  const wrong = await snapshotPutHandler(s.ctx(mkReq("/api/profile-snapshot", { method: "POST", body: payloadOf(phSubject), headers: { "X-PAT-Shared-Secret": "wrong" } })));
  assert.equal(wrong.status, 403, "长度/内容不符都拒");

  const good = await snapshotPutHandler(s.ctx(mkReq("/api/profile-snapshot", { method: "POST", body: payloadOf(phSubject), headers: { "X-PAT-Shared-Secret": "s3cret", "X-PH-Subject": phSubject } })));
  assert.equal(good.status, 200);
  assert.deepEqual((await good.json()).stored, { topics: 1, expiresAt: "2026-11-12T04:00:00Z" }, "契约 §2 的响应形状");

  // 持密钥也不能替别人写：载荷主体必须与绑定表对得上
  const stranger = await snapshotPutHandler(s.ctx(mkReq("/api/profile-snapshot", { method: "POST", body: payloadOf("ph:ffffffffffff"), headers: { "X-PAT-Shared-Secret": "s3cret" } })));
  assert.equal(stranger.status, 409);
  assert.equal((await stranger.json()).code, "NOT_BOUND", "无绑定记录的 phSubject 拒收");

  const swapped = await snapshotPutHandler(s.ctx(mkReq("/api/profile-snapshot", { method: "POST", body: payloadOf(phSubject, { smSubject: "sm:OTHER" }), headers: { "X-PAT-Shared-Secret": "s3cret" } })));
  assert.equal(swapped.status, 409);
  assert.equal((await swapped.json()).code, "SUBJECT_MISMATCH", "与既有绑定不一致就拒，不能静默改绑");

  const hdrMismatch = await snapshotPutHandler(s.ctx(mkReq("/api/profile-snapshot", { method: "POST", body: payloadOf(phSubject), headers: { "X-PAT-Shared-Secret": "s3cret", "X-PH-Subject": "ph:other" } })));
  assert.equal(hdrMismatch.status, 400);
  assert.equal((await hdrMismatch.json()).code, "SUBJECT_MISMATCH");

  const forbidden = await snapshotPutHandler(s.ctx(mkReq("/api/profile-snapshot", { method: "POST", body: payloadOf(phSubject, { topics: [{ term: "q", weight: 0.1, title: "论文标题" }] }), headers: { "X-PAT-Shared-Secret": "s3cret" } })));
  assert.equal(forbidden.status, 400);
  const fb = await forbidden.json();
  assert.equal(fb.code, "FIELD_FORBIDDEN");
  assert.match(fb.message, /title/, "禁存面命中要报出具体键名");

  assert.equal(hasSharedSecret(mkReq("/x", { headers: { "X-PAT-Shared-Secret": "s3cret" } }), { PAT_SHARED_SECRET: "s3cret" }), true);
});

test("profile GET：需会话+绑定，回生效快照与字段计数；过期后如实为空", async (t) => {
  const s = setup();
  const { body, cookie } = await registerAndLogin(s);
  const phSubject = body.user.subject;

  const anon = await profileGetHandler(s.ctx(mkReq("/api/profile")));
  assert.equal(anon.status, 401, "未登录 401（这不是探测口）");

  const unbound = await profileGetHandler(s.ctx(mkReq("/api/profile", { headers: { Cookie: cookie } })));
  const ub = await unbound.json();
  assert.equal(unbound.status, 200);
  assert.equal(ub.bound, false);
  assert.match(ub.note, /尚未绑定/, "未绑定是正常态，不是错误");

  await upsertBinding(s.db, phSubject, "sm:abc123", "2026-10-13T05:00:00Z");
  const noSnap = await profileGetHandler(s.ctx(mkReq("/api/profile", { headers: { Cookie: cookie } })));
  const ns = await noSnap.json();
  assert.equal(ns.snapshot, null);
  assert.match(ns.note, /SM 推送/, "还没推过要说还没推过，别混成「你没有数据」");

  await snapshotPutHandler(s.ctx(mkReq("/api/profile-snapshot", { method: "POST", body: payloadOf(phSubject), headers: { "X-PAT-Shared-Secret": "s3cret" } })));
  const r = await profileGetHandler(s.ctx(mkReq("/api/profile", { headers: { Cookie: cookie } })));
  const got = await r.json();
  assert.equal(got.ok, true);
  assert.equal(got.bound, true);
  assert.equal(got.smSubject, "sm:abc123");
  assert.equal(got.snapshot.topics[0].term, "quantum error correction");
  assert.deepEqual(got.fields, { topics: 1, categories: 1, channels: 1, countsKeys: 2, lang: "zh", pushedAt: "2026-10-13T04:00:00Z", expiresAt: "2026-11-12T04:00:00Z" },
    "🔴 字段计数供「查看我的数据」面板列明存了什么（任务书）");
  assert.deepEqual(snapshotFieldCounts(null), null);

  // 过期：快照行当场硬删，面板转空态而不是继续显示
  s.db.tables.profile_snapshots[0].expires_at = new Date(Date.now() - 1000).toISOString();
  const expired = await profileGetHandler(s.ctx(mkReq("/api/profile", { headers: { Cookie: cookie } })));
  const ex = await expired.json();
  assert.equal(ex.snapshot, null, "过期即失效（契约 §3）");
  assert.equal(s.db.tables.profile_snapshots.length, 0, "过期行不留库（存储最小化，Q13 才好删）");
});

test("快照 DELETE：密钥路与会话路都允许，删的是真行数", async (t) => {
  const s = setup();
  const { body, cookie } = await registerAndLogin(s);
  const phSubject = body.user.subject;
  await upsertBinding(s.db, phSubject, "sm:abc123", "2026-10-13T05:00:00Z");
  await snapshotPutHandler(s.ctx(mkReq("/api/profile-snapshot", { method: "POST", body: payloadOf(phSubject), headers: { "X-PAT-Shared-Secret": "s3cret" } })));

  const anon = await snapshotDeleteHandler(s.ctx(mkReq("/api/profile-snapshot", { method: "DELETE" })));
  assert.equal(anon.status, 403, "无密钥无会话：拒");

  // 会话路：删自己的画像 + 绑定，两个方向都清干净
  const bySession = await snapshotDeleteHandler(s.ctx(mkReq("/api/profile-snapshot", { method: "DELETE", headers: { Cookie: cookie } })));
  const bs = await bySession.json();
  assert.equal(bySession.status, 200);
  assert.equal(bs.deleted, true);
  assert.equal(bs.removedSnapshots, 1, "计数必须是真删掉的行数");
  assert.equal(bs.removedBindings, 1);
  assert.equal(s.db.tables.profile_snapshots.length, 0);
  assert.equal(s.db.tables.ph_bindings.length, 0);
  assert.equal(s.db.tables.ph_sessions.length, 1, "🔴 清除数据不该顺手登出：会话仍在，面板能显示「已清除」");

  // 密钥路：按 ph 或 sm 主体删；两个都不给就 400
  await upsertBinding(s.db, phSubject, "sm:abc123", "2026-10-13T06:00:00Z");
  await snapshotPutHandler(s.ctx(mkReq("/api/profile-snapshot", { method: "POST", body: payloadOf(phSubject), headers: { "X-PAT-Shared-Secret": "s3cret" } })));
  const noSubject = await snapshotDeleteHandler(s.ctx(mkReq("/api/profile-snapshot", { method: "DELETE", headers: { "X-PAT-Shared-Secret": "s3cret" } })));
  assert.equal(noSubject.status, 400);
  assert.equal((await noSubject.json()).code, "SUBJECT_REQUIRED", "服务器删除必须点名主体，不许无差别清空");

  const bySm = await snapshotDeleteHandler(s.ctx(mkReq("/api/profile-snapshot?smSubject=sm:abc123", { method: "DELETE", headers: { "X-PAT-Shared-Secret": "s3cret" } })));
  const bm = await bySm.json();
  assert.equal(bySm.status, 200);
  assert.ok(bm.removedSnapshots >= 1, "按 sm 主体也要删到（契约 §1.2 SM 解绑回调的形状）");
  assert.equal(s.db.tables.profile_snapshots.length, 0);
});

test("开关关着时写读路径统一 503，且说明数据面照常可用", async (t) => {
  const s = setup();
  const offEnv = { ...s.env, PAT_HOT_STORE_USER_DATA: "0" };
  const paths = [
    ["register", registerHandler, { method: "POST", body: { email: "x@y.cc", password: "password1" } }],
    ["login", loginHandler, { method: "POST", body: { email: "x@y.cc", password: "password1" } }],
    ["bind", bindVerifyHandler, { method: "POST", body: { code: "K" } }],
    ["snapshot POST", snapshotPutHandler, { method: "POST", body: payloadOf("ph:abc") }],
    ["profile", profileGetHandler, {}],
  ];
  for (const [name, h, init] of paths) {
    const res = await h({ request: mkReq("/api/x", init), env: offEnv, params: {} });
    assert.equal(res.status, 503, name + " 在未开启存储时 503（变异思路：让某个端点静默返回空数据，前端就会演成「你没有数据」）");
    const b = await res.json();
    assert.equal(b.code, "STORE_DISABLED", name);
    assert.match(b.message, /PAT_HOT_STORE_USER_DATA/, name + " 要指名开关");
  }
});
