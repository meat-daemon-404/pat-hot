/**
 * POST /api/account/register —— 本站本地账号建号（线路契约 §1，PH 侧 W2）。
 * 为谁：想在 PAT-HOT 上按自己的研究兴趣排序、又还没绑 ScholarMatrix 的读者。
 * 入参只有 {email, password}：身份绝不从 body 里的 id 字段取（契约 §0）。
 * 红线：邮箱小写去重；密码只设 8 位下限，不装复杂度的样子；口令用 PBKDF2
 * 加盐散列后入库，明文和可逆形式都不落库；会话句柄是高熵随机串，
 * 只进 HttpOnly cookie。
 * 失败语义（逐型分开，不混成"操作失败"）：
 *   400 邮箱/密码形状不合法 · 409 EMAIL_TAKEN · 429 RATE_LIMITED（每 IP 每小时 5 次）
 *   503 STORE_DISABLED（未开 PAT_HOT_STORE_USER_DATA）· 500 DB_UNAVAILABLE（没绑 D1）。
 * 逻辑本体在 functions/_lib/handlers.mjs——本文件只做 Pages 文件路由要求的具名再导出，
 * 所以 `node --test tests/js` 测的就是线上跑的同一份实现。
 */
import { registerHandler, handleOptions } from "../../_lib/handlers.mjs";

export const onRequestPost = registerHandler;
export const onRequestOptions = handleOptions;
