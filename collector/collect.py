#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
opto-hot — 光电行业热点统计（以 AIHOT 为模板）

流程: 多源采集(RSS + 行业站) -> 清洗去重 -> 领域分类 -> 打分 -> 热点聚类
输出: data/items.json, data/hot-topics.json, data/daily.json, data/report.csv, dist/index.html

用法:
    python collector/collect.py                 # 全流程
    python collector/collect.py --limit 30      # 每个源最多取 30 条
    python collector/collect.py --skip-html     # 跳过 HTML 站
"""

import argparse
import csv
import hashlib
import html as htmlmod
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_DIR = os.path.join(ROOT, "data")
DIST_DIR = os.path.join(ROOT, "dist")
SOURCES_PATH = os.path.join(HERE, "sources.json")
CONFIG_PATH = os.path.join(HERE, "config.json")
REPO_URL = "https://github.com/sun-zihang/opto-hot"

# ---------------- 集中配置（collector/config.json，可缺省回退） ----------------
DEFAULT_CONFIG = {
    "scoring": {
        "w_source": 45.0, "w_convergence": 20.0, "w_signal": 15.0, "w_recency": 20.0,
        "convergence_cap": 6, "signal_cap": 10, "recency_days": 30,
        "missing_pubdate_penalty": 0.5,
    },
    "tiers": {
        "official": {"select_threshold": 55.0, "label": "官方"},
        "media": {"select_threshold": 65.0, "label": "媒体"},
        "default": "media",
    },
    "heat": {
        "recent_hours": 48, "source_cap": 6, "signal_cap": 10,
        "status_hot_min_sources": 5, "status_hot_min_heat": 80.0,
        "status_trending_min_sources": 3,
    },
    "clustering": {"tfidf_threshold": 0.14},
    "daily": {
        "headline_count": 1, "picks_count": 4, "flash_count": 10,
        "max_per_source": 2, "dedup_window_days": 7, "per_category_limit": 8,
    },
    "llm": {
        "provider": "sensenova",
        "model": "sensenova-6.8-flash-lite",
        "api_url": "https://token.sensenova.cn/v1/chat/completions",
        "max_items": 30, "batch_size": 8, "timeout": 40,
        "density_penalty": 0.9,
    },
    "images": {
        "provider": "sensenova",
        "model": "sensenova-u1.5-lite",
        "api_url": "https://token.sensenova.cn/v1/images/generations",
        "max_images": 6,
        "size": "2752x1536",
        "aspect_ratio": "16:9",
        "timeout": 120,
        "watermark": False,
        "retention_days": 30,
    },
}


def _deep_merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            user = json.load(f)
        return _deep_merge(DEFAULT_CONFIG, user)
    except Exception as e:
        if os.path.exists(CONFIG_PATH):
            print("[!] 配置文件读取失败，使用默认配置: %s" % e, flush=True)
        return _deep_merge(DEFAULT_CONFIG, {})


CONFIG = load_config()
# 信源名 -> tier（official/media），main() 中从 sources.json 构建
_SOURCE_TIER = {}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 opto-hot/0.1")

TZ_CN = timezone(timedelta(hours=8))
NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
}

# ---------------- 领域词表 ----------------
DOMAIN_TERMS = [
    "激光", "光模块", "光通信", "光芯片", "光电", "光学", "镜头", "光纤", "光子", "光刻",
    "光刻机", "激光雷达", "光伏", "红外", "探测器", "成像", "显示", "面板", "OLED",
    "Mini LED", "Micro LED", "LED", "投影", "AR", "VR", "XR", "激光器", "晶圆", "掩模",
    "光电子", "传感器", "车载", "自动驾驶", "半导体", "硅光", "CPO", "相干", "WDM",
    "PON", "光网络", "数据中心", "算力", "EUV", "光刻胶", "光栅", "全息", "太赫兹",
    "摄像头", "相机", "镜片", "棱镜", "TOF", "3D传感", "屏幕", "发光", "照明", "背光",
    "驱动", "封装", "基板", "玻璃", "镀膜", "机器视觉", "激光焊接", "激光切割",
    "激光打标", "激光清洗", "医疗激光", "光纤传感", "海缆", "光缆", "硅光芯片",
    "VCSEL", "DFB", "EML", "硅基OLED", "量子点", "MicroOLED", "AMOLED", "光互联",
    "光引擎", "光交换", "OCS", "光计算", "智能驾驶", "智驾",
    "laser", "photonics", "optical", "optics", "fiber", "fibre", "lidar", "led",
    "oled", "display", "infrared", "imaging", "sensor", "semiconductor", "euv",
    "photonic", "quantum", "camera", "microled", "miniled", "vcsel", "holographic",
    "optoelectronic", "lidars", "silicon photonics",
]

STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "for", "on", "with", "and", "or", "from",
    "by", "at", "is", "are", "was", "were", "be", "been", "has", "have", "had",
    "its", "their", "this", "that", "new", "news", "how", "why", "what", "via",
    "over", "under", "into", "about", "after", "before", "between", "per", "as",
    "up", "down", "out", "off", "2026", "2025", "will", "can", "may", "could",
    "would", "should", "not", "no", "yes", "one", "two", "first", "last", "day",
    # 学术/新闻通用词
    "using", "used", "use", "show", "shows", "shown", "report", "reports",
    "review", "reviews", "key", "important", "significant", "advanced",
    "recent", "recently", "second", "third", "order", "room", "time", "times",
    "week", "weeks", "year", "years", "month", "months", "made", "make",
    "making", "build", "built", "creating", "create", "provides", "provide",
    "offer", "offers", "enable", "enables", "enabling", "allow", "allows",
    "allowing", "help", "helps", "improve", "improves", "improved", "enhance",
    "enhances", "enhanced", "achieve", "achieves", "achieved", "explore",
    "explores", "exploring", "investigate", "investigates", "investigating",
    "design", "designs", "designed", "develop", "develops", "developed",
    "development", "applications", "application", "devices", "device",
    "structures", "structure", "properties", "property", "materials",
    "material", "techniques", "technique", "technology", "technologies",
    "through", "control", "generation", "learning", "hybrid", "interaction",
    "networks", "network", "systems", "system", "methods", "method", "based",
    "model", "models", "phase", "between", "toward", "towards", "high", "low",
    "large", "small", "single", "multi", "novel", "demonstrate", "demonstrates",
    "demonstrated", "demonstrating", "study", "studies", "analysis", "approach",
    "framework", "performance", "results", "result", "beyond", "within",
    "without", "along", "across", "among", "around", "behind", "inside",
    "outside", "throughout", "upon", "analysis", "comparative", "comparison",
    "limits", "limit", "based", "using", "toward", "overcoming", "overcome",
    "break", "breaking", "power", "wall", "programmable", "programming",
    "observations", "observation", "newly", "emerging", "towards", "toward",
    "and", "the", "for", "into", "along", "silencing", "pain", "light",
    "artificial", "leaf", "hot", "electron", "based", "using", "through",
}

CATEGORY_RULES = [
    ("激光", ["激光", "laser", "lasers"]),
    ("光通信", ["光通信", "光模块", "光纤", "光缆", "海缆", "光网络", "光芯片", "硅光",
               "CPO", "WDM", "PON", "相干", "800G", "1.6T", "光互联", "光交换", "OCS",
               "光引擎", "fiber", "fibre", "photonics", "optical network",
               "optical communication", "submarine cable", "数据中心", "智算"]),
    ("显示与面板", ["OLED", "Mini LED", "Micro LED", "LED", "显示", "面板", "AMOLED",
                 "背光", "量子点", "屏幕", "display", "microled", "miniled", "AR",
                 "VR", "XR", "眼镜", "头显"]),
    ("光电芯片与半导体", ["半导体", "晶圆", "EUV", "光刻", "光刻机", "掩模", "封装",
                       "VCSEL", "DFB", "EML", "semiconductor", "euv", "wafer",
                       "lithograph", "chip", "芯片"]),
    ("光学元件与成像", ["光学", "镜头", "镜片", "棱镜", "相机", "成像", "TOF", "3D传感",
                     "红外", "探测器", "摄像头", "optics", "lens", "imaging", "camera",
                     "infrared", "全息", "光波导", "光场", "显微"]),
    ("光传感与激光雷达", ["激光雷达", "光纤传感", "传感器", "lidar", "sensor", "雷达"]),
    ("光伏与新能源", ["光伏", "太阳能", "光电转换", "photovoltaic", "solar"]),
    ("科研进展", ["arxiv", "nature photonics", "量子", "太赫兹", "quantum", "论文", "研究"]),
    ("产业与资本", ["IPO", "上市", "并购", "收购", "融资", "投资", "营收", "净利润", "财报",
                  "半年报", "产能", "扩产", "中标", "订单", "产业", "政策", "标准", "展会",
                  "博览会", "峰会", "论坛", "投产", "下线", "揭牌", "亮相", "发布", "推出",
                  "合作", "签约", "预增", "定增", "获批", "大单", "调研", "基地", "战略",
                  "人工智能大会", "WAIC"]),
    ("通信与算力", ["通信", "运营商", "5G", "6G", "算力", "人工智能", "大模型", "昇腾",
                  "云网", "数字化", "智能化", "AI", "电信", "移动", "联通", "网络",
                  "宽带", "数据"]),
]
RESEARCH_SOURCES = {"arXiv 光学与光子学 (physics.optics)", "Nature Photonics", "Phys.org 物理新闻"}
CATEGORY_ORDER = [c for c, _ in CATEGORY_RULES] + ["其他"]


def log(msg):
    print(msg, flush=True)


def now_utc():
    return datetime.now(timezone.utc)


def http_get(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/xml;q=0.9, text/html;q=0.8, */*;q=0.7",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), r.headers.get("Content-Type", "")


def detect_charset(data, declared=None):
    if declared:
        cs = declared.lower().split(";")[0].strip()
        if cs in ("gb2312", "gbk", "gb18030", "gb1323", "gb-2312"):
            return "gbk"
        return cs or "utf-8"
    head = data[:4096].decode("latin1", "ignore")
    m = re.search(r'charset=["\']?\s*([\w-]+)', head, re.I)
    if m:
        cs = m.group(1).lower()
        if cs in ("gb2312", "gbk", "gb18030", "gb1323", "gb-2312"):
            return "gbk"
        return cs
    return "utf-8"


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    fmts = (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    )
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def parse_rss(data):
    root = None
    err = None
    try:
        root = ET.fromstring(data)
    except Exception as e:
        err = e
    if root is None:
        text = None
        for enc in ("gbk", "gb18030", "utf-8"):
            try:
                text = data.decode(enc)
                break
            except Exception:
                continue
        if text is None:
            raise err if err else ValueError("cannot decode feed")
        text = re.sub(r"<\?xml[^>]*\?>", "", text, count=1)
        root = ET.fromstring(text)

    RSS1 = "{http://purl.org/rss/1.0/}"
    tag = (root.tag or "").rsplit("}", 1)[-1]
    entries = []

    if tag == "rss":  # RSS 2.0
        ch = root.find("channel")
        if ch is None:
            return None, entries
        for it in ch.findall("item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            desc = it.findtext("description") or it.findtext("content:encoded", namespaces=NS) or ""
            pub = it.findtext("pubDate") or it.findtext("dc:date", namespaces=NS)
            if title or link:
                entries.append({"title": title, "link": link, "desc": desc, "pub": pub})

    elif tag == "RDF":  # RSS 1.0 (RDF)
        for it in root.findall(RSS1 + "item"):
            title = (it.findtext(RSS1 + "title") or "").strip()
            lel = it.find(RSS1 + "link")
            link = (lel.text or "").strip() if lel is not None else ""
            desc = (it.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
                    or it.findtext("description") or "")
            pub = it.findtext("dc:date", namespaces=NS) or it.findtext(RSS1 + "date")
            if title or link:
                entries.append({"title": title, "link": link, "desc": desc, "pub": pub})

    elif tag == "feed":  # Atom
        for e in root.findall("atom:entry", NS):
            title = (e.findtext("atom:title", namespaces=NS) or "").strip()
            lel = e.find("atom:link", namespaces=NS)
            link = lel.get("href", "") if lel is not None else ""
            pub = e.findtext("atom:published", namespaces=NS) or e.findtext("atom:updated", namespaces=NS)
            desc = e.findtext("atom:summary", namespaces=NS) or ""
            if title or link:
                entries.append({"title": title, "link": link, "desc": desc, "pub": pub})
    return None, entries


def parse_html_links(data, charset, base, cfg):
    text = data.decode(charset, "replace")
    pattern = cfg.get("anchor_pattern")
    links = []
    for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', text, re.S | re.I):
        href = htmlmod.unescape(m.group(1)).strip()
        if href.startswith(("javascript:", "#", "mailto:", "tel:")):
            continue
        if pattern and not re.search(pattern, href):
            continue
        title = re.sub(r"<[^>]+>", "", m.group(2))
        title = htmlmod.unescape(title)
        title = re.sub(r"\s+", " ", title).strip()
        if len(title) < 8:
            continue
        pub = None
        t = title
        if cfg.get("title_date") == "prefix":
            md = re.match(r"^\s*(\d{4}-\d{2}-\d{2})\s*[|\u00b7\-\u2013\u2014]?\s*", title)
            if md:
                pub = md.group(1)
                t = title[md.end():].strip(" |\u00b7-\u2013\u2014\t").strip()
        ud = cfg.get("url_date")
        if ud == "y-m-d":
            mu = re.search(r"(20\d{2})(\d{2})(\d{2})-", href)
            if mu:
                pub = "%s-%s-%s" % (mu.group(1), mu.group(2), mu.group(3))
        elif ud == "y-m-d-t":
            mu = re.search(r"t(\d{4})(\d{2})(\d{2})", href)
            if mu:
                pub = "%s-%s-%s" % (mu.group(1), mu.group(2), mu.group(3))
        elif ud == "y-m":
            mu = re.search(r"/(20\d{2})-(\d{2})/", href)
            if not mu:
                mu = re.search(r"/industry/(20\d{2})(\d{2})/", href)
            if mu:
                pub = "%s-%s" % (mu.group(1), mu.group(2))
        if not t:
            continue
        full = urllib.parse.urljoin(base, href)
        links.append({"title": t, "href": full, "pub": pub})
    seen = set()
    out = []
    for lk in links:
        k = norm_title(lk["title"])
        if k in seen:
            continue
        seen.add(k)
        out.append(lk)
    return out


def norm_title(t):
    t = t.lower()
    t = re.sub(r"[^\w\u4e00-\u9fff]+", "", t)
    return t


def kw_hit(title_lower, term):
    t = term.lower()
    if re.search(r"[a-z0-9]", t):
        return re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", title_lower) is not None
    return t in title_lower


def extract_keywords(title):
    tl = title.lower()
    kws = set()
    for term in DOMAIN_TERMS:
        if kw_hit(tl, term):
            kws.add(term.lower())
    for w in re.findall(r"[a-z][a-z0-9+.\-]{2,}", tl):
        w2 = w.strip("+.-")
        if w2 and w2 not in STOPWORDS and len(w2) >= 4 and w2 not in kws:
            kws.add(w2)
    return sorted(kws)


def classify(title, source):
    tl = title.lower()
    for cat, kws in CATEGORY_RULES:
        for kw in kws:
            if kw_hit(tl, kw):
                return cat
    if source in RESEARCH_SOURCES:
        return "科研进展"
    return "其他"


def make_id(title, url):
    return hashlib.sha1((norm_title(title) + "|" + url).encode("utf-8")).hexdigest()[:12]


def age_days(dt):
    return max(0.0, (now_utc() - dt).total_seconds() / 86400.0)


def eff_dt(it):
    """优先使用原文发布时间，缺失时回退到收录时间（AIHOT 时间轴语义）"""
    p = it.get("published_at")
    if p and len(p) >= 10:
        dt = parse_date(p)
        if dt:
            return dt
    return datetime.fromisoformat(it["discovered_at"])


# ---------------- 采集 ----------------
def fetch_rss(cfg, limit):
    data, ctype = http_get(cfg["url"])
    _, entries = parse_rss(data)
    kws = [k.lower() for k in cfg.get("filter_keywords", [])]
    tk = [k.lower() for k in cfg.get("title_keywords", [])]
    items = []
    for e in entries:
        title = (e["title"] or e["link"] or "").strip()
        if not title:
            continue
        if kws and not any(k in title.lower() for k in kws):
            continue
        if tk and not any(k in title.lower() for k in tk):
            continue
        pub = parse_date(e["pub"])
        desc_plain = re.sub(r"<[^>]+>", " ", e["desc"] or "")
        summary = re.sub(r"\s+", " ", htmlmod.unescape(desc_plain)).strip()[:500]
        items.append({
            "title": htmlmod.unescape(title).strip(),
            "url": (e["link"] or "").strip(),
            "published_at": pub.isoformat() if pub else None,
            "summary": summary or None,
        })
        if len(items) >= limit:
            break
    return items


SOGOU_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def fetch_sogou(cfg, limit):
    """搜狗微信：多查询 + 会话 Cookie + 反爬检测 + 公众号/时间/摘要提取"""
    import http.cookiejar
    import urllib.parse as up
    queries = cfg.get("queries") or []
    if not queries:
        m = re.search(r"[?&]query=([^&]+)", cfg["url"])
        queries = [up.unquote(m.group(1))] if m else ["光电行业"]
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    tk = [k.lower() for k in cfg.get("title_keywords", [])]
    seen = set()
    items = []
    for q in queries:
        url = "https://weixin.sogou.com/weixin?type=2&query=" + up.quote(q)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": SOGOU_UA, "Referer": "https://weixin.sogou.com/"})
            data = opener.open(req, timeout=20).read().decode("utf-8", "replace")
        except Exception as e:
            log("[FAIL] 搜狗微信 query=%s: %s" % (q, e))
            time.sleep(2)
            continue
        if "antispider" in data or "请输入验证码" in data or "news-list" not in data:
            log("[!] 搜狗微信 query=%s 触发反爬或页面异常，跳过" % q)
            time.sleep(2)
            continue
        for m2 in re.finditer(r'id="sogou_vr_\d+_box_\d+"[\s\S]*?</li>', data):
            blk = m2.group(0)
            tm = re.search(r'uigs="article_title_\d+"[^>]*>([\s\S]*?)</a>', blk)
            if not tm:
                continue
            title = re.sub(r"<[^>]+>", "", tm.group(1))
            title = re.sub(r"<!--red_beg-->|<!--red_end-->", "", title)
            title = re.sub(r"\s+", " ", htmlmod.unescape(title)).strip()
            if len(title) < 8:
                continue
            hm = re.search(r'href="(/link\?url=[^"]+)"', blk)
            if not hm:
                continue
            am = re.search(r'class="all-time-y2"[^>]*>([^<]+)<', blk)
            account = htmlmod.unescape(am.group(1)).strip() if am else ""
            tmm = re.search(r"timeConvert\('(\d+)'\)", blk)
            pub = None
            if tmm:
                try:
                    pub = datetime.fromtimestamp(int(tmm.group(1)), timezone.utc).isoformat()
                except Exception:
                    pass
            sm = re.search(r'class="txt-info"[^>]*>([\s\S]*?)</p>', blk)
            summary = re.sub(r"<[^>]+>", "", sm.group(1)) if sm else ""
            summary = re.sub(r"<!--red_beg-->|<!--red_end-->", "", summary)
            summary = re.sub(r"\s+", " ", htmlmod.unescape(summary)).strip()[:300]
            if pub:
                try:
                    if age_days(datetime.fromisoformat(pub)) > 90:
                        continue
                except Exception:
                    pass
            if tk and not any(k in title.lower() for k in tk):
                continue
            key = norm_title(title)
            if key in seen:
                continue
            seen.add(key)
            src = cfg["name"] + (" · " + account if account else "")
            items.append({"title": title,
                          "url": urllib.parse.urljoin("https://weixin.sogou.com", hm.group(1)),
                          "published_at": pub, "summary": summary or None, "source": src})
            if len(items) >= limit:
                break
        time.sleep(1.2)
        if len(items) >= limit:
            break
    return items


def fetch_html(cfg, limit):
    if cfg.get("sogou_wechat"):
        return fetch_sogou(cfg, limit)
    data, ctype = http_get(cfg["url"])
    charset = cfg.get("charset") or detect_charset(data, ctype)
    links = parse_html_links(data, charset, cfg["url"], cfg)
    tk = [k.lower() for k in cfg.get("title_keywords", [])]
    items = []
    for lk in links:
        if tk and not any(k in lk["title"].lower() for k in tk):
            continue
        items.append({
            "title": lk["title"],
            "url": lk["href"],
            "published_at": lk["pub"],
            "summary": None,
        })
        if len(items) >= limit:
            break
    return items


def collect(sources, limit, skip_rss=False, skip_html=False):
    raw = []
    for stype in ("rss", "html"):
        if stype == "rss" and skip_rss:
            continue
        if stype == "html" and skip_html:
            continue
        for cfg in sources.get(stype, []):
            try:
                got = fetch_rss(cfg, limit) if stype == "rss" else fetch_html(cfg, limit)
                log("[OK] %-4s %s: %d 条" % (stype, cfg["name"], len(got)))
                for g in got:
                    g["source"] = g.get("source") or cfg["name"]
                    g["source_base"] = cfg["name"]
                    g["source_type"] = stype
                    g["source_weight"] = cfg.get("weight", 0.8)
                raw.extend(got)
            except Exception as e:
                log("[FAIL] %-4s %s: %s" % (stype, cfg["name"], e))
    return raw


# ---------------- 热点聚类 ----------------
def text_tokens(title):
    """向量化 token：中文字符二元组 + 英文词 + 领域特征词（用于 TF-IDF 语义向量）"""
    tl = title.lower()
    toks = []
    for seg in re.findall(r"[\u4e00-\u9fff]+", tl):
        if len(seg) == 1:
            toks.append(seg)
        else:
            toks.append(seg)
            toks.extend(seg[i:i + 2] for i in range(len(seg) - 1))
    toks.extend(w for w in re.findall(r"[a-z][a-z0-9]{2,}", tl) if w not in STOPWORDS)
    for term in DOMAIN_TERMS:
        if kw_hit(tl, term):
            toks.append("DT:" + term.lower())
    return toks


def tfidf_vectors(items):
    docs = [text_tokens(it["title"]) for it in items]
    df = {}
    for d in docs:
        for t in set(d):
            df[t] = df.get(t, 0) + 1
    n = max(1, len(docs))
    vecs = []
    for d in docs:
        c = {}
        for t in d:
            c[t] = c.get(t, 0) + 1
        v = {t: (1 + (f ** 0.5)) * (n / (df.get(t, 1) + 1)) for t, f in c.items()}
        vecs.append(v)
    return vecs


def cosine_sim(a, b):
    inter = [t for t in a if t in b]
    if not inter:
        return 0.0
    dot = sum(a[t] * b[t] for t in inter)
    na = sum(x * x for x in a.values()) ** 0.5
    nb = sum(x * x for x in b.values()) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def cluster_semantic(items, threshold=0.14):
    """语义聚类：TF-IDF 向量贪心聚合为主；可选神经嵌入做近重复合并（OPTOHOT_EMBED=1）"""
    n = len(items)
    tfidf = tfidf_vectors(items)
    sim = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            s = cosine_sim(tfidf[i], tfidf[j])
            sim[i][j] = sim[j][i] = s
    groups = list(range(n))
    while True:
        best = (threshold, -1, -1)
        for i in range(n):
            gi = groups[i]
            if gi < 0:
                continue
            for j in range(i + 1, n):
                gj = groups[j]
                if gj < 0 or gi == gj:
                    continue
                if sim[i][j] > best[0]:
                    best = (sim[i][j], i, j)
        if best[1] < 0:
            break
        ga, gb = groups[best[1]], groups[best[2]]
        for k in range(n):
            if groups[k] == gb:
                groups[k] = ga

    # 神经近重复合并（真实嵌入；相似度>=0.70 视为同一事件的重复/改写报道）
    if os.environ.get("OPTOHOT_EMBED") == "1":
        try:
            os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "20")
            os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "10")
            try:
                urllib.request.urlopen(urllib.request.Request(
                    "https://huggingface.co/BAAI/bge-small-zh-v1.5/resolve/main/config.json",
                    headers={"User-Agent": UA}), timeout=8)
            except Exception:
                log("[!] HuggingFace 不可达，跳过神经近重复合并")
                use_nn = False
            else:
                use_nn = True
            if use_nn:
                from sentence_transformers import SentenceTransformer
                _m = SentenceTransformer("BAAI/bge-small-zh-v1.5")
                vecs = _m.encode([it["title"] for it in items], normalize_embeddings=True)

                def find(x):
                    while parent[x] != x:
                        parent[x] = parent[parent[x]]
                        x = parent[x]
                    return x

                def union(a, b):
                    ra, rb = find(a), find(b)
                    if ra != rb:
                        parent[rb] = ra

                parent = list(range(n))
                for i in range(n):
                    vi = vecs[i]
                    for j in range(i + 1, n):
                        s = float(sum(vi[k] * vecs[j][k] for k in range(len(vi))))
                        if s >= 0.70:
                            union(i, j)
                gset = {}
                for idx, g in enumerate(groups):
                    gset.setdefault(g, []).append(idx)
                for members in gset.values():
                    for k in range(1, len(members)):
                        union(members[0], members[k])
                rootmap = {}
                ng = [0] * n
                for x in range(n):
                    r = find(x)
                    if r not in rootmap:
                        rootmap[r] = len(rootmap)
                    ng[x] = rootmap[r]
                groups = ng
                log("[*] 神经近重复合并完成（sentence-transformers / bge-small-zh）")
        except Exception as e:
            log("[!] 神经嵌入不可用，仅 TF-IDF 聚类: %s" % e)

    from collections import defaultdict
    gmap = defaultdict(list)
    for idx, g in enumerate(groups):
        if g >= 0:
            gmap[g].append(items[idx])
    topics = []
    for its in gmap.values():
        if len(its) >= 2:
            terms = set()
            for it in its:
                terms.update(it.get("keywords", []))
            topics.append({"terms": terms, "ids": {i["id"] for i in its}})
    return topics


def cluster_topics(items):
    return cluster_semantic(items)


def compute_scores(items, topics, source_weight, source_tier=None, cfg=None):
    """条目打分（AIHOT 方法论移植版）：
    score = w_source*来源权重 + w_convergence*跨源收敛度 + w_signal*主题信号 + w_recency*时效
    - 跨源收敛度：同一事件被越多独立来源报道，得分越高（防单源刷榜）
    - 旧文不刷屏：无可信发布时间的条目，时效分打折
    """
    cfg = cfg or CONFIG
    sc = cfg["scoring"]
    w_src, w_conv = sc["w_source"], sc["w_convergence"]
    w_sig, w_rec = sc["w_signal"], sc["w_recency"]
    conv_cap = max(1, sc["convergence_cap"])
    sig_cap = max(1, sc["signal_cap"])
    rec_days = max(1, sc["recency_days"])
    pub_pen = sc["missing_pubdate_penalty"]
    # 事件 -> 独立来源集合（跨源收敛度）
    topic_sources = {}
    for t in topics:
        srcs = {i["source"] for i in items if i["id"] in t["ids"]}
        for iid in t["ids"]:
            topic_sources.setdefault(iid, set()).update(srcs)
    item_topic = {}
    for t in topics:
        for iid in t["ids"]:
            item_topic[iid] = max(item_topic.get(iid, 0), len(t["ids"]))
    for it in items:
        sig = item_topic.get(it["id"], 0)
        nsrc = len(topic_sources.get(it["id"], set()))
        conv = min(1.0, nsrc / conv_cap)
        dt = eff_dt(it)
        rec = max(0.0, 1 - age_days(dt) / rec_days)
        if not it.get("published_at"):
            rec *= pub_pen  # 无可信发布时间：时效分打折，不再全额回退收录时间
        sw = source_weight.get(it["source"], 0.8)
        it["score"] = round(w_src * sw + w_conv * conv
                            + w_sig * min(1.0, sig / sig_cap) + w_rec * rec, 1)
        it["convergence"] = round(conv, 3)
    for t in topics:
        finalize_topic(t, items, source_tier, cfg)
    topic_map = {}
    for t in topics:
        for iid in t["ids"]:
            topic_map[iid] = (t["id"], t["title"])
    for it in items:
        if it["id"] in topic_map:
            it["topic_id"], it["topic_title"] = topic_map[it["id"]]


def merge_duplicate_topics(topics, items):
    """合并高度重叠或代表条目相同的主题"""
    changed = True
    while changed:
        changed = False
        for i in range(len(topics)):
            for j in range(i + 1, len(topics)):
                a, b = topics[i], topics[j]
                inter = len(a["ids"] & b["ids"])
                if inter / max(1, min(len(a["ids"]), len(b["ids"]))) >= 0.5:
                    a["ids"] |= b["ids"]
                    a["terms"] |= b["terms"]
                    topics.pop(j)
                    changed = True
                    break
            if changed:
                break
    rep = {}
    for t in topics:
        its = [it for it in items if it["id"] in t["ids"]]
        rep[id(t)] = max(its, key=lambda i: i["discovered_at"]) if its else None
    groups = {}
    order = []
    for t in topics:
        b = rep[id(t)]
        key = b["id"] if b else ("none:" + str(id(t)))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(t)
    out = []
    for key in order:
        gs = groups[key]
        if len(gs) == 1:
            out.append(gs[0])
        else:
            base = gs[0]
            for g in gs[1:]:
                base["ids"] |= g["ids"]
                base["terms"] |= g["terms"]
            out.append(base)
    return out

def pick_representative(its, source_tier):
    """选出一篇代表报道：官方一手源优先 -> 有正文摘要 -> 分数高 -> 发布时间早"""
    def _key(i):
        tier_rank = 0 if source_tier.get(i.get("source_base") or i["source"]) == "official" else 1
        has_text = 0 if i.get("summary") else 1
        return (tier_rank, has_text, -i.get("score", 0), i.get("discovered_at", ""))
    return min(its, key=_key)


def finalize_topic(t, items, source_tier=None, cfg=None):
    cfg = cfg or CONFIG
    hc = cfg["heat"]
    recent_h = hc["recent_hours"]
    source_tier = source_tier or {}
    its = [it for it in items if it["id"] in t["ids"]]
    srcs = {i["source"] for i in its}
    # 48 小时窗口内，每个独立来源只算一次（单源刷榜无效）
    recent_srcs = {i["source"] for i in its if age_days(eff_dt(i)) <= recent_h / 24.0}
    t["source_count"] = len(srcs)
    t["signal_count"] = len(its)
    t["sources"] = sorted(srcs)
    t["score"] = round(
        100 * (0.45 * min(1.0, len(srcs) / hc["source_cap"])
               + 0.35 * min(1.0, len(its) / hc["signal_cap"])
               + 0.20 * min(1.0, len(recent_srcs) / max(1, len(srcs)))), 1)
    t["latest_at"] = max(i["discovered_at"] for i in its)
    rep = pick_representative(its, source_tier)
    t["representative"] = {
        "title": rep["title"], "url": rep["url"], "source": rep["source"],
        "published_at": rep.get("published_at"), "score": rep["score"],
        "summary": (rep.get("summary") or "")[:240],
    }
    t["folded_count"] = max(0, len(srcs) - 1)  # "另有 N 家信源报道"
    best = max(its, key=lambda i: i["score"])
    t["title"] = best["title"]
    t["terms"] = sorted(t["terms"])
    t["id"] = make_id(t["title"], "|".join(sorted(i["id"] for i in its)))
    t["links"] = [{
        "title": i["title"], "url": i["url"], "source": i["source"],
        "score": i["score"], "published_at": i["published_at"],
    } for i in sorted(its, key=lambda x: x["score"], reverse=True)[:5]]
    try:
        tvec = tfidf_vectors(its)
        centroid = {}
        for v in tvec:
            for kk, w in v.items():
                centroid[kk] = centroid.get(kk, 0) + w
        ranked = sorted(centroid.items(), key=lambda x: -x[1])
        t["top_terms"] = [k2 for k2, _ in ranked if not k2.startswith("DT:")][:5] or [k2 for k2, _ in ranked][:5]
    except Exception:
        t["top_terms"] = []


def dedupe_topic_titles(topics, items, source_tier=None):
    """合并标题相同的主题（例如同一事件的多个角度）"""
    by_title = {}
    order = []
    for t in topics:
        key = t["title"]
        if key not in by_title:
            by_title[key] = []
            order.append(key)
        by_title[key].append(t)
    out = []
    for key in order:
        gs = by_title[key]
        if len(gs) == 1:
            out.append(gs[0])
            continue
        base = gs[0]
        ids = set()
        terms = set()
        for g in gs:
            ids |= g["ids"]
            terms |= set(g["terms"])
        base["ids"] = ids
        base["terms"] = terms
        finalize_topic(base, items, source_tier)
        out.append(base)
    return out


# ---------------- 统计 ----------------
def build_daily(items, topics, generated):
    def in_window(it, days):
        return age_days(eff_dt(it)) <= days
    n24 = sum(1 for it in items if in_window(it, 1))
    n7 = sum(1 for it in items if in_window(it, 7))
    cats = []
    for cat in CATEGORY_ORDER:
        its = [it for it in items if it["category"] == cat]
        if its:
            cats.append({
                "category": cat,
                "total": len(its),
                "last24h": sum(1 for i in its if in_window(i, 1)),
                "last7d": sum(1 for i in its if in_window(i, 7)),
            })
    days = []
    today = (generated + timedelta(hours=8)).date()
    for k in range(13, -1, -1):
        d = today - timedelta(days=k)
        c = sum(1 for it in items
                if (eff_dt(it) + timedelta(hours=8)).date() == d)
        days.append({"date": d.isoformat(), "count": c})
    src_map = {}
    for it in items:
        s = src_map.setdefault(it["source"], {
            "source": it["source"], "count": 0, "latestAt": it["discovered_at"]})
        s["count"] += 1
        if it["discovered_at"] > s["latestAt"]:
            s["latestAt"] = it["discovered_at"]
    return {
        "generatedAt": generated.isoformat(),
        "total": len(items),
        "last24h": n24,
        "last7d": n7,
        "topicCount": len(topics),
        "byCategory": cats,
        "byDay": days,
        "bySource": sorted(src_map.values(), key=lambda s: -s["count"]),
    }


def fetch_text(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    cs = detect_charset(data)
    txt = data.decode(cs, "replace")
    txt = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", txt, flags=re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = htmlmod.unescape(txt)
    return re.sub(r"\s+", " ", txt)


def extract_biz_text(text, title=""):
    """从详情页文本提取 项目号/预算/截止时间（比标题级更可靠）"""
    biz = {}
    m = re.search(r"(?:项目|招标|采购)(?:编号|项目号|标段号)\s*[:：]\s*([^\s，。；,;]{3,40})", text)
    if not m:
        m = re.search(r"(?:招标编号|项目编号|采购编号|标段(?:编)?号)\s*[:：]?\s*([A-Za-z0-9][A-Za-z0-9\-_（）()]{3,})", text)
    if m:
        biz["project_no"] = m.group(1).strip()
    m = re.search(r"预算(?:金额|资金)?\s*[:：]\s*([0-9,，.]+)\s*(万|亿)?\s*元", text)
    if m:
        biz["budget"] = m.group(1).replace(",", "").replace("，", "") + (m.group(2) or "") + "元"
    m = re.search(r"(?:投标|递交|报名|获取采购文件|响应文件)(?:截止|递交截止)(?:时间)?\s*[:：]?\s*(\d{4}年\d{1,2}月\d{1,2}日(?:\s*\d{1,2}[:：]\d{2})?)", text)
    if not m:
        m = re.search(r"截止时间\s*[:：]?\s*(\d{4}[-年/.]\d{1,2}[-月/.]\d{1,2}日?(?:\s*\d{1,2}[:：]\d{2})?)", text)
    if m:
        biz["deadline"] = m.group(1).replace("年", "-").replace("月", "-").replace("日", "").replace("：", ":")
    if "project_no" not in biz:
        m = re.search(r"(?:发文字号|文号|文件编号)\s*[:：]?\s*([^\s，。；]{3,30})", text)
        if m:
            biz["project_no"] = m.group(1).strip()
    return biz


BIZ_SOURCES = {"中国政府采购网", "中国招标投标公共服务平台", "工信部要闻"}


def extract_biz(title):
    """从标题提取招标/政策结构化字段（项目号/预算/截止时间）——v1 标题级解析"""
    biz = {}
    m = re.search(r"(?:项目|招标|采购)?(?:编号|标段号|文号)\s*[:：]?\s*([A-Za-z0-9][A-Za-z0-9\-—－_（）()]{3,})", title)
    if m:
        biz["project_no"] = m.group(1).strip("（）()")
    m = re.search(r"预算(?:金额|资金)?\s*[:：]?\s*([0-9,，.]+)\s*(万|亿)?\s*元", title)
    if m:
        num = m.group(1).replace(",", "").replace("，", "")
        biz["budget"] = (num + (m.group(2) or "") + "元")
    m = re.search(r"(?:截止|开标|投标截止|递交(?:截止)?)(?:时间)?\s*[:：]?\s*(\d{4}[-年/.]\d{1,2}[-月/.]\d{1,2}日?(?:\s*\d{1,2}[:：]\d{2})?)", title)
    if m:
        biz["deadline"] = m.group(1).replace("年", "-").replace("月", "-").replace("日", "").replace("：", ":")
    return biz


# ---------------- 日报归档 ----------------
WEEKDAYS_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
MONTHS_CN = "一二三四五六七八九十"


def cn_date(dstr):
    """2026-08-03 -> 2026年8月3日"""
    try:
        y, m, d = dstr.split("-")
        return "%s年%d月%d日" % (y, int(m), int(d))
    except Exception:
        return dstr


def role_tag(source):
    if any(k in source for k in ("arXiv", "Nature Photonics", "Phys.org")):
        return "科研"
    if any(k in source for k in ("OFweek", "LEDinside", "CIOE", "COEMA", "C114")):
        return "行业媒体"
    return "媒体"


def build_dailies(items, existing=None):
    """按天生成光电日报（AIHOT 日报机制 + 编排规则）：
    每期 = 头条 1 条 + 今日看点 N 条 + 快讯若干；同一信源在正文最多出现 K 条；
    近 7 天日报已出现过的事件不再入正文（进快讯或略过）。
    """
    dc = CONFIG["daily"]
    by_date = {}
    for it in items:
        d = (eff_dt(it) + timedelta(hours=8)).date().isoformat()
        by_date.setdefault(d, []).append(it)

    def covered_topic_ids(before_date):
        """before_date 之前 dedup_window_days 天内各日报覆盖过的事件 id"""
        out = set()
        try:
            base = datetime.strptime(before_date, "%Y-%m-%d").date()
        except Exception:
            return out
        for dd, entry in (existing or {}).items():
            try:
                delta = (base - datetime.strptime(dd, "%Y-%m-%d").date()).days
            except Exception:
                continue
            if 0 < delta <= dc["dedup_window_days"]:
                out.update((entry or {}).get("topic_ids", []) or [])
        return out

    def art(a):
        return {
            "title": a["title"],
            "url": a["url"],
            "source": a["source"],
            "summary": (a.get("llm_summary") or a.get("summary") or "")[:240],
            "reason": a.get("llm_reason"),
            "density": a.get("density"),
            "score": a["score"],
            "role": role_tag(a["source"]),
            "published_at": a.get("published_at"),
            "topic_id": a.get("topic_id"),
            "topic_title": a.get("topic_title"),
        }

    out = {}
    for d, its in sorted(by_date.items()):
        ranked = sorted(its, key=lambda i: i["score"], reverse=True)
        covered = covered_topic_ids(d)

        def fresh(a):
            tid = a.get("topic_id")
            return not tid or tid not in covered

        # 正文：头条 + 看点，同一信源最多 max_per_source 条
        body, seen_src = [], {}
        for a in ranked:
            if not fresh(a):
                continue
            c = seen_src.get(a["source"], 0)
            if c >= dc["max_per_source"]:
                continue
            body.append(a)
            seen_src[a["source"]] = c + 1
            if len(body) >= dc["headline_count"] + dc["picks_count"]:
                break
        if not body:
            # 兜底：全是旧事件时仍出正文，避免空日报
            for a in ranked:
                c = seen_src.get(a["source"], 0)
                if c >= dc["max_per_source"]:
                    continue
                body.append(a)
                seen_src[a["source"]] = c + 1
                if len(body) >= dc["headline_count"] + dc["picks_count"]:
                    break
        headline = art(body[0]) if body else None
        picks = [art(a) for a in body[1:]]
        used_ids = {a["id"] for a in body}
        flash = [art(a) for a in ranked
                 if a["id"] not in used_ids and fresh(a)][:dc["flash_count"]]
        # 保留原有分类结构（兼容旧前端/归档浏览）
        sections = []
        for cat in CATEGORY_ORDER:
            arts = [i for i in its if i["category"] == cat][:dc["per_category_limit"]]
            if arts:
                sections.append({"category": cat, "articles": [art(a) for a in arts]})
        if not sections and not body:
            continue
        try:
            wd = WEEKDAYS_CN[datetime.strptime(d, "%Y-%m-%d").weekday()]
        except Exception:
            wd = ""
        body_chars = sum(len((x.get("summary") or "")) for x in ([headline] if headline else []) + picks)
        out[d] = {
            "date": d,
            "weekday": wd,
            "label": cn_date(d),
            "headline": headline,
            "picks": picks,
            "flash": flash,
            "sections": sections,
            "topic_ids": sorted({a.get("topic_id") for a in body if a.get("topic_id")}),
            "tocCount": len(body) + len(flash),
            "readMinutes": max(1, round(body_chars / 300)),
        }
    result = dict(existing or {})
    result.update(out)
    cutoff = (datetime.now(TZ_CN).date() - timedelta(days=365)).isoformat()
    return {k: v for k, v in result.items() if k >= cutoff}


# ---------------- HTML 报告（AIHOT 风格） ----------------
CAT_CLS = {
    "激光": "laser", "光通信": "fiber", "显示与面板": "display", "光电芯片与半导体": "chip",
    "光学元件与成像": "optics", "光传感与激光雷达": "sensing", "光伏与新能源": "pv",
    "科研进展": "research", "产业与资本": "capital", "通信与算力": "telecom", "其他": "other",
}

APP_CSS = r"""

:root{
  --bg:#eef0f6; --card:#ffffff; --line:#e2e7f1; --ink:#17233d; --muted:#64748b;
  --accent:#4f46e5; --accent-deep:#3730a3; --accent-soft:rgba(79,70,229,.09);
  --side:#0f172a; --side-ink:#c3cede; --side-dim:#7c8aa5;
  --gold:#b45309; --gold-bg:rgba(180,83,9,.1);
  --ok:#047857; --ok-bg:rgba(4,120,87,.1);
  --warn:#b45309; --warn-bg:rgba(180,83,9,.1);
  --bad:#9ca3af; --bad-bg:#f1f2f4;
  --radius:14px; --shadow:0 1px 2px rgba(23,35,61,.05),0 4px 14px rgba(23,35,61,.05);
}
*{margin:0;padding:0;box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{background:var(--bg);color:var(--ink);font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","HarmonyOS Sans SC","Microsoft YaHei",sans-serif;line-height:1.6}
a{color:inherit;text-decoration:none}
a:hover{color:var(--accent)}
.mono{font-variant-numeric:tabular-nums;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.shell{display:grid;grid-template-columns:232px 1fr;min-height:100vh}
/* ---- dark sidebar ---- */
.sidebar{background:var(--side);color:var(--side-ink);padding:20px 14px;position:sticky;top:0;height:100vh;display:flex;flex-direction:column;gap:6px}
.brand{display:flex;align-items:center;gap:10px;padding:4px 8px 16px;color:#fff}
.brand .mark{width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,#6366f1,#8b5cf6);display:flex;align-items:center;justify-content:center;font-weight:800;font-size:15px;color:#fff}
.brand .name{font-weight:700;font-size:16px;line-height:1.2}
.brand .name small{display:block;font-weight:400;font-size:11px;color:var(--side-dim)}
.nav-sec{font-size:11px;color:var(--side-dim);letter-spacing:1px;padding:10px 10px 4px}
.nav-link{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:10px;color:var(--side-ink);font-size:14px}
.nav-link .ic{width:18px;text-align:center}
.nav-link:hover{background:rgba(255,255,255,.06);color:#fff}
.nav-link.on{background:rgba(99,102,241,.22);color:#fff;font-weight:600}
.side-foot{margin-top:auto;font-size:11px;color:var(--side-dim);padding:8px 10px;line-height:1.7}
/* ---- main / topbar ---- */
.main{min-width:0;display:flex;flex-direction:column}
.topbar{position:sticky;top:0;z-index:40;background:rgba(255,255,255,.88);backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
.topbar-in{max-width:1060px;margin:0 auto;padding:10px 20px;display:flex;align-items:center;gap:12px}
.search{flex:1;display:flex;align-items:center;gap:8px;background:var(--bg);border:1px solid var(--line);border-radius:12px;padding:7px 13px}
.search input{flex:1;border:0;background:none;outline:0;font-size:14px;color:var(--ink)}
.btn{border:1px solid var(--line);background:var(--card);color:var(--accent);border-radius:10px;padding:6px 12px;font-size:13px;cursor:pointer;font-weight:600;white-space:nowrap}
.btn:hover{border-color:var(--accent)}
.gen{font-size:12px;color:var(--muted);white-space:nowrap}
.content{max-width:1060px;width:100%;margin:0 auto;padding:20px}
.view{display:none}.view.on{display:block;animation:fade .18s ease}
@keyframes fade{from{opacity:.4}to{opacity:1}}
.card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}
.ph{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:16px 20px;margin-bottom:16px}
.ph h1{font-size:19px;font-weight:750}
.ph .sub{font-size:12.5px;color:var(--muted)}
.ph .note{flex-basis:100%;font-size:12px;color:var(--muted);background:var(--accent-soft);border-radius:8px;padding:6px 10px}
/* ---- feed ---- */
.day{margin-bottom:22px}
.day-h{display:flex;align-items:baseline;gap:10px;padding:0 4px 10px}
.day-h h2{font-size:16px;font-weight:700}
.day-h .w{font-size:12.5px;color:var(--muted)}
.day-h .c{margin-left:auto;font-size:12px;color:var(--muted)}
.icard{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);padding:14px 18px;margin-bottom:12px}
.icard:hover{border-color:#c7cdfb}
.irow{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:7px}
.isrc{font-size:12.5px;font-weight:650}
.itime{font-size:12px;color:var(--muted)}
.iscore{margin-left:auto;font-size:14px;font-weight:750}
.s-hi{color:var(--accent-deep)}.s-mid{color:var(--gold)}.s-lo{color:#9aa3b2}
.bdg{font-size:11px;border-radius:7px;padding:1px 8px;white-space:nowrap;font-weight:600}
.b-cat{color:var(--accent-deep);background:var(--accent-soft)}
.b-pick{color:var(--gold);background:var(--gold-bg)}
.b-tier{color:var(--ok);background:var(--ok-bg)}
.b-dh{color:var(--ok);background:var(--ok-bg)}
.b-dm{color:var(--warn);background:var(--warn-bg)}
.b-dl{color:#6b7280;background:var(--bad-bg)}
.ititle{font-size:15px;font-weight:650;line-height:1.55}
.ireason{margin-top:6px;font-size:13px;color:var(--accent-deep);background:var(--accent-soft);border-radius:8px;padding:6px 10px}
.ireason b{font-weight:700}
.isum{margin-top:6px;font-size:13px;color:var(--muted)}
.iorig{margin-top:8px;display:inline-block;font-size:12px;color:var(--muted)}
/* ---- hot ---- */
.hrow{display:flex;gap:14px;align-items:flex-start;padding:15px 20px;border-top:1px solid var(--line)}
.hrow:first-child{border-top:0}
.hrank{font-family:ui-monospace,Menlo,monospace;font-size:19px;font-weight:800;color:#a3adbf;width:34px;text-align:center;padding-top:2px}
.hrow:nth-child(1) .hrank,.hrow:nth-child(2) .hrank,.hrow:nth-child(3) .hrank{color:var(--accent)}
.hmain{flex:1;min-width:0}
.htitle{font-size:15px;font-weight:700;line-height:1.5}
.hmeta{font-size:12px;color:var(--muted);margin-top:5px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.hbar{height:6px;background:var(--bg);border-radius:4px;margin-top:8px;overflow:hidden}
.hbar i{display:block;height:100%;background:linear-gradient(90deg,#818cf8,var(--accent));border-radius:4px}
.himg{width:100%;max-height:230px;object-fit:cover;border-radius:10px;margin-top:10px;border:1px solid var(--line)}
.hero .himg{max-height:260px}
.flag{font-size:11px;border-radius:7px;padding:1px 8px;font-weight:700}
.f-hot{color:#b91c1c;background:rgba(185,28,28,.1)}
.f-warm{color:var(--warn);background:var(--warn-bg)}
.f-watch{color:var(--muted);background:var(--bg)}
.fold{margin-top:9px;font-size:12.5px}
.fold summary{cursor:pointer;color:var(--accent);font-weight:600;list-style:none}
.fold summary::-webkit-details-marker{display:none}
.fold summary:before{content:"▸ ";font-size:11px}
.fold[open] summary:before{content:"▾ "}
.fold .fl{margin:7px 0 2px 14px;display:flex;flex-direction:column;gap:5px}
.fold .fl a{color:var(--muted)}
.fold .fl a:hover{color:var(--accent)}
.fold .fl .fs{color:#a3adbf;font-size:11.5px;margin-left:6px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.chip{font-size:11px;background:var(--bg);color:var(--muted);border-radius:20px;padding:2px 10px}
.chip.term{background:var(--accent-soft);color:var(--accent-deep)}
.hsort{margin-left:auto;display:inline-flex;gap:6px}
.hsort button{border:1px solid var(--line);background:var(--card);color:var(--muted);border-radius:9px;padding:3px 11px;font-size:12px;cursor:pointer}
.hsort button.on{color:#fff;background:var(--accent);border-color:var(--accent)}
/* ---- daily ---- */
.dshell{display:grid;grid-template-columns:200px 1fr;gap:16px;align-items:start}
.dside{position:sticky;top:76px}
.dside .card{padding:12px}
.dside h3{font-size:12px;color:var(--muted);margin-bottom:8px;font-weight:600}
.dday{display:flex;justify-content:space-between;font-size:12.5px;padding:6px 9px;border-radius:8px;cursor:pointer}
.dday:hover{background:var(--accent-soft)}
.dday.on{background:var(--accent-soft);color:var(--accent-deep);font-weight:700}
.dbody{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);padding:22px 24px}
.deye{font-size:11px;letter-spacing:3px;color:var(--muted)}
.dtitle{font-size:21px;font-weight:800;margin:3px 0 16px}
.hero{border:1.5px solid #c7cdfb;border-radius:12px;padding:16px 18px;margin-bottom:18px;background:linear-gradient(180deg,rgba(79,70,229,.06),rgba(79,70,229,.015))}
.hero .k{font-size:11px;font-weight:800;color:var(--accent);letter-spacing:2px}
.hero .t{font-size:17px;font-weight:750;margin:6px 0}
.hero .m{font-size:12px;color:var(--muted);display:flex;gap:10px;flex-wrap:wrap}
.dpicks{margin-bottom:18px}
.dpick{padding:12px 2px;border-top:1px solid var(--line)}
.dpick:first-child{border-top:0}
.dpick .t{font-size:14.5px;font-weight:650}
.dpick .m{font-size:12px;color:var(--muted);margin:4px 0;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.dsec-t{font-size:13px;font-weight:750;color:var(--accent-deep);margin:18px 0 6px;letter-spacing:1px}
.flash{list-style:none}
.flash li{font-size:13px;padding:7px 2px;border-top:1px dashed var(--line);display:flex;gap:8px}
.flash li:first-child{border-top:0}
.flash .dot{color:var(--accent);font-weight:800}
/* ---- topics / data ---- */
.tgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));gap:12px}
.tcard{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);padding:15px 17px;cursor:pointer}
.tcard:hover{border-color:var(--accent);transform:translateY(-1px)}
.tcard .n{font-weight:700;font-size:14.5px;display:flex;justify-content:space-between;align-items:center}
.tcard .nums{font-size:12px;color:var(--muted);margin-top:8px;display:flex;gap:14px}
.tcard .nums b{color:var(--accent-deep)}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);padding:15px 18px}
.stat .num{font-size:27px;font-weight:800;color:var(--accent-deep)}
.stat .lbl{font-size:12px;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-weight:600;font-size:12px}
.chart{display:flex;align-items:flex-end;gap:6px;height:110px;padding:10px 4px 0}
.bcol{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;gap:4px;height:100%}
.bcol .bar{width:66%;background:linear-gradient(180deg,#818cf8,var(--accent));border-radius:5px 5px 0 0;min-height:2px}
.bcol .dl{font-size:10px;color:var(--muted)}
.dlrow{display:flex;gap:10px;margin-top:14px;flex-wrap:wrap}
.empty{color:var(--muted);padding:28px;text-align:center;font-size:13px}
pre{background:#0f172a;color:#dbe4ff;border-radius:10px;padding:13px 15px;overflow-x:auto;font-size:12px;line-height:1.55}
.anote{font-size:12.5px;color:var(--muted);margin-top:8px}
footer{max-width:1060px;margin:0 auto;padding:12px 20px 32px;font-size:12px;color:var(--muted);text-align:center}
footer a{color:var(--accent);font-weight:600}
@media (max-width:920px){
  .shell{grid-template-columns:1fr}
  .sidebar{position:static;height:auto;flex-direction:row;align-items:center;overflow-x:auto;padding:10px 12px;gap:4px}
  .brand{padding:0 8px 0 0}.brand .name small{display:none}
  .nav-sec,.side-foot{display:none}
  .nav-link{white-space:nowrap;padding:7px 11px;font-size:13px}
  .dshell{grid-template-columns:1fr}
  .dside{position:static}
  .stats{grid-template-columns:1fr 1fr}
  .content{padding:14px}
  .topbar-in{flex-wrap:wrap}
  .gen{display:none}
  .search{order:3;flex-basis:100%}
}
"""

APP_JS = r"""
const S = __SNAPSHOT__;
const $ = (sel, root=document) => root.querySelector(sel);
const $$ = (sel, root=document) => [...root.querySelectorAll(sel)];
const esc = s => String(s==null?"":s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
const CAT_CLS = S.catCls || {};
const CAT_EN = {"激光":"Laser","光通信":"Optical Comm","显示与面板":"Display & Panel","光电芯片与半导体":"Opto Chip & Semi","光学元件与成像":"Optics & Imaging","光传感与激光雷达":"Sensing & LiDAR","光伏与新能源":"PV & Energy","科研进展":"Research","产业与资本":"Industry & Capital","通信与算力":"Telecom & Compute","其他":"Other"};
const STATUS_EN = {"爆":"Hot","发酵中":"Trending","关注中":"Watch"};
const DENS_EN = {"高":"High","中":"Medium","低":"Low"};
const I18N = {
  zh: { feed:"精选", all:"全部动态", hot:"热点榜", daily:"光电日报", topics:"主题", data:"数据", agent:"Agent 接入",
    search:"搜索光电资讯 / 公司 / 关键词…", catAll:"全部", sortScore:"按推荐分", sortTime:"按时间",
    feedSub:"按推荐分排序的光电行业时间线", thresholdNote:"精选门槛：官方信源 ≥ {o} 分 · 媒体信源 ≥ {m} 分（可在 collector/config.json 调整）",
    hotCard:"光电热点", hotMore:"完整榜单 →", daySel:"条精选", noMatch:"没有匹配的条目",
    hotPage:"光电热点榜", hotSub:"事件级热度：48 小时内每独立来源只计一次", heatVal:"热度", sources:"信源", signals:"信号",
    repMore:"另有 {n} 家信源报道", repOne:"1 家信源报道",
    dailyPage:"光电日报", dailySub:"自动生成 · 每日一篇（含历史归档）", toc:"今日看点", archive:"日报归档",
    headlineK:"头 条", picksK:"今日看点", flashK:"快 讯", moreK:"分栏目浏览",
    topicsPage:"主题", topicsSub:"光电行业分类统计，点击进入筛选",
    dataPage:"数据", dataSub:"统计与导出", total:"收录总数", h24:"24 小时新增", h7:"7 天新增", hotTopic:"热点话题", trend:"每日收录趋势（近 14 天）",
    srcTable:"数据来源", latest:"最新收录", dlCSV:"下载 CSV", dlItems:"查看 items.json", dlHot:"查看 hot-topics.json", dlDaily:"查看 dailies.json",
    agentPage:"Agent 接入", agentSub:"面向 AI / LLM / 智能体的数据接口（免鉴权，静态 JSON）", apiTitle:"数据 API（v1）",
    apiDesc:"数据每 6 小时自动更新，接口免鉴权，AI 智能体 / 脚本可直接消费。", endpoint:"接口", desc:"说明", open:"打开",
    curl:"用法示例（curl）", llmsNote:"站点根目录提供 llms.txt（LLM 友好入口），Agent 可先读取它再按需拉取接口。", base:"接口基地址（本页 URL 去掉 index.html）",
    reason:"推荐理由", density:"信息密度", official:"官方", pick:"精选",
    footer:"Opto-Hot · 光电行业热点统计（AIHOT 方法论）· 数据来自公开网络，仅供参考，不构成投资建议 · GitHub 开源" },
  en: { feed:"Selected", all:"All Items", hot:"Hot Topics", daily:"Daily Brief", topics:"Topics", data:"Data", agent:"Agent API",
    search:"Search optics / photonics news…", catAll:"All", sortScore:"By score", sortTime:"By time",
    feedSub:"Optoelectronics timeline ranked by score", thresholdNote:"Selection bar: official sources ≥ {o} · media sources ≥ {m} (tune in collector/config.json)",
    hotCard:"Hot Topics", hotMore:"Full ranking →", daySel:"selected", noMatch:"No matching items",
    hotPage:"Hot Ranking", hotSub:"Event-level heat: each independent source counts once per 48h", heatVal:"heat", sources:"sources", signals:"signals",
    repMore:"{n} more sources", repOne:"1 source",
    dailyPage:"Daily Brief", dailySub:"Auto-generated daily (with archive)", toc:"Today's picks", archive:"Archive",
    headlineK:"HEADLINE", picksK:"Today's picks", flashK:"Flash", moreK:"Browse by category",
    topicsPage:"Topics", topicsSub:"Category stats — click to filter",
    dataPage:"Data", dataSub:"Stats & export", total:"Total items", h24:"24h new", h7:"7d new", hotTopic:"Hot topics", trend:"Daily trend (14 days)",
    srcTable:"Sources", latest:"Latest", dlCSV:"Download CSV", dlItems:"items.json", dlHot:"hot-topics.json", dlDaily:"dailies.json",
    agentPage:"Agent API", agentSub:"Open JSON APIs for AI / LLM agents (no auth)", apiTitle:"Data API (v1)",
    apiDesc:"Data refreshes every 6h. Endpoints need no auth and are agent/script friendly.", endpoint:"Endpoint", desc:"Description", open:"Open",
    curl:"Examples (curl)", llmsNote:"llms.txt at site root is an LLM-friendly entry point.", base:"Base URL (this page URL minus index.html)",
    reason:"Why it matters", density:"Info density", official:"Official", pick:"Pick",
    footer:"Opto-Hot · optoelectronics hot-topic stats (AIHOT methodology) · public data, for reference only · open source on GitHub" }
};
let LANG = localStorage.getItem("opto-lang") || "zh";
const T = I18N[LANG];
const state = { q:"", cat:"全部", sort:"score", dailyDate:"", hotSort:"heat" };
function tr(){ $$("[data-i18n]").forEach(el=>{ const k=el.dataset.i18n; if(T[k]) el.textContent = T[k]; }); $("#lang").textContent = LANG==="zh"?"EN":"中"; $("#q").placeholder = T.search; }
function fmtRel(iso){ if(!iso) return ""; const t=new Date(iso); const d=(Date.now()-t.getTime())/1000; if(d<60) return "刚刚"; if(d<3600) return Math.floor(d/60)+" 分钟前"; if(d<86400) return Math.floor(d/3600)+" 小时前"; return Math.floor(d/86400)+" 天前"; }
function effDate(it){ const p=it.published_at; if(p&&p.length>=10) return p.slice(0,10); const d=new Date(it.discovered_at); return new Date(d.getTime()+8*3600*1000).toISOString().slice(0,10); }
function fmtDay(dstr){ const parts=dstr.split("-"); if(LANG==="en") return dstr; return parts[0]+"年"+Number(parts[1])+"月"+Number(parts[2])+"日"; }
function wdCN(dstr){ const w=["周日","周一","周二","周三","周四","周五","周六"][new Date(dstr+"T00:00:00+08:00").getDay()]; return LANG==="en"?["Sun","Mon","Tue","Wed","Thu","Fri","Sat"][new Date(dstr+"T00:00:00+08:00").getDay()]:w; }
function todayCN(){ return new Date(Date.now()+8*3600*1000).toISOString().slice(0,10); }
function isToday(d){ return d===todayCN(); }
function scoreCls(s){ return s>=75?"s-hi":(s>=50?"s-mid":"s-lo"); }
function pubLabel(it){ if(it.published_at){ const p=it.published_at; if(p.length===7) return p+"（月级）发布"; if(p.length===10) return p+" 发布"; return p.replace("T"," ").slice(5,16)+" 发布"; } return "收录 "+fmtRel(it.discovered_at); }
function catName(c){ return LANG==="en" ? (CAT_EN[c]||c) : c; }
function statusName(s){ return LANG==="en" ? (STATUS_EN[s]||s) : s; }
function densName(d){ return LANG==="en" ? (DENS_EN[d]||d) : d; }
function catBadge(c){ return '<span class="bdg b-cat">'+esc(catName(c))+'</span>'; }
function pickBadge(){ return '<span class="bdg b-pick">'+T.pick+'</span>'; }
function tierBadge(t){ return t==="official"?'<span class="bdg b-tier">'+T.official+'</span>':""; }
function densBadge(d){ if(!d) return ""; const cls=d==="高"?"b-dh":(d==="中"?"b-dm":"b-dl"); return '<span class="bdg '+cls+'" title="'+T.density+'">'+esc(densName(d))+'</span>'; }
function scoreEl(it){ return '<span class="iscore mono '+scoreCls(it.score)+'" title="score / 100">'+Math.round(it.score)+'</span>'; }
function summaryOf(it){ return it.llm_summary || it.summary || ""; }
function itemCard(it){
  const reason = it.llm_reason ? '<div class="ireason"><b>'+T.reason+'：</b>'+esc(it.llm_reason)+'</div>' : "";
  const sum = summaryOf(it);
  return '<article class="icard"><div class="irow">'+catBadge(it.category)+tierBadge(it.tier)+'<span class="isrc">'+esc(it.source)+'</span><span class="itime">'+esc(pubLabel(it))+'</span>'+(it.selected?pickBadge():"")+densBadge(it.density)+scoreEl(it)+'</div>'
    +'<div class="ititle"><a href="'+esc(it.url)+'" target="_blank" rel="noopener">'+esc(it.title)+'</a></div>'
    +reason+(sum?'<div class="isum">'+esc(sum)+'</div>':"")
    +'<a class="iorig" href="'+esc(it.url)+'" target="_blank" rel="noopener">↗ source</a></article>';
}
function threshNote(){ const th=S.thresholds||{official:55,media:65}; return T.thresholdNote.replace("{o}",th.official).replace("{m}",th.media); }
const renderers = {};
function router(){ const h=(location.hash||"#/").replace("#",""); const name=h.split("?")[0]||"/"; const map={"/":"feed","/all":"all","/hot":"hot","/daily":"daily","/topics":"topics","/data":"data","/agent":"agent"}; const v=map[name]||"feed"; $$(".nav-link").forEach(a=>a.classList.toggle("on", a.getAttribute("href")===("#"+name))); $$(".view").forEach(x=>x.classList.remove("on")); $("#view-"+v).classList.add("on"); (renderers[v]||renderers.feed)(); window.scrollTo(0,0); }
function renderFeed(){
  const root=$("#view-feed");
  const top=(S.topics||[]).slice(0,5);
  let hot='<div class="card ph" style="margin-bottom:16px"><h1>'+T.hotCard+'</h1><span class="sub"></span><a class="btn" style="margin-left:auto" href="#/hot">'+T.hotMore+'</a></div>';
  hot+='<div style="margin-bottom:20px">'+top.map((t,i)=>'<div class="icard" style="margin-bottom:8px"><div class="irow"><span class="mono" style="font-weight:800;color:var(--accent)">'+(i+1)+'</span><span class="isrc">'+esc((t.sources||[])[0]||"")+'</span><span class="itime">'+t.source_count+' '+T.sources+' · '+Math.round(t.heat||t.score)+' '+T.heatVal+'</span></div><div class="ititle"><a href="'+esc((t.representative||{}).url||"#/hot")+'" target="_blank" rel="noopener">'+esc(t.title)+'</a></div></div>').join("")+'</div>';
  const groups={}; for(const it of S.items){ const d=effDate(it); (groups[d]=groups[d]||[]).push(it); }
  const days=Object.keys(groups).sort().reverse().slice(0,7);
  let tl="";
  for(const d of days){ const its=groups[d].slice().sort((a,b)=>b.score-a.score).slice(0,20);
    tl+='<div class="day"><div class="day-h"><h2>'+(isToday(d)?"今天 "+fmtDay(d):fmtDay(d))+'</h2><span class="w">'+wdCN(d)+'</span><span class="c">'+its.length+' '+T.daySel+'</span></div>'+its.map(itemCard).join("")+'</div>'; }
  root.innerHTML='<div class="card ph"><h1>'+T.feed+'</h1><span class="sub">'+T.feedSub+'</span><div class="note">'+esc(threshNote())+'</div></div>'+hot+tl;
}
function renderAll(){
  const root=$("#view-all"); let its=S.items.slice();
  if(state.q){ const q=state.q.toLowerCase(); its=its.filter(i=>(i.title+" "+(i.llm_summary||i.summary||"")+" "+i.source).toLowerCase().includes(q)); }
  if(state.cat!=="全部") its=its.filter(i=>i.category===state.cat);
  if(state.sort==="score") its.sort((a,b)=>b.score-a.score); else its.sort((a,b)=>b.discovered_at.localeCompare(a.discovered_at));
  root.innerHTML='<div class="card ph"><h1>'+T.all+'</h1><span class="sub">'+its.length+'</span><span class="hsort" style="margin-left:auto"><select id="all-cat" class="btn"><option value="全部">'+T.catAll+'</option></select><select id="all-sort" class="btn"><option value="score">'+T.sortScore+'</option><option value="time">'+T.sortTime+'</option></select></span><div class="note">'+esc(threshNote())+'</div></div><div id="all-list">'+(its.length?its.map(itemCard).join(""):'<div class="empty">'+T.noMatch+'</div>')+'</div>';
  const cats=[...new Set(S.items.map(i=>i.category))];
  const sel=$("#all-cat"); for(const c of cats){ const o=document.createElement("option"); o.value=c; o.textContent=catName(c); if(c===state.cat) o.selected=true; sel.appendChild(o); }
  $("#all-sort").value=state.sort;
  sel.onchange=e=>{ state.cat=e.target.value; renderAll(); };
  $("#all-sort").onchange=e=>{ state.sort=e.target.value; renderAll(); };
}
function renderHot(){
  const root=$("#view-hot"); let ts=(S.topics||[]).slice();
  if(state.hotSort==="sources") ts.sort((a,b)=>b.source_count-a.source_count);
  const maxHeat=Math.max(...ts.map(t=>t.heat||t.score||0),1);
  const head='<div class="card ph"><h1>'+T.hotPage+'</h1><span class="sub">'+T.hotSub+'</span><span class="hsort"><button data-hs="heat" class="'+(state.hotSort==="heat"?"on":"")+'">'+T.heatVal+'</button><button data-hs="sources" class="'+(state.hotSort==="sources"?"on":"")+'">'+T.sources+'</button></span></div>';
  root.innerHTML=head+'<div class="card">'+ts.map((t,i)=>{
    const s=t.status; const flag=s==="爆"?'<span class="flag f-hot">'+statusName(s)+'</span>':(s==="发酵中"?'<span class="flag f-warm">'+statusName(s)+'</span>':'<span class="flag f-watch">'+statusName(s)+'</span>');
    const rep=t.representative||{}; const rurl=rep.url||((t.links||[])[0]||{}).url||"";
    const reason=rep.llm_reason?'<div class="ireason"><b>'+T.reason+'：</b>'+esc(rep.llm_reason)+'</div>':"";
    const rsum=rep.llm_summary||rep.summary;
    const chips=((t.top_terms||[]).map(x=>'<span class="chip term">'+esc(x)+'</span>').join(""))+((t.sources||[]).map(x=>'<span class="chip">'+esc(x)+'</span>').join(""));
    const flinks=(t.links||[]).map(l=>'<a href="'+esc(l.url)+'" target="_blank" rel="noopener">'+esc(l.title)+'<span class="fs">'+esc(l.source)+'</span></a>').join("");
    const fold=(t.folded_count>0&&flinks)?'<details class="fold"><summary>'+T.repMore.replace("{n}",t.folded_count)+'</summary><div class="fl">'+flinks+'</div></details>':"";
    const bar='<div class="hbar"><i style="width:'+Math.max(4,Math.round((t.heat||t.score)/maxHeat*100))+'%"></i></div>';
    return '<div class="hrow"><div class="hrank">'+(i+1)+'</div><div class="hmain"><div class="htitle"><a href="'+esc(rurl)+'" target="_blank" rel="noopener">'+esc(t.title)+'</a> '+flag+'</div>'
      +'<div class="hmeta"><span>'+esc(rep.source||((t.sources||[])[0]||""))+'</span><span>'+fmtRel(t.latest_at)+'</span><span>'+t.source_count+' '+T.sources+' · '+t.signal_count+' '+T.signals+'</span><span class="mono" style="font-weight:700;color:var(--accent-deep)">'+Math.round(t.heat||t.score)+'</span></div>'
      +reason+(t.image?'<img class="himg" src="'+esc(t.image)+'" alt="" loading="lazy">':"")+(rsum?'<div class="isum">'+esc(rsum)+'</div>':"")+bar+'<div class="chips">'+chips+'</div>'+fold+'</div></div>';
  }).join("")+'</div>';
}
function dailyArticle(a, big){
  const reason=a.reason?'<div class="ireason"><b>'+T.reason+'：</b>'+esc(a.reason)+'</div>':"";
  return '<div class="'+(big?"dpick":"dpick")+'"><div class="t"><a href="'+esc(a.url)+'" target="_blank" rel="noopener">'+esc(a.title)+'</a></div>'
    +'<div class="m"><span>'+esc(a.source)+'</span><span>'+esc(pubLabel(a))+'</span>'+densBadge(a.density)+'</div>'+reason+(a.summary?'<div class="isum">'+esc(a.summary)+'</div>':"")+'</div>';
}
function renderDaily(){
  const root=$("#view-daily"); const dates=Object.keys(S.dailies||{}).sort().reverse();
  const d=state.dailyDate&&S.dailies[state.dailyDate]?state.dailyDate:(dates[0]||todayCN()); state.dailyDate=d;
  const rep=S.dailies[d];
  let side='<aside class="dside"><div class="card"><h3>'+T.archive+'（'+dates.length+'）</h3>';
  let cm=""; for(const x of dates){ const m=x.slice(0,7); if(m!==cm){ cm=m; side+='<div class="anote" style="margin:6px 2px 2px">'+m+'</div>'; } side+='<div class="dday'+(x===d?" on":"")+'" data-d="'+x+'"><span>'+x.slice(5)+'</span><span>'+wdCN(x)+'</span></div>'; }
  side+='</div></aside>';
  let body='<div class="dbody">';
  if(rep){
    body+='<div class="deye">OPTOHOT DAILY</div><div class="dtitle">'+esc(rep.label)+' · '+esc(rep.weekday)+'</div>';
    const hl=rep.headline||(((rep.sections||[])[0]||{}).articles||[])[0];
    if(hl){ body+='<div class="hero"><div class="k">'+T.headlineK+'</div><div class="t"><a href="'+esc(hl.url)+'" target="_blank" rel="noopener">'+esc(hl.title)+'</a></div><div class="m"><span>'+esc(hl.source)+'</span><span>'+esc(pubLabel(hl))+'</span>'+densBadge(hl.density)+'</div>'+(hl.image?'<img class="himg" src="'+esc(hl.image)+'" alt="" loading="lazy">':"")+(hl.reason?'<div class="ireason"><b>'+T.reason+'：</b>'+esc(hl.reason)+'</div>':"")+(hl.summary?'<div class="isum">'+esc(hl.summary)+'</div>':"")+'</div>'; }
    const picks=rep.picks||[];
    if(picks.length){ body+='<div class="dsec-t">'+T.picksK+'</div><div class="dpicks">'+picks.map(a=>dailyArticle(a)).join("")+'</div>'; }
    const flash=rep.flash||[];
    if(flash.length){ body+='<div class="dsec-t">'+T.flashK+'</div><ul class="flash">'+flash.map(a=>'<li><span class="dot">•</span><span><a href="'+esc(a.url)+'" target="_blank" rel="noopener">'+esc(a.title)+'</a> <span style="color:var(--muted);font-size:12px">'+esc(a.source)+'</span></span></li>').join("")+'</ul>'; }
    const secs=(rep.sections||[]).filter(s=>s.articles&&s.articles.length);
    if(secs.length){ body+='<div class="dsec-t">'+T.moreK+'</div>'+secs.map(s=>'<div class="dpick"><div class="t" style="font-size:13.5px;color:var(--accent-deep)">'+esc(catName(s.category))+' · '+s.articles.length+'</div>'+s.articles.slice(0,5).map(a=>'<div style="font-size:13px;padding:3px 0"><a href="'+esc(a.url)+'" target="_blank" rel="noopener">'+esc(a.title)+'</a></div>').join("")+'</div>').join(""); }
  } else { body+='<div class="empty">-</div>'; }
  body+='</div>';
  root.innerHTML='<div class="card ph"><h1>'+T.dailyPage+'</h1><span class="sub">'+T.dailySub+'</span></div><div class="dshell">'+side+body+'</div>';
  $$(".dday", root).forEach(el=>el.onclick=()=>{ state.dailyDate=el.dataset.d; renderDaily(); });
}
function renderTopics(){
  const root=$("#view-topics"); const rows=(S.daily&&S.daily.byCategory)||[];
  root.innerHTML='<div class="card ph"><h1>'+T.topicsPage+'</h1><span class="sub">'+T.topicsSub+'</span></div><div class="tgrid">'+rows.map(r=>'<div class="tcard" data-cat="'+esc(r.category)+'"><div class="n">'+esc(catName(r.category))+'<span class="bdg b-cat">'+r.total+'</span></div><div class="nums"><span>24h <b>'+r.last24h+'</b></span><span>7d <b>'+r.last7d+'</b></span></div></div>').join("")+'</div>';
  $$(".tcard", root).forEach(el=>el.onclick=()=>{ state.cat=el.dataset.cat; location.hash="#/all"; });
}
function renderData(){
  const root=$("#view-data"); const dl=S.daily||{byDay:[],bySource:[]};
  const maxDay=Math.max(...dl.byDay.map(x=>x.count),1);
  const chart='<div class="chart">'+dl.byDay.map(x=>'<div class="bcol"><div class="bar" title="'+x.date+': '+x.count+'" style="height:'+Math.max(2,x.count/maxDay*100).toFixed(1)+'%"></div><span class="dl">'+x.date.slice(5)+'</span></div>').join("")+'</div>';
  const rows=(dl.bySource||[]).map(s=>'<tr><td>'+esc(s.source)+'</td><td>'+s.count+'</td><td>'+fmtRel(s.latestAt)+'</td></tr>').join("");
  root.innerHTML='<div class="card ph"><h1>'+T.dataPage+'</h1><span class="sub">'+T.dataSub+'</span></div>'
    +'<div class="stats"><div class="stat"><div class="num">'+dl.total+'</div><div class="lbl">'+T.total+'</div></div><div class="stat"><div class="num">'+dl.last24h+'</div><div class="lbl">'+T.h24+'</div></div><div class="stat"><div class="num">'+dl.last7d+'</div><div class="lbl">'+T.h7+'</div></div><div class="stat"><div class="num">'+dl.topicCount+'</div><div class="lbl">'+T.hotTopic+'</div></div></div>'
    +'<div class="card" style="padding:16px 18px"><h3 style="font-size:14px;margin-bottom:6px">'+T.trend+'</h3>'+chart+'</div>'
    +'<div class="card" style="padding:16px 18px;margin-top:14px"><h3 style="font-size:14px;margin-bottom:6px">'+T.srcTable+'</h3><table><thead><tr><th>'+T.srcTable+'</th><th>'+T.total+'</th><th>'+T.latest+'</th></tr></thead><tbody>'+rows+'</tbody></table></div>'
    +'<div class="dlrow"><a class="btn" href="data/report.csv" download>'+T.dlCSV+'</a><a class="btn" href="data/items.json" target="_blank">'+T.dlItems+'</a><a class="btn" href="data/hot-topics.json" target="_blank">'+T.dlHot+'</a><a class="btn" href="data/dailies.json" target="_blank">'+T.dlDaily+'</a></div>';
}
function renderAgent(){
  const root=$("#view-agent");
  const base=location.href.split("?")[0].split("#")[0].replace(/index\.html$/,"");
  const eps=[["items",T.dlItems],["hot-topics",T.dlHot],["dailies",T.dlDaily],["daily","daily.json"],["stories","stories.json"],["biz","政策/招投标库"]];
  const rows=eps.map(([k,d])=>'<tr><td class="mono">api/v1/'+k+'.json</td><td>'+d+'</td><td><a href="'+base+'api/v1/'+k+'.json" target="_blank" rel="noopener">'+T.open+' ↗</a></td></tr>').join("");
  const curl=eps.map(([k])=>'curl '+base+'api/v1/'+k+'.json').join("\n");
  const feeds=["feed.xml","category/laser.xml","category/fiber.xml","category/display.xml","category/chip.xml","category/optics.xml","category/sensing.xml","category/pv.xml","category/research.xml","category/capital.xml","category/telecom.xml","category/other.xml"];
  const feedRows=feeds.map((f,idx)=>'<tr><td class="mono">feed/'+f+'</td><td>'+(idx===0?'RSS 全部':'分类 RSS')+'</td><td><a href="'+base+'feed/'+f+'" target="_blank" rel="noopener">'+T.open+' ↗</a></td></tr>').join("");
  const moreRows='<tr><td class="mono">api/v1/openapi.json</td><td>OpenAPI 3.1</td><td><a href="'+base+'api/v1/openapi.json" target="_blank" rel="noopener">'+T.open+' ↗</a></td></tr><tr><td class="mono">llms.txt</td><td>LLM 友好入口</td><td><a href="'+base+'llms.txt" target="_blank" rel="noopener">'+T.open+' ↗</a></td></tr>';
  root.innerHTML='<div class="card ph"><h1>'+T.agentPage+'</h1><span class="sub">'+T.agentSub+'</span></div>'
    +'<div class="card" style="padding:16px 18px"><h3 style="font-size:15px;margin-bottom:4px">🤖 '+T.apiTitle+'</h3><p class="anote">'+T.apiDesc+'</p><p class="anote">'+T.base+'：<span class="mono">'+esc(base)+'</span></p><table style="margin-top:10px"><thead><tr><th>'+T.endpoint+'</th><th>'+T.desc+'</th><th></th></tr></thead><tbody>'+rows+moreRows+'</tbody></table></div>'
    +'<div class="card" style="padding:16px 18px;margin-top:14px"><h3 style="font-size:15px;margin-bottom:4px">RSS</h3><table style="margin-top:8px"><tbody>'+feedRows+'</tbody></table></div>'
    +'<div class="card" style="padding:16px 18px;margin-top:14px"><h3 style="font-size:15px;margin-bottom:4px">'+T.curl+'</h3><pre>'+esc(curl)+'</pre><p class="anote">'+T.llmsNote+'</p><p class="anote">Agent Skill：仓库 <span class="mono">agent/skills/opto-hot</span></p></div>';
}
renderers.feed=renderFeed; renderers.all=renderAll; renderers.hot=renderHot; renderers.daily=renderDaily; renderers.topics=renderTopics; renderers.data=renderData; renderers.agent=renderAgent;
function bind(){ $("#q").addEventListener("input",e=>{ state.q=e.target.value; if(location.hash==="#/all") renderAll(); }); $("#lang").onclick=()=>{ LANG = LANG==="zh"?"en":"zh"; localStorage.setItem("opto-lang", LANG); location.reload(); }; window.addEventListener("hashchange",router); document.addEventListener("keydown",e=>{ if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==="k"){ e.preventDefault(); $("#q").focus(); } }); tr(); router(); }
document.addEventListener("DOMContentLoaded", bind);
"""

APP_HTML = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Opto-Hot · 光电行业热点统计</title>
<style>/*__CSS__*/</style>
</head>
<body>
<div class="shell">
  <aside class="sidebar">
    <a class="brand" href="#/"><span class="mark">OH</span><span class="name">Opto-Hot<small>光电行业热点统计</small></span></a>
    <div class="nav-sec">内容</div>
    <a class="nav-link" href="#/"><span class="ic">✦</span><span data-i18n="feed">精选</span></a>
    <a class="nav-link" href="#/all"><span class="ic">☰</span><span data-i18n="all">全部动态</span></a>
    <a class="nav-link" href="#/hot"><span class="ic">🔥</span><span data-i18n="hot">热点榜</span></a>
    <a class="nav-link" href="#/daily"><span class="ic">📰</span><span data-i18n="daily">光电日报</span></a>
    <a class="nav-link" href="#/topics"><span class="ic">◈</span><span data-i18n="topics">主题</span></a>
    <a class="nav-link" href="#/data"><span class="ic">◉</span><span data-i18n="data">数据</span></a>
    <div class="nav-sec">工具</div>
    <a class="nav-link" href="#/agent"><span class="ic">🤖</span><span data-i18n="agent">Agent 接入</span></a>
    <div class="side-foot">AIHOT 方法论 · 零依赖采集<br>数据来自公开网络，仅供参考</div>
  </aside>
  <div class="main">
    <header class="topbar"><div class="topbar-in">
      <label class="search"><input id="q" type="search" placeholder="搜索光电资讯 / 公司 / 关键词…" autocomplete="off"></label>
      <button id="lang" class="btn" title="切换语言 / Language">EN</button>
      <span class="gen">生成于 __GEN__ · 北京时间</span>
    </div></header>
    <div class="content">
      <section id="view-feed" class="view"></section>
      <section id="view-all" class="view"></section>
      <section id="view-hot" class="view"></section>
      <section id="view-daily" class="view"></section>
      <section id="view-topics" class="view"></section>
      <section id="view-data" class="view"></section>
      <section id="view-agent" class="view"></section>
    </div>
    <footer><span data-i18n="footer">Opto-Hot · 光电行业热点统计（AIHOT 方法论）· 数据来自公开网络，仅供参考，不构成投资建议</span> · <a href="https://github.com/sun-zihang/opto-hot" target="_blank" rel="noopener">github.com/sun-zihang/opto-hot</a></footer>
  </div>
</div>
<script>
/*__JS__*/
</script>
</body>
</html>
"""


def fmt_dt(iso):
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ_CN).strftime("%m-%d %H:%M")
    except Exception:
        return iso


def pub_label(it):
    if it.get("published_at"):
        p = it["published_at"]
        if len(p) == 7:
            return p + "（月级）发布"
        if len(p) == 10:
            return p + " 发布"
        return p.replace("T", " ")[:16] + " 发布"
    return "收录 " + fmt_dt(it["discovered_at"])


def render_app_html(items, topics, daily, dailies, generated):
    import json as _json
    snapshot = {
        "generatedAt": generated.isoformat(),
        "catCls": CAT_CLS,
        "items": items,
        "topics": topics,
        "daily": daily,
        "dailies": dailies,
        "thresholds": {k: v["select_threshold"] for k, v in CONFIG["tiers"].items()
                       if isinstance(v, dict) and "select_threshold" in v},
    }
    snap_json = _json.dumps(snapshot, ensure_ascii=False)
    snap_json = snap_json.replace("</", "<\\/")
    html = APP_HTML.replace("/*__CSS__*/", APP_CSS).replace("/*__JS__*/", APP_JS)
    html = html.replace("__SNAPSHOT__", snap_json)
    html = html.replace("__GEN__", generated.astimezone(TZ_CN).strftime("%Y-%m-%d %H:%M"))
    return html

# ---------------- 输出 ----------------
def build_rss(items, title, link, description, limit=50):
    import xml.sax.saxutils as su
    its = sorted(items, key=lambda it: it["discovered_at"], reverse=True)[:limit]
    pub = max(it["discovered_at"] for it in its) if its else now_utc().isoformat()
    out = []
    for it in its:
        out.append(
            "<item><title>%s</title><link>%s</link><description>%s</description>"
            "<guid isPermaLink=\"false\">%s</guid><pubDate>%s</pubDate>"
            "<source>%s</source><category>%s</category></item>"
            % (su.escape(it["title"]), su.escape(it["url"]), su.escape((it.get("summary") or "")[:500]),
               it["id"], it["discovered_at"], su.escape(it["source"]), su.escape(it["category"])))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
            "<title>%s</title><link>%s</link><description>%s</description>"
            "<lastBuildDate>%s</lastBuildDate>%s</channel></rss>"
            % (su.escape(title), su.escape(link), su.escape(description), pub, "".join(out)))


def build_openapi(generated):
    def ep(summary):
        return {"get": {"summary": summary, "responses": {"200": {"description": "OK"}}}}
    return {
        "openapi": "3.1.0",
        "info": {"title": "Opto-Hot API v1", "version": "1.0.0",
                 "description": "光电行业热点统计静态 JSON 接口（免鉴权，每 6 小时更新，AI/Agent 可直接消费）。"},
        "servers": [{"url": ""}],
        "paths": {
            "/api/v1/index.json": ep("接口索引"),
            "/api/v1/items.json": ep("全部条目"),
            "/api/v1/hot-topics.json": ep("热点榜"),
            "/api/v1/dailies.json": ep("光电日报（按日期归档）"),
            "/api/v1/daily.json": ep("统计聚合"),
            "/api/v1/stories.json": ep("事件故事（多源聚合）"),
            "/feed.xml": ep("RSS（最新 50 条）"),
            "/feed/category/{slug}.xml": ep("分类 RSS（slug: laser/fiber/display/chip/optics/sensing/pv/research/capital/telecom/other）"),
        },
    }


def write_outputs(items, topics, daily, dailies, generated):
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(DIST_DIR, exist_ok=True)

    def dump(obj, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

    tiers = CONFIG["tiers"]
    hc = CONFIG["heat"]

    def _tier_of(it):
        return _SOURCE_TIER.get(it.get("source_base") or it["source"]) or tiers.get("default", "media")

    def _threshold(it):
        return tiers.get(_tier_of(it), tiers["media"])["select_threshold"]

    for it in items:
        it.setdefault("links", {})
        it["links"]["original"] = it["url"]
        it["tier"] = _tier_of(it)
        it["selected"] = it["score"] >= _threshold(it)
        it["role"] = role_tag(it["source"])
    for t in topics:
        t["heat"] = t["score"]
        if t["source_count"] >= hc["status_hot_min_sources"] and t["score"] >= hc["status_hot_min_heat"]:
            t["status"] = "爆"
        elif t["source_count"] >= hc["status_trending_min_sources"]:
            t["status"] = "发酵中"
        else:
            t["status"] = "关注中"

    dump({"schemaVersion": 1, "generatedAt": generated.isoformat(),
          "count": len(items), "items": items}, os.path.join(DATA_DIR, "items.json"))
    dump({"schemaVersion": 1, "generatedAt": generated.isoformat(),
          "count": len(topics), "items": topics}, os.path.join(DATA_DIR, "hot-topics.json"))
    dump(daily, os.path.join(DATA_DIR, "daily.json"))
    dump({"schemaVersion": 1, "generatedAt": generated.isoformat(),
          "count": len(dailies), "dailies": dailies}, os.path.join(DATA_DIR, "dailies.json"))

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "title", "category", "source", "published_at", "discovered_at",
                "score", "url", "role", "selected"])
    for it in items:
        w.writerow([it["id"], it["title"], it["category"], it["source"],
                    it.get("published_at") or "", it["discovered_at"], it["score"], it["url"],
                    it["role"], it["selected"]])
    with open(os.path.join(DATA_DIR, "report.csv"), "w", encoding="utf-8-sig", newline="") as f:
        f.write(buf.getvalue())

    with open(os.path.join(DIST_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_app_html(items, topics, daily, dailies, generated))

    # ---- 静态托管副本（GitHub Pages / CloudBase 均从 dist 发布） ----
    import shutil
    dist_data = os.path.join(DIST_DIR, "data")
    os.makedirs(dist_data, exist_ok=True)
    for fn in ("items.json", "hot-topics.json", "daily.json", "dailies.json", "report.csv"):
        shutil.copyfile(os.path.join(DATA_DIR, fn), os.path.join(dist_data, fn))

    # ---- Agent / API 接口（静态 JSON，v1） ----
    api_dir = os.path.join(DIST_DIR, "api", "v1")
    os.makedirs(api_dir, exist_ok=True)
    stories = []
    for t in topics:
        stories.append({
            "id": t["id"],
            "title": t["title"],
            "status": t.get("status"),
            "heat": t.get("heat", t.get("score")),
            "sourceCount": t["source_count"],
            "signalCount": t["signal_count"],
            "latestAt": t["latest_at"],
            "sources": t.get("sources", []),
            "links": t.get("links", []),
        })
    dump({"schemaVersion": 1, "generatedAt": generated.isoformat(),
          "count": len(items), "items": items}, os.path.join(api_dir, "items.json"))
    dump({"schemaVersion": 1, "generatedAt": generated.isoformat(),
          "count": len(topics), "items": topics}, os.path.join(api_dir, "hot-topics.json"))
    dump(dailies, os.path.join(api_dir, "dailies.json"))
    dump(daily, os.path.join(api_dir, "daily.json"))
    dump({"schemaVersion": 1, "generatedAt": generated.isoformat(),
          "count": len(stories), "items": stories}, os.path.join(api_dir, "stories.json"))
    dump({
        "name": "Opto-Hot API v1",
        "description": "光电行业热点统计静态 JSON 接口（免鉴权，每 6 小时更新）",
        "endpoints": {
            "items": "api/v1/items.json",
            "hot-topics": "api/v1/hot-topics.json",
            "dailies": "api/v1/dailies.json",
            "daily": "api/v1/daily.json",
            "stories": "api/v1/stories.json",
        },
    }, os.path.join(api_dir, "index.json"))

    # ---- RSS 分类 feed + OpenAPI ----
    feed_dir = os.path.join(DIST_DIR, "feed", "category")
    os.makedirs(feed_dir, exist_ok=True)
    site_link = "https://opto-hot-a455-d3g2s3dt865d86640.webapps.tcloudbase.com"
    with open(os.path.join(DIST_DIR, "feed.xml"), "w", encoding="utf-8") as f:
        f.write(build_rss(items, "Opto-Hot 光电热点", site_link + "/", "光电行业热点统计（AIHOT 模式）", 50))
    by_cat = {}
    for it in items:
        by_cat.setdefault(it["category"], []).append(it)
    for cat, its in by_cat.items():
        slug = CAT_CLS.get(cat, "other")
        with open(os.path.join(feed_dir, slug + ".xml"), "w", encoding="utf-8") as f:
            f.write(build_rss(its, "Opto-Hot · %s" % cat, site_link + "/#/all", cat, 30))
    with open(os.path.join(api_dir, "openapi.json"), "w", encoding="utf-8") as f:
        json.dump(build_openapi(generated), f, ensure_ascii=False, indent=2)

    # ---- 政策/招投标结构化库 ----
    biz_items = [it for it in items if it["source"] in BIZ_SOURCES]
    biz_rows = [{
        "source": it["source"], "title": it["title"], "url": it["url"],
        "category": it["category"], "published_at": it.get("published_at"),
        "discovered_at": it["discovered_at"],
        "project_no": (it.get("biz") or {}).get("project_no"),
        "budget": (it.get("biz") or {}).get("budget"),
        "deadline": (it.get("biz") or {}).get("deadline"),
    } for it in biz_items]
    biz_doc = {"schemaVersion": 1, "generatedAt": generated.isoformat(),
               "count": len(biz_rows),
               "fields": ["project_no", "budget", "deadline"], "items": biz_rows}
    dump(biz_doc, os.path.join(DATA_DIR, "biz.json"))
    shutil.copyfile(os.path.join(DATA_DIR, "biz.json"), os.path.join(dist_data, "biz.json"))
    dump(biz_doc, os.path.join(api_dir, "biz.json"))
    bbuf = io.StringIO()
    bw = csv.writer(bbuf)
    bw.writerow(["source", "title", "category", "url", "published_at", "discovered_at",
                 "project_no", "budget", "deadline"])
    for r in biz_rows:
        bw.writerow([r["source"], r["title"], r["category"], r["url"],
                     r.get("published_at") or "", r["discovered_at"],
                     r.get("project_no") or "", r.get("budget") or "", r.get("deadline") or ""])
    with open(os.path.join(DATA_DIR, "biz.csv"), "w", encoding="utf-8-sig", newline="") as f:
        f.write(bbuf.getvalue())
    shutil.copyfile(os.path.join(DATA_DIR, "biz.csv"), os.path.join(dist_data, "biz.csv"))

    # ---- llms.txt（LLM / Agent 友好入口） ----
    llms = """# Opto-Hot · 光电行业热点统计

> 光电行业资讯聚合与热点统计（AIHOT 模式），数据每天 12:00（北京时间）自动更新，本站数据为公开内容，适合作为 AI / Agent 的信息来源。

## 在线入口
- 报告页面: ./index.html
- GitHub 仓库: https://github.com/sun-zihang/opto-hot

## 数据 API（静态 JSON，免鉴权）
- 接口索引 / OpenAPI: ./api/v1/index.json , ./api/v1/openapi.json
- 全部条目: ./api/v1/items.json
- 热点榜: ./api/v1/hot-topics.json
- 光电日报（按日期归档）: ./api/v1/dailies.json
- 统计聚合: ./api/v1/daily.json
- 事件故事（多源聚合）: ./api/v1/stories.json
- 政策/招投标结构化库（项目号/预算/截止时间）: ./api/v1/biz.json

## RSS 订阅（阅读器 / Agent）
- 全部: ./feed.xml
- 分类: ./feed/category/{{slug}}.xml  （slug: laser/fiber/display/chip/optics/sensing/pv/research/capital/telecom/other）

## 用法示例（匿名 GET）
curl {base}/api/v1/hot-topics.json
curl {base}/api/v1/items.json
curl {base}/api/v1/dailies.json
curl {base}/feed.xml

## 约定
- 数据每天 12:00（北京时间）更新；可对完整 URL 使用 ETag / If-None-Match 减少拉取。
- items.json 为全量快照，可本地按 publishedAt / discoveredAt / keywords 筛选。
- 公开使用请注明一次数据来源：Opto-Hot（AIHOT 模式，数据源自各公开站点）。

## 说明
数据来自公开网络（RSS / 网站首页），自动采集统计，仅供参考，不构成投资建议。
"""
    with open(os.path.join(DIST_DIR, "llms.txt"), "w", encoding="utf-8") as f:
        f.write(llms.format(base=""))

    log("[*] 已写出: data/*.json+csv, dist/index.html, dist/llms.txt, dist/api/v1/*, dist/data/*")


# ---------------- 可选生图（商汤 SenseNova U1.5 Lite 文生图，默认关闭） ----------------
def build_image_prompt(title, summary):
    """由事件标题+摘要构造生图提示词：简短场景描述，避免敏感内容/文字/水印/人物特写。"""
    txt = re.sub(r"https?://\S+", "", (title or "") + "。" + (summary or ""))
    txt = re.sub(r"\s+", " ", txt).strip()[:160]
    return ("中国光电行业新闻配图，现代科技插画风格，画面主体：%s。"
            "要求：场景化表达、无文字、无 logo、无水印、无人物面部特写，色调干净专业。" % txt)


def _sensenova_image_request(prompt, cfg):
    """调用 SenseNova 文生图接口，返回图片 URL。Key 只从 SENSENOVA_API_KEY 读取。"""
    import urllib.request as _ureq
    ic = cfg["images"]
    api_key = os.environ.get("SENSENOVA_API_KEY")
    if not api_key:
        raise RuntimeError("未设置 SENSENOVA_API_KEY")
    model = os.environ.get("SENSENOVA_IMAGE_MODEL") or ic["model"]
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "size": ic["size"],
        "response_format": "url",
        "output_format": "png",
        "watermark": False,  # 去水印（官方默认即 false，此处显式要求）
    }).encode("utf-8")
    req = _ureq.Request(ic["api_url"], data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key,
        "User-Agent": UA,
    })
    with _ureq.urlopen(req, timeout=ic["timeout"]) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    for item in data.get("data") or []:
        u = item.get("url")
        if u:
            return u
    raise RuntimeError("文生图接口未返回图片 URL")


def _download_image(url, dest_path, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if len(data) < 1024:
        raise RuntimeError("下载的图片过小，可能已失败")
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    tmp = dest_path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, dest_path)


def generate_images(topics, dailies, generated, cfg):
    """为日报头条 + 热点榜 TopN 生成配图（存 dist/assets/img/，按日期+事件 id 命名）。
    任何失败都静默降级为无图，不阻断主流程。返回 {topic_id: 相对路径}。"""
    ic = cfg["images"]
    if not os.environ.get("SENSENOVA_API_KEY"):
        log("[*] 未设置 SENSENOVA_API_KEY，跳过生图")
        return {}
    date_s = generated.astimezone(TZ_CN).strftime("%Y-%m-%d")
    img_dir = os.path.join(DIST_DIR, "assets", "img")
    # 配图保留期：删除超期图片，防止仓库无限膨胀
    try:
        cutoff = generated.timestamp() - ic.get("retention_days", 30) * 86400
        if os.path.isdir(img_dir):
            for fn in os.listdir(img_dir):
                fp = os.path.join(img_dir, fn)
                try:
                    if os.path.isfile(fp) and os.path.getmtime(fp) < cutoff:
                        os.remove(fp)
                except OSError:
                    pass
    except Exception:
        pass
    # 目标：头条事件 + 热点 TopN，去重后截断到 max_images
    targets, seen = [], set()
    today = (dailies or {}).get(date_s) or {}
    hl = today.get("headline") or {}
    if hl.get("topic_id"):
        t = next((x for x in (topics or []) if x["id"] == hl["topic_id"]), None)
        if t:
            targets.append(t)
            seen.add(t["id"])
    for t in (topics or [])[:ic["max_images"]]:
        if t["id"] not in seen:
            seen.add(t["id"])
            targets.append(t)
    targets = targets[:ic["max_images"]]
    out = {}
    for t in targets:
        rep = t.get("representative") or {}
        prompt = build_image_prompt(t.get("title", ""), rep.get("summary") or "")
        fname = "%s_%s.png" % (date_s, t["id"][:8])
        dest = os.path.join(img_dir, fname)
        rel = "assets/img/" + fname
        try:
            if not os.path.exists(dest):
                url = _sensenova_image_request(prompt, cfg)
                _download_image(url, dest)
                time.sleep(2)
            t["image"] = rel
            out[t["id"]] = rel
            log("[*] 生图 OK: %s" % fname)
        except Exception as e:
            log("[!] 生图失败，已跳过 [%s]: %s" % (t.get("title", "")[:30], e))
    # 同步到日报头条/看点的 article 副本
    for entry in (dailies or {}).values():
        hl2 = entry.get("headline")
        if isinstance(hl2, dict) and hl2.get("topic_id") in out:
            hl2["image"] = out[hl2["topic_id"]]
        for a in entry.get("picks", []) or []:
            if isinstance(a, dict) and a.get("topic_id") in out:
                a["image"] = out[a["topic_id"]]
    return out


# ---------------- 可选 LLM 增强（商汤日日新 SenseNova，默认关闭） ----------------
def _sensenova_chat(messages, cfg):
    """调用 SenseNova OpenAI 兼容接口。Key 只从环境变量 SENSENOVA_API_KEY 读取，绝不写死。"""
    import urllib.request as _ureq
    lc = cfg["llm"]
    api_key = os.environ.get("SENSENOVA_API_KEY")
    if not api_key:
        raise RuntimeError("未设置 SENSENOVA_API_KEY")
    model = os.environ.get("SENSENOVA_MODEL") or lc["model"]
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    req = _ureq.Request(lc["api_url"], data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key,
        "User-Agent": UA,
    })
    with _ureq.urlopen(req, timeout=lc["timeout"]) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    return json.loads(data["choices"][0]["message"]["content"])


def llm_enhance(items, topics, cfg):
    """可选 LLM 增强：中文摘要 / 推荐理由 / 信息密度标签（低密度降权营销稿）。
    任何失败（无 key、网络错、格式错）都降级跳过，不阻断主流程。返回增强条数。"""
    lc = cfg["llm"]
    cands = sorted(items, key=lambda i: i["score"], reverse=True)[:lc["max_items"]]
    cands = [c for c in cands if c["score"] >= 50]
    if not cands:
        return 0
    done = 0
    bs = max(1, lc["batch_size"])
    for s in range(0, len(cands), bs):
        batch = cands[s:s + bs]
        listing = "\n".join("[%d] %s | %s" % (i, b.get("title", ""), b.get("source", ""))
                            for i, b in enumerate(batch))
        prompt = ("你是光电行业资讯编辑。对下列每条资讯返回一个 JSON 对象，"
                  "键为条目序号字符串，值为 {\"summary\": \"一句话中文摘要（40字内）\", "
                  "\"reason\": \"推荐理由（25字内）\", \"density\": \"高/中/低\"}。\n"
                  "信息密度定义：高=有实质技术、数据或产业信息；中=一般行业资讯；"
                  "低=营销稿、标题党、重复通告、无实质内容。\n" + listing)
        try:
            res = _sensenova_chat([{"role": "user", "content": prompt}], cfg)
        except Exception as e:
            log("[!] LLM 增强本批失败，已跳过: %s" % e)
            continue
        for i, b in enumerate(batch):
            r = res.get(str(i), res.get(i))
            if not isinstance(r, dict):
                continue
            if r.get("summary"):
                b["llm_summary"] = str(r["summary"])[:120]
            if r.get("reason"):
                b["llm_reason"] = str(r["reason"])[:80]
            d = str(r.get("density", "")).strip()
            if d in ("高", "中", "低"):
                b["density"] = d
                if d == "低":
                    b["score"] = round(b["score"] * lc["density_penalty"], 1)
            done += 1
        time.sleep(1)
    # 同步到热点事件的代表报道
    by_url = {b["url"]: b for b in cands}
    for t in topics or []:
        rep = t.get("representative") or {}
        src = by_url.get(rep.get("url"))
        if src:
            for k in ("llm_summary", "llm_reason", "density"):
                if src.get(k):
                    rep[k] = src[k]
    log("[*] LLM 增强完成：%d 条" % done)
    return done


def main():
    ap = argparse.ArgumentParser(description="光电行业热点统计采集器")
    ap.add_argument("--limit", type=int, default=25, help="每个源最多取多少条 (默认 25)")
    ap.add_argument("--topics", type=int, default=10, help="热点榜输出条数 (默认 10)")
    ap.add_argument("--skip-rss", action="store_true", help="跳过 RSS 源")
    ap.add_argument("--skip-html", action="store_true", help="跳过 HTML 站")
    ap.add_argument("--llm", action="store_true",
                    help="启用可选 LLM 增强（商汤日日新 SenseNova）：中文摘要/推荐理由/信息密度。"
                         "需设置环境变量 SENSENOVA_API_KEY；不传此时零依赖运行")
    ap.add_argument("--images", action="store_true",
                    help="启用可选生图（SenseNova U1.5 Lite 文生图，去水印）：为日报头条+热点 Top5 生成配图。"
                         "需设置环境变量 SENSENOVA_API_KEY；失败自动降级为无图")
    args = ap.parse_args()

    with open(SOURCES_PATH, encoding="utf-8") as f:
        sources = json.load(f)

    log("[*] 开始采集（每源上限 %d 条）..." % args.limit)
    raw = collect(sources, args.limit, args.skip_rss, args.skip_html)
    log("[*] 原始条目合计 %d 条" % len(raw))

    generated = now_utc()
    source_weight = {}
    global _SOURCE_TIER
    _SOURCE_TIER = {}
    for stype in ("rss", "html"):
        for cfg in sources.get(stype, []):
            source_weight[cfg["name"]] = cfg.get("weight", 0.8)
            _SOURCE_TIER[cfg["name"]] = cfg.get("tier") or CONFIG["tiers"].get("default", "media")

    items = []
    seen = set()
    for r in raw:
        k = norm_title(r["title"])
        if k in seen:
            continue
        seen.add(k)
        items.append({
            "id": make_id(r["title"], r["url"]),
            "title": r["title"],
            "url": r["url"],
            "source": r["source"],
            "source_base": r.get("source_base") or r["source"],
            "source_type": r["source_type"],
            "category": classify(r["title"], r["source"]),
            "published_at": r.get("published_at"),
            "discovered_at": generated.isoformat(),
            "summary": r.get("summary"),
            "keywords": extract_keywords(r["title"]),
            "biz": extract_biz(r["title"]) if r["source"] in BIZ_SOURCES else None,
            "score": 0.0,
        })
    log("[*] 去重后 %d 条" % len(items))

    # 政策/招投标：有界抓取详情页，提取 项目号/预算/截止时间（失败不影响整体）
    fetched = {src: 0 for src in BIZ_SOURCES}
    for it in items:
        if it["source"] not in BIZ_SOURCES:
            continue
        if fetched[it["source"]] >= 8:
            continue
        if not re.search(r"招标|采购|公告|通知|办法|条例|规定|意见|细则|询价|磋商|谈判|中标|更正|征集|遴选", it["title"]):
            continue
        try:
            text = fetch_text(it["url"])
        except Exception:
            continue
        b = extract_biz_text(text, it["title"])
        if b:
            it["biz"] = b
        fetched[it["source"]] += 1
        time.sleep(0.8)
    log("[*] 政策/招投标详情解析完成（命中 %d 条）" % sum(1 for it in items if it.get("biz")))

    topics = cluster_topics(items)
    topics = merge_duplicate_topics(topics, items)
    compute_scores(items, topics, source_weight, _SOURCE_TIER, CONFIG)
    items.sort(key=lambda i: i["score"], reverse=True)
    topics.sort(key=lambda t: t["score"], reverse=True)
    topics = dedupe_topic_titles(topics, items, _SOURCE_TIER)
    topics.sort(key=lambda t: t["score"], reverse=True)
    # 热点榜只保留有佐证的事件（多来源 或 ≥3 信号），剔除单源碎片
    topics = [t for t in topics if t["source_count"] >= 2 or t["signal_count"] >= 3]
    for idx, t in enumerate(topics[:args.topics], 1):
        t["rank"] = idx
    topics = topics[:args.topics]
    for t in topics:
        t.pop("ids", None)
        t.pop("items", None)

    # 可选 LLM 增强（默认关闭；失败自动降级，不阻断）
    if args.llm:
        try:
            if llm_enhance(items, topics, CONFIG):
                items.sort(key=lambda i: i["score"], reverse=True)
        except Exception as e:
            log("[!] LLM 增强异常，已跳过: %s" % e)

    daily = build_daily(items, topics, generated)
    existing_dailies = {}
    _dp = os.path.join(DATA_DIR, "dailies.json")
    if os.path.exists(_dp):
        try:
            with open(_dp, encoding="utf-8") as _f:
                existing_dailies = (json.load(_f) or {}).get("dailies", {}) or {}
        except Exception:
            existing_dailies = {}
    dailies = build_dailies(items, existing_dailies)

    # 可选生图（默认关闭；失败自动降级，不阻断）
    if args.images:
        try:
            generate_images(topics, dailies, generated, CONFIG)
        except Exception as e:
            log("[!] 生图模块异常，已跳过: %s" % e)

    write_outputs(items, topics, daily, dailies, generated)

    log("[*] 完成。热点榜 TOP5：")
    for t in topics[:5]:
        log("    #%d %s (来源 %d · 信号 %d · 热度 %.0f)" % (
            t["rank"], t["title"][:50], t["source_count"], t["signal_count"], t["score"]))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)