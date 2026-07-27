export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).end();

  const { resumeBase64, resumeText, baseCity, district, keywords, category, experience } = req.body || {};

  if (!baseCity || (!resumeBase64 && !resumeText)) {
    return res.status(400).json({ error: { message: '缺少简历或 base 地信息' } });
  }

  const apiKey = process.env.ANTHROPIC_API_KEY;

  const contentBlocks = [];
  if (resumeBase64) {
    contentBlocks.push({
      type: 'document',
      source: { type: 'base64', media_type: 'application/pdf', data: resumeBase64 },
    });
  } else {
    contentBlocks.push({ type: 'text', text: `以下是我的简历内容：\n\n${resumeText}` });
  }

  const preferenceLines = [
    `工作地点偏好（base 地）：${baseCity}${district ? `，${district}` : ''}`,
    keywords ? `目标岗位/关键词：${keywords}` : '',
    category ? `岗位类别偏好：${category}` : '',
    experience ? `经验要求：${experience}` : '',
  ].filter(Boolean).join('\n');

  const promptText = `你是一名资深猎头顾问。请阅读我随附的简历，并使用联网搜索工具，帮我查找当前真实在招、与我背景匹配的职位。

${preferenceLines}

要求：
1. 只返回你通过联网搜索确认目前仍在招聘的真实职位，务必附上真实、可点击的原始链接（公司官网招聘页、BOSS直聘、猎聘、LinkedIn、拉勾、智联招聘等均可），绝不编造任何链接或职位信息。
2. 优先匹配我的技能、经验年限和过往行业背景，职位地点需在“${baseCity}”或明确支持远程。
3. 每条职位请说明投递方式（如“官网投递”“内推”“BOSS直聘在线沟通”等）。
4. 如果能在招聘信息中找到薪资范围，请一并给出；找不到就留空，不要编造。
5. 先用1-2句话简单介绍你的搜索思路，然后严格按以下格式输出一个 JSON 代码块（用 \`\`\`json 包裹），代码块内不要有注释或多余文字：

[
  {
    "title": "职位名称",
    "company": "公司名称",
    "location": "工作地点",
    "salary_range": "薪资范围，找不到则为空字符串",
    "match_reason": "为什么适合我（1句话）",
    "apply_method": "投递方式",
    "apply_link": "真实链接",
    "source_note": "信息来源，如'公司官网'或'BOSS直聘'"
  }
]

请返回 6-10 条结果，按匹配度从高到低排序。如果找不到足够匹配的真实职位，宁可少返回，也不要编造。`;

  contentBlocks.push({ type: 'text', text: promptText });

  const response = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
    },
    body: JSON.stringify({
      model: 'claude-sonnet-5',
      max_tokens: 6000,
      system: '你是一名信息准确、绝不编造链接和职位信息的资深猎头顾问，只依据联网搜索到的真实公开信息作答，找不到足够真实匹配的职位时宁可少给。',
      messages: [{ role: 'user', content: contentBlocks }],
      tools: [{ type: 'web_search_20250305', name: 'web_search', max_uses: 6 }],
    }),
  });

  const data = await response.json();
  res.status(response.status).json(data);
}
