---
name: web-search
description: 联网搜索——当用户问题涉及最新信息、时事、或本地知识库无法覆盖的内容时，通过 Brave Search API 获取外部资料作为回答依据。
always: false
---

# Web Search

## When to Use

- User asks about current events, recent developments, or time-sensitive information
- Keywords detected: "最新", "今天", "新闻", "网上", "搜索", "latest", "current", "today", "news"
- LightRAG retrieval returned empty or insufficient results AND the topic is factual
- User explicitly requests external sources

## How to Apply

1. **Formulate search query** — extract the core question, translate to effective search terms
   - Prefer specific terms over broad ones
   - Include language hint if user is asking in Chinese (add Chinese keywords)
   - Limit to 3-5 key terms

2. **Execute search** — call Brave Search API with the query
   - Max 5 results per query
   - Filter for educational/authoritative sources when possible

3. **Evaluate results** — check relevance and recency
   - Discard results older than the user's implied timeframe
   - Prefer .edu, .org, Wikipedia, established media
   - Flag if no relevant results found

4. **Synthesize into answer** — integrate web results with existing knowledge
   - Always cite sources with URL
   - Clearly distinguish "from web search" vs "from course materials"
   - If web results contradict course materials, present both and explain

## Safety

- Never search for harmful, illegal, or age-inappropriate content
- Respect robots.txt and rate limits
- Do not expose raw API keys or internal URLs to the user
- Whitelist domains for K12 content (Wikipedia, Khan Academy, educational sites)

## Output Format

When citing web results in the response:

```
根据搜索结果：
- [来源标题](URL) — 关键信息摘要
- [来源标题](URL) — 关键信息摘要

基于以上资料，...
```

## Fallback

If search fails or returns no results:
- Inform user: "我没有找到相关的最新资料，以下基于我的通用知识回答"
- Proceed with LLM general knowledge
- Suggest user verify time-sensitive claims independently
