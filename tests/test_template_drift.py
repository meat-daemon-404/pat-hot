# -*- coding: utf-8 -*-
"""模板→产物同步自检（纯标准库，无网络）。

锁住的回归（2026-10-13）：折叠串台的模板修复提交后，仓库里的 dist/index.html
没重渲染——Pages 部署的正是仓库产物，修复根本没上线，只能事后手工补 build 提交。
--check 从此要求产物等于模板重渲染（快照数据除外）。
"""
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "collector"))

import collect  # noqa: E402


def _dist_html():
    p = os.path.join(ROOT, "dist", "index.html")
    if not os.path.exists(p):
        return None
    with io.open(p, encoding="utf-8") as f:
        return f.read()


class TestInlineAppScript(unittest.TestCase):
    def test_finds_script_holding_snapshot_not_first(self):
        """head 里的主题引导脚本在先，必须按"含 const S"取段而不是取第一个 <script>。"""
        html = ("<html><head><script>var bootstrap=1;</script></head>"
                "<body><script>\nconst S = {};\nalert(1)\n</script></body></html>")
        js = collect.inline_app_script(html)
        self.assertIsNotNone(js)
        self.assertIn("const S", js)
        self.assertIn("alert(1)", js)
        self.assertNotIn("bootstrap", js)

    def test_none_when_no_snapshot_script(self):
        self.assertIsNone(collect.inline_app_script("<html><script>x</script></html>"))


class TestTemplateDrift(unittest.TestCase):
    def setUp(self):
        self.html = _dist_html()
        if self.html is None:
            self.skipTest("dist/index.html 尚未生成")
        self._css, self._js, self._html_tpl = collect.APP_CSS, collect.APP_JS, collect.APP_HTML

    def tearDown(self):
        collect.APP_CSS, collect.APP_JS, collect.APP_HTML = self._css, self._js, self._html_tpl

    def test_current_artifact_matches_templates(self):
        problems = collect.check_template_drift(self.html)
        self.assertEqual(problems, [],
                         "当前 dist/index.html 应与模板一致（不一致就先跑 --rebuild）：%s" % problems)

    def test_css_edit_without_rebuild_is_caught(self):
        collect.APP_CSS = self._css + "\n.newrule{color:red}\n"
        self.assertTrue(collect.check_template_drift(self.html),
                        "改 app.css 不重渲染必须被 --check 拦下")

    def test_js_edit_without_rebuild_is_caught(self):
        collect.APP_JS = "// helper added\n" + self._js
        self.assertTrue(collect.check_template_drift(self.html),
                        "改 app.js 不重渲染必须被 --check 拦下")

    def test_shell_edit_without_rebuild_is_caught(self):
        """app.html 的 head/body 改动（如主题引导脚本）只比 CSS/JS 会漏掉。"""
        collect.APP_HTML = self._html_tpl.replace("</body>", "<div id='x'></div></body>")
        self.assertTrue(collect.check_template_drift(self.html),
                        "改 app.html 不重渲染必须被 --check 拦下")

    def test_snapshot_data_change_alone_is_ignored(self):
        """快照是数据，每次采集都变，不能算模板漂移。"""
        i = self.html.index('"generatedAt"')
        bumped = self.html[:i] + self.html[i:].replace('"generatedAt": "20', '"generatedAt": "21', 1)
        self.assertEqual(collect.check_template_drift(bumped), [],
                         "只有快照数据不同必须放行")


class TestHeadScriptSurvivesBuild(unittest.TestCase):
    def test_head_bootstrap_present_in_artifact(self):
        """模板 head 里若有引导脚本，产物必须原样带上（骨架断言的端到端佐证）。"""
        html = _dist_html()
        if html is None:
            self.skipTest("dist/index.html 尚未生成")
        head_tpl = collect.APP_HTML[:collect.APP_HTML.index("<style")]
        # 去掉占位符行本身，其余 head 内容应逐字出现在产物头部之前
        for line in head_tpl.splitlines():
            line = line.strip()
            if line and "/*__CSS__*/" not in line:
                self.assertIn(line, html[:html.index("<style")],
                              "模板 head 内容未原样进入产物：%s" % line)


if __name__ == "__main__":
    unittest.main(verbosity=2)
