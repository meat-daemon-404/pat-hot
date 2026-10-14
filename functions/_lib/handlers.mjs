/**
 * 身份与画像后端的处理器（路由文件只做"原样再导出"，逻辑全在这里，
 * 因此 node --test 测的就是线上跑的本体，不是副本）。
 *
 * 三条贯穿全部处理器的红线：
 *  1. 身份只从 ph_session cookie 解析出的会话取；body/query 里任何
 *     userId / smSubject 之类的"我是谁"字段一律不采信（契约 §0）。
 *  2. 失败响应一律 {ok:false, code, message}，message 说真原因。
 *  3. 用户数据面受 PAT_HOT_STORE_USER_DATA 开关；关着的时候这些端点
 *     明确 503，而不是假装"你没有数据"。
 */

import {
  fail, ok, json, readJsonBody, cookieHandle, sessionCookieValue, withSetCookie,
  clientIp, originOf, hostOf, isHttps, storeEnabled, storeDisabledResponse, optionsResponse,
} from "./http.mjs";
import {
  pwHash, pwVerify, newUserId, checkPasswordShape, normalizeEmail, secretEqual,
} from "./crypto.mjs";
import { validateSnapshotPayload } from "./snapshot.mjs";
import {
  ensureSchema, requireDb, DbUnavailable,
  findUserByEmail, findUserById, insertUser, createSession, resolveSession, deleteSession,
  getBinding, upsertBinding, deleteBinding, putProfile, getActiveProfile,
  selectProfilesByPh, selectProfileBySm, deleteProfilesByPh, deleteProfileBySm,
  consumeRate, phSubjectOf,
  SESSION_TTL_MS,
} from "./db.mjs";
import { redeemBindCode, notifySmUnbind, SmCallError } from "./smclient.mjs";
import { snapshotActive } from "./ranking.mjs";

export const REGISTER_WINDOW_MS = 3600 * 1000;
export const REGISTER_LIMIT = 5; // 每 IP 每小时 5 次注册尝试（任务书）
export const LOGIN_WINDOW_MS = 15 * 60 * 1000;
export const LOGIN_LIMIT = 20; // 每 IP 每 15 分钟：挡口令爆破，正常用户撞不到

/** D1 不可用：说真原因，别让前端拿到"空数据"去猜。 */
function dbDown(origin, host, e) {
  return fail("DB_UNAVAILABLE", "后端数据库不可用：" + String((e && e.message) || e).slice(0, 200), 500, origin, host);
}

function unexpected(origin, host, e) {
  return fail("INTERNAL", "服务端异常：" + String((e && e.message) || e).slice(0, 200), 500, origin, host);
}

/**
 * 统一的入口封装：开关检查 → 取 D1 → 建表探针 → 进 handler。
 * handler 返回 Response 就原样发出（多数是失败响应），
 * 返回 { session, ... } 由具体处理器继续。
 */
async function withBackend(context, handler, { needStore = true, needDb = true } = {}) {
  const { request, env } = context;
  const origin = originOf(request);
  const host = hostOf(request);
  if (needStore && !storeEnabled(env)) return storeDisabledResponse(origin, host);
  let db = null;
  if (needDb) {
    try {
      db = requireDb(env);
    } catch (e) {
      return dbDown(origin, host, e);
    }
    try {
      await ensureSchema(db);
    } catch (e) {
      return dbDown(origin, host, e);
    }
  }
  try {
    return await handler({ request, env, db, origin, host });
  } catch (e) {
    if (e instanceof DbUnavailable) return dbDown(origin, host, e);
    if (e instanceof SmCallError) {
      // 状态与机器码由 smclient 按契约逐条定好（401 SECRET_MISMATCH /
      // 410 CODE_INVALID / 502 SM_UNREACHABLE / 503 SECRET_MISSING），
      // 这里只如实透出，不在第二处重新猜一遍——两处猜必然漂移。
      const status = Number.isFinite(e.status) && e.status >= 400 && e.status <= 599 ? e.status : 502;
      return fail(e.code, e.message, status, origin, host);
    }
    return unexpected(origin, host, e);
  }
}

/** 会话 → { user, phSubject }；无有效会话返回 null（只认 cookie）。 */
async function sessionUser(db, request, nowMs = Date.now()) {
  const handle = cookieHandle(request);
  if (!handle) return null;
  const s = await resolveSession(db, handle, nowMs);
  if (!s) return null;
  return { session: s, userId: s.userId, phSubject: phSubjectOf(s.userId) };
}

/**
 * 服务器侧调用判定：X-PAT-Shared-Secret 与 PAT_SHARED_SECRET 相等。
 * 未配置密钥时永不为真（空 == 空 不算通过）。
 */
export function hasSharedSecret(request, env) {
  const got = request.headers.get("X-PAT-Shared-Secret") || "";
  return secretEqual(got, env && env.PAT_SHARED_SECRET);
}

/**
 * 对外只回非秘密字段。
 * （上一版读 u.email，而两条 SELECT 回来的列名是 email_lc，
 *   JSON.stringify 把 undefined 直接丢掉，前端拿到的 user 里根本没有 email，
 *   注册页"你当前的账号"就永远是空的。这里按真实列名读并写明。）
 */
function publicUser(u) {
  return {
    id: u.id,
    subject: phSubjectOf(u.id),
    email: u.email_lc || u.emailLc || null,
    createdAt: u.created_at || null,
  };
}

/** 快照的字段计数：给前端"查看/清除我的数据"面板列明存了什么、各几项。 */
export function snapshotFieldCounts(snap) {
  if (!snap) return null;
  return {
    topics: Array.isArray(snap.topics) ? snap.topics.length : 0,
    categories: Array.isArray(snap.categories) ? snap.categories.length : 0,
    channels: Array.isArray(snap.channels) ? snap.channels.length : 0,
    countsKeys: snap.counts && typeof snap.counts === "object" ? Object.keys(snap.counts).length : 0,
    lang: snap.lang || null,
    pushedAt: snap.pushedAt || null,
    expiresAt: snap.expiresAt || null,
  };
}

// ---------------- POST /api/account/register ----------------

export const registerHandler = (context) => withBackend(context, async ({ request, env, db, origin, host }) => {
  const ip = clientIp(request);
  const bucket = await consumeRate(db, "register:" + ip, REGISTER_LIMIT, REGISTER_WINDOW_MS);
  if (!bucket.allow) {
    return fail("RATE_LIMITED",
      "注册尝试过多（每 IP 每小时 " + REGISTER_LIMIT + " 次），请 " + bucket.retryAfterSec + " 秒后再试",
      429, origin, host);
  }

  const body = await readJsonBody(request);
  if (!body.ok) return fail(body.code, body.message, 400, origin, host);
  // 身份不取自请求体：这里连读都不读 body.userId，注册只认 email+password。
  const em = normalizeEmail(body.value.email);
  if (!em.ok) return fail(em.code, em.message, 400, origin, host);
  const pw = checkPasswordShape(body.value.password);
  if (!pw.ok) return fail(pw.code, pw.message, 400, origin, host);

  if (await findUserByEmail(db, em.value)) {
    return fail("EMAIL_TAKEN", "该邮箱已注册，请直接登录", 409, origin, host);
  }

  const id = newUserId();
  const now = Date.now();
  const createdAt = new Date(now).toISOString();
  const hash = await pwHash(pw.value);
  try {
    await insertUser(db, { id, emailLc: em.value, pwHash: hash, createdAt });
  } catch (e) {
    const msg = String((e && e.message) || e);
    if (/UNIQUE|constraint/i.test(msg)) {
      return fail("EMAIL_TAKEN", "该邮箱已注册（并发创建撞上唯一约束），请直接登录", 409, origin, host);
    }
    throw e;
  }

  const sess = await createSession(db, id, now);
  const res = ok({
    user: { id, subject: phSubjectOf(id), email: em.value, createdAt },
    session: { expiresAt: sess.expiresAt },
    bound: false,
  }, origin, host);
  return withSetCookie(res, sessionCookieValue(sess.handle, {
    maxAgeSec: Math.floor(SESSION_TTL_MS / 1000),
    secure: isHttps(request),
  }));
});

// ---------------- POST /api/account/login ----------------

export const loginHandler = (context) => withBackend(context, async ({ request, db, origin, host }) => {
  const ip = clientIp(request);
  const bucket = await consumeRate(db, "login:" + ip, LOGIN_LIMIT, LOGIN_WINDOW_MS);
  if (!bucket.allow) {
    return fail("RATE_LIMITED", "登录尝试过多（每 IP 15 分钟 " + LOGIN_LIMIT + " 次），请 "
      + bucket.retryAfterSec + " 秒后再试", 429, origin, host);
  }

  const body = await readJsonBody(request);
  if (!body.ok) return fail(body.code, body.message, 400, origin, host);
  const em = normalizeEmail(body.value.email);
  if (!em.ok) return fail(em.code, em.message, 400, origin, host);
  const pw = checkPasswordShape(body.value.password);
  if (!pw.ok) return fail(pw.code, pw.message, 400, origin, host);

  const user = await findUserByEmail(db, em.value);
  // 邮箱不存在与密码错共用同一个 code/message：不给账号枚举留口子。
  if (!user || !(await pwVerify(pw.value, user.pw_hash))) {
    return fail("BAD_CREDENTIALS", "邮箱或密码不正确", 401, origin, host);
  }

  const now = Date.now();
  const sess = await createSession(db, user.id, now);
  const binding = await getBinding(db, phSubjectOf(user.id));
  const res = ok({
    user: publicUser(user),
    session: { expiresAt: sess.expiresAt },
    bound: !!binding,
  }, origin, host);
  return withSetCookie(res, sessionCookieValue(sess.handle, {
    maxAgeSec: Math.floor(SESSION_TTL_MS / 1000),
    secure: isHttps(request),
  }));
});

// ---------------- POST /api/account/logout ----------------

export const logoutHandler = (context) => withBackend(context, async ({ request, db, origin, host }) => {
  const handle = cookieHandle(request);
  if (handle) await deleteSession(db, handle);
  // 无论会话是否存在都清 cookie：幂等，重复调用不报错。
  const res = ok({ loggedOut: true }, origin, host);
  return withSetCookie(res, sessionCookieValue("", { maxAgeSec: 0, secure: isHttps(request) }));
});

// ---------------- GET /api/account/me ----------------

/**
 * 前端探测用（任务书：无会话不算错误）。上一版返回 401 NOT_AUTHENTICATED，
 * 浏览器控制台会把每次"未登录探测"记成一条网络错误，而且前端要 try/catch
 * 一个正常的业务态——现在按契约返回 200 {ok:false,reason:"NO_SESSION"}。
 *
 * 探测口的纪律：**任何"没有会话"的成因都回 200 + 说清 reason**，
 * 连"数据面开关没开 / D1 没绑"也算——站点在 fork 默认（零后端）下仍要
 * 能安静地探测出"当前没人登录"，而不是每次首屏都甩一条红错进控制台。
 * reason 分型照实：NO_SESSION / STORE_DISABLED / DB_UNAVAILABLE，
 * 前端据此决定是提示登录，还是提示"本站未开启账号面"。
 */
export const meHandler = (context) => withBackend(context, async ({ request, env, db, origin, host }) => {
  if (!storeEnabled(env)) {
    return json({ ok: false, reason: "STORE_DISABLED" }, 200, origin, host);
  }
  let live = db;
  try {
    if (!live) live = requireDb(env);
    await ensureSchema(live);
  } catch (e) {
    return json({ ok: false, reason: "DB_UNAVAILABLE" }, 200, origin, host);
  }
  const u = await sessionUser(live, request);
  if (!u) return json({ ok: false, reason: "NO_SESSION" }, 200, origin, host);
  const user = await findUserById(live, u.userId);
  if (!user) {
    // 会话指向已删除的用户（解绑即清/删号之后）：把会话也硬删，别留幽灵。
    await deleteSession(live, cookieHandle(request));
    return json({ ok: false, reason: "NO_SESSION", note: "账号不存在，会话已清除，请重新注册或登录" }, 200, origin, host);
  }
  const binding = await getBinding(live, u.phSubject);
  const snapshots = binding ? await getActiveProfile(live, binding.sm_subject) : [];
  return ok({
    user: publicUser(user),
    bound: !!binding,
    smSubject: binding ? binding.sm_subject : null,
    hasSnapshot: snapshots.length > 0,
    // 前端拿这个决定要不要再请求 /api/profile（少一次往返，也不多一次）
    snapshot: snapshots.length ? snapshots[0].payload : null,
  }, origin, host);
}, { needStore: false, needDb: false });

// ---------------- POST /api/bind/verify ----------------

export const bindVerifyHandler = (context) => withBackend(context, async ({ request, env, db, origin, host }) => {
  const u = await sessionUser(db, request);
  if (!u) return fail("NOT_AUTHENTICATED", "需要先在本站登录后再绑定：绑定关系挂在本地账号上", 401, origin, host);

  const body = await readJsonBody(request);
  if (!body.ok) return fail(body.code, body.message, 400, origin, host);
  const code = String(body.value.code || "").trim();
  if (!code) return fail("CODE_REQUIRED", "缺少绑定码 code（在 SM 侧「绑定 PAT-HOT」生成）", 400, origin, host);
  if (code.length > 128) return fail("CODE_INVALID", "绑定码过长", 400, origin, host);
  // 🔴 body 里若带 smSubject/phSubject/userId 一律忽略：phSubject 由会话推出，
  // smSubject 只信 SM 兑换响应的回值（契约 §1.1）。

  // context.fetchImpl 只在本仓测试里注入（Pages 的 context 没有这个属性，
  // 生产路径恒为 undefined → smclient 用全局 fetch）。不为测试另开一条代码分支。
  const redeemed = await redeemBindCode(env, { code, phSubject: u.phSubject, fetchImpl: context.fetchImpl });
  const nowIso = new Date().toISOString();
  await upsertBinding(db, u.phSubject, redeemed.smSubject, nowIso);

  // SM 的兑换响应可以顺带带回快照（契约 §1.1 示例）：有就按 §2 同一条校验路径入库。
  let profileStored = null;
  let profileNote = null;
  if (redeemed.profile) {
    const payload = Object.assign({}, redeemed.profile);
    payload.smSubject = redeemed.smSubject;
    payload.phSubject = u.phSubject;
    const v = validateSnapshotPayload(payload, { nowMs: Date.now() });
    if (v.ok) {
      await putProfile(db, v.value, nowIso);
      profileStored = { topics: v.value.topics.length, expiresAt: v.value.expiresAt };
    } else {
      // 绑定已经成立，快照不合规只是没存下来说清楚，不骗用户"画像也同步好了"。
      profileNote = v.code + "：" + v.message;
    }
  }

  return ok({
    bound: true,
    phSubject: u.phSubject,
    smSubject: redeemed.smSubject,
    profileStored,
    profileNote,
  }, origin, host);
});

// ---------------- POST /api/bind/unbind ----------------

export const bindUnbindHandler = (context) => withBackend(context, async ({ request, env, db, origin, host }) => {
  const u = await sessionUser(db, request);
  if (!u) return fail("NOT_AUTHENTICATED", "未登录", 401, origin, host);
  const binding = await getBinding(db, u.phSubject);
  if (!binding) return ok({ unbound: false, note: "当前账号没有绑定关系" }, origin, host);

  // 解绑即硬删（契约 §1.2）：快照与绑定行一起消失，不留墓碑。
  const profiles = await getActiveProfile(db, binding.sm_subject);
  await deleteProfilesByPh(db, u.phSubject);
  await deleteProfileBySm(db, binding.sm_subject);
  await deleteBinding(db, u.phSubject);

  let notify = { ok: true };
  try {
    notify = await notifySmUnbind(env, { phSubject: u.phSubject, fetchImpl: context.fetchImpl });
  } catch (e) {
    notify = { ok: false, code: e instanceof SmCallError ? e.code : "SM_NOTIFY_FAILED", message: String((e && e.message) || e).slice(0, 200) };
  }
  return ok({
    unbound: true,
    removedSnapshots: profiles.length,
    smNotified: notify.ok,
    // 本地已经删干净；SM 侧没通知到时会把下一次推送撞进 PH 的"未绑定"拒收，
    // 这里如实告诉调用方，不假装成功。
    smNotifyNote: notify.ok ? null : (notify.code + "：" + (notify.message || "")),
  }, origin, host);
});

// ---------------- POST /api/profile-snapshot ----------------

/**
 * 严格服务器对服务器（任务书口径）：POST 只认 X-PAT-Shared-Secret，
 * 头缺失 / env 未配置 / 两边皆空——一律 403，不开"已登录会话也能写画像"的后门。
 * 快照是 SM 侧算出来的权威画像；若允许浏览器直接 POST 自报主题词，
 * 任何人都能伪造兴趣来刷本站排序，"按你的研究兴趣排序"这句话就失去意义。
 * （DELETE 才两条路都走——「清除我的数据」必须由本人会话发起，见下。）
 */
export const snapshotPutHandler = (context) => withBackend(context, async ({ request, env, db, origin, host }) => {
  if (!hasSharedSecret(request, env)) {
    return fail("FORBIDDEN",
      "画像快照只接受 SM 服务器回调（请求头 X-PAT-Shared-Secret）。"
      + "想看自己存了什么请用 GET /api/profile，想清除请用 DELETE。",
      403, origin, host);
  }

  const body = await readJsonBody(request);
  if (!body.ok) return fail(body.code, body.message, 400, origin, host);

  const v = validateSnapshotPayload(body.value, { nowMs: Date.now() });
  if (!v.ok) return fail(v.code, v.message, 400, origin, host); // FIELD_FORBIDDEN / EXPIRES_* 等全在这里落地
  const snap = v.value;

  // 主体一致性：持密钥也不能替别人写快照——载荷的两个主体必须与绑定表对得上。
  const hdrPh = request.headers.get("X-PH-Subject") || "";
  if (hdrPh && hdrPh !== snap.phSubject) {
    return fail("SUBJECT_MISMATCH", "X-PH-Subject（" + hdrPh + "）与载荷 phSubject（"
      + snap.phSubject + "）不一致", 400, origin, host);
  }
  const binding = await getBinding(db, snap.phSubject);
  if (!binding) {
    return fail("NOT_BOUND", "phSubject 没有绑定记录，拒收（先走 /api/bind/verify）：" + snap.phSubject, 409, origin, host);
  }
  if (binding.sm_subject !== snap.smSubject) {
    return fail("SUBJECT_MISMATCH", "该 phSubject 已绑定 " + binding.sm_subject + "，与载荷 smSubject "
      + snap.smSubject + " 不一致（可能已换绑，让 SM 重新绑定）", 409, origin, host);
  }

  await putProfile(db, snap, new Date().toISOString());
  return ok({ stored: { topics: snap.topics.length, expiresAt: snap.expiresAt } }, origin, host);
});

// ---------------- DELETE /api/profile-snapshot ----------------

export const snapshotDeleteHandler = (context) => withBackend(context, async ({ request, env, db, origin, host }) => {
  const byServer = hasSharedSecret(request, env);
  let phSubject = "";
  let smSubject = "";

  if (byServer) {
    // SM 侧解绑回调：DELETE ?phSubject=ph:<id>（契约 §1.2 的 PH 端点形状）
    const url = new URL(request.url);
    phSubject = url.searchParams.get("phSubject") || request.headers.get("X-PH-Subject") || "";
    smSubject = url.searchParams.get("smSubject") || "";
    if (!phSubject && !smSubject) {
      return fail("SUBJECT_REQUIRED", "服务器删除需要 phSubject 或 smSubject 之一", 400, origin, host);
    }
  } else {
    const u = await sessionUser(db, request);
    if (!u) return fail("FORBIDDEN", "删除画像需要 SM 服务器密钥或已登录会话", 403, origin, host);
    phSubject = u.phSubject;
    const binding = await getBinding(db, phSubject);
    if (binding) smSubject = binding.sm_subject;
  }

  let removedSnapshots = 0;
  let removedBindings = 0;
  // 先查后删：返回的计数必须是"真的删了几行"，不能是"打算删几类"。
  const phSet = new Set();
  const smSet = new Set();
  if (smSubject) {
    const row = await selectProfileBySm(db, smSubject);
    if (row) { smSet.add(row.sm_subject); if (row.ph_subject) phSet.add(row.ph_subject); }
    smSet.add(smSubject);
  }
  if (phSubject) {
    phSet.add(phSubject);
    const rows = await selectProfilesByPh(db, phSubject);
    for (const r of rows) if (r.sm_subject) smSet.add(r.sm_subject);
  }
  for (const ph of phSet) {
    const n = await deleteProfilesByPh(db, ph);
    removedSnapshots += n;
    if (await deleteBinding(db, ph)) removedBindings += 1;
  }
  for (const sm of smSet) {
    const n = await deleteProfileBySm(db, sm);
    removedSnapshots += n;
  }
  // 会话侧请求还顺手清掉自己的会话吗？不清：面板上"清除我的数据"之后用户
  // 仍应能看到"已清除"的界面，把登出留给显式的 /api/account/logout。
  return ok({
    deleted: true,
    removedSnapshots,
    removedBindings,
    phSubject: phSubject || null,
    smSubject: smSubject || null,
  }, origin, host);
});

// ---------------- GET /api/profile ----------------

/**
 * 前端「查看 / 清除我的数据」面板的数据源（任务书）：返回当前**生效**快照
 * + 字段计数。生效判定走 ranking.snapshotActive（契约 §3 的过期即失效口径），
 * 与前端渲染用的是同一个函数——面板说"还在生效"而列表不按它排序，
 * 或者反过来，都是用户能直接看见的不一致。
 */
export const profileGetHandler = (context) => withBackend(context, async ({ request, db, origin, host }) => {
  const u = await sessionUser(db, request);
  if (!u) return fail("NOT_AUTHENTICATED", "未登录", 401, origin, host);
  const binding = await getBinding(db, u.phSubject);
  if (!binding) return ok({ bound: false, snapshot: null, note: "尚未绑定 ScholarMatrix" }, origin, host);
  const rows = await getActiveProfile(db, binding.sm_subject);
  // getActiveProfile 已经硬删过期行；这里再按 snapshotActive 复核一次，
  // 保证"面板显示的生效性"与"前端重排的生效性"用的是同一句判定。
  const active = rows.filter((r) => snapshotActive({ expiresAt: r.expiresAt }));
  if (!active.length) {
    return ok({ bound: true, smSubject: binding.sm_subject, snapshot: null, fields: null,
      note: "尚无生效画像（SM 推送后自动出现）" }, origin, host);
  }
  const snap = active[0].payload;
  return ok({
    bound: true,
    smSubject: binding.sm_subject,
    phSubject: u.phSubject,
    snapshot: snap,
    fields: snapshotFieldCounts(snap),
  }, origin, host);
});

// ---------------- OPTIONS 预检 ----------------

export function handleOptions(context) {
  return optionsResponse(originOf(context.request), hostOf(context.request));
}
