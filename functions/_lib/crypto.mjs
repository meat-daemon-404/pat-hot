/**
 * 口令与会话句柄：只用 WebCrypto（Pages Functions 与 Node 18+ 都有
 * globalThis.crypto.subtle），零依赖、不引第三方算法。
 *
 * 为什么是 PBKDF2 而不是 bcrypt/argon2：Pages Function 跑在 V8 isolate 里，
 * 没有原生 bcrypt，纯 JS 的 argon2/bcrypt 慢一个量级且要引依赖。WebCrypto 的
 * PBKDF2-SHA256 是平台内置、可审计的替代，代价是用高迭代次数（21 万）补强度。
 * 这是取舍，不是"最佳实践"宣称。
 *
 * 存储格式：<saltHex>$<hashHex>$<iterations>
 * 前两段即约定的 salt$hash 十六进制；第三段带迭代次数，是为了以后调参时
 * 旧口令仍可校验（没有这一段，提高迭代数会让所有存量账号静默登录失败）。
 */

export const PBKDF2_ITERATIONS = 210000; // ≥100k（任务书下限），Node 20 上约 150–250ms
export const PBKDF2_KEY_BITS = 256;
export const SALT_BYTES = 16;
export const HANDLE_BYTES = 32; // 256 bit：会话句柄不可猜测，cookie 即能力凭证
export const PASSWORD_MIN = 8;
export const PASSWORD_MAX = 256;

function hexOf(buf) {
  const u = new Uint8Array(buf);
  let s = "";
  for (const b of u) s += (b < 16 ? "0" : "") + b.toString(16);
  return s;
}

function randomBytes(n) {
  const a = new Uint8Array(n);
  crypto.getRandomValues(a);
  return a;
}

export function randomHex(nBytes) {
  return hexOf(randomBytes(nBytes).buffer);
}

/** 本地账号 id：12 位随机 hex，前缀 ph: 由调用方拼（契约 §1 主体命名空间）。 */
export function newUserId() {
  return randomHex(6);
}

/** 会话句柄：高熵随机 hex，不含用户信息，可安全出现在 cookie 里。 */
export function newSessionHandle() {
  return randomHex(HANDLE_BYTES);
}

async function derive(password, saltBytes, iterations, keyBits) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(String(password)),
    "PBKDF2",
    false,
    ["deriveBits"]
  );
  return crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt: saltBytes, iterations: iterations | 0 },
    key,
    keyBits
  );
}

export async function pwHash(password, iterations = PBKDF2_ITERATIONS) {
  const salt = randomBytes(SALT_BYTES);
  const bits = await derive(password, salt, iterations, PBKDF2_KEY_BITS);
  return hexOf(salt.buffer) + "$" + hexOf(bits) + "$" + (iterations | 0);
}

/** 等长定字比较：不因提前返回产生时间差。 */
function equalHex(a, b) {
  if (typeof a !== "string" || typeof b !== "string") return false;
  if (a.length !== b.length) return false;
  if (!/^[0-9a-f]*$/i.test(a) || !/^[0-9a-f]*$/i.test(b)) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export async function pwVerify(password, stored) {
  const seg = String(stored || "").split("$");
  if (seg.length !== 3) return false;
  const [saltHex, hashHex, iterStr] = seg;
  if (!/^[0-9a-f]{2,}$/i.test(saltHex) || !/^[0-9a-f]{2,}$/i.test(hashHex)) return false;
  const iterations = parseInt(iterStr, 10);
  // 迭代数越界（0、负、被篡改的巨大值）都按非法存储拒绝：否则一次 deriveBits
  // 能把 Function 的 CPU 配额打满，变成"任何知道别人邮箱的人都能拖垮登录接口"。
  if (!(iterations >= 1000) || iterations > 5000000) return false;
  const salt = new Uint8Array(saltHex.length / 2);
  for (let i = 0; i < salt.length; i++) salt[i] = parseInt(saltHex.substr(i * 2, 2), 16);
  const bits = await derive(password, salt, iterations, PBKDF2_KEY_BITS);
  return equalHex(hexOf(bits), hashHex.toLowerCase());
}

/**
 * 共享密钥比较（X-PAT-Shared-Secret）。任一侧为空即拒绝——
 * "空 secret 与空 header 相等"是真实事故形状：未配置的部署不能白拿权限。
 */
export function secretEqual(a, b) {
  const x = String(a == null ? "" : a);
  const y = String(b == null ? "" : b);
  if (!x || !y) return false;
  if (x.length !== y.length) return false;
  let diff = 0;
  for (let i = 0; i < x.length; i++) diff |= x.charCodeAt(i) ^ y.charCodeAt(i);
  return diff === 0;
}

/** 口令下限只到"8 位起"：账号仅服务本站个性化排序，不设过度门槛。 */
export function checkPasswordShape(pw) {
  const s = String(pw == null ? "" : pw);
  if (!s) return { ok: false, code: "PASSWORD_REQUIRED", message: "请填写密码" };
  if (s.length < PASSWORD_MIN) {
    return { ok: false, code: "PASSWORD_WEAK", message: "密码至少 " + PASSWORD_MIN + " 位" };
  }
  if (s.length > PASSWORD_MAX) {
    return { ok: false, code: "PASSWORD_TOO_LONG", message: "密码最长 " + PASSWORD_MAX + " 位" };
  }
  return { ok: true, value: s };
}

/**
 * 邮箱只做形状校验 + 小写归一，不发验证邮件：站点匿名可读，账号只服务
 * 个性化（README 如实写明"不发邮件"）。因此不宣称"邮箱已验证"。
 */
export function normalizeEmail(email) {
  const s = String(email == null ? "" : email).trim().toLowerCase();
  if (!s) return { ok: false, code: "EMAIL_REQUIRED", message: "请填写邮箱" };
  if (s.length > 254) return { ok: false, code: "EMAIL_TOO_LONG", message: "邮箱过长" };
  if (!/^[^\s@,;:]+@[^\s@,;.]+(\.[^\s@,;.]+)+$/.test(s)) {
    return { ok: false, code: "EMAIL_INVALID", message: "邮箱格式不正确" };
  }
  return { ok: true, value: s };
}
