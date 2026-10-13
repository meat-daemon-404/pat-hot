/**
 * HTTP 共用层（会话 cookie / CORS / 解析；functions/_lib/http.mjs）。
 * 只测纯函数面——不真起服务、不打网络。
 *
 * 这一层的红线是"身份只从 cookie 会话取"（契约 §0）与
 * "CORS 不给任意站点开凭据门"，所以下面每条都盯着这两点。
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  SESSION_COOKIE, corsHeaders, json, fail, ok, optionsResponse,
  parseCookies, cookieHandle, sessionCookieValue, withSetCookie,
  readJsonBody, clientIp, originOf, hostOf, isHttps,
  storeEnabled, storeDisabledResponse, siteOf,
} from "../../functions/_lib/http.mjs";

const req = (url, headers = {}) => new Request(url, { headers });

test("parseCookies：常规解析、首个同名生效、畸形片段容错", () => {
  assert.deepEqual(parseCookies("a=1; b=2"), { a: "1", b: "2" });
  assert.deepEqual(parseCookies(""), {}, "空 header 不炸");
  assert.deepEqual(parseCookies(null), {}, "缺 header 不炸（变异思路：String(header).split 不做 || \"\" 就会在 null 上抛）");
  assert.deepEqual(parseCookies("a=1; a=2"), { a: "1" }, "同名取第一个，不被后面覆盖");
  assert.deepEqual(parseCookies("=novalue; b=2"), { b: "2" }, "没有键名的片段跳过");
  assert.deepEqual(parseCookies("flagonly; b=2"), { b: "2" }, "没有等号的片段跳过");
  assert.deepEqual(parseCookies("t=a%3Db"), { t: "a=b" }, "值里的百分号编码要还原");
  assert.deepEqual(parseCookies("t=%E4%B8%AD"), { t: "中" }, "UTF-8 百分号编码");
  assert.deepEqual(parseCookies("t=%zz"), { t: "%zz" }, "非法百分号序列原样保留而不是抛错");
});

test("cookieHandle：只认 ph_session，别的一律不算身份", () => {
  const r = req("https://pat-hot.pages.dev/api/account/me", { Cookie: "other=x; ph_session=abc123; ph_other=y" });
  assert.equal(cookieHandle(r), "abc123");
  assert.equal(cookieHandle(req("https://x/api/account/me", { Cookie: "session=abc" })), "",
    "名字差一点也不算（变异思路：模糊匹配会把别的站点的 session cookie 当成本站身份）");
  assert.equal(cookieHandle(req("https://x/api/account/me")), "", "无 Cookie 头返回空串");
});

test("sessionCookieValue：HttpOnly + SameSite=Lax + Secure 一个都不能少", () => {
  const v = sessionCookieValue("handle123", { maxAgeSec: 3600 });
  assert.match(v, /^ph_session=handle123;/);
  assert.match(v, /Path=\//);
  assert.match(v, /HttpOnly/, "🔴 必须 HttpOnly：否则页面脚本能读走会话句柄（XSS 即账号接管）");
  assert.match(v, /SameSite=Lax/, "🔴 SameSite=Lax：跨站 POST 不带 cookie，挡 CSRF 绑定/改密这类动作");
  assert.match(v, /Secure/, "https 下必须 Secure");
  assert.match(v, /Max-Age=3600/);
  assert.ok(!/Expires=/.test(v), "有 Max-Age 时不该带过期日期");

  const noSecure = sessionCookieValue("h", { maxAgeSec: 60, secure: false });
  assert.ok(!/Secure/.test(noSecure), "本地 http://localhost 调试时不发 Secure（否则浏览器丢 cookie，表现成本地登录永远失败）");

  const cleared = sessionCookieValue("", { maxAgeSec: 0 });
  assert.match(cleared, /Max-Age=0/, "登出要立刻过期");
  assert.match(cleared, /Expires=Thu, 01 Jan 1970/, "并带上 epoch 日期（老浏览器只认 Expires）");
  assert.equal(sessionCookieValue("h", { maxAgeSec: -5 }).match(/Max-Age=(\d+)/)[1], "0",
    "负数不许写成 Max-Age=-5（变异思路：不做 Math.max(0,…) 会产出非法 cookie 属性）");
});

test("withSetCookie：Set-Cookie 附在响应上且不改状态码", async () => {
  const base = json({ ok: true }, 200);
  const res = withSetCookie(base, sessionCookieValue("h", { maxAgeSec: 60 }));
  assert.equal(res.status, 200);
  assert.match(res.headers.get("Set-Cookie"), /^ph_session=h;/);
});

test("corsHeaders：同站回显 + 允许凭据；跨站只回 * 且绝不带 Allow-Credentials", () => {
  const same = corsHeaders("https://pat-hot.pages.dev", "pat-hot.pages.dev");
  assert.equal(same["Access-Control-Allow-Origin"], "https://pat-hot.pages.dev");
  assert.equal(same["Access-Control-Allow-Credentials"], "true");
  assert.equal(same.Vary, "Origin");

  // branch 预览部署：不同主机、同一站点，凭据仍要放行（否则预览环境登录直接坏）
  const branch = corsHeaders("https://feat-x.pat-hot.pages.dev", "pat-hot.pages.dev");
  assert.equal(branch["Access-Control-Allow-Credentials"], "true", "同 eTLD+1 的预览子域要放行");

  // 🔴 恶意站点：不给凭据门
  const evil = corsHeaders("https://evil.example.com", "pat-hot.pages.dev");
  assert.equal(evil["Access-Control-Allow-Origin"], "*",
    "跨站必须退回 *（变异思路：无条件回显 Origin 就是向任意网站声明'你可以凭凭据读用户画像'，那等于账号接管）");
  assert.ok(!("Access-Control-Allow-Credentials" in evil), "🔴 跨站不许出现 Allow-Credentials");
  assert.notEqual(evil["Access-Control-Allow-Origin"], "https://evil.example.com");

  assert.equal(corsHeaders("", "pat-hot.pages.dev")["Access-Control-Allow-Origin"], "*", "无 Origin（同源请求/服务器调用）回 *");
  // 本地调试：localhost 的源与主机必须自己匹配，不与线上站互认
  assert.equal(corsHeaders("http://localhost:8788", "localhost:8788")["Access-Control-Allow-Credentials"], "true");
  assert.ok(!("Access-Control-Allow-Credentials" in corsHeaders("http://localhost:8788", "pat-hot.pages.dev")));
});

test("siteOf：eTLD+1 近似，主机带端口也能比", () => {
  assert.equal(siteOf("https://pat-hot.pages.dev"), "pages.dev");
  assert.equal(siteOf("feat-x.pat-hot.pages.dev"), "pages.dev");
  assert.equal(siteOf("evil-example.com"), "evil-example.com");
  assert.equal(siteOf("localhost:8788"), "localhost");
  assert.equal(siteOf("127.0.0.1:8787"), "127.0.0.1");
  assert.equal(siteOf(""), "", "空主机不许误判成任何站点");
});

test("json / fail / ok：响应形状 {ok, code, message} 与 no-store", async () => {
  const r = fail("CODE_INVALID", "码已用过", 410, "https://pat-hot.pages.dev", "pat-hot.pages.dev");
  assert.equal(r.status, 410);
  assert.equal(r.headers.get("Content-Type"), "application/json");
  assert.equal(r.headers.get("Cache-Control"), "no-store", "🔴 账号面绝不许缓存：会话相关响应被缓存就是跨用户泄露");
  assert.deepEqual(await r.json(), { ok: false, code: "CODE_INVALID", message: "码已用过" });

  const o = ok({ bound: true }, "", "pat-hot.pages.dev");
  assert.equal(o.status, 200);
  assert.deepEqual(await o.json(), { ok: true, bound: true });
});

test("optionsResponse：204 预检，带同源相同的 CORS 口径", () => {
  const r = optionsResponse("https://evil.example.com", "pat-hot.pages.dev");
  assert.equal(r.status, 204);
  assert.equal(r.headers.get("Access-Control-Allow-Origin"), "*");
  assert.ok(!r.headers.get("Access-Control-Allow-Credentials"), "预检也不许给跨站声明可带凭据");
  assert.match(r.headers.get("Access-Control-Allow-Headers"), /X-PAT-Shared-Secret/);
});

test("readJsonBody：坏 JSON / 非对象各有其码（不混成 500）", async () => {
  const mk = (body, type = "application/json") =>
    new Request("https://x/api/profile-snapshot", { method: "POST", body, headers: { "Content-Type": type } });
  assert.deepEqual(await readJsonBody(mk('{"a":1}')), { ok: true, value: { a: 1 } });
  assert.equal((await readJsonBody(mk("not json"))).code, "BAD_JSON");
  assert.equal((await readJsonBody(mk("[]"))).code, "BAD_BODY", "数组不算对象载荷");
  assert.equal((await readJsonBody(mk("null"))).code, "BAD_BODY");
  assert.equal((await readJsonBody(mk('"str"'))).code, "BAD_BODY");
  assert.equal((await readJsonBody(mk("", "text/plain"))).code, "BAD_JSON", "空体也是坏 JSON，不是 500");
});

test("clientIp / originOf / hostOf / isHttps：从请求头取真实来源", () => {
  const r = req("https://pat-hot.pages.dev/api/account/register", {
    "CF-Connecting-IP": " 203.0.113.9 ", "X-Forwarded-For": "198.51.100.7, 10.0.0.1", Origin: "https://pat-hot.pages.dev",
  });
  assert.equal(clientIp(r), "203.0.113.9", "CF 头优先（XFF 首段可被客户端伪造）");
  assert.equal(clientIp(req("https://x/", { "X-Forwarded-For": "198.51.100.7, 10.0.0.1" })), "198.51.100.7");
  assert.equal(clientIp(req("https://x/")), "local", "本地 dev 落到 local，不是空串（空串会让所有本地请求共用同一个限流桶，反而互相顶掉）");
  assert.equal(originOf(r), "https://pat-hot.pages.dev");
  assert.equal(originOf(req("https://x/")), "");
  assert.equal(hostOf(r), "pat-hot.pages.dev");
  assert.equal(isHttps(r), true);
  assert.equal(isHttps(req("http://localhost:8788/api/account/me")), false);
});

test("storeEnabled：只有字符串 1 算开，其余一律关", () => {
  assert.equal(storeEnabled({ PAT_HOT_STORE_USER_DATA: "1" }), true);
  for (const v of [undefined, "", "0", "true", "1 ", 1, "yes"]) {
    assert.equal(storeEnabled({ PAT_HOT_STORE_USER_DATA: v }), false, JSON.stringify(v) + " 不算开（变异思路：写成 truthy 判断，'0' 和 'true' 都会误开机）");
  }
  assert.equal(storeEnabled({}), false, "缺 env 也不许开");
  assert.equal(storeEnabled(undefined), false, "整个 env 缺失不许抛");
});

test("storeDisabledResponse：503 + STORE_DISABLED，并说明数据面不受影响", async () => {
  const r = storeDisabledResponse("", "pat-hot.pages.dev");
  assert.equal(r.status, 503);
  const b = await r.json();
  assert.equal(b.ok, false);
  assert.equal(b.code, "STORE_DISABLED");
  assert.match(b.message, /PAT_HOT_STORE_USER_DATA/, "报错要指名那个开关");
  assert.match(b.message, /免鉴权只读/, "🔴 必须说清数据面照常可用——别让 fork 用户以为整站挂了");
});

test("SESSION_COOKIE 常量与 cookie 串一致（改名字两处必须同改）", () => {
  assert.equal(SESSION_COOKIE, "ph_session");
  assert.match(sessionCookieValue("h", { maxAgeSec: 1 }), new RegExp("^" + SESSION_COOKIE + "=h;"));
  assert.equal(cookieHandle(req("https://x/", { Cookie: SESSION_COOKIE + "=z" })), "z");
});
