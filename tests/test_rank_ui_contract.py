# -*- coding: utf-8 -*-
"""账号面板 / 兴趣重排 / ScholarMatrix 出站深链 —— 前端面契约测试（纯标准库，无网络）。

单独成文件：锁的是 collector/templates/ 在 W2 前端半新增的三件事，与
test_collect.py 的采集契约、test_scroll_contract.py 的列表渲染契约、
test_theme.py 的主题/路由齐备性都不相干。

为什么只能静态锚钉：后端路由（/api/account/*、/api/profile、/api/bind/verify）
由并行代理在 functions/ 里实现，浏览器无法在这里真跑；而这三面里最贵的
不是功能没做，是**承诺被悄悄改掉**——

1. 出站深链（契约 §5）：只有条目 refs 带 verified 的 doi/arxiv 才许出现
   「在 ScholarMatrix 深读」。无锚点给出链＝跳过去建不出文献，正面撞
   「宁缺毋假」红线（patJourney.js 同判例）。b64url 必须与 SM 侧
   frontend/src/lib/patJourney.js 的 b64url 逐字节同形：编码不同形时 SM 端
   decodePapersFromQuery 解出乱码 JSON，整条静默失败，两端各自看都是绿的。
2. 账号视图（契约 §1.1）：#?bind=CODE 在登录后自动 POST /api/bind/verify。
   失败必须展示服务端回的真原因+机器码（契约 §0：网络故障/未登录/源站反爬
   三种不许混成一句「操作失败」）。
3. 兴趣重排（契约 §3）：🔴 只改顺序，绝不改分数徽标显示值——分数是对外
   承诺的可复现口径（thresholdNote、数据页、API 全是它）。且探测以
   localStorage 的 ph_logged_in 标记为门：开源 fork 的静态用户零额外请求，
   未登录路径必须与今天逐字节一致。

变异思路（改坏即红，故意示范两条以上）：
· 把 refs 门 `if(!r||!(r.doi||r.arxiv)) return "";` 放松成 `if(!r) return "";`
  ——refs 存在但 doi/arxiv 皆空的条目就会出假链，TestOutboundDeepLink
  的 literal 锚当场红。
· 把 scoreEl 的徽标改成 `Math.round(s*(1+w))` 让分数跟着重排"动起来"——
  TestRerankTouchNothingPinned 钉的原字面当场红。
· 把探测门删掉改成 bind() 直接 GET /api/account/me——fork 用户每次开站
  多两个 404 请求，maybeProbe/probeAccount 的 mark!=="1" 双锚红。
· 把 b64url 写成裸 btoa(String)（不先 UTF-8 化）——中文标题条目在 SM 端
  解码炸掉，TestB64urlShape 锚红（btoa(unescape(encodeURIComponent 字面）。
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


def _fn_body(name, source=JS):
    """从 `function name(` 起切到下一个行首 function 为止（模板里这些函数都
    在顶层，行首 function 即下一个成员；到文件尾则取全余文）。"""
    i = source.index("function %s(" % name)
    m = re.search(r"\nfunction ", source[i + 10:])
    j = i + 10 + m.start() if m else len(source)
    return source[i:j]


class TestB64urlShape(unittest.TestCase):
    """b64url 必须与 SM 侧 patJourney.js/deepLink.js 逐字符同形。

    SM 端解码是 decodeURIComponent(escape(atob(t.replace(-→+,_→/))))；
    我们这边编码差一步（少 UTF-8 化、少去填充），中文标题就解不成 JSON。
    """

    def test_b64url_uses_utf8_roundtrip_and_urlsafe(self):
        body = _fn_body("b64url").replace(" ", "")
        self.assertIn("btoa(unescape(encodeURIComponent(String(s))))", body,
                      "b64url 不再是 UTF-8 往返形态，SM 端 b64urlDecode 会解出乱码")
        for rep in ('replace(/\\+/g,"-")', 'replace(/\\//g,"_")', 'replace(/=+$/,"")'):
            self.assertIn(rep, body, "b64url 少了 %s，与 SM 侧不同形" % rep)

    def test_sm_base_is_https_pages_dev(self):
        self.assertIn('const SM_BASE="https://scholarmatrix.pages.dev/";', JS,
                      "深链主机变了：契约 §5 钉死 SM 主机是 scholarmatrix.pages.dev")


class TestOutboundDeepLink(unittest.TestCase):
    """出站深链：refs 门控 + descriptor 形状 + 无条件出链的反向锚。"""

    def test_refs_gate_literal(self):
        # 判定形状：refs 存在且 (doi || arxiv)，缺一出假链就撞宁缺毋假红线。
        self.assertIn("if(!r||!(r.doi||r.arxiv)) return \"\";", JS,
                      "refs 门控字面没了：无编号条目不许出 ScholarMatrix 按钮")

    def test_suspect_is_not_a_deep_read_entry(self):
        # 契约 §0：只有 confidence:"verified" 的编号可建真论文；suspect 不许当深读入口。
        self.assertIn("if(r.confidence!==\"verified\") return \"\";", JS,
                      "verified 门没了：suspect 编号会被当成可建论文的锚跳出去")

    def test_descriptor_shape_and_key_order(self):
        # 键序 title→kind→source→doi→arxiv→url 照 patJourney.buildPatOutboundUrl，
        # 同输入两端 JSON.stringify 逐字节一致，对拍测试才有意义。
        self.assertIn('const d={title:String(it.title||"").slice(0,300),kind:"paper",source:"pat-hot"};', JS)
        flat = re.sub(r"\s+", "", JS)
        self.assertIn('if(r.doi)d.doi=r.doi;if(r.arxiv)d.arxiv=r.arxiv;if(it.url)d.url=it.url;', flat,
                      "descriptor 条件键顺序变了，与 SM 侧构造不再同形")

    def test_href_gated_before_base_concat(self):
        """反向锚：拼 SM_BASE 的那一行之前必须有『无 descriptor 返回空』守卫。

        变异思路：删掉 `if(!j) return "";` 让 smOutHref 无条件拼串——这条红。
        """
        body = _fn_body("smOutHref").replace(" ", "")
        i = body.index('if(!j)return"";')
        j = body.index('returnSM_BASE+"?add="+b64url(j);')
        self.assertLess(i, j, "smOutHref 的拼链行不再排在空描述符守卫之后：出现无条件出链路径")

    def test_no_unconditional_sm_link_anywhere(self):
        """模板里 scholarmatrix.pages.dev 只许出现在 SM_BASE 定义一处；
        ?add= 拼串只许出现在 smOutHref 一处。多一处＝多一条没过门的出链路径。"""
        self.assertEqual(JS.count("scholarmatrix.pages.dev"), 1,
                         "又硬编码了一个 ScholarMatrix 地址：出链路径必须只此一家、受门控制")
        self.assertEqual(JS.count("?add="), 1,
                         "?add= 拼接出现在第二处，那条路径没有 refs 门控")

    def test_button_hidden_when_href_empty(self):
        body = _fn_body("smDeepBtn").replace(" ", "")
        self.assertIn("consth=smOutHref(it);if(!h)return\"\";", body,
                      "smDeepBtn 不再以空 href 短路：无锚条目会渲染出坏按钮")

    def test_card_mounts_button_via_gated_helper(self):
        """条目卡操作区挂的是 smDeepBtn(it)（带门），不许卡里直接拼 href。"""
        i = JS.index("function itemCard(")
        j = JS.index("\nfunction ", i + 10)
        body = JS[i:j]
        self.assertIn("smDeepBtn(it)", body, "itemCard 不再经 smDeepBtn 挂深链按钮")
        self.assertNotIn("SM_BASE", body, "itemCard 里直接拼 SM_BASE＝绕过出门守卫的第二条路")


class TestAccountView(unittest.TestCase):
    """#/account 注册进路由三件套 + 绑定兑换 + 真原因纪律。"""

    def test_route_registered(self):
        self.assertIn('"/account":"account"', JS, "router map 没有 /account")
        self.assertRegex(JS, r"renderers\.account\s*=", "account 视图没注册 renderer，点了白屏")
        self.assertIn('id="view-account"', HTML, "account 视图没有承载 section")

    def test_endpoints_match_contract(self):
        for lit, why in [
            ('"/api/account/"+kind', "注册/登录 POST（register|login，契约 §1.1 前置）"),
            ('"GET","/api/account/me"', "会话探测 GET"),
            ('"GET","/api/profile"', "绑定状态与快照 GET"),
            ('"DELETE","/api/profile-snapshot"', "清除我的数据（契约 §1.2 硬删）"),
            ('"POST","/api/bind/verify"', "绑定码兑换（契约 §1.1 ②）"),
        ]:
            self.assertIn(lit, JS, "%s 的字面调用路径变了：%s" % (why, lit))

    def test_credentials_include_on_every_account_call(self):
        """会话是 Cookie 的：apiCall 一处带 credentials:\"include\"，全部账号请求共用。
        变异思路：把这处改成 omit——登录态全断，这条与 endpoints 锚同时给出线索。"""
        body = _fn_body("apiCall").replace(" ", "")
        self.assertIn('credentials:"include"', body, "apiCall 不再携带凭证，Cookie 会话面全断")

    def test_bind_flow_requires_login_then_verifies(self):
        flat = re.sub(r"\s+", "", _fn_body("redeemBind"))
        self.assertIn("if(!code||!PROFILE.logged)return;", flat,
                      "兑换不再先要求已登录：未登录自动兑换只会拿到假 401")
        self.assertIn('{code:code}', flat, "POST /api/bind/verify 的载荷形状变了")

    def test_bind_failure_shows_server_reason_not_generic(self):
        """契约 §0：失败要说真原因。成功走 bindOk 文案；失败必须经 realError
        把服务端 error+机器码带出来，不许退回一句「操作失败」。"""
        body = re.sub(r"\s+", "", _fn_body("redeemBind"))
        self.assertIn('ACC.msg=T.bindOk;', body)
        i = body.index("else{")
        self.assertIn("realError(res,T.bindFail)", body[i:i + 120],
                      "绑定失败分支不走 realError：真原因+机器码被吞，违反契约 §0")

    def test_real_error_keeps_reason_and_machine_code(self):
        body = re.sub(r"\s+", "", _fn_body("realError"))
        self.assertIn("j.error||j.reason||j.message", body, "不再优先展示服务端回的真原因原文")
        self.assertIn("j.code||j.machine||j.err_code", body, "机器码没拼进展示，两端排查断了线索")
        self.assertIn("res.status===0", body, "网络层失败（status 0）与业务失败混为一谈了")


class TestProbeGatedByLocalStorage(unittest.TestCase):
    """探测门：localStorage 有 ph_logged_in=1 才启动账号探测。

    开源 fork 的静态用户（从没在本浏览器登录过）打开站点，账号面必须
    零额外请求——这是「未登录路径与今天逐字节一致」的机制保证，不是装饰。
    变异思路：把 maybeProbe 里 mark!=="1" 的早退删掉，bind() 一起跑就多发
    两个请求；两个函数体各钉一处，删一处另一处仍红（防"改一半"）。
    """

    def test_marker_key_literal(self):
        self.assertIn('const PH_LOGIN_KEY="ph_logged_in";', JS,
                      "探测门标记键名变了：老访客的登录标记会失灵（静默失去重排）")

    def test_maybe_probe_gate_literal(self):
        body = re.sub(r"\s+", "", _fn_body("maybeProbe"))
        self.assertIn('if(mark!=="1"){', body, "maybeProbe 的 localStorage 门没了")
        self.assertNotIn("fetch(", body, "maybeProbe 自己不该发请求")

    def test_probe_account_double_gate(self):
        body = re.sub(r"\s+", "", _fn_body("probeAccount"))
        self.assertIn('if(mark!=="1"){', body,
                      "probeAccount 体内的第二道门没了：绕过 maybeProbe 的调用会漏请求")
        self.assertIn('"/api/account/me"', body, "探测端点变了")

    def test_bind_starts_probe_after_router(self):
        flat = re.sub(r"\s+", "", JS)
        self.assertRegex(flat, r"router\(\);maybeProbe\(\);",
                         "bind() 不再于首屏渲染后过门探测：登录用户的胶囊永远不会出现")


class TestRerankTouchNothingPinned(unittest.TestCase):
    """重排只改顺序：分数徽标渲染行钉原字面，比较键只进 sort()。"""

    def test_score_badge_line_untouched(self):
        """钉死徽标行的关键字面（模板初版至今一字未动）。变异思路：徽标若要
        跟着 score_final 变成 Math.round(s*(1+w))，Math.round(s) 的孤立出现
        当场没了，红。"""
        i = JS.index("function scoreEl(")
        j = JS.index("\n", i)
        line = JS[i:j]
        self.assertIn("class=\"iscore mono '+scoreCls(s)+'\"", line)
        self.assertIn("' / 100\">'+Math.round(s)+'</span>'", line,
                      "分数徽标显示值不再是孤立的 Math.round(s)：重排触碰了对外承诺的显示值（契约 §3）")
        self.assertNotIn("hitWeight", line)
        self.assertNotIn("rankKey", line)
        self.assertNotIn("PROFILE", line)

    def test_no_score_mutation_anywhere(self):
        """全模板不存在对条目 score 字段的赋值——命中权重只活在比较器里。"""
        hits = re.findall(r"\bscore\s*=[^=>]", JS)
        self.assertEqual(hits, [], "模板出现了 .score= 赋值：%s——分数被改写就不是重排了" % hits)

    def test_feed_and_hot_sort_on_comparators(self):
        """精选按 rankKey、热点按 topicKey，且热点无快照不重排（保上游原序）。"""
        flat = re.sub(r"\s+", "", JS)
        self.assertIn("groups[d].slice().sort((a,b)=>rankKey(b)-rankKey(a))", flat,
                      "精选日分组排序不再走 rankKey：重排没接上，或偷偷改回了别的键")
        self.assertIn("elseif(PROFILE.snap)ts.sort((a,b)=>topicKey(b)-topicKey(a));", flat,
                      "热点排序不再以快照在场为条件：无快照时也会破坏今天的原序")

    def test_pill_only_with_active_snapshot(self):
        body = re.sub(r"\s+", "", _fn_body("rankPillHtml"))
        self.assertIn('if(!PROFILE.snap)return"";', body,
                      "胶囊不再以活跃快照为门：未登录/无快照用户也会看到「按你的研究兴趣排序」")

    def test_hit_weights_only_in_keyfn(self):
        """score_final = score × (1 + Σ命中权重)：公式只出现在 rankKey/topicKey。"""
        self.assertIn("((it.score)||0)*(1+hitWeight(", JS)
        self.assertIn("((t.heat||t.score)||0)*(1+hitWeight(", JS)
        body = re.sub(r"\s+", "", _fn_body("hitWeight"))
        self.assertIn("sum+=tp.w;", body, "主题命中不再累加快照随行权重")
        self.assertIn("s.cats.indexOf(String(cat).toLowerCase())>=0", body,
                      "分类命中不再走小写比对（快照 categories 是小写口径）")


class TestPillAndPanelStyled(unittest.TestCase):
    """轻量存在性：胶囊与深链按钮有样式挂点，内联进产物后不至于裸奔。"""

    def test_css_hooks_present(self):
        for sel in (".rankpill", ".smbtn", ".amsg", ".ainfo", ".abody"):
            self.assertIn(sel, CSS, "%s 样式没了：新面板会以裸 HTML 上线" % sel)

    def test_dark_theme_reuses_tokens(self):
        """新增块只许用既有颜色 token（test_theme 的硬编码色扫描是全局的，
        这里再点名一次最容易写错的面板底纹，防"顺手加个 #fff"）。"""
        body = CSS[CSS.index(".rankpill"):CSS.index(".abind")]
        self.assertNotIn("#", re.sub(r"/\*.*?\*/", "", body, flags=re.S),
                         "胶囊样式块出现了硬编码颜色，深色模式会漏白")


if __name__ == "__main__":
    unittest.main(verbosity=2)
