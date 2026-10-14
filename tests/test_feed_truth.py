# -*- coding: utf-8 -*-
"""2026-10-13 精选页体检后的修复契约（纯标准库 + 可选 numpy，无网络）。

锁住的回归（全部有实测证据，见 scratch/probe_*.py 与录屏 QQ20261013-202542.mp4）：

1. 精选页不过滤 selected：「精选」页内容等于全部动态，没过门槛的诺奖稿
   （62.8 分 < 媒体门槛 65）顶着「20 条精选」出现。
2. 组头计数说谎：slice(0,20) 之后用 its.length 当精选数，34 条精选显示 20、
   0 条精选也显示 20。
3. 日组内联折叠：录屏实测点组头折叠让下方内容单帧跳 +31px / +164px。
   用户要求改成独立日历界面、点击跳转（#/cal）。
4. 时区：effDate/pubLabel 直接切 UTC 串，27/86 条归错天、页面上永远没有「今天」。
5. 聚类巨簇：OPTOHOT_EMBED=1 的嵌入近重复合并用单链并查集（sim>=0.70 传递闭包），
   把三频道各 22/56/69 条连成单簇。修复为平均链接凝聚 + 规模上限。
6. 热度公式：signal_count=len(its) 是全历史条数，48h 窗口没作用到 0.35 项；
   单源连发 6 篇能排热点榜第 2。修复为只数窗口内、且每源限贡献。
7. 热点榜文不对题：t["title"] 取 max(score)、链接取 pick_representative 另选的那条。
   修复为标题与代表报道同源。
8. 趋势页半截周：自然周在周二拿 2 天对 7 天。修复为滚动 window_days 窗口。
"""
import io
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TPL = os.path.join(ROOT, "collector", "templates")
sys.path.insert(0, os.path.join(ROOT, "collector"))

import collect  # noqa: E402


def _read(name):
    with io.open(os.path.join(TPL, name), encoding="utf-8") as f:
        return f.read()


JS = _read("app.js")
HTML = _read("app.html")


class TestFeedShowsOnlySelected(unittest.TestCase):
    def _feed_body(self):
        i = JS.index("function renderFeed()")
        j = JS.index("\n// ---- 日历页", i)
        return JS[i:j]

    def test_feed_filters_selected(self):
        body = self._feed_body()
        self.assertIn("C.items.filter(i=>i.selected)", body,
                      "精选页又不过滤 selected 了：内容会等于全部动态，"
                      "没过门槛的条目顶着「精选」标题出现（2026-10-13 实测）")

    def test_group_count_is_true_selected_count(self):
        """计数必须在截断之前取：旧实现 slice(0,20) 后写 its.length。"""
        body = self._feed_body()
        self.assertNotIn(".slice(0,20)", body,
                         "精选页又按 20 条截断了：超出部分被隐藏，计数也跟着说谎")
        self.assertIn("its.length+' '+T.daySel", body,
                      "组头计数不再取该天真实精选条数")

    def test_no_inline_day_collapse(self):
        """日组内联折叠已移除：录屏实测点组头折叠下方内容单帧跳 +31/+164px。"""
        self.assertNotIn("data-dayh", JS,
                         "日组折叠交互回来了：它会整块顶走下方内容（录屏已量化），"
                         "日期导航应走独立日历页 #/cal")
        self.assertNotIn("state.collapsed", JS,
                         "state.collapsed 残留：折叠状态已无消费者")


class TestCalendarView(unittest.TestCase):
    def test_calendar_route_registered(self):
        self.assertIn('"/cal":"cal"', JS, "路由表没有 /cal")
        self.assertIn('id="view-cal"', HTML, "app.html 缺 view-cal section")
        self.assertIn("renderers.cal=renderCal", JS, "日历视图没注册 renderer")
        self.assertIn('href="#/cal"', HTML, "导航里没有日历入口")

    def test_calendar_day_jumps_to_feed(self):
        i = JS.index("function bind()")
        body = JS[i:]
        self.assertIn("data-calday", body,
                      "日历格子没有 data-calday：点日期无法跳回精选页")
        self.assertIn('location.hash="#/"', body,
                      "点日历日期不跳回精选页，跳转承诺落空")
        # 落点必须交给 renderFeed 排帧，不能在点击里直接滚：
        # hashchange→router 是异步的，旧实现 requestAnimationFrame 里
        # $("#day-"+feedDay).scrollIntoView 会被 router 的 scrollTo(0,0)
        # 顶掉（320px 实测 y 停在 0，跳转承诺落空）。
        self.assertIn("state.calJumpDay=cd.dataset.calday", body,
                      "日历跳转没有把落点延后到渲染完成，会被 router 归零")
        fi = JS.index("function renderFeed(")
        fb = JS[fi:JS.index("function calDays(", fi)]
        self.assertIn("state.calJumpDay", fb,
                      "renderFeed 不再消费 calJumpDay：跳回精选页后不滚到对应分组")
        # 变异实测：把守卫改成 if(false&&state.calJumpDay) 字符串全在、
        # 落点永不执行——必须断言守卫本身，而不是只断言变量名出现过。
        self.assertRegex(fb.replace(" ", ""), r"if\(state\.calJumpDay\)\{",
                         "calJumpDay 守卫被条件短路（if(false&&…)）：跳转落点静默失效")
        self.assertIn('getElementById("day-"+day)', fb,
                      "renderFeed 没有按日期取分组元素")
        self.assertIn("scrollTo(", fb, "renderFeed 排好帧却没有真正滚动")

    def test_retap_guard_keeps_caljump(self):
        """日历格 href="#/" 与精选 tab 同址：retap 监听必须让路。

        旧实现里点日历某天后，"再点当前 tab"会在同一次 dispatch 里多调一次
        router，随后 hashchange 判成 retap 再归零，落点被顶回 0
        （trace：scrollTo(507) 之后紧跟 scrollTo(0,0)）。加了
        e.defaultPrevented 让路闸后，320/390 各 3 次实测 y 稳定 507。
        """
        i = JS.index('const a=e.target.closest(\'a[href^="#/"')
        guard = JS[i - 260:i + 260]
        self.assertIn("defaultPrevented", guard,
                      "retap 监听没让路：日历跳转的落点会被随后的 router 顶回 0")


class TestBeijingTimeDisplay(unittest.TestCase):
    def test_effdate_uses_beijing_day(self):
        self.assertIn("function cnDayOf(", JS,
                      "cnDayOf 没了：published_at 的 UTC 日会被当北京日用")
        i = JS.index("function effDate(")
        j = JS.index("\n", i)
        self.assertIn("cnDayOf(p)", JS[i:j],
                      "effDate 又直接切 UTC 前 10 位：27/86 条会归错天，"
                      "页面上也永远出不来「今天」这一组")

    def test_publabel_uses_beijing_time(self):
        i = JS.index("function pubLabel(")
        j = JS.index("function catName(", i)
        self.assertIn("8*3600*1000", JS[i:j],
                      "pubLabel 没有把时刻换算到北京时间：卡片会比真实晚 8 小时")

    def test_freshnote_latest_uses_beijing(self):
        i = JS.index("function freshNote(")
        j = JS.index("function hotPage(", i)
        seg = JS[i:j]
        self.assertIn("new Date(latest)", seg,
                      "freshNote 的最新文章时间仍按 UTC 原串切片，"
                      "会和「数据 今天 更新」自相矛盾")


class TestAverageLinkage(unittest.TestCase):
    """平均链接必须挡住单链传染：A~B、B~C 相似但 A~C 不相似时不许并成一簇。"""

    def test_chain_does_not_merge_dissimilar_ends(self):
        sim = [[1.0, 0.5, 0.05],
               [0.5, 1.0, 0.5],
               [0.05, 0.5, 1.0]]
        g = collect.average_linkage(sim, 0.3)
        # A~B=0.5 先并；并后 ({A,B},C) 的平均相似 = (0.05+0.5)/2 = 0.275 <= 0.3，
        # 所以 C 必须留在外面——单链实现会把 C 也拖进来。
        self.assertEqual(g[0], g[1])
        self.assertNotEqual(g[0], g[2],
                            "平均链接仍把 A、C 并成一簇（A~C 只有 0.05）：链式传染没修掉")

    def test_size_cap_blocks_oversized_merge(self):
        sim = [[1.0, 0.9, 0.9],
               [0.9, 1.0, 0.9],
               [0.9, 0.9, 1.0]]
        g = collect.average_linkage(sim, 0.5, size_cap=2)
        self.assertEqual(len(set(g)), 2,
                         "size_cap 没生效：三个两两 0.9 的条目应被拆成 2 簇")

    def test_initial_groups_are_respected(self):
        sim = [[1.0, 0.1, 0.9],
               [0.1, 1.0, 0.1],
               [0.9, 0.1, 1.0]]
        g = collect.average_linkage(sim, 0.5, initial=[7, 8, 7])
        self.assertEqual(g[0], g[2])
        self.assertNotEqual(g[0], g[1])

    def test_config_thresholds_are_wired(self):
        cc = collect.CONFIG.get("clustering") or {}
        self.assertIn("embed_threshold", cc,
                      "嵌入合并阈值没进配置：0.70 硬编码是巨簇根因，必须可调")
        self.assertGreaterEqual(cc["embed_threshold"], 0.72,
                                "embed_threshold 低于实测安全值 0.72")
        self.assertIn("max_cluster_size", cc, "缺簇规模上限兜底")


class TestHeatUsesRecentWindow(unittest.TestCase):
    def _topic(self, ages_days):
        now = datetime.now(timezone.utc)
        items = []
        for k, age in enumerate(ages_days):
            pub = (now - timedelta(days=age)).isoformat()
            items.append({"id": "i%d" % k, "title": "t%d" % k, "url": "u%d" % k,
                          "source": "s%d" % (k % 2), "source_base": "s%d" % (k % 2),
                          "published_at": pub, "discovered_at": pub,
                          "score": 70.0, "summary": "x", "keywords": []})
        t = {"ids": {i["id"] for i in items}, "terms": set()}
        collect.finalize_topic(t, items, {}, collect.CONFIG)
        return t, items

    def test_signal_count_only_counts_recent_window(self):
        # 6 条里 4 条是 30 天前的旧文：48h 窗口内只有 2 条
        t, _ = self._topic([0.1, 0.2, 30, 31, 32, 33])
        self.assertLessEqual(t["signal_count"], 2,
                             "signal_count 又数全历史了：旧事件攒够条数就能拿满热度")

    def test_single_source_cannot_saturate_signal_term(self):
        # 单源连发 6 篇（source 交替被 %2 打破，这里手工构造同源）
        now = datetime.now(timezone.utc)
        items = []
        for k in range(6):
            pub = (now - timedelta(hours=k)).isoformat()
            items.append({"id": "j%d" % k, "title": "x%d" % k, "url": "v%d" % k,
                          "source": "solo", "source_base": "solo",
                          "published_at": pub, "discovered_at": pub,
                          "score": 70.0, "summary": "x", "keywords": []})
        t = {"ids": {i["id"] for i in items}, "terms": set()}
        collect.finalize_topic(t, items, {}, collect.CONFIG)
        cap = collect.CONFIG["heat"]["signal_cap"]
        per = collect.CONFIG["heat"].get("signal_per_source_cap", 2)
        src_cap = collect.CONFIG["heat"]["source_cap"]
        # signal_count 是窗口内的原始条数（展示用，6 条就是 6 条）；进分数的那一项
        # 必须被每源上限截断：单源 6 篇只算 per 个信号。
        self.assertEqual(t["signal_count"], 6)
        expect = round(100 * (0.45 * min(1.0, 1 / src_cap)
                              + 0.35 * min(1.0, per / cap)
                              + 0.20 * 1.0), 1)
        self.assertAlmostEqual(t["score"], expect, places=1,
                               msg="单源 6 篇的热度 %s 不等于按每源上限 %d 截断后的 %s"
                                   % (t["score"], per, expect))
        self.assertLess(t["score"], 100 * 0.35,
                        "单源簇热度不应吃满 0.35 那一项")

    def test_topic_title_matches_representative(self):
        t, items = self._topic([0.1, 0.2])
        self.assertEqual(t["title"], t["representative"]["title"],
                         "热点标题与代表报道不同源：卡片会文不对题")


class TestTrendsRollingWindow(unittest.TestCase):
    def _dailies(self, dates):
        out = {}
        for d in dates:
            out[d] = {"date": d, "sections": [
                {"category": "科研进展",
                 "articles": [{"score": 80.0, "topic_id": "t1",
                               "topic_title": "T1", "title": "a"}]}]}
        return out

    def test_windows_are_equal_length_and_adjacent(self):
        gen = datetime(2026, 10, 13, 2, 0, tzinfo=timezone.utc)  # 周二
        dates = [(gen.astimezone(collect.TZ_CN).date() - timedelta(days=i)).isoformat()
                 for i in range(20)]
        tr = collect.build_trends(self._dailies(dates), gen, collect.CONFIG)
        win = tr.get("windowDays", 7)
        ws, we = tr["windowStart"], tr["windowEnd"]
        ps, pe = tr["prevStart"], tr["prevEnd"]
        self.assertEqual((datetime.fromisoformat(we) - datetime.fromisoformat(ws)).days,
                         win - 1, "当前窗口不是完整 %d 天" % win)
        self.assertEqual((datetime.fromisoformat(pe) - datetime.fromisoformat(ps)).days,
                         win - 1, "前一窗口不是完整 %d 天" % win)
        self.assertEqual((datetime.fromisoformat(ws) - datetime.fromisoformat(pe)).days,
                         1, "两个窗口不紧邻，中间会漏天或重叠")

    def test_tuesday_no_longer_compares_two_days_to_seven(self):
        """周二的旧实现：this_week 只含周一周二 2 天，却和完整上周 7 天比。"""
        gen = datetime(2026, 10, 13, 2, 0, tzinfo=timezone.utc)
        dates = [(gen.astimezone(collect.TZ_CN).date() - timedelta(days=i)).isoformat()
                 for i in range(20)]
        tr = collect.build_trends(self._dailies(dates), gen, collect.CONFIG)
        delta = tr["categoryDelta"][0]
        # 每天 80 分：滚动 7 天窗口下 thisWeek 应为 7*80=560，而不是 2*80=160
        self.assertAlmostEqual(delta["thisWeek"], 560.0, places=1,
                               msg="thisWeek=%s 仍是半截周（2 天）的量" % delta["thisWeek"])
        self.assertAlmostEqual(delta["deltaPct"], 0.0, places=1,
                               msg="等长等量窗口下环比应为 0%%，实测 %s%%" % delta["deltaPct"])


class TestConfigCarriesNewKnobs(unittest.TestCase):
    def test_config_json_has_clustering_and_heat_knobs(self):
        with io.open(os.path.join(ROOT, "collector", "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        cc = cfg.get("clustering") or {}
        self.assertIn("embed_threshold", cc)
        self.assertIn("max_cluster_size", cc)
        self.assertIn("signal_per_source_cap", cfg.get("heat") or {})
        self.assertIn("window_days", cfg.get("trends") or {},
                      "trends 段没有 window_days：滚动窗口不可调")


if __name__ == "__main__":
    unittest.main(verbosity=2)
