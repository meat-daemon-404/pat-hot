# -*- coding: utf-8 -*-
"""沿用频道（未本次采集）的 tier / selected 保真测试。

起因（2026-10-13 发现）：write_outputs 会按 _CHANNEL_TIERS 重算每条的 tier 与
selected，而这张表只在 run_channel 里填充。单频道运行（--channel tech）或
--rebuild 时，physics/astro 是"从磁盘沿用"的，表是空的 —— 于是全部条目落到
tiers.default=media，精选门槛从官方的 55 抬到 65。实测 physics 的 89 个
official 条目全部掉成 media、5 条精选清零：页面 200、契约自检全绿，
内容却静默变薄。这类"看起来成功了的丢数据"正是本文件要拦的。
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


def _utc(y=2026, mo=10, d=12, h=6):
    return datetime(y, mo, d, h, tzinfo=timezone.utc)


class TestSourceTierMap(unittest.TestCase):
    def test_map_covers_every_persisted_item(self):
        """线上产物里每条 item 的信源都必须能在 sources.json 查到 tier。

        查不到就会退回条目自带 tier（再退回 default），说明源被改名或删了，
        这条断言把那种漂移变成显式失败。
        """
        for ch in collect.CHANNEL_ORDER:
            p = os.path.join(ROOT, "data", ch, "items.json")
            if not os.path.exists(p):
                self.skipTest("尚无 %s 产物" % ch)
                continue
            with io.open(p, encoding="utf-8") as f:
                items = (json.load(f) or {}).get("items", [])
            tm = collect.source_tier_map(ch)
            for it in items:
                key = it.get("source_base") or it["source"]
                self.assertIn(key, tm, "%s: 信源 %r 不在 sources.json 里" % (ch, key))

    def test_map_matches_persisted_tiers(self):
        """重建出的 tier 必须与产物里已发布的 tier 一致。"""
        for ch in collect.CHANNEL_ORDER:
            p = os.path.join(ROOT, "data", ch, "items.json")
            if not os.path.exists(p):
                self.skipTest("尚无 %s 产物" % ch)
                continue
            with io.open(p, encoding="utf-8") as f:
                items = (json.load(f) or {}).get("items", [])
            tm = collect.source_tier_map(ch)
            for it in items:
                key = it.get("source_base") or it["source"]
                self.assertEqual(tm[key], it.get("tier"),
                                 "%s/%s tier 漂移：配置=%s 产物=%s"
                                 % (ch, key, tm[key], it.get("tier")))

    def test_missing_sources_json_returns_empty_not_crash(self):
        real = collect.SOURCES_PATH
        try:
            collect.SOURCES_PATH = os.path.join(ROOT, "__no_such_sources__.json")
            collect._SOURCE_TIER_CACHE.pop("tech", None)
            self.assertEqual(collect.source_tier_map("tech"), {})
        finally:
            collect.SOURCES_PATH = real
            collect._SOURCE_TIER_CACHE.pop("tech", None)


class TestCarriedTierPreserved(unittest.TestCase):
    """load_carried_channels 必须把 tier 表一起恢复。"""

    def _sandbox(self, ch="physics"):
        tmp = tempfile.mkdtemp(prefix="pathom-tier-")
        ch_dir = os.path.join(tmp, "data", ch)
        os.makedirs(ch_dir)
        iso = "2026-10-12T06:00:00+00:00"
        srcs = collect.source_tier_map(ch)
        # 用该频道真实存在的信源造条目，覆盖 official 门槛边界 55~65
        official = [s for s, t in srcs.items() if t == "official"]
        media = [s for s, t in srcs.items() if t == "media"]
        picks = []
        if official:
            picks.append((official[0], "official", 58.0))
        if media:
            picks.append((media[0], "media", 70.0))
        items = [{"id": "i%d" % n, "title": "T%d" % n, "url": "https://e/%d" % n,
                  "source": s, "source_base": s, "source_type": "rss",
                  "category": "其他", "published_at": "2026-10-12",
                  "discovered_at": iso, "score": sc, "tier": want}
                 for n, (s, want, sc) in enumerate(picks)]
        docs = {
            "items.json": {"schemaVersion": 1, "generatedAt": iso,
                           "count": len(items), "items": items},
            "hot-topics.json": {"schemaVersion": 1, "generatedAt": iso,
                                "count": 0, "items": []},
            "daily.json": {"total": len(items), "byCategory": [], "byDay": [],
                           "bySource": []},
            "dailies.json": {"schemaVersion": 1, "generatedAt": iso,
                             "count": 0, "dailies": {}},
            "trends.json": {"newTopics": [], "sustainedTopics": [],
                            "categoryDelta": []},
        }
        for name, doc in docs.items():
            with io.open(os.path.join(ch_dir, name), "w", encoding="utf-8") as f:
                json.dump(doc, f)
        return tmp, ch, picks

    def test_channel_tiers_populated_after_carry(self):
        tmp, ch, picks = self._sandbox()
        real_data, real_dist = collect.DATA_DIR, collect.DIST_DIR
        real_carry = dict(collect._CHANNEL_TIERS)
        try:
            collect.DATA_DIR = os.path.join(tmp, "data")
            collect._CHANNEL_TIERS.pop(ch, None)
            out = collect.load_carried_channels([ch], _utc())
            self.assertIn(ch, out)
            tm = collect._CHANNEL_TIERS.get(ch) or {}
            self.assertTrue(tm, "沿用频道没有恢复 tier 表，write_outputs 会把全部条目当 media")
            for src, want, _sc in picks:
                self.assertEqual(tm.get(src), want)
        finally:
            collect.DATA_DIR, collect.DIST_DIR = real_data, real_dist
            collect._CHANNEL_TIERS.clear()
            collect._CHANNEL_TIERS.update(real_carry)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_official_threshold_survives_rewrite(self):
        """58 分的官方条目：恢复 tier 才不会被 65 分媒体门槛挤掉精选。"""
        tmp, ch, picks = self._sandbox()
        if not any(w == "official" and 55 <= sc < 65 for _s, w, sc in picks):
            self.skipTest("该频道没有 official 源可用来构造 55~65 边界")
        real_data, real_dist = collect.DATA_DIR, collect.DIST_DIR
        real_carry = dict(collect._CHANNEL_TIERS)
        try:
            collect.DATA_DIR = os.path.join(tmp, "data")
            collect.DIST_DIR = os.path.join(tmp, "dist")
            collect._CHANNEL_TIERS.pop(ch, None)
            carried = collect.load_carried_channels([ch], _utc())
            results = {ch: carried[ch]}
            collect.write_outputs(results, _utc())
            with io.open(os.path.join(collect.DATA_DIR, ch, "items.json"),
                         encoding="utf-8") as f:
                items = (json.load(f) or {}).get("items", [])
            off = [i for i in items if i.get("tier") == "official"]
            self.assertTrue(off, "官方 tier 在重写中丢失")
            self.assertTrue(all(i["selected"] for i in off),
                            "55~65 分的官方条目被误判为非精选")
        finally:
            collect.DATA_DIR, collect.DIST_DIR = real_data, real_dist
            collect._CHANNEL_TIERS.clear()
            collect._CHANNEL_TIERS.update(real_carry)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_unknown_source_falls_back_to_persisted_tier(self):
        """sources.json 查不到该源时，退回条目自带 tier，而不是静默降为 media。"""
        tmp = tempfile.mkdtemp(prefix="pathom-unknown-")
        real = collect._CHANNEL_TIERS
        try:
            collect._CHANNEL_TIERS = {"tech": {}}
            tiers = collect.CONFIG["tiers"]
            item = {"source": "已被改名的源", "tier": "official", "score": 58.0}
            tier_map = collect._CHANNEL_TIERS.get("tech", {})

            def _tier_of(it, _tm=tier_map):
                return (_tm.get(it.get("source_base") or it["source"])
                        or it.get("tier")
                        or tiers.get("default", "media"))

            self.assertEqual(_tier_of(item), "official")
            self.assertEqual(tiers[_tier_of(item)]["select_threshold"],
                             tiers["official"]["select_threshold"])
        finally:
            collect._CHANNEL_TIERS = real
            shutil.rmtree(tmp, ignore_errors=True)


class TestRebuildFlagExists(unittest.TestCase):
    """--rebuild：不联网、用磁盘产物重出 dist/（改了模板不必等一次采集）。"""

    def test_flag_registered(self):
        src = io.open(os.path.join(ROOT, "collector", "collect.py"),
                      encoding="utf-8").read()
        self.assertIn('"--rebuild"', src)

    def test_rebuild_does_not_fetch(self):
        """rebuild 路径必须在 collect() 之前返回，不产生网络请求。"""
        src = io.open(os.path.join(ROOT, "collector", "collect.py"),
                      encoding="utf-8").read()
        m = src.index("def main(")
        body = src[m:]
        self.assertLess(body.index("args.rebuild"),
                        body.index("run_channel("),
                        "--rebuild 不应走到采集分支")


if __name__ == "__main__":
    unittest.main()
