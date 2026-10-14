/**
 * PAT-HOT 按需中文摘要 Worker
 * POST /  {title, source, summary, url, domain}
 * 返回 {zh_full, summary, reason, density}
 * SENSENOVA_API_KEY 通过 Worker Secret 配置，不在代码中
 */

const CORS = {
  "Access-Control-Allow-Origin": "https://pat-hot.pages.dev",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

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

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: CORS });
    }
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405, headers: CORS });
    }
    const apiKey = env.SENSENOVA_API_KEY;
    if (!apiKey) {
      return new Response(JSON.stringify({ error: "未配置 SENSENOVA_API_KEY" }), {
        status: 500,
        headers: { ...CORS, "Content-Type": "application/json" },
      });
    }
    let body;
    try {
      body = await request.json();
    } catch {
      return new Response(JSON.stringify({ error: "请求体不是合法 JSON" }), {
        status: 400,
        headers: { ...CORS, "Content-Type": "application/json" },
      });
    }
    const { title = "", source = "", summary = "", domain = "科学" } = body;
    if (!title) {
      return new Response(JSON.stringify({ error: "缺少 title" }), {
        status: 400,
        headers: { ...CORS, "Content-Type": "application/json" },
      });
    }
    try {
      const resp = await fetch("https://token.sensenova.cn/v1/chat/completions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": "Bearer " + apiKey,
        },
        body: JSON.stringify({
          model: "sensenova-6.8-flash-lite",
          messages: [{ role: "user", content: buildPrompt(title, source, summary, domain) }],
          temperature: 0.2,
          response_format: { type: "json_object" },
        }),
      });
      if (!resp.ok) {
        const t = await resp.text();
        return new Response(JSON.stringify({ error: `SenseNova 返回 ${resp.status}: ${t.slice(0, 200)}` }), {
          status: 502,
          headers: { ...CORS, "Content-Type": "application/json" },
        });
      }
      const data = await resp.json();
      const content = JSON.parse(data.choices[0].message.content);
      const r = content["0"] || content[0] || content;
      return new Response(
        JSON.stringify({
          zh_full: String(r.zh_full || "").slice(0, 1200),
          summary: String(r.summary || "").slice(0, 300),
          reason: String(r.reason || "").slice(0, 80),
          density: ["高", "中", "低"].includes(r.density) ? r.density : "",
        }),
        { headers: { ...CORS, "Content-Type": "application/json" } }
      );
    } catch (e) {
      return new Response(JSON.stringify({ error: String(e.message || e).slice(0, 300) }), {
        status: 500,
        headers: { ...CORS, "Content-Type": "application/json" },
      });
    }
  },
};
