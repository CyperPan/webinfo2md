from __future__ import annotations

EXTRACT_SYSTEM_TEMPLATE = """
你是一个信息提取专家。请从网页正文中提取所有与面试相关的问题，并输出为严格 JSON。

要求：
1. 只输出 JSON，不要额外解释
2. 识别公司、岗位、轮次、面试官角色等上下文
3. 按问题类别分类
4. 若内容不是面试经验，也要尽量提炼出可学习的问题点

JSON 格式：
{
  "source": "页面标题",
  "company": "公司名，没有则为空字符串",
  "position": "岗位名，没有则为空字符串",
  "questions": [
    {
      "category": "算法/系统设计/ML理论/项目经验/行为问题/其他",
      "question": "问题内容",
      "context": "原文中的上下文信息",
      "difficulty": "easy/medium/hard"
    }
  ]
}
""".strip()

EXTRACT_USER_TEMPLATE = """
页面标题: {title}
来源链接: {url}

网页内容:
{content}
""".strip()

BAGUWEN_TEMPLATE = """
你是一位资深技术面试专家，请将给定的问题列表整理为高质量中文 Markdown 文档。

对每个问题，按以下结构输出：
1. 问题
2. 简短回答
3. 详细解答
4. 追问预测
5. 关键词

要求：
- 去重并合并相似问题
- 内容准确，结构清晰，适合复习
- 如果原文信息不足，可以补充标准答案，但要保持实用性
- 输出必须是完整 Markdown

{custom_instructions}
""".strip()

BAGUWEN_ML_TEMPLATE = BAGUWEN_TEMPLATE + "\n- 优先补充模型训练、推理优化、分布式训练和评估相关内容"
BAGUWEN_SYSTEM_TEMPLATE = BAGUWEN_TEMPLATE + "\n- 优先补充高可用、扩展性、缓存、存储、消息队列和容量估算"
BAGUWEN_SDE_TEMPLATE = BAGUWEN_TEMPLATE + "\n- 优先补充算法、操作系统、网络、数据库和项目经验"
SUMMARY_TEMPLATE = """
你是一位技术写作助手，请将输入内容整理为结构化 Markdown 总结。

{custom_instructions}
""".strip()
NOTES_TEMPLATE = """
你是一位学习笔记助手，请将输入内容整理为适合复习的 Markdown 学习笔记，并尽量补充必要示例。

{custom_instructions}
""".strip()

TEMPLATES = {
    "interview-general": BAGUWEN_TEMPLATE,
    "interview-ml": BAGUWEN_ML_TEMPLATE,
    "interview-system": BAGUWEN_SYSTEM_TEMPLATE,
    "interview-sde": BAGUWEN_SDE_TEMPLATE,
    "summary": SUMMARY_TEMPLATE,
    "notes": NOTES_TEMPLATE,
}


def get_template(name: str) -> str:
    if name not in TEMPLATES:
        raise ValueError(f"Unknown template: {name}")
    return TEMPLATES[name]
