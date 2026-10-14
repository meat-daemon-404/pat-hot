/**
 * 口令散列与共享密钥比较（线路契约 §1 的地基；functions/_lib/crypto.mjs）。
 * 只测纯函数面：不打网络、不碰 D1。
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  pwHash, pwVerify, secretEqual, checkPasswordShape, normalizeEmail,
  randomHex, newUserId, newSessionHandle,
  PBKDF2_ITERATIONS, PASSWORD_MIN, SALT_BYTES, HANDLE_BYTES,
} from "../../functions/_lib/crypto.mjs";

const PW = "Correct-Horse-9";

test("pwHash / pwVerify 往返：同口令过，异口令不过", async () => {
  const stored = await pwHash(PW);
  const seg = stored.split("$");
  // 存储格式 <saltHex>$<hashHex>$<iterations>
  assert.equal(seg.length, 3, "必须是三段（变异思路：若 pwHash 不再带迭代数，调参后所有旧口令会静默登录失败）");
  assert.equal(seg[0].length, SALT_BYTES * 2, "salt 段应是 16 字节的 hex（变异思路：salt 长度写成 0 就等于同口令同 hash）");
  assert.equal(seg[2], String(PBKDF2_ITERATIONS));

  assert.equal(await pwVerify(PW, stored), true, "同口令必须校验通过");
  assert.equal(await pwVerify(PW.toLowerCase(), stored), false, "差一个字母必须不过（变异思路：derive 若忽略 password 参数就会两边都过）");
});

test("迭代数不得超过 Cloudflare Workers 的 WebCrypto 上限", () => {
  // 🔴 真生产回归钉：首版写 210000，Node 20 的 deriveBits 允许（本地 68 项全绿），
  // 一上 Pages Functions 注册当场 500：
  //   "Pbkdf2 failed: iteration counts above 100000 are not supported (requested 210000)"
  // 也就是说这条只能靠"真跑一次生产"发现——现在把它钉成静态断言，
  // 谁日后为"提高强度"把数调回 10 万以上，本地就红，不必再等生产炸。
  assert.ok(PBKDF2_ITERATIONS <= 100000,
    "Workers 的 PBKDF2 deriveBits 上限是 100000，超过即生产注册 500（Node 测试环境不报错，测不出来）");
  assert.ok(PBKDF2_ITERATIONS >= 100000,
    "任务书下限是 ≥100k；若真要调低必须先改任务书口径，不能悄悄降强度");
  // 变异思路：把 PBKDF2_ITERATIONS 改成 210000 → 第一条红；改成 1000 → 第二条红。
});

test("同一口令两次散列得到不同存储（salt 随机，不是恒定 hash）", async () => {
  const a = await pwHash(PW);
  const b = await pwHash(PW);
  assert.notEqual(a, b, "salt 必须是随机串（变异思路：salt 若固定，同口令的用户 hash 相同，撞库表就成立了）");
  assert.equal(await pwVerify(PW, a), true);
  assert.equal(await pwVerify(PW, b), true);
});

test("中文口令按字符往返，空口令不静默放行", async () => {
  const stored = await pwHash("密码测试-锁");
  assert.equal(await pwVerify("密码测试-锁", stored), true, "非 ASCII 口令必须能往返（变异思路：TextEncoder 换成 latin1 就会在这里炸）");
  assert.equal(await pwVerify("密码测试-错", stored), false);
  assert.equal(await pwVerify("", stored), false);
});

test("迭代数越界的存储一律拒（0 / 负 / 天量 / 非数字 / 段数不对）", async () => {
  const salt = randomHex(SALT_BYTES);
  const hash = randomHex(32);
  const cases = [
    [salt + "$" + hash + "$0", "iterations=0"],
    [salt + "$" + hash + "$-1", "负数"],
    [salt + "$" + hash + "$999999999", "超上限：一次 deriveBits 能烧光 Function 的 CPU 配额"],
    [salt + "$" + hash + "$abc", "非数字"],
    [salt + "$" + hash, "缺第三段"],
    [salt + "$" + hash + "$5$9", "段数过多"],
    ["$" + hash + "$1000", "salt 为空"],
  ];
  for (const [stored, why] of cases) {
    assert.equal(await pwVerify(PW, stored), false, why + " 必须拒绝，而不是开始算");
  }
  // 合法下界仍可校验：证明上面不是"全都返回 false"混过去的
  const okStored = await pwHash(PW, 1000);
  assert.equal(await pwVerify(PW, okStored), true,
    "1000 次（下界）应可校验（变异思路：把下界写成 >1000，1000 本身就被拒，这里会红）");
});

test("secretEqual：任一侧为空即拒，逐字相等才过", () => {
  assert.equal(secretEqual("", ""), false, "空 == 空 不算通过：未配置的部署不能白拿权限");
  assert.equal(secretEqual("s3cret", ""), false);
  assert.equal(secretEqual("", "s3cret"), false);
  assert.equal(secretEqual(null, null), false);
  assert.equal(secretEqual(undefined, "x"), false);
  assert.equal(secretEqual("s3cret", "s3cret"), true);
  assert.equal(secretEqual("s3cret", "s3creu"), false, "最后一个字符不同也要拒（变异思路：只比长度就会放过这种）");
  assert.equal(secretEqual("s3cret", "s3crett"), false, "长度不同要拒");
  assert.equal(secretEqual("  a  ", "a"), false, "空白不参与归一：带空格的密钥就是不等于干净的密钥");
});

test("checkPasswordShape：只设下限 8 位，另设过长上限防 DoS", () => {
  assert.equal(checkPasswordShape("").ok, false);
  assert.equal(checkPasswordShape("").code, "PASSWORD_REQUIRED");
  assert.equal(checkPasswordShape("a".repeat(PASSWORD_MIN - 1)).code, "PASSWORD_WEAK", "7 位必须拒");
  assert.equal(checkPasswordShape("a".repeat(PASSWORD_MIN)).ok, true,
    "正好 8 位必须过（变异思路：写成 > PASSWORD_MIN 就变成要 9 位）");
  assert.equal(checkPasswordShape("八个字的中文密码").ok, true, "中文按字符数计：够 8 个字符就够，本站不装复杂度");
  assert.equal(checkPasswordShape("六个中文密码").code, "PASSWORD_WEAK", "6 个字符不足 8 位");
  assert.equal(checkPasswordShape("a".repeat(4000)).ok, false, "超长拒（不给 PBKDF2 送 1MB 口令）");
});

test("normalizeEmail：小写归一 + trim，形状不合法各有其码", () => {
  assert.equal(normalizeEmail("  Admin@Example.COM ").value, "admin@example.com",
    "必须小写去空格（变异思路：不归一化就会让 A@b.com 与 a@b.com 建成两个号）");
  assert.equal(normalizeEmail("").code, "EMAIL_REQUIRED");
  assert.equal(normalizeEmail("nope").code, "EMAIL_INVALID");
  assert.equal(normalizeEmail("a b@c.com").code, "EMAIL_INVALID", "含空格要拒");
  assert.equal(normalizeEmail("a@b").code, "EMAIL_INVALID", "没有点号的域名要拒");
  assert.equal(normalizeEmail("a@b.c").ok, true, "最短合法形状要放行");
  assert.equal(normalizeEmail("a".repeat(300) + "@b.com").code, "EMAIL_TOO_LONG");
});

test("随机句柄：会话句柄足够长且是纯 hex（cookie 即能力凭证）", () => {
  const h = newSessionHandle();
  assert.equal(h.length, HANDLE_BYTES * 2);
  assert.match(h, /^[0-9a-f]+$/,
    "必须是 hex（变异思路：掺进非 hex 字符的话，resolveSession 的形状粗筛会把它整条判死）");
  assert.notEqual(h, newSessionHandle());
  assert.match(newUserId(), /^[0-9a-f]{12}$/);
});
