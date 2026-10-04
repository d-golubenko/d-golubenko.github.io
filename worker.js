// Agent names are self-reported User-Agent hints, not verified identities.
export function classifyAgent(userAgent) {
  const known = /OAI-SearchBot|ChatGPT-User|GPTBot|Claude-SearchBot|Claude-User|ClaudeBot|PerplexityBot|Perplexity-User|Googlebot|Bingbot|Applebot|DuckDuckBot/i.exec(userAgent);
  if (known) return { category: /Googlebot|Bingbot|Applebot|DuckDuckBot/i.test(known[0]) ? "search_bot" : "ai_bot", agent: known[0].toLowerCase() };
  if (/bot|crawler|spider|slurp/i.test(userAgent)) return { category: "other_bot", agent: "other_bot" };
  return { category: "browser_or_unknown", agent: "browser_or_unknown" };
}

export default {
  async fetch(request, env) {
    const response = await env.ASSETS.fetch(request);
    const url = new URL(request.url);
    const visitor = classifyAgent(request.headers.get("user-agent") || "");
    // No IP addresses, query strings, cookies, or raw User-Agent are recorded.
    console.log({
      event: "site_visit",
      path: url.pathname.slice(0, 256),
      method: request.method,
      status: response.status,
      content_type: response.headers.get("content-type")?.split(";")[0] || "",
      category: visitor.category,
      agent: visitor.agent
    });
    return response;
  }
};
