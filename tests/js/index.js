// 为什么存在这个文件：`node --test tests/js` 是任务书验收命令的字面写法。
// Node 23+ 把 --test 的位置参数当文件/模块解析（目录不再是搜索根，
// 直接给目录会报 ERR_UNSUPPORTED_DIR_IMPORT / MODULE_NOT_FOUND），
// 目录解析规则会落到本文件（CommonJS 的目录 → index.js）。
// 本文件把同目录下全部 *.test.mjs require 进来——Node ≥22.12 支持
// require(esm)，测试照常注册、照常跑。
//
// 老版本 Node（CI ubuntu-latest 自带的 Node 20 仍按目录扫描）：
// index.js 不匹配测试文件命名规则（*.test.mjs 等）会被扫描跳过，
// 五个 .test.mjs 各自独立成进程运行。两种解析路径跑的是同一批用例，
// 不存在"测试只在某版本上绿"的运气。
const { readdirSync } = require("node:fs");
const path = require("node:path");

const files = readdirSync(__dirname).filter((f) => f.endsWith(".test.mjs")).sort();
if (files.length === 0) {
  throw new Error("tests/js/index.js：同目录没有 *.test.mjs，测试套件丢失");
}
for (const f of files) {
  require(path.join(__dirname, f));
}
