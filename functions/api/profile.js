/**
 * GET /api/profile —— 前端「查看 / 清除我的数据」面板的数据源（线路契约 §2 / §3）。
 * 为谁：已登录且已绑定 ScholarMatrix 的读者，来看"你到底替我存了什么"。
 * 前提：需有效会话 + 绑定记录；两者缺一个都如实说明（会话缺失 401，
 *   未绑定返回 ok 且 bound:false，"没有画像"与"没连上后端"必须区分开）。
 * 红线：只回**当前生效**的快照——过期判定用 ranking.snapshotActive，
 *   与前端重排用的是同一个函数，面板说"还生效"而列表不按它排序
 *   （或反过来）是用户能直接看见的不一致。
 *   回的是快照本体 + 字段计数（topics/categories/channels 各几项、存了什么计数键），
 *   面板据此把"存了什么"摊开给人看，不用用户去猜。
 * 失败语义：401 NOT_AUTHENTICATED · 503 STORE_DISABLED · 500 DB_UNAVAILABLE；
 *   无快照不算错误（200 + snapshot:null + 一句真原因 note）。
 * 实现见 functions/_lib/handlers.mjs 的 profileGetHandler。
 */
import { profileGetHandler, handleOptions } from "../_lib/handlers.mjs";

export const onRequestGet = profileGetHandler;
export const onRequestOptions = handleOptions;
