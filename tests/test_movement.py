# -*- coding: utf-8 -*-
"""compute_movement 回归锁（AIHOT hot.ts 运动徽标的静态移植）。

锁住的语义：
1. 首轮没有基线：只有发布时间落进 new_hours 的事件算 new，其余 unknown——
   不许把"第一次跑"渲染成一屏"新"。
2. 间隔超过 movement_max_gap_hours（周末/停机恢复）：一律不报涨跌，
   绝不把"恢复了采集"说成"暴涨"（AIHOT behind/late 排除的静态对应）。
3. 可比基线：prev heat 为 0 → new；涨幅 > up_pct → up，≥ rising_pct → rising
   徽标；跌幅 → down；带外推的次级标题匹配（topic id 每轮按成员重算）。
4. surge：近 new_hours 窗口新加入的独立来源 ≥3 且占比 ≥50%（多家开始报）。
5. "新"锚定最早**发布时间**而不是 discovered——无可信发布时间的条目
   discovered 恒等于本轮时刻，全按 discovered 会把每轮都判成"新"。
"""
import io
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

TZ = timezone.utc


def _iso(dt):
    return dt.astimezone(TZ).isoformat()


class TestComputeMovement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pathot-mv-")
        self._data = collect.DATA_DIR
        collect.DATA_DIR = self.tmp

    def tearDown(self):
        collect.DATA_DIR = self._data
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_prev(self, ch, items, gen):
        d = os.path.join(self.tmp, ch)
        os.makedirs(d, exist_ok=True)
        with io.open(os.path.join(d, "hot-topics.json"), "w", encoding="utf-8") as f:
            json.dump({"schemaVersion": 1, "generatedAt": _iso(gen),
                       "count": len(items), "items": items}, f)

    def _item(self, iid, title, source, pub, disc, score=50.0):
        return {"id": iid, "title": title, "url": "https://e/" + iid,
                "source": source, "source_base": source,
                "published_at": _iso(pub) if pub else None,
                "discovered_at": _iso(disc), "summary": "x" * 120, "score": score}

    def _topic(self, tid, title, ids, score, sources, signals):
        return {"id": tid, "title": title, "ids": set(ids), "terms": set(),
                "score": score, "source_count": len(sources), "signal_count": signals,
                "sources": sorted(sources), "latest_at": "2026-10-13T00:00:00+00:00"}

    def test_first_run_no_baseline(self):
        now = datetime(2026, 10, 13, 10, 0, tzinfo=TZ)
        fresh = self._item("i1", "刚发生", "S", now - timedelta(hours=2), now)
        old = self._item("i2", "旧事件", "S", now - timedelta(days=2), now)
        topics = [self._topic("t1", "刚发生", ["i1"], 60, {"S"}, 1),
                  self._topic("t2", "旧事件", ["i2"], 90, {"S"}, 3)]
        collect.compute_movement(topics, [fresh, old], "tech", now)
        by = {t["id"]: t for t in topics}
        self.assertEqual(by["t1"]["trend"], "new")
        self.assertIn("new", by["t1"]["badges"])
        self.assertEqual(by["t2"]["trend"], "unknown",
                         "首轮无基线不许把旧事件标成新或涨跌")
        self.assertIsNone(by["t2"]["trendPct"])

    def test_stale_gap_never_reports_growth(self):
        now = datetime(2026, 10, 13, 10, 0, tzinfo=TZ)
        # 上一轮是 4 天前（周末停机）：恢复后热度暴涨也不能报 up/rising
        self._write_prev("tech", [{"id": "t1", "title": "事件", "heat": 10.0}],
                         now - timedelta(days=4))
        it = self._item("i1", "事件", "S", now - timedelta(hours=1), now)
        topics = [self._topic("t1", "事件", ["i1"], 95, {"S"}, 6)]
        collect.compute_movement(topics, [it], "tech", now)
        self.assertEqual(topics[0]["trend"], "new", "只有发布时间确实是新的才 new")
        self.assertNotIn("rising", topics[0]["badges"])
        self.assertIsNone(topics[0]["trendPct"], "不可比间隔绝不给涨跌百分比")

    def test_up_rising_down_with_comparable_baseline(self):
        now = datetime(2026, 10, 13, 10, 0, tzinfo=TZ)
        base = now - timedelta(hours=12)
        self._write_prev("tech", [
            {"id": "tA", "title": "升温事件", "heat": 50.0},
            {"id": "tB", "title": "回落事件", "heat": 80.0},
            {"id": "tC", "title": "平稳事件", "heat": 60.0},
        ], base)
        # 标题匹配路径：本轮 id 与上一轮不同（成员集合变了→id 重算）
        ta = self._item("ia", "升温事件", "S1", base - timedelta(hours=8), base)
        tb = self._item("ib", "回落事件", "S1", base - timedelta(hours=8), base)
        tc = self._item("ic", "平稳事件", "S1", base - timedelta(hours=8), base)
        topics = [self._topic("NEW_A", "升温事件", ["ia"], 62.0, {"S1"}, 2),
                  self._topic("tB", "回落事件", ["ib"], 55.0, {"S1"}, 2),
                  self._topic("tC", "平稳事件", ["ic"], 61.0, {"S1"}, 2)]
        collect.compute_movement(topics, [ta, tb, tc], "tech", now)
        by = {t["title"]: t for t in topics}
        self.assertEqual(by["升温事件"]["trend"], "up")
        self.assertIn("rising", by["升温事件"]["badges"], "涨幅 24% ≥15% 要徽标")
        self.assertEqual(by["回落事件"]["trend"], "down")
        self.assertLess(by["回落事件"]["trendPct"], -10)
        self.assertEqual(by["平稳事件"]["trend"], "flat")
        self.assertEqual(by["平稳事件"]["badges"], [])

    def test_zero_prev_heat_is_new(self):
        now = datetime(2026, 10, 13, 10, 0, tzinfo=TZ)
        base = now - timedelta(hours=12)
        self._write_prev("tech", [{"id": "tZ", "title": "旧闻", "heat": 0.0}], base)
        it = self._item("iz", "旧闻", "S", base - timedelta(days=1), base)
        topics = [self._topic("tZ", "旧闻", ["iz"], 70, {"S"}, 4)]
        collect.compute_movement(topics, [it], "tech", now)
        self.assertEqual(topics[0]["trend"], "new", "上一窗口零证据=刚出现（AIHOT prevAll<=0）")

    def test_surge_requires_multiple_new_sources(self):
        now = datetime(2026, 10, 13, 10, 0, tzinfo=TZ)
        base = now - timedelta(hours=12)
        self._write_prev("tech", [{"id": "tS", "title": "大事件", "heat": 40.0}], base)
        # 两家早在报道，最近 6h 又进来三家：新参与者 3/5 = 60% ≥ 阈值
        its = [self._item("i1", "大事件报道", "S1", base - timedelta(hours=20), base),
               self._item("i2", "大事件报道2", "S2", base - timedelta(hours=20), base),
               self._item("i3", "大事件跟进", "S3", now - timedelta(hours=3), now),
               self._item("i4", "大事件跟进", "S4", now - timedelta(hours=2), now),
               self._item("i5", "大事件跟进", "S5", now - timedelta(hours=1), now)]
        topics = [self._topic("tS", "大事件", ["i1", "i2", "i3", "i4", "i5"],
                              44.0, {"S1", "S2", "S3", "S4", "S5"}, 5)]
        collect.compute_movement(topics, its, "tech", now)
        self.assertIn("surge", topics[0]["badges"])
        self.assertNotIn("rising", topics[0]["badges"], "surge 优先，rising 让位")

    def test_untrusted_pubdate_items_do_not_flood_new(self):
        # 无可信发布时间的条目：discovered 恒等于本轮时刻；
        # "新"只锚定有发布时间的最早证据，否则每轮都会误报成一屏"新"
        now = datetime(2026, 10, 13, 10, 0, tzinfo=TZ)
        base = now - timedelta(hours=12)
        self._write_prev("tech", [{"id": "tU", "title": "无时间事件", "heat": 60.0}], base)
        it = self._item("iu", "无时间事件", "S", None, now)
        topics = [self._topic("tU", "无时间事件", ["iu"], 72.0, {"S"}, 3)]
        collect.compute_movement(topics, [it], "tech", now)
        self.assertEqual(topics[0]["trend"], "up", "72 vs 60 = +20% > 10%")
        self.assertNotIn("new", topics[0]["badges"])

    def test_missing_prev_file_is_first_run(self):
        now = datetime(2026, 10, 13, 10, 0, tzinfo=TZ)
        it = self._item("i1", "事件", "S", now - timedelta(days=1), now)
        topics = [self._topic("t1", "事件", ["i1"], 60, {"S"}, 2)]
        collect.compute_movement(topics, [it], "tech", now)
        self.assertEqual(topics[0]["trend"], "unknown")

    def test_stories_fields_are_written(self):
        # 运动字段必须同时进频道版与扁平镜像 stories（同一内容的两个地址，
        # 历史上出过两边字段漂移让消费端拿到不同形状）
        src = io.open(os.path.join(ROOT, "collector", "collect.py"),
                      encoding="utf-8").read()
        self.assertEqual(src.count('"trend": t.get("trend", "unknown")'), 2,
                         "频道版与扁平镜像各写一次，缺一边就是漂移")


if __name__ == "__main__":
    unittest.main()
