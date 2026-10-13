/**
 * POST /api/account/login —— 口令换会话（线路契约 §1）。
 * 为谁：已建号的读者；成功即下发 ph_session cookie（HttpOnly / SameSite=Lax / Secure）。
 * 红线：身份只从会话取，登录成功后前端一律靠 /api/account/me 认人，
 *   不把自己 id 存进 localStorage 再回传。
 *   邮箱不存在与密码错共用同一条 BAD_CREDENTIALS——不给账号枚举留口子。
 * 失败语义：400 形状不合法 · 401 BAD_CREDENTIALS（不分型，防枚举）
 *   429 RATE_LIMITED（每 IP 15 分钟 20 次）· 503 STORE_DISABLED · 500 DB_UNAVAILABLE。
 * 实现见 functions/_lib/handlers.mjs 的 loginHandler。
 */
import { loginHandler, handleOptions } from "../../_lib/handlers.mjs";

export const onRequestPost = loginHandler;
export const onRequestOptions = handleOptions;
