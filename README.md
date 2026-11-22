# PAT-HOT · 多学科科研与技术情报聚合系统

[![Pages Deploy](https://github.com/meat-daemon-404/pat-hot/actions/workflows/collect.yml/badge.svg)](https://github.com/meat-daemon-404/pat-hot/actions/workflows/collect.yml)
[![Live Cloudflare Pages](https://img.shields.io/badge/Cloudflare_Pages-pat--hot.pages.dev-F38020?logo=cloudflare)](https://pat-hot.pages.dev)
[![Live GitHub Pages](https://img.shields.io/badge/GitHub_Pages-sun--zihang.github.io%2Fpat--hot-222222?logo=github)](https://sun-zihang.github.io/pat-hot/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://github.com/meat-daemon-404/pat-hot)
[![Node Tests](https://img.shields.io/badge/Node_Tests-77%2F77_Passing-2ea44f?logo=nodedotjs)](https://github.com/meat-daemon-404/pat-hot/tree/master/tests/js)

> **PAT-HOT**（Physics · Astronomy · Tech · Materials · Chemistry · Medicine · Bio · CS · Math · Cross · News）是对标 **AI HOT** 工程体系构建的**多学科科研与前沿科技情报聚合、去重聚类、LLM 精筛摘要与学术联动平台**。系统通过零外库或纯标准库回退的采集管线，每日两次抓取 11 个频道的 60+ 权威信源（arXiv、Crossref、APS、OSA、Nature、Science、IEEE、PubMed、Hacker News、GitHub Trending 等），生成静态双面 API 契约产物与无框架 Web 工作台，并与 [智阅矩阵 ScholarMatrix](https://scholarmatrix.pages.dev) 实现双向文献锚点与账号画像联动。

## 在线访问与核心入口

| 部署端 | 访问地址 | 角色定位 |
| :--- | :--- | :--- |
| **Cloudflare Pages（主站）** | <https://pat-hot.pages.dev> | 完整静态前端 + Pages Functions（`/api/summarize`、`/api/auth/*`、`/api/sync/*`、`/api/bind/*`）+ D1 云同步 |
| **GitHub Pages（镜像）** | <https://sun-zihang.github.io/pat-hot/> | 纯静态多频道情报看板 + `/api/v1/*` 公开只读 JSON 数据契约 |
| **联动工作台（智阅矩阵）** | <https://scholarmatrix.pages.dev> | 跨站 `?add=` 文献一键入库、`papers-index.json` 文献索引消费与一次性绑定码画像同步 |

## 十一大情报频道（`config/channels.json`）

| 频道 ID | 名称 | 核心信源覆盖 |
| :--- | :--- | :--- |
| `tech` | 综合科技（默认主频） | Hacker News、GitHub Trending、Ars Technica、MIT Tech Review、IEEE Spectrum、The Verge 等 |
| `opto` | 光电与激光 | Optics Express、Optica、Applied Optics、Laser Focus World、arXiv `physics.optics`、SPIE 等 |
| `phys` | 物理学 | Physical Review Letters / X / A–E、Nature Physics、CERN、APS Physics、arXiv `cond-mat` / `quant-ph` / `hep-*` |
| `astro` | 天文与天体物理 | ApJ、MNRAS、A&A、NASA Breaking News、ESA、Universe Today、arXiv `astro-ph.*` |
| `mat` | 材料科学 | Nature Materials、Advanced Materials、Acta Materialia、Materials Today、arXiv `cond-mat.mtrl-sci` |
| `chem` | 化学与化工 | JACS、Angewandte Chemie、Nature Chemistry、Chemical Science、ChemRxiv、C&EN |
| `med` | 临床与医学 | NEJM、The Lancet、JAMA、BMJ、Nature Medicine、medRxiv、PubMed 核心临床期刊 |
| `bio` | 生命科学 | Nature、Science、Cell、Nature Biotechnology / Genetics、bioRxiv、eLife |
| `cs` | 计算机与 AI | arXiv `cs.AI` / `cs.LG` / `cs.CL` / `cs.CV` / `cs.SY`、HuggingFace Papers、ACM TechNews、OpenAI / Anthropic Research |
| `math` | 数学与统计 | Annals of Mathematics、Inventiones、JAMS、arXiv `math.*` / `stat.*`、Quanta Magazine (Math) |
| `cross` / `news` | 交叉学科 & 科技快讯 | PNAS、Nature Communications、Science Advances、综合前沿科技与产业政策快讯 |

## 核心架构与对标 AI HOT 工程特性

### 1. 多源韧性采集与双态回退（`collector/collect.py`）
- **零依赖回退（stdlib-only fallback）**：即使在未安装 `feedparser`、`requests`、`PyYAML` 的精简 Python 环境中，也能自动回退至 `urllib.request` + `xml.etree.ElementTree` 完成 RSS 2.0 / Atom / RDF 解析与采集。
- **跨网络环境抖动防护**：
  - GitHub Trending HTML 抓取失败时自动回退至 GitHub Search REST API（过去 7 天高星活跃仓库），附带 `X-GitHub-Api-Version: 2022-11-28` 并兼容 `GITHUB_TOKEN`。
  - Hacker News 官方 Firebase API 超时或阻断时，自动无缝切换至 `hn.algolia.com/api/v1/search`（`front_page`）。
  - Crossref REST API 强制携带 `mailto` 礼貌池参数与指数退避重试，避免 `429 Too Many Requests`。

### 2. 跨周期语义聚类、热度指数与信号分层
- **跨周期话题追踪**：融合 TF-IDF 词项权重、实体共现与多周期快照（`data/history/`），识别 `new`（新上榜）、`rising`（升温）、`hot`（高热）、`cooling`（降温）状态及 `trendPct` 变化率。
- **确定性角色与价值分层**：为每条情报赋予 `headline` / `Breakthrough` / `core` / `watch` 角色标签及多维评分，支持按时间窗口（24h / 3d / 7d / 30d）、信源类别、关键词、收藏夹及阅读状态实时过滤。

### 3. 双阶段 LLM 精筛、SelectBench 评测与 9 条零幻觉摘要门禁
- **采集期 LLM 精筛与中文摘要**：支持智谱 GLM / DeepSeek / OpenAI 兼容接口，具备 429 `Retry-After` 退避、连接池复用、熔断器（连续失败自动降级启发式规则，不阻塞构建）以及 `data/.llm_cache.json` 跨轮次持久化缓存（按 `channel + prompt_hash + model + item_key` 严格隔离，缓存命中 0 延迟）。
- **边缘侧实时 AI 解读（`functions/api/summarize.js` + `worker/pat-hot-llm.js`）**：
  - 对标 AI HOT 最新 `aihot-llm` Worker 规范，内置 **9 条反幻觉硬规则**（严禁把标题英文字母缩写拆字翻译、仅存在标题时必须以“仅据标题”或“标题显示”开头、严禁脑补未出现的数字/机构/融资金额、空泛标题必须原样指出信息不足）。
  - 统一启用 `thinking: { type: "disabled" }` 与 18 秒超时守卫，防止推理 token 挤占 `max_tokens: 400` 导致 JSON 截断。
  - 内置确定性后置清洗器 `sanitizeWording()`（自动剥离“赋能/抓手/闭环/护城河/颠覆/革命性/里程碑”等空洞套话）与 `normalizeSummaryPayload()`（标题回退模式下自动将 `summary` 裁剪至 65 字以内、`why` 裁剪至 45 字以内，且仅保留 1 条核心要点）。
- **离线评测基准（`scripts/eval_selection.py`）**：
  - 支持 `--channel` 按频道独立加载 `selection_system_prompt()` 与缓存命名空间，并提供 `tier_offset_sweep`（`{-6, -4, -2, 0, +2, +4, +6}`）阈值扫描。
  - 支持 `--compare <report_a.json> <report_b.json>` 对标 AI HOT `SelectBench` 输出双报告并排对比（Precision / Recall / F1 / LLM vs Heuristic 增量 Δ）以及 `--self-test` 离线回归自检。

### 4. 云端同步与智阅矩阵（ScholarMatrix）双向联动（`functions/api/` + `schema.sql`）
- **零信任密码学与会话安全（`functions/_lib/crypto.mjs`）**：基于 WebCrypto `PBKDF2-HMAC-SHA256`（100,000 次迭代，严格兼容 Cloudflare Workers 运行时上限与 Node 18+）与常数时间比较 `timingSafeEqualHex`，支持多设备收藏夹、已读状态、自定义过滤视图与偏好设置云端增量同步（`/api/sync/pull`、`/api/sync/push`）。
- **智阅矩阵跨站账号绑定与解绑（`/api/bind/*`）**：
  - 支持生成 10 分钟有效期的 8 位一次性绑定码（`/api/bind/issue-code`）、跨站凭据认领（`/api/bind/claim`）、画像快照推送（`/api/bind/push-profile`）、状态查询（`/api/bind/status`）以及完整解绑清理（`/api/bind/unbind`，同时支持已登录 Bearer Token 解绑与跨站 `X-Matrix-Bind-Secret` + `patUserId` 解绑）。
  - 完整记录 `paper_events` 学术互动流水并在解绑时清理 `external_bindings` 绑定映射。

## 快速开始

### 环境准备

```bash
git clone https://github.com/meat-daemon-404/pat-hot.git
cd pat-hot
python -m pip install -r requirements.txt
```

> 说明：`requirements.txt` 包含 `feedparser`、`requests`、`PyYAML`、`pytest`。若处于受限环境，直接运行 `python collector/collect.py --offline` 也可通过内置标准库回退模式完成完整构建。

### 常用开发与构建命令

| 场景 | 命令 | 说明 |
| :--- | :--- | :--- |
| **离线快照构建（推荐本地验证）** | `python collector/collect.py --offline --channel all` | 不发起外网请求，基于现有 `data/` 快照重新计算聚类、热度、站点资产与 `/api/v1/*` 产物 |
| **全频道实时采集构建** | `python collector/collect.py --channel all` | 抓取全部 11 个频道的 RSS/API 信源，生成 `dist/` 静态站点与 API 产物 |
| **单频道快速采集** | `python collector/collect.py --channel opto` | 仅采集并重建指定频道（如 `opto`、`phys`、`cs`） |
| **开启 LLM 精筛与摘要** | `GLM_API_KEY=xxx python collector/collect.py --channel all` | 使用智谱 `glm-4.7-flash`（或通过 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` 指定兼容接口）生成精筛评分与中文摘要 |
| **本地预览静态站点** | `python -m http.server 8080 --directory dist` | 启动本地 HTTP 服务访问 `http://127.0.0.1:8080` |
| **选品基准评测与对比** | `python scripts/eval_selection.py --self-test` | 运行离线 SelectBench 自检；也可传入 `--compare a.json b.json` 输出双报告对比表 |
| **线上双端契约一致性审计** | `python scripts/audit_live_contract.py --max-drift-hours 18` | 校验 GitHub Pages 与 Cloudflare Pages 线上 `/api/v1/*` 契约及 `generated_at` 跨端漂移 |

### 自动化测试门禁

```bash
# 1. 运行 Python 采集、聚类、跨站契约与 README 字段一致性测试（17 个测试文件）
pytest -q

# 2. 运行 Node.js 边缘函数、WebCrypto、绑定/解绑与 AI 摘要反幻觉测试（77 项测试）
node --test tests/js/*.test.mjs
```

## 目录结构与关键产物

```text
pat-hot/
├── collector/
│   └── collect.py               # 核心采集、去重、聚类、热度计算、LLM 精筛、静态站点与 API 生成器
├── config/
│   ├── channels.json            # 11 个学科/科技频道元数据、色板与信源映射
│   ├── sources.yaml             # 60+ 权威 RSS / Atom / REST API 信源定义与权重配置
│   └── keywords.yaml            # 学科高价值关键词、突破性信号词与降权噪声词表
├── web/
│   ├── index.html               # 响应式单页情报工作台模板（无前端框架构建依赖）
│   ├── style.css                # 亮/暗双主题、学科色板与高密度卡片样式
│   ├── app.js                   # 多频道切换、全文检索、智阅矩阵联动、AI 摘要弹窗与云同步客户端
│   └── sw.js                    # Service Worker 离线缓存与静态资源加速
├── functions/                   # Cloudflare Pages Functions 边缘后端
│   ├── _lib/                    # WebCrypto PBKDF2 (100k)、JWT/Session、CORS、Turnstile 与 HTTP 工具
│   └── api/
│       ├── summarize.js         # /api/summarize 边缘 AI 摘要（9 条反幻觉门禁 + 套话清洗 + 18s 超时）
│       ├── auth/                # /api/auth/{register,login,logout,me} 账号认证体系
│       ├── sync/                # /api/sync/{pull,push} 收藏夹、已读、视图与偏好增量同步
│       └── bind/                # /api/bind/{issue-code,claim,status,push-profile,unbind} 智阅矩阵双向绑定
├── worker/
│   └── pat-hot-llm.js           # 独立 Cloudflare Worker 版 AI 摘要网关（与 functions/api/summarize.js 逻辑同源）
├── scripts/
│   ├── eval_selection.py        # SelectBench 选品评测、tier_offset 扫描与 --compare 双报告对比工具
│   └── audit_live_contract.py   # 线上 GitHub Pages / Cloudflare Pages 契约一致性与时效漂移审计脚本
├── schema.sql                   # Cloudflare D1 数据库 Schema（users / sessions / user_state / external_bindings / paper_events）
├── data/                        # 最新采集快照与历史归档（items.json / hot-topics.json / stories.json / stats.json）
└── tests/                       # pytest 测试套件（17 个模块）+ tests/js/ Node 测试套件（77 项断言）
```

## 数据契约与字段规范（`/api/v1/` & `data/`）

构建产物在 `dist/data/` 与 `dist/api/v1/<channel>/` 下同步输出，供前端工作台与第三方学术工具（如智阅矩阵 ScholarMatrix）直接消费。各核心 JSON 产物的顶层与条目字段契约如下（由 `tests/test_doc_fields.py` 自动校验）：

- data/items.json：{id, title, url, links.original, source, category, published_at, discovered_at, score, selected, summary, role, keywords, refs?}（条目字段是 snake_case；published_at 可为 null）
- data/hot-topics.json：{rank, title, status, trend, trendPct, badges, heat, source_count, signal_count, latest_at, sources, links, terms, representative.refs?}（混合命名：trendPct / digestTitle 是 camelCase 例外，计数与时间字段是 snake_case；stories.json 则整份是 camelCase——三份产物别互相类推）
- `dist/api/v1/<channel>/papers-index.json`：专为学术联动提供的扁平化论文索引，包含 `doi`、`arxiv_id`、`pmid`、`title`、`url`、`channel`、`published_at` 与 `refs` 规范化学术标识符。
- `dist/api/v1/channels.json` 与 `dist/api/v1/manifest.json`：全局频道目录、构建时间戳（`generated_at`）、端点清单与各频道信号计数。

## 自动构建与部署流水线

- **定时采集（`.github/workflows/collect.yml`）**：GitHub Actions 每日定时运行两次，cron 表达式为 `17 22,10 * * *`（即 UTC 时间 `22:17` 与 `10:17`，对应北京时间 **每日 `06:17` 与 `18:17` UTC+8**），同时支持 `workflow_dispatch` 手动触发。
- **双端发布**：采集完成后自动将最新 `data/` 快照提交回仓库，并同步部署至 GitHub Pages（`https://sun-zihang.github.io/pat-hot/`）与 Cloudflare Pages（`https://pat-hot.pages.dev`）。

## 许可证

本项目基于 [MIT License](LICENSE) 开源。
