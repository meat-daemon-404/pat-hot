/**
 * POST /api/account/logout —— 结束当前会话（线路契约 §1）。
 * 为谁：要离开或换账号的读者。
 * 红线：只删**当前 cookie 指向的那一条**会话行（物理删，不留墓碑），
 *   不顺手删绑定、也不删画像——那是 /api/bind/unbind 与 /api/profile-snapshot
 *   DELETE 各自的职责，登出不该有副作用（用户"退出登录"不等于"忘掉我的画像"）。
 * 失败语义：无会话也返回 200（幂等，重复调用不报错），cookie 一律置过期。
 *   真正会失败的只有 503 STORE_DISABLED 与 500 DB_UNAVAILABLE。
 * 实现见 functions/_lib/handlers.mjs 的 logoutHandler。
 */
import { logoutHandler, handleOptions } from "../../_lib/handlers.mjs";

export const onRequestPost = logoutHandler;
export const onRequestOptions = handleOptions;
