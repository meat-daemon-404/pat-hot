# -*- coding: utf-8 -*-
"""列表滚动契约测试（纯标准库，无网络、无第三方依赖）。

单独成文件：锁的是 collector/templates/ 里"长列表怎么渲染"这一件事，
与 test_collect.py 的采集/输出契约、test_theme.py 的主题契约都不相干。

锁住的回归（2026-10-12 录屏）：快速滑动时内容整屏空白 0.83s、滑过头、位置丢失。
根因两条，互相遮掩，所以两条都要钉住：

1. .icard 用了 content-visibility:auto + contain-intrinsic-size:auto 220px，
   而真实卡片高 131~351（中位 250）。滑过的卡片被换成估高占位，文档高度在
   手指下持续塌陷：实测精选页一次 1900px 的 fling 缩 1332px、单帧最多跳 644px
   （录屏里 t=1.87s 那帧正是 +668px）；全部页 90→240 条时缩 4466px。
2. 全部页无限滚动走整页 innerHTML 重建。它本来要 180~280ms，正好落在用户
   手指还在滑的那一帧；content-visibility 把这笔开销藏住了，于是没人发现
   重建本身才是该修的东西 —— 只删属性会让卡顿从"位置丢失"变成"直接掉帧"。

所以：估高不许回来，重建也不许回来。
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


def _css_rules(css):
    """[(selector, declarations)]，注释先剥掉——注释里提到属性名不算用。"""
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [(m.group(1).strip(), m.group(2))
            for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", body, re.S)]


class TestNoIntrinsicHeightLie(unittest.TestCase):
    def test_icard_does_not_use_content_visibility(self):
        """卡片不许再用估高换性能：估高与真实高度不符就会在滑动中塌陷文档高度。"""
        hits = [sel for sel, decl in _css_rules(CSS)
                if "content-visibility" in decl and re.search(r"\bicard\b", sel)]
        self.assertEqual(
            hits, [],
            ".icard 又用上了 content-visibility（%s）。它的占位高度和真实卡片高度"
            "（131~351，中位 250）对不上，快速滑动时文档高度会在手指下塌陷，"
            "复现 2026-10-12 录屏的滑过头/整屏空白。长列表性能请走追加式渲染。"
            % "、".join(hits))

    def test_no_contain_intrinsic_size_left(self):
        """估高属性本身也不该残留：没有 content-visibility 时它是死代码，
        留着只会让人以为占位高度还是 220px。"""
        hits = [sel for sel, decl in _css_rules(CSS) if "contain-intrinsic-size" in decl]
        self.assertEqual(hits, [], "仍有 contain-intrinsic-size：%s" % "、".join(hits))


class TestAppendOnlyPaging(unittest.TestCase):
    """全部页的分页必须是追加，不许退回整页 innerHTML 重建。"""

    def _renderall_body(self):
        i = JS.index("function renderAll()")
        # 到下一个顶层 function 为止
        j = re.search(r"\nfunction ", JS[i + 10:]).start() + i + 10
        return JS[i:j]

    def test_append_helper_exists(self):
        self.assertIn("function appendAllPage(", JS,
                      "追加式分页的入口没了，无限滚动可能退回整页重建")

    def test_append_uses_insert_adjacent_html(self):
        i = JS.index("function appendAllPage(")
        j = re.search(r"\nfunction ", JS[i + 10:]).start() + i + 10
        body = JS[i:j]
        self.assertIn("insertAdjacentHTML", body,
                      "appendAllPage 不再用插入方式追加，改成重建会让滑动再次掉帧")
        self.assertNotIn("root.innerHTML", body,
                         "appendAllPage 里出现了整页 innerHTML 重建（实测 180~280ms）")

    def test_renderall_seeds_context_rendered_count(self):
        """重建时必须把 rendered 同步成实际插入条数，否则下一次追加会重复。"""
        body = self._renderall_body()
        self.assertIn("allCtx", body, "renderAll 不再维护 allCtx，追加会算错起点")
        self.assertRegex(body.replace(" ", ""), r"rendered:\s*shown")

    def test_more_label_uses_total_not_shown(self):
        """「加载更多 (60/300)」的分母是全集条数。写成已渲染条数会变成 (60/60)
        还留着按钮，用户以为到底了。"""
        i = JS.index("function moreLabel(")
        j = JS.index("}", i)
        body = JS[i:j]
        self.assertRegex(body.replace(" ", ""), r"shown\s*\+\s*'/'\s*\+\s*total")

    def test_sentinel_guard_prevents_double_append(self):
        """追加前先摘掉哨兵，否则同一帧里 IntersectionObserver 会连发两次。"""
        i = JS.index("function appendAllPage(")
        j = re.search(r"\nfunction ", JS[i + 10:]).start() + i + 10
        body = JS[i:j]
        self.assertRegex(body.replace(" ", ""), r"if\(from>=its\.length\)return",
                         "缺少到底守卫")
        self.assertIn("allObserver.disconnect()", body,
                      "追加前没先断开 observer，可能一帧连发两次")

    def test_no_scrollby_hack_left(self):
        """旧代码在加载更多后 window.scrollBy({top:-60}) 找补位置，
        追加式渲染不需要它；留着说明又退回重建了。"""
        self.assertNotIn("scrollBy({top:-60})", JS,
                         "scrollBy(-60) 找补回来了，说明整页重建也回来了")


class TestFilterResetsPaging(unittest.TestCase):
    """筛选/排序/搜索/换频道都必须从第一页重来，不能在旧列表上追加。"""

    def test_every_full_rebuild_path_resets_allshown(self):
        # 三处整页重建的入口：分类、排序、搜索跳转。空格位置随手写风格变，
        # 所以先把空白抹掉再匹配。
        flat = re.sub(r"\s+", "", JS)
        for pat, why in [
            (r'state\.cat=e\.target\.value;state\.allShown=ALL_PAGE;contentReset\("all"\)', "分类切换"),
            (r'state\.sort=e\.target\.value;state\.allShown=ALL_PAGE;contentReset\("all"\)', "排序切换"),
            (r"gotoAll=.*?state\.allShown=ALL_PAGE", "搜索跳转"),
        ]:
            self.assertRegex(flat, pat, "%s 没有重置 allShown，会在旧列表上接着追加" % why)


class TestContentReset(unittest.TestCase):
    """列表内容被整体替换后必须回顶部，且缓存位置一起清零。

    锁住的回归（2026-10-13 落点探针实测）：全部页滚到 y=5000（180 条、docH 47294）
    后换排序，列表重建为 30 条（docH 7188），但 scrollY 停在 5000——用户落在新
    列表的中段；若原本滚得更深（如 y=20000），会被浏览器钳到 6344，直接落在
    新列表最底部。排序/分类/搜索/主题卡/日报日期/未读筛选/热点排序都是这类
    "整体替换"，合并进来的「只看科研」是第八类（且同时替换两个视图）。视图缓存
    引入后问题加倍：SCROLL[v] 还存着旧 y，切走再切回会把旧位置恢复到换掉后的列表
    上，比原来更糟。

    区分：取消星标/标记已读是"删一条"，位置应保持（浏览器 scroll anchoring 处理），
    月份折叠是纯 UI 收起，正文没换——这些都不能走 contentReset。
    """

    def test_content_reset_clears_cached_position(self):
        i = JS.index("function contentReset(")
        j = JS.index("}", i)
        body = JS[i:j].replace(" ", "")
        self.assertIn("SCROLL[v]=0", body,
                      "只滚回顶部不清缓存，切走再切回会把旧 y 恢复到新列表上")
        self.assertIn('invalidate(v)', body,
                      "contentReset 必须作废视图缓存，让重画走正常路径")
        self.assertIn("window.scrollTo(0,0)", body, "当前可见时不回顶部等于没修")

    def test_all_wholesale_replace_paths_use_content_reset(self):
        """七条整体替换路径一个都不能漏（漏的那条就是这次的 bug 现场）。"""
        flat = re.sub(r"\s+", "", JS)
        for pat, why in [
            (r'state\.cat=e\.target\.value;[^}]*contentReset\("all"\)', "分类切换"),
            (r'state\.sort=e\.target\.value;[^}]*contentReset\("all"\)', "排序切换"),
            (r'gotoAll=\(\)=>\{[^}]*contentReset\("all"\)', "搜索跳转"),
            (r'state\.cat=el\.dataset\.cat;[^}]*contentReset\("all"\)', "主题卡跳转"),
            (r'state\.dailyDate=el\.dataset\.d;contentReset\("daily"\)', "日报日期切换"),
            (r'state\.unreadOnly=!state\.unreadOnly;contentReset\("feed"\)', "未读筛选"),
            (r'state\.hotSort=b\.dataset\.hs;contentReset\("hot"\)', "热点排序"),
        ]:
            self.assertRegex(flat, pat, "%s 没有走 contentReset，会落在替换后列表的中段" % why)

    def test_sci_toggle_resets_both_list_views(self):
        """「只看科研」是持久开关，同时决定精选页和全部页的列表内容（合并 2026-10-13
        远端功能时引入的交互）：只 reset 当前视图，另一个视图会留着上一个筛选条件的
        列表 + 旧滚动位置，切过去才看到过期内容。两个视图必须一起重置。"""
        i = JS.index("function sciToggle(")
        j = JS.index("}", i)
        body = JS[i:j]
        self.assertIn('contentReset("feed")', body, "科研开关没重置精选页")
        self.assertIn('contentReset("all")', body, "科研开关没重置全部页")
        self.assertIn("state.allShown=ALL_PAGE", body,
                      "全部页还留着已加载的多页，重置后应从第一页开始")
        # 两个入口共用一个函数，别各自实现一份漏掉另一个视图
        self.assertIn("sb.onclick=sciToggle", JS, "精选页科研按钮没走 sciToggle")
        self.assertIn("sba.onclick=sciToggle", JS, "全部页科研按钮没走 sciToggle")

    def test_month_collapse_does_not_reset_position(self):
        """月份折叠只是收起归档，正文没换：走 contentReset 会莫名把用户弹回顶部。"""
        i = JS.index('$$(".amonth", root).forEach')
        j = JS.index("\n", i)
        self.assertNotIn("contentReset", JS[i:j],
                         "月份折叠不该重置滚动位置，正文根本没换")

    def test_fav_removal_keeps_position(self):
        """取消星标是"删一条"，不是整体替换：保持位置，别滥用 contentReset。"""
        i = JS.index("function toggleFav(")
        j = JS.index("}", i)
        self.assertNotIn("contentReset", JS[i:j],
                         "删一条不该弹回顶部，浏览器 scroll anchoring 会保持位置")


class TestViewCache(unittest.TestCase):
    """视图缓存：切 tab 不重画、不丢位置，但数据一变就必须作废。

    锁住的回归（2026-10-13）：router() 每次都重画视图再 scrollTo(0,0)，从全部页
    切到热点再切回来，读到的位置和已加载的 270 条一起没了。录屏最后那段
    "往回滑找位置然后放弃"就是这个。<section> 本来就常驻 DOM，重画纯属自找。
    """

    def _router(self):
        i = JS.index("function router()")
        j = JS.index("\nfunction ", i + 10)
        return JS[i:j]

    def test_router_only_renders_when_not_rendered(self):
        body = self._router()
        self.assertRegex(body.replace(" ", ""), r'if\(!RENDERED\.has\(v\)\)',
                         "router 又无条件重画视图了，位置和已加载分页会再次丢失")

    def test_router_records_old_position_before_hiding_view(self):
        """必须在改 class 之前读 scrollY：旧视图一 display:none 文档高度就塌，
        scrollY 被钳到 0，之后再读只能读到 0。"""
        body = self._router().replace(" ", "")
        i = body.index("SCROLL[LAST_VIEW]=")
        j = body.index('classList.remove("on")')
        self.assertLess(i, j, "记录位置的语句必须排在隐藏旧视图之前")

    def test_retap_of_current_tab_goes_to_top(self):
        body = self._router().replace(" ", "")
        self.assertIn("retap", body,
                      "缓存了位置就得留一个回顶部的出口，否则用户只能手动往上滚")

    def test_retap_handler_exists(self):
        """点当前 tab 不改 hash、不触发 hashchange，router 根本不会被调用，
        所以必须有一个 click 兜底。"""
        self.assertRegex(JS.replace(" ", ""), r'location\.hash\)router\(\)',
                         "缺少同 tab 点击的兜底，回顶部永远走不到")

    def test_channel_switch_invalidates_everything(self):
        i = JS.index("function setChannel(")
        j = JS.index("\nfunction ", i + 10)
        self.assertIn("invalidateAll()", JS[i:j],
                      "换频道等于换掉全部数据，九个视图的缓存必须一起作废")

    def test_filter_paths_invalidate_all_view(self):
        """分类/主题卡/搜索三条路都会改 state.cat|state.q，
        不作废缓存就会看到上一个筛选条件的列表。"""
        for pat, why in [
            (r'state\.cat=el\.dataset\.cat;[^}]*?contentReset\("all"\)', "主题卡跳转"),
            (r'gotoAll=\(\)=>\{[^}]*?contentReset\("all"\)', "搜索跳转"),
        ]:
            self.assertRegex(JS, pat, "%s 没有作废 all 视图" % why)

    def test_fav_and_read_write_dom_in_place(self):
        """星标/已读是单张卡片的状态，且同一张卡可能同时存在于多个常驻视图。
        靠重绘传播已经行不通，必须就地写回 DOM。"""
        for fn in ("applyFavToDom", "applyReadToDom"):
            self.assertIn("function %s(" % fn, JS, "%s 没了，跨视图状态会不一致" % fn)
        i = JS.index("function toggleFav(")
        j = JS.index("}", i)
        self.assertIn("applyFavToDom", JS[i:j], "toggleFav 不再同步 DOM")
        self.assertIn('removeCardNodeOrInvalidate("fav"', JS[i:j],
                      "收藏页删一条既不作废也不删节点，会留着上一个星标集合")

    def test_single_removal_does_not_rerender_visible_view(self):
        """读掉/取消收藏只删那一个节点。整页重画会销毁滚动锚点：实测只看未读时
        读掉视口上方的卡，scrollY 不变但视口中心内容跳了约一张卡（点开文章回来
        列表已跳位，正是录屏最后"往回滑找位置"的机制）。"""
        i = JS.index("function markRead(")
        j = JS.index("}", i)
        self.assertIn('removeCardNodeOrInvalidate("feed"', JS[i:j],
                      "markRead 又走 invalidate 整页重画，删一条会跳位置")
        body = JS[JS.index("function removeCardNodeOrInvalidate("):]
        body = body[:body.index("\nfunction ", 10)]
        self.assertIn("c.remove()", body, "不再是节点级删除")
        self.assertIn("invalidate(v)", body, "隐藏视图仍要 invalidate")
        self.assertIn("T.noFav", body,
                      "收藏页删空不补空态：绕过 renderer 后是一屏空白，看着像坏了")
        self.assertIn("T.noMatch", body, "精选删空同样要补空态")

    def test_fav_click_does_not_toggle_class_locally(self):
        """toggleFav 已经用绝对状态写过 class，click 里再 toggle 一次会翻回去。"""
        self.assertNotIn('toggleFav(f.dataset.fav); f.classList.toggle("on")', JS,
                         "click 里重复翻转 class，会把刚写对的星标状态弄反")

    def test_invalidate_rerenders_visible_view(self):
        """作废的正是屏幕上这个视图时必须立刻重画，否则用户看到过期内容：
        在收藏页取消星标，卡片还留在列表里，要切走再切回才消失。"""
        i = JS.index("function invalidate(")
        j = JS.index("\nfunction ", i + 10)
        body = JS[i:j]
        self.assertRegex(body.replace(" ", ""), r"if\(v===LAST_VIEW",
                         "invalidate 只删缓存不重画，可见视图会留下过期 DOM")
        self.assertIn("renderers[v]", body, "invalidate 没有真的重画当前视图")

    def test_invalidate_marks_rerendered_view_back_rendered(self):
        """重画成功必须标回 RENDERED。漏了它，之后用户滚动的位置在切走时不会被
        记录（router 的 RENDERED.has 条件不成立），切回被当成首访重画+弹回顶部——
        位置缓存对所有筛选过的视图静默失效。实测：换排序→滚到 2400→切走→切回，
        回到 0 而不是 2400。add 必须在渲染之后（抛错不标，留给下次重试）。"""
        i = JS.index("function invalidate(")
        j = JS.index("\nfunction ", i + 10)
        body = JS[i:j].replace(" ", "")
        self.assertIn("renderers[v]||renderers.feed)();RENDERED.add(v)", body,
                      "invalidate 重画后没标回 RENDERED，可见视图的位置缓存会静默失效")

    def test_invalidate_has_recursion_guard(self):
        """renderer 里若再触发 invalidate，没有守卫就是无限递归。"""
        i = JS.index("function invalidate(")
        j = JS.index("\nfunction ", i + 10)
        self.assertIn("!RENDERING", JS[i:j], "缺少重入守卫")
        self.assertIn("finally", JS[i:j], "RENDERING 必须用 finally 复位，抛错后不能永久卡住")

    def test_gotoAll_does_not_double_render(self):
        """contentReset 内部经 invalidate 重画可见视图，gotoAll 再自己 renderAll 就是画两遍。"""
        i = JS.index("const gotoAll=")
        body = JS[i:JS.index("};", i)]        # 注意：不能按第一个 ';' 切，那只能看到赋值
        self.assertIn('contentReset("all")', body, "gotoAll 不再作废 all 视图")
        self.assertNotIn("renderAll()", body,
                         "gotoAll 里重复 renderAll，all 可见时会连画两次")


class TestImageReservedSpace(unittest.TestCase):
    """配图必须预留高度，否则解码那一刻把下面整段内容推走。"""

    def test_himg_declares_aspect_ratio(self):
        i = CSS.index(".himg{")
        body = CSS[i:CSS.index("}", i)]
        self.assertIn("aspect-ratio", body,
                      ".himg 没有预留宽高比，--images 出图后会在图片解码处产生跳变")

    def test_aspect_ratio_matches_config(self):
        with io.open(os.path.join(ROOT, "collector", "config.json"), encoding="utf-8") as f:
            cfg = f.read()
        m = re.search(r'"aspect_ratio"\s*:\s*"(\d+):(\d+)"', cfg)
        if not m:
            self.skipTest("config 里没有 aspect_ratio")
        i = CSS.index(".himg{")
        body = CSS[i:CSS.index("}", i)]
        self.assertIn("aspect-ratio:%s/%s" % (m.group(1), m.group(2)), body.replace(" ", ""),
                      "预留比例和实际出图比例不一致，等于没预留")


class TestExpandBodyLookup(unittest.TestCase):
    """展开阅读 的正文查找：getElementById 不能用 CSS.escape。

    来源：给 .xbody 折叠正文做性能剖析时撞出来的。CSS.escape 是给"选择器"用的，
    getElementById 要的是原始 id。卡片写的是 id="xb-591a…"，而
    CSS.escape("591a…") 返回 "\\35 91a…"，于是查不到：按钮文案翻成"收起"，
    正文高度永远是 0。全站 577 条里 364 条（63%）的 id 是纯十六进制、以数字开头，
    全都点不开 —— 而且不报错，所以从 a67fef8 起一直没人发现。
    """

    def test_getelementbyid_is_not_passed_css_escape(self):
        hits = re.findall(r"getElementById\([^)]*CSS\.escape[^)]*\)", JS)
        self.assertEqual(hits, [],
                         "getElementById 里套了 CSS.escape，数字开头的 id 会查不到：%s" % hits)

    def test_expand_body_id_matches_markup(self):
        """写入端和查找端必须用同一个 id 形态：都用原始 it.id。"""
        self.assertIn("""id="xb-'+it.id+'""", JS, "正文 id 的写法变了，查找端要跟着变")
        self.assertIn('getElementById("xb-"+id)', JS.replace(" ", ""),
                      "查找端不再是原始 id，会重演 63% 卡片点不开的事故")


if __name__ == "__main__":
    unittest.main(verbosity=2)
