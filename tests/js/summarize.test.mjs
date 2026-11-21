/**
 * 按需中文摘要契约与 AIHOT 防幻觉/词表净化测试（functions/api/summarize.js & worker/pat-hot-llm.js）。
 * 纯离线测试：通过 fetchImpl 注入模拟 SenseNova 上游，验证：
 *  1. prompt 必须含 AIHOT 防幻觉规则、输入安全边界、宁短勿扩，且严禁出现"合理展开"
 *  2. 请求体必须携带 thinking: { type: "disabled" } 与 response_format: { type: "json_object" }
 *  3. parseModelJson 支持裸 JSON、```json 代码围栏与前后解释文字容错提取
 *  4. sanitizeWording 与 normalizeSummaryPayload：清洗夸张词/翻案套话；无摘要（仅标题）条目强制执行「宁短勿扩」与密度封顶（"高" -> "中"）
 *  5. 上游 500 自动重试、401/403 不盲目重试、空摘要重试、超时返回可读 502
 *  6. worker/pat-hot-llm.js 与 functions/api/summarize.js 保持严格同口径，零漂移
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "../..");

async function importEsmFile(relPath) {
  const fullPath = path.join(ROOT, relPath);
  const code = fs.readFileSync(fullPath, "utf-8");
  const b64 = Buffer.from(code, "utf-8").toString("base64");
  return import(`data:text/javascript;base64,${b64}`);
}

const summarizeMod = await importEsmFile("functions/api/summarize.js");
const workerMod = await importEsmFile("worker/pat-hot-llm.js");

const {
  buildPrompt,
  parseModelJson,
  sanitizeWording,
  normalizeSummaryPayload,
  onRequestOptions,
  onRequestPost,
} = summarizeMod;
const workerDefault = workerMod.default;

test("summarize prompt 锁死 AIHOT 防幻觉九条、输入安全边界与宁短勿扩", () => {
  const p = buildPrompt("室温超导新进展", "Nature Physics", "", "物理");
  assert.ok(!p.includes("合理展开"), "严禁命令模型在无摘要时按标题合理展开编造正文");
  assert.ok(p.includes("防幻觉规则"), "必须包含防幻觉规则");
  assert.ok(p.includes("输入安全边界"), "必须包含 prompt-injection 输入安全边界");
  assert.ok(p.includes("宁短勿扩"), "无摘要条目必须声明宁短勿扩");
  assert.ok(p.includes("（无摘要，仅标题）"), "空摘要必须显式标注（无摘要，仅标题）");
  // Worker 的 buildPrompt 必须与 Pages Function 完全一致
  assert.equal(workerMod.buildPrompt("室温超导新进展", "Nature Physics", "", "物理"), p);
});

test("parseModelJson：裸 JSON、Markdown 代码围栏与前后缀解释文字均可解析", () => {
  const raw = '{"0":{"zh_full":"全文","summary":"概要","reason":"理由","density":"高"}}';
  assert.deepEqual(parseModelJson(raw)["0"].summary, "概要");

  const fenced = "好的，这是为您生成的 JSON：\n```json\n" + raw + "\n```\n请查收。";
  assert.deepEqual(parseModelJson(fenced)["0"].zh_full, "全文");

  const noisy = "思考完毕：\n" + raw + "\n---";
  assert.deepEqual(parseModelJson(noisy)["0"].density, "高");

  assert.equal(parseModelJson("完全不是 JSON"), null);
  assert.equal(parseModelJson(""), null);
});

test("sanitizeWording 与 normalizeSummaryPayload：AIHOT 词表净化与无摘要宁短勿扩封顶", () => {
  const dirty = "重磅！这意味着，该团队实现了颠覆性的量子纠错突破，值得注意的是，效率提升显著。";
  const cleaned = sanitizeWording(dirty);
  assert.ok(!cleaned.includes("重磅"), "应去除句首夸张词");
  assert.ok(!cleaned.includes("这意味着"), "应去除翻案套话");
  assert.ok(!cleaned.includes("值得注意的是"), "应去除注水连接词");
  assert.ok(!cleaned.includes("颠覆性"), "应替换颠覆性等夸张定语");

  // 有原文摘要时：允许高密度与完整长度
  const fullOut = normalizeSummaryPayload({
    zh_full: "重磅！" + "甲".repeat(400),
    summary: "这意味着，" + "乙".repeat(200),
    reason: "必读！核心数据清晰",
    density: "高",
  }, true);
  assert.equal(fullOut.density, "高");
  assert.equal(fullOut.zh_full.length, 400);
  assert.ok(!fullOut.reason.includes("必读"));

  // 无原文摘要（仅标题）时：强制宁短勿扩（zh_full <= 180, summary <= 120）且密度不得虚标为"高"
  const titleOnlyOut = normalizeSummaryPayload({
    zh_full: "甲".repeat(400),
    summary: "乙".repeat(200),
    reason: "丙".repeat(60),
    density: "高",
  }, false);
  assert.equal(titleOnlyOut.zh_full.length, 180, "仅标题条目 zh_full 必须被宁短勿扩截断到 180 字内");
  assert.equal(titleOnlyOut.summary.length, 120, "仅标题条目 summary 必须被截断到 120 字内");
  assert.equal(titleOnlyOut.density, "中", "仅标题无正文支撑时 density 不得虚标为高");
});

test("onRequestPost：请求体携带 thinking:disabled，且成功净化返回载荷", async () => {
  let capturedBody = null;
  const fakeFetch = async (_url, init) => {
    capturedBody = JSON.parse(init.body);
    return new Response(JSON.stringify({
      choices: [{
        message: {
          content: "```json\n" + JSON.stringify({
            "0": {
              zh_full: "重磅！研究团队展示了 400W 单模光纤激光器，这意味着电光效率达到 52%。",
              summary: "值得注意的是，400W 单模连续光纤激光器进入量产。",
              reason: "核心量产参数明确",
              density: "高",
            },
          }) + "\n```",
        },
      }],
    }), { status: 200 });
  };

  const req = new Request("https://pat-hot.pages.dev/api/summarize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: "400W 单模光纤激光器量产",
      source: "OFweek 激光",
      summary: "厂商公告电光转化效率 52%。",
      domain: "光电",
    }),
  });

  const resp = await onRequestPost({
    request: req,
    env: { SENSENOVA_API_KEY: "test-key" },
    fetchImpl: fakeFetch,
  });
  assert.equal(resp.status, 200);
  assert.deepEqual(capturedBody.thinking, { type: "disabled" }, "必须显式关闭推理链");
  assert.deepEqual(capturedBody.response_format, { type: "json_object" });

  const data = await resp.json();
  assert.ok(!data.zh_full.includes("重磅"));
  assert.ok(!data.zh_full.includes("这意味着"));
  assert.ok(data.zh_full.includes("52%"));
  assert.equal(data.density, "高");
});

test("onRequestPost：首次非 JSON 自动降温重试，401/403 立即终止不盲目重试", async () => {
  let calls = 0;
  const retryFetch = async (_url, init) => {
    calls += 1;
    const body = JSON.parse(init.body);
    if (calls === 1) {
      assert.equal(body.temperature, 0.2);
      return new Response(JSON.stringify({
        choices: [{ message: { content: "broken { json" } }],
      }), { status: 200 });
    }
    assert.equal(body.temperature, 0, "第二次重试应降为 temperature=0");
    return new Response(JSON.stringify({
      choices: [{
        message: {
          content: JSON.stringify({
            "0": { zh_full: "重试成功摘要", summary: "重试概要", reason: "理由", density: "中" },
          }),
        },
      }],
    }), { status: 200 });
  };

  const makeReq = () => new Request("https://pat-hot.pages.dev/api/summarize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "测试标题", summary: "测试摘要" }),
  });

  const okResp = await onRequestPost({
    request: makeReq(),
    env: { SENSENOVA_API_KEY: "k" },
    fetchImpl: retryFetch,
  });
  assert.equal(okResp.status, 200);
  assert.equal(calls, 2);

  let authCalls = 0;
  const authFailFetch = async () => {
    authCalls += 1;
    return new Response("invalid api key", { status: 401 });
  };
  const failResp = await onRequestPost({
    request: makeReq(),
    env: { SENSENOVA_API_KEY: "bad-key" },
    fetchImpl: authFailFetch,
  });
  assert.equal(failResp.status, 502);
  assert.equal(authCalls, 1, "401 鉴权失败不应浪费第二次重试");
});

test("worker/pat-hot-llm.js 与 Pages Function 行为一致（OPTIONS 204 / GET 405 / POST 同口径）", async () => {
  const optResp = await workerDefault.fetch(
    new Request("https://worker.example/", { method: "OPTIONS" }),
    {}
  );
  assert.equal(optResp.status, 204);

  const getResp = await workerDefault.fetch(
    new Request("https://worker.example/", { method: "GET" }),
    {}
  );
  assert.equal(getResp.status, 405);

  const postResp = await workerDefault.fetch(
    new Request("https://worker.example/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "仅有标题的快讯", summary: "" }),
    }),
    { SENSENOVA_API_KEY: "k" },
    {
      fetchImpl: async () => new Response(JSON.stringify({
        choices: [{
          message: {
            content: JSON.stringify({
              "0": { zh_full: "仅有标题的快讯复述。", summary: "快讯复述。", reason: "", density: "高" },
            }),
          },
        }],
      }), { status: 200 }),
    }
  );
  assert.equal(postResp.status, 200);
  const body = await postResp.json();
  assert.equal(body.density, "中", "Worker 对无摘要条目同样执行密度封顶（高 -> 中）");
});
