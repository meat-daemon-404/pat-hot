/**
 * 身份与画像后端的共用层（W2 / 线路契约 §1–§3）。
 *
 * 为什么是 .mjs：Pages Functions 本身按 ESM 模块加载，扩展名无关；
 * 但本仓要在 CI 用 `node --test tests/js` 直接 import **线上同一份实现**。
 * Node 默认把 .js 当 CommonJS，用 .mjs 就能不引入根 package.json
 * （那会让 Pages 构建配置多一个未知变量）。
 * 路由文件（functions/api/ 下的 .js）只是把这里导出的 handler 原样再导出一个
 * 具名 export（Pages 的文件路由要求具名导出），不含任何逻辑——
 * 也就是说测试测的就是线上跑的代码本体，不是副本。
 *
 * （别在块注释里写路径 glob：斜杠+星号+斜杠的那三个字符会提前闭合本注释，
 *   esbuild 与 node --check 都会在那一行报 Unexpected "*"，而 Pages Functions
 *   构建失败的现场比这更难读。本仓的上一版就栽在这里，此句是那次的墓碑。）
 */

export const SESSION_COOKIE = "ph_session";

const CORS_METHODS = "GET,POST,DELETE,OPTIONS";
const CORS_HEADERS = "Content-Type, X-PAT-Shared-Secret, X-PH-Subject";

/**
 * 站点的 eTLD+1 近似：够用于「同站/跨站」判定。
 * 入参既可能是 Origin（带 scheme 的完整 URL，如 https://a.pages.dev），
 * 也可能是 Host（裸主机名，可带端口），两种都要能算出同一个站点键——
 * 判定两边各喂一种，漏掉任一种都会把同站误判成跨站（登录在预览环境静默失效）。
 * 公共后缀（co.uk 这类）在这里一律取最后两段，误差只会让判定更严
 * （把两个不同子域当成同站），不会放行更宽的范围——判定用 eTLD+1 相等，
 * 猜大了最多是把别人当自家人拒掉，猜小了才是放水。
 */
export function siteOf(value) {
  let h = String(value || "").trim().toLowerCase();
  if (!h) return "";
  if (h.includes("://")) {
    try { h = new URL(h).host; } catch (e) { return ""; }
  } else {
    h = h.split("/")[0];
  }
  h = h.replace(/^\[|\]$/g, "").split(":")[0];
  if (!h) return "";
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(h) || h === "localhost") return h;
  const parts = h.split(".");
  return parts.length <= 2 ? h : parts.slice(-2).join(".");
}

/**
 * CORS。本站前端与接口同源（单页内嵌在本仓产物里），浏览器只在跨站时才带
 * Origin 并需要预检，所以策略是：**只有同站（eTLD+1 相同）的 Origin** 才
 * 原样回显 + Allow-Credentials；其余一律回 "*" 且不声明可带凭据。
 *
 * 为什么不写死 "*"：带凭据的请求里 `Access-Control-Allow-Origin: *` 会被
 * 浏览器直接判非法——cookie 带不过去、响应也读不到，等于登录功能静默失效。
 *
 * 为什么不能无脑回显任意 Origin（上一版的写法）：那等于向任何网站声明
 * "你可以凭凭据读这些接口的响应"。眼下 SameSite=Lax 恰好让跨站 fetch
 * 带不上 ph_session，攻击者只能拿到未鉴权的错误响应，所以还没成真漏洞；
 * 但这层保护属于 cookie 属性、不属于 CORS 属性，哪天把 SameSite 调成
 * None（或新增一条不靠 cookie 的鉴权路径）就会立刻变成跨站读取用户画像。
 * 鉴权面自己该把自己关紧，不指望隔壁文件发的那个属性兜底。
 *
 * 需要跨"源"但仍同"站"的真实场景：branch 预览部署
 * （`<branch>.pat-hot.pages.dev` 调 `pat-hot.pages.dev`）——这类照常放行。
 */
export function corsHeaders(origin, requestHost = "") {
  const allowCredentialed = Boolean(origin) && siteOf(origin) === siteOf(requestHost);
  if (origin && allowCredentialed) {
    return {
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Credentials": "true",
      "Access-Control-Allow-Methods": CORS_METHODS,
      "Access-Control-Allow-Headers": CORS_HEADERS,
      Vary: "Origin",
    };
  }
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": CORS_METHODS,
    "Access-Control-Allow-Headers": CORS_HEADERS,
  };
}

export function json(obj, status = 200, origin = "", requestHost = "") {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      ...corsHeaders(origin, requestHost),
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    },
  });
}

/**
 * 失败响应统一 {ok:false, code, message}：code 给机器（前端与测试都断言它），
 * message 给人读。契约 §0 要求"失败要说真原因"——网络故障 / 密钥不对 /
 * 码已用过 三种不许混成一条"操作失败"，也不许混成"暂无数据"。
 */
export function fail(code, message, status, origin = "", requestHost = "") {
  return json({ ok: false, code, message }, status, origin, requestHost);
}

export function ok(extra = {}, origin = "", requestHost = "") {
  return json({ ok: true, ...extra }, 200, origin, requestHost);
}

export function optionsResponse(origin = "", requestHost = "") {
  return new Response(null, { status: 204, headers: corsHeaders(origin, requestHost) });
}

export async function readJsonBody(request) {
  try {
    const v = await request.json();
    if (v === null || typeof v !== "object" || Array.isArray(v)) {
      return { ok: false, code: "BAD_BODY", message: "请求体需为 JSON 对象" };
    }
    return { ok: true, value: v };
  } catch (e) {
    return {
      ok: false,
      code: "BAD_JSON",
      message: "请求体不是合法 JSON：" + String((e && e.message) || e).slice(0, 160),
    };
  }
}

export function parseCookies(header) {
  const out = {};
  for (const part of String(header || "").split(";")) {
    const i = part.indexOf("=");
    if (i < 1) continue;
    const k = part.slice(0, i).trim();
    const v = part.slice(i + 1).trim();
    if (!k || out[k] !== undefined) continue;
    try { out[k] = decodeURIComponent(v); } catch (e) { out[k] = v; }
  }
  return out;
}

/** 会话句柄唯一来源：cookie。body 里任何身份字段一律不采信（契约 §0）。 */
export function cookieHandle(request) {
  return parseCookies(request.headers.get("Cookie"))[SESSION_COOKIE] || "";
}

/**
 * Secure 只在 https 下发。本地 `wrangler pages dev` 是 http://localhost，
 * 带 Secure 的 cookie 会被浏览器丢掉，表现成"本地登录永远失败"这种最难查的
 * 假故障；localhost 本身在浏览器安全上下文豁免名单里，少一个 Secure
 * 不降低实际安全性。
 */
export function sessionCookieValue(handle, { maxAgeSec = 0, secure = true } = {}) {
  const parts = [
    SESSION_COOKIE + "=" + handle,
    "Path=/",
    "HttpOnly",
    "SameSite=Lax",
    "Max-Age=" + Math.max(0, Math.floor(maxAgeSec)),
  ];
  if (secure) parts.push("Secure");
  if (maxAgeSec === 0) parts.push("Expires=Thu, 01 Jan 1970 00:00:00 GMT");
  return parts.join("; ");
}

export function withSetCookie(response, cookie) {
  response.headers.append("Set-Cookie", cookie);
  return response;
}

/** 客户端 IP：CF 头优先，其次 XFF 第一段；本地 dev 落到 "local"。 */
export function clientIp(request) {
  const cf = request.headers.get("CF-Connecting-IP");
  if (cf) return String(cf).trim();
  const xff = request.headers.get("X-Forwarded-For");
  if (xff) return String(xff.split(",")[0]).trim();
  return "local";
}

export function originOf(request) {
  return request.headers.get("Origin") || "";
}

/** 请求自身的主机名：CORS 同站判定要用它和 Origin 比，不能只信 Origin 一侧。 */
export function hostOf(request) {
  try {
    return new URL(request.url).host;
  } catch (e) {
    return String(request.headers.get("Host") || "");
  }
}

export function isHttps(request) {
  try {
    return new URL(request.url).protocol === "https:";
  } catch (e) {
    return false;
  }
}

/**
 * 用户数据面总开关。缺省关闭 = fork 拿到的就是"不存用户数据"的站点，
 * 与纯静态时代行为一致（README「特性」如实写）。
 * 只认字符串 "1"：env 在 Workers 里恒是字符串，写成 truthy 判断会让 "0"
 * 也开机；这里连数字 1 都拒，就是不让"开关"的口径含糊到要靠记忆判断。
 */
export function storeEnabled(env) {
  return Boolean(env) && env.PAT_HOT_STORE_USER_DATA === "1";
}

export function storeDisabledResponse(origin, requestHost = "") {
  return fail(
    "STORE_DISABLED",
    "本站未开启用户数据存储（需环境变量 PAT_HOT_STORE_USER_DATA=1）。"
    + "数据面接口不受影响，仍免鉴权只读可用。",
    503,
    origin,
    requestHost
  );
}
