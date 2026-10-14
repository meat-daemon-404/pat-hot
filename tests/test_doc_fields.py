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
        "keywords": ["a"], "links": {"original": "u"}}
HOT = {"rank": 1, "title": "h", "trendPct": 5, "digestTitle": "d",
       "source_count": 2, "signal_count": 3, "latest_at": "2026-01-01",
       "status": "热", "trend": "+5"}

OK_README = (
    "- data/items.json：{id, title, links.original, published_at, discovered_at, keywords}\n"
    "- data/hot-topics.json：{rank, title, status, trend, trendPct, digestTitle, "
    "source_count, signal_count, latest_at}\n")
OK_LLMS = "- items.json 为全量快照，可本地按 published_at / discovered_at / keywords 筛选。"


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


class RealRepoArtifact(unittest.TestCase):
    """真实产物回归锁：现行 README 点的字段必须都在 dist 产物里。"""

    def test_readme_fields_exist_in_dist(self):
        rp = os.path.join(ROOT, "README.md")
        lp = os.path.join(ROOT, "dist", "llms.txt")
        if not (os.path.exists(rp) and os.path.exists(lp)):
            self.skipTest("仓库产物未生成")
        with io.open(rp, encoding="utf-8") as f:
            readme = f.read()
        with io.open(lp, encoding="utf-8") as f:
            llms = f.read()
        real_dist = collect.DIST_DIR
        try:
            collect.DIST_DIR = os.path.join(ROOT, "dist")
            problems = collect.doc_field_problems(llms, readme)
        finally:
            collect.DIST_DIR = real_dist
        self.assertEqual(problems, [], "文档字段与产物漂移:\n" + "\n".join(problems))


if __name__ == "__main__":
    unittest.main()
