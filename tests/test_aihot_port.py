# -*- coding: utf-8 -*-
"""预筛 / 词表订正 / 事件综述 三项 AIHOT 移植的回归锁。

锁住的语义（都来自 AIHOT 原文档，逐条对应）：
1. 预筛（prefilter.md）：宽进严出——BLOCK 需要正面依据；UNKNOWN 与 PASS 一样
   继续往下走，绝不因为"拿不准"丢内容；模型失败一律按放行处理（预筛是增益，
   不是闸门）；BLOCK 的条目不再进任何公开页。
2. 预筛必须为下游留出预算（与 enhance 同一个坑）：否则预筛会吃光 deadline，
   让写作/双打分/抽取/订正/综述在第一批就被熔断。
3. 词表订正（mend-wording.md / wording.ts）：只查模型自己写的字段，**不碰
   信源原标题**（那是替原站改稿）；只列一眼能判断的词，"首次/最大/唯一"
   这类正文支持的正当用法绝不在表内；订正后仍命中的结果不采纳（防止改坏）。
4. 事件综述（story-digest.md）：只给多源事件写（单源没有综述可言）；
   失败降级为无综述、不阻断；综述标题超过 30 字不替换展示标题。
"""
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "collector"))
import collect  # noqa: E402


class TestPrefilter(unittest.TestCase):
    def setUp(self):
        self._sleep = collect.time.sleep
        collect.time.sleep = lambda s: None

    def tearDown(self):
        collect.time.sleep = self._sleep
        collect.start_llm_budget(None)

    def _item(self, title, score=80.0, summary="x" * 120):
        return {"id": collect.make_id(title, "https://e/" + title), "title": title,
                "url": "https://e/" + title, "source": "OFweek 光电频道",
                "source_base": "OFweek 光电频道", "published_at": None,
                "discovered_at": "2026-10-13T00:00:00+00:00",
                "summary": summary, "score": score, "keywords": []}

    def test_only_block_is_dropped_unknown_kept(self):
        items = [self._item("A 条"), self._item("B 条"), self._item("C 条")]
        real = collect._sensenova_chat
        collect._sensenova_chat = lambda m, c, **k: {
            "0": {"label": "BLOCK", "reason": "纯娱乐"},
            "1": {"label": "UNKNOWN", "reason": "看不清"},
            "2": {"label": "PASS", "reason": "相关"},
        }
        try:
            blocked = collect.llm_prefilter(items, collect.CONFIG)
        finally:
            collect._sensenova_chat = real
        self.assertEqual(blocked, 1)
        self.assertTrue(items[0].get("blocked"), "BLOCK 必须标记")
        self.assertNotIn("blocked", items[1], "UNKNOWN 不能丢：AIHOT 保留待补材料")
        self.assertNotIn("blocked", items[2])

    def test_model_failure_releases_everything(self):
        items = [self._item("A 条"), self._item("B 条")]
        real = collect._sensenova_chat

        def boom(m, c, **k):
            raise RuntimeError("upstream 500")

        collect._sensenova_chat = boom
        try:
            blocked = collect.llm_prefilter(items, collect.CONFIG)
        finally:
            collect._sensenova_chat = real
        self.assertEqual(blocked, 0, "预筛失败必须全部放行，不能因抖动清空频道")
        self.assertFalse(any(i.get("blocked") for i in items))

    def test_prefilter_reserves_budget_for_downstream(self):
        # 只剩 40s、reserve=150 → 预筛必须一发都不发（留给下游）
        items = [self._item("A 条")]
        calls = [0]
        real = collect._sensenova_chat
        collect._sensenova_chat = lambda m, c, **k: (calls.__setitem__(0, calls[0] + 1),
                                                    {"0": {"label": "PASS"}})[1]
        try:
            collect.start_llm_budget(360)
            collect._LLM_DEADLINE[0] = collect.time.monotonic() + 40
            collect.llm_prefilter(items, collect.CONFIG)
        finally:
            collect._sensenova_chat = real
        self.assertEqual(calls[0], 0, "预筛吃光预算会饿死下游五个阶段")

    def test_low_score_items_never_cost_money(self):
        items = [self._item("低分条", score=30.0)]
        calls = [0]
        real = collect._sensenova_chat
        collect._sensenova_chat = lambda m, c, **k: (calls.__setitem__(0, calls[0] + 1), {})[1]
        try:
            collect.llm_prefilter(items, collect.CONFIG)
        finally:
            collect._sensenova_chat = real
        self.assertEqual(calls[0], 0, "进不了公开页的低分条目不为它花模型钱")


class TestWordingMend(unittest.TestCase):
    def setUp(self):
        self._sleep = collect.time.sleep
        collect.time.sleep = lambda s: None

    def tearDown(self):
        collect.time.sleep = self._sleep
        collect.start_llm_budget(None)

    def _item(self, **kw):
        it = {"id": "i1", "title": "原标题：某公司重磅发布新品", "url": "https://e/1",
              "source": "S", "source_base": "S", "score": 80.0,
              "discovered_at": "2026-10-13T00:00:00+00:00"}
        it.update(kw)
        return it

    def test_detects_only_model_written_hype(self):
        # find_wording_issues 是通用文本匹配；"只查模型写的字段、不碰信源标题"
        # 由 llm_mend_wording 的字段范围保证（见下一个测试）
        it = self._item(llm_summary="该成果颠覆了传统认知。")
        self.assertEqual([h[0] for h in collect.find_wording_issues(it["llm_summary"])], ["颠覆"])
        self.assertEqual([h[0] for h in collect.find_wording_issues("这家公司重磅发布了新品")], ["重磅"])

    def test_mend_never_touches_source_title(self):
        # 回归：标题是信源原文，改它就是替原站改稿——即使标题里有禁用词，
        # 订正也只能改模型自己写的字段
        it = self._item(title="原标题：某公司重磅发布新品", llm_summary="颠覆认知。")
        seen = {}
        real = collect._sensenova_chat

        def spy(messages, cfg, **k):
            seen["prompt"] = messages[0]["content"]
            return {"0": {"summary": "改变了既有认识。"}}

        collect._sensenova_chat = spy
        try:
            collect.llm_mend_wording([it], [], collect.CONFIG)
        finally:
            collect._sensenova_chat = real
        self.assertEqual(it["title"], "原标题：某公司重磅发布新品",
                         "信源标题绝不能被订正改写")
        self.assertNotIn("title", seen.get("prompt", "").split("现有文字")[-1][:200],
                         "标题不该出现在订正输入里")

    def test_legitimate_first_max_not_flagged(self):
        # AIHOT 口径：排他性表述只有原文明确写出时才保留——所以不能进禁用表，
        # 否则"水星达最大东大距"这类正当用法会被误改
        for legit in ("水星达最大东大距", "该团队首次实现室温超导观测", "这是目前唯一的中文源"):
            self.assertEqual(collect.find_wording_issues(legit), [],
                             "正文支持的正当用法不许误伤：%s" % legit)

    def test_mend_rewrites_and_keeps_facts(self):
        it = self._item(llm_summary="重磅！该公司颠覆了行业。", zh_full="颠覆性突破。")
        real = collect._sensenova_chat
        collect._sensenova_chat = lambda m, c, **k: {
            "0": {"zh_full": "该公司发布了新产品。", "summary": "该公司发布了新产品。"}}
        try:
            done = collect.llm_mend_wording([it], [], collect.CONFIG)
        finally:
            collect._sensenova_chat = real
        self.assertEqual(done, 1)
        self.assertEqual(it["zh_full"], "该公司发布了新产品。")
        self.assertEqual(it["llm_summary"], "该公司发布了新产品。")

    def test_still_bad_result_is_rejected(self):
        # 模型改完仍命中禁用词 → 不采纳，保留原文（宁可留坏词也不接受坏改）
        it = self._item(llm_summary="颠覆传统认知。")
        real = collect._sensenova_chat
        collect._sensenova_chat = lambda m, c, **k: {"0": {"summary": "颠覆了所有认知。"}}
        try:
            collect.llm_mend_wording([it], [], collect.CONFIG)
        finally:
            collect._sensenova_chat = real
        self.assertEqual(it["llm_summary"], "颠覆传统认知。", "改完仍违规就不采纳")

    def test_mend_syncs_topic_representative(self):
        # 代表稿是 enhance 阶段复制的副本，不同步的话热点榜还显示坏词
        it = self._item(llm_summary="颠覆认知。")
        topics = [{"representative": {"url": "https://e/1", "llm_summary": "颠覆认知。"}}]
        real = collect._sensenova_chat
        collect._sensenova_chat = lambda m, c, **k: {"0": {"summary": "改变了既有认识。"}}
        try:
            collect.llm_mend_wording([it], topics, collect.CONFIG)
        finally:
            collect._sensenova_chat = real
        self.assertEqual(topics[0]["representative"]["llm_summary"], "改变了既有认识。")


class TestStoryDigest(unittest.TestCase):
    def setUp(self):
        self._sleep = collect.time.sleep
        collect.time.sleep = lambda s: None

    def tearDown(self):
        collect.time.sleep = self._sleep
        collect.start_llm_budget(None)

    def _topic(self, tid, sources, title="事件"):
        return {"id": tid, "title": title, "source_count": sources, "signal_count": sources,
                "links": [{"url": "https://e/1", "title": "报道一", "source": "S1"},
                          {"url": "https://e/2", "title": "报道二", "source": "S2"}]}

    def test_single_source_topics_get_no_digest(self):
        topics = [self._topic("t1", 1)]
        calls = [0]
        real = collect._sensenova_chat
        collect._sensenova_chat = lambda m, c, **k: (calls.__setitem__(0, calls[0] + 1), {})[1]
        try:
            done = collect.llm_digest(topics, [], collect.CONFIG)
        finally:
            collect._sensenova_chat = real
        self.assertEqual(done, 0, "单源没有综述可言")
        self.assertEqual(calls[0], 0)

    def test_digest_written_and_title_capped(self):
        topics = [self._topic("t1", 3)]
        items = [{"url": "https://e/1", "title": "报道一", "source": "S1", "summary": "x" * 200},
                 {"url": "https://e/2", "title": "报道二", "source": "S2", "summary": "y" * 200}]
        real = collect._sensenova_chat
        collect._sensenova_chat = lambda m, c, **k: {
            "title": "某公司发布新品并开始交付", "digest": "第一句讲核心变化。\n\n第二段讲背景。"}
        try:
            done = collect.llm_digest(topics, items, collect.CONFIG)
        finally:
            collect._sensenova_chat = real
        self.assertEqual(done, 1)
        self.assertIn("核心变化", topics[0]["digest"])
        self.assertEqual(topics[0]["digestTitle"], "某公司发布新品并开始交付")

    def test_overlong_digest_title_not_used(self):
        topics = [self._topic("t1", 3)]
        items = [{"url": "https://e/1", "title": "报道一", "source": "S1", "summary": "x" * 200}]
        real = collect._sensenova_chat
        collect._sensenova_chat = lambda m, c, **k: {
            "title": "这是一个明显超过三十个字的非常冗长的所谓综述标题用来测试截断逻辑是否正确工作",
            "digest": "正文。"}
        try:
            collect.llm_digest(topics, items, collect.CONFIG)
        finally:
            collect._sensenova_chat = real
        self.assertNotIn("digestTitle", topics[0], "超长标题不许替换展示标题")
        self.assertEqual(topics[0]["digest"], "正文。")

    def test_non_dict_response_does_not_crash(self):
        topics = [self._topic("t1", 3)]
        items = [{"url": "https://e/1", "title": "报道一", "source": "S1", "summary": "x" * 200}]
        real = collect._sensenova_chat
        collect._sensenova_chat = lambda m, c, **k: ["not", "a", "dict"]
        try:
            done = collect.llm_digest(topics, items, collect.CONFIG)
        finally:
            collect._sensenova_chat = real
        self.assertEqual(done, 0)
        self.assertNotIn("digest", topics[0])

    def test_failure_degrades_without_blocking(self):
        topics = [self._topic("t1", 3)]
        items = [{"url": "https://e/1", "title": "报道一", "source": "S1", "summary": "x" * 200}]
        real = collect._sensenova_chat

        def boom(m, c, **k):
            raise RuntimeError("timeout")

        collect._sensenova_chat = boom
        try:
            done = collect.llm_digest(topics, items, collect.CONFIG)
        finally:
            collect._sensenova_chat = real
        self.assertEqual(done, 0)
        self.assertNotIn("digest", topics[0])


class TestNewPromptContracts(unittest.TestCase):
    """三个新 prompt 的关键纪律必须在位（与既有的 score/extract 契约测试同一思路）。"""

    def test_prefilter_has_three_labels_and_guard(self):
        p = collect.CONFIG["prompts"]["prefilter"]
        for lab in ("PASS", "BLOCK", "UNKNOWN"):
            self.assertIn(lab, p)
        self.assertIn("不可信数据", p, "预筛同样要防注入")
        self.assertIn("不能仅以", p, "BLOCK 需要正面依据，不能靠'未提及'")

    def test_mend_is_scoped_to_listed_issues(self):
        p = collect.CONFIG["prompts"]["mend"]
        self.assertIn("只改列出的这几处", p)
        self.assertIn("不增删事实", p)
        self.assertIn("{fields}", p)

    def test_digest_first_sentence_rule(self):
        p = collect.CONFIG["prompts"]["digest"]
        self.assertIn("第一句直接说清", p)
        self.assertIn("不推测、不补造", p)
        self.assertIn("不能悄悄抹平", p, "新旧矛盾必须写明（AIHOT story-digest）")

    def test_wording_table_is_deliberately_narrow(self):
        # 表里不许出现正文支持的正当用法（否则会误改正常词）
        joined = "|".join(pat for pat, _ in collect.READER_WORDING)
        for legit in ("首次", "最大", "唯一"):
            self.assertNotIn(legit, joined,
                             "%s 是正文支持的正当用法，进禁用表会误伤" % legit)
        self.assertTrue(collect.READER_WORDING, "词表不该为空")


if __name__ == "__main__":
    unittest.main(verbosity=2)
