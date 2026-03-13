# webinfo2md

一个命令行工具：抓取网页内容，通过 LLM 提取并整理关键信息，输出结构化的 Markdown 文档。

支持面试八股文整理、技术文档摘要、笔记提取等多种场景。

## 功能特性

- 自动抓取网页（httpx 静态抓取 + Playwright 动态渲染双模式）
- 两阶段 LLM 流水线：并发分块提取 → 并行批次合成
- 支持 6 种 LLM 提供商：OpenAI、Anthropic、Claude、DeepSeek、Kimi、Gemini
- 交互式模式：逐步引导选择提供商、模型、输入 API Key 并验证
- 多 URL 合并：多个网页的内容合并到一个文档中
- 输出格式优化：元数据表格、目录、分类分组、总结表
- 支持深度爬取、Cookie 登录、无限滚动等高级功能

## 环境要求

- Python >= 3.11
- pip（推荐使用虚拟环境）
- 至少一个 LLM 提供商的 API Key

## 安装

### 1. 克隆项目

```bash
git clone https://github.com/CyperPan/webinfo2md.git
cd webinfo2md
```

### 2. 创建虚拟环境（推荐）

```bash
python -m venv .venv
source .venv/bin/activate  # macOS / Linux
# .venv\Scripts\activate   # Windows
```

### 3. 安装项目

基础安装（仅包含核心依赖）：

```bash
pip install -e .
```

按需安装 LLM 提供商依赖：

```bash
# OpenAI / DeepSeek / Kimi / Gemini（共用 openai SDK）
pip install -e ".[openai]"

# Anthropic / Claude
pip install -e ".[anthropic]"

# 动态渲染页面支持（Playwright）
pip install -e ".[playwright]"
playwright install chromium

# 全部安装（开发环境）
pip install -e ".[dev,openai,anthropic,playwright]"
```

## 配置 API Key

有三种方式提供 API Key（优先级从高到低）：

### 方式一：命令行参数

```bash
webinfo2md --api-key "sk-xxx" --url "https://example.com"
```

### 方式二：环境变量

```bash
# 在 .env 文件或 shell 中设置
export OPENAI_API_KEY="sk-xxx"
export ANTHROPIC_API_KEY="sk-ant-xxx"
export DEEPSEEK_API_KEY="sk-xxx"
export KIMI_API_KEY="sk-xxx"
export GEMINI_API_KEY="xxx"

# 通用变量（适用于所有提供商）
export LLM_API_KEY="sk-xxx"
```

支持的环境变量完整列表：

| 提供商 | 环境变量 |
|--------|----------|
| OpenAI | `OPENAI_API_KEY`, `LLM_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY`, `CLAUDE_API_KEY`, `LLM_API_KEY` |
| DeepSeek | `DEEPSEEK_API_KEY`, `LLM_API_KEY` |
| Kimi | `KIMI_API_KEY`, `MOONSHOT_API_KEY`, `LLM_API_KEY` |
| Gemini | `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `LLM_API_KEY` |

### 方式三：配置文件

创建 `~/.webinfo2md/config.yaml`：

```yaml
provider: openai
model: gpt-4o-mini
api_key: sk-xxx          # 也可以省略，使用环境变量
template: interview-general
chunk_size: 3000
max_concurrency: 5
pages: 5
crawl_delay_min: 0.5
crawl_delay_max: 1.5

# Playwright 配置（可选）
force_playwright: false
playwright:
  enable_scroll: false
  wait_until: networkidle
  wait_timeout_ms: 20000
  # cookie_file: ~/.webinfo2md/cookies.json
  # screenshot_path: ./debug.png
```

## 使用教程

### 快速开始（交互式模式）

最简单的方式，工具会逐步引导你完成所有设置：

```bash
webinfo2md --interactive
```

交互流程：
1. 选择 LLM 提供商（openai / anthropic / deepseek / kimi / gemini）
2. 确认或修改模型名称
3. 输入 API Key（自动验证是否有效）
4. 输入网页 URL
5. 描述需要提取的信息类型
6. 等待处理，输出文件自动保存到 `output/` 目录

### 命令行模式

一行命令完成所有操作：

```bash
webinfo2md \
  --url "https://example.com/interview-post" \
  --provider openai \
  --model gpt-4o-mini \
  --prompt "提取所有面试问题，整理为八股文格式，补充标准答案"
```

输出文件默认保存到 `output/` 目录。也可以用 `--output` 指定路径：

```bash
webinfo2md \
  --url "https://example.com" \
  --output my_notes.md
```

### 常用场景

**面试八股文整理：**

```bash
webinfo2md \
  --url "https://www.nowcoder.com/discuss/353159520220291072" \
  --provider openai \
  --prompt "提取所有面试问题，整理为八股文格式，补充标准答案"
```

**技术文档摘要：**

```bash
webinfo2md \
  --url "https://docs.python.org/3/library/asyncio.html" \
  --prompt "提取核心概念、API 用法和最佳实践"
```

**多网页合并整理：**

```bash
webinfo2md \
  --url-list urls.txt \
  --prompt "提取所有面试问题，合并同类问题"
```

其中 `urls.txt` 每行一个 URL：

```
https://example.com/page1
https://example.com/page2
# 以 # 开头的行会被忽略
https://example.com/page3
```

**动态渲染页面（需要 Playwright）：**

```bash
webinfo2md \
  --url "https://example.com/spa-page" \
  --force-playwright \
  --scroll \
  --cookie-file ~/.webinfo2md/cookies.json
```

**预览模式（不调用 LLM）：**

```bash
webinfo2md \
  --url "https://example.com" \
  --dry-run
```

输出爬取页数、分块数、预估 Token 数，用于在正式运行前评估成本。

### 完整参数列表

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--url` | 目标网页 URL | 交互输入 |
| `--url-list` | URL 列表文件路径 | - |
| `--provider` | LLM 提供商 | `openai` |
| `--model` | 模型名称 | 各提供商默认模型 |
| `--api-key` | API Key | 环境变量 / 交互输入 |
| `--prompt` | 提取指令 | 交互输入 |
| `--template` | 内置模板 | `interview-general` |
| `--output` | 输出文件路径 | `output/<url-slug>.md` |
| `--output-dir` | 批量输出目录 | - |
| `--config` | 配置文件路径 | `~/.webinfo2md/config.yaml` |
| `--depth` | 爬取深度（跟踪链接层数） | `0` |
| `--pages` | 最大爬取页数 | `5` |
| `--chunk-size` | 分块大小（Token） | `3000` |
| `--concurrency` / `-j` | 并发提取数 | `5` |
| `--force-playwright` | 强制使用 Playwright | `false` |
| `--cookie-file` | Playwright Cookie 文件 | - |
| `--scroll` / `--no-scroll` | 是否无限滚动 | `false` |
| `--screenshot` | 保存调试截图 | - |
| `--dry-run` | 仅爬取分块，不调用 LLM | `false` |
| `--verbose` | 详细日志 | `false` |
| `--interactive` | 交互式模式 | `false` |

### 默认模型

| 提供商 | 默认模型 |
|--------|----------|
| openai | `gpt-4o-mini` |
| anthropic / claude | `claude-3-7-sonnet-latest` |
| deepseek | `deepseek-chat` |
| kimi | `moonshot-v1-32k` |
| gemini | `gemini-2.5-flash` |

## 示例输出

以 `https://example.com` 为输入，输出文件内容如下：

```markdown
# Example Domain

| 属性 | 信息 |
|------|------|
| 来源 | https://example.com |
| 整理时间 | 2026-03-13 11:41 |
| 问题总数 | 1 |

---

## 目录
- [域名使用](#域名使用)

---

## 域名使用

### 1. 什么是 Example Domain 的目的？
- **简短回答**：Example Domain 用于文档示例，避免在实际操作中使用。
- **详细解答**：
  - Example Domain 是一个专门为文档和示例而设的域名。
  - 其主要目的是提供一个无需获得许可的示例域名，方便开发者和文档撰写者使用。
  - 使用此域名可以避免在真实环境中使用真实域名，减少潜在的法律问题。
- **追问预测**：
  - 你能举例说明在什么情况下使用 Example Domain 吗？
  - 还有哪些类似的示例域名？
- **关键词**：`Example Domain` `文档示例` `无需许可`

---

## 总结

| 类别       | 问题数 | 关键技能点          |
|------------|--------|---------------------|
| 域名使用   | 1      | 域名用途，文档示例  |
```

面试场景的输出会包含更多分类（如 Hadoop、Spark、Flink 等），每个问题带有简短回答、详细解答、追问预测和关键词标签。

## 工作原理

```
输入 URL → 爬取网页 → 清洗 HTML → 分块
                                      ↓
                              并发 LLM 提取（每块独立）
                                      ↓
                              合并去重 → 并行批次合成
                                      ↓
                              生成结构化 Markdown → output/
```

1. **爬取**：先用 httpx 静态抓取，内容不足时自动回退到 Playwright
2. **分块**：将长文本按 ~3000 Token 切分，保证每块在 LLM 上下文窗口内
3. **提取**：5 路并发调用 LLM，从每个分块中提取结构化 JSON
4. **合成**：将所有提取结果合并去重，按分类分批并行生成最终 Markdown

## License

MIT
