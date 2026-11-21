/**
 * POST /api/bind/unbind —— 解绑即清（线路契约 §1.2）。
 * 为谁：已在本站绑定 ScholarMatrix、想解除跨站关联并物理清除本站画像快照的读者。
 * 前提：必须已登录本站（身份只从 ph_session cookie 解析，忽略 body 里的任何身份字段）。
 * 红线（解绑即硬删）：按 ph_subject 与 sm_subject 双方向物理删除 profile_snapshots
 *   与 ph_bindings，不留软删墓碑；本地会话本身保留（退出登录是 /api/account/logout 的职责）。
 * 出站：DELETE {SM_BASE}/api/pat/bind?by=ph&subject=ph:<本地用户 id>，带 X-PAT-Shared-Secret
 *   与 X-PH-Subject，8 秒上限。若 SM 回调失败或超时，本地硬删依然生效，并在响应
 *   smNotified:false / smNotifyNote 中如实告知原因，绝不假装远端也已清完。
 * 失败语义：401 NOT_AUTHENTICATED · 503 STORE_DISABLED · 500 DB_UNAVAILABLE；
 *   当前无绑定关系时返回 200 {ok:true, unbound:false}（幂等）。
 * 实现见 functions/_lib/handlers.mjs 的 bindUnbindHandler。
 */
import { bindUnbindHandler, handleOptions } from "../../_lib/handlers.mjs";

export const onRequestPost = bindUnbindHandler;
export const onRequestOptions = handleOptions;
