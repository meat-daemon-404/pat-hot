/**
 * POST /api/bind/verify —— 用 SM 发来的一次性码把两边账号绑上（线路契约 §1.1 ②）。
 * 为谁：已在 ScholarMatrix 点了「绑定 PAT-HOT」、拿着 10 分钟短码来到本站的读者。
 * 前提：必须已登录本站（绑定关系挂在 ph_users 的本地账号上）；body 只有 {code}。
 * 红线：body 里若带 smSubject / phSubject / userId 一律忽略——phSubject 由会话
 *   反推，smSubject 只信 SM 兑换响应的回值（契约 §0「身份只从会话取」）。
 *   共享密钥只在这一跳的服务器对服务器请求头里走，绝不下发给浏览器。
 * 出站：GET {SM_BASE}/api/pat/bind.redeem?code=…，带 X-PAT-Shared-Secret 与
 *   X-PH-Subject: ph:<本地用户 id>，8 秒上限，超时即断（不占 isolate）。
 * 成功 → db.upsertBinding，返回 {ok, smSubject}；SM 若顺带回快照则同路入库。
 * 失败分型（照契约 §0 说真原因，四种不许混）：
 *   401 SECRET_MISMATCH 两端密钥不一致 · 410 CODE_INVALID 码不存在/已用/已过期
 *   502 SM_UNREACHABLE 网络故障或超时（附真原因） · 503 STORE_DISABLED 未开数据面
 *   另：401 NOT_AUTHENTICATED 未登录 · 400 CODE_REQUIRED · 429 SM_RATE_LIMITED。
 * 实现见 functions/_lib/handlers.mjs 的 bindVerifyHandler。
 */
import { bindVerifyHandler, handleOptions } from "../../_lib/handlers.mjs";

export const onRequestPost = bindVerifyHandler;
export const onRequestOptions = handleOptions;
