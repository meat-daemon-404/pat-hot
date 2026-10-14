/**
 * GET /api/account/me —— 前端"我登录了吗"的探测口（线路契约 §1）。
 * 为谁：单页站点每次渲染都要知道该不该显示"按你的研究兴趣排序"和账号面板。
 * 红线：**没有会话不是错误**，按任务书返回 200 {ok:false, reason:"NO_SESSION"}——
 *   未登录是本站的默认态（数据面免鉴权可读），用 401 会让浏览器控制台在
 *   每个正常访问上都记一条红错，也逼前端去 catch 一个业务常态。
 *   身份只从 ph_session cookie 解析，query/body 里写什么都不认（契约 §0）。
 * 返回：有会话时给 user{id,subject,email,createdAt} + bound + smSubject +
 *   hasSnapshot + snapshot（前端据此决定要不要再请求 /api/profile）。
 * 失败语义：503 STORE_DISABLED（开关关着时探测也如实说开关关着，
 *   别让前端把"后端没配"演成"你没登录"）· 500 DB_UNAVAILABLE。
 * 实现见 functions/_lib/handlers.mjs 的 meHandler。
 */
import { meHandler, handleOptions } from "../../_lib/handlers.mjs";

export const onRequestGet = meHandler;
export const onRequestOptions = handleOptions;
