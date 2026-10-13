/**
 * PH → SM 的服务器回调客户端（契约 §1.1 / §1.2）。
 *
 * 失败必须说真原因，四种不能混成一种（契约 §0）：
 *   网络故障 / 超时 / 403 密钥不对 / 410 码已用或过期 / 上游 5xx。
 * 错误对象带 machine code，路由直接翻译成响应体的 code 字段。
 *
 * 超时 8s：任务书定的上限（Pages Function 单次约 30s 墙上时钟，
 * 留足余量给后续 D1 写入）。AbortController 不用裸 Promise.race——
 * 后者不会真的取消请求，SM 慢的时候照样占着 isolate。
 */

export const SM_BASE_DEFAULT = "https://scholarmatrix.pages.dev";
export const CALLBACK_TIMEOUT_MS = 8000;

export class SmCallError extends Error {
  /** @param {string} code 机器码（如 SM_UNREACHABLE / SM_SECRET_FORBIDDEN / CODE_USED） */
  constructor(code, message, { status = 0, detail = "" } = {}) {
    super(message);
    this.name = "SmCallError";
    this.code = code;
    this.status = status;
    this.detail = String(detail || "").slice(0, 200);
  }
}

/**
 * SM_BASE 只允许 https 且主机在白名单内。
 * 为什么硬校验主机：环境变量是最容易被人误填成 http://localhost 或
 * 带路径/查询的东西，而这一跳带的是共享密钥——密钥泄露给任意
 * host 就是事故。契约 §7 明确"代码里仍硬校验主机"。
 */
export function resolveSmBaseUrl(env) {
  const raw = String((env && env.SM_BASE) || SM_BASE_DEFAULT).trim();
  let u;
  try { u = new URL(raw); } catch (e) {
    throw new SmCallError("SM_BASE_INVALID", "SM_BASE 不是合法 URL：" + raw.slice(0, 80));
  }
  if (u.protocol !== "https:") {
    throw new SmCallError("SM_BASE_INVALID", "SM_BASE 必须是 https，收到 " + u.protocol + "//" + u.host);
  }
  const host = u.hostname.toLowerCase();
  const allowed = /(^|\.)pages\.dev$/i.test(host) || /(^|\.)workers\.dev$/i.test(host)
    || host === "localhost" || host === "127.0.0.1";
  if (!allowed) {
    throw new SmCallError("SM_BASE_NOT_ALLOWED", "SM_BASE 主机不在白名单（pages.dev/workers.dev/本地调试）：" + host);
  }
  if (u.pathname !== "/" && u.pathname !== "") {
    throw new SmCallError("SM_BASE_INVALID", "SM_BASE 只能到主机根，不要带路径：" + raw.slice(0, 80));
  }
  return u.origin;
}

export async function smFetch(base, pathWithQuery, { secret, phSubject, method = "GET", timeoutMs = CALLBACK_TIMEOUT_MS, fetchImpl } = {}) {
  const secretStr = String(secret == null ? "" : secret);
  // 只判空串不够：Pages 环境变量误配成空白（复制粘贴带个空格）时长得跟真密钥
  // 一样能过 truthy 检查。
  if (!secretStr.trim()) {
    throw new SmCallError("SECRET_MISSING", "未配置 PAT_SHARED_SECRET，无法回调 SM（Pages 环境变量里加 Secret）", { status: 503 });
  }
  // 首尾有空格的密钥就地拒绝，而不是照样发出去：这一跳要求两端逐字相等，
  // 带着空格出门只会换来"SM 一直回 401"这种最难查的症状——真原因在配置里，
  // 就该在配置这一步说出来。（中间的空格不动：那可能是密钥本身的内容。）
  if (secretStr !== secretStr.trim()) {
    throw new SmCallError("SECRET_MISSING",
      "PAT_SHARED_SECRET 首尾含空白字符（多半是复制粘贴带进来的），已就地拒绝发送。"
      + "请在 Pages 环境变量里重设不带空白的值。", { status: 503 });
  }
  const headers = { "X-PAT-Shared-Secret": secretStr, Accept: "application/json" };
  if (phSubject) headers["X-PH-Subject"] = phSubject;
  const doFetch = fetchImpl || fetch;
  // 超时用 AbortSignal.timeout（任务书指定）：真的取消请求，不像裸 Promise.race
  // 那样"响应被丢弃但连接还占着 isolate"。CF Workers 与 Node 18+ 都有；
  // 万一运行环境缺这个静态方法，退回手写 controller，行为一致。
  let signal = null;
  let fallbackCtrl = null;
  let fallbackTimer = null;
  if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
    signal = AbortSignal.timeout(timeoutMs);
  } else {
    fallbackCtrl = new AbortController();
    fallbackTimer = setTimeout(() => fallbackCtrl.abort(), timeoutMs);
    signal = fallbackCtrl.signal;
  }
  let resp;
  try {
    resp = await doFetch(base + pathWithQuery, { method, headers, signal, redirect: "manual" });
  } catch (e) {
    const msg = String((e && e.message) || e).slice(0, 160);
    // 超时判定看 signal 本身：CF/Node 在超时抛出的 name 不一致
    // （TimeoutError / AbortError），认名字会漏。
    if (signal.aborted) {
      throw new SmCallError("SM_TIMEOUT", "回调 SM 超时（>" + Math.round(timeoutMs / 1000) + "s）：" + msg);
    }
    throw new SmCallError("SM_UNREACHABLE", "回调 SM 网络故障（DNS/连接/TLS）：" + msg);
  } finally {
    if (fallbackTimer) clearTimeout(fallbackTimer);
  }

  const status = resp.status;
  let body = null;
  const text = await resp.text().catch(() => "");
  if (text) {
    try { body = JSON.parse(text); } catch (e) { body = null; }
  }
  return { status, body, text };
}

/** 从 SM 的响应里挑一句人能读的原因（没有就回落到状态码本身）。 */
function smMessage(res, fallback) {
  const b = res && res.body;
  if (b && typeof b === "object") {
    const m = b.message || b.error || b.detail;
    if (typeof m === "string" && m.trim()) return m.trim().slice(0, 200);
  }
  return fallback;
}

/**
 * 兑换一次性绑定码（契约 §1.1 ②）。
 * @returns {{smSubject:string, profile?:object}}
 */
/**
 * 上游状态 → 对客户端的状态与机器码映射，逐条对齐任务书
 * （401 SECRET_MISMATCH / 410 CODE_INVALID / 502 SM_UNREACHABLE 附原因 / 503 STORE_DISABLED）：
 * 这里定好 SmCallError.status，路由层只如实透出，不再二次猜。
 * 404 与 410 归同一类 CODE_INVALID（"这个码不能用"），但 message 里说清
 * 上游到底是 404 还是 410——分类给机器，真原因给人。
 */
export async function redeemBindCode(env, { code, phSubject, fetchImpl } = {}) {
  const base = resolveSmBaseUrl(env);
  const secret = env && env.PAT_SHARED_SECRET;
  const q = "/api/pat/bind.redeem?code=" + encodeURIComponent(String(code || ""));
  let res;
  try {
    res = await smFetch(base, q, { secret, phSubject, fetchImpl });
  } catch (e) {
    // 网络故障与超时都归 502 SM_UNREACHABLE（附真原因）。SM_TIMEOUT 不另立门户：
    // 对前端而言两者同样是"这一跳没走通"，细分在 message 里保留。
    if (e instanceof SmCallError && (e.code === "SM_UNREACHABLE" || e.code === "SM_TIMEOUT")) {
      throw new SmCallError("SM_UNREACHABLE", e.message, { status: 502 });
    }
    throw e; // SECRET_MISSING / SM_BASE_* 是本地配置问题，原样（503/502）透出
  }

  if (res.status === 401 || res.status === 403) {
    throw new SmCallError("SECRET_MISMATCH",
      "SM 拒绝共享密钥（上游 " + res.status + "）：两端 PAT_SHARED_SECRET 不一致或未配置。" + smMessage(res, ""),
      { status: 401, detail: res.text });
  }
  if (res.status === 404 || res.status === 410) {
    throw new SmCallError("CODE_INVALID",
      (res.status === 410 ? "绑定码已使用或已过期（上游 410）" : "绑定码不存在（上游 404）") + "。回 SM 重新发起绑定（bind.begin）拿新码。"
      + smMessage(res, ""),
      { status: 410, detail: res.text });
  }
  if (res.status === 429) {
    throw new SmCallError("SM_RATE_LIMITED", "SM 侧限流（429）：稍后再试。" + smMessage(res, ""), { status: 429, detail: res.text });
  }
  if (!res.status || res.status >= 400) {
    throw new SmCallError("SM_UPSTREAM_ERROR", "SM 返回 " + res.status + "。" + smMessage(res, ""),
      { status: 502, detail: res.text });
  }
  if (!res.body) {
    throw new SmCallError("SM_BAD_RESPONSE", "SM 兑换响应不是合法 JSON（可能被反爬或网关拦下）",
      { status: 502, detail: res.text });
  }
  if (res.body.ok === false) {
    throw new SmCallError("SM_REDEEM_REJECTED", "SM 拒绝兑换：" + smMessage(res, JSON.stringify(res.body).slice(0, 160)),
      { status: 502, detail: res.text });
  }
  const smSubject = res.body.smSubject || (res.body.profile && res.body.profile.smSubject);
  if (typeof smSubject !== "string" || !/^(sm|wx):[A-Za-z0-9_.:-]+$/.test(smSubject)) {
    throw new SmCallError("SM_BAD_RESPONSE", "SM 响应缺少合法 smSubject（契约 §1 要求 sm:/wx: 前缀）",
      { status: 502, detail: res.text });
  }
  return { smSubject, profile: res.body.profile || null };
}

/**
 * 反向解绑通知（契约 §1.2）：PH 侧删账号/解绑时调
 * DELETE SM /api/pat/bind?by=ph&subject=ph:<id>。
 * 返回 {ok, code, message}；调用方决定失败是否致命（本站：告警但不阻塞本地硬删，
 * 因为本地已经删干净，SM 侧收不到通知时它的下一次推送会被 PH 拒收）。
 */
export async function notifySmUnbind(env, { phSubject, fetchImpl } = {}) {
  const base = resolveSmBaseUrl(env);
  const secret = env && env.PAT_SHARED_SECRET;
  const q = "/api/pat/bind?by=ph&subject=" + encodeURIComponent(String(phSubject || ""));
  const res = await smFetch(base, q, { secret, phSubject, method: "DELETE", fetchImpl });
  if (res.status >= 200 && res.status < 300) return { ok: true, status: res.status };
  return {
    ok: false,
    status: res.status,
    code: res.status === 403 || res.status === 401 ? "SM_SECRET_FORBIDDEN" : "SM_UNBIND_FAILED",
    message: "SM 解绑通知返回 " + res.status + "：" + smMessage(res, "上游未给出原因"),
  };
}
