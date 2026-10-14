# -*- coding: utf-8 -*-
"""对外文档点名的字段名，必须真实存在于产物 JSON（纯标准库，无网络）。

起因（2026-10-14 实测线上 dist/llms.txt）：它教 Agent「按 publishedAt /
discoveredAt 筛选 items.json」，README 也这么写，但 items 整份是 snake_case，
真实键是 published_at / discovered_at。照文档写的代码取到 undefined，筛 24h
命中 0 条——Agent 不会来问人，只会判定"这站没数据"。

字段改名只发生在代码侧，文档是另一条独立变更线，靠人记必然漏。这里把
check_contract 里的 doc_field_problems 钉成测试：
  1) 正确文档 -> 0 问题；
  2) llms.txt / README 各写错一个键 -> 精确抓到；
  3) 嵌套字段（links.original）写错也抓；camelCase 合法键（trendPct 等）不误报；
  4) 空榜单、产物缺席 -> 静默，不做空判定式假报；
  5) 真实仓库产物：现行 README + 模板渲染的 llms.txt 必须 0 问题（回归锁）。
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "collector"))

import collect  # noqa: E402

ITEM = {"id": "x", "title": "t", "published_at": None, "discovered_at": "2026-01-01",
        "keywords": ["a"], "links": {"original": "u"},
        "url": "http://e", "summary": "s", "category": "laser", "role": "main",
        "source": "Nature Photonics", "source_base": "np", "tier": "official",
        "selected": True, "score": 94.5}
HOT = {"rank": 1, "title": "h", "trendPct": 5, "digestTitle": "d",
       "source_count": 2, "signal_count": 3, "latest_at": "2026-01-01",
       "status": "热", "trend": "+5", "heat": 88.0, "score": 80.0,
       "sources": ["s"], "links": [{"u": 1}]}

OK_README = (
    "- data/items.json：{id, title, links.original, published_at, discovered_at, keywords}\n"
    "- data/hot-topics.json：{rank, title, status, trend, trendPct, digestTitle, "
    "source_count, signal_count, latest_at}\n")
OK_LLMS = "- items.json 为全量快照，可本地按 published_at / discovered_at / keywords 筛选。"

# daily.json 是统计聚合（字段在顶层，数组元素的字段在 byCategory[0] 里）
DAILY_AGG = {"generatedAt": "2026-01-01", "total": 1, "last24h": 1, "last7d": 1,
             "topicCount": 1, "byCategory": [{"category": "laser", "total": 1,
                                              "last24h": 1, "last7d": 1}],
             "byDay": [{"date": "2026-01-01", "count": 1}],
             "bySource": [{"source": "s", "count": 1, "latestAt": "2026-01-01"}]}
# dailies.json 是裸日期字典，文档点名的字段在**值**里；归档里存在两种历史格式，
# 早期格式没有 headline/picks/flash——所以取样必须锁定"最新一期"（见下面两个回归测试）。
DAILIES = {"2026-01-01": {"date": "2026-01-01", "label": "L", "weekday": "周一",
                          "sections": [], "readMinutes": 3, "tocCount": 0},
           "2026-03-05": {"date": "2026-03-05", "label": "L", "weekday": "周三",
                          "sections": [], "readMinutes": 3, "tocCount": 0,
                          "headline": {"title": "h"}, "picks": [], "flash": [],
                          "topic_ids": ["t"]}}

# SKILL.md 的「字段命名」表（可安装 Agent Skill，会被复制成离线副本）
SKILL_OK = """## 字段命名（务必照抄，别猜）
| 端点 | 时间 | 计数 | 其它 |
|---|---|---|---|
| `items.json` | `published_at` / `discovered_at`（下划线） | `score` | `source` 是**字符串**；另有 `keywords`、`links.original`、`url`、`title`、`summary`、`category`、`role` |
| `hot-topics.json` | `latest_at`（下划线） | `source_count` / `signal_count`（下划线） | `rank`、`status`、`heat`、`score`、`sources`、`links` |
| `daily.json` | `generatedAt` | `total` / `last24h` / `last7d` / `topicCount` | `byCategory[{category,total,last24h,last7d}]`、`byDay[{date,count}]`、`bySource[{source,count,latestAt}]` |
| `dailies.json` | — | — | 裸日期字典，键 `YYYY-MM-DD`，值含 `headline`/`picks`/`flash`/`sections`/`label`/`weekday` |
"""


class DocFieldGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dist = os.path.join(self.tmp, "dist")
        self.api = os.path.join(self.dist, "api", "v1", "tech")
        os.makedirs(self.api)
        self._real_dist = collect.DIST_DIR
        self._real_alias = collect.FLAT_ALIAS_CHANNEL
        collect.DIST_DIR = self.dist
        collect.FLAT_ALIAS_CHANNEL = "tech"

    def tearDown(self):
        collect.DIST_DIR = self._real_dist
        collect.FLAT_ALIAS_CHANNEL = self._real_alias
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _payloads(self, items, hot):
        for name, obj in (("items.json", items), ("hot-topics.json", hot)):
            with io.open(os.path.join(self.api, name), "w", encoding="utf-8") as f:
                json.dump({"items": obj}, f)

    def _payload(self, name, doc):
        with io.open(os.path.join(self.api, name), "w", encoding="utf-8") as f:
            json.dump(doc, f)

    def _all_payloads(self):
        self._payloads([ITEM], [HOT])
        self._payload("daily.json", DAILY_AGG)
        self._payload("dailies.json", DAILIES)

    def test_correct_docs_no_problems(self):
        self._payloads([ITEM], [HOT])
        self.assertEqual(collect.doc_field_problems(OK_LLMS, OK_README), [])

    def test_camelcase_legit_keys_not_flagged(self):
        # trendPct / digestTitle 真实存在，混合命名不误报（不搞"统一风格"规则）
        self._payloads([ITEM], [HOT])
        self.assertEqual(collect.doc_field_problems(OK_LLMS, OK_README), [])

    def test_stale_llms_field_caught(self):
        self._payloads([ITEM], [HOT])
        bad = OK_LLMS.replace("published_at / discovered_at", "publishedAt / discoveredAt")
        got = collect.doc_field_problems(bad, OK_README)
        self.assertEqual(len(got), 2, got)
        self.assertTrue(all("llms.txt" in p for p in got), got)

    def test_stale_readme_field_caught(self):
        self._payloads([ITEM], [HOT])
        bad = OK_README.replace("published_at, discovered_at", "publishedAt, discoveredAt")
        got = collect.doc_field_problems(OK_LLMS, bad)
        self.assertEqual(len(got), 2, got)

    def test_nested_field_caught(self):
        self._payloads([ITEM], [HOT])
        bad = OK_README.replace("links.original", "links.wrong")
        got = collect.doc_field_problems(OK_LLMS, bad)
        self.assertEqual(len(got), 1, got)
        self.assertIn("links.wrong", got[0])

    def test_empty_items_no_vacuous_alarm(self):
        self._payloads([], [])
        bad = OK_LLMS.replace("published_at", "publishedAt")
        self.assertEqual(collect.doc_field_problems(bad, OK_README), [])

    def test_missing_payload_silent(self):
        # 产物缺席由存在性检查报错，本检查不叠加噪音
        self.assertEqual(collect.doc_field_problems(OK_LLMS, OK_README), [])

    # ---- SKILL.md 字段表（可安装 Agent Skill，离线副本最需要钉死）----

    def test_skill_table_correct_no_problems(self):
        self._all_payloads()
        self.assertEqual(collect.doc_field_problems(OK_LLMS, OK_README, SKILL_OK), [])

    def test_skill_bare_root_key_is_checked(self):
        # 回归锁：上一版核验用的正则是 r"^([A-Za-z]\w*)(?:\[\{...\}\])?$|^\.(\w+)?$"，
        # 第二个分支的 ^ 在中间永远匹配不上，而第一个分支要求"要么带 [{}]"——
        # 结果**裸根键全部落到"不是字段声明"分支被静默跳过**，items/hot-topics/
        # dailies 三行等于没验。看着一片绿，其实闸门是空的。
        self._all_payloads()
        bad = SKILL_OK.replace("`published_at` / `discovered_at`", "`publishedAt` / `discoveredAt`")
        got = collect.doc_field_problems(OK_LLMS, OK_README, bad)
        self.assertEqual(len(got), 2, got)
        self.assertTrue(all("items.json" in x for x in got), got)

    def test_skill_array_element_fields_caught(self):
        self._all_payloads()
        bad = SKILL_OK.replace("byCategory[{category,total,last24h,last7d}]",
                               "byCategory[{cat,ttl}]")
        got = collect.doc_field_problems(OK_LLMS, OK_README, bad)
        self.assertEqual(len(got), 1, got)
        self.assertIn("byCategory", got[0])

    def test_skill_dailies_value_fields_caught(self):
        self._all_payloads()
        bad = SKILL_OK.replace("`headline`/`picks`/`flash`", "`headline`/`picks`/`breaking`")
        got = collect.doc_field_problems(OK_LLMS, OK_README, bad)
        self.assertEqual(len(got), 1, got)
        self.assertIn("dailies.json", got[0])
        self.assertIn("breaking", got[0])

    def test_skill_samples_latest_period_not_file_order(self):
        # 回归锁：dailies.json 的键是日期，但 doc.values() 是**文件插入序**，
        # 不是日期序；且归档里存在两种历史格式。上一版取 vals[0]，格式刚好
        # "缺字段"时会假报文档错、"多字段"时又用旧数据把真漂移糊过去。
        self._payloads([ITEM], [HOT])
        self._payload("daily.json", DAILY_AGG)
        # 最新一期（2026-03-05）确实有 headline；插入序第一条是没有的旧格式。
        self._payload("dailies.json", DAILIES)
        self.assertEqual(collect.doc_field_problems(OK_LLMS, OK_README, SKILL_OK), [])

    def test_skill_field_removed_from_latest_period_is_caught(self):
        # 反向：只有旧日期有 headline，最新一期删掉了 -> 必须报。
        # 用"值键并集"会拿旧数据糊过去，这正是上一版的第二个漏洞。
        self._payloads([ITEM], [HOT])
        self._payload("daily.json", DAILY_AGG)
        aged = {"2026-03-05": dict(DAILIES["2026-03-05"]),
                "2026-04-01": {"date": "2026-04-01", "label": "L", "weekday": "周二",
                               "sections": [], "readMinutes": 3, "tocCount": 0}}
        self._payload("dailies.json", aged)
        got = collect.doc_field_problems(OK_LLMS, OK_README, SKILL_OK)
        self.assertTrue(got, "最新一期已无 headline/picks/flash，闸门却放过了")
        self.assertIn("headline", "".join(got))


class RealRepoArtifact(unittest.TestCase):
    """真实产物回归锁：现行 README / llms.txt / SKILL.md 点的字段必须都在产物里。"""

    def test_readme_fields_exist_in_dist(self):
        rp = os.path.join(ROOT, "README.md")
        lp = os.path.join(ROOT, "dist", "llms.txt")
        sp = os.path.join(ROOT, "agent", "skills", "opto-hot", "SKILL.md")
        if not (os.path.exists(rp) and os.path.exists(lp)):
            self.skipTest("仓库产物未生成")
        with io.open(rp, encoding="utf-8") as f:
            readme = f.read()
        with io.open(lp, encoding="utf-8") as f:
            llms = f.read()
        skill = None
        if os.path.exists(sp):
            with io.open(sp, encoding="utf-8") as f:
                skill = f.read()
        real_dist = collect.DIST_DIR
        try:
            collect.DIST_DIR = os.path.join(ROOT, "dist")
            problems = collect.doc_field_problems(llms, readme, skill)
        finally:
            collect.DIST_DIR = real_dist
        self.assertEqual(problems, [], "文档字段与产物漂移:\n" + "\n".join(problems))

    def test_skill_md_field_table_matches_dist(self):
        # SKILL.md 会被安装成离线副本（~/.agents/skills/opto-hot），网站改了它
        # 不会自己跟着改，所以单独钉一条：字段表逐行对真实产物核验。
        sp = os.path.join(ROOT, "agent", "skills", "opto-hot", "SKILL.md")
        if not os.path.exists(sp):
            self.skipTest("SKILL.md 不存在")
        with io.open(sp, encoding="utf-8") as f:
            skill = f.read()
        real_dist = collect.DIST_DIR
        try:
            collect.DIST_DIR = os.path.join(ROOT, "dist")
            problems = collect.doc_field_problems("", "", skill)
        finally:
            collect.DIST_DIR = real_dist
        self.assertEqual(problems, [], "SKILL.md 字段表与产物漂移:\n" + "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
