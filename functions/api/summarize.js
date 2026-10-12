/**
 * PAT-HOT 按需中文摘要（Cloudflare Pages Function，同站 /api/summarize）
 * POST /api/summarize  {title, source, summary, url, domain}
 * 返回 {zh_full, summary, reason, density}
 * SENSENOVA_API_KEY 通过 Pages 环境变量（Secret）配置，不在代码/仓库中。
 *
 * 为什么走同站而不是 *.workers.dev：workers.dev 在中国大陆普遍被 DNS 污染/封锁
 * （实测本机 academic-ai-worker.3335264558.workers.dev 解析到 Facebook 段且 TCP 失败），
 * 而本站受众正是「无法访问外网的中国大学生」。同站 Function 免 CORS、免被墙。
 */

const UPSTREAM = "https://token.sensenova.cn/v1/chat/completions";
const MODEL = "sensenova-6.8-flash-lite";

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { ...CORS, "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

function buildPrompt(title, source, summary, domain) {
  const desc = (summary || "").replace(/\s+/g, " ").slice(0, 600);
  return (
    `你是${domain}资讯编辑，读者是无法访问外网的中国大学生，只能在站内阅读你的中文输出。` +
    `对下列资讯返回一个 JSON 对象，键为 "0"，值为 {"zh_full": "中文完整摘要（300-500字）：把摘要翻译整理成通顺中文，保留关键数据、结论、背景和意义；英文摘要要全文翻译，不要省略；无摘要时根据标题合理展开", ` +
    `"summary": "中文内容概要（150-250字）", "reason": "推荐理由（25字内）", "density": "高/中/低"}。\n` +
    `信息密度：高=有实质技术、数据或产业信息；中=一般资讯；低=营销稿、标题党、无实质内容。\n` +
    `[0] ${title}\n来源：${source}\n摘要：${desc || "（无摘要，仅标题）"}`
  );
}

/**
 * 稳健解析模型返回：推理模型偶尔把 JSON 包在 ```json 代码围栏里或前后带解释文字，
 * 直接 JSON.parse 会抛 "Unexpected token" 而让整次摘要失败。
 */
function parseModelJson(text) {
  const raw = String(text || "");
  const attempts = [];
  attempts.push(raw);
  const fence = raw.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fence) attempts.push(fence[1]);
  const first = raw.indexOf("{");
  const last = raw.lastIndexOf("}");
  if (first >= 0 && last > first) attempts.push(raw.slice(first, last + 1));
  for (const s of attempts) {
    const t = (s || "").trim();
    if (!t) continue;
    try { return JSON.parse(t); } catch (e) { /* 试下一种 */ }
  }
  return null;
}

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: CORS });
}

export async function onRequestPost(context) {
  const { request, env } = context;
  const apiKey = env.SENSENOVA_API_KEY;
  if (!apiKey) return json({ error: "未配置 SENSENOVA_API_KEY" }, 500);

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "请求体不是合法 JSON" }, 400);
  }
  const { title = "", source = "", summary = "", domain = "科学" } = body || {};
  if (!title) return json({ error: "缺少 title" }, 400);

  const messages = [{
    role: "user",
    content: buildPrompt(String(title).slice(0, 500), String(source).slice(0, 200), String(summary), String(domain).slice(0, 40)),
  }];

  let lastError = "上游无响应";
  const startedAt = Date.now();
  for (let attempt = 0; attempt < 2; attempt++) {
    // Pages Function 单次调用约 30s 墙上时钟上限：首次已经很慢时不再重试，
    // 否则第二次会一起超时，用户只会拿到平台的 500 而不是一条可读的错误。
    if (attempt > 0 && Date.now() - startedAt > 10000) break;
    try {
      const resp = await fetch(UPSTREAM, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: "Bearer " + apiKey },
        body: JSON.stringify({
          model: MODEL,
          messages,
          temperature: attempt === 0 ? 0.2 : 0,
          response_format: { type: "json_object" },
        }),
      });
      if (!resp.ok) {
        const t = await resp.text();
        lastError = `SenseNova 返回 ${resp.status}: ${t.slice(0, 200)}`;
        if (resp.status === 401 || resp.status === 403) break;
        continue;
      }
      const data = await resp.json();
      const msg = data && data.choices && data.choices[0] && data.choices[0].message;
      if (!msg || !msg.content) { lastError = "上游返回空内容"; continue; }
      const content = parseModelJson(msg.content);
      if (!content) { lastError = "上游返回非 JSON（已重试）"; continue; }
      const r = content["0"] || content[0] || content;
      return json({
        zh_full: String(r.zh_full || "").slice(0, 1200),
        summary: String(r.summary || "").slice(0, 300),
        reason: String(r.reason || "").slice(0, 80),
        density: ["高", "中", "低"].includes(r.density) ? r.density : "",
      });
    } catch (e) {
      lastError = String((e && e.message) || e).slice(0, 300);
    }
  }
  return json({ error: lastError }, 502);
}
