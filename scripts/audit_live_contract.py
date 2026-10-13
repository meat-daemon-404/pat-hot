#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PAT-HOT 线上契约审计（纯标准库，只读，不写任何文件）。

为什么需要它（--check 看不见的那一类）
------------------------------------------------
collector/collect.py 的 --check 只看本地 dist/ 目录，而且只断言"约定的地址在不在、
形状对不对"。它结构上看不见两件事：

1) 镜像失鲜。扁平地址 api/v1/*.json 与 data/*.json 是重构前就发布给外部消费者的
   兼容层，由 write_outputs 每次把 T 光电频道复制过去。文件在、返回 200、内容却是
   上一轮的——这种"静默变旧"--check 完全放行。2026-10-13 实测：两个线上域名的
   api/v1/biz.json 都还在发 2026-10-11 的 25 条，而 api/v1/tech/biz.json 已经是
   2026-10-12 的 26 条，--check 全绿。
2) 部署不一致。GitHub Pages 由 CI 每次推 master 自动部署，Cloudflare Pages 只在手动
   `wrangler pages deploy` 时更新。同一份仓库在两个域名上可以是两代产物。--check 是
   本机的，永远看不见这件事。

所以这个脚本做三件 --check 做不到的事：跨域名比对、镜像与频道数据逐字段比对、
分类 feed 与 items.json 一致性比对（feed 里出现 items.json 没有的条目 = 陈旧残留）。

用法
------------------------------------------------
  python scripts/audit_live_contract.py                 # 审计两个线上域名
  python scripts/audit_live_contract.py --host URL      # 只审计指定域名，可重复
  python scripts/audit_live_contract.py --self-test     # 不打网络，验证审计逻辑本身会报警
退出码：0 = 没问题；1 = 发现问题（或自测失败）；2 = 网络不可达，无法判定。
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

DEFAULT_HOSTS = [
    "https://sun-zihang.github.io/pat-hot/",
    "https://pat-hot.pages.dev/",
]
CHANNELS = ["physics", "astro", "tech"]
FLAT_ALIAS = "tech"          # 扁平地址的内容 = 这个频道
JSON_ENDPOINTS = ["items", "hot-topics", "dailies", "daily", "stories", "trends"]
UA = {"User-Agent": "pat-hot-audit/1.0 (+github.com/sun-zihang/pat-hot)"}
TIMEOUT = 90
# 三频道声明的分类数（physics 9 / astro 8 / tech 11）里最小的那个是 8；取 5
# 作为"确实跑过一轮"的下限，既不会因为某频道缩表就误报，也不会让空跑蒙混过关。
MIN_FEED_CHECKS = 5


def fetch(host, path):
    """返回 (status, bytes, error)。网络失败时 status 为 None。"""
    url = host.rstrip("/") + "/" + path.lstrip("/")
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read(), None
    except urllib.error.HTTPError as e:
        return e.code, b"", None
    except Exception as e:
        return None, b"", "%s: %s" % (type(e).__name__, str(e)[:80])


def load_json(host, path, problems, label):
    st, body, err = fetch(host, path)
    if err:
        problems.append("[%s] %s 网络不可达（%s）" % (label, path, err))
        return None, True        # (值, 是否网络故障)
    if st != 200:
        problems.append("[%s] %s 返回 %s（对外承诺的地址应该 200）" % (label, path, st))
        return None, False
    if body[:1] not in (b"{", b"["):
        problems.append("[%s] %s 不是 JSON，开头是 %r——Pages 对缺失路径会返回 200 + 单页 HTML，"
                        "光看状态码发现不了" % (label, path, body[:24]))
        return None, False
    try:
        return json.loads(body.decode("utf-8")), False
    except Exception as e:
        problems.append("[%s] %s JSON 解析失败：%s" % (label, path, e))
        return None, False


def canon(obj):
    """规范化比较：忽略键顺序。"""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def channel_path(ch, name):
    return "api/v1/%s/%s.json" % (ch, name)


def flat_path(name):
    return "api/v1/%s.json" % name


def audit_host(host, problems, stats=None):
    """审计一个域名。返回 True 表示遇到网络故障（结论不可信）。

    stats 记录各类比对实际做了多少次：没有它，"OK"可能只是"什么都没比"
    （比如 index.html 取不到 -> 声明的 slug 表为空 -> feed 检查整段跳过）。
    """
    if stats is None:
        stats = {}
    tally = lambda key, n=1: stats.__setitem__(key, stats.get(key, 0) + n)
    label = host.replace("https://", "").rstrip("/")
    net_fail = False


    # --- 1. 每个频道的端点必须可取且是 JSON ---
    docs = {}
    for ch in CHANNELS:
        for name in JSON_ENDPOINTS:
            doc, nf = load_json(host, channel_path(ch, name), problems, label)
            if nf:
                net_fail = True
            docs["%s/%s" % (ch, name)] = doc
    if net_fail:
        return True

    # --- 2. 扁平兼容地址必须与频道数据逐字段相同 ---
    # 这是今天真实出过问题的地方：文件在、200、内容旧一轮。
    for name in JSON_ENDPOINTS:
        flat, nf = load_json(host, flat_path(name), problems, label)
        if nf:
            return True
        chan = docs.get("%s/%s" % (FLAT_ALIAS, name))
        if flat is None or chan is None:
            continue
        # api/v1/dailies.json 线上一直是"裸日期字典"，频道地址是带 schemaVersion 的
        # 包装文档——两种形状都是已发布契约，比对时剥掉包装。
        flat_core = flat.get("dailies", flat) if isinstance(flat, dict) else flat
        chan_core = chan.get("dailies", chan) if isinstance(chan, dict) else chan
        tally("mirror_comparisons")
        if canon(flat_core) != canon(chan_core):
            fg = (flat.get("generatedAt") if isinstance(flat, dict) else None) or "?"
            cg = (chan.get("generatedAt") if isinstance(chan, dict) else None) or "?"
            problems.append("[%s] 镜像失鲜：%s 与 %s 内容不一致（扁平 %s / 频道 %s）——"
                            "老订阅者会拿到旧数据，而 --check 看不见"
                            % (label, flat_path(name), channel_path(FLAT_ALIAS, name),
                               str(fg)[:19], str(cg)[:19]))

    # --- 3. biz（政策/招投标）同样有扁平地址，且只有光电频道产出 ---
    fb, nf = load_json(host, "api/v1/biz.json", problems, label)
    if nf:
        return True
    cb, _ = load_json(host, channel_path(FLAT_ALIAS, "biz"), problems, label)
    if fb is not None and cb is not None:
        tally("mirror_comparisons")
        if canon(fb) != canon(cb):
            problems.append("[%s] 镜像失鲜：api/v1/biz.json 与 api/v1/tech/biz.json 不一致"
                            "（%s 条 vs %s 条）"
                            % (label, fb.get("count"), cb.get("count")))

    # --- 4. 分类 feed：地址必须真的存在、必须是 XML、条目必须在同类 items.json 里 ---
    items_by_ch = {}
    for ch in CHANNELS:
        doc = docs.get("%s/items" % ch)
        items_by_ch[ch] = ({i.get("url") for i in (doc or {}).get("items", [])},
                           _cats_of(doc))
    declared = _declared_slugs(host, docs, problems, label)
    if not declared:
        problems.append("[%s] 取不到站点自己宣传的分类表（index.html 快照里的 catCls），"
                        "feed 检查整段没跑——这个 OK 不算数" % label)
    for ch, slugmap in declared.items():
        have_urls, cat_counts = items_by_ch[ch]
        for cat, slug in sorted(slugmap.items()):
            path = "feed/%s/category/%s.xml" % (ch, slug)
            st, body, err = fetch(host, path)
            if err:
                net_fail = True
                continue
            tally("feed_checks")
            if st != 200:
                problems.append("[%s] %s 返回 %s（Agent 接入页把它列成订阅地址）"
                                % (label, path, st))
                continue
            if body[:5] != b"<?xml":
                problems.append("[%s] %s 不是 XML，开头 %r——Pages 对缺失路径返回 200 + 单页 "
                                "HTML，阅读器会以为订阅成功" % (label, path, body[:24]))
                continue
            try:
                links = re.findall(rb"<link>(https?://[^<]+)</link>", body)[1:]
            except Exception as e:
                problems.append("[%s] %s 提取 link 失败：%s" % (label, path, e))
                continue
            for u in links:
                uu = u.decode("utf-8").replace("&amp;", "&")
                if uu not in have_urls:
                    problems.append("[%s] %s 里的 %r 不在 api/v1/%s/items.json（陈旧残留）"
                                    % (label, path, uu[:70], ch))
            n_data = cat_counts.get(cat, 0)
            if len(links) > min(n_data, 30):
                problems.append("[%s] %s 条目数 %d 多于数据里的 %d 条"
                                % (label, path, len(links), n_data))
    if net_fail:
        return True

    # --- 5. 两个域名的 index.html 内嵌快照 generatedAt 一致性（跨域名只报不判） ---
    st, body, err = fetch(host, "index.html")
    if err:
        return True
    m = re.search(r"const S = (.*?);\r?\n", body.decode("utf-8", "replace"), re.S)
    if not m:
        problems.append("[%s] index.html 里找不到内嵌快照 const S（多半是旧产物）" % label)
    else:
        try:
            snap = json.loads(m.group(1).replace("<\\/", "</"))
            have = set(snap.get("channels") or {})
            if have != set(CHANNELS):
                problems.append("[%s] 快照频道 %s，缺 %s"
                                % (label, sorted(have), sorted(set(CHANNELS) - have)))
        except Exception as e:
            problems.append("[%s] 快照无法解析：%s" % (label, e))

    # --- 6. 空跑守卫 ---
    # 放在 audit_host 里而不是 main()：这样 --self-test（直接调 audit_host）和
    # 变异测试都覆盖得到。写在 main() 里等于这道关没人测过。
    n_mirror = stats.get("mirror_comparisons", 0)
    n_feed = stats.get("feed_checks", 0)
    if n_mirror < len(JSON_ENDPOINTS) + 1:
        problems.append("[%s] 镜像比对只做了 %d 次（应至少 %d 次）——结论不成立"
                        % (label, n_mirror, len(JSON_ENDPOINTS) + 1))
    if n_feed < MIN_FEED_CHECKS:
        problems.append("[%s] feed 只检查了 %d 个，少于 %d 个——结论不成立"
                        % (label, n_feed, MIN_FEED_CHECKS))
    return False



def _cats_of(items_doc):
    out = {}
    for i in (items_doc or {}).get("items", []):
        out[i.get("category")] = out.get(i.get("category"), 0) + 1
    return out


def _declared_slugs(host, docs, problems, label):
    """从 index.html 快照的 catCls 取"站点自己对外宣传的分类 slug 表"。

    故意不用仓库里的 channels.json：要查的就是"线上页面宣传的地址"与
    "线上真实可取的地址"是否对得上，用本地配置会把这个偏差抹掉。
    """
    st, body, err = fetch(host, "index.html")
    if err:
        problems.append("[%s] index.html 不可达，无法确定宣传的分类" % label)
        return {}
    m = re.search(r"const S = (.*?);\r?\n", body.decode("utf-8", "replace"), re.S)
    if not m:
        return {}
    try:
        snap = json.loads(m.group(1).replace("<\\/", "</"))
    except Exception:
        return {}
    out = {}
    for ch, cd in (snap.get("channels") or {}).items():
        if ch in CHANNELS and cd.get("catCls"):
            out[ch] = dict(cd["catCls"])
    return out


# ---------------------------------------------------------------- 自测
# 审计逻辑本身必须会响。以下用合成数据跑比对函数，确认"镜像失鲜""HTML 冒充
# JSON""feed 残留旧条目"三种情况都能被报出来——守门不响比没有守门更糟。
def self_test():
    fails = []

    def expect(cond, what):
        if not cond:
            fails.append(what)

    # 1) 镜像比较逻辑：内容不同必须判为不一致
    flat = {"schemaVersion": 1, "generatedAt": "2026-10-11T10:50:55+00:00",
            "count": 25, "items": [{"url": "https://a/1"}]}
    chan = {"schemaVersion": 1, "generatedAt": "2026-10-12T14:08:22+00:00",
            "count": 26, "items": [{"url": "https://a/1"}, {"url": "https://a/2"}]}
    expect(canon(flat) != canon(chan), "镜像内容不同时未判为不一致")
    same = {"generatedAt": "x", "items": [{"a": 1, "b": 2}]}
    other = {"items": [{"b": 2, "a": 1}], "generatedAt": "x"}
    expect(canon(same) == canon(other), "键顺序不同被误判为不一致")

    # 2) dailies 的两种已发布形状必须能对齐（裸字典 vs 包装文档）
    bare = {"2026-10-12": {"headline": {"title": "T"}}}
    wrapped = {"schemaVersion": 1, "count": 1,
               "dailies": {"2026-10-12": {"headline": {"title": "T"}}}}
    b = bare.get("dailies", bare)
    w = wrapped.get("dailies", wrapped)
    expect(canon(b) == canon(w), "dailies 两种形状对齐失败")

    # 3) HTML 冒充 JSON：状态 200 也要拦
    for body in (b"<!DOCTYPE html><html>", b""):
        expect(body[:1] not in (b"{", b"["), "非 JSON 开头未被识别")

    # 4) feed 残留：条目不在 items.json 就要报
    have = {"https://keep/1"}
    links = [b"https://keep/1", b"https://gone/2"]
    stale = [u.decode().replace("&amp;", "&") for u in links if u.decode() not in have]
    expect(stale == ["https://gone/2"], "feed 陈旧条目识别失败")

    # 5) 声明过的分类必须逐个成 slug
    catcls = {"引力波": "gw", "科研进展": "research"}
    expect(sorted(catcls.values()) == ["gw", "research"], "slug 表处理异常")

# 6) 用假网络跑一遍 audit_host 本体：上面 1-5 只测了纯函数，测不到主流程的
#    签名/分支错误（就真出过一次：audit_host 多了一个没人用的参数，纯函数自测
#    全绿，真跑才炸）。这里把 fetch 换成合成响应，确认三类已知问题都能被报出。
    real_fetch = globals()["fetch"]
    try:
        globals()["fetch"] = _fake_fetch
        probs = []
        audit_host("https://fake.invalid/", probs)
        joined = "\n".join(probs)
        # 两条镜像检查分别断言：只写"镜像失鲜"的话，短路掉其中一条，另一条
        # 也会产出同样的字样，自测照样绿——变异测试实测到这两个盲区。
        expect("api/v1/items.json 与" in joined, "audit_host 没报出 items 镜像失鲜")
        expect("api/v1/biz.json 与" in joined, "audit_host 没报出 biz 镜像失鲜")
        expect("陈旧残留" in joined, "audit_host 没报出 feed 陈旧残留")
        expect("不是 XML" in joined, "audit_host 没报出 HTML 冒充 feed")
        expect(_net_blind(probs) is False, "假网络下不该判为不可达")

        # 全绿场景：一致、都是 XML，不该报任何问题
        globals()["fetch"] = _fake_fetch_ok
        probs2 = []
        audit_host("https://fake.invalid/", probs2)
        expect(not probs2, "一致数据下误报：%s" % probs2[:2])

        # 不可达场景：必须判为"未判定"，不能当成通过
        globals()["fetch"] = _fake_fetch_down
        probs3 = []
        blind = audit_host("https://fake.invalid/", probs3)
        expect(blind is True, "网络全断时 audit_host 没返回不可达（会被当成通过）")
        expect(_net_blind(probs3), "网络全断时没记录不可达问题")

        # 空跑场景：端点都取得到、feed 也都在，但站点不宣传任何分类 ->
        # 一次 feed 检查都没做成。这种"什么都没比"绝不能算通过。
        globals()["fetch"] = _fake_fetch_empty
        probs4 = []
        stats4 = {}
        audit_host("https://fake.invalid/", probs4, stats4)
        expect(stats4.get("feed_checks", 0) == 0, "空分类表下不该记到 feed 检查")
        expect(any("取不到站点自己宣传的分类表" in p for p in probs4),
               "空分类表没给出针对性诊断（只剩笼统的一句，运维看不出是快照缺 catCls）")
        expect(any("结论不成立" in p for p in probs4),
               "空跑未被守卫拦下：%s" % probs4[:2])

        # 镜像一次都没比成的场景：频道端点在、扁平端点全 404 ->
        # 镜像比对数为 0，必须被镜像侧守卫拦下（这条之前没有任何样本覆盖，
        # 变异测试实测到"短路掉镜像计数守卫"自测照样绿）。
        globals()["fetch"] = _fake_fetch_no_flat
        probs5 = []
        stats5 = {}
        audit_host("https://fake.invalid/", probs5, stats5)
        expect(stats5.get("mirror_comparisons", 0) == 0,
               "扁平端点全 404 时镜像比对数应为 0，实际 %s" % stats5.get("mirror_comparisons"))
        expect(any("镜像比对只做了" in p for p in probs5),
               "镜像一次没比成却没人报警：%s" % probs5[:2])
    finally:
        globals()["fetch"] = real_fetch

    return fails


def _net_blind(problems):
    return any("网络不可达" in p for p in problems)


def _mk_docs(stamp, n_items):
    """造一份频道数据：items 数量与 generatedAt 可控，用于制造镜像偏差。"""
    items = [{"url": "https://x/%d" % i, "category": "科研进展"} for i in range(n_items)]
    return {
        "items": {"schemaVersion": 1, "generatedAt": stamp,
                  "count": len(items), "items": items},
        "hot-topics": {"schemaVersion": 1, "generatedAt": stamp, "count": 0, "items": []},
        "dailies": {"schemaVersion": 1, "generatedAt": stamp, "count": 0, "dailies": {}},
        "daily": {"generatedAt": stamp, "total": len(items)},
        "stories": {"schemaVersion": 1, "generatedAt": stamp, "count": 0, "items": []},
        "trends": {"generatedAt": stamp, "newTopics": [], "sustainedTopics": []},
        "biz": {"schemaVersion": 1, "generatedAt": stamp, "count": len(items),
                "items": [{"url": "https://x/%d" % i} for i in range(n_items)]},
    }


_CHANNEL_DATA = {}

# 假站点宣传的分类表。真实站点声明 28 个（physics 9 / astro 8 / tech 11），
# 这里取 6 个：既高于 MIN_FEED_CHECKS，让"一切正常"的样本能真的通过，
# 又不至于让自测跑太久。低于阈值的空样本另测（见 _fake_fetch_empty）。
_FIXTURE_SLUGS = {
    "physics": {"生物物理": "biophys", "量子信息与计算": "quantum"},
    "astro": {"引力波": "gw", "系外行星": "exoplanet", "科研进展": "research"},
    "tech": {"激光": "laser"},
}


def _index_html(slugs_by_ch):
    snap = {"channels": {ch: {"catCls": dict(m)} for ch, m in slugs_by_ch.items()},
            "generatedAt": "2026-10-12T14:08:22+00:00"}
    return ("<!DOCTYPE html><html><head></head><body><script>const S = %s;\n"
            "</script></body></html>" % json.dumps(snap)).encode("utf-8")


def _fake_fetch(host, path):
    """故意制造四类问题：

    - api/v1/items.json（扁平）落后一轮 -> 镜像失鲜
    - api/v1/biz.json（扁平）落后一轮 -> 镜像失鲜
    - feed/astro/category/gw.xml 里一条 items.json 没有的条目 -> 陈旧残留
    - feed/astro/category/exoplanet.xml 用 SPA HTML 顶替 -> HTML 冒充 feed
    """
    global _CHANNEL_DATA
    _CHANNEL_DATA = _mk_docs("2026-10-12T14:08:22+00:00", 3)
    if path.startswith("api/v1/") and path.endswith(".json"):
        name = path.split("/")[-1][:-5]
        if name not in _CHANNEL_DATA:
            return 404, b"", None
        # 扁平地址（api/v1/<name>.json，正好两段斜杠）里让 items 与 biz 变旧
        if path.count("/") == 2 and name in ("items", "biz"):
            stale = _mk_docs("2026-10-11T10:50:55+00:00", 2)
            return 200, json.dumps(stale[name]).encode(), None
        return 200, json.dumps(_CHANNEL_DATA[name]).encode(), None
    if path == "index.html":
        return 200, _index_html(_FIXTURE_SLUGS), None
    if path == "feed/astro/category/gw.xml":    # 残留：条目不在 items.json
        return 200, (b"<?xml version='1.0'?><rss><channel><link>https://site/</link>"
                     b"<item><link>https://x/999</link></item></channel></rss>"), None
    if path == "feed/astro/category/exoplanet.xml":  # HTML 冒充 feed
        return 200, b"<!DOCTYPE html><html><body>SPA fallback</body></html>", None
    if path.endswith(".xml"):
        return 200, (b"<?xml version='1.0'?><rss><channel><link>https://site/</link>"
                     b"</channel></rss>"), None
    return 404, b"", None


def _fake_fetch_down(host, path):
    """全部请求都连不上：审计必须说"未判定"，而不是"通过"。"""
    return None, b"", "URLError: simulated outage"


def _fake_fetch_empty(host, path):
    """端点全都取得到、feed 也都在，但 index.html 不宣传任何分类：
    这正是"一次比对都没做成却报 OK"的形态，必须被空跑守卫拦下。"""
    data = _mk_docs("2026-10-12T14:08:22+00:00", 2)
    if path.startswith("api/v1/") and path.endswith(".json"):
        name = path.split("/")[-1][:-5]
        if name in data:
            return 200, json.dumps(data[name]).encode(), None
    if path == "index.html":
        return 200, _index_html({ch: {} for ch in CHANNELS}), None
    if path.endswith(".xml"):
        return 200, (b"<?xml version='1.0'?><rss><channel><link>https://site/</link>"
                     b"</channel></rss>"), None
    return 404, b"", None


def _fake_fetch_no_flat(host, path):
    """频道端点齐全，但所有扁平地址（api/v1/<name>.json）都 404。

    镜像比对因此一次也做不成。若守卫只看"有没有报错"，这种站点会被判 OK。
    """
    data = _mk_docs("2026-10-12T14:08:22+00:00", 2)
    if path.startswith("api/v1/") and path.endswith(".json"):
        name = path.split("/")[-1][:-5]
        if path.count("/") == 2:          # 扁平地址：全部 404
            return 404, b"", None
        if name in data:                  # 频道地址：正常
            return 200, json.dumps(data[name]).encode(), None
    if path == "index.html":
        return 200, _index_html(_FIXTURE_SLUGS), None
    if path.endswith(".xml"):
        return 200, (b"<?xml version='1.0'?><rss><channel><link>https://site/</link>"
                     b"</channel></rss>"), None
    return 404, b"", None


def _fake_fetch_ok(host, path):
    """一切自洽：镜像与频道一致，feed 都是合法 XML 且不含多余条目。

    分类表用 _FIXTURE_SLUGS（6 个），必须高于 MIN_FEED_CHECKS，否则"健康样本"
    会被空跑守卫判死，自测就失去意义。
    """
    data = _mk_docs("2026-10-12T14:08:22+00:00", 2)
    if path.startswith("api/v1/") and path.endswith(".json"):
        name = path.split("/")[-1][:-5]
        if name in data:
            return 200, json.dumps(data[name]).encode(), None
    if path == "index.html":
        return 200, _index_html(_FIXTURE_SLUGS), None
    if path.endswith(".xml"):
        return 200, (b"<?xml version='1.0'?><rss><channel><link>https://site/</link>"
                     b"</channel></rss>"), None
    return 404, b"", None




def main():
    ap = argparse.ArgumentParser(description="PAT-HOT 线上契约审计")
    ap.add_argument("--host", action="append", default=None,
                    help="要审计的域名，可重复；默认审计 GitHub Pages 与 Cloudflare Pages")
    ap.add_argument("--self-test", action="store_true",
                    help="不打网络，验证审计逻辑本身会报警")
    args = ap.parse_args()

    if args.self_test:
        fails = self_test()
        for f in fails:
            print("[x] " + f)
        print("self-test: %s" % ("FAILED" if fails else "OK"))
        return 1 if fails else 0

    hosts = args.host or DEFAULT_HOSTS
    problems = []
    any_net = False
    for h in hosts:
        before = len(problems)
        stats = {}
        url = h if h.endswith("/") else h + "/"
        net = audit_host(url, problems, stats)
        any_net = any_net or net
        # 空跑守卫在 audit_host 里（那里 --self-test 与变异测试都覆盖得到；
        # 写在 main() 里等于这道关没人测过）。这里只汇报。
        verdict = ("网络不可达，未判定" if net
                   else ("发现 %d 个问题" % (len(problems) - before)
                         if len(problems) > before else "OK"))
        print("[*] %s：%s（比对 %d 次、feed %d 个）"
              % (h, verdict, stats.get("mirror_comparisons", 0),
                 stats.get("feed_checks", 0)))

    if problems:
        print("\n发现 %d 个问题：" % len(problems))
        for p in problems:
            print("  - " + p)
        return 1
    if any_net:
        print("\n[*] 有域名不可达，结论不完整")
        return 2
    print("\n[*] 线上契约审计通过：端点可取、镜像与频道一致、feed 与数据一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
