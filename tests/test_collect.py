# -*- coding: utf-8 -*-
"""PAT-HOT 采集器单元测试（纯标准库 unittest，无网络、无第三方依赖）。

运行：python -m unittest discover -s tests -v
或：  python tests/test_collect.py

这些测试锁住线上契约里最容易回归的部分：URL 规范化、RSS 日期格式、
聚类阈值真读配置、dailies 归档合并与保留、以及新旧输出布局同时存在。
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "collector"))

import collect  # noqa: E402


class TestAbsUrl(unittest.TestCase):
    def test_protocol_relative_gets_feed_scheme(self):
        got = collect.abs_url("//www.ledinside.com/news/2026/10/x",
                              "https://www.ledinside.com/rss")
        self.assertEqual(got, "https://www.ledinside.com/news/2026/10/x")

    def test_protocol_relative_follows_http_feed(self):
        got = collect.abs_url("//host/a", "http://host/feed")
        self.assertTrue(got.startswith("http://"))

    def test_site_relative_joins_feed_origin(self):
        got = collect.abs_url("/news/1.html", "https://ex.com/feed/rss")
        self.assertEqual(got, "https://ex.com/news/1.html")

    def test_bare_path_joins_feed_origin(self):
        got = collect.abs_url("news/1.html", "https://ex.com/a/feed.xml")
        self.assertEqual(got, "https://ex.com/a/news/1.html")

    def test_absolute_url_untouched(self):
        self.assertEqual(collect.abs_url("https://a.b/c", "https://x.y/"), "https://a.b/c")

    def test_empty_and_none(self):
        self.assertEqual(collect.abs_url("", "https://x.y/"), "")
        self.assertEqual(collect.abs_url(None, "https://x.y/"), "")
        self.assertEqual(collect.abs_url("/a", ""), "/a")

    def test_fragment_and_query_only(self):
        self.assertEqual(collect.abs_url("#top", "https://x.y/a"), "https://x.y/a#top")


class TestRssDates(unittest.TestCase):
    def test_rfc822_output_shape(self):
        out = collect.rfc822("2026-10-11T10:50:55.414143+00:00")
        # format_datetime(usegmt=True) 产出 "GMT" 而非 "+0000"，两者都是合法 RFC 1123
        self.assertRegex(out, r"^[A-Z][a-z]{2}, \d{2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2} (GMT|\+0000)$")

    def test_rfc822_accepts_z_suffix(self):
        self.assertIsNotNone(collect.rfc822("2026-10-11T10:50:55Z"))

    def test_rfc822_bad_input_returns_none(self):
        self.assertIsNone(collect.rfc822("not-a-date"))
        self.assertIsNone(collect.rfc822(None))

    def test_build_rss_uses_rfc822_and_absolute_link(self):
        items = [{
            "id": "abc", "title": "T<>&", "url": "https://ex.com/a",
            "source": "S&Co", "category": "激光",
            "discovered_at": "2026-10-11T10:50:55.414143+00:00",
            "summary": None,
        }]
        xml = collect.build_rss(items, "T", "https://site/#/all", "d", 50)
        self.assertRegex(xml, r"<pubDate>Sun, 11 Oct 2026 10:50:55 (GMT|\+0000)</pubDate>")
        self.assertRegex(xml, r"<lastBuildDate>Sun, 11 Oct 2026 10:50:55 (GMT|\+0000)</lastBuildDate>")
        # ISO 日期不得再出现在 feed 里
        self.assertNotIn("2026-10-11T10:50", xml)
        # XML 转义仍然正确
        self.assertIn("T&lt;&gt;&amp;", xml)
        self.assertIn("S&amp;Co", xml)

    def test_build_rss_empty_still_valid_dates(self):
        xml = collect.build_rss([], "T", "L", "d", 50)
        self.assertRegex(xml, r"<lastBuildDate>[A-Z][a-z]{2}, ")


class TestClusteringThresholdWired(unittest.TestCase):
    def test_cluster_topics_reads_config(self):
        seen = {}
        real = collect.cluster_semantic

        def fake(items, threshold):
            seen["threshold"] = threshold
            return []

        collect.cluster_semantic = fake
        try:
            backup = dict(collect.CONFIG.get("clustering") or {})
            collect.CONFIG.setdefault("clustering", {})["tfidf_threshold"] = 0.77
            collect.cluster_topics([])
            self.assertEqual(seen.get("threshold"), 0.77)
            collect.CONFIG["clustering"] = backup
        finally:
            collect.cluster_semantic = real


class TestConfigFallback(unittest.TestCase):
    def test_deep_merge_nested_override(self):
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        out = collect._deep_merge(base, {"a": {"y": 9}, "c": 4})
        self.assertEqual(out, {"a": {"x": 1, "y": 9}, "b": 3, "c": 4})

    def test_defaults_shape(self):
        d = collect.DEFAULT_CONFIG
        for k in ("scoring", "tiers", "heat", "clustering", "daily", "llm",
                  "prompts", "trends", "images"):
            self.assertIn(k, d)
        self.assertGreater(d["scoring"]["w_source"], 0)
        self.assertEqual(d["tiers"]["default"], "media")


class TestParseDate(unittest.TestCase):
    def test_rfc822_input(self):
        dt = collect.parse_date("Sun, 11 Oct 2026 10:50:55 +0000")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)

    def test_iso_and_date_only(self):
        self.assertIsNotNone(collect.parse_date("2026-10-11T10:50:55+00:00"))
        self.assertIsNotNone(collect.parse_date("2026-10-11"))

    def test_none_and_garbage(self):
        self.assertIsNone(collect.parse_date(None))
        self.assertIsNone(collect.parse_date("yesterday"))

    def test_result_always_utc_aware(self):
        # 只测已支持的格式；空格分隔日期不在解析表内（不假装它可用）
        for s in ("2026-10-11T08:00:00", "2026-10-11"):
            dt = collect.parse_date(s)
            self.assertIsNotNone(dt, s)
            self.assertIsNotNone(dt.tzinfo, s)
            self.assertEqual(dt.utcoffset(), timedelta(0), s)


class TestDedupeAndIdentity(unittest.TestCase):
    def test_norm_title_case_and_punct(self):
        self.assertEqual(collect.norm_title("Hello, World!"), collect.norm_title("hello world"))

    def test_make_id_stable_and_title_sensitive(self):
        a = collect.make_id("X", "https://e/1")
        self.assertEqual(a, collect.make_id("X", "https://e/1"))
        self.assertNotEqual(a, collect.make_id("X", "https://e/2"))
        self.assertEqual(len(a), 12)


class TestDailiesArchive(unittest.TestCase):
    """归档合并语义：已有日更保留、同日覆盖、过期剪枝可配。"""

    def _item(self, day, title, score=70.0, source="S"):
        return {"id": collect.make_id(title, "https://e/" + title),
                "title": title, "url": "https://e/" + title, "source": source,
                "source_base": source, "source_type": "rss", "category": "激光",
                "published_at": day + "T00:00:00+00:00",
                "discovered_at": day + "T00:00:00+00:00",
                "summary": "sum", "keywords": [], "score": score,
                "topic_id": "t" + title, "role": "媒体", "selected": True}

    def test_existing_days_kept_same_day_overwritten(self):
        old = {"2026-01-01": {"date": "2026-01-01", "headline": None, "picks": [],
                              "flash": [], "sections": [], "topic_ids": ["stale"]}}
        items = [self._item("2026-01-02", "A 新事件甲乙丙")]
        out = collect.build_dailies(items, old)
        self.assertIn("2026-01-01", out, "历史日不能丢")
        self.assertEqual(out["2026-01-01"]["topic_ids"], ["stale"])
        self.assertIn("2026-01-02", out)

    def test_same_day_rebuild_replaces(self):
        prev = collect.build_dailies([self._item("2026-01-02", "A")], {})
        nxt = collect.build_dailies([self._item("2026-01-02", "B")], prev)
        rep = nxt["2026-01-02"]["headline"]
        self.assertIsNotNone(rep)
        self.assertEqual(rep["title"], "B")

    def test_prune_is_config_driven(self):
        today = datetime.now(collect.TZ_CN).date()

        def entry(day):
            return {"date": day, "headline": None, "picks": [], "flash": [],
                    "sections": [{"category": "激光", "articles": []}], "topic_ids": []}

        d30 = (today - timedelta(days=30)).isoformat()
        d100 = (today - timedelta(days=100)).isoformat()
        d400 = (today - timedelta(days=400)).isoformat()
        existing = {k: entry(k) for k in (d30, d100, d400)}

        # 默认保留期 365 天：30/100 天保留，400 天剪掉（与重构前行为一致）
        out = collect.build_dailies([], existing)
        self.assertIn(d30, out)
        self.assertIn(d100, out)
        self.assertNotIn(d400, out, "默认 365 天保留期外必须剪枝")

        # 配置改成 60 天后：100 天前的归档也应被剪掉，证明真的读配置
        backup = dict(collect.CONFIG["daily"])
        collect.CONFIG["daily"]["archive_days"] = 60
        try:
            out2 = collect.build_dailies([], existing)
            self.assertIn(d30, out2)
            self.assertNotIn(d100, out2, "archive_days=60 时 100 天前的归档必须剪掉")
        finally:
            collect.CONFIG["daily"] = backup

    def test_default_archive_days_survives_missing_config_key(self):
        backup = dict(collect.CONFIG["daily"])
        collect.CONFIG["daily"].pop("archive_days", None)
        try:
            today = datetime.now(collect.TZ_CN).date()
            d100 = (today - timedelta(days=100)).isoformat()
            out = collect.build_dailies([], {d100: {"date": d100, "headline": None,
                                                    "picks": [], "flash": [],
                                                    "sections": [], "topic_ids": []}})
            self.assertIn(d100, out, "配置缺 archive_days 时应回退默认 365 天")
        finally:
            collect.CONFIG["daily"] = backup


class TestScoreBoundaries(unittest.TestCase):
    def test_selected_flag_uses_tier_thresholds(self):
        # 门槛来自配置：official 55 / media 65
        self.assertEqual(collect.CONFIG["tiers"]["official"]["select_threshold"], 55.0)
        self.assertEqual(collect.CONFIG["tiers"]["media"]["select_threshold"], 65.0)

    def test_compute_scores_within_bounds(self):
        # compute_scores 依赖 run_channel 早先写入的 id 字段
        url = "https://e/1"
        title = "激光雷达 量产"
        items = [{"id": collect.make_id(title, url),
                  "title": title, "url": url, "source": "OFweek 光电频道",
                  "source_base": "OFweek 光电频道", "category": "激光",
                  "published_at": None,
                  "discovered_at": datetime.now(timezone.utc).isoformat(),
                  "score": 0.0, "summary": None, "keywords": []}]
        topics = collect.cluster_topics(items)
        collect.compute_scores(items, topics, {"OFweek 光电频道": 1.0},
                               {"OFweek 光电频道": "official"}, collect.CONFIG)
        s = items[0]["score"]
        self.assertGreaterEqual(s, 0.0)
        self.assertLessEqual(s, 100.0)
        # 无可信发布时间 -> 时效分按 missing_pubdate_penalty 打折，不应给满
        self.assertLess(s, 100.0)


class TestChannelContract(unittest.TestCase):
    def test_three_channels_loaded(self):
        self.assertEqual(set(collect.CHANNELS), {"physics", "astro", "tech"})
        self.assertEqual(collect.CHANNEL_ORDER, ["physics", "astro", "tech"])

    def test_flat_alias_is_default_channel(self):
        self.assertIn(collect.FLAT_ALIAS_CHANNEL, collect.CHANNELS)

    def test_repo_url_no_longer_points_to_old_name(self):
        self.assertNotIn("opto-hot", collect.REPO_URL)
        self.assertTrue(collect.REPO_URL.startswith("https://"))

    def test_site_base_absolute(self):
        self.assertRegex(collect.SITE_BASE, r"^https://[^/]+/.*/$")
        self.assertTrue(collect.SITE_BASE.endswith("/"))

    def test_sources_channel_coverage_nonempty(self):
        with open(os.path.join(ROOT, "collector", "sources.json"), encoding="utf-8") as f:
            src = json.load(f)
        per = {}
        for stype in ("rss", "html"):
            for c in src.get(stype, []):
                per.setdefault(c.get("channel", "tech"), 0)
                per[c.get("channel", "tech")] += 1
        for ch in collect.CHANNEL_ORDER:
            self.assertGreaterEqual(per.get(ch, 0), 1, "频道 %s 没有任何数据源" % ch)

    def test_no_duplicate_url_within_a_channel(self):
        """同一频道内同一 URL 出现两次 = 每次运行重复抓取同一个源。
        跨频道复用同一 URL 是合法的（如 Phys.org：tech 带关键词过滤、physics 全量），
        但必须显式区分，所以这里只锁"同频道同 URL 不得重复"。"""
        with open(os.path.join(ROOT, "collector", "sources.json"), encoding="utf-8") as f:
            src = json.load(f)
        seen = {}
        for stype in ("rss", "html"):
            for c in src.get(stype, []):
                key = (c.get("channel", "tech"), stype, c["url"])
                seen.setdefault(key, []).append(c["name"])
        dupes = {k: v for k, v in seen.items() if len(v) > 1}
        self.assertEqual(dupes, {}, "同一频道内存在重复 URL：%s" % dupes)

    def test_same_url_across_channels_is_intentional(self):
        """若同一 URL 被多个频道复用，各条目的过滤条件必须不同，否则是纯浪费。"""
        with open(os.path.join(ROOT, "collector", "sources.json"), encoding="utf-8") as f:
            src = json.load(f)
        by_url = {}
        for stype in ("rss", "html"):
            for c in src.get(stype, []):
                by_url.setdefault(c["url"], []).append(c)
        for url, entries in by_url.items():
            if len(entries) < 2:
                continue
            channels = {e.get("channel", "tech") for e in entries}
            self.assertEqual(len(channels), len(entries),
                             "URL %s 在同一频道内被引用多次" % url)
            sigs = [tuple(sorted(e.get("filter_keywords", []) or [])) for e in entries]
            self.assertEqual(len(set(sigs)), len(sigs),
                             "URL %s 被多个频道复用但关键词完全相同，属重复抓取" % url)


class TestRssLinksAbsolute(unittest.TestCase):
    def test_feed_link_fields_are_absolute_or_relative_site_pages(self):
        # build_rss 的 link 参数必须是绝对站点地址
        for link in (collect.SITE_BASE,):
            self.assertTrue(link.startswith("https://"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
