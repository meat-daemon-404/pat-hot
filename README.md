# Opto-Hot · 光电行业热点统计

以 [AIHOT](https://aihot.virxact.com) 为模板的开源「光电行业热点统计」工具：

> **在线报告（GitHub Pages）**：https://sun-zihang.github.io/opto-hot/
>
> **在线报告（腾讯云开发 CloudBase 静态托管）**：https://opto-hot-a455-d3g2s3dt865d86640.webapps.tcloudbase.com/

自动采集公开网络上的光电产业资讯，去重分类、聚类打分，输出热点榜 / 精选 / 分类统计 / 每日趋势，并生成可离线打开的中文 HTML 报告。

## 特性

- **多源采集**：19 个公开数据源（RSS + 行业网站 + 微信公众号精选 + 政策/招投标），中文为主、兼顾国际
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
- **AIHOT 风格 UI**：六个视图（精选时间线 / 全部动态 / 热点榜 / 光电日报 / 主题 / 数据），浅色卡片风、侧边导航、评分与热度徽章，移动端自适应
- **日报归档机制**：自动按天生成光电日报（今日看点 TOC + 分类文章 + 日历归档），历史归档按日期/月份回看
- **多语言与交互**：中 / English 一键切换；图表 tooltip；热点榜按热度/信源排序；搜索 + 分类 + 排序
- **Agent 接入**：免鉴权静态 JSON API（`api/v1/*`）+ OpenAPI 3.1 + 分类 RSS feed + `llms.txt` + 可安装 Skill（`agent/skills/opto-hot`）
- **手机适配**：响应式布局（窄屏单列、顶部搜索、横向导航），移动端可正常浏览
- **自动化**：内置 GitHub Actions，每 6 小时自动刷新数据并提交


## CloudBase 部署

| 项 | 值 |
|---|---|
| 环境 | `a455-d3g2s3dt865d86640`（ap-shanghai） |
| 应用服务名 | opto-hot（最新版本 opto-hot-005） |
| 访问域名 | https://opto-hot-a455-d3g2s3dt865d86640.webapps.tcloudbase.com/ |
| 控制台 | https://tcb.cloud.tencent.com/dev?envId=a455-d3g2s3dt865d86640 |

- 该域名与 GitHub Pages（sun-zihang.github.io/opto-hot/）相互独立、可同时访问，数据同源于 data/ 下的采集产物。
- 更新方式：本地重新构建 dist/ 后，用 CloudBase 部署工具以同一服务名 opto-hot 重新部署即可生成新版本，**域名保持不变**。
- 数据刷新仍由 GitHub Actions 每 6 小时自动完成；CloudBase 侧如需同步，可在本地运行 python collector/collect.py 后重新部署。

## UI 与机制（对标 AIHOT）

| 视图 | 对应 AIHOT 页面 | 说明 |
|---|---|---|
| 精选 #/ | /（精选） | 按日分组的资讯时间线：来源、时间、分类徽章、推荐分、精选标记 |
| 全部动态 #/all | /all | 全部条目，支持关键词搜索 + 分类筛选 + 按推荐分/时间排序 |
| 热点榜 #/hot | /hot | 排名 + 状态（爆/发酵中/关注中）+ 信源数/信号数/热度值 + 信源展开 |
| 光电日报 #/daily | /daily | 报头 + 今日看点 TOC + 分类文章 + 日历归档 |
| 主题 #/topics | /topics | 分类卡片（24h/7d/总数），点击进入筛选 |
| 数据 #/data | - | 统计卡片、14 天趋势、来源表、CSV/JSON 下载 |
| Agent 接入 #/agent | /agent | API 端点 + RSS + OpenAPI + curl 示例 + Skill 说明 |

**数据机制**（静态 JSON API，兼容 AIHOT 字段风格）：
- data/items.json：{id, title, url, links.original, source, category, publishedAt, discoveredAt, score, selected, summary, role, keywords}
- data/hot-topics.json：{rank, title, status, heat, sourceCount, signalCount, latestAt, sources, links, terms}
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
git clone https://github.com/sun-zihang/opto-hot.git
cd opto-hot
python collector/collect.py          # 需要联网；Python 3.8+
```

生成产物：

| 文件 | 说明 |
|---|---|
| `dist/index.html` | AIHOT 风格单页应用（精选/全部/热点榜/日报/主题/数据，内嵌数据可离线打开） |
| `data/items.json` | 全部采集条目（含分类、关键词、得分） |
| `data/hot-topics.json` | 热点榜（rank / 来源数 / 信号数 / 链接） |
| `data/daily.json` | 统计：分类、每日趋势、来源分布 |
| `data/dailies.json` | 光电日报归档（按日期） |
| `data/report.csv` | 条目 CSV 导出（Excel 可直接打开） |

常用参数：

```bash
python collector/collect.py --limit 30   # 每个源最多取 30 条
python collector/collect.py --topics 15  # 热点榜输出 15 条
python collector/collect.py --skip-html  # 跳过行业网站（只跑 RSS）
python collector/collect.py --llm        # 可选：SenseNova LLM 增强（需 SENSENOVA_API_KEY）
python collector/collect.py --images     # 可选：SenseNova 生图配图（需 SENSENOVA_API_KEY）
```

## 集中配置

`collector/config.json` 集中了评分权重（`scoring`）、信源分级与精选门槛（`tiers`）、热度参数（`heat`）、
聚类阈值（`clustering`）、日报编排（`daily`）、LLM 增强（`llm`）与生图（`images`）的全部参数。
调标准只改这个文件，不用改代码；删除该文件或留空字段会自动回退内置默认值。

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
- Key **绝不写进代码/仓库**，只从环境变量 `SENSENOVA_API_KEY` 读取；
  无 key、超时、配额不足等任何失败都会静默降级（跳过增强/无图），不阻断主流程。
- GitHub Actions 默认**不启用**（不产生费用）。如需启用：仓库 Settings → Secrets 添加
  `SENSENOVA_API_KEY`，并在工作流的采集命令后加上 `--llm` / `--images`，例如：
  `python collector/collect.py --limit 25 --llm`。

## 数据源（13 个）

| 类型 | 名称 | 地址 | 权重 |
|---|---|---|---|
| RSS | arXiv 光学与光子学 (physics.optics) | `http://export.arxiv.org/rss/physics.optics` | 0.8 |
| RSS | Nature Photonics | `https://www.nature.com/nphoton.rss` | 0.9 |
| RSS | Phys.org 物理新闻（关键词过滤） | `https://phys.org/rss-feed/physics-news/` | 0.6 |
| RSS | C114中国通信网_要闻精选 | `http://www.c114.com.cn/rss/rss_news_489.xml` | 0.9 |
| RSS | C114中国通信网_通信财经 | `http://www.c114.com.cn/rss/rss_news_24.xml` | 0.9 |
| RSS | C114中国通信网_IT资讯 | `http://www.c114.com.cn/rss/rss_news_27.xml` | 0.8 |
| RSS | C114中国通信网_设备商 | `http://www.c114.com.cn/rss/rss_news_18.xml` | 0.9 |
| RSS | C114中国通信网_监管 | `http://www.c114.com.cn/rss/rss_news_550.xml` | 0.7 |
| HTML | OFweek 光电频道 | `https://optics.ofweek.com/` | 1.0 |
| HTML | OFweek 激光频道 | `https://laser.ofweek.com/` | 1.0 |
| HTML | LEDinside 中文 | `https://www.ledinside.cn/` | 0.9 |
| HTML | CIOE 中国光博会 | `https://cioe.cn/` | 0.9 |
| HTML | COEMA 中国光电子行业协会 | `https://www.coema.org.cn/` | 0.8 |
| RSS | LEDinside 英文 | `https://www.ledinside.com/rss` | 0.8 |
| RSS | EDN 电子工程专辑（关键词过滤） | `https://www.edn.com/feed/` | 0.6 |
| HTML | 搜狗微信·光电行业 | `https://weixin.sogou.com/weixin?type=2&query=光电行业` | 0.7 |
| HTML | 中国政府采购网 | `https://www.ccgp.gov.cn/` | 0.8 |
| HTML | 中国招标投标公共服务平台 | `http://www.cebpubservice.com/` | 0.8 |
| HTML | 工信部要闻（关键词过滤） | `https://www.miit.gov.cn/` | 0.8 |

> 抓取说明：COEMA 页面实际为 GBK 编码（meta 声明为 utf-8）；OFweek 为 GB2312；C114 RSS 为 GBK 编码的 RSS 2.0；Nature Photonics 为 RSS 1.0 (RDF)。采集器已做对应处理。源配置在 `collector/sources.json`，可自由增删。

## 打分模型（透明可复现）

- 条目得分 = `w_source × 来源权重 + w_convergence × 跨源收敛度 + w_signal × min(1, 主题信号数/10) + w_recency × 时效`，默认权重 45 / 20 / 15 / 20；其中时效 = `max(0, 1 − 距今天数/30)`，**无可信发布时间的条目时效分 ×0.5**
- 跨源收敛度 = `min(1, 事件独立来源数/6)`：同一事件被越多独立来源报道，得分越高，防单源刷榜
- 主题热度 = `100 × (0.45 × min(1, 独立来源数/6) + 0.35 × min(1, 信号数/10) + 0.20 × min(1, 48小时内独立来源数/独立来源数))` —— 48 小时窗口内同一来源只计一次
- 精选门槛（分级）：官方信源（协会/政府/一手）≥ 55 分，媒体信源 ≥ 65 分
- 聚类：以领域词表 + 英文词（去停用词）做关键词索引，≥2 条命中的词构成候选主题；重叠 ≥50% 或代表条目相同的主题自动合并
- 以上权重、门槛、窗口均可在 `collector/config.json` 调整，缺失字段自动回退内置默认值

## 目录结构

```
opto-hot/
├── collector/
│   ├── collect.py        # 主脚本：采集→清洗→分类→打分→聚类→输出
│   ├── sources.json      # 数据源配置（RSS / HTML 解析规则 + tier 分级）
│   └── config.json       # 集中配置：评分权重/精选门槛/聚类阈值/日报编排/LLM与生图
├── data/                 # 生成的数据（JSON / CSV）
├── dist/index.html       # 生成的 HTML 报告
├── .github/workflows/update.yml  # 每 6 小时自动更新
├── README.md
└── LICENSE               # MIT
```

## 每天 12:00 自动更新（北京时间）

**GitHub Actions（默认启用，推荐）**

![workflow](https://github.com/sun-zihang/opto-hot/actions/workflows/update.yml/badge.svg)

`.github/workflows/update.yml` 每天 12:00（北京时间，即 UTC 04:00）运行一次：
1. 运行 `python collector/collect.py --limit 25` 重新采集（真嵌入聚类）
2. 有变化则提交并推送数据（`chore: 刷新光电热点数据 …`）
3. **直接部署 GitHub Pages**（`actions/deploy-pages`），线上站点立即更新

也可在 Actions 页面手动 `workflow_dispatch` 触发。注意：GitHub 服务器位于海外，个别国内站点可能超时，采集器对每个源单独容错，单源失败不影响整体输出。

**本地计划任务（可选）**

- `scripts/install-schedule.ps1`：注册 Windows 计划任务，每天 12:00 运行一次 `scripts/auto-update.ps1`（采集 → git 提交 → push，触发 GitHub Pages 重新部署）

**CloudBase 说明（已停止自动同步，2026-08-05）**

- 按用户要求，站点数据**仅在 GitHub Pages 更新**；CloudBase（`a455` 环境）不再自动部署，保持为静态快照。
- 如需手动部署 CloudBase，可运行 `scripts/cloudbase-deploy.ps1`（需 mcporter 已登录，或设置环境变量 `TCB_API_KEY`）。

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