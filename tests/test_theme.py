# -*- coding: utf-8 -*-
"""主题与前端模板契约测试（纯标准库，无网络、无第三方依赖）。

单独成文件：这些断言针对 collector/templates/ 的前端模板，与 test_collect.py
锁的采集/输出契约是两回事。

锁住的回归：
1. 深色块必须覆盖浅色块的全部颜色 token —— 只往 :root 加 token 而忘了
   html[data-theme="dark"]，深色模式那处会回退成浅色值，出现"黑底白块"。
2. token 块之外不得残留硬编码颜色（.ava 是唯一被批准的例外，见下）。
3. 模板引用到的每个文案键，中英两套都要存在 —— "更多"页的收藏行曾渲染出
   undefined，因为 rows 里塞的是拼好的字面量而不是 i18n 键。
4. 路由表 / <section> / renderer 三处必须齐备，缺一处点了没反应。
"""
import io
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TPL = os.path.join(ROOT, "collector", "templates")


def _read(name):
    with io.open(os.path.join(TPL, name), encoding="utf-8") as f:
        return f.read()


CSS = _read("app.css")
JS = _read("app.js")
HTML = _read("app.html")

# 唯一批准的硬编码颜色：头像字母色。它压在 avaColor() 生成的 hsl 底上，
# 底色明度固定在 46% 左右，两种主题下白字对比度都够，跟随主题反而更差。
APPROVED_LITERAL_COLORS = {".ava": "#fff"}


def _block(css, start):
    i = css.index(start)
    return css[i:css.index("}", i)]


def _color_tokens(block):
    return dict(re.findall(r"(--[a-z0-9]+)\s*:\s*(#[0-9a-fA-F]{3,6})\s*[;}]", block))


def _i18n_body(lang):
    """花括号配对取出 I18N.zh / I18N.en 的对象体。

    注意锚定到行首：裸找 "en:" 会命中 "open:" 这类键名的尾部。
    """
    i = JS.index("const I18N = {")
    m = re.compile(r"^\s*%s:\s*\{" % lang, re.M).search(JS, i)
    assert m, "找不到 I18N.%s 段" % lang
    k = JS.index("{", m.start())
    depth = 0
    for pos in range(k, len(JS)):
        if JS[pos] == "{":
            depth += 1
        elif JS[pos] == "}":
            depth -= 1
            if depth == 0:
                return JS[k + 1:pos]
    raise AssertionError("I18N.%s 花括号不配对" % lang)


def _i18n_keys(lang):
    # 先把字符串字面量清空再取键名："Selection bar: official…" 这类值里的
    # 冒号会被 (词+冒号) 误认成键名 "bar"，键名永远在引号外。
    body = re.sub(r'"(?:[^"\\]|\\.)*"', '""', _i18n_body(lang))
    return set(re.findall(r"([A-Za-z][A-Za-z0-9]*)\s*:", body))


def _route_map():
    m = re.search(r"function router\(\).*?const map=\{(.*?)\};", JS, re.S)
    assert m, "找不到 router 的路由表"
    return dict(re.findall(r'"(/[a-z-]*)":"([a-z]+)"', m.group(1)))


class TestThemeTokenParity(unittest.TestCase):
    def test_both_theme_blocks_exist(self):
        self.assertIn(":root{", CSS)
        self.assertIn('html[data-theme="dark"]{', CSS)

    def test_dark_block_covers_every_light_color_token(self):
        light = _color_tokens(_block(CSS, ":root{"))
        dark = _color_tokens(_block(CSS, 'html[data-theme="dark"]{'))
        missing = sorted(k for k in light if k not in dark)
        self.assertEqual(missing, [],
                         "这些颜色 token 只在浅色块定义，深色模式会漏白：%s" % missing)

    def test_no_hardcoded_color_outside_token_blocks(self):
        body = CSS[CSS.index("}", CSS.index('html[data-theme="dark"]')) + 1:]
        found = []
        for m in re.finditer(r"#[0-9a-fA-F]{3,6}\b", body):
            sel = body[:m.start()].rsplit("{", 1)[0].rsplit("}", 1)[-1].strip()
            sel = sel.splitlines()[-1].strip() if sel else ""
            if APPROVED_LITERAL_COLORS.get(sel) == m.group(0):
                continue
            found.append((body[:m.start()].count("\n") + 1, sel, m.group(0)))
        self.assertEqual(found, [],
                         "模板残留硬编码颜色，深色模式会漏白：%s" % found)

    def test_approved_exception_is_still_just_the_avatar(self):
        """例外清单不许悄悄长大。"""
        self.assertEqual(len(APPROVED_LITERAL_COLORS), 1)

    def test_theme_bootstrap_is_in_head(self):
        """首屏前必须把 data-theme 落到 <html>，否则深色模式先闪一屏浅色。"""
        head = HTML[:HTML.index("</head>")]
        self.assertIn("pat-theme", head)
        self.assertIn('setAttribute("data-theme"', head)
        self.assertIn("prefers-color-scheme: dark", head)

    def test_theme_toggle_button_exists(self):
        self.assertIn('id="theme"', HTML)
        self.assertIn("setTheme", JS)


class TestI18nKeyCompleteness(unittest.TestCase):
    def test_zh_and_en_have_same_keys(self):
        zh, en = _i18n_keys("zh"), _i18n_keys("en")
        self.assertEqual(sorted(zh - en), [], "这些键只有中文有")
        self.assertEqual(sorted(en - zh), [], "这些键只有英文有")
        self.assertGreater(len(zh), 40)

    def test_referenced_copy_keys_exist(self):
        zh = _i18n_keys("zh")
        used = set(re.findall(r"\bT\.([A-Za-z][A-Za-z0-9]*)", JS))
        used |= set(re.findall(r'data-i18n="([A-Za-z][A-Za-z0-9]*)"', HTML))
        missing = sorted(used - zh)
        self.assertEqual(missing, [], "引用了不存在的文案键：%s" % missing)

    def test_more_menu_rows_use_i18n_keys(self):
        """每行标题必须是 i18n 键。

        回归：收藏行曾把 LANG 三元表达式塞进副标题位，而 renderMore 用
        T[r[2]] 取值，页面渲染出 "undefined"。
        """
        m = re.search(r"function renderMore\(\).*?const rows=(\[.*?\]);", JS, re.S)
        self.assertIsNotNone(m, "找不到 renderMore 的 rows 定义")
        rows_src = m.group(1)
        self.assertNotIn("LANG===", rows_src, "rows 里不要拼语言分支，交给 i18n")
        zh = _i18n_keys("zh")
        for lit in re.findall(r'"([A-Za-z][A-Za-z0-9]*)"', rows_src):
            self.assertIn(lit, zh, "rows 引用了未知文案键 %s" % lit)


class TestShellLocalization(unittest.TestCase):
    """页面外壳（<head> / 页头 / 页脚 / 相对时间）必须随语言切换。

    回归（2026-10-14 浏览器实测 EN 模式）：切到英文后，标签页标题、
    <html lang>、meta description、频道导航 aria-label、页脚"生成于 …"、
    卡片元信息行的"收录 N 小时前"、日报标题"2026年10月13日 · 周二"、
    以及接口表里写死的"LLM 友好入口 / RSS（T 光电主 feed）"全是中文。
    这些文案不在 data-i18n 上（在 <head> 里或属性上），所以 tr() 必须
    单独收口；漏一处，EN 页面就在标签页 / 无障碍标签 / 页脚里混出中文。
    """

    def _fn(self, name):
        i = JS.index("function %s(" % name)
        j = re.search(r"\nfunction ", JS[i + 10:]).start() + i + 10
        return JS[i:j]

    def test_tr_sets_lang_title_meta_aria_gen(self):
        tr = self._fn("tr")
        self.assertIn('document.documentElement.lang', tr,
                      "tr() 不再改 <html lang>：EN 页面语言标记仍是 zh-CN")
        self.assertIn("document.title", tr, "tr() 不再改标签页标题")
        self.assertIn("meta[name=", tr, "tr() 不再改 meta description")
        self.assertIn('og:title', tr, "tr() 不再改 og:title")
        self.assertIn('setAttribute("aria-label"', tr, "tr() 不再改频道导航 aria-label")
        self.assertIn(".gen", tr, "tr() 不再填页脚生成时间：.gen 会空掉或永远是中文")

    def test_footer_gen_uses_data_attribute(self):
        # 外壳文案进词典后，构建时间戳放 data-gen，由 tr() 按语言拼；
        # __GEN__ 仍必须原样出现在模板里（构建时替换），否则产物会缺时间。
        self.assertIn('data-gen="__GEN__"', HTML,
                      "页脚生成时间不再用 data-gen=\"__GEN__\"：改回写死中文就会漏翻译")
        self.assertEqual(HTML.count("__GEN__"), 1, "__GEN__ 必须恰好出现一次")

    def test_shell_copy_keys_exist_in_both_langs(self):
        zh, en = _i18n_keys("zh"), _i18n_keys("en")
        for k in ("pageTitle", "pageDesc", "ogTitle", "ogDesc",
                  "channelAria", "genAt", "colon"):
            self.assertIn(k, zh, "外壳文案键 %s 只有英文有或缺中文" % k)
            self.assertIn(k, en, "外壳文案键 %s 缺英文" % k)

    def test_relative_time_is_language_aware(self):
        rel = self._fn("fmtRel")
        self.assertIn('LANG==="en"', rel,
                      "fmtRel 又不分语言了：EN 下卡片与数据页会显示「N 小时前」")
        self.assertIn("ago", rel, "fmtRel 缺英文分支")

    def test_pub_label_is_language_aware(self):
        pub = self._fn("pubLabel")
        self.assertIn('LANG==="en"', pub,
                      "pubLabel 又不分语言：EN 卡片元信息行会漏出「发布 / 收录」")

    def test_score_tooltip_is_language_aware(self):
        """AI 双打分卡的 tooltip 分语言。

        回归（卡片子树属性扫描——此前的浏览器漏译扫描器跳过了 .icard）：
        scoreEl 的 title 曾写死 (llm?"AI 双打分均值":"score")+" / 100"，
        EN 下每张 AI 打分卡悬停都漏中文。" / 100" 语言中立可留，
        短语必须换成 T.aiScore，且词典里中英各就各位。
        """
        se = self._fn("scoreEl")
        self.assertIn("T.aiScore", se,
                      "scoreEl 的 AI tooltip 又写死中文：EN 卡片悬停漏「AI 双打分均值」")
        self.assertNotIn("双打分均值", se, "scoreEl 函数体里不该再出现中文字面量")
        # 用 _i18n_body 的行首锚定取段，别用裸 "en:"——它会命中值里的英文冒号。
        for lang, want_cjk in (("zh", True), ("en", False)):
            body = _i18n_body(lang)
            m = re.search(r'aiScore:"((?:[^"\\]|\\.)*)"', body)
            self.assertTrue(m, "%s 段找不到 aiScore" % lang)
            has = bool(re.search(r"[\u4e00-\u9fff]", m.group(1)))
            if want_cjk:
                self.assertTrue(has, "aiScore 的中文值丢了：ZH 卡片 tooltip 会变英文")
            else:
                self.assertFalse(has, "aiScore 的英文值混进中文：EN tooltip 又漏了")

    def test_agent_page_has_no_hardcoded_chinese_chrome(self):
        """接口页表格说明必须走词典或双语三元，不能写死中文。

        注意不能一刀切禁中文：中文分支本来就该含「RSS（T 光电主 feed）」，
        所以按行查——出现中文的那一行必须同时有英文分支。
        """
        i = JS.index("function renderAgent")
        body = JS[i:JS.index("function renderMore")]
        lines = body.splitlines()
        rss = [ln for ln in lines if "主 feed）" in ln]
        self.assertTrue(rss, "renderAgent 里找不到 RSS 主 feed 说明行，结构变了")
        for ln in rss:
            self.assertIn('LANG==="en"', ln,
                          "RSS 主 feed 说明没有英文分支：EN 下这一格会漏中文")
            self.assertIn("RSS (main feed", ln, "RSS 主 feed 说明的英文分支没了")
        self.assertFalse([ln for ln in lines if "友好入口" in ln],
                         "renderAgent 又写死了「LLM 友好入口」，应改用 T.llmsEntry")
        self.assertIn("T.llmsEntry", body, "llms.txt 说明不再引用 T.llmsEntry")

    def test_daily_title_rebuilt_in_en(self):
        # rep.label / rep.weekday 是采集端写死的中文，EN 下必须按 date 重排。
        # 逐行查 dLabel 与 dWeek：只查整段有没有 LANG 会被另一个变量蒙过——
        # 变异测试里把 dLabel 单独改回 rep.label，段级检查照样绿。
        i = JS.index("function renderDaily")
        body = JS[i:JS.index("function renderTopics")]
        dl = [ln for ln in body.splitlines() if "const dLabel=" in ln]
        dw = [ln for ln in body.splitlines() if "const dWeek=" in ln]
        self.assertEqual(len(dl), 1, "dLabel 定义行找不到或不止一处，日报标题结构变了")
        self.assertEqual(len(dw), 1, "dWeek 定义行找不到或不止一处")
        self.assertIn('LANG==="en"', dl[0],
                      "dLabel 不再分语言：EN 下日报标题会是采集端写死的「2026年10月13日」")
        self.assertIn('LANG==="en"', dw[0],
                      "dWeek 不再分语言：EN 下日报标题的星期会是写死的「周二」")
        self.assertIn("wdCN(rep.date)", dw[0], "EN 日报标题没有用 wdCN(date) 重算星期")
        self.assertIn("esc(dLabel)", body, "dtitle 不再输出 dLabel")
        self.assertIn("esc(dWeek)", body, "dtitle 不再输出 dWeek")


class TestViewWiring(unittest.TestCase):
    def test_every_route_has_section_and_renderer(self):
        for path, view in _route_map().items():
            self.assertIn('id="view-%s"' % view, HTML,
                          "路由 %s 没有对应的 view-%s section" % (path, view))
            self.assertRegex(JS, r"renderers\.%s\s*=" % view,
                             "视图 %s 没注册 renderer，点了白屏" % view)

    def test_nav_targets_are_routed(self):
        routes = set(_route_map().keys())
        routes.add("/")  # #/ 与空 hash 都落到精选
        for h in set(re.findall(r'href="#(/[a-z-]*)"', HTML)):
            self.assertIn(h, routes, "导航指向 %s，路由表里没有" % h)
        for h in set(re.findall(r'location\.hash="#(/[a-z-]*)"', JS)):
            self.assertIn(h, routes, "代码跳转到 %s，路由表里没有" % h)

    def test_data_i18n_targets_are_known(self):
        zh = _i18n_keys("zh")
        for k in set(re.findall(r'data-i18n="([A-Za-z][A-Za-z0-9]*)"', HTML)):
            self.assertIn(k, zh)

    def test_favorites_are_viewable(self):
        """收藏写进 localStorage 后必须有地方看，否则星标是死功能。"""
        self.assertIn('lsGet("pat-fav")', JS)
        self.assertIn("function renderFav", JS)
        self.assertEqual(_route_map().get("/fav"), "fav")


class TestLocalBackup(unittest.TestCase):
    """收藏/已读/设置的导出导入备份（AIHOT：只存本机，但可以导出、导入备份）。

    锁住的回归：
    1. LS_KEYS 必须与实际使用的 localStorage 键一致——少一个键，那份数据
       就悄悄不在备份里，用户换设备后才发现"已读丢了"。
    2. 导入必须校验 app 标记，坏文件/别的站的文件一律不动现场。
    3. 导入成功后必须热重载 READ/FAV 并刷新页面——只写 localStorage 不重载
       等于导入了但看不见。
    """

    def test_ls_keys_cover_every_used_key(self):
        m = re.search(r"const LS_KEYS = \[(.*?)\];", JS)
        self.assertIsNotNone(m, "找不到 LS_KEYS")
        declared = set(re.findall(r'"([^"]+)"', m.group(1)))
        used = set(re.findall(r'lsGet\("([^"]+)"\)|lsSet\("([^"]+)"|localStorage\.get(?:Item|).?\("([^"]+)"\)|localStorage\.setItem\("([^"]+)"', JS))
        used = {x for tup in used for x in tup if x}
        # pat-theme 由 <head> 引导脚本与 setTheme 直接读写
        used |= {"pat-theme"}
        missing = sorted(used - declared)
        self.assertEqual(missing, [], "这些键在用却不在备份清单里：%s" % missing)

    def test_import_validates_app_marker(self):
        self.assertIn('o.app !== "PAT-HOT"', JS, "导入必须校验文件来源")
        self.assertIn("badFile", JS)

    def test_import_reloads_state(self):
        i = JS.index("function applyBackup")
        body = JS[i:JS.index("function pickBackupFile")]
        self.assertIn('READ = lsGet("pat-read")', body)
        self.assertIn('FAV = lsGet("pat-fav")', body)
        self.assertIn("location.reload()", body, "导入后必须刷新，否则界面还读旧值")

    def test_import_never_touches_users_file(self):
        # 回归：初版曾调 f.remove()——那会删用户磁盘上的真备份文件。
        # 只允许移除临时 <input> 元素本身（inp.remove()）。
        i = JS.index("function pickBackupFile")
        body = JS[i:i + 900]
        self.assertNotIn("f.remove", body, "绝不允许删除用户的备份文件")
        self.assertIn("inp.remove()", body, "临时 input 用完要从 DOM 摘掉")


class TestTemplatePlaceholders(unittest.TestCase):
    def test_html_placeholders_present_exactly_once(self):
        for ph in ("/*__CSS__*/", "/*__JS__*/"):
            self.assertEqual(HTML.count(ph), 1, ph)

    def test_js_snapshot_placeholder(self):
        self.assertEqual(JS.count("__SNAPSHOT__"), 1)
        self.assertIn("const S = __SNAPSHOT__;", JS)

    def test_generated_marker_is_replaced_by_build(self):
        # __GEN__ 只应出现在模板里，构建时替换
        self.assertIn("__GEN__", HTML)


class TestSearchReachability(unittest.TestCase):
    """搜索框此前只在 #/all 有反应：别的视图里打字像坏了。"""

    def test_input_navigates_to_all_view(self):
        self.assertRegex(JS, r"function bind\(\)[\s\S]*?gotoAll[\s\S]*?#/all",
                         "搜索输入应跳转到全部页")

    def test_enter_submits_search(self):
        self.assertRegex(JS, r'q\.addEventListener\("keydown"[\s\S]{0,200}Enter',
                         "回车应提交搜索")


if __name__ == "__main__":
    unittest.main()
