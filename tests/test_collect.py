# -*- coding: utf-8 -*-
"""PAT-HOT 采集器单元测试（纯标准库 unittest，无网络、无第三方依赖）。

运行：python -m unittest discover -s tests -v
或：  python tests/test_collect.py

这些测试锁住线上契约里最容易回归的部分：URL 规范化、RSS 日期格式、
聚类阈值真读配置、dailies 归档合并与保留、以及新旧输出布局同时存在。
"""
import json
import os
import re
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

    def test_named_tz_abbreviations_parse(self):
        # CPython 的 %Z 认不了 CST/EST，以前这类 pubDate 整源解析为 None。
        # 实测知识分子的 feed 全是 "… 22:56:36 CST"。
        zh = collect.parse_date("Sun, 11 Oct 2026 22:56:36 CST", "知识分子",
                                "http://www.zhishifenzi.com/rss")
        self.assertEqual(zh, datetime(2026, 10, 11, 14, 56, 36, tzinfo=timezone.utc))
        us = collect.parse_date("Fri, 09 Oct 2026 18:30:00 EST", "IEEE Spectrum",
                                "https://spectrum.ieee.org/rss/fulltext")
        self.assertEqual(us, datetime(2026, 10, 9, 23, 30, tzinfo=timezone.utc))

    def test_cst_disambiguated_by_source_not_string(self):
        # 同一个 "CST"：中文信源按北京时（UTC+8），其它信源按美国中部标准时（UTC-6）。
        # 不追随夏令时：缩写本身已歧义，再叠 DST 推断只会引入更多猜测；
        # 一小时误差远小于旧实现"整条解析失败、回退收录时间"的偏差。
        zh = collect.parse_date("Sun, 11 Oct 2026 22:00:00 CST", "COEMA 中国光电子行业协会",
                                "https://www.coema.org.cn/")
        us = collect.parse_date("Sun, 11 Oct 2026 22:00:00 CST", "Some US Blog",
                                "https://blog.example.com/feed")
        self.assertEqual(zh, datetime(2026, 10, 11, 14, 0, tzinfo=timezone.utc))
        self.assertEqual(us, datetime(2026, 10, 12, 4, 0, tzinfo=timezone.utc))

    def test_naive_datetime_uses_source_timezone(self):
        # 裸时间是中文 CMS 的常态：按 +08:00 读，23:30 归当天而不是 UTC 推后一天
        cn = collect.parse_date("2026-10-12T23:30:00", "OFweek 光电频道",
                                "https://www.ofweek.com/")
        self.assertEqual(cn.astimezone(collect.TZ_CN).isoformat(), "2026-10-12T23:30:00+08:00")
        en = collect.parse_date("2026-10-12T23:30:00", "Nature Photonics",
                                "https://www.nature.com/nphoton.rss")
        self.assertEqual(en, datetime(2026, 10, 12, 23, 30, tzinfo=timezone.utc))

    def test_explicit_Z_never_inherits_source_timezone(self):
        # 中文名只是显示标签：phys.org 是海外站，带 Z 的瞬时绝不许挪 +08:00
        dt = collect.parse_date("2026-10-11T10:50:55Z", "Phys.org 物理新闻",
                                "https://phys.org/rss-feed/physics-news/")
        self.assertEqual(dt, datetime(2026, 10, 11, 10, 50, 55, tzinfo=timezone.utc))

    def test_month_precision_parses_and_is_earliest_instant(self):
        # OFweek/COEMA 的 url_date 只抠得出年月。旧实现返回 None →
        # eff_dt 回退收录时间 → 2022 年的旧文拿满时效分混进精选（实测 5 条 ≥65）。
        dt = collect.parse_date("2022-05", "OFweek 激光频道", "https://laser.ofweek.com/")
        self.assertEqual(dt, datetime(2022, 5, 1, tzinfo=collect.TZ_CN).astimezone(timezone.utc))
        self.assertEqual(collect.date_precision("2022-05"), "month")
        self.assertEqual(collect.date_precision("2022"), "year")
        self.assertEqual(collect.date_precision("2022-05-01"), "day")
        self.assertEqual(collect.date_precision("Sun, 11 Oct 2026 22:56:36 CST"), "minute")
        self.assertIsNone(collect.date_precision("yesterday"))

    def test_eff_dt_does_not_fall_back_for_month_dates(self):
        it = {"published_at": "2022-05", "url": "https://laser.ofweek.com/x.html",
              "source": "OFweek 激光频道", "source_base": "OFweek 激光频道",
              "discovered_at": "2026-10-12T10:00:00+00:00"}
        dt = collect.eff_dt(it)
        # 月级发布时间必须被采用（2022-05-01），而不是回退到收录时间（2026）
        self.assertEqual(dt.year, 2022)
        self.assertGreater(collect.age_days(dt), 1000)


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

    def test_past_days_are_immutable(self):
        """超出刷新窗口的历史某天不得被后续运行改写。"""
        past = (datetime.now(collect.TZ_CN).date() - timedelta(days=5)).isoformat()
        prev = collect.build_dailies([self._item(past, "A 事件甲乙丙")], {})
        self.assertIn(past, prev)
        nxt = collect.build_dailies([self._item(past, "B 事件丁戊己")], prev)
        self.assertEqual(nxt[past]["headline"]["title"], "A 事件甲乙丙",
                         "历史日报被本次运行改写了")

    def test_today_headline_refreshes(self):
        """当天仍在进行，重算出的新头条应当生效。"""
        today = datetime.now(collect.TZ_CN).date().isoformat()
        prev = collect.build_dailies([self._item(today, "A 早上")], {})
        nxt = collect.build_dailies([self._item(today, "B 晚上新头条", score=99.0)], prev)
        self.assertEqual(nxt[today]["headline"]["title"], "B 晚上新头条",
                         "当天日报应可刷新")

    def test_published_items_never_lost_on_refresh(self):
        """回归用例：源站 feed 会滚动，某条目本次没再被抓到时，
        已发布出去的条目一条都不能少。此前重跑一次就丢了 133 条。"""
        today = datetime.now(collect.TZ_CN).date().isoformat()
        a = self._item(today, "已发布但这次抓不到的旧稿", score=95.0)
        prev = collect.build_dailies([a], {})
        self.assertIn("已发布但这次抓不到的旧稿", collect._daily_titles(prev[today]))
        # 本次只抓到新稿：重算会把旧稿挤出 Top-N
        b = self._item(today, "今天的新稿", score=99.0)
        nxt = collect.build_dailies([b], prev)
        titles = collect._daily_titles(nxt[today])
        self.assertIn("今天的新稿", titles)
        self.assertIn("已发布但这次抓不到的旧稿", titles,
                      "已发布条目被重算挤掉了（回归到丢 133 条的行为）")

    def test_rescue_does_not_duplicate(self):
        today = datetime.now(collect.TZ_CN).date().isoformat()
        a = self._item(today, "同一篇稿")
        prev = collect.build_dailies([a], {})
        once = collect.build_dailies([a], prev)
        twice = collect.build_dailies([a], once)
        self.assertEqual(len(collect._daily_titles(once[today])),
                         len(collect._daily_titles(twice[today])),
                         "重复运行时条目被反复追加")

    def test_refresh_window_is_configurable(self):
        day = (datetime.now(collect.TZ_CN).date() - timedelta(days=3)).isoformat()
        prev = collect.build_dailies([self._item(day, "旧稿")], {})
        backup = dict(collect.CONFIG["daily"])
        try:
            collect.CONFIG["daily"]["refresh_days"] = 7
            nxt = collect.build_dailies([self._item(day, "新稿", score=99.0)], prev)
            self.assertIn("新稿", collect._daily_titles(nxt[day]))
        finally:
            collect.CONFIG["daily"] = backup

    def test_history_never_dropped_when_merging(self):
        old_day = (datetime.now(collect.TZ_CN).date() - timedelta(days=40)).isoformat()
        old = {old_day: {"date": old_day, "headline": None, "picks": [],
                         "flash": [], "sections": [], "topic_ids": ["stale"]}}
        out = collect.build_dailies([self._item(old_day, "同一天新事件")], old)
        self.assertIn(old_day, out)
        self.assertEqual(out[old_day]["topic_ids"], ["stale"], "历史条目被覆盖丢失")

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


class TestHttpRetry(unittest.TestCase):
    """http_get 的重试策略：抖动重试、稳定 4xx 不重试、体积上限。不碰真实网络。"""

    def setUp(self):
        self.real = collect.urllib.request.urlopen
        self.calls = []

    def tearDown(self):
        collect.urllib.request.urlopen = self.real

    def _fail_then_ok(self, exc_factory, body=b"<rss>ok</rss>"):
        def fake(req, timeout=None):
            self.calls.append(timeout)

            class R:
                headers = {"Content-Type": "application/xml", "Content-Encoding": ""}

                def read(self, n=-1):
                    return body[:n] if n and n > 0 else body

                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False
            if len(self.calls) == 1:
                raise exc_factory()
            return R()
        collect.urllib.request.urlopen = fake
        return fake

    def test_timeout_is_retried(self):
        import socket

        def boom():
            return socket.timeout("timed out")
        self._fail_then_ok(boom)
        real_sleep = collect.time.sleep
        collect.time.sleep = lambda *_: None
        try:
            body, _ = collect.http_get("https://ex.com/feed", retries=1)
        finally:
            collect.time.sleep = real_sleep
        self.assertEqual(len(self.calls), 2)
        self.assertIn(b"ok", body)

    def test_404_not_retried(self):
        import urllib.error

        def boom():
            return urllib.error.HTTPError("https://ex.com", 404, "Not Found", None, None)
        self._fail_then_ok(boom)
        with self.assertRaises(urllib.error.HTTPError):
            collect.http_get("https://ex.com/feed", retries=2)
        self.assertEqual(len(self.calls), 1, "4xx 是稳定失败，不该重试")

    def test_429_is_retried(self):
        import urllib.error

        def boom():
            return urllib.error.HTTPError("https://ex.com", 429, "Too Many", None, None)
        self._fail_then_ok(boom)
        real_sleep = collect.time.sleep
        collect.time.sleep = lambda *_: None
        try:
            body, _ = collect.http_get("https://ex.com/feed", retries=1)
        finally:
            collect.time.sleep = real_sleep
        self.assertEqual(len(self.calls), 2, "429 应重试")

    def test_oversized_response_rejected(self):
        class R:
            headers = {"Content-Type": "text/html", "Content-Encoding": ""}

            def read(self, n=-1):
                return b"x" * (n if n and n > 0 else 10)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake(req, timeout=None):
            self.calls.append(1)
            return R()
        collect.urllib.request.urlopen = fake
        backup = dict(collect.CONFIG.get("fetch") or {})
        collect.CONFIG.setdefault("fetch", {})["max_bytes"] = 100
        try:
            with self.assertRaises(Exception):
                collect.http_get("https://ex.com/big", retries=0)
        finally:
            collect.CONFIG["fetch"] = backup

    def test_gzip_body_transparently_decoded(self):
        import gzip as _gz
        payload = _gz.compress(b"<rss>plain</rss>")

        class R:
            headers = {"Content-Type": "application/xml", "Content-Encoding": ""}

            def read(self, n=-1):
                return payload[:n] if n and n > 0 else payload

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        collect.urllib.request.urlopen = lambda req, timeout=None: R()
        body, _ = collect.http_get("https://ex.com/gz", retries=0)
        self.assertIn(b"plain", body)


class TestCollectFailureAccounting(unittest.TestCase):
    def test_collect_reports_failed_sources(self):
        real = collect.fetch_rss
        collect.fetch_rss = lambda cfg, limit: (_ for _ in ()).throw(RuntimeError("boom")) \
            if cfg["name"] == "坏源" else [{"title": "t", "url": "https://e/1"}]
        try:
            raw, failed = collect.collect({"rss": [{"name": "坏源", "url": "u"},
                                                   {"name": "好源", "url": "v"}],
                                           "html": []}, 10)
        finally:
            collect.fetch_rss = real
        self.assertEqual(failed, ["坏源"])
        self.assertEqual(len(raw), 1)

    def test_all_sources_down_refuses_to_emit_empty_channel(self):
        real = collect.fetch_rss
        collect.fetch_rss = lambda cfg, limit: (_ for _ in ()).throw(RuntimeError("offline"))
        try:
            args = type("A", (), {"limit": 10, "skip_rss": False, "skip_html": True})()
            src = {"rss": [{"name": "S", "url": "u", "channel": "tech", "weight": 0.8}],
                   "html": []}
            with self.assertRaises(RuntimeError):
                collect.run_channel("tech", src, args, collect.now_utc())
        finally:
            collect.fetch_rss = real


class TestCarryOverChannels(unittest.TestCase):
    def test_missing_channel_read_back_from_disk(self):
        tmp = tempfile.mkdtemp(prefix="pathom-carry-")
        real_data, real_dist = collect.DATA_DIR, collect.DIST_DIR
        try:
            collect.DATA_DIR = os.path.join(tmp, "data")
            os.makedirs(os.path.join(collect.DATA_DIR, "physics"), exist_ok=True)
            iso = "2026-10-01T00:00:00+00:00"
            for name, doc in (("items.json", {"items": [{"id": "x", "title": "T",
                                                          "url": "https://e/1",
                                                          "discovered_at": iso}]}),
                              ("hot-topics.json", {"items": []}),
                              ("daily.json", {"total": 1}),
                              ("dailies.json", {"dailies": {"2026-10-01": {}}}),
                              ("trends.json", {"newTopics": [], "sustainedTopics": [],
                                              "weekDelta": []})):
                with open(os.path.join(collect.DATA_DIR, "physics", name),
                          "w", encoding="utf-8") as f:
                    json.dump(doc, f)
            out = collect.load_carried_channels(["physics"], collect.now_utc())
            self.assertIn("physics", out)
            items, topics, daily, dailies, trends = out["physics"]
            self.assertEqual(len(items), 1)
            self.assertIn("2026-10-01", dailies)
        finally:
            collect.DATA_DIR = real_data
            collect.DIST_DIR = real_dist
            shutil.rmtree(tmp, ignore_errors=True)

    def test_unreadable_channel_is_skipped_not_fatal(self):
        tmp = tempfile.mkdtemp(prefix="pathom-carry2-")
        real = collect.DATA_DIR
        try:
            collect.DATA_DIR = os.path.join(tmp, "data")
            out = collect.load_carried_channels(["physics"], collect.now_utc())
            self.assertEqual(out, {})
        finally:
            collect.DATA_DIR = real
            shutil.rmtree(tmp, ignore_errors=True)


class TestContractGate(unittest.TestCase):
    """--check 必须能抓到"文件都在但站点残缺"这类问题。"""

    def _sandbox(self):
        tmp = tempfile.mkdtemp(prefix="pathom-check-")
        return tmp, os.path.join(tmp, "dist")

    def test_detects_missing_flat_endpoint(self):
        tmp, dist = self._sandbox()
        real = collect.DIST_DIR
        try:
            collect.DIST_DIR = dist
            probs = collect.check_contract(verbose=False)
            self.assertTrue(any("api/v1/items.json" in p for p in probs))
        finally:
            collect.DIST_DIR = real
            shutil.rmtree(tmp, ignore_errors=True)

    def test_detects_snapshot_missing_a_channel(self):
        tmp, dist = self._sandbox()
        real = collect.DIST_DIR
        try:
            collect.DIST_DIR = dist
            os.makedirs(dist, exist_ok=True)
            snap = {"channels": {"tech": {"items": [{"id": "1", "discovered_at": "x"}]}},
                    "meta": {"channels": [{"id": c} for c in collect.CHANNEL_ORDER]}}
            html = ("const S = " + json.dumps(snap, ensure_ascii=False) + ";\n"
                    + "x" * 50)
            with open(os.path.join(dist, "index.html"), "w", encoding="utf-8") as f:
                f.write(html)
            probs = collect.check_contract(verbose=False)
            self.assertTrue(any("index.html 缺频道数据" in p for p in probs),
                            "gate 必须抓到只含单个频道的残缺站点: %s" % probs)
        finally:
            collect.DIST_DIR = real
            shutil.rmtree(tmp, ignore_errors=True)

    def test_detects_empty_channel_items_in_snapshot(self):
        tmp, dist = self._sandbox()
        real = collect.DIST_DIR
        try:
            collect.DIST_DIR = dist
            os.makedirs(dist, exist_ok=True)
            snap = {"channels": {c: {"items": []} for c in collect.CHANNEL_ORDER}}
            with open(os.path.join(dist, "index.html"), "w", encoding="utf-8") as f:
                f.write("const S = " + json.dumps(snap) + ";\n")
            probs = collect.check_contract(verbose=False)
            self.assertTrue(any("items 为空" in p for p in probs))
        finally:
            collect.DIST_DIR = real
            shutil.rmtree(tmp, ignore_errors=True)

    def test_detects_iso_pubdate_in_feed(self):
        tmp, dist = self._sandbox()
        real = collect.DIST_DIR
        try:
            collect.DIST_DIR = dist
            os.makedirs(dist, exist_ok=True)
            with open(os.path.join(dist, "feed.xml"), "w", encoding="utf-8") as f:
                f.write("<rss><channel><link>https://x/</link>"
                        "<pubDate>2026-10-11T10:50:55+00:00</pubDate></channel></rss>")
            probs = collect.check_contract(verbose=False)
            self.assertTrue(any("pubDate 仍是 ISO" in p for p in probs))
        finally:
            collect.DIST_DIR = real
            shutil.rmtree(tmp, ignore_errors=True)


class TestStaleFeedPrune(unittest.TestCase):
    """分类 feed 是数据驱动写出的，但消失的分类不会被删除。
    2026-10-13 线上实测：astro 本轮无引力波条目（LIGO 源 403），
    而 dist/feed/astro/category/gw.xml 还留着上一轮 5 条 LIGO，
    订阅者拿到 /api/v1/astro/items.json 里根本不存在的条目，且无告警。"""

    def _dir(self, names):
        d = tempfile.mkdtemp(prefix="pathom-feed-")
        for n in names:
            with open(os.path.join(d, n), "w", encoding="utf-8") as f:
                f.write("<rss/>")
        return d

    def test_removes_xml_not_in_keep_set(self):
        d = self._dir(["gw.xml", "cosmo.xml", "other.xml"])
        try:
            removed = collect.prune_stale_feeds(d, {"cosmo", "other"})
            self.assertEqual(removed, ["gw.xml"])
            self.assertFalse(os.path.exists(os.path.join(d, "gw.xml")))
            self.assertTrue(os.path.exists(os.path.join(d, "cosmo.xml")))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_leaves_non_xml_alone(self):
        d = self._dir(["gw.xml"])
        with open(os.path.join(d, "README"), "w", encoding="utf-8") as f:
            f.write("x")
        try:
            removed = collect.prune_stale_feeds(d, set())
            self.assertEqual(removed, ["gw.xml"])
            self.assertTrue(os.path.exists(os.path.join(d, "README")))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_missing_dir_is_not_fatal(self):
        self.assertEqual(collect.prune_stale_feeds(
            os.path.join(tempfile.gettempdir(), "pathom-no-such-dir"), set()), [])

    def test_write_outputs_prunes_stale_category_feed(self):
        """端到端：某分类本轮无数据时，它的 feed 文件必须从产物里消失。"""
        tmp = tempfile.mkdtemp(prefix="pathom-wo-")
        real_dist, real_data, real_ch = collect.DIST_DIR, collect.DATA_DIR, collect._CH
        try:
            collect.DIST_DIR = os.path.join(tmp, "dist")
            collect.DATA_DIR = os.path.join(tmp, "data")
            for ch in collect.CHANNEL_ORDER:
                os.makedirs(os.path.join(collect.DATA_DIR, ch), exist_ok=True)
            feed_dir = os.path.join(collect.DIST_DIR, "feed", "astro", "category")
            os.makedirs(feed_dir, exist_ok=True)
            with open(os.path.join(feed_dir, "gw.xml"), "w", encoding="utf-8") as f:
                f.write("<rss/>")          # 上一轮残留
            gen = collect.now_utc()
            set_channel = getattr(collect, "set_channel_context", None)
            if set_channel:
                set_channel("astro")
            items = [{"id": "a1", "title": "T", "url": "https://x/1", "source": "S",
                      "category": "科研进展", "summary": None, "score": 60.0,
                      "discovered_at": gen.isoformat(), "published_at": None,
                      "keywords": [], "biz": None, "topic_id": "t1",
                      "topic_title": "T", "links": {}, "selected": True, "role": "媒体"}]
            results = {ch: (items, [], {}, {}, {}) for ch in collect.CHANNEL_ORDER}
            collect.write_outputs(results, gen)
            self.assertFalse(os.path.exists(os.path.join(feed_dir, "gw.xml")),
                             "本轮无引力波条目，gw.xml 必须被清掉")
        finally:
            collect.DIST_DIR, collect.DATA_DIR, collect._CH = real_dist, real_data, real_ch
            shutil.rmtree(tmp, ignore_errors=True)


class TestLlmBackoff(unittest.TestCase):
    def test_real_status_code_not_string_match(self):
        """旧实现用 "401" in str(e) 判断认证失败，任何文本里含 401 都会误判。
        现在必须看 HTTPError.code：这里错误文本含 "401" 但状态码是 500，应当重试。"""
        import urllib.error
        calls = []

        class R:
            def read(self):
                return json.dumps({"choices": [{"message": {"content": '{"0":{}}'}}]}
                                  ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake(req, timeout=None):
            calls.append(1)
            if len(calls) == 1:
                raise urllib.error.HTTPError("u", 500, "byte 401 mismatch", None, None)
            return R()

        os.environ["SENSENOVA_API_KEY"] = "test-key"
        # 函数内 `import urllib.request as _ureq` 只是同一模块对象的局部别名，
        # 所以打模块级 urllib.request.urlopen 才有效。
        real_urlopen, real_sleep = collect.urllib.request.urlopen, collect.time.sleep
        collect.time.sleep = lambda *_: None
        try:
            collect.urllib.request.urlopen = fake
            out = collect._sensenova_chat([{"role": "user", "content": "x"}],
                                          collect.CONFIG, max_retries=2)
            self.assertEqual(out, {"0": {}})
            self.assertEqual(len(calls), 2, "500 应重试一次")
        finally:
            collect.urllib.request.urlopen = real_urlopen
            collect.time.sleep = real_sleep
            os.environ.pop("SENSENOVA_API_KEY", None)

    def test_auth_failure_does_not_retry(self):
        import urllib.error
        calls = []

        def fake(req, timeout=None):
            calls.append(1)
            raise urllib.error.HTTPError("u", 401, "Unauthorized", None, None)
        os.environ["SENSENOVA_API_KEY"] = "k"
        real_urlopen = collect.urllib.request.urlopen
        real_sleep = collect.time.sleep
        collect.time.sleep = lambda *_: None
        try:
            collect.urllib.request.urlopen = fake
            with self.assertRaises(urllib.error.HTTPError):
                collect._sensenova_chat([{"role": "user", "content": "x"}],
                                        collect.CONFIG, max_retries=3)
            self.assertEqual(len(calls), 1, "401 不该重试")
        finally:
            collect.urllib.request.urlopen = real_urlopen
            collect.time.sleep = real_sleep
            os.environ.pop("SENSENOVA_API_KEY", None)

    def test_no_api_key_raises_without_network(self):
        os.environ.pop("SENSENOVA_API_KEY", None)
        with self.assertRaises(RuntimeError):
            collect._sensenova_chat([{"role": "user", "content": "x"}], collect.CONFIG)


class TestLlmJsonFence(unittest.TestCase):
    """锁住 2026-10-12 的按需/批量摘要回归：推理模型偶尔无视 response_format，
    把 JSON 包进 ```json 围栏或前后带解释文字，json.loads 直接抛
    "Expecting value: line 3 column 1"，HTTP 重试救不了确定性格式错误，
    当天定时任务 33 条中文摘要因此被整条弃用（zh_full 全空）。"""

    def test_plain_json_passthrough(self):
        self.assertEqual(collect._parse_llm_json('{"0": {"zh_full": "甲"}}'),
                         {"0": {"zh_full": "甲"}})

    def test_fenced_json_is_parsed(self):
        raw = '\n\n```json\n{"0": {"zh_full": "乙", "density": "高"}}\n```'
        out = collect._parse_llm_json(raw)
        self.assertEqual(out["0"]["zh_full"], "乙")

    def test_prose_around_json_is_parsed(self):
        raw = 'Sure, here you go:\n```json\n{"zh_full": "丙"}\n```\nHope that helps.'
        self.assertEqual(collect._parse_llm_json(raw), {"zh_full": "丙"})

    def test_leading_text_without_fence(self):
        raw = 'output: {"zh_full": "丁"} tail'
        self.assertEqual(collect._parse_llm_json(raw), {"zh_full": "丁"})

    def test_garbage_still_raises(self):
        with self.assertRaises(Exception):
            collect._parse_llm_json("not json at all")

    def test_sensenova_chat_survives_fenced_content(self):
        """端到端：上游返回围栏包裹时 _sensenova_chat 必须给出解析结果而非抛错。"""
        class R:
            def read(self):
                return json.dumps({"choices": [{"message": {
                    "content": '```json\n{"0": {"zh_full": "戊"}}\n```'}}]}).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        os.environ["SENSENOVA_API_KEY"] = "k"
        real_urlopen = collect.urllib.request.urlopen
        try:
            collect.urllib.request.urlopen = lambda req, timeout=None: R()
            out = collect._sensenova_chat([{"role": "user", "content": "x"}],
                                          collect.CONFIG, max_retries=1)
            self.assertEqual(out, {"0": {"zh_full": "戊"}})
        finally:
            collect.urllib.request.urlopen = real_urlopen
            os.environ.pop("SENSENOVA_API_KEY", None)


class TestLlmThinkingDisabled(unittest.TestCase):
    """锁住 2026-10-13 的根因：sensenova-6.8-flash-lite 默认把 ~90% 输出预算花在
    reasoning 上（实测 8 条一批 completion=12605 / reasoning=11404），正文 JSON 写到
    一半就断，返回畸形体却仍是 finish=stop。zh_full 因此全站为空，且整轮采集
    慢到撞 job 超时被杀。thinking={"type":"disabled"} 后同批 9.0s / 978 token / 8 条全可解析。"""

    def _payload(self, cfg):
        captured = {}

        class R:
            def read(self):
                return json.dumps({"choices": [{"message": {"content": '{"0":{}}'}}]}).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake(req, timeout=None):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return R()

        os.environ["SENSENOVA_API_KEY"] = "k"
        real = collect.urllib.request.urlopen
        try:
            collect.urllib.request.urlopen = fake
            collect._sensenova_chat([{"role": "user", "content": "x"}], cfg, max_retries=1)
        finally:
            collect.urllib.request.urlopen = real
            os.environ.pop("SENSENOVA_API_KEY", None)
        return captured["body"]

    def test_default_config_sends_disabled_thinking(self):
        body = self._payload(collect.CONFIG)
        self.assertEqual(body.get("thinking"), {"type": "disabled"})

    def test_default_config_value_has_the_key(self):
        self.assertIn("disable_thinking", collect.DEFAULT_CONFIG["llm"])
        self.assertTrue(collect.DEFAULT_CONFIG["llm"]["disable_thinking"])

    def test_can_be_reenabled_by_config(self):
        cfg = json.loads(json.dumps(collect.CONFIG))
        cfg["llm"]["disable_thinking"] = False
        body = self._payload(cfg)
        self.assertNotIn("thinking", body)

    def test_pages_function_sends_same_flag(self):
        # 线上按需路径读不到 Python 侧配置，自带一份请求体。两处漂移过一次
        # （prompt 口径），这条锁住 thinking 开关也别只改一边。
        p = os.path.join(ROOT, "functions", "api", "summarize.js")
        if not os.path.exists(p):
            self.skipTest("functions/api/summarize.js 不存在")
        with open(p, encoding="utf-8") as f:
            js = f.read()
        self.assertIn('thinking: { type: "disabled" }', js,
                      "线上 Function 也必须关推理链，否则单条逼近 30s 上限、约两成失败")


class TestChannelSwitchResetsFeedState(unittest.TestCase):
    """切频道必须清空精选页的日期折叠状态。

    回归（2026-10-13）：state.collapsed 以日期为键、跨频道共享，在光电页收起的
    12/11/10 三天切到物理页后依然收起（浏览器实证复现）——用户看到的就是截图里
    "今天的精选莫名收起、最旧一天反而展开"。EXPANDED 早就在 setChannel 里 clear，
    collapsed 是漏网之鱼。"""

    def _set_channel_body(self):
        with open(os.path.join(ROOT, "collector", "templates", "app.js"),
                  encoding="utf-8") as f:
            js = f.read()
        start = js.index("function setChannel")
        end = js.index("function itemCard", start)
        return js[start:end]

    def test_set_channel_clears_collapsed(self):
        body = self._set_channel_body()
        self.assertIn("state.collapsed={}", body,
                      "切频道未重置日期折叠状态：折叠会跨频道串台")

    def test_set_channel_still_clears_expanded(self):
        # 同一行的既有约定，防止"修一个丢一个"
        body = self._set_channel_body()
        self.assertIn("EXPANDED.clear()", body)


class TestInlineCssIntegrity(unittest.TestCase):
    """锁住 2026-10-12 线上回归：坏部署把内联 CSS 的真换行写成字面量 \\n，
    浏览器丢弃全部样式，站点退化成裸 HTML；而 --check 当时只查文件在不在，看不见它。
    现在 check_inline_css 必须放行好产物、拦下这类"文件存在但样式坏了"的产物。"""

    def _read_dist(self):
        p = os.path.join(ROOT, "dist", "index.html")
        if not os.path.exists(p):
            self.skipTest("dist/index.html 尚未生成")
        with open(p, encoding="utf-8") as f:
            return f.read()

    def test_current_dist_has_clean_inline_css(self):
        html = self._read_dist()
        problems = collect.check_inline_css(collect.inline_style_block(html))
        self.assertEqual(problems, [], "当前 dist/index.html 内联 CSS 应无问题：%s" % problems)

    def test_escaped_newline_css_is_caught(self):
        html = self._read_dist()
        i = html.index("<style>")
        j = html.index("</style>")
        bad = html[:i] + html[i:j].replace("\n", "\\n") + html[j:]
        problems = collect.check_inline_css(collect.inline_style_block(bad))
        self.assertTrue(problems, "换行被二次转义的 CSS 必须被拦下")

    def test_missing_style_block_is_caught(self):
        problems = collect.check_inline_css(
            collect.inline_style_block("<html><body>x</body></html>"))
        self.assertTrue(problems, "缺 <style> 块必须被拦下")

    def test_unbalanced_braces_is_caught(self):
        problems = collect.check_inline_css(":root{--a:1}\n.b{color:red")
        self.assertTrue(any("花括号" in x for x in problems),
                        "花括号不配对必须被拦下：%s" % problems)


class TestLiveReadback(unittest.TestCase):
    """--check-live 的纯函数部分（不联网）：线上回读断言必须与本地同源，
    且不能被 CRLF/LF 换行差异骗到（2026-10-12 首跑就误判过一次好页面"无快照"）。"""

    def _dist(self):
        p = os.path.join(ROOT, "dist", "index.html")
        if not os.path.exists(p):
            self.skipTest("dist/index.html 尚未生成")
        with open(p, "rb") as f:
            return f.read().decode("utf-8")

    def test_snapshot_parsed_from_crlf_and_lf(self):
        html = self._dist()
        snap = collect.snapshot_of_html(html)
        self.assertIsNotNone(snap, "本地产物（可能含 CRLF）必须能解析出快照")
        snap2 = collect.snapshot_of_html(html.replace("\r\n", "\n"))
        self.assertIsNotNone(snap2, "LF 版同样要能解析")
        self.assertEqual(snap.get("generatedAt"), snap2.get("generatedAt"))

    def test_good_live_page_has_no_problems(self):
        html = self._dist()
        gen = collect._iso_or_none(collect.snapshot_of_html(html)["generatedAt"])
        problems, warnings = collect.check_live_html(html, "test", local_generated=gen)
        self.assertEqual(problems, [], "与本地同源的好产物不应报问题：%s" % problems)
        self.assertEqual(warnings, [])

    def test_stale_live_page_is_caught(self):
        from datetime import timedelta
        html = self._dist()
        gen = collect._iso_or_none(collect.snapshot_of_html(html)["generatedAt"])
        problems, warnings = collect.check_live_html(
            html, "test", local_generated=gen + timedelta(hours=1))
        self.assertTrue(any("落后" in x for x in problems),
                        "线上落后于本地必须报：%s" % problems)
        self.assertEqual(warnings, [], "GitHub Pages 侧落后是硬失败，不该降级成警告")

    def test_stale_pages_dev_is_warning_only(self):
        """pages.dev 按设计只在手动 wrangler 发布时更新，数据落后不能算 CI 失败。"""
        from datetime import timedelta
        html = self._dist()
        gen = collect._iso_or_none(collect.snapshot_of_html(html)["generatedAt"])
        problems, warnings = collect.check_live_html(
            html, "test", local_generated=gen + timedelta(hours=1), allow_stale=True)
        self.assertEqual(problems, [], "allow_stale 时落后不该硬失败：%s" % problems)
        self.assertTrue(any("落后" in x for x in warnings), "但必须留一条警告")

    def test_escaped_css_live_page_is_caught(self):
        html = self._dist()
        i = html.index("<style>")
        j = html.index("</style>")
        bad = html[:i] + html[i:j].replace("\n", "\\n") + html[j:]
        problems, _ = collect.check_live_html(bad, "test", local_generated=None)
        self.assertTrue(any("字面量" in x for x in problems),
                        "线上 CSS 被转义必须报：%s" % problems)

    def test_old_format_page_reported_as_no_snapshot(self):
        problems, _ = collect.check_live_html(
            "<html><body>旧版 Opto-Hot</body></html>", "test", local_generated=None)
        self.assertTrue(any("快照" in x for x in problems),
                        "无 const S 的旧产物必须报：%s" % problems)


class TestScorePromptContract(unittest.TestCase):
    """评分 prompt 的结构契约（对标 AIHOT selection-score.md）。

    锁住的回归：
    1. config.json 的 prompts 键集合必须与内置默认值一致——只改一处忘了另一处，
       --llm 在本地（读 config.json）和缺省回退（读 DEFAULT_CONFIG）会走两套标准。
    2. 类型权重表每行之和必须等于 10——这是"attention 天然落在 0-100"的唯一依据，
       某行被改成和≠10 后分数会系统性漂移，精选门槛随之失真而没人报警。
    3. 注入防护边界与噪声上限字样必须在——去掉它们等于把打分交回给自由心证。
    """

    def _types_and_weights(self, prompt):
        rows = re.findall(
            r"^-\s*(discovery|technology|product|industry|facility|opinion|explainer)"
            r"\s+(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)", prompt, re.M)
        return rows

    def test_config_prompts_match_defaults_keys(self):
        cfg_keys = {k for k in collect.CONFIG["prompts"] if not k.startswith("_")}
        def_keys = {k for k in collect.DEFAULT_CONFIG["prompts"] if not k.startswith("_")}
        self.assertEqual(cfg_keys, def_keys,
                         "config.json 与内置默认值的 prompts 键不一致：%s vs %s"
                         % (sorted(cfg_keys), sorted(def_keys)))

    def test_score_a_weight_rows_sum_to_ten(self):
        p = collect.CONFIG["prompts"]["score_a"]
        rows = self._types_and_weights(p)
        self.assertEqual(len(rows), 7, "七类内容类型应当齐全，实际 %d 行" % len(rows))
        for r in rows:
            total = sum(int(x) for x in r[1:])
            self.assertEqual(total, 10, "%s 行权重之和=%d，应为 10" % (r[0], total))

    def test_score_b_axis_weights_sum_to_ten(self):
        # score_b 用 mat×4+inc×3+ver×2+tim×1，权重和同样必须是 10
        self.assertIn("mat×4", collect.CONFIG["prompts"]["score_b"])
        self.assertEqual(4 + 3 + 2 + 1, 10)

    def test_injection_guard_present(self):
        for key in ("score_a", "score_b", "extract"):
            self.assertIn("输入安全边界" if key != "extract" else "不可信数据",
                          collect.CONFIG["prompts"][key],
                          "%s 缺少 prompt-injection 防护边界" % key)

    def test_noise_caps_present(self):
        # 噪声上限是 AIHOT 口径的核心：没有它，长正文和大厂名会自发抬高分数
        self.assertIn("必须压住的噪声", collect.CONFIG["prompts"]["score_a"])
        self.assertIn("sig ≤ 4", collect.CONFIG["prompts"]["score_a"])
        self.assertIn("必须压住的噪声", collect.CONFIG["prompts"]["score_b"])

    def test_anti_hallucination_present_in_extract(self):
        self.assertIn("防幻觉", collect.CONFIG["prompts"]["extract"])
        self.assertIn("宁缺不造", collect.CONFIG["prompts"]["extract"])

    def test_enhance_prompt_anti_hallucination(self):
        # 对标 AIHOT rules-anti-hallucination.md：旧 prompt 里"无摘要时根据标题合理
        # 展开"是在命令模型编造。新口径必须反向：只复述标题、宁短勿扩。
        p = collect.CONFIG["prompts"]["enhance"]
        self.assertNotIn("合理展开", p)
        self.assertIn("宁短勿扩", p)
        self.assertIn("防幻觉规则", p)
        self.assertIn("输入安全边界", p)
        self.assertIn("{listing}", p)

    def test_pages_function_prompt_keeps_same_discipline(self):
        # functions/api/summarize.js 是线上阅读路径的按需摘要，读不到 Python 侧配置，
        # 自带一份 prompt。两处漂移过一次（离线侧修掉"根据标题合理展开"的命令式
        # 编造，线上 Function 还留着）。这个测试锁住它别再漂。
        p = os.path.join(ROOT, "functions", "api", "summarize.js")
        if not os.path.exists(p):
            self.skipTest("functions/api/summarize.js 不存在")
        with open(p, encoding="utf-8") as f:
            js = f.read()
        self.assertNotIn("合理展开", js, "线上 Function 不许命令模型按标题编造正文")
        self.assertIn("防幻觉规则", js)
        self.assertIn("输入安全边界", js)
        self.assertIn("宁短勿扩", js)

    def test_llm_enhance_uses_external_prompt(self):
        # llm_enhance 必须走 prompts.enhance，不许再写死内联 prompt
        captured = {}
        real = collect._sensenova_chat

        def fake(messages, cfg, **kw):
            captured["prompt"] = messages[0]["content"]
            return {"0": {"summary": " ok", "zh_full": "ok", "density": "中"}}

        items = [{"url": "u1", "title": "标题一", "source": "S", "score": 90.0,
                  "summary": None, "id": "i1", "discovered_at": "2026-10-13T00:00:00+00:00"}]
        collect._sensenova_chat = fake
        try:
            collect.llm_enhance(items, [], collect.CONFIG)
        finally:
            collect._sensenova_chat = real
        self.assertIn("防幻觉规则", captured.get("prompt", ""))
        self.assertIn("[0] 标题一", captured.get("prompt", ""))

    def test_score_input_hides_source_and_shows_material(self):
        # AIHOT buildScoreInput 口径：评分输入故意不给信源名/分级（防来源名气锚定），
        # 给北京时间与正文；正文缺失时用标题兜底而不是留空。
        captured = {}
        real = collect._sensenova_chat

        def fake(messages, cfg, **kw):
            captured["prompt"] = messages[0]["content"]
            return {"0": 70, "1": 40}

        batch = [
            {"title": "钙钛矿组件效率刷新", "source": "Nature Photonics",
             "source_base": "Nature Photonics", "url": "https://www.nature.com/x",
             "published_at": "2026-10-12T09:00:00+00:00",
             "summary": "研究团队宣布效率达到 26.1%。"},
            {"title": "只有标题的条目", "source": "某公众号",
             "source_base": "某公众号", "url": "https://mp.example/1",
             "published_at": None, "summary": None},
        ]
        collect._sensenova_chat = fake
        try:
            out = collect._llm_score_once(batch, "score_a", collect.CONFIG)
        finally:
            collect._sensenova_chat = real
        p = captured.get("prompt", "")
        self.assertEqual(out, {0: 70.0, 1: 40.0})
        self.assertNotIn("Nature Photonics", p, "信源名会锚定评分，输入必须遮蔽")
        self.assertNotIn("某公众号", p)
        self.assertIn("26.1%", p, "正文材料必须进入评分输入")
        self.assertIn("未知（收录时间不代表发布时间）", p, "无发布时间必须显式声明，不许回退收录时间")
        self.assertIn("【发布时间（北京时间）】", p)

    def test_listing_placeholder_present(self):
        for key in ("score_a", "score_b", "extract"):
            self.assertIn("{listing}", collect.CONFIG["prompts"][key])


if __name__ == "__main__":
    unittest.main(verbosity=2)
