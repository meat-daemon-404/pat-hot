#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PAT-HOT — 物理·天文·光电热点统计（以 AIHOT 为模板）

三频道：P 物理 / A 天文 / T 光电（原 opto-hot 内容）。

流程: 多源采集(RSS + 行业站) -> 清洗去重 -> 领域分类 -> 打分 -> 热点聚类
输出: data/<channel>/*.json, dist/index.html（三频道）, dist/api/v1/<channel>/*

用法:
    python collector/collect.py                          # 全频道全流程
    python collector/collect.py --channel tech             # 只跑光电频道
    python collector/collect.py --channel physics --limit 5
    python collector/collect.py --skip-html               # 跳过 HTML 站
"""

import argparse
import collections
import csv
import hashlib
import html as htmlmod
import io
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_DIR = os.path.join(ROOT, "data")
DIST_DIR = os.path.join(ROOT, "dist")
SOURCES_PATH = os.path.join(HERE, "sources.json")
CONFIG_PATH = os.path.join(HERE, "config.json")
CHANNELS_PATH = os.path.join(HERE, "channels.json")
REPO_URL = "https://github.com/sun-zihang/pat-hot"
BRAND = "PAT-HOT"
# 站点对外基址：RSS <link>/<channel> 与文档里的 curl 示例必须是绝对地址，
# 阅读器/AI 客户端拿到相对路径无法解析（旧值指向已下线的 CloudBase，全站 404）。
SITE_BASE = "https://sun-zihang.github.io/pat-hot/"
# 向后兼容：三频道重构后主输出改为 data/<ch>/ 与 api/v1/<ch>/，但已发布的外部
# 消费者（RSS 订阅、Agent Skill、llms.txt、README）读的是扁平老地址。
# 默认频道继续镜像一份扁平产物，避免下一次定时运行直接打断线上契约。
FLAT_ALIAS_CHANNEL = "tech"

# ---------------- 频道定义（collector/channels.json） ----------------
with open(CHANNELS_PATH, encoding="utf-8") as _cf:
    _CHANNELS_DOC = json.load(_cf)
CHANNELS = _CHANNELS_DOC["channels"]
CHANNEL_ORDER = _CHANNELS_DOC.get("order", ["physics", "astro", "tech"])
CHANNEL_DEFAULT = _CHANNELS_DOC.get("default", "tech")

# 当前频道上下文（run_channel 开始时设置；classify/build_daily 等通过它取规则）
_CH = CHANNEL_DEFAULT
_CHANNEL_TIERS = {}  # ch_id -> {source_name: tier}
# 本进程各频道抓取概况 {ch_id: {n_src, failed, raw}}，供 main() 判断本次抓取健康度；不落盘
_RUN_STATS = {}
CATEGORY_RULES = []
CATEGORY_ORDER = []
CAT_CLS = {}
RESEARCH_SOURCES = set()


def set_channel_context(ch_id):
    """设置当前频道的分类规则/顺序/slug/research 源（供 classify 等函数使用）。"""
    global _CH, CATEGORY_RULES, CATEGORY_ORDER, CAT_CLS, RESEARCH_SOURCES
    ch = CHANNELS[ch_id]
    CATEGORY_RULES = [(c, kws) for c, kws in ch["category_rules"]]
    CATEGORY_ORDER = list(ch["categories"])
    CAT_CLS = dict(ch["category_slug"])
    RESEARCH_SOURCES = set(ch.get("research_sources", []))
    _CH = ch_id


def ch_name(ch_id=None, lang="zh"):
    """频道显示名。"""
    return CHANNELS[ch_id or _CH]["name"].get(lang, lang)


def clean_latex(t):
    """清理 arXiv 标题中的 LaTeX 标记（去 $ 符号等），只做展示层清理。"""
    t = t.replace("$", "")
    t = t.replace("\\,", " ").replace("\\;", " ").replace("\\:", " ").replace("\\!", "")
    t = re.sub(r"\\([a-zA-Z]+)", r"\1", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

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
    "fetch": {
        "timeout": 25, "retries": 1, "max_bytes": 12582912,
        "text_timeout": 15,
        # 失败源占比超过它就拒绝写出：宁可 CI 红一次、线上继续端著上一份好数据，
        # 也不要发布一个"页面 200 但内容很薄"的静默降级站点。
        "max_source_failure_ratio": 0.6,
    },
    "daily": {
        "headline_count": 1, "picks_count": 4, "flash_count": 10,
        "max_per_source": 2, "dedup_window_days": 7, "per_category_limit": 8,
        "archive_days": 365,
    },
    "llm": {
        "provider": "sensenova",
        "model": "sensenova-6.8-flash-lite",
        "api_url": "https://token.sensenova.cn/v1/chat/completions",
        "max_items": 30, "batch_size": 3, "timeout": 120,
        "density_penalty": 0.9,
        "max_score_items": 30, "max_extract_items": 20,
    },
    "prompts": {
        "score_a": "你是光电行业资讯的资深编辑。请按以下标准为每条资讯打分（0-100 的整数）：\n- 行业重要性（40分）：对光电产业（激光/光通信/显示/半导体/光学/传感/光伏）的实质影响\n- 信息价值（30分）：是否有具体数据、技术细节或公司动态，而非泛泛而谈\n- 时效性（20分）：是否为近期新事件\n- 稀缺性（10分）：是否独家或少见报道\n只返回一个 JSON 对象，键为条目序号字符串，值为分數数字。不要解释、不要多余文字。\n{listing}",
        "score_b": "你是光电行业投资分析师。请独立判断每条资讯的“值得关注度”（0-100 的整数），注意这是你独立于其他标准的第二次判断：\n- 90-100：行业重大事件（并购/突破性技术/重大政策）\n- 70-89：重要公司动态或实质性技术进展\n- 50-69：一般行业资讯\n- 30-49：边缘相关或营销味较重\n- 0-29：无关或无价值\n只返回一个 JSON 对象，键为条目序号字符串，值为分數数字。不要解释、不要多余文字。\n{listing}",
        "extract": "你是光电行业资讯编辑。对每条资讯返回一个 JSON 对象，键为条目序号字符串，值为 {\"entities\": [\"提到的公司/机构名，最多3个\"], \"event\": \"谁做了什么，一句话（30字内）\", \"tags\": [\"1-3个标签，如：激光雷达/并购/财报\"]}。\n{listing}",
    },
    "trends": {
        "sustained_min_days": 3,
        "lookback_days": 14,
        "top_new": 10,
        "top_sustained": 10,
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



UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 PAT-HOT/2.0")

TZ_CN = timezone(timedelta(hours=8))
NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "atom": "http://www.w3.org/2005/Atom",
    "content": "http://purl.org/rss/1.0/modules/content/",
}

# ---------------- 领域词表（关键词抽取用，非分类） ----------------
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
    # 物理
    "量子计算", "量子比特", "qubit", "超导", "拓扑", "凝聚态", "希格斯", "higgs",
    "暗物质", "中微子", "neutrino", "等离子体", "plasma", "聚变", "fusion",
    # 天文
    "系外行星", "exoplanet", "黑洞", "black hole", "引力波", "gravitational wave",
    "超新星", "supernova", "星系", "galaxy", "宇宙", "cosmology", "火星", "mars",
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


def log(msg):
    print(msg, flush=True)


def now_utc():
    return datetime.now(timezone.utc)


MAX_BYTES = 12 * 1024 * 1024  # 兜底上限；实际值取 CONFIG["fetch"]["max_bytes"]


def _decode_body(raw, encoding, ctype):
    enc = (encoding or "").lower()
    if "gzip" in enc or (ctype or "").lower().find("gzip") >= 0 or raw[:2] == b"\x1f\x8b":
        try:
            import gzip
            return gzip.decompress(raw)
        except Exception:
            return raw
    if "deflate" in enc:
        try:
            import zlib
            return zlib.decompress(raw)
        except Exception:
            try:
                import zlib
                return zlib.decompressobj(-zlib.MAX_WBITS).decompress(raw)
            except Exception:
                return raw
    return raw


def http_get(url, timeout=None, retries=1):
    """抓取一个 URL，带重试与响应体上限。

    此前任何一次抖动（超时 / 连接重置）都会让整个源在本次运行里消失，而进程仍以
    0 退出：线上数据悄悄变薄却看不出来。现在做一次退避重试，并把失败计数交给
    调用方与 main() 的"源失败比例"闸门。
    """
    timeout = timeout or (CONFIG.get("fetch", {}) or {}).get("timeout", 25)
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                # 不主动请求压缩：urllib 不会自动解压，一旦站点把内容错标成 identity
                # 就会让整源解析失败而静默掉数据。下面仍会处理"服务器硬塞 gzip"的情况。
                "Accept": "application/rss+xml, application/xml;q=0.9, text/html;q=0.8, */*;q=0.7",
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                cap = int((CONFIG.get("fetch", {}) or {}).get("max_bytes", MAX_BYTES))
                raw = r.read(cap + 1)
                if len(raw) > cap:
                    raise ValueError("响应超过上限 %d 字节" % cap)
                body = _decode_body(raw, r.headers.get("Content-Encoding", ""),
                                    r.headers.get("Content-Type", ""))
                return body, r.headers.get("Content-Type", "")
        except Exception as e:
            last = e
            # 4xx（除 429）是稳定失败：权限/不存在，重试没意义；超时与 5xx 才重试
            code = getattr(e, "code", None)
            if isinstance(code, int) and 400 <= code < 500 and code != 429:
                break
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise last if last else RuntimeError("http_get 未知失败: %s" % url)


def abs_url(url, base):
    """把源给出的链接规范化为绝对 URL。
    RSS/HTML 里常见 //host/path（协议相对）与 /path（站点相对），
    直接写进 items.json / RSS <link> / 前端 href 会变成打不开的链接。
    """
    u = (url or "").strip()
    if not u or not base:
        return u
    if u.startswith("//"):
        scheme = "http" if base.startswith("http://") else "https"
        return scheme + ":" + u
    if u.startswith(("/", "#", "?")):
        return urllib.parse.urljoin(base, u)
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:", u):
        return urllib.parse.urljoin(base, u)
    return u


def rfc822(iso):
    """ISO8601 -> RFC 822 日期。RSS 2.0 的 pubDate/lastBuildDate 必须是 RFC 822，
    之前直接写 ISO，严格阅读器（Feedly/部分邮箱客户端）会当成无日期或丢弃条目。
    """
    try:
        dt = datetime.fromisoformat((iso or "").replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return format_datetime(dt.astimezone(timezone.utc), usegmt=True)
    except Exception:
        return None


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
    feed_base = cfg.get("url") or ""
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
        # 摘要保留较长（供站内展开阅读），卡片展示时前端截断
        summary = re.sub(r"\s+", " ", htmlmod.unescape(desc_plain)).strip()[:2500]
        url = abs_url(e["link"] or "", feed_base)
        if not url:
            continue
        items.append({
            "title": htmlmod.unescape(title).strip(),
            "url": url,
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
    """抓取一个频道的全部源。返回 (条目列表, 失败的源名列表)。

    失败源必须回报给调用方：单个源抖动只让数据变薄，但如果整频道全挂，
    write_outputs 会写出一个空站点，而进程仍以 0 退出、CI 仍显示绿色。
    """
    raw = []
    failed = []
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
                failed.append(cfg["name"])
    return raw, failed


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
    # 聚类阈值此前被写死在 cluster_semantic 的默认参数里，config.json 的
    # clustering.tfidf_threshold 从未生效；这里真正读配置，保持默认值不变。
    thr = (CONFIG.get("clustering") or {}).get("tfidf_threshold", 0.14)
    return cluster_semantic(items, thr)


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
        "zh_full": rep.get("zh_full"),
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


def fetch_text(url, timeout=None, retries=1):
    """详情页正文抓取（政策/招投标字段解析用）。走与 http_get 相同的重试与体积上限。"""
    timeout = timeout or (CONFIG.get("fetch", {}) or {}).get("text_timeout", 15)
    data, _ = http_get(url, timeout=timeout, retries=retries)
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
    if any(k in source for k in ("arXiv", "Nature", "CERN", "LIGO", "Phys.org", "Quanta")):
        return "科研"
    if any(k in source for k in ("NASA", "ESA", "MIT News")):
        return "官方"
    if any(k in source for k in ("OFweek", "LEDinside", "CIOE", "COEMA", "C114")):
        return "行业媒体"
    return "媒体"


def _daily_titles(e):
    """一条日报里已对外发布的全部标题（头条/看点/快讯/分类正文）。"""
    s = set()
    if not e:
        return s
    if e.get("headline"):
        s.add(e["headline"].get("title"))
    for k in ("picks", "flash"):
        for a in e.get(k, []) or []:
            s.add(a.get("title"))
    for sec in e.get("sections", []) or []:
        for a in sec.get("articles", []) or []:
            s.add(a.get("title"))
    return {t for t in s if t}


def _merge_daily_entry(old, new):
    """当天与昨天的日报合并：以本次重算为准，但已对外发布的条目一条都不能少。

    为什么不能整条覆盖（原实现 result.update(out) 的问题）：分数每次运行都会漂移，
    重算会把已公开的条目挤出 Top-N——实测一次重跑改写 34/106 天、丢掉 133 条。
    为什么不能只追加：源站 feed 会滚动，本次看不到的旧条目若不保留就会凭空消失。
    所以这里用「最新重算为基底 + 找回缺失的已发布条目」，两头都不丢。
    """
    if not old:
        return new
    base = dict(new or {})
    have = _daily_titles(base)
    rescued = 0

    def take(a, cat=None):
        nonlocal rescued
        t = a.get("title")
        if not t or t in have:
            return None
        have.add(t)
        rescued += 1
        return dict(a)

    # 头条/看点/快讯里的已发布条目：无分类信息，统一补进快讯，不动正文 Top-N
    extra_flash = []
    hl = old.get("headline")
    if isinstance(hl, dict):
        r = take(hl)
        if r:
            extra_flash.append(r)
    for k in ("picks", "flash"):
        for a in old.get(k, []) or []:
            r = take(a)
            if r:
                extra_flash.append(r)
    if extra_flash:
        base["flash"] = list(base.get("flash", []) or []) + extra_flash

    # 分类正文里已发布的条目：补回同分类
    by_cat = {}
    for sec in old.get("sections", []) or []:
        cat = sec.get("category")
        for a in sec.get("articles", []) or []:
            r = take(a, cat)
            if r:
                by_cat.setdefault(cat, []).append(r)
    if by_cat:
        sections = [dict(s) for s in (base.get("sections", []) or [])]
        idx = {s.get("category"): i for i, s in enumerate(sections)}
        for cat, arts in by_cat.items():
            if cat in idx:
                sections[idx[cat]]["articles"] = list(sections[idx[cat]].get("articles", []) or []) + arts
            else:
                sections.append({"category": cat, "articles": arts})
        base["sections"] = sections

    base["topic_ids"] = sorted(set(old.get("topic_ids", []) or [])
                               | set(base.get("topic_ids", []) or []))
    body_n = (1 if base.get("headline") else 0) + len(base.get("picks", []) or [])
    base["tocCount"] = body_n + len(base.get("flash", []) or [])
    base["amended"] = int((old or {}).get("amended", 0) or 0) + rescued
    return base


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
            "zh_full": a.get("zh_full"),
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
    # 归档语义：已发布的历史某天不再被后续运行改写。
    # 此前 result.update(out) 会用"当天分数 Top-N"覆盖旧条目，而分数随每次运行漂移，
    # 实测一次重跑就改写了 34/106 天、丢掉 133 个已公开条目 —— 日报归档必须不可变。
    # 但"昨天"仍要允许补写：每天 06:00 的那次运行会发现前一天晚间发布、
    # 当时还没被抓到的条目，若严格锁死昨天就会把它们永久漏出日报归档。
    _today = datetime.now(TZ_CN).date()
    refresh_days = max(0, int(dc.get("refresh_days", 1) or 0))
    refresh_floor = (_today - timedelta(days=refresh_days)).isoformat()
    kept, merged_days, written, rescued = 0, 0, 0, 0
    for d, entry in out.items():
        prev = result.get(d)
        if prev is None:
            result[d] = entry
            written += 1
        elif d >= refresh_floor:
            merged = _merge_daily_entry(prev, entry)
            rescued += int(merged.get("amended", 0) or 0) - int((prev or {}).get("amended", 0) or 0)
            merged_days += 1
            result[d] = merged
        else:
            kept += 1
    if kept or merged_days:
        log("[*] 归档保护：%d 天原样保留，%d 天按重算刷新（近 %d 天，找回已发布条目 %d 条），%d 天新建"
            % (kept, merged_days, refresh_days, rescued, written))
    # 保留期改为配置驱动（此前写死 365 天，README 声称"参数全部集中在 config.json"）
    keep_days = int(dc.get("archive_days", 365) or 365)
    cutoff = (datetime.now(TZ_CN).date() - timedelta(days=keep_days)).isoformat()
    return {k: v for k, v in result.items() if k >= cutoff}


def build_trends(dailies, generated, cfg):
    """周维度趋势聚合（AIHOT 周报思想），只消费 dailies.json，不新增采集：
    - 本周 vs 上周：各分类热度（文章 score 求和）变化
    - 新上榜事件：本周出现、过去 lookback_days 天未出现过的事件
    - 持续发酵事件：lookback_days 内出现天数 >= sustained_min_days 的事件
    同一事件跨天只算一件。
    """
    tc = cfg.get("trends", {})
    lookback = max(7, tc.get("lookback_days", 14))
    min_days = max(2, tc.get("sustained_min_days", 3))
    now_cn = generated.astimezone(TZ_CN).date()
    monday = now_cn - timedelta(days=now_cn.weekday())
    this_week = {(monday + timedelta(days=i)).isoformat() for i in range(7)}
    last_monday = monday - timedelta(days=7)
    last_week = {(last_monday + timedelta(days=i)).isoformat() for i in range(7)}
    hist_start = (monday - timedelta(days=lookback)).isoformat()

    cat_heat = {"this": collections.Counter(), "last": collections.Counter()}
    topic_days = collections.defaultdict(set)   # topic_id -> set(date)
    topic_title = {}
    topic_score = collections.Counter()

    for d, entry in (dailies or {}).items():
        if d < hist_start or d > now_cn.isoformat():
            continue
        bucket = "this" if d in this_week else ("last" if d in last_week else None)
        for sec in (entry or {}).get("sections", []) or []:
            cat = sec.get("category") or "其他"
            for a in sec.get("articles", []) or []:
                s = float(a.get("score") or 0)
                if bucket:
                    cat_heat[bucket][cat] += s
                tid = a.get("topic_id")
                if tid:
                    topic_days[tid].add(d)
                    topic_title[tid] = a.get("topic_title") or a.get("title") or tid
                    topic_score[tid] += s

    cats = sorted(set(cat_heat["this"]) | set(cat_heat["last"]),
                  key=lambda c: cat_heat["this"][c], reverse=True)
    category_delta = []
    for c in cats:
        tw, lw = round(cat_heat["this"][c], 1), round(cat_heat["last"][c], 1)
        pct = round((tw - lw) / lw * 100, 1) if lw > 0 else (100.0 if tw > 0 else 0.0)
        category_delta.append({"category": c, "thisWeek": tw, "lastWeek": lw, "deltaPct": pct})

    week_start = monday.isoformat()
    new_topics, sustained = [], []
    for tid, days in topic_days.items():
        days_sorted = sorted(days)
        in_this_week = any(d in this_week for d in days_sorted)
        first_seen = days_sorted[0]
        if in_this_week and first_seen >= week_start:
            # 本周首次出现：再确认 lookback 窗口内更早无记录（topic_id 本身即按事件归一）
            new_topics.append({"topic_id": tid, "title": topic_title.get(tid, tid),
                               "score": round(topic_score[tid], 1), "days": len(days_sorted)})
        if len(days_sorted) >= min_days:
            sustained.append({"topic_id": tid, "title": topic_title.get(tid, tid),
                              "days": len(days_sorted),
                              "score": round(topic_score[tid], 1)})
    new_topics.sort(key=lambda x: x["score"], reverse=True)
    sustained.sort(key=lambda x: (x["days"], x["score"]), reverse=True)
    top_n, top_s = tc.get("top_new", 10), tc.get("top_sustained", 10)

    return {
        "schemaVersion": 1,
        "generatedAt": generated.isoformat(),
        "weekStart": week_start,
        "categoryDelta": category_delta,
        "newTopics": new_topics[:top_n],
        "sustainedTopics": sustained[:top_s],
    }


# ---------------- HTML 报告（AIHOT 风格） ----------------
def _load_template(_name):
    _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", _name)
    with open(_p, encoding="utf-8") as _f:
        return _f.read().rstrip("\n")


APP_CSS = _load_template("app.css")
APP_JS = _load_template("app.js")
APP_HTML = _load_template("app.html")

# APP_JS -> collector/templates (template split for push size)

# APP_HTML -> collector/templates (template split for push size)


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


def render_app_html(channel_results, generated):
    """渲染三频道单页：__SNAPSHOT__ = {channels: {id: {...}}, meta: {...}}。"""
    import json as _json
    channels = {}
    for ch_id, (items, topics, daily, dailies, trends) in channel_results.items():
        ch = CHANNELS[ch_id]
        # 本频道数据自己的收录时间；沿用上次产物时不能冒用本次运行时刻，
        # 否则页面上"生成于 …"会让旧频道看起来像刚刷新过。
        stamps = [i.get("discovered_at") for i in (items or []) if i.get("discovered_at")]
        ch_gen = max(stamps) if stamps else generated.isoformat()
        channels[ch_id] = {
            "id": ch_id,
            "letter": ch["letter"],
            "name": ch["name"],
            "generatedAt": ch_gen,
            "catCls": dict(ch["category_slug"]),
            "catEn": dict(ch["category_en"]),
            "items": items,
            "topics": topics,
            "daily": daily,
            "dailies": dailies,
            "trends": trends or {},
            "thresholds": {k: v["select_threshold"] for k, v in CONFIG["tiers"].items()
                           if isinstance(v, dict) and "select_threshold" in v},
        }
    snapshot = {
        "generatedAt": generated.isoformat(),
        "brand": BRAND,
        "meta": {
            "channels": [{"id": c, "letter": CHANNELS[c]["letter"],
                          "name": CHANNELS[c]["name"]} for c in CHANNEL_ORDER],
            "default": CHANNEL_DEFAULT,
        },
        "channels": channels,
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
    pub_raw = max(it["discovered_at"] for it in its) if its else now_utc().isoformat()
    # RSS 2.0 要求 RFC 822 日期；同时保留绝对站点地址供阅读器展示
    pub = rfc822(pub_raw) or format_datetime(now_utc(), usegmt=True)
    out = []
    for it in its:
        idate = rfc822(it["discovered_at"]) or pub
        out.append(
            "<item><title>%s</title><link>%s</link><description>%s</description>"
            "<guid isPermaLink=\"false\">%s</guid><pubDate>%s</pubDate>"
            "<source>%s</source><category>%s</category></item>"
            % (su.escape(it["title"]), su.escape(it["url"]), su.escape((it.get("summary") or "")[:500]),
               it["id"], idate, su.escape(it["source"]), su.escape(it["category"])))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
            "<title>%s</title><link>%s</link><description>%s</description>"
            "<lastBuildDate>%s</lastBuildDate>%s</channel></rss>"
            % (su.escape(title), su.escape(link), su.escape(description), pub, "".join(out)))


def build_openapi(generated):
    def ep(summary):
        return {"get": {"summary": summary, "responses": {"200": {"description": "OK"}}}}
    paths = {
        "/api/v1/index.json": ep("接口索引"),
        "/feed.xml": ep("RSS（最新 50 条，T 光电频道）"),
        "/feed/category/{slug}.xml": ep("兼容分类 RSS（重构前地址，内容 = %s 频道）"
                                        % CHANNELS[FLAT_ALIAS_CHANNEL]["name"]["zh"]),
    }
    for ch_id in CHANNEL_ORDER:
        ch = CHANNELS[ch_id]
        paths["/api/v1/%s/items.json" % ch_id] = ep("%s：全部条目" % ch["name"]["zh"])
        paths["/api/v1/%s/hot-topics.json" % ch_id] = ep("%s：热点榜" % ch["name"]["zh"])
        paths["/api/v1/%s/dailies.json" % ch_id] = ep("%s：日报（按日期归档）" % ch["name"]["zh"])
        paths["/api/v1/%s/daily.json" % ch_id] = ep("%s：统计聚合" % ch["name"]["zh"])
        paths["/api/v1/%s/stories.json" % ch_id] = ep("%s：事件故事" % ch["name"]["zh"])
        paths["/api/v1/%s/trends.json" % ch_id] = ep("%s：趋势" % ch["name"]["zh"])
    # 重构前就发布的扁平地址（内容 = FLAT_ALIAS_CHANNEL 频道），仍在线且持续更新，
    # 必须一并声明；否则 Agent 读 OpenAPI 会以为这些地址不存在。
    for k, zh in (("items", "全部条目"), ("hot-topics", "热点榜"),
                  ("dailies", "日报归档（裸日期字典）"), ("daily", "统计聚合"),
                  ("stories", "事件故事"), ("trends", "趋势")):
        paths["/api/v1/%s.json" % k] = ep(
            "兼容地址（%s 频道）：%s" % (CHANNELS[FLAT_ALIAS_CHANNEL]["name"]["zh"], zh))
    return {
        "openapi": "3.1.0",
        "info": {"title": "PAT-HOT API v1", "version": "2.0.0",
                 "description": "物理·天文·光电热点统计静态 JSON 接口（免鉴权，每天 6:00/18:00 北京时间更新，AI/Agent 可直接消费）。"},
        "servers": [{"url": SITE_BASE.rstrip("/")}],
        "paths": paths,
    }



def _csv_rows(items):
    """条目 -> report.csv 文本（表头 + 行），供频道目录与扁平兼容层复用。"""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "title", "category", "source", "published_at", "discovered_at",
                "score", "url", "role", "selected"])
    for it in items:
        w.writerow([it["id"], it["title"], it["category"], it["source"],
                    it.get("published_at") or "", it["discovered_at"], it["score"], it["url"],
                    it["role"], it["selected"]])
    return buf.getvalue()


def write_outputs(channel_results, generated):
    """多频道输出：
    - data/<ch>/{items,hot-topics,daily,dailies,trends,report}.json+csv，data/channels.json
    - dist/index.html（三频道单页），dist/feed.xml（主 feed：T 光电），dist/llms.txt
    - dist/data/<ch>/*（静态托管副本），dist/api/v1/<ch>/*，dist/feed/<ch>/category/*.xml
    """
    import shutil
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(DIST_DIR, exist_ok=True)

    def dump(obj, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

    tiers = CONFIG["tiers"]
    hc = CONFIG["heat"]

    # 频道清单
    dump({"brand": BRAND, "generatedAt": generated.isoformat(),
          "channels": [{"id": c, "letter": CHANNELS[c]["letter"], "name": CHANNELS[c]["name"]}
                       for c in CHANNEL_ORDER]},
         os.path.join(DATA_DIR, "channels.json"))

    for ch_id, (items, topics, daily, dailies, trends) in channel_results.items():
        set_channel_context(ch_id)
        ch = CHANNELS[ch_id]
        tier_map = _CHANNEL_TIERS.get(ch_id, {})

        def _tier_of(it, _tm=tier_map):
            return _tm.get(it.get("source_base") or it["source"]) or tiers.get("default", "media")

        def _threshold(it):
            return tiers.get(_tier_of(it), tiers["media"])["select_threshold"]

        for it in items:
            it.setdefault("links", {})
            it["links"]["original"] = it["url"]
            it["tier"] = _tier_of(it)
            eff = it["llm_score"] if it.get("llm_score") is not None else it["score"]
            it["selected"] = eff >= _threshold(it)
            it["role"] = role_tag(it["source"])
        for t in topics:
            t["heat"] = t["score"]
            if t["source_count"] >= hc["status_hot_min_sources"] and t["score"] >= hc["status_hot_min_heat"]:
                t["status"] = "爆"
            elif t["source_count"] >= hc["status_trending_min_sources"]:
                t["status"] = "发酵中"
            else:
                t["status"] = "关注中"

        ch_data = os.path.join(DATA_DIR, ch_id)
        dump({"schemaVersion": 1, "generatedAt": generated.isoformat(),
              "count": len(items), "items": items}, os.path.join(ch_data, "items.json"))
        dump({"schemaVersion": 1, "generatedAt": generated.isoformat(),
              "count": len(topics), "items": topics}, os.path.join(ch_data, "hot-topics.json"))
        dump(daily, os.path.join(ch_data, "daily.json"))
        dump({"schemaVersion": 1, "generatedAt": generated.isoformat(),
              "count": len(dailies), "dailies": dailies}, os.path.join(ch_data, "dailies.json"))
        dump(trends, os.path.join(ch_data, "trends.json"))

        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "title", "category", "source", "published_at", "discovered_at",
                    "score", "url", "role", "selected"])
        for it in items:
            w.writerow([it["id"], it["title"], it["category"], it["source"],
                        it.get("published_at") or "", it["discovered_at"], it["score"], it["url"],
                        it["role"], it["selected"]])
        with open(os.path.join(ch_data, "report.csv"), "w", encoding="utf-8-sig", newline="") as f:
            f.write(buf.getvalue())

        # 静态托管副本
        dist_data = os.path.join(DIST_DIR, "data", ch_id)
        os.makedirs(dist_data, exist_ok=True)
        for fn in ("items.json", "hot-topics.json", "daily.json", "dailies.json", "trends.json",
                   "report.csv"):
            shutil.copyfile(os.path.join(ch_data, fn), os.path.join(dist_data, fn))

        # API
        api_dir = os.path.join(DIST_DIR, "api", "v1", ch_id)
        os.makedirs(api_dir, exist_ok=True)
        stories = []
        for t in topics:
            stories.append({
                "id": t["id"], "title": t["title"], "status": t.get("status"),
                "heat": t.get("heat", t.get("score")),
                "sourceCount": t["source_count"], "signalCount": t["signal_count"],
                "latestAt": t["latest_at"], "sources": t.get("sources", []),
                "links": t.get("links", []),
            })
            _rep = t.get("representative") or {}
            if _rep.get("llm_score") is not None:
                stories[-1]["llmScore"] = _rep["llm_score"]
        dump({"schemaVersion": 1, "generatedAt": generated.isoformat(),
              "count": len(items), "items": items}, os.path.join(api_dir, "items.json"))
        dump({"schemaVersion": 1, "generatedAt": generated.isoformat(),
              "count": len(topics), "items": topics}, os.path.join(api_dir, "hot-topics.json"))
        dump(dailies, os.path.join(api_dir, "dailies.json"))
        dump(daily, os.path.join(api_dir, "daily.json"))
        dump(trends, os.path.join(api_dir, "trends.json"))
        dump({"schemaVersion": 1, "generatedAt": generated.isoformat(),
              "count": len(stories), "items": stories}, os.path.join(api_dir, "stories.json"))

        # 分类 RSS（按频道）
        feed_dir = os.path.join(DIST_DIR, "feed", ch_id, "category")
        os.makedirs(feed_dir, exist_ok=True)
        by_cat = {}
        for it in items:
            by_cat.setdefault(it["category"], []).append(it)
        for cat, its in by_cat.items():
            slug = CAT_CLS.get(cat, "other")
            with open(os.path.join(feed_dir, slug + ".xml"), "w", encoding="utf-8") as f:
                f.write(build_rss(its, "PAT-HOT · %s%s" % (ch["letter"], cat),
                                  SITE_BASE + "#/all", cat, 30))

        # 政策/招投标结构化库（仅 T 光电频道）
        if ch_id == "tech":
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
            dump(biz_doc, os.path.join(ch_data, "biz.json"))
            shutil.copyfile(os.path.join(ch_data, "biz.json"),
                            os.path.join(dist_data, "biz.json"))
            dump(biz_doc, os.path.join(DIST_DIR, "api", "v1", ch_id, "biz.json"))
            bbuf = io.StringIO()
            bw = csv.writer(bbuf)
            bw.writerow(["source", "title", "category", "url", "published_at", "discovered_at",
                         "project_no", "budget", "deadline"])
            for r in biz_rows:
                bw.writerow([r["source"], r["title"], r["category"], r["url"],
                             r.get("published_at") or "", r["discovered_at"],
                             r.get("project_no") or "", r.get("budget") or "",
                             r.get("deadline") or ""])
            with open(os.path.join(ch_data, "biz.csv"), "w", encoding="utf-8-sig", newline="") as f:
                f.write(bbuf.getvalue())
            shutil.copyfile(os.path.join(ch_data, "biz.csv"),
                            os.path.join(dist_data, "biz.csv"))

    # ---- 向后兼容：把默认频道镜像回扁平老地址 ----
    # 三频道重构后主输出是 data/<ch>/ 与 api/v1/<ch>/，但线上已有消费者读的是
    # 重构前的扁平地址（README、llms.txt、RSS 订阅、已发布的 Agent Skill 都写
    # api/v1/items.json）。没有这一层，下一次定时运行会把全部老地址打成 404。
    # 用 channel_results 显式取频道，不依赖循环变量的残留值。
    alias = channel_results.get(FLAT_ALIAS_CHANNEL)
    if alias:
        a_items, a_topics, a_daily, a_dailies, a_trends = alias
        a_stories = []
        for t in a_topics:
            _s = {"id": t["id"], "title": t["title"], "status": t.get("status"),
                  "heat": t.get("heat", t.get("score")),
                  "sourceCount": t["source_count"], "signalCount": t["signal_count"],
                  "latestAt": t["latest_at"], "sources": t.get("sources", []),
                  "links": t.get("links", [])}
            _rep = t.get("representative") or {}
            if _rep.get("llm_score") is not None:
                _s["llmScore"] = _rep["llm_score"]
            a_stories.append(_s)
        gen = generated.isoformat()
        # 线上 api/v1/dailies.json 一直是「裸日期字典」（消费者直接 dailies["2026-10-11"] 取值），
        # 而 data/ 与 dist/data/ 是带 schemaVersion 的包装文档。两种形状都是已发布契约，
        # 这里严格照搬线上现状，不做"统一"，否则会打断现有 Agent/RSS 消费者。
        dailies_doc = {"schemaVersion": 1, "generatedAt": gen,
                       "count": len(a_dailies), "dailies": a_dailies}
        api_v1_dir = os.path.join(DIST_DIR, "api", "v1")
        flat_dist = os.path.join(DIST_DIR, "data")
        for name, doc in (("items.json", {"schemaVersion": 1, "generatedAt": gen,
                                          "count": len(a_items), "items": a_items}),
                          ("hot-topics.json", {"schemaVersion": 1, "generatedAt": gen,
                                               "count": len(a_topics), "items": a_topics}),
                          ("dailies.json", dailies_doc),
                          ("daily.json", a_daily),
                          ("trends.json", a_trends),
                          ("stories.json", {"schemaVersion": 1, "generatedAt": gen,
                                            "count": len(a_stories), "items": a_stories})):
            dump(doc, os.path.join(api_v1_dir, name))
            shutil.copyfile(os.path.join(api_v1_dir, name), os.path.join(flat_dist, name))
        # api 层的 dailies 用裸字典覆盖上面写出的包装文档（保持线上形状）
        dump(a_dailies, os.path.join(api_v1_dir, "dailies.json"))
        for src, dst in (("dailies.json", os.path.join(DATA_DIR, "dailies.json")),
                         ("items.json", os.path.join(DATA_DIR, "items.json")),
                         ("hot-topics.json", os.path.join(DATA_DIR, "hot-topics.json")),
                         ("daily.json", os.path.join(DATA_DIR, "daily.json")),
                         ("trends.json", os.path.join(DATA_DIR, "trends.json"))):
            shutil.copyfile(os.path.join(DATA_DIR, FLAT_ALIAS_CHANNEL, src), dst)
        with open(os.path.join(DATA_DIR, "report.csv"), "w",
                  encoding="utf-8-sig", newline="") as f:
            f.write(_csv_rows(a_items))
        shutil.copyfile(os.path.join(DATA_DIR, "report.csv"),
                        os.path.join(flat_dist, "report.csv"))
        # 扁平分类 feed：dist/feed/category/<slug>.xml（老订阅地址）
        set_channel_context(FLAT_ALIAS_CHANNEL)
        feed_flat = os.path.join(DIST_DIR, "feed", "category")
        os.makedirs(feed_flat, exist_ok=True)
        by_cat = {}
        for it in a_items:
            by_cat.setdefault(it["category"], []).append(it)
        for cat, its in by_cat.items():
            slug = CAT_CLS.get(cat, "other")
            with open(os.path.join(feed_flat, slug + ".xml"), "w", encoding="utf-8") as f:
                f.write(build_rss(its, "PAT-HOT · %s" % cat,
                                  SITE_BASE + "#/all", cat, 30))
        # 政策/招投标库只有 T 光电频道产出，但线上一直有扁平地址
        # （data/biz.json、dist/data/biz.json、dist/api/v1/biz.json、biz.csv）。
        # 不镜像就会静默变旧：文件在、返回 200，内容却是上一次的。
        for name, dest in (("biz.json", os.path.join(api_v1_dir, "biz.json")),
                           ("biz.json", os.path.join(flat_dist, "biz.json")),
                           ("biz.json", os.path.join(DATA_DIR, "biz.json")),
                           ("biz.csv", os.path.join(flat_dist, "biz.csv")),
                           ("biz.csv", os.path.join(DATA_DIR, "biz.csv"))):
            src_p = os.path.join(DATA_DIR, FLAT_ALIAS_CHANNEL, name)
            if os.path.exists(src_p):
                shutil.copyfile(src_p, dest)
        log("[*] 向后兼容扁平产物已镜像（频道 %s -> data/、dist/data/、dist/api/v1/、dist/feed/category/）"
            % FLAT_ALIAS_CHANNEL)

    # ---- 三频道单页 ----
    with open(os.path.join(DIST_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_app_html(channel_results, generated))

    # ---- 主 feed（默认频道，保持老订阅者兼容） ----
    _alias_items = channel_results.get(FLAT_ALIAS_CHANNEL, ([], None, None, None, None))[0] \
        if FLAT_ALIAS_CHANNEL in channel_results else []
    with open(os.path.join(DIST_DIR, "feed.xml"), "w", encoding="utf-8") as f:
        f.write(build_rss(_alias_items, "PAT-HOT 热点", SITE_BASE,
                          "物理·天文·光电热点统计（AIHOT 模式）", 50))

    # ---- API 索引 + OpenAPI ----
    api_v1 = os.path.join(DIST_DIR, "api", "v1")
    os.makedirs(api_v1, exist_ok=True)
    eps = {}
    for ch_id in channel_results:
        for k in ("items", "hot-topics", "dailies", "daily", "stories", "trends"):
            eps["%s/%s" % (ch_id, k)] = "api/v1/%s/%s.json" % (ch_id, k)
    # 重构前就已发布的扁平地址（内容 = T 光电频道）也登记进索引，
    # 否则 Agent 读 index.json 会以为只有频道地址，找不到仍在线上的老地址。
    if FLAT_ALIAS_CHANNEL in channel_results:
        for k in ("items", "hot-topics", "dailies", "daily", "stories", "trends"):
            eps["legacy:%s" % k] = "api/v1/%s.json" % k
    dump({"name": "PAT-HOT API v1",
          "description": "物理·天文·光电热点统计静态 JSON 接口（免鉴权，每天 6:00/18:00 北京时间更新）。"
                         "api/v1/<频道>/* 为当前布局；legacy:* 是重构前的扁平地址，内容等同 T 光电频道，仍持续更新。",
          "channels": list(channel_results),
          "defaultChannel": CHANNEL_DEFAULT,
          "endpoints": eps},
         os.path.join(api_v1, "index.json"))
    with open(os.path.join(api_v1, "openapi.json"), "w", encoding="utf-8") as f:
        json.dump(build_openapi(generated), f, ensure_ascii=False, indent=2)

    # ---- llms.txt ----
    ch_lines = "\n".join(
        "- %s（%s）: {base}/api/v1/%s/items.json , {base}/api/v1/%s/hot-topics.json , {base}/api/v1/%s/dailies.json"
        % (CHANNELS[c]["name"]["zh"], CHANNELS[c]["letter"], c, c, c)
        for c in channel_results)
    llms = """# PAT-HOT · 物理·天文·光电热点统计

> 物理 / 天文 / 光电三频道资讯聚合与热点统计（AIHOT 模式），数据每天 6:00、18:00（北京时间）自动更新，本站数据为公开内容，适合作为 AI / Agent 的信息来源。

## 在线入口
- 报告页面: {base}/index.html
- GitHub 仓库: {repo}

## 数据 API（静态 JSON，免鉴权，按频道）
- 接口索引 / OpenAPI: {base}/api/v1/index.json , {base}/api/v1/openapi.json
%s

## 兼容地址（重构前的扁平路径，仍可用，内容为 T 光电频道）
- {base}/api/v1/items.json , {base}/api/v1/hot-topics.json , {base}/api/v1/dailies.json
- {base}/api/v1/daily.json , {base}/api/v1/stories.json , {base}/api/v1/trends.json

## RSS 订阅（阅读器 / Agent）
- 主 feed（T 光电）: {base}/feed.xml
- 分类: {base}/feed/<频道>/category/<slug>.xml

## 用法示例（匿名 GET）
curl {base}/api/v1/tech/hot-topics.json
curl {base}/api/v1/physics/items.json
curl {base}/api/v1/astro/dailies.json
curl {base}/feed.xml

## 约定
- 数据每天 6:00、18:00（北京时间）更新；可对完整 URL 使用 ETag / If-None-Match 减少拉取。
- items.json 为全量快照，可本地按 publishedAt / discoveredAt / keywords 筛选。
- api/v1/dailies.json 为裸日期字典（键是 YYYY-MM-DD）；data/dailies.json 才带 schemaVersion 包装。
- 公开使用请注明一次数据来源：PAT-HOT（AIHOT 模式，数据源自各公开站点）。

## 说明
数据来自公开网络（RSS / 网站首页），自动采集统计，仅供参考，不构成投资建议。
""" % ch_lines
    with open(os.path.join(DIST_DIR, "llms.txt"), "w", encoding="utf-8") as f:
        f.write(llms.format(base=SITE_BASE.rstrip("/"), repo=REPO_URL))

    log("[*] 已写出: data/<ch>/*.json+csv, dist/index.html, dist/llms.txt, dist/api/v1/<ch>/*, dist/feed.xml")


# ---------------- 可选生图（商汤 SenseNova U1.5 Lite 文生图，默认关闭） ----------------
def build_image_prompt(title, summary):
    """由事件标题+摘要构造生图提示词：简短场景描述，避免敏感内容/文字/水印/人物特写。"""
    txt = re.sub(r"https?://\S+", "", (title or "") + "。" + (summary or ""))
    txt = re.sub(r"\s+", " ", txt).strip()[:160]
    return ("中国%s新闻配图，现代科技插画风格，画面主体：%s。"
            "要求：场景化表达、无文字、无 logo、无水印、无人物面部特写，色调干净专业。" % (CHANNELS[_CH]["name"]["zh"], txt))


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


def generate_images(topics, dailies, generated, cfg, ch_id="tech"):
    """为日报头条 + 热点榜 TopN 生成配图（存 dist/assets/img/，按频道+日期+事件 id 命名）。
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
        fname = "%s_%s_%s.png" % (ch_id, date_s, t["id"][:8])
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
def _sensenova_chat(messages, cfg, max_retries=3):
    """调用 SenseNova OpenAI 兼容接口。Key 只从环境变量 SENSENOVA_API_KEY 读取，绝不写死。
    带指数退避重试（2s/4s），应对超时和瞬时网络抖动；401/403 认证失败不重试。"""
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
    with_retry = lc["timeout"]
    last_err = None
    for attempt in range(max_retries):
        try:
            req = _ureq.Request(lc["api_url"], data=payload, headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + api_key,
                "User-Agent": UA,
            })
            with _ureq.urlopen(req, timeout=with_retry) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception as e:
            last_err = e
            # 用真实 HTTP 状态码判断，不用字符串匹配：原实现写 "401" in str(e)，
            # 任何文本里恰好含 401/403（字节数、端口、标题）都会误判成认证失败而放弃重试。
            code = getattr(e, "code", None)
            if isinstance(code, int) and code in (401, 403):
                log("[x] LLM 认证失败（%d），不重试：%s" % (code, str(e)[:120]))
                raise
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                # 429 时尊重服务端 Retry-After，退避过短只会继续撞配额
                if isinstance(code, int) and code == 429:
                    try:
                        wait = max(wait, int(float(e.headers.get("Retry-After", wait))))
                    except Exception:
                        pass
                log("[!] LLM 请求失败（第%d/%d次），%ds后重试: %s" % (attempt + 1, max_retries, wait, e))
                time.sleep(wait)
    raise last_err


def _ch_prompt(key, cfg):
    """取外置 prompt，并把其中的"光电"替换为当前频道的领域词。"""
    p = cfg["prompts"][key]
    dom = CHANNELS[_CH]["domain"]["zh"]
    if dom != "光电行业":
        p = p.replace("光电行业", dom).replace("光电产业", dom).replace("光电", CHANNELS[_CH]["name"]["zh"])
    return p


def _apply_enhance(b, r, lc):
    """把单条 LLM 增强结果写回条目，成功返回 1，失败返回 0。"""
    if not isinstance(r, dict):
        return 0
    ok = False
    if r.get("zh_full"):
        b["zh_full"] = str(r["zh_full"])[:1200]
        ok = True
    if r.get("summary"):
        b["llm_summary"] = str(r["summary"])[:300]
        ok = True
    if r.get("reason"):
        b["llm_reason"] = str(r["reason"])[:80]
    d = str(r.get("density", "")).strip()
    if d in ("高", "中", "低"):
        b["density"] = d
        if d == "低":
            b["score"] = round(b["score"] * lc["density_penalty"], 1)
    return 1 if ok else 0


def llm_enhance(items, topics, cfg):
    """可选 LLM 增强：中文完整摘要 / 内容概要 / 推荐理由 / 信息密度标签。
    zh_full：基于 RSS 摘要全文翻译整理成中文（300-500字），是站内阅读的主体，
    目标读者无法访问外网，仅凭中文摘要就要能完整理解文章内容。
    summary：150-250 字中文内容概要，用于卡片预览。
    覆盖所有有摘要的条目（不再只限 Top30），任何失败都降级跳过，不阻断主流程。返回增强条数。"""
    lc = cfg["llm"]
    # 所有条目都处理：有 RSS 摘要的做全文翻译，无摘要的只看标题给概要
    cands = sorted(items, key=lambda i: i["score"], reverse=True)
    if not cands:
        return 0
    done = 0
    bs = max(1, lc["batch_size"])
    for s in range(0, len(cands), bs):
        batch = cands[s:s + bs]
        def _listing(b, i):
            desc = (b.get("summary") or "").strip()
            desc = re.sub(r"\s+", " ", desc)[:600]
            return "[%d] %s\n来源：%s\n摘要：%s" % (i, b.get("title", ""), b.get("source", ""), desc or "（无摘要，仅标题）")
        listing = "\n\n".join(_listing(b, i) for i, b in enumerate(batch))
        prompt = ("你是%s资讯编辑，读者是无法访问外网的中国大学生，只能在站内阅读你的中文输出。对下列每条资讯返回一个 JSON 对象，"
                  "键为条目序号字符串，值为 {\"zh_full\": \"中文完整摘要（300-500字）：把上面的摘要翻译整理成通顺中文，保留关键数据、结论、背景和意义；英文摘要要全文翻译，不要省略；无摘要时根据标题合理展开\", "
                  "\"summary\": \"中文内容概要（150-250字）：假设读者打不开原文，仅凭概要就要完全理解这件事讲了什么、为什么重要\", "
                  "\"reason\": \"推荐理由（25字内）\", \"density\": \"高/中/低\"}。\n"
                  "信息密度定义：高=有实质技术、数据或产业信息；中=一般行业资讯；"
                  "低=营销稿、标题党、重复通告、无实质内容。\n" % CHANNELS[_CH]["domain"]["zh"] + listing)
        try:
            res = _sensenova_chat([{"role": "user", "content": prompt}], cfg)
        except Exception as e:
            log("[!] LLM 增强整批失败，降级逐条重试: %s" % e)
            # 逐条降级：单条请求更小、更快，坏条目不连累好条目
            for b in batch:
                try:
                    single_listing = _listing(b, 0)
                    single_prompt = prompt.rsplit(listing, 1)[0] + single_listing
                    sres = _sensenova_chat([{"role": "user", "content": single_prompt}], cfg, max_retries=2)
                    r = sres.get("0", sres.get(0))
                    if isinstance(r, dict):
                        done += _apply_enhance(b, r, lc)
                except Exception as e2:
                    log("[!] 单条增强失败，跳过: %s | %s" % (b.get("title", "")[:30], e2))
                time.sleep(0.5)
            continue
        for i, b in enumerate(batch):
            r = res.get(str(i), res.get(i))
            if not isinstance(r, dict):
                continue
            done += _apply_enhance(b, r, lc)
        time.sleep(1)
    # 同步到热点事件的代表报道
    by_url = {b["url"]: b for b in cands}
    for t in topics or []:
        rep = t.get("representative") or {}
        src = by_url.get(rep.get("url"))
        if src:
            for k in ("zh_full", "llm_summary", "llm_reason", "density"):
                if src.get(k):
                    rep[k] = src[k]
    log("[*] LLM 增强完成：%d 条" % done)
    return done


def _llm_score_once(batch, prompt_key, cfg):
    """用 prompts 段中的指定 prompt 独立打一次分，返回 {序号: 分数}。"""
    listing = "\n".join("[%d] %s | %s" % (i, b.get("title", ""), b.get("source", ""))
                        for i, b in enumerate(batch))
    prompt = _ch_prompt(prompt_key, cfg).replace("{listing}", listing)
    res = _sensenova_chat([{"role": "user", "content": prompt}], cfg)
    out = {}
    for i in range(len(batch)):
        v = res.get(str(i), res.get(i))
        try:
            s = float(v)
        except (TypeError, ValueError):
            continue
        out[i] = max(0.0, min(100.0, s))
    return out


def llm_double_score(items, topics, cfg):
    """LLM 两次独立打分（AIHOT 方法论）：同一评分对象用两种视角各打一次，
    取平均为 llm_score；平均分低于 tier 门槛的不进精选。失败降级，不阻断。"""
    lc = cfg["llm"]
    tiers = cfg["tiers"]
    cands = sorted(items, key=lambda i: i["score"], reverse=True)[:lc.get("max_score_items", 30)]
    cands = [c for c in cands if c["score"] >= 50]
    if not cands:
        return 0
    done = 0
    bs = max(1, lc["batch_size"])
    for s in range(0, len(cands), bs):
        batch = cands[s:s + bs]
        try:
            sa = _llm_score_once(batch, "score_a", cfg)
            time.sleep(1)
            sb = _llm_score_once(batch, "score_b", cfg)
        except Exception as e:
            log("[!] LLM 双打分本批失败，已跳过: %s" % e)
            continue
        for i, b in enumerate(batch):
            if i not in sa or i not in sb:
                continue
            a, c = sa[i], sb[i]
            avg = round((a + c) / 2, 1)
            b["llm_score_a"] = round(a, 1)
            b["llm_score_b"] = round(c, 1)
            b["llm_score"] = avg
            done += 1
        time.sleep(1)
    # 同步到热点事件的代表报道
    by_url = {b["url"]: b for b in cands if b.get("llm_score") is not None}
    for t in topics or []:
        rep = t.get("representative") or {}
        src = by_url.get(rep.get("url"))
        if src:
            rep["llm_score"] = src["llm_score"]
    log("[*] LLM 双打分完成：%d 条" % done)
    return done


def llm_extract(items, cfg):
    """LLM 结构化抽取：对入选条目抽取主体（公司/机构）、事件一句话、标签。
    存入 entities / event / tags 字段（只增字段）。失败降级，不阻断。"""
    lc = cfg["llm"]
    cands = [c for c in items if c.get("selected")]
    cands = sorted(cands, key=lambda i: i["score"], reverse=True)[:lc.get("max_extract_items", 20)]
    if not cands:
        return 0
    done = 0
    bs = max(1, lc["batch_size"])
    for s in range(0, len(cands), bs):
        batch = cands[s:s + bs]
        listing = "\n".join("[%d] %s | %s" % (i, b.get("title", ""), b.get("source", ""))
                            for i, b in enumerate(batch))
        prompt = _ch_prompt("extract", cfg).replace("{listing}", listing)
        try:
            res = _sensenova_chat([{"role": "user", "content": prompt}], cfg)
        except Exception as e:
            log("[!] LLM 结构化抽取本批失败，已跳过: %s" % e)
            continue
        for i, b in enumerate(batch):
            r = res.get(str(i), res.get(i))
            if not isinstance(r, dict):
                continue
            ents = r.get("entities")
            if isinstance(ents, list):
                b["entities"] = [str(x)[:30] for x in ents[:3] if str(x).strip()]
            ev = r.get("event")
            if ev:
                b["event"] = str(ev)[:60]
            tags = r.get("tags")
            if isinstance(tags, list):
                b["tags"] = [str(x)[:16] for x in tags[:3] if str(x).strip()]
            done += 1
        time.sleep(1)
    log("[*] LLM 结构化抽取完成：%d 条" % done)
    return done


def load_carried_channels(missing, generated):
    """把本次没有采集的频道，从上一次落盘的产物读回来。

    否则单频道运行（--channel tech）会写出一个只含 tech 的 dist/index.html：
    前端标签页仍按 CHANNEL_ORDER 渲染出 P/A/T 三个页签，点了却没反应；
    api/v1/index.json 也不再列出 physics/astro，而磁盘上那两个频道的 JSON
    还在（旧内容）。站点自相矛盾，且 --check 看不见——因为它只查文件在不在。
    """
    out = {}
    for ch_id in missing:
        ch_data = os.path.join(DATA_DIR, ch_id)
        try:
            with open(os.path.join(ch_data, "items.json"), encoding="utf-8") as f:
                items = (json.load(f) or {}).get("items", [])
            with open(os.path.join(ch_data, "hot-topics.json"), encoding="utf-8") as f:
                topics = (json.load(f) or {}).get("items", [])
            with open(os.path.join(ch_data, "daily.json"), encoding="utf-8") as f:
                daily = json.load(f)
            with open(os.path.join(ch_data, "dailies.json"), encoding="utf-8") as f:
                doc = json.load(f) or {}
                dailies = doc.get("dailies", doc) or {}
            with open(os.path.join(ch_data, "trends.json"), encoding="utf-8") as f:
                trends = json.load(f)
        except Exception as e:
            log("[!] [%s] 无法回读上次产物（%s），本次站点将不含该频道" % (ch_id, e))
            continue
        vintage = (items[0].get("discovered_at") if items else None) or "未知"
        log("[*] [%s] 本次未采集，沿用上次产物：%d 条（收录于 %s）"
            % (ch_id, len(items), str(vintage)[:19]))
        out[ch_id] = (items, topics, daily, dailies, trends)
    return out


def run_channel(ch_id, sources, args, generated):
    """运行单个频道的完整管线：采集→去重→分类→聚类→打分→日报→趋势。
    返回 (items, topics, daily, dailies, trends)。"""
    set_channel_context(ch_id)
    ch_sources = {"rss": [c for c in sources.get("rss", []) if c.get("channel", "tech") == ch_id],
                  "html": [c for c in sources.get("html", []) if c.get("channel", "tech") == ch_id]}
    n_src = len(ch_sources["rss"]) + len(ch_sources["html"])
    log("[*] 频道 %s（%s）：%d 个源，开始采集（每源上限 %d 条）..." % (
        ch_id, ch_name(ch_id), n_src, args.limit))
    raw, failed = collect(ch_sources, args.limit, args.skip_rss, args.skip_html)
    log("[*] [%s] 原始条目合计 %d 条（%d/%d 个源失败）" % (ch_id, len(raw), len(failed), n_src))
    _RUN_STATS[ch_id] = {"n_src": n_src, "failed": list(failed), "raw": len(raw)}
    # 有配置源却一条都没拿到 = 整频道抓取失败。此时继续写出会用空数据覆盖线上，
    # 页面 200 但内容为空，比 404 更难被发现；直接中止，让 CI 变红而不是提交空站点。
    if n_src and not raw:
        raise RuntimeError("[%s] %d 个源全部失败，拒绝写出空数据" % (ch_id, n_src))

    source_weight = {}
    global _SOURCE_TIER
    _SOURCE_TIER = {}
    for stype in ("rss", "html"):
        for cfg in ch_sources.get(stype, []):
            source_weight[cfg["name"]] = cfg.get("weight", 0.8)
            _SOURCE_TIER[cfg["name"]] = cfg.get("tier") or CONFIG["tiers"].get("default", "media")
    _CHANNEL_TIERS[ch_id] = dict(_SOURCE_TIER)

    items = []
    seen = set()
    for r in raw:
        title = r["title"]
        # arXiv 标题含 LaTeX，做展示层清理
        if "arxiv" in (r.get("source") or "").lower():
            title = clean_latex(title)
        k = norm_title(title)
        if k in seen:
            continue
        seen.add(k)
        items.append({
            "id": make_id(title, r["url"]),
            "title": title,
            "url": r["url"],
            "channel": ch_id,
            "source": r["source"],
            "source_base": r.get("source_base") or r["source"],
            "source_type": r["source_type"],
            "category": classify(title, r["source"]),
            "published_at": r.get("published_at"),
            "discovered_at": generated.isoformat(),
            "summary": r.get("summary"),
            "keywords": extract_keywords(title),
            "biz": extract_biz(title) if r["source"] in BIZ_SOURCES else None,
            "score": 0.0,
        })
    log("[*] [%s] 去重后 %d 条" % (ch_id, len(items)))

    # 政策/招投标：仅 T（光电）频道；有界抓取详情页（失败不影响整体）
    if ch_id == "tech":
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
        log("[*] [%s] 政策/招投标详情解析完成（命中 %d 条）" % (ch_id, sum(1 for it in items if it.get("biz"))))

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
            llm_double_score(items, topics, CONFIG)
            llm_extract(items, CONFIG)
        except Exception as e:
            log("[!] [%s] LLM 增强异常，已跳过: %s" % (ch_id, e))

    daily = build_daily(items, topics, generated)
    existing_dailies = {}
    _dp = os.path.join(DATA_DIR, ch_id, "dailies.json")
    # 兼容旧版扁平位置：首次运行时自动迁移 tech 频道的历史归档
    _old_dp = os.path.join(DATA_DIR, "dailies.json")
    if not os.path.exists(_dp) and ch_id == "tech" and os.path.exists(_old_dp):
        try:
            os.makedirs(os.path.dirname(_dp), exist_ok=True)
            import shutil as _sh
            _sh.copyfile(_old_dp, _dp)
            log("[*] [%s] 已从旧位置迁移历史日报归档" % ch_id)
        except Exception as e:
            log("[!] [%s] 归档迁移失败: %s" % (ch_id, e))
    if os.path.exists(_dp):
        try:
            with open(_dp, encoding="utf-8") as _f:
                existing_dailies = (json.load(_f) or {}).get("dailies", {}) or {}
        except Exception as e:
            # 归档损坏时绝不当成"没有历史"：那会让下一次写出把上百天日报永久抹掉。
            # 备份坏文件、中止本频道写出，人工可恢复。
            log("[x] [%s] 日报归档无法解析，拒绝以空历史覆盖：%s" % (ch_id, e))
            try:
                bad = _dp + ".corrupt-%s" % now_utc().strftime("%Y%m%dT%H%M%SZ")
                shutil.copyfile(_dp, bad)
                log("[!] [%s] 坏归档已备份为 %s" % (ch_id, os.path.basename(bad)))
            except Exception as e2:
                log("[!] [%s] 坏归档备份失败：%s" % (ch_id, e2))
            raise RuntimeError("日报归档损坏，已中止以免覆盖历史：%s" % _dp)
    dailies = build_dailies(items, existing_dailies)
    trends = build_trends(dailies, generated, CONFIG)
    log("[*] [%s] 趋势聚合完成：本周新事件 %d 个，持续发酵 %d 个" %
        (ch_id, len(trends["newTopics"]), len(trends["sustainedTopics"])))

    # 可选生图（默认关闭；失败自动降级，不阻断）
    if args.images:
        try:
            generate_images(topics, dailies, generated, CONFIG, ch_id)
        except Exception as e:
            log("[!] [%s] 生图模块异常，已跳过: %s" % (ch_id, e))

    log("[*] [%s] 完成。热点榜 TOP5：" % ch_id)
    for t in topics[:5]:
        log("    #%d %s (来源 %d · 信号 %d · 热度 %.0f)" % (
            t["rank"], t["title"][:50], t["source_count"], t["signal_count"], t["score"]))
    return items, topics, daily, dailies, trends


# ---------------- 契约自检（CI 与本地发布前把关） ----------------
# 背景：三频道重构把产物路径从 api/v1/*.json 改成 api/v1/<ch>/*.json，但没有任何
# 检查发现"已发布消费者的地址全部 404"，README/Skill 也继续写老地址。
# 这里把"对外承诺的端点必须真实存在且形状正确"固化成可执行断言。
def expected_flat_endpoints():
    """重构前就发布、至今仍被外部消费者使用的扁平地址。"""
    return ["api/v1/index.json", "api/v1/openapi.json", "api/v1/items.json",
            "api/v1/hot-topics.json", "api/v1/dailies.json", "api/v1/daily.json",
            "api/v1/stories.json", "api/v1/trends.json",
            "data/items.json", "data/hot-topics.json", "data/dailies.json",
            "data/report.csv", "feed.xml", "llms.txt", "index.html"]


def expected_channel_endpoints(ch_id):
    return ["api/v1/%s/items.json" % ch_id, "api/v1/%s/hot-topics.json" % ch_id,
            "api/v1/%s/dailies.json" % ch_id, "api/v1/%s/daily.json" % ch_id,
            "api/v1/%s/stories.json" % ch_id, "api/v1/%s/trends.json" % ch_id]


def inline_style_block(html):
    """取 <style>…</style> 之间的内联 CSS；没有则返回 None。"""
    i = html.find("<style")
    if i < 0:
        return None
    i = html.find(">", i)
    if i < 0:
        return None
    j = html.find("</style>", i)
    if j < 0:
        return None
    return html[i + 1:j]


def check_inline_css(css):
    """内联 CSS 必须是真换行的原始样式，不能是被二次转义的字符串。

    2026-10-12 线上事故：某次手工 wrangler 部署上传的 index.html 里，整段 CSS 的
    换行变成了字面量 \\n（反斜杠+n），浏览器把每一行当成一个畸形声明全部丢弃，
    站点退化成无样式裸 HTML。而 --check 当时只查"文件在不在 + 快照 JSON 能不能解析"，
    完全看不见这类"文件存在但内容坏了"的产物，所以坏部署顺利上线。
    """
    problems = []
    if css is None:
        return ["dist/index.html 找不到内联 <style> 块（页面会完全没有样式）"]
    # 字面量 \n：真换行被转义的直接证据（app.css 里没有、也不该有这种写法）
    lit = css.count("\\n")
    if lit:
        problems.append("dist/index.html 内联 CSS 里有 %d 处字面量 \\n（换行被二次转义），"
                        "浏览器会丢弃全部样式——线上会变成裸 HTML" % lit)
    if "\n" not in css:
        problems.append("dist/index.html 内联 CSS 没有任何真换行，疑似整段被压成字符串")
    # 花括号不配对 = CSS 被截断或转义到结构破坏
    if css.count("{") != css.count("}"):
        problems.append("dist/index.html 内联 CSS 花括号不配对（{ %d / } %d），样式表已损坏"
                        % (css.count("{"), css.count("}")))
    return problems


def check_contract(verbose=True):
    """返回问题列表；空列表表示对外契约完整。"""
    problems = []

    def need(rel, why):
        p = os.path.join(DIST_DIR, rel.replace("/", os.sep))
        if not os.path.exists(p):
            problems.append("缺失 %s（%s）" % (rel, why))

    for rel in expected_flat_endpoints():
        need(rel, "重构前已发布的对外地址，缺了就是线上 404")
    for ch_id in CHANNEL_ORDER:
        for rel in expected_channel_endpoints(ch_id):
            need(rel, "频道 API")

    # 形状契约：api/v1/dailies.json 是裸日期字典（线上现状，消费者依赖它）
    p = os.path.join(DIST_DIR, "api", "v1", "dailies.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                doc = json.load(f)
            if "dailies" in doc or "schemaVersion" in doc:
                problems.append("api/v1/dailies.json 形状变了（消费者按裸日期字典读取）")
        except Exception as e:
            problems.append("api/v1/dailies.json 解析失败: %s" % e)

    p = os.path.join(DIST_DIR, "api", "v1", "items.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                doc = json.load(f)
            for k in ("schemaVersion", "generatedAt", "count", "items"):
                if k not in doc:
                    problems.append("api/v1/items.json 缺少字段 %s" % k)
        except Exception as e:
            problems.append("api/v1/items.json 解析失败: %s" % e)

    # RSS：日期必须 RFC 822，<link> 必须是阅读器可解析的绝对地址
    p = os.path.join(DIST_DIR, "feed.xml")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            txt = f.read()
        if re.search(r"<pubDate>\d{4}-\d{2}-\d{2}T", txt):
            problems.append("feed.xml 的 pubDate 仍是 ISO 格式（阅读器会当成无日期）")
        lk = re.search(r"<link>([^<]*)</link>", txt)
        if lk and not lk.group(1).startswith("http"):
            problems.append("feed.xml 的 <link> 不是绝对地址: %r" % lk.group(1))

    # 对外文档不能残留改名前的死链或相对地址
    p = os.path.join(DIST_DIR, "llms.txt")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            txt = f.read()
        if "opto-hot" in txt:
            problems.append("llms.txt 仍指向已改名的旧仓库地址")
        if "./api/v1" in txt:
            problems.append("llms.txt 仍使用相对地址，Agent 无法直接请求")

    if REPO_URL and "opto-hot" in REPO_URL:
        problems.append("REPO_URL 指向旧仓库名")
    if not SITE_BASE.startswith("https://"):
        problems.append("SITE_BASE 必须是 https 绝对地址")

    # 单页快照必须含全部频道：此前 --channel tech 重跑会写出"导航有三个页签、
    # S.channels 只有 tech"的残缺站点，而上面只查文件在不在的检查看不见它。
    p = os.path.join(DIST_DIR, "index.html")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            html = f.read()
        # 内联 CSS 完整性：文件存在但样式被转义坏掉，同样等于线上事故。
        problems.extend(check_inline_css(inline_style_block(html)))
        snap = snapshot_of_html(html)
        if snap is None:
            problems.append("dist/index.html 里找不到可解析的内嵌快照 const S = …")
        else:
            have = set((snap.get("channels") or {}).keys())
            want = set(CHANNEL_ORDER)
            if have != want:
                problems.append("dist/index.html 缺频道数据 %s（导航仍会显示它们）"
                                % "、".join(sorted(want - have)))
            for cid, chd in (snap.get("channels") or {}).items():
                if not (chd.get("items") or []):
                    problems.append("dist/index.html 频道 %s 的 items 为空" % cid)

    if verbose:
        if problems:
            log("[!] 契约自检发现 %d 个问题:" % len(problems))
            for x in problems:
                log("      - " + x)
        else:
            log("[*] 契约自检通过：扁平兼容地址 + 三频道地址全部就位")
    return problems


# ---------------- 线上回读自检（部署完成 ≠ 内容正确） ----------------
# 背景：2026-10-12 事故——pages.dev 上跑的 index.html 内联 CSS 换行被转义成字面量
# \n，且是重构前的旧产物；本地产物一直是好的，--check 只查本地，两者都看不见
# "线上部署错了"这一整类故障。这里把同源断言用到从线上读回的页面上。
# (地址, 是否容忍数据落后)：GitHub Pages 由 CI 每次部署，落后=传播坏了，硬失败；
# pages.dev 按设计只在手动 wrangler 发布时更新，数据落后只是提示，但样式坏掉仍是硬失败。
LIVE_CHECK_TARGETS = [
    ("https://pat-hot.pages.dev/", True),
    (SITE_BASE + "index.html", False),
]


def _iso_or_none(s):
    try:
        return datetime.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None


def snapshot_of_html(html):
    """取内嵌快照 const S = {...} 的 dict；取不到返回 None。

    ;\\r?\\n 两种换行都要认：本地产物在 Windows 上是 CRLF，文本模式读会翻译成 \\n，
    但从线上二进制 decode 回来的保留 \\r\\n——只写 ;\\n 会把好页面误判成"无快照"。
    """
    m = re.search(r"const S = (.*?);\r?\n", html, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1).replace("<\\/", "</"))
    except Exception:
        return None


def check_live_html(html, label, local_generated=None, allow_stale=False):
    """对一份"从线上读回来的 index.html"跑与 --check 同源的断言。
    返回 (problems, warnings)：allow_stale 时"数据落后"降级为警告。"""
    problems = []
    warnings = []
    for x in check_inline_css(inline_style_block(html)):
        problems.append("[%s] %s" % (label, x))
    snap = snapshot_of_html(html)
    if snap is None:
        problems.append("[%s] 找不到可解析的内嵌快照 const S（多半是旧版产物）" % label)
        return problems, warnings
    have = set((snap.get("channels") or {}).keys())
    want = set(CHANNEL_ORDER)
    if have != want:
        problems.append("[%s] 线上频道 %s，缺 %s（部署的是旧产物或残缺产物）"
                        % (label, sorted(have), "、".join(sorted(want - have)) or "无"))
    live_gen = _iso_or_none(snap.get("generatedAt"))
    if live_gen is None:
        problems.append("[%s] 快照没有可解析的 generatedAt" % label)
    elif local_generated and live_gen < local_generated:
        msg = ("[%s] 线上 generatedAt=%s 落后于本地 dist=%s（本地产物没部署上去）"
               % (label, live_gen.isoformat(), local_generated.isoformat()))
        (warnings if allow_stale else problems).append(msg)
    return problems, warnings


def local_dist_generated():
    """本地 dist/index.html 的 generatedAt；读不到返回 None。"""
    p = os.path.join(DIST_DIR, "index.html")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            snap = snapshot_of_html(f.read())
    except Exception:
        return None
    return _iso_or_none((snap or {}).get("generatedAt"))


def check_live(targets=None, timeout=30, verbose=True):
    """拉取线上页面回读自检；返回 (problems, warnings)。
    problems 为空表示线上内容健康（GitHub Pages 侧不落后于本地产物）。"""
    targets = targets or LIVE_CHECK_TARGETS
    local_gen = local_dist_generated()
    problems = []
    warnings = []
    for u, allow_stale in targets:
        try:
            req = urllib.request.Request(
                u, headers={"User-Agent": "pat-hot-check-live/1.0 (+github.com/sun-zihang/pat-hot)"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
            html = body.decode("utf-8", "replace")
        except Exception as e:
            problems.append("[%s] 拉取失败: %s" % (u, e))
            continue
        found, warns = check_live_html(html, u, local_gen, allow_stale=allow_stale)
        problems.extend(found)
        warnings.extend(warns)
        if verbose:
            log("[*] 回读 %s（%d 字节）：%s"
                % (u, len(body), "OK" if not (found or warns)
                   else ("发现 %d 个问题" % len(found) if found else "%d 个警告" % len(warns))))
    if verbose:
        if not problems and not warnings:
            log("[*] 线上回读自检通过：样式完整、频道齐全、不落后于本地产物")
    return problems, warnings


def main():
    ap = argparse.ArgumentParser(description="PAT-HOT 三频道热点统计采集器（物理/天文/光电）")
    ap.add_argument("--channel", choices=["tech", "physics", "astro", "all"], default="all",
                    help="运行哪个频道（默认 all：三个频道依次跑）")
    ap.add_argument("--limit", type=int, default=25, help="每个源最多取多少条 (默认 25)")
    ap.add_argument("--topics", type=int, default=10, help="热点榜输出条数 (默认 10)")
    ap.add_argument("--skip-rss", action="store_true", help="跳过 RSS 源")
    ap.add_argument("--skip-html", action="store_true", help="跳过 HTML 站")
    ap.add_argument("--llm", action="store_true",
                    help="启用可选 LLM 增强（商汤日日新 SenseNova）：中文内容概要/推荐理由/信息密度。"
                         "需设置环境变量 SENSENOVA_API_KEY；不传此时零依赖运行")
    ap.add_argument("--images", action="store_true",
                    help="启用可选生图（SenseNova U1.5 Lite 文生图，去水印）：为日报头条+热点 Top5 生成配图。"
                         "需设置环境变量 SENSENOVA_API_KEY；失败自动降级为无图")
    ap.add_argument("--check", action="store_true",
                    help="只运行对外契约自检（不采集、不写文件）：确认扁平兼容地址与"
                         "三频道地址都存在且形状正确；有问题时以非零退出码结束。CI 用它在部署前把关。")
    ap.add_argument("--check-live", action="store_true",
                    help="回读线上页面做同源断言（内联 CSS 完整性 + 频道齐全 + 不落后于本地 dist）。"
                         "部署完成不等于内容正确：CI 的 deploy-pages 步骤成功不代表 wrangler 那边"
                         "的 pages.dev 也发了同一份产物。有问题时以非零退出码结束。")
    ap.add_argument("--live-url", action="append", default=None, metavar="URL",
                    help="配合 --check-live：只回读指定地址，可重复；默认回读 pages.dev 与 GitHub Pages。")
    args = ap.parse_args()

    if args.check:
        # 只做契约自检（CI 发布前 gate）：不采集、不写文件
        return 1 if check_contract() else 0

    if args.check_live:
        targets = [(u, False) for u in args.live_url] if args.live_url else None
        found, warns = check_live(targets=targets)
        for w in warns:
            log("[~] " + w)
        if found:
            log("[!] 线上回读自检发现 %d 个问题:" % len(found))
            for x in found:
                log("      - " + x)
            return 1
        return 0

    with open(SOURCES_PATH, encoding="utf-8") as f:
        sources = json.load(f)

    generated = now_utc()
    ch_list = CHANNEL_ORDER if args.channel == "all" else [args.channel]
    results = {}
    for ch_id in ch_list:
        results[ch_id] = run_channel(ch_id, sources, args, generated)

    # 未采集的频道沿用上次产物，避免单频道运行写出"标签页有三个、数据只有一个"的残缺站点
    missing = [c for c in CHANNEL_ORDER if c not in results]
    if missing:
        results.update(load_carried_channels(missing, generated))
        for c in CHANNEL_ORDER:
            if c not in results:
                log("[x] 频道 %s 既未采集也无历史产物，无法产出完整站点" % c)
                return 1

    # 抓取健康度闸门：失败源占比过高时拒绝写出。
    # 半瘫的数据照样能让页面 200，比空页面更难察觉；宁可是 CI 红一次。
    n_all = sum(_RUN_STATS.get(c, {}).get("n_src", 0) for c in ch_list)
    n_bad = sum(len(_RUN_STATS.get(c, {}).get("failed", [])) for c in ch_list)
    if n_all:
        ratio = n_bad / float(n_all)
        max_ratio = (CONFIG.get("fetch", {}) or {}).get("max_source_failure_ratio", 0.6)
        log("[*] 抓取健康度：%d/%d 个源失败（%.0f%%），阈值 %.0f%%"
            % (n_bad, n_all, ratio * 100, max_ratio * 100))
        if ratio > max_ratio:
            log("[x] 失败源比例超过阈值，拒绝写出产物（exit 1）")
            return 1

    write_outputs(results, generated)
    log("[*] 全部完成。各频道条数：%s" % ", ".join(
        "%s=%d" % (c, len(results[c][0])) for c in ch_list))

    # 写完立即自检：契约不完整就不要让 CI 把坏产物提交/部署出去
    problems = check_contract()
    if problems:
        log("[x] 产物契约自检未通过，请修复后再提交（exit 1）")
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        sys.exit(130)