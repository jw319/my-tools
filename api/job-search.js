export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).end();

  const { resumeBase64, resumeText, baseCity, district, keywords, categories, experience, campusMode, gradYear } = req.body || {};

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

  const categoryList = Array.isArray(categories) ? categories.filter(Boolean) : [];

  const preferenceLines = [
    `工作地点偏好（base 地）：${baseCity}${district ? `，${district}` : ''}`,
    keywords ? `目标岗位/关键词：${keywords}` : '',
    categoryList.length ? `感兴趣的岗位方向（可能不止一个）：${categoryList.join('、')}` : '',
    !campusMode && experience ? `经验要求：${experience}` : '',
    campusMode ? `目标届别：${gradYear || '2027届'}` : '',
  ].filter(Boolean).join('\n');

  const categoryInstruction = categoryList.length > 1
    ? `我选了多个感兴趣的方向（${categoryList.join('、')}），请尽量覆盖到每个方向都至少有 1-2 个结果，不要全部集中在一个方向。`
    : '';

  const promptText = campusMode ? `你是一名熟悉中国校园招聘节奏的猎头顾问。请阅读我随附的简历，并使用联网搜索工具，帮我查找目前真实可投的、面向${gradYear || '2027届'}的机会。

${preferenceLines}

背景：正式秋招大规模启动前，很多公司会先放出提前批、暑期实习（表现好可留用转正）、内推码、宣讲会预告等机会，这些现在就可以关注和投递。请重点找这类信息，而不是要等到秋招正式开始才有的岗位。

要求：
1. 只返回你通过联网搜索确认目前真实开放中的机会，务必附上真实、可点击的原始链接（公司官网校招页、牛客网、BOSS直聘校园版、实习僧等均可），绝不编造任何链接或信息。
2. 优先匹配我的专业背景和简历经历，地点需在“${baseCity}”或明确支持远程/多地点。
${categoryInstruction}
3. 每条机会请说明属于哪种类型（提前批 / 暑期实习 / 内推 / 宣讲会 / 其他），以及具体投递方式（如“官网投递”“内推码：xxx”“牛客网投递”等）。
4. 如果能找到截止时间或薪资/实习津贴信息，请一并给出；找不到就留空，不要编造。
5. 先用1-2句话简单介绍你的搜索思路，然后严格按以下格式输出一个 JSON 代码块（用 \`\`\`json 包裹），代码块内不要有注释或多余文字：

[
  {
    "title": "职位名称",
    "company": "公司名称",
    "location": "工作地点",
    "category": "所属岗位方向，如'产品'、'市场营销'，没有明确方向就留空",
    "opportunity_type": "提前批 / 暑期实习 / 内推 / 宣讲会 / 其他",
    "salary_range": "薪资或实习津贴，找不到则为空字符串",
    "match_reason": "为什么适合我（1句话）",
    "apply_method": "投递方式",
    "apply_link": "真实链接",
    "source_note": "信息来源"
  }
]

请返回 6-10 条结果，按匹配度和紧迫程度排序。如果找不到足够真实的机会，宁可少返回，也不要编造。` : `你是一名资深猎头顾问。请阅读我随附的简历，并使用联网搜索工具，结合我的简历背景和下面填写的兴趣方向，帮我查找当前真实在招、我可能感兴趣的职位。

${preferenceLines}

要求：
1. 只返回你通过联网搜索确认目前仍在招聘的真实职位，务必附上真实、可点击的原始链接（公司官网招聘页、BOSS直聘、猎聘、LinkedIn、拉勾、智联招聘等均可），绝不编造任何链接或职位信息。
2. 优先匹配我的技能、经验年限和过往行业背景，职位地点需在“${baseCity}”或明确支持远程；如果我填写了感兴趣的岗位方向，职位应落在这些方向内。
${categoryInstruction}
3. 每条职位请说明投递方式（如“官网投递”“内推”“BOSS直聘在线沟通”等），并标注这条职位属于我填写的哪个岗位方向（如果我填写了方向的话）。
4. 如果能在招聘信息中找到薪资范围，请一并给出；找不到就留空，不要编造。
5. 先用1-2句话简单介绍你的搜索思路，然后严格按以下格式输出一个 JSON 代码块（用 \`\`\`json 包裹），代码块内不要有注释或多余文字：

[
  {
    "title": "职位名称",
    "company": "公司名称",
    "location": "工作地点",
    "category": "所属岗位方向，如'产品'、'市场营销'，没有明确方向就留空",
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
