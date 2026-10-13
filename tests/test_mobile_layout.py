# -*- coding: utf-8 -*-
"""移动端版式契约测试（纯标准库，无网络、无第三方依赖）。

单独成文件：锁的是 collector/templates/ 里"窄屏下东西放不放得下"这一件事，
和 test_scroll_contract.py 的滑动位置、test_theme.py 的主题都不相干。

锁住的回归（2026-10-13 浏览器实测，320/360/390/430px × 10 条路由）：

1. 顶栏横向溢出。.top-in 是 flex 且子项都不收缩（.logo/.chseg a/.seg a 全是
   white-space:nowrap），一行的固有宽度是 478px。实测 320~430px 下
   document.scrollWidth 恒等于 478，整页横向滚动，主题（◐）和 EN 两个按钮
   被挤出屏幕外——用户看不到，也点不到。收窄子项治不了：即使把内边距压到
   5px 8px、把中文标签藏掉，也还是 478。
2. 页脚被标签栏压住。.tabbar 是 position:fixed、高 66px，而 footer 在 .wrap
   之外，拿不到 .wrap 的 96px 下内边距：滚到底时最后 66px（含"生成于 …"那行）
   整段压在标签栏底下，等于没写。
3. 元信息行折行。.irow 里的来源名和发布时间没有 nowrap，360px 实测 .isrc 高 42、
   .itime 高 38，各占两行，卡片被撑高、看起来像排版坏了。
4. 表格被挤成竖排。auto 表格的最小宽度由最长不可断行片段决定：320px 下卡片
   内宽只有 250，而「api/v1/tech/hot-topics.json」这类接口路径放不下，浏览器
   就把列挤到一两个字符宽——实测「7 小时」竖排成三行。更隐蔽的是 .mono 上的
   接口路径会把文档最小宽度撑到 370，整页横向滚动，但只在智能体页出现。
5. 点不中的小目标。星标 17×20、xbtn/obtn 高 33、upill 高 30、日期折叠头高 38，
   都低于 44 的触摸下限；星标是收藏的唯一入口，点不中就等于没有这个功能。
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

# tabbar 的实际高度：.tabbar 的上下内边距 6+8，加一行图标 22 + 间距 3 + 文字 11
# 的行盒，实测 66px（390px 视口）。
TABBAR_H = 66


def _css_rules(css):
    """[(selector, declarations)]，注释先剥掉——注释里提到属性名不算用。"""
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [(m.group(1).strip(), m.group(2))
            for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", body, re.S)]


def _decls(selector):
    """某条选择器的声明串；没找到返回 ""。选择器按原样精确匹配。"""
    for sel, decl in _css_rules(CSS):
        if sel == selector:
            return decl
    return ""


def _media(condition):
    """@media 块内部的规则串，用花括号配平取，正则做不到嵌套。

    直接对全文跑 _css_rules 会把 @media 的括号当成规则的边界，
    于是「footer 在窄屏下补了下内边距」这件事会读成不存在。
    """
    out = []
    for m in re.finditer(r"@media\s*\(([^)]*)\)\s*\{", CSS):
        if m.group(1).strip() != condition:
            continue
        depth, i = 1, m.end()
        while i < len(CSS) and depth:
            if CSS[i] == "{":
                depth += 1
            elif CSS[i] == "}":
                depth -= 1
            i += 1
        out.append(CSS[m.end():i - 1])
    return "\n".join(out)


def _rule_in(text, selector):
    for sel, decl in _css_rules(text):
        if sel == selector:
            return decl
    return ""


def _px(decl, prop):
    """取某条声明的数值（px），取不到返回 None。"""
    m = re.search(r"(?:^|;)\s*" + prop + r"\s*:\s*(-?[\d.]+)px", decl)
    return float(m.group(1)) if m else None


class TestHeaderDoesNotOverflow(unittest.TestCase):
    """顶栏必须能换行。收窄子项治不了：478px 是子项 nowrap 的固有宽度。"""

    def test_top_in_wraps(self):
        decl = _decls(".top-in")
        self.assertIn("display:flex", decl.replace(" ", ""), ".top-in 不再是 flex 了，先看这行改成了什么")
        self.assertIn(
            "flex-wrap:wrap", decl.replace(" ", ""),
            "顶栏又变回不换行了。.logo/.chseg a/.seg a 全是 white-space:nowrap，"
            "一行固有宽度 478px：320~430px 下整页横向滚动，主题（◐）和 EN 按钮被"
            "挤出屏幕，用户既看不到也点不到。收窄内边距或藏中文标签都不够。")

    def test_no_nowrap_escape_hatch_in_header(self):
        """顶栏的子项本来就 nowrap，换行是唯一的出路——如果有人把 wrap 换成
        overflow-x:auto，等于把按钮藏进一条看不见的横滑条里。"""
        decl = _decls(".top-in")
        self.assertNotIn("overflow", decl.replace(" ", ""),
                         ".top-in 用 overflow 藏溢出了：横滑条里的按钮等于不存在，"
                         "换成 flex-wrap:wrap 让它们各自成行")


class TestFooterClearsTabbar(unittest.TestCase):
    """页脚不能被 fixed 的标签栏压住。"""

    def test_narrow_screen_footer_reserves_tabbar_height(self):
        narrow = _media("max-width:759px")
        self.assertTrue(narrow, "找不到 max-width:759px 的媒体查询，页脚的补偿规则没了")
        decl = _rule_in(narrow, "footer")
        self.assertTrue(decl, "窄屏媒体查询里没有 footer 规则，页脚仍会被标签栏压住")
        m = re.search(r"padding-bottom\s*:\s*calc\(\s*([\d.]+)px\s*\+\s*([\d.]+)px", decl)
        self.assertIsNotNone(
            m, "footer 的下内边距不再是 calc(基准 + 标签栏高)：%r。footer 在 .wrap "
               "之外，拿不到 .wrap 的 96px 下内边距，滚到底时最后 66px（含「生成于 …」"
               "那行）会整段压在 fixed 标签栏底下。" % decl)
        self.assertGreaterEqual(
            float(m.group(2)), TABBAR_H,
            "footer 只补了 %s px，标签栏高 %d px，仍然遮挡" % (m.group(2), TABBAR_H))
        self.assertIn("safe-area-inset-bottom", decl,
                      "没留 iOS 底部安全区：全面屏上标签栏更高，页脚会再次被压住")


class TestMetaRowSingleLine(unittest.TestCase):
    """来源名和发布时间必须各占一行——折行会撑高卡片，看起来像排版坏了。"""

    def test_isrc_ellipsizes_instead_of_wrapping(self):
        decl = _decls(".isrc").replace(" ", "")
        for prop in ("white-space:nowrap", "overflow:hidden", "text-overflow:ellipsis",
                     "min-width:0"):
            self.assertIn(prop, decl,
                          ".isrc 少了 %s：来源名放不下时会折成两行（360px 实测高 42），"
                          "卡片被撑高。来源名可收缩，超出用省略号。" % prop)

    def test_itime_does_not_shrink_or_wrap(self):
        decl = _decls(".itime").replace(" ", "")
        self.assertIn("white-space:nowrap", decl,
                      ".itime 没有 nowrap：发布时间会折行（360px 实测高 38）")
        self.assertIn("flex:none", decl,
                      ".itime 不参与收缩：它一被压窄就折行，而时间字符串短且固定，"
                      "该收缩的是来源名")


class TestTapTargets(unittest.TestCase):
    """触摸目标不得小于 44×44；视觉尺寸可以不变，用伪元素撑命中区。"""

    def test_fav_hit_area_is_44(self):
        decl = _decls(".fav")
        self.assertEqual(_px(decl, "width"), 44,
                         "收藏星标的宽度不是 44px：它是收藏的唯一入口，17×20 的手指"
                         "点不中，等于没有这个功能")
        self.assertEqual(_px(decl, "height"), 44, "收藏星标的高度不是 44px")

    def test_fav_hit_area_does_not_push_layout(self):
        """放大命中区不能顺带撑开卡片右上角：靠负外边距把多出来的空白吃掉。"""
        decl = _decls(".fav").replace(" ", "")
        self.assertIn("margin:-", decl,
                      "星标没有负外边距，44×44 会把 .irow 撑高、卡片右上角错位")

    def test_small_buttons_extend_hit_area_to_44(self):
        for sel in (".xbtn,.obtn,.upill,.icobtn",):
            decl = _decls(sel)
            self.assertTrue(decl, "%s 规则没了，按钮的命中区扩展一起消失" % sel)
            self.assertIn("position:relative", decl.replace(" ", ""),
                          "%s 不是定位元素，伪元素撑出来的命中区会跑到别处" % sel)
        pseudo = _decls(".xbtn::after,.obtn::after,.upill::after,.icobtn::after")
        m = re.search(r"min-height\s*:\s*(\d+)px", pseudo)
        self.assertIsNotNone(m, "按钮的伪元素命中区没了：xbtn/obtn 高 33、upill 高 30、"
                                "icobtn 高 34，都低于 44 的触摸下限")
        self.assertGreaterEqual(int(m.group(1)), 44,
                                "命中区只有 %spx，仍低于 44" % m.group(1))

    def test_icon_buttons_do_not_steal_neighbour_taps(self):
        """顶栏三个图标按钮之间只隔 .top-in 的 gap，横向每侧最多扩 gap/2。

        这里刻意不要求 44 宽：外扩 5px 就够 44，但会超出 6px 的间隙，让相邻命中区
        重叠 2px。重叠带里 DOM 靠后的元素胜出，于是点在搜索图标右侧会切主题——
        一次改状态的误触。实测外扩 3px 时命中区 40×44、间隙 0.00、互不重叠；
        40 宽比 44 少 4px，好过一次会翻转整页配色的误触。
        """
        gap = _px(_decls(".top-in"), "gap")
        self.assertIsNotNone(gap, ".top-in 没有 gap：三个图标按钮会贴在一起")
        decl = _decls(".icobtn::after").replace(" ", "")
        self.assertTrue(decl, ".icobtn 的横向命中区扩展没了：按钮 34px 宽，左右各有一半"
                                "间隙点不中，而图标本身只有 20px")
        left = re.search(r"(?:^|;)left:(-?[\d.]+)px", decl)
        right = re.search(r"(?:^|;)right:(-?[\d.]+)px", decl)
        self.assertIsNotNone(left, ".icobtn::after 没写 left：横向扩展量无从判断")
        self.assertIsNotNone(right, ".icobtn::after 没写 right")
        grow = -float(left.group(1))
        self.assertEqual(grow, -float(right.group(1)),
                         ".icobtn::after 左右扩展量不对称：%s / %s" % (left.group(1), right.group(1)))
        self.assertGreater(grow, 0, ".icobtn 没有横向扩展，34px 按钮两侧的死区仍然点不中")
        self.assertLessEqual(
            2 * grow, gap,
            "图标按钮每侧外扩 %.1fpx，两侧共 %.1fpx，超过 %s px 的间隙：相邻命中区重叠，"
            "重叠带里 DOM 靠后的按钮胜出，点搜索会切主题" % (grow, 2 * grow, gap))

    def test_pill_links_only_grow_vertically(self):
        """头部胶囊彼此只隔 2px，命中区横向扩出去会和邻居重叠。"""
        pseudo = _decls(".chseg a::after,.seg a::after")
        self.assertIn("left:0", pseudo.replace(" ", ""),
                      "胶囊的命中区往左右扩了：相邻胶囊只隔 2px，重叠后点哪个由 DOM "
                      "顺序决定，反而更糟")
        m = re.search(r"min-height\s*:\s*(\d+)px", pseudo)
        self.assertIsNotNone(m, "胶囊链接的命中区扩展没了（实测 36×30 / 56×31）")
        self.assertGreaterEqual(int(m.group(1)), 44, "胶囊命中区低于 44")

    def test_day_header_is_44_tall(self):
        """日期折叠头实测 38px，靠上下内边距补到 44。"""
        decl = _decls(".day-h")
        self.assertTrue(decl, ".day-h 规则没了")
        mh = re.search(r"min-height\s*:\s*(\d+)px", decl)
        pad = re.search(r"padding\s*:\s*(-?[\d.]+)px\s+\S+\s+(-?[\d.]+)px", decl)
        if mh:
            self.assertGreaterEqual(int(mh.group(1)), 44, "折叠头高度低于 44")
        elif pad:
            self.assertGreaterEqual(
                float(pad.group(1)) + float(pad.group(2)), 18,
                "日期折叠头的上下内边距合计只有 %s px（实测 38px 高，补到 44 需要 18px）。"
                "折叠头是整天的开关，点不中会让用户以为那天没有内容。"
                % (float(pad.group(1)) + float(pad.group(2))))
        else:
            self.fail(".day-h 既没有 min-height 也没有上下内边距：高度回到 38px，"
                      "低于 44 的触摸下限")


class TestTablesStayReadable(unittest.TestCase):
    """表格宁可自己横向滚动，也不许把列压成竖排。"""

    def test_wide_tables_stack_on_phones(self):
        """窄屏下 .tw.wide 必须逐条堆叠，不能只靠横滑。

        实测（320/360/390/430px）：表格 418px、卡片内宽只有 250~360，第三列
        「打开 ↗」整个落在卡片外——8 个链接没有一个在可视区，而 .tw 的横向
        滚动没有视觉提示，用户不会想到去滑，等于所有接口都点不开。
        堆叠后 8/8 链接可见，且 .tw 不再需要横滑。
        """
        narrow = _media("max-width:759px")
        flat = narrow.replace(" ", "")
        self.assertIn(".tw.widetable,.tw.widetbody,.tw.widetr,.tw.widetd{display:block}", flat,
                      "窄屏下接口/RSS 表没有改成块级堆叠：第三列「打开 ↗」会落在卡片外，"
                      "8 个链接一个都点不到")
        self.assertIn(".tw.widethead{display:none}", flat,
                      "窄屏下堆叠后还留着表头：每行前面会多出一条表头行")
        self.assertIn(".tw.widetable{width:100%;min-width:0}", flat,
                      "堆叠后表格宽度没重置：.tw.wide table 的 width:max-content 还在，"
                      "表格仍会超出卡片")
        # 桌面端必须还是三列表格
        wide = _media("min-width:760px")
        self.assertIn(".tabbar{display:none}", wide.replace(" ", ""),
                      "宽屏媒体查询没了：桌面端会同时出现标签栏和顶部导航")

    def test_tw_is_a_scroll_container(self):
        decl = _decls(".tw").replace(" ", "")
        self.assertIn("overflow-x:auto", decl,
                      ".tw 不再是横向滚动容器：320px 下接口路径会把列挤到一两个字符宽"
                      "（实测「7 小时」竖排成三行）")

    def test_wide_tables_size_to_content(self):
        decl = _decls(".tw.wide table").replace(" ", "")
        self.assertIn("width:max-content", decl,
                      ".tw.wide 的表格不再按内容取宽：接口/RSS 路径会被折断或挤扁，"
                      "宁可横向滚动")
        self.assertIn("min-width:100%", decl,
                      ".tw.wide 少了 min-width:100%：宽屏下表格会比卡片窄，右侧留一条空")

    def test_mono_breaks_anywhere(self):
        """overflow-wrap 必须是 anywhere：break-word 不参与最小内容宽度的计算，
        等于没解决「路径把文档撑宽」这个问题。"""
        decl = _decls(".mono").replace(" ", "")
        self.assertIn("overflow-wrap:anywhere", decl,
                      ".mono 不再 anywhere 断行：api/v1/tech/hot-topics.json 这类路径"
                      "会把表格最小宽度撑到 314px，320px 视口下文档宽 370，整页横向滚动")

    def test_nowrap_helper_exists(self):
        self.assertIn("white-space:nowrap", _decls(".nw").replace(" ", ""),
                      ".nw 工具类没了：表格里的计数/时间列会折行")

    def test_views_use_the_right_table_wrapper(self):
        """数据来源表不加 wide（来源名允许折行），接口/RSS 表加 wide。"""
        self.assertIn('<div class="tw"><table>', JS,
                      "数据来源表不再用 .tw 包裹：320px 下会被挤成竖排")
        self.assertEqual(JS.count('<div class="tw wide">'), 2,
                         "接口表和 RSS 表的 .tw wide 包裹数量不对（应为 2）：路径类内容"
                         "必须按内容取宽 + 横向滚动，而不是断行或压扁")
        # 计数列和时间列必须各自 nowrap，一个都不能少——只加一个的话另一个
        # 照样折行，卡片还是会被撑高。整行一起匹配，避免"只改了一半"也通过。
        flat = re.sub(r"\s+", "", JS)
        self.assertRegex(
            flat,
            r'<tr><td>\'\+esc\(s\.source\)\+\'</td><tdclass="nw">\'\+s\.count\+\'</td>'
            r'<tdclass="nw">\'\+fmtRel\(s\.latestAt\)\+\'</td></tr>',
            "数据来源表的计数/时间列不是各自 nowrap：320px 下会折成两行")
        self.assertIn('<th class="nw">', JS,
                      "数据来源表的表头没有 nowrap：实测「打开」会断成两行")


if __name__ == "__main__":
    unittest.main(verbosity=2)
