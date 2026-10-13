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
