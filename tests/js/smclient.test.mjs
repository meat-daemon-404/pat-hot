/**
 * PH → SM 出站回调（functions/_lib/smclient.mjs）。
 * 不打真网络：fetchImpl 注入，超时用显式短 timeoutMs 跑真 AbortSignal。
 * 盯的是契约 §0 的"失败要说真原因"与契约 §7 的"代码里仍硬校验主机"。
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  smFetch, redeemBindCode, notifySmUnbind, resolveSmBaseUrl,
  SmCallError, SM_BASE_DEFAULT, CALLBACK_TIMEOUT_MS,
} from "../../functions/_lib/smclient.mjs";

const ENV = { PAT_SHARED_SECRET: "s3cret", SM_BASE: "https://scholarmatrix.pages.dev" };
const up = (status, body, contentType = "application/json") => async () =>
  new Response(body === "" || body === null ? null : (typeof body === "string" ? body : JSON.stringify(body)), { status, headers: { "Content-Type": contentType } });

test("SM_BASE 默认值就是契约 §7 写的主机", () => {
  assert.equal(SM_BASE_DEFAULT, "https://scholarmatrix.pages.dev");
  assert.equal(resolveSmBaseUrl({}), SM_BASE_DEFAULT, "没配 env 也走契约默认值");
  assert.equal(CALLBACK_TIMEOUT_MS, 8000, "任务书定的 8 秒上限");
});

test("SM_BASE 硬校验：非 https、白名单外主机、带路径都拒", () => {
  const cases = [
    ["http://scholarmatrix.pages.dev", "SM_BASE_INVALID", "明文 http 必须拒（带的是共享密钥）"],
    ["https://evil.com", "SM_BASE_NOT_ALLOWED", "白名单外主机必须拒（变异思路：不校验主机，SM_BASE 填什么就把密钥发给什么）"],
    ["https://example.org/x", "SM_BASE_NOT_ALLOWED", "非 pages.dev/workers.dev 一律拒"],
    ["https://a.pages.dev/api", "SM_BASE_INVALID", "不许带路径（会拼出双段路径）"],
    ["not-a-url", "SM_BASE_INVALID", "非法 URL 说人话"],
  ];
  for (const [v, code, why] of cases) {
    try { resolveSmBaseUrl({ SM_BASE: v }); assert.fail(why + "：不该放行 " + v); }
    catch (e) { assert.equal(e.code, code, why); assert.ok(e instanceof SmCallError); }
  }
  // 放行面
  assert.equal(resolveSmBaseUrl({ SM_BASE: "https://feat.pat-hot.pages.dev" }), "https://feat.pat-hot.pages.dev");
  assert.equal(resolveSmBaseUrl({ SM_BASE: "https://w-x.workers.dev" }), "https://w-x.workers.dev", "workers.dev 允许（SM 侧同源部署别名）");
  assert.equal(resolveSmBaseUrl({ SM_BASE: "http://localhost:8788" }), "http://localhost:8788", "本地调试放行，否则对拍跑不起来");
  assert.equal(resolveSmBaseUrl({ SM_BASE: "https://scholarmatrix.pages.dev/" }), "https://scholarmatrix.pages.dev", "尾斜杠归一");
});

test("未配置密钥：就地 503，绝不发出这一跳", async () => {
  let touched = 0;
  const spy = () => { touched++; return up(200, {}); };
  for (const secret of ["", undefined, null, "   ", "  s3cret  "]) {
    await assert.rejects(
      smFetch("https://scholarmatrix.pages.dev", "/x", { secret, fetchImpl: spy }),
      (e) => { assert.equal(e.code, "SECRET_MISSING"); assert.equal(e.status, 503); return true; },
      JSON.stringify(secret) + " 必须拒（变异思路：只判空串，带空白的密钥照样发出，换来 SM 永远 401 的难查症状）");
  }
  assert.equal(touched, 0, "一次都不该出站");
});

test("出站带上契约规定的两个头，并带 AbortSignal", async () => {
  const seen = [];
  const impl = async (url, init) => { seen.push({ url, init }); return new Response(JSON.stringify({ ok: true, smSubject: "sm:x" }), { status: 200 }); };
  await redeemBindCode(ENV, { code: "K/中文 码", phSubject: "ph:u1", fetchImpl: impl });
  assert.equal(seen[0].url, "https://scholarmatrix.pages.dev/api/pat/bind.redeem?code=" + encodeURIComponent("K/中文 码"),
    "码要 URL 编码，否则含空格/斜杠的码会拼坏查询串");
  assert.equal(seen[0].init.headers["X-PAT-Shared-Secret"], "s3cret");
  assert.equal(seen[0].init.headers["X-PH-Subject"], "ph:u1", "契约 §1.1：SM 侧要靠这个头存 phSubject");
  assert.ok(seen[0].init.signal, "必须带 signal（裸 Promise.race 不真取消，SM 慢时照样占 isolate）");
  assert.equal(seen[0].init.method, "GET", "兑换是 GET");
});

test("上游状态 → 机器码与状态码逐条对齐任务书", async () => {
  const cases = [
    [401, { message: "bad" }, "SECRET_MISMATCH", 401],
    [403, "forbidden", "SECRET_MISMATCH", 401],
    [404, {}, "CODE_INVALID", 410],
    [410, {}, "CODE_INVALID", 410],
    [429, {}, "SM_RATE_LIMITED", 429],
    [500, "boom", "SM_UPSTREAM_ERROR", 502],
    [200, "<html>cf 反爬</html>", "SM_BAD_RESPONSE", 502],
    [200, { ok: false, message: "already used" }, "SM_REDEEM_REJECTED", 502],
    [200, { ok: true }, "SM_BAD_RESPONSE", 502, "缺 smSubject"],
    [200, { ok: true, smSubject: "no-prefix" }, "SM_BAD_RESPONSE", 502, "主体没前缀"],
  ];
  for (const [status, body, code, expectStatus, note] of cases) {
    let err = null;
    try { await redeemBindCode(ENV, { code: "K", phSubject: "ph:1", fetchImpl: up(status, body) }); }
    catch (e) { err = e; }
    assert.ok(err, (note || "") + " 上游 " + status + " 必须抛错，不许静默成功");
    assert.equal(err.code, code, (note || "") + " 上游 " + status + " 的机器码");
    assert.equal(err.status, expectStatus, (note || "") + " 透出给客户端的状态码");
  }
});

test("message 带上游真原因，并截断到 200 字符内", async () => {
  const long = "x".repeat(5000);
  let err = null;
  try { await redeemBindCode(ENV, { code: "K", fetchImpl: up(500, long, "text/plain") }); } catch (e) { err = e; }
  assert.ok(err.message.includes("500"), "要把上游状态码说清楚（契约 §0：网络故障/密钥不对/码已用过 三种不许混）");
  assert.ok(err.detail.length <= 200, "上游正文截断，别把 5KB 塞进响应");
});

test("网络故障与超时都归 502 SM_UNREACHABLE，原因分开", async () => {
  let err = null;
  try { await redeemBindCode(ENV, { code: "K", fetchImpl: async () => { throw Object.assign(new Error("getaddrinfo ENOTFOUND x"), { name: "TypeError" }); } }); }
  catch (e) { err = e; }
  assert.equal(err.code, "SM_UNREACHABLE");
  assert.equal(err.status, 502);
  assert.match(err.message, /ENOTFOUND/, "原始原因要留住");

  const hang = (u, init) => new Promise((_, rej) => init.signal.addEventListener("abort", () => rej(new Error("signal aborted"))));
  const t0 = Date.now();
  err = null;
  try { await redeemBindCode(ENV, { code: "K", fetchImpl: hang, timeoutMs: 60 }); }
  catch (e) { err = e; }
  assert.equal(err.code, "SM_UNREACHABLE", "超时归到同一类（对前端都是这一跳没走通），真原因在 message");
  assert.equal(err.status, 502);
  assert.match(err.message, /超时/, "message 要说是超时，不是 DNS");
  assert.ok(Date.now() - t0 < 3000, "AbortSignal.timeout 真的在 60ms 附近打断，没等满默认 8s");
});

test("反向解绑通知：成功与失败都如实回报，不假装成功", async () => {
  const okN = await notifySmUnbind(ENV, { phSubject: "ph:1", fetchImpl: up(204, null) });
  assert.equal(okN.ok, true, "2xx 算通知到了");
  const bad = await notifySmUnbind(ENV, { phSubject: "ph:1", fetchImpl: up(403, "nope") });
  assert.equal(bad.ok, false);
  assert.equal(bad.code, "SM_SECRET_FORBIDDEN", "403 归密钥问题");
  assert.match(bad.message, /403/);
  const gone = await notifySmUnbind(ENV, { phSubject: "ph:1", fetchImpl: up(404, "gone") });
  assert.equal(gone.ok, false);
  assert.equal(gone.code, "SM_UNBIND_FAILED");
  const url = [];
  await notifySmUnbind(ENV, { phSubject: "ph:u1", fetchImpl: async (u, init) => { url.push([u, init.method]); return new Response("", { status: 200 }); } });
  assert.equal(url[0][0], "https://scholarmatrix.pages.dev/api/pat/bind?by=ph&subject=ph%3Au1", "契约 §1.2 的反向调用形状");
  assert.equal(url[0][1], "DELETE");
  // 没配密钥：抛错而不是默默"通知失败"
  await assert.rejects(() => notifySmUnbind({ SM_BASE: ENV.SM_BASE }, { phSubject: "ph:1", fetchImpl: up(200, {}) }), (e) => e.code === "SECRET_MISSING");
});
