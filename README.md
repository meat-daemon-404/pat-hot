# PAT-HOT · 物理·天文·光电热点统计

以 [AIHOT](https://aihot.virxact.com) 为模板的开源三频道热点统计工具：**P 物理** / **A 天文** / **T 光电**。

> **在线报告（GitHub Pages）**：https://sun-zihang.github.io/pat-hot/
>
> **在线报告（Cloudflare Pages）**：https://pat-hot.pages.dev

自动采集公开网络上的物理、天文、光电产业资讯，去重分类、聚类打分，输出热点榜 / 精选 / 分类统计 / 每日趋势，并生成可离线打开的中文 HTML 报告。

## 特性

- **三频道**：P 物理（凝聚态/高能粒子/AMO/量子信息等）、A 天文（系外行星/宇宙学/引力波/深空探测等）、T 光电（原有光电频道），各频道独立采集、聚类、日报，站内一键切换
- **时间窗口**：24 小时 / 7 天精选，优先采用原文发布时间，缺失时回退为收录时间（AIHOT 时间轴语义）
- **领域分类**：激光、光通信、显示与面板、光电芯片与半导体、光学元件与成像、光传感与激光雷达、光伏与新能源、科研进展、产业与资本、通信与算力
- **热点榜**：按「跨源收敛度 / 独立来源数 / 48 小时报道密度」加权打分；事件内同一来源 48 小时只计一次，防单源刷榜；**语义向量聚类**（TF-IDF 字符/词/领域特征 + 余弦，可选真嵌入）合并同一事件，减少噪声主题
- **代表报道**：同一事件多篇报道折叠为一篇代表（官方一手源优先 → 有全文 → 分数高 → 发布早），其余在"另有 N 家信源报道"下展开
- **分级精选**：信源分 official（官方/协会/政府）/ media（媒体）两级，精选门槛不同（官方 ≥55，媒体 ≥65，可在 `collector/config.json` 调整）
- **旧文不刷屏**：无可信发布时间的条目时效分打折，不再全额回退收录时间
- **日报编排**：头条 1 条 + 今日看点 2–4 条 + 快讯；同一信源在正文最多 2 条；近 7 天已出现过的事件不再入正文
- **零依赖**：仅用 Python 标准库；HTML 报告为自包含单文件（无 CDN / 无外部资源）
- **可选 LLM 增强**（`--llm`，默认关闭）：接商汤日日新 SenseNova（`sensenova-6.8-flash-lite`），为精选条目生成一句话中文摘要、推荐理由、信息密度标签（低密度营销稿自动降权）；Key 只从环境变量 `SENSENOVA_API_KEY` 读取，失败自动降级
- **可选生图**（`--images`，默认关闭）：接 SenseNova U1.5 Lite 文生图（`watermark=false` 去水印），为日报头条 + 热点榜 Top5 生成配图，存 `dist/assets/img/`；失败自动降级为无图
- **配置外置**：评分权重、精选门槛、聚类阈值、日报编排参数全部集中在 `collector/config.json`，调标准不改代码
- **AIHOT 风格 UI**：九个视图（精选时间线 / 全部动态 / 热点榜 / 光电日报 / 主题 / 趋势 / 数据 / Agent 接入 / 更多），浅色卡片风、侧边导航、评分与热度徽章，移动端自适应
- **日报归档机制**：自动按天生成光电日报（今日看点 TOC + 分类文章 + 日历归档），历史归档按日期/月份回看
- **多语言与交互**：中 / English 一键切换；图表 tooltip；热点榜按热度/信源排序；搜索 + 分类 + 排序
- **本地数据可备份**：已读、收藏、主题、语言、频道只存在这台浏览器（清缓存即丢）；收藏页可**导出**为 JSON 备份、换设备后**导入**恢复（AIHOT 的本地数据 + 导出备份口径）。导出的文件带 `app:"PAT-HOT"` 标记，别的文件会被拒绝且不动现场
- **Agent 接入**：免鉴权静态 JSON API（`api/v1/<频道>/*`，频道：physics/astro/tech；重构前的扁平 `api/v1/*` 仍保留兼容）+ OpenAPI 3.1 + 分类 RSS feed + `llms.txt` + 可安装 Skill（`agent/skills/opto-hot`）
- **手机适配**：响应式布局（窄屏单列、顶部搜索、横向导航），移动端可正常浏览
- **自动化**：内置 GitHub Actions，每天 6:00 / 18:00（北京时间）自动刷新数据并提交
- **趋势追踪**：周维度聚合（本周 vs 上周分类热度、新上榜/持续发酵事件），独立趋势视图
- **LLM 深挖**（可选）：两次独立打分定精选资格 + 结构化抽取（主体/事件/标签），prompt 全部外置


## UI 与机制（对标 AIHOT）

| 视图 | 对应 AIHOT 页面 | 说明 |
|---|---|---|
| 精选 #/ | /（精选） | 按日分组的资讯时间线：来源、时间、分类徽章、推荐分、精选标记 |
| 全部动态 #/all | /all | 全部条目，支持关键词搜索 + 分类筛选 + 按推荐分/时间排序，无限滚动分页 |
| 热点榜 #/hot | /hot | 排名 + 状态（爆/发酵中/关注中）+ **运动徽标（新/升温/多家跟进/回落，AIHOT 与 6h 前比的静态版：与上一轮发布比）** + 信源数/信号数/热度值 + 信源展开 |
| 光电日报 #/daily | /daily | 报头 + 今日看点 TOC + 分类文章 + 日历归档 |
| 主题 #/topics | /topics | 分类卡片（24h/7d/总数），点击进入筛选 |
| 趋势 #/trends | /trends | 分类热度涨跌条、新上榜事件、持续发酵事件 |
| 数据 #/data | - | 统计卡片、14 天趋势、来源表、CSV/JSON 下载 |
| Agent 接入 #/agent | /agent | API 端点 + RSS + OpenAPI + curl 示例 + Skill 说明 |
| 更多 #/more | - | 语言/频道等次要入口收纳（窄屏） |

**数据机制**（静态 JSON API，兼容 AIHOT 字段风格）：
- data/items.json：{id, title, url, links.original, source, category, published_at, discovered_at, score, selected, summary, role, keywords}（条目字段是 snake_case；published_at 可为 null）
- data/hot-topics.json：{rank, title, status, trend, trendPct, badges, heat, source_count, signal_count, latest_at, sources, links, terms}（混合命名：trendPct / digestTitle 是 camelCase 例外，计数与时间字段是 snake_case；stories.json 则整份是 camelCase——三份产物别互相类推）
- data/dailies.json：按日期归档的日报（历史合并保留）；data/daily.json：统计聚合
- **Agent 接口**：`api/v1/{items,hot-topics,dailies,daily,stories,index,openapi}.json`（静态 JSON / OpenAPI 3.1，免鉴权）+ 分类 RSS（`feed.xml` / `feed/category/{slug}.xml`）+ 站点根 `llms.txt`
- 时间窗口语义：优先原文发布时间，缺失回退收录时间；24h / 7d / 日报按北京时间

**相比 AIHOT 的改进**：
- 打分公式透明可复现（AIHOT 为「AI 编辑部评分」，本工具公式见下）
- 光电行业专属分类（10 类）与领域词表
- 完全离线可用（单文件 HTML + 内嵌数据），无需后端
- 开源 + MIT + GitHub Actions 自动刷新
## 快速开始

```bash
git clone https://github.com/sun-zihang/pat-hot.git
cd pat-hot
python collector/collect.py          # 需要联网；Python 3.8+
```

跑完可用 `python collector/collect.py --check` 自检对外契约（所有已发布端点是否就位、形状是否正确），CI 在提交前会强制这一关。

生成产物：

| 文件 | 说明 |
|---|---|
| `dist/index.html` | AIHOT 风格单页应用（九视图，三频道数据全部内嵌，可离线打开） |
| `data/<频道>/items.json` | 全部采集条目（含分类、关键词、得分、tier、selected） |
| `data/<频道>/hot-topics.json` | 热点榜（rank / 状态 / 来源数 / 信号数 / 链接） |
| `data/<频道>/daily.json` | 统计：分类、每日趋势、来源分布 |
| `data/<频道>/dailies.json` | 日报归档（按日期，历史不可变） |
| `data/<频道>/trends.json` | 周维度趋势（本周 vs 上周、新上榜、持续发酵） |
| `data/<频道>/report.csv` | 条目 CSV 导出（Excel 可直接打开） |
| `dist/api/v1/<频道>/*.json` | 按频道的静态 JSON API（含 `stories.json`） |
| `dist/api/v1/*.json` | 重构前的扁平兼容地址，内容 = T 光电频道 |
| `data/dailies.json` 等 | 扁平兼容副本，同上，勿删 |

常用参数：

```bash
python collector/collect.py --limit 30   # 每个源最多取 30 条
python collector/collect.py --topics 15  # 热点榜输出 15 条
python collector/collect.py --channel tech     # 只跑光电频道（其余频道沿用上次的产物）
python collector/collect.py --skip-html  # 跳过行业网站（只跑 RSS）
python collector/collect.py --check      # 只自检对外契约，不采集不写文件
python collector/collect.py --llm        # 可选：SenseNova LLM 增强（需 SENSENOVA_API_KEY）
python collector/collect.py --images     # 可选：SenseNova 生图配图（需 SENSENOVA_API_KEY）
```

## 集中配置

`collector/config.json` 集中了评分权重（`scoring`）、信源分级与精选门槛（`tiers`）、热度参数（`heat`）、
聚类阈值（`clustering`）、日报编排与归档保留（`daily`）、抓取超时与失败率闸门（`fetch`）、趋势（`trends`）、
LLM 增强（`llm`）与生图（`images`）的全部参数。
调标准只改这个文件，不用改代码；删除该文件或留空字段会自动回退内置默认值。

| 段落 | 关键参数 | 作用 |
|---|---|---|
| `scoring` | `w_source / w_convergence / w_signal / w_recency`、`missing_pubdate_penalty` | 条目打分权重与无可信发布时间时的时效惩罚 |
| `tiers` | `official / media` 的 `select_threshold` | 分级精选门槛（55 / 65） |
| `heat` | `recent_hours / source_cap / signal_cap / status_*` | 热点榜热度与「爆 / 发酵中 / 关注中」判定 |
| `clustering` | `tfidf_threshold` | 语义聚类合并阈值 |
| `daily` | `headline_count / picks_count / flash_count / max_per_source / dedup_window_days / per_category_limit` | 日报编排 |
| `daily` | `archive_days`（默认 365） | 日报归档保留天数，超期自动剪枝 |
| `daily` | `refresh_days`（默认 1） | 归档刷新窗口：近 N 天按重算刷新，更早的历史原样保留 |
| `fetch` | `timeout / retries / text_timeout / max_bytes` | 单源超时、抖动重试次数、详情页超时、响应体积上限 |
| `fetch` | `max_source_failure_ratio`（默认 0.6） | 失败源占比超过即拒绝写出产物，避免发布内容变薄的站点 |
| `trends` | `lookback_days / sustained_min_days / top_new / top_sustained` | 周维度趋势聚合 |
| `images` | `retention_days` | 生成配图的保留天数（仅图片，与日报归档无关） |

**日报归档语义**：已发布的历史某天不会被后续运行改写。当天与 `refresh_days` 内的近期天按本次重算刷新，
但**已对外发布的条目一条都不会少**——源站 feed 会滚动，某条目本次可能已不在列表里，
覆盖式重算会把已公开条目挤出 Top-N，所以合并时会把它们找回。

信源分级在 `collector/sources.json` 中每个源的 `tier` 字段声明：`official`（官方/协会/政府/一手）
或 `media`（媒体），精选门槛分别为 55 / 65 分。

## 可选：LLM 增强与生图（默认关闭，零费用）

- LLM 增强（`--llm`）：调用商汤日日新 SenseNova OpenAI 兼容接口
  `https://token.sensenova.cn/v1/chat/completions`（模型 `sensenova-6.8-flash-lite`，
  模型 ID 以商汤控制台为准，可用 `SENSENOVA_MODEL` 环境变量覆盖），
  为高分条目生成一句话中文摘要、推荐理由、信息密度标签（高/中/低，低密度营销稿自动降权 0.9）。
- 生图（`--images`）：调用 SenseNova U1.5 Lite 文生图接口
  `https://token.sensenova.cn/v1/images/generations`（模型 `sensenova-u1.5-lite`，
  以商汤控制台为准，可用 `SENSENOVA_IMAGE_MODEL` 环境变量覆盖；调用传 `watermark=false` 去水印），
  为日报头条 + 热点榜 Top5 生成配图，存 `dist/assets/img/`（按日期+事件 id 命名，超 `retention_days` 天自动清理）。
- **两次独立打分**（AIHOT 方法论）：对高分候选条目用两种视角（行业编辑 / 投资分析师）各打一次 0–100，
  取平均为 `llm_score`；平均分低于所属 tier 精选门槛的不进精选。页面分数徽标优先展示 AI 均值（带 AI 角标）。
- **先补材料再打分**（AIHOT 纪律：不凭标题打分）：摘要不足 `llm.material_min_summary` 字的评分候选，
  打分前有界抓取详情页正文（`material_max_fetch` 全频道上限、`material_per_source` 单源上限），
  仅作为模型输入；抓取正文**不发布**（AIHOT site_fulltext 许可口径：站内默认只展示摘要 + 原文链接，
  全文需信源明确允许），落盘前自动剥离。
- **LLM 时间预算熔断**（`llm.budget_seconds`，默认 360）：上游半死不活时在预算内收尾——
  已增强条目照常发布，低分尾部留给下次刷新。2026-10-13 实测事故：无预算时逐批退避无限累加，
  采集挂近 5 小时并堵死全部后续定时刷新；步骤级超时只把挂死换成失败，换不回数据发布。
- **配置漂移提醒**：`collector/config.json` 的 `llm` 段覆盖内置默认值——历史上出过
  "只改默认值没改 config.json，调优从未生效"的事故（680da69 / batch 8→3）。改任何一侧都要同步另一侧。
- **结构化抽取**：对入选条目抽取 `entities`（公司/机构）、`event`（谁做了什么，一句话）、`tags`（标签），
  存入条目 JSON（只增字段），页面条目卡片直接展示。
- Prompt 全部外置在 `collector/config.json` 的 `prompts` 段（`score_a` / `score_b` / `extract`），
  `{listing}` 为条目列表占位符；调评分/抽取标准只改配置，不用改代码。
- Key **绝不写进代码/仓库**，只从环境变量 `SENSENOVA_API_KEY` 读取；
  无 key、超时、配额不足等任何失败都会静默降级（跳过增强/无图），不阻断主流程。
- GitHub Actions 默认**不启用**（不产生费用）。如需启用：仓库 Settings → Secrets 添加
  `SENSENOVA_API_KEY`，并在工作流的采集命令后加上 `--llm` / `--images`，例如：
  `python collector/collect.py --limit 25 --llm`。

## 数据源（45 个：36 RSS + 9 HTML）

按频道划分：**T 光电 26 · P 物理 9 · A 天文 10**（`collector/sources.json` 的 `channel` 字段决定归属）。

| 频道 | 类型 | 名称 | 地址 | 权重 | 分级 |
|---|---|---|---|---|---|
| T 光电 | HTML | CIOE 中国光博会 | `https://cioe.cn/` | 0.9 | official |
| T 光电 | HTML | COEMA 中国光电子行业协会 | `https://www.coema.org.cn/` | 0.8 | official |
| T 光电 | HTML | LEDinside 中文 | `https://www.ledinside.cn/` | 0.9 | media |
| T 光电 | HTML | OFweek 光电频道 | `https://optics.ofweek.com/` | 1.0 | media |
| T 光电 | HTML | OFweek 激光频道 | `https://laser.ofweek.com/` | 1.0 | media |
| T 光电 | HTML | 中国招标投标公共服务平台 | `http://www.cebpubservice.com/` | 0.8 | official |
| T 光电 | HTML | 中国政府采购网 | `https://www.ccgp.gov.cn/` | 0.8 | official |
| T 光电 | HTML | 工信部要闻（标题词过滤） | `https://www.miit.gov.cn/` | 0.8 | official |
| T 光电 | HTML | 搜狗微信·光电行业（标题词过滤） | `https://weixin.sogou.com/weixin?type=2&query=%E5%85%89%E7%9…` | 0.7 | media |
| T 光电 | RSS | C114中国通信网_IT资讯 | `http://www.c114.com.cn/rss/rss_news_27.xml` | 0.8 | media |
| T 光电 | RSS | C114中国通信网_监管 | `http://www.c114.com.cn/rss/rss_news_550.xml` | 0.7 | media |
| T 光电 | RSS | C114中国通信网_要闻精选 | `http://www.c114.com.cn/rss/rss_news_489.xml` | 0.9 | media |
| T 光电 | RSS | C114中国通信网_设备商 | `http://www.c114.com.cn/rss/rss_news_18.xml` | 0.9 | media |
| T 光电 | RSS | C114中国通信网_通信财经 | `http://www.c114.com.cn/rss/rss_news_24.xml` | 0.9 | media |
| T 光电 | RSS | EDN 电子工程专辑（关键词过滤） | `https://www.edn.com/feed/` | 0.6 | media |
| T 光电 | RSS | IEEE Spectrum（关键词过滤） | `https://spectrum.ieee.org/rss/fulltext` | 0.7 | media |
| T 光电 | RSS | LEDinside 英文 | `https://www.ledinside.com/rss` | 0.8 | media |
| T 光电 | RSS | Laser Focus World | `https://www.laserfocusworld.com/__rss/website-scheduled-con…` | 0.8 | media |
| T 光电 | RSS | Nature Photonics | `https://www.nature.com/nphoton.rss` | 0.9 | official |
| T 光电 | RSS | Phys.org 物理新闻（关键词过滤） | `https://phys.org/rss-feed/physics-news/` | 0.6 | media |
| T 光电 | RSS | Physics World（关键词过滤） | `https://physicsworld.com/feed/` | 0.7 | media |
| T 光电 | RSS | YouTube·Edmund Optics（关键词过滤） | `https://www.youtube.com/feeds/videos.xml?channel_id=UCA3_rC…` | 0.6 | media |
| T 光电 | RSS | YouTube·Photonics Media（关键词过滤） | `https://www.youtube.com/feeds/videos.xml?channel_id=UCEBZpt…` | 0.6 | media |
| T 光电 | RSS | YouTube·SPIETV（关键词过滤） | `https://www.youtube.com/feeds/videos.xml?channel_id=UC0GnZ4…` | 0.6 | media |
| T 光电 | RSS | YouTube·Thorlabs（关键词过滤） | `https://www.youtube.com/feeds/videos.xml?channel_id=UCS0b3D…` | 0.6 | media |
| T 光电 | RSS | arXiv 光学与光子学 (physics.optics) | `http://export.arxiv.org/rss/physics.optics` | 0.8 | official |
| P 物理 | RSS | CERN 新闻 | `https://home.cern/news/rss` | 0.7 | official |
| P 物理 | RSS | MIT News 物理 | `https://news.mit.edu/rss/topic/physics` | 0.7 | official |
| P 物理 | RSS | Nature Physics 学科聚合 | `https://www.nature.com/subjects/physics.rss` | 0.7 | official |
| P 物理 | RSS | Nature 量子物理 | `https://www.nature.com/subjects/quantum-physics.rss` | 0.7 | official |
| P 物理 | RSS | New Scientist 物理 | `https://www.newscientist.com/subject/physics/feed/` | 0.7 | media |
| P 物理 | RSS | Phys.org 物理新闻 | `https://phys.org/rss-feed/physics-news/` | 0.7 | media |
| P 物理 | RSS | Quanta Magazine | `https://www.quantamagazine.org/feed/` | 0.7 | media |
| P 物理 | RSS | arXiv quant-ph 论文速递 | `https://arxiv.org/rss/quant-ph` | 0.4 | official |
| P 物理 | RSS | 知识分子 | `http://www.zhishifenzi.com/rss` | 0.7 | media |
| A 天文 | RSS | Astronomy Magazine | `https://www.astronomy.com/feed` | 0.7 | media |
| A 天文 | RSS | ESA 空间科学 | `https://www.esa.int/rssfeed/Our_Activities/Space_Science` | 0.7 | official |
| A 天文 | RSS | LIGO | `https://www.ligo.org/feed/` | 0.7 | official |
| A 天文 | RSS | MIT News 太空探索 | `https://news.mit.edu/rss/topic/space-exploration` | 0.7 | official |
| A 天文 | RSS | NASA 快讯 | `https://www.nasa.gov/rss/dyn/breaking_news.rss` | 0.7 | official |
| A 天文 | RSS | Nature 天文和天体物理 | `https://www.nature.com/subjects/astronomy-and-astrophysics.rss` | 0.7 | official |
| A 天文 | RSS | New Scientist 太空 | `https://www.newscientist.com/subject/space/feed/` | 0.7 | media |
| A 天文 | RSS | Phys.org 太空新闻 | `https://phys.org/rss-feed/space-news/` | 0.7 | media |
| A 天文 | RSS | Universe Today | `https://www.universetoday.com/feed/` | 0.7 | media |
| A 天文 | RSS | arXiv astro-ph.CO 论文速递 | `https://arxiv.org/rss/astro-ph.CO` | 0.4 | official |

> X/Twitter 为**可选源**（默认不启用）：`collector/sources.json` 顶部 `_x_twitter_optional`
> 有配置示例。RSSHub 的 `/twitter/user/:id` 路由需要自建 RSSHub 实例（或可用的公共实例），
> 且 X 反爬严格、可能需要登录态；启用时把示例对象加入 `rss` 数组即可。
>
> 抓取说明：COEMA 页面实际为 GBK 编码（meta 声明为 utf-8）；OFweek 为 GB2312；C114 RSS 为 GBK 编码的 RSS 2.0；Nature Photonics 为 RSS 1.0 (RDF)。采集器已做对应处理。源配置在 `collector/sources.json`，可自由增删。
>
> 分级说明：`tier=official`（官方/协会/政府/一手）18 个、`tier=media`（媒体）27 个，精选门槛分别为 55 / 65 分。

## 打分模型（透明可复现）

- 条目得分 = `w_source × 来源权重 + w_convergence × 跨源收敛度 + w_signal × min(1, 主题信号数/10) + w_recency × 时效`，默认权重 45 / 20 / 15 / 20；其中时效 = `max(0, 1 − 距今天数/30)`。**时效不可信就打折**（×`missing_pubdate_penalty`，默认 0.5）：没有发布时间、有却解析不出来、或粒度粗于"天"（url_date 只能从链接抠出年月，如 `2026-09`）都算不可信——宁可把旧文读旧，也不让 2022 年的文章按"今天刚收录"拿满时效分挤进精选
- **时间口径**（对标 AIHOT：中文网页时间不带时区时按信源时区读，默认 +08:00）：裸日期时间按信源补全时区（中文站 +08:00、海外站 UTC），显式 `Z` / `+0000` 永远按 UTC；`CST` 这类具名时区缩写按信源消歧（域名优先于中文名，`CST` 对中文信源读北京时、其余读美国中部时）。月级/年级发布时间取该区间**最早时刻**
- 跨源收敛度 = `min(1, 事件独立来源数/6)`：同一事件被越多独立来源报道，得分越高，防单源刷榜
- 主题热度 = `100 × (0.45 × min(1, 独立来源数/6) + 0.35 × min(1, 信号数/10) + 0.20 × min(1, 48小时内独立来源数/独立来源数))` —— 48 小时窗口内同一来源只计一次
- 精选门槛（分级）：官方信源（协会/政府/一手）≥ 55 分，媒体信源 ≥ 65 分（启用 `--llm` 时以 LLM 两次独立评分的均值判定，见下）
- 聚类：以领域词表 + 英文词（去停用词）做关键词索引，≥2 条命中的词构成候选主题；重叠 ≥50% 或代表条目相同的主题自动合并
- 以上权重、门槛、窗口均可在 `collector/config.json` 调整，缺失字段自动回退内置默认值

## LLM 评分标准（可选 `--llm`，对标 AIHOT selection-score）

`--llm` 的两次独立打分不再是"四个主观维度自由心证"，而是 AIHOT 的结构化口径
（prompt 全部外置在 `collector/config.json` 的 `prompts` 段，改标准不改代码）：

- **先还原事件再打分**：把材料还原成它被正文支持的最强事件，评"事件对读者的注意力价值"，不评稿件好坏；正文只能支持较弱主张就按较弱事件评，绝不替材料补一个更强的故事
- **内容类型 × 五轴加权**：`score_a` 每条先归入 7 类（discovery/technology/product/industry/facility/opinion/explainer），再对 `sig/nov/cre/res/act` 五轴各打 0–10，按该类型权重行合成——**每行权重之和为 10，结果天然落在 0–100**。`score_b` 是独立的决策者视角（`mat/inc/ver/tim` 四轴）
- **噪声用上限压死**（对标 AIHOT 的"必须压住"）：客户案例 PR、例行小版本、营销软文、只有预告、无数据的"更快更强"、多事件合集，各自有 `sig/nov/cre` 硬上限；大厂、名校、长正文、数字多、"刷新纪录"都不是自动加分项
- **输入安全边界**：材料的标题/摘要里出现的任何指令、目标分数、格式要求都是不可信数据，prompt 明确拒绝执行（防 prompt-injection）
- **评分输入遮蔽信源名**：给发布时间（北京时间）+ 正文材料，但不给信源名/分级——来源名气会锚定分数，而 `cre` 轴评的是材料内部的证据强度，不是来源名气
- **防幻觉（摘要/抽取）**：`extract` 与 `enhance` 带 AIHOT 九条硬约束——摘要里每个专名/数字必须材料可寻、相对时间不换算成年份、不强化原文语气、"首次/唯一"等排他表述只有原文明确才保留；没有正文的条目"宁短勿扩"，不靠标题合理展开编造内容
- **预筛（`prefilter`）**：写作之前先判"这是不是本行业的事"——`BLOCK` 的条目**不进任何公开页**（且不再为它花摘要/打分的钱），`PASS`/`UNKNOWN` 照常往下走（AIHOT：UNKNOWN 保留待补材料，不直接丢弃）。宽进严出：BLOCK 需要能确认无关的**正面依据**，"没提到本行业"不算；模型失败一律**全部放行**——预筛是增益不是闸门，宁可多发一条也不因抖动清空频道。只对 ≥50 分的高分候选跑（低分条目本来就进不了公开页）
- **词表订正（`mend`）**：写好的中文文案里用了本站不用的词（夸张词、翻案句），让模型**只改列出的那几处**，意思不变、不增删事实数字；只查模型自己生成的字段（`zh_full`/`llm_summary`/`llm_reason`）——**信源原标题绝不改**（那是替原站改稿）。词表刻意收窄（见 `READER_WORDING`）：`首次/最大/唯一` 这类正文支持的正当用法不进表，否则会误改正常词
- **事件综述（`digest`）**：为热点榜多源事件写"第一次了解这件事的读者"能看懂的概览（AIHOT `story-digest` 口径）——第一句直接说清核心变化与结论、不按日期逐条复述、只写报道里有的事实、新旧矛盾要写明不能悄悄抹平。实测：光电热点事件平均 11.6 篇报道，此前页面只有一句代表稿摘要。单源事件不写（没有综述可言）

## 精选门槛校准（改了标准，先校准再上线）

`tiers.select_threshold`（55/65）和评分 prompt 是"标准"，两者必须互相校准——
AIHOT 的纪律：**先改标准、再动门槛；门槛只能整体平移，解决不了"哪一类判错了"**。
`scripts/eval_selection.py` 是这套纪律的纯标准库实现：

1. 从你的信源挑 100–200 条，逐条标"该选 / 不该选 / 两可"，存 `.data/gold.jsonl`
   （不进 Git；格式见 `scripts/gold.example.jsonl`）。多放难例；评测只看单条
   该不该选，不因同事件已选过另一篇就标"不该选"
2. 跑评测（需 `SENSENOVA_API_KEY`，真调模型，无 key 直接退出、绝不伪造结果）：
   `python scripts/eval_selection.py --label 第一版评分标准`
3. 看指标：查准 / 查全 / F1、**覆盖率**、**完整准确率**（模型失败也算没做对，
   失败样本不许从分母里消失——高分但经常答不合格式的模型不该被吹成好模型）、
   40→90 门槛扫描，错例与逐条结果写到 `.data/eval/`
4. 判错的"该选没选上"→ 把这类价值写进 prompt 的"必须正常评价"；
   "不该选却选上"→ 写进"必须压住的噪声"；改完再跑，两版报告并排对比
5. 同一条材料重跑走 `.data/eval-cache.json` 的内容哈希缓存，不重复花钱
   （AIHOT 回执语义的静态版）

## 与 AIHOT 的已知差距（刻意不移植）

AIHOT 是 Node/TypeScript + PostgreSQL 的服务端框架（api/worker/web 三进程 + 任务队列），
本站是零依赖 Python 静态生成器（单文件 HTML + 静态 JSON + GitHub Pages）。以下能力
依赖持久服务或数据库，与"打开即看、离线可用"的架构冲突，不移植：付费调用回执与
预算熔断、后台管理/内容诊断/SelectBench 并排对比、MCP 服务端、事件页模型综述的
在线生成、周报月报自动汇编出刊（本站数据量下日报已覆盖）。可移植的**方法论**——
评分结构化、日期时区口径、防幻觉纪律、校准闭环、旧文不刷屏——已全部落地在上两节。
不使用 AIHOT 的名字与 Logo（其 MIT 授权不含品牌）。

## 趋势模块

基于 `data/<频道>/dailies.json` 的周维度聚合，不新增采集，每次运行自动生成 `data/<频道>/trends.json`
（同步到 `dist/data/<频道>/trends.json` 与 `api/v1/<频道>/trends.json`，另在兼容地址
`dist/api/v1/trends.json` 提供 T 光电频道内容）：

- **本周 vs 上周**：各分类热度（文章 score 求和）变化，涨跌百分比
- **新上榜事件**：本周首次出现的事件（同一事件跨天只算一件）
- **持续发酵事件**：近 14 天内出现 ≥3 天的事件

页面新增 **趋势** 视图（📈）：分类热度涨跌条、新上榜事件、持续发酵事件。
参数在 `collector/config.json` 的 `trends` 段（回看天数、持续天数阈值、展示条数）。

## 目录结构

```
pat-hot/
├── collector/
│   ├── collect.py        # 主脚本：采集→清洗去重→分类→打分→聚类→日报/趋势→输出
│   ├── channels.json     # 三频道定义（P 物理 / A 天文 / T 光电）
│   ├── sources.json      # 数据源配置（RSS / HTML 解析规则 + tier 分级 + channel 归属）
│   ├── config.json       # 集中配置：评分权重/精选门槛/聚类阈值/日报编排/抓取/LLM与生图
│   └── templates/        # 单页站点模板（app.html / app.css / app.js，构建时内联）
├── data/<频道>/          # 采集产物：items / hot-topics / daily / dailies / trends / report.csv
├── dist/                 # 部署产物（GitHub Pages 根目录）
│   ├── index.html        # 三频道单页，数据全部内嵌，可离线打开
│   ├── api/v1/<频道>/    # 按频道的静态 JSON API
│   ├── api/v1/*.json     # 重构前的扁平地址，内容 = T 光电频道（向后兼容，勿删）
│   ├── feed.xml          # 主 RSS（T 光电）
│   ├── feed/<频道>/category/*.xml 与 feed/category/*.xml  # 分类 RSS（新/旧两种地址）
│   └── llms.txt          # LLM / Agent 友好入口
├── agent/skills/opto-hot # 可安装的 Agent Skill（光电频道）
├── tests/                # 纯标准库单元测试（python -m unittest discover -s tests）
├── functions/api/summarize.js  # Cloudflare Pages Function（按需中文摘要，仅 CF 侧生效）
├── scripts/              # 本地计划任务、手动部署脚本、门槛校准评测（eval_selection.py）
└── .github/workflows/    # update.yml（定时采集+自检+部署）/ pages.yml（推送即部署）
```

`dist/api/v1/*.json`、`dist/data/*.json`、`dist/feed/category/*.xml` 这些**扁平地址是重构前就发布
给外部消费者（RSS 订阅、Agent Skill、llms.txt、README）的兼容层**，由 `collect.py` 每次运行时把
T 光电频道镜像过去。`python collector/collect.py --check` 会在提交前确认它们都在。

## 每天 6:00 / 18:00（北京时间）自动更新

**GitHub Actions（默认启用，推荐）**

![workflow](https://github.com/sun-zihang/pat-hot/actions/workflows/update.yml/badge.svg)

`.github/workflows/update.yml` 每天 6:00 与 18:00（北京时间，即 cron `0 22,10 * * *` UTC）各运行一次：
1. 跑 `tests/` 下的单元测试（纯标准库、无网络）
2. 运行 `python collector/collect.py --limit 25 --llm` 重新采集（真嵌入聚类）
3. `python collector/collect.py --check` 自检对外契约，不通过就不提交
4. 有变化则提交并推送数据（`chore: 刷新 PAT-HOT 数据 …`）
5. **直接部署 GitHub Pages**（`actions/deploy-pages`），线上站点立即更新
6. `python collector/collect.py --check-live` 回读线上页面做同源断言（样式完整 +
   三频道齐全 + GitHub Pages 不落后于本次提交）。部署"成功"不等于内容正确——
   2026-10-12 的坏产物正是部署成功上线的。此步只告警不红（Pages 传播有延迟，且
   坏产物已在线上，跑红也不回滚）；pages.dev 是手动发布，数据落后只提示。

也可在 Actions 页面手动 `workflow_dispatch` 触发。注意：GitHub 服务器位于海外，个别国内站点可能超时，采集器对每个源单独容错，单源失败不影响整体输出。

**本地计划任务（可选）**

- `scripts/install-schedule.ps1`：注册 Windows 计划任务，每天 12:00 运行一次 `scripts/auto-update.ps1`（采集 → 契约自检 → git 提交 → push，触发 GitHub Pages 重新部署）

## 部署到 Cloudflare Pages（按需中文摘要接口）

Cloudflare Pages 项目 `pat-hot`（`pat-hot.pages.dev`）**未接 Git 自动发布**，与上面的
GitHub Pages 是两套独立部署。`functions/api/summarize.js` 这个 Pages Function 只有在
手动 `wrangler pages deploy` 时才会上线；CI 的定时刷新只重跑 GitHub Pages，不会动它。
所以改了 `functions/` 或想让摘要接口上线，需要在本地按下面步骤发一次。

密钥（一次性）：`SENSENOVA_API_KEY` 已作为 Pages Secret 写入 production 与 preview 两个环境，
不进代码也不进仓库。换 key 时重跑：

```
wrangler pages secret put SENSENOVA_API_KEY --project-name pat-hot            # production
wrangler pages secret put SENSENOVA_API_KEY --project-name pat-hot -e preview  # preview
```

发布（functions 目录需与静态资源目录同级，且命令的当前工作目录能解析到两者）：

```
wrangler pages deploy <静态资源目录> --project-name pat-hot --branch master
```

`--branch master` 即 production；换成别的分支名就是预览部署，验证后再用
`wrangler pages deployment list --project-name pat-hot` 确认。

三个已知坑（2026-10-12 实测）：

1. **Pages Function 发布偶发 `Unknown internal error occurred`**：Cloudflare 侧的间歇性
   失败，同一次产物重试 2-3 次即可成功；production 发布失败时旧线上产物不受影响，可放心重试。
2. **构建 Functions 用的 `esbuild.exe` 若位于 `D:\` 下会被 Windows 权限拒绝写任何输出目录**
   （报 `Failed to write to output file ... Access is denied`，连写到 `C:\` 也失败）。
   绕法：把该 exe 复制一份到 `C:\` 下并用 `ESBUILD_BINARY_PATH` 指向它：
   `env:ESBUILD_BINARY_PATH = "C:\...\esbuild.exe"; wrangler pages deploy ...`。
3. **不要手工把 index.html 转义后再上传**：曾有一次线上 `pat-hot.pages.dev` 整段内联 CSS
   的换行变成字面量 `\n`（反斜杠+n），浏览器把每行当畸形声明全部丢弃，站点退化成无样式裸
   HTML。根因是上传的产物被二次转义，不是 `collect.py` 的构建问题（本地 `dist/` 一直干净）。
   发布务必直接 `wrangler pages deploy dist`（部署仓库里 `--check` 通过的 `dist/`），
   不要经任何"读进来再写出去"的中间脚本。`--check` 现已加内联 CSS 完整性断言，坏产物当场拦下；
   发完再跑一次 `python collector/collect.py --check-live` 回读线上确认（见上节第 6 步）。

> 为什么是 Pages Function 而不是独立 Worker：`*.workers.dev` 在中国大陆被 DNS 污染
> 且 TCP 不通（实测解析到 Facebook 段），而本站受众正是无法访问外网的用户。同站
> Function 免 CORS、免被墙。`window.PAT_LLM_WORKER` 仍保留为显式覆盖入口，
> 默认为同站 `/api/summarize`，非 pages.dev 镜像（GitHub Pages）自动回指 `pat-hot.pages.dev`。

## 路线图

- [x] 接入更多源（英文行业媒体、微信公众号精选、政策/招投标信息）
- [x] 嵌入向量语义聚类（TF-IDF 向量 + 可选真嵌入），替代关键词聚类
- [x] 历史日报归档，支持按日期 / 月份回看
- [x] 多语言报告（中/EN）与图表交互（筛选 / 排序 / tooltip）
- [x] Agent 接入（静态 JSON API + llms.txt）
- [x] 微信公众号覆盖更全：多查询 + 会话 Cookie + 反爬检测 + 公众号/时间/摘要字段（90 天新鲜度过滤）
- [x] 政策 / 招投标结构化库（`data/biz.json`：项目号 / 预算 / 截止时间，详情页解析）
- [x] 真嵌入聚类（CI 内置 bge-small-zh + HF 缓存；TF-IDF 事件聚类 + 神经近重复合并）与主题可解释性（`top_terms`）
- [ ] 微信验证码彻底绕过（受平台策略限制，采用多查询 + 降级处理缓解）


## 数据与免责声明

数据来自公开网络（RSS / 网站首页），由本工具自动采集与统计，仅供行业资讯参考，**不构成任何投资建议**。各源内容版权归原作者/原站所有；如原站不允许抓取，请在 `sources.json` 中移除对应源。

## License

[MIT](LICENSE)