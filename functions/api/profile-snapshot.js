/**
 * /api/profile-snapshot —— SM 推送与清除画像快照的唯一入口（线路契约 §2 / §1.2）。
 * 为谁：POST 只服务 ScholarMatrix 服务器（服务器对服务器）；DELETE 同时服务
 *   SM 服务器的解绑回调与已登录读者自己的「清除我的数据」。
 * 红线（POST）：必须带 X-PAT-Shared-Secret 且与 PAT_SHARED_SECRET 逐字相等——
 *   头缺失、env 未配置、两边都是空串，一律拒绝（空 == 空不算通过）。
 *   body 里的 smSubject/phSubject 不许当身份用，只当"要写哪个主体"声明，
 *   仍要与 X-PH-Subject、与绑定表交叉核对，不能替别人写画像。
 * 红线（全链）：validateSnapshotPayload 是唯一守门人——禁存面（标题 / DOI /
 *   arXiv / 摘要 / URL / 阅读历史）与白名单不过就 400 带具体原因，绝不"洗白"入库。
 * 开关：env.PAT_HOT_STORE_USER_DATA !== "1" → 503 STORE_DISABLED（fork 默认不存用户数据）。
 * 失败语义：400 FIELD_FORBIDDEN / EXPIRES_* 等（带字段名）· 403 FORBIDDEN 无密钥无会话
 *   · 409 NOT_BOUND / SUBJECT_MISMATCH · 503 STORE_DISABLED · 500 DB_UNAVAILABLE。
 * DELETE 按 sm/ph 主体物理删除（profile_snapshots + ph_bindings），不留软删墓碑。
 * 实现见 functions/_lib/handlers.mjs 的 snapshotPutHandler / snapshotDeleteHandler。
 */
import {
  snapshotPutHandler, snapshotDeleteHandler, handleOptions,
} from "../_lib/handlers.mjs";

export const onRequestPost = snapshotPutHandler;
export const onRequestDelete = snapshotDeleteHandler;
export const onRequestOptions = handleOptions;
