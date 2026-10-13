# -*- coding: utf-8 -*-
"""分类 RSS 完整性契约测试（纯标准库，无网络）。

起因（2026-10-13 实测线上）：write_outputs 过去只给"本次恰好有条目的分类"
写 feed，而 Agent 接入页把 channels.json 里声明的每个分类都列成订阅地址。
两边一错位，physics 的 biophys/statphys、astro 的 exoplanet 三个地址就是死链；
更糟的是 Cloudflare Pages 对缺失路径返回 200 + 单页 HTML（不是 404），
RSS 阅读器拿到一份 HTML 还以为订阅成功了。

同一次审计还发现第二类错位：分类清空后旧文件留在原地，feed 内容与同批发布的
items.json 自相矛盾——HEAD 的 astro/gw.xml 里 5 条全部不在 HEAD 的
data/astro/items.json 里，等于在宣传一份与数据无关的榜单。
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "collector"))

import collect  # noqa: E402


def _channels():
    with io.open(os.path.join(ROOT, "collector", "channels.json"), encoding="utf-8") as f:
        return json.load(f)


def _text(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def _json(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


class TestFeedCompleteness(unittest.TestCase):
    def test_every_declared_category_has_a_feed_file(self):
        """channels.json 声明的分类必须逐个有对应 feed（Agent 页照此列表宣传）。"""
        chs = _channels()
        for ch_id in chs["order"]:
            for cat, slug in chs["channels"][ch_id]["category_slug"].items():
                p = os.path.join(ROOT, "dist", "feed", ch_id, "category", slug + ".xml")
                self.assertTrue(os.path.exists(p),
                                "缺 %s（分类「%s」被 Agent 页列为订阅地址）" % (
                                    os.path.relpath(p, ROOT).replace("\\", "/"), cat))

    def test_every_published_feed_is_parseable_xml(self):
        for ch_id in _channels()["order"]:
            d = os.path.join(ROOT, "dist", "feed", ch_id, "category")
            if not os.path.isdir(d):
                continue
            for fn in sorted(os.listdir(d)):
                p = os.path.join(d, fn)
                raw = _text(p)
                self.assertTrue(raw.lstrip().startswith("<?xml"),
                                "%s/%s 开头不是 XML 声明" % (ch_id, fn))
                try:
                    root = ET.fromstring(raw)
                except ET.ParseError as e:
                    self.fail("%s/%s 不是合法 XML：%s（半截写入会让阅读器拿到坏文档）"
                              % (ch_id, fn, e))
                self.assertIsNotNone(root.find("channel"), "%s/%s 无 channel" % (ch_id, fn))

    def test_feed_items_match_published_data(self):
        """feed 里的条目必须真在同类别的 items.json 里，且条数一致（上限 30）。"""
        chs = _channels()
        for ch_id in chs["order"]:
            ip = os.path.join(ROOT, "data", ch_id, "items.json")
            if not os.path.exists(ip):
                self.skipTest("尚无 %s 产物" % ch_id)
            with io.open(ip, encoding="utf-8") as f:
                items = (json.load(f) or {}).get("items", [])
            by_cat = {}
            for it in items:
                by_cat.setdefault(it["category"], []).append(it)
            urls = {i["url"] for i in items}
            for cat, slug in chs["channels"][ch_id]["category_slug"].items():
                p = os.path.join(ROOT, "dist", "feed", ch_id, "category", slug + ".xml")
                if not os.path.exists(p):
                    continue
                raw = _text(p)
                # 第一个 <link> 是 channel 的站点地址，条目 link 从第二个起
                links = re.findall(r"<link>(https?://[^<]+)</link>", raw)[1:]
                for u in links:
                    self.assertIn(u.replace("&amp;", "&"), urls,
                                  "%s/%s.xml 里的 %r 不在 data/%s/items.json（陈旧残留）"
                                  % (ch_id, slug, u[:70], ch_id))
                expect = min(len(by_cat.get(cat, [])), 30)
                self.assertEqual(len(links), expect,
                                 "%s/%s.xml 条目数 %d != 数据里的 %d"
                                 % (ch_id, slug, len(links), expect))

    def test_flat_legacy_feeds_cover_alias_channel(self):
        chs = _channels()
        for cat, slug in chs["channels"][collect.FLAT_ALIAS_CHANNEL]["category_slug"].items():
            p = os.path.join(ROOT, "dist", "feed", "category", slug + ".xml")
            self.assertTrue(os.path.exists(p),
                            "缺扁平订阅地址 feed/category/%s.xml（分类「%s」，重构前就有读者）"
                            % (slug, cat))


class TestEmptyFeedIsReproducible(unittest.TestCase):
    """零条目分类的 lastBuildDate 必须取本次生成时刻，不能是 now_utc()。

    否则每个 CI 周期都会把这 3 个空文件重新写一遍不同字节，产物不可复现，
    git 里天天长出无意义 diff。
    """

    def test_build_rss_uses_fallback_not_now(self):
        dt = datetime(2026, 10, 12, 14, 8, 22, tzinfo=timezone.utc)
        a = collect.build_rss([], "T", "https://x/#/all", "d", 30, fallback_dt=dt)
        b = collect.build_rss([], "T", "https://x/#/all", "d", 30, fallback_dt=dt)
        self.assertEqual(a, b, "同一时刻两次渲染不一致")
        self.assertIn("Mon, 12 Oct 2026 14:08:22", a)
        self.assertNotIn("<item>", a, "空分类不该产出 item")

    def test_build_rss_without_fallback_still_valid(self):
        a = collect.build_rss([], "T", "https://x/#/all", "d", 30)
        ET.fromstring(a)  # 不抛异常即可
        self.assertTrue(a.lstrip().startswith("<?xml"))


class TestCheckContractCatchesMissingFeed(unittest.TestCase):
    """新加的这道关必须真会响：删掉一个 feed 就该报出来。"""

    def test_deleting_an_advertised_feed_is_caught(self):
        tmp = tempfile.mkdtemp(prefix="pathom-feedgate-")
        real = collect.DIST_DIR
        try:
            collect.DIST_DIR = tmp
            # 只造出"其它都在、缺一个"的最小局面：直接调用断言段落代价太高，
            # 这里改为验证函数对空目录确实会报缺 feed。
            problems = collect.check_contract(verbose=False)
            missing = [p for p in problems if p.startswith("缺失 feed/")]
            self.assertTrue(missing,
                            "空 dist 下 check_contract 应报出缺失的分类 feed，实际：%r"
                            % problems[:3])
            declared = set()
            for c in _channels()["order"]:
                declared |= set(_channels()["channels"][c]["category_slug"].values())
            # 消息形如「缺失 feed/astro/category/gw.xml（…）」，全角括号紧跟文件名，
            # 按空格切会切错，直接用正则取路径。
            reported = set()
            for p in missing:
                m = re.search(r"缺失 (feed/\S+?\.xml)", p)
                if m:
                    reported.add(m.group(1).rsplit("/", 1)[-1][:-4])
            self.assertTrue(declared & reported,
                            "报出的 feed 应与声明分类有交集：%r vs %r"
                            % (sorted(reported)[:6], sorted(declared)[:6]))
        finally:
            collect.DIST_DIR = real
            shutil.rmtree(tmp, ignore_errors=True)

    def test_html_masquerading_as_feed_is_caught(self):
        """Pages 的 200+SPA 回退形态：文件在、但不是 XML，必须单独报出来。"""
        tmp = tempfile.mkdtemp(prefix="pathom-feedhtml-")
        real = collect.DIST_DIR
        try:
            # 必须先把 DIST_DIR 指到沙箱：否则 check_contract 查的是真 dist，
            # 那份是好的，测试就会"绿着什么也没测"。
            collect.DIST_DIR = tmp
            d = os.path.join(tmp, "feed", "astro", "category")
            os.makedirs(d)
            with io.open(os.path.join(d, "gw.xml"), "w", encoding="utf-8") as f:
                f.write("<!DOCTYPE html><html><body>PAT-HOT</body></html>")
            problems = collect.check_contract(verbose=False)
            hits = [p for p in problems if "gw.xml" in p and "XML" in p]
            self.assertTrue(hits, "HTML 冒充 feed 未被发现：%r" % problems[:3])
        finally:
            collect.DIST_DIR = real
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
