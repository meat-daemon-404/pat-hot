# -*- coding: utf-8 -*-
"""文献编号（DOI / arXiv）抽取契约测试。

单独成文件：锁的是"事件→论文锚点"这一件事，与 test_collect.py 的采集/输出契约、
test_tier_carryover.py 的 tier 沿用互不相干。纯标准库、无网络。

钉住的回归（按危险程度排）：

1. **不造假边界**：Nature 单页实测带 43~246 个 doi.org 链接，全部是正文参考文献列表，
   属于**别的论文**。抽取通路只读 <head> 的"本篇自述元数据"，一旦有人为了提覆盖率
   改成"扫正文链接"，锚点就会把别人的论文安到本事件头上——这是本文件存在的头号理由，
   所以下面用一份「头部无自述元数据、正文塞满 DOI」的 fixture 把它钉成红。
2. **doi: 前缀**：站点 citation_doi 的 content 实测写作 `doi:10.1038/…`。不在清洗层
   剥掉，形状校验判它非法，于是 Nature 整批命中静默归零，而 Nature 是唯一抽得到的
   那类源——等于整条通路做没了却不报错。
3. **百分号编码**：href 里的 10.1126%2Fscience.abb2823 不解码就发布，下游拼出来是
   打不开的地址。
4. **配额先行**：抓取失败照样打了源站，必须计入拓取上限；否则整站 500 时会被反复拓。

判据形状与 collect.py 的 check_contract 用同一组常量（DOI_SHAPE_RE / ARX_ID_RE），
所以"抽取层放行"与"发布前自检放行"不会各说一套。
"""
import io
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "collector"))

import collect  # noqa: E402


# ---------------- fixture ----------------

def nature_like_page(doi="10.1038/s41567-026-03487-x"):
    """真实形态的期刊页：头部自述 DOI（带 doi: 前缀）+ 正文一长串参考文献 DOI。"""
    refs = "".join('<a href="https://doi.org/10.1038/rev%03d">[%d]</a>' % (n, n)
                   for n in range(60))
    return (
        "<!DOCTYPE html><html><head>"
        '<meta name="citation_title" content="Chip-mediated manipulation"/>'
        '<meta name="citation_doi" content="doi:%s"/>' % doi +
        '<link rel="canonical" href="https://www.nature.com/articles/s41567-026-03487-x"/>'
        "</head><body>" + refs + "</body></html>"
    )


REFLIST_ONLY_PAGE = (
    "<!DOCTYPE html><html><head>"
    '<meta name="citation_title" content="MIT radio burst coverage"/>'
    '<meta property="og:url" content="https://news.mit.edu/2026/radio-bursts-1006"/>'
    "</head><body>"
    # 正文参考文献：形状完全合法，但不属于本篇
    '<a href="https://doi.org/10.1038/s41586-020-02110-6">1</a>'
    '<a href="https://dx.doi.org/10.1126/science.abb2823">2</a>'
    '<p>DOI: 10.6084/m9.figshare.33187908</p>'
    "</body></html>"
)

ARXIV_META_PAGE = (
    "<html><head>"
    '<meta name="citation_arxiv_id" content="2610.13867v1"/>'
    '<meta name="citation_doi" content="info:doi/10.1103/PhysRevX.14.021014"/>'
    "</head><body>x</body></html>"
)

ENCODED_CANONICAL_PAGE = (
    "<html><head>"
    '<link rel="canonical" href="https://doi.org/10.1126%2Fscience.abb2823"/>'
    "</head><body></body></html>"
)

NO_META_PAGE = "<html><head><title>plain</title></head><body>nothing</body></html>"


class TestCleanDoi(unittest.TestCase):
    def test_strips_doi_prefix(self):
        """站点自述元数据带 doi: 前缀是常态，不是脏数据。"""
        self.assertEqual(collect._clean_doi("doi:10.1038/s41567-026-03487-x"),
                         "10.1038/s41567-026-03487-x")
        self.assertEqual(collect._clean_doi("DOI:10.1038/a.1"), "10.1038/a.1")
        self.assertEqual(collect._clean_doi("info:doi/10.1038/a.1"), "10.1038/a.1")

    def test_decodes_percent_slash(self):
        self.assertEqual(collect._clean_doi("10.1126%2Fscience.abb2823"),
                         "10.1126/science.abb2823")

    def test_strips_site_prefix(self):
        self.assertEqual(collect._clean_doi("https://doi.org/10.1038/a.1"), "10.1038/a.1")
        self.assertEqual(collect._clean_doi("http://dx.doi.org/10.1038/a.1"), "10.1038/a.1")

    def test_trims_trailing_punctuation(self):
        self.assertEqual(collect._clean_doi("10.1038/a.1."), "10.1038/a.1")

    def test_rejects_value_with_trailing_prose(self):
        """带逗号和空格的串一律拒收：截断等于猜哪一段才是本篇 DOI。

        文本通路（DOI_IN_TEXT_RE）本就在逗号/空白处切断，所以这种串只会从
        元数据通路进来，而那类页面写两个 DOI 时属异常形态——宁缺毋假。
        """
        self.assertEqual(collect._clean_doi("10.1038/a.1, and more"), "")
        self.assertEqual(collect._clean_doi("10.1038/a.1, 10.1038/b.2"), "")

    def test_rejects_non_shapes(self):
        for bad in ("", "10.1/a", "1012345/x", "not-a-doi", "2610.13867",
                    "10.123456789012345/x"):
            self.assertEqual(collect._clean_doi(bad), "", "应拒收: %r" % bad)

    def test_arxiv_shape_and_version(self):
        self.assertEqual(collect._clean_arxiv("2610.13867v1"), "2610.13867")
        self.assertEqual(collect._clean_arxiv("2610.13867"), "2610.13867")
        for bad in ("", "hep-th/9901001", "2610.138", "261013867", "arXiv:2610.13867"):
            self.assertEqual(collect._clean_arxiv(bad), "", "应拒收: %r" % bad)


class TestHeadSlice(unittest.TestCase):
    def test_only_head(self):
        page = nature_like_page()
        head = collect.head_slice(page)
        self.assertIn("citation_doi", head)
        self.assertNotIn("10.1038/rev001", head)

    def test_no_head_tag_falls_back_to_prefix(self):
        self.assertIn("citation_doi", collect.head_slice(nature_like_page().replace("</head>", "", 1)))


class TestExtractFromHtml(unittest.TestCase):
    def test_reads_self_meta_only(self):
        r = collect.extract_refs_from_html(nature_like_page(),
                                           "https://www.nature.com/articles/s41567-026-03487-x")
        self.assertEqual(r.get("doi"), "10.1038/s41567-026-03487-x")
        self.assertEqual(r.get("via"), "self_meta")

    def test_ignores_reference_list(self):
        """🔴 不造假主判据：头部没有本篇自述 DOI 时，正文里再多合法 DOI 也不收。

        这条一旦变红，说明有人把抽取面从 <head> 扩到了正文——那会把别人的论文
        挂到本事件名下，属于对外发布假锚点，不是覆盖率提升。
        """
        r = collect.extract_refs_from_html(REFLIST_ONLY_PAGE,
                                           "https://news.mit.edu/2026/radio-bursts-1006")
        self.assertEqual(r, {}, "正文参考文献的 DOI 绝不能进 refs: %r" % r)

    def test_arxiv_meta_and_prefixed_doi(self):
        r = collect.extract_refs_from_html(ARXIV_META_PAGE)
        self.assertEqual(r.get("arxiv"), "2610.13867")
        self.assertEqual(r.get("doi"), "10.1103/PhysRevX.14.021014")

    def test_canonical_doi_org_decodes(self):
        r = collect.extract_refs_from_html(ENCODED_CANONICAL_PAGE)
        self.assertEqual(r.get("doi"), "10.1126/science.abb2823")

    def test_item_url_as_last_resort(self):
        r = collect.extract_refs_from_html(NO_META_PAGE, "https://doi.org/10.1038/from-url")
        self.assertEqual(r.get("doi"), "10.1038/from-url")

    def test_empty_is_correct(self):
        self.assertEqual(collect.extract_refs_from_html(NO_META_PAGE, "https://x/1"), {})


class TestExtractFromText(unittest.TestCase):
    def test_arxiv_in_summary(self):
        r = collect.extract_refs_from_text(
            "Two-loop power spectrum",
            "arXiv:2610.13867v1 Announce Type: new Abstract: ...",
            "https://arxiv.org/abs/2610.13867")
        self.assertEqual(r.get("arxiv"), "2610.13867")
        self.assertEqual(r.get("via"), "feed_text")

    def test_doi_needs_context(self):
        """裸 10.x/y 会撞版本号/经费号，必须带 DOI: 或 doi.org 上下文才收。"""
        self.assertEqual(collect.extract_refs_from_text("v10.2023 release", "budget 10.5000/gx", ""), {})
        r = collect.extract_refs_from_text("Paper", "DOI: 10.1038/s41566-026-02009-8", "")
        self.assertEqual(r.get("doi"), "10.1038/s41566-026-02009-8")

    def test_doi_org_url_counts(self):
        r = collect.extract_refs_from_text("T", "", "https://doi.org/10.1038/s41567-026-03487-x")
        self.assertEqual(r.get("doi"), "10.1038/s41567-026-03487-x")

    def test_article_page_url_is_not_a_doi(self):
        """nature.com/articles/s41567-… 是文章页地址，不含 10.1038/ 前缀，**不是** DOI。

        把它当 DOI 发出去，下游会拿它去 doi.org 解析出一个打不开的地址——这正是
        「不发假链接」要挡的形态。编号只在元数据里，故这里走 self_meta 通路。
        """
        url = "https://www.nature.com/articles/s41567-026-03487-x"
        self.assertEqual(collect.extract_refs_from_text("Chip-mediated", "", url), {})
        r = collect.merge_refs(collect.extract_refs_from_text("Chip-mediated", "", url),
                               collect.extract_refs_from_html(nature_like_page(), url))
        self.assertEqual(r["doi"], "10.1038/s41567-026-03487-x")
        self.assertEqual(r["via"], "self_meta")


class TestMergeRefs(unittest.TestCase):
    def test_confidence_and_key_order(self):
        r = collect.merge_refs({"doi": "10.1038/a", "via": "feed_text"},
                               {"arxiv": "2610.13867", "via": "self_meta"})
        self.assertEqual(list(r.keys()), ["doi", "arxiv", "via", "confidence"])
        self.assertEqual(r["via"], "feed_text+self_meta")
        self.assertEqual(r["confidence"], "verified")

    def test_first_wins(self):
        r = collect.merge_refs({"doi": "10.1038/a", "via": "feed_text"},
                               {"doi": "10.1038/b", "via": "self_meta"})
        self.assertEqual(r["doi"], "10.1038/a")

    def test_empty_in_empty_out(self):
        self.assertEqual(collect.merge_refs({}, {}), {})
        self.assertEqual(collect.merge_refs(None), {})


class TestSourceGate(unittest.TestCase):
    def test_journal_sources_on(self):
        for s in ("Nature Photonics", "Nature 量子物理", "arXiv quant-ph 论文速递",
                  "Light: Science & Applications"):
            self.assertTrue(collect.source_wants_refs(s), s)

    def test_industry_sources_off(self):
        """产业/新闻稿型源不进深拓：实测 0/23 命中，拓了只是白烧源站配额。"""
        for s in ("OFweek 光电频道", "OFweek 激光频道", "CERN 新闻", "MIT News 物理",
                  "Universe Today", "ESA 空间科学", "中国招标投标公共服务平台",
                  "CIOE 中国光博会", "Phys.org 物理新闻", "New Scientist 物理",
                  "Quanta Magazine", "LEDinside 英文", "C114中国通信网_要闻精选"):
            self.assertFalse(collect.source_wants_refs(s), s)

    def test_explicit_flag_overrides_hint(self):
        self.assertTrue(collect.source_wants_refs("某新期刊", True))
        self.assertFalse(collect.source_wants_refs("Nature Photonics", False))
        # 缺省（未声明）时按 hint 判：既不能全开也不能全关
        self.assertFalse(collect.source_wants_refs("随便什么源", None))


class TestCollectRefs(unittest.TestCase):
    def _items(self):
        return [
            {"id": "a", "title": "Chip-mediated manipulation", "source": "Nature 量子物理",
             "url": "https://www.nature.com/articles/s41567-026-03487-x",
             "summary": "", "score": 90.0},
            {"id": "b", "title": "MIT radio bursts", "source": "MIT News 物理",
             "url": "https://news.mit.edu/2026/radio-bursts-1006",
             "summary": "", "score": 80.0},
            {"id": "c", "title": "Already in summary", "source": "arXiv quant-ph 论文速递",
             "url": "https://arxiv.org/abs/2610.13867",
             "summary": "arXiv:2610.13867v1 Abstract: ...", "score": 70.0},
        ]

    def test_feed_path_needs_no_request(self):
        calls = []
        items = self._items()
        res = collect.collect_refs(items, {"refs": {"max_fetch": 24, "per_source": 10,
                                                    "interval_sec": 0}},
                                   "tech", {"MIT News 物理": False},
                                   fetcher=lambda u: calls.append(u) or nature_like_page(),
                                   sleeper=lambda s: None)
        self.assertEqual(items[2]["refs"]["arxiv"], "2610.13867")
        self.assertEqual(res["feed_hits"], 1)
        self.assertNotIn(items[2]["url"], calls, "自带编号的条目不该再拓一次")

    def test_journal_deep_fetch(self):
        items = self._items()
        res = collect.collect_refs(items, {"refs": {"max_fetch": 24, "per_source": 10,
                                                    "interval_sec": 0}},
                                   "tech", {}, fetcher=lambda u: nature_like_page(),
                                   sleeper=lambda s: None)
        self.assertEqual(items[0]["refs"]["doi"], "10.1038/s41567-026-03487-x")
        self.assertNotIn("refs", items[1], "新闻稿源不该被拓，也不该有锚点")
        self.assertEqual(res["fetched"], 1, "只有期刊型源该被拓")

    def test_per_source_cap_and_failure_counts_quota(self):
        """🔴 配额先记：整站失败时也必须停止继续敲门，否则源站 500 会被集中轰击。"""
        seen = []

        def boom(url):
            seen.append(url)
            raise RuntimeError("500")
        items = [{"id": "n%d" % i, "title": "T%d" % i, "source": "Nature Photonics",
                  "url": "https://nature.com/a%d" % i, "summary": "", "score": 90.0 - i}
                 for i in range(20)]
        res = collect.collect_refs(items, {"refs": {"max_fetch": 6, "per_source": 3,
                                                    "interval_sec": 0}},
                                   "tech", {}, fetcher=boom, sleeper=lambda s: None)
        self.assertEqual(len(seen), 3, "单源上限 3 就该停，失败也占额: %d" % len(seen))
        self.assertEqual(res["failed"], 3)
        self.assertEqual(res["fetched"], 0)

    def test_channel_cap(self):
        seen = []
        items = []
        for i in range(40):
            items.append({"id": "x%d" % i, "title": "T%d" % i,
                          "source": "Nature Photonics %d" % i,
                          "url": "https://nature.com/a%d" % i, "summary": "",
                          "score": 90.0 - i * 0.1})
        collect.collect_refs(items, {"refs": {"max_fetch": 5, "per_source": 10,
                                              "interval_sec": 0}},
                             "tech", {},
                             fetcher=lambda u: seen.append(u) or NO_META_PAGE,
                             sleeper=lambda s: None)
        self.assertEqual(len(seen), 5)

    def test_non_http_url_skipped(self):
        items = [{"id": "z", "title": "T", "source": "Nature Photonics",
                  "url": "mailto:x@y", "summary": "", "score": 1.0}]
        res = collect.collect_refs(items, {"refs": {"max_fetch": 5, "per_source": 5,
                                                    "interval_sec": 0}},
                                   "tech", {}, fetcher=lambda u: (_ for _ in ()).throw(AssertionError("不该拓")),
                                   sleeper=lambda s: None)
        self.assertEqual(res["fetched"], 0)


class TestPapersIndex(unittest.TestCase):
    def test_only_anchored_items(self):
        from datetime import datetime, timezone
        items = [
            {"id": "a", "title": "A", "source": "Nature", "url": "u1",
             "refs": {"doi": "10.1038/a", "via": "self_meta", "confidence": "verified"},
             "selected": True, "published_at": "2026-10-12T00:00:00+00:00",
             "category": "科研进展"},
            {"id": "b", "title": "B", "source": "OFweek", "url": "u2",
             "selected": True, "published_at": "2026-10-11T00:00:00+00:00",
             "category": "产业与资本"},
        ]
        doc = collect.build_papers_index(items, datetime(2026, 10, 13, tzinfo=timezone.utc), "tech")
        self.assertEqual(doc["count"], 1, "无锚点条目不该出现在反查表里")
        self.assertEqual(doc["items"][0]["id"], "a")
        self.assertEqual(doc["items"][0]["doi"], "10.1038/a")
        self.assertNotIn("summary", doc["items"][0], "这张表不该二次发布正文")
        self.assertEqual(doc["channel"], "tech")

    def test_empty_channel_still_valid_doc(self):
        from datetime import datetime, timezone
        doc = collect.build_papers_index([], datetime(2026, 10, 13, tzinfo=timezone.utc), "physics")
        self.assertEqual(doc["count"], 0)
        self.assertEqual(doc["items"], [])


class TestContractGlue(unittest.TestCase):
    """papers-index 必须同时被「期望地址」「索引」「OpenAPI」认到，否则线上就是死链。"""

    def test_expected_endpoints_include_papers_index(self):
        for ch in collect.CHANNEL_ORDER:
            self.assertIn("api/v1/%s/papers-index.json" % ch,
                          collect.expected_channel_endpoints(ch))

    def test_flat_alias_not_required(self):
        """新增地址不进扁平兼容层：老消费者从没见过它，镜像只会多一个没人维护的口径。"""
        self.assertNotIn("api/v1/papers-index.json", collect.expected_flat_endpoints())

    def test_refs_config_defaults_exist(self):
        d = collect.DEFAULT_CONFIG
        self.assertIn("refs", d)
        for k in ("max_fetch", "per_source", "interval_sec", "page_max_bytes"):
            self.assertIn(k, d["refs"])

    def test_http_get_accepts_max_bytes_override(self):
        import inspect
        sig = inspect.signature(collect.http_get)
        self.assertIn("max_bytes", sig.parameters)
        self.assertIsNone(sig.parameters["max_bytes"].default, "缺省必须走原 12MB 口径")

    def test_sources_declares_journal_flag(self):
        """sources.json 里期刊型源要显式声明 refs_fetch，让口径可读、可改而不必改代码。"""
        import json
        with io.open(os.path.join(ROOT, "collector", "sources.json"), encoding="utf-8") as f:
            srcs = json.load(f)
        flagged = [c["name"] for s in ("rss", "html") for c in srcs.get(s, [])
                   if c.get("refs_fetch")]
        self.assertTrue(flagged, "没有任何源声明 refs_fetch")
        for n in ("Nature Photonics", "Nature 量子物理", "Nature Physics 学科聚合",
                  "Nature 天文和天体物理"):
            if any(n in x for x in [c["name"] for s in ("rss", "html") for c in srcs.get(s, [])]):
                self.assertIn(n, flagged, "%s 是期刊型源却没标 refs_fetch" % n)
        for bad in ("OFweek 光电频道", "CERN 新闻", "MIT News 物理", "Universe Today"):
            self.assertNotIn(bad, flagged, "%s 实测 0 命中，不该声明要拓" % bad)


if __name__ == "__main__":
    unittest.main()
