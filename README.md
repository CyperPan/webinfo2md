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
- 反检测与 stealth 模式：集成 playwright-stealth，应对反爬机制
- 登录墙检测：自动识别需要登录的页面，给出明确提示
- 持久化浏览器登录：首次手动扫码登录后自动保持会话状态

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
  wait_timeout_ms: 30000
  # cookie_file: ~/.webinfo2md/cookies.json
  # screenshot_path: ./debug.png
  # user_data_dir: ~/.webinfo2md/browser_profile
  # intercept_api: false
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

**需要登录的网站（一亩三分地、小红书等）：**

```bash
# 首次运行：打开浏览器窗口，手动扫码或输入账号登录
webinfo2md \
  --url "https://www.xiaohongshu.com/search_result?keyword=ai+infra面经" \
  --user-data-dir ./browser_profile \
  --no-headless \
  --force-playwright \
  --provider openai \
  --dry-run

# 后续运行：自动复用保存的登录状态（可用 headless 模式）
webinfo2md \
  --url "https://www.xiaohongshu.com/search_result?keyword=ai+infra面经" \
  --user-data-dir ./browser_profile \
  --force-playwright \
  --scroll \
  --provider openai \
  --prompt "提取AI Infra相关的面试问题和面经"
```

**论坛深度爬取（一亩三分地面经版）：**

```bash
webinfo2md \
  --url "https://www.1point3acres.com/bbs/forum-145-1.html" \
  --depth 1 \
  --pages 10 \
  --provider openai \
  --prompt "提取所有AI Infra、ML Infra相关的面试问题和面经信息"
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
| `--user-data-dir` | 持久化浏览器目录（保存登录状态） | - |
| `--no-headless` | 显示浏览器窗口（用于手动登录） | `false` |
| `--intercept-api` | 拦截 API 响应获取结构化数据 | `false` |
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

## 网站兼容性测试

以下是在主流中文内容平台上的测试结果（2026-03-14）：

### 一亩三分地 (1point3acres.com)

| 测试项 | 结果 |
|--------|------|
| 论坛分区页 (gid=38) | ✅ 无需登录，可正常爬取 |
| 面经子版块 (forum-145) | ✅ 无需登录，可获取帖子标题和元信息 |
| 帖子详情页 | ⚠️ 部分内容可见（标题、公司、岗位、面试类型），正文需积分/登录 |
| 搜索功能 | ❌ 需要登录 |
| 深度爬取 (depth=1) | ✅ 可跟踪链接进入子页面 |

**测试命令：**

```bash
# 预览模式 — 检查爬取效果
webinfo2md \
  --url "https://www.1point3acres.com/bbs/forum-145-1.html" \
  --depth 1 --pages 5 \
  --provider openai --dry-run
# 结果：5 pages, 24 chunks, 18005 tokens

# 完整运行 — 生成面经整理文档
webinfo2md \
  --url "https://www.1point3acres.com/bbs/forum-145-1.html" \
  --depth 1 --pages 10 \
  --provider openai \
  --prompt "提取所有AI Infra、ML Infra、分布式系统相关的面试问题和面经信息" \
  --output output/1p3a-ai-infra-mianjing.md
# 结果：22 chunks, 7 questions extracted, 结构化 Markdown 输出
```

**建议**：使用 `--user-data-dir --no-headless` 登录后可获取完整帖子内容，显著提升提取质量。

### 小红书 (xiaohongshu.com)

| 测试项 | 结果 |
|--------|------|
| 搜索页面 | ❌ 需要登录（显示占位骨架） |
| 探索页面 | ❌ 反爬限制（IP 风险检测） |
| 笔记详情页 | ❌ 需要登录 |
| Stealth 模式 | ✅ 可绕过 IP 风险检测 |
| 登录墙检测 | ✅ 自动识别并给出明确提示 |

**小红书使用方式（需要登录）：**

```bash
# 步骤 1：首次运行，打开浏览器手动登录（扫码或手机号）
webinfo2md \
  --url "https://www.xiaohongshu.com/search_result?keyword=ai+infra面经" \
  --user-data-dir ./xhs_profile \
  --no-headless \
  --force-playwright \
  --provider openai --dry-run

# 检测到登录墙后，工具会自动等待你在浏览器中完成登录
# 登录成功后会自动继续爬取

# 步骤 2：后续运行，复用登录态
webinfo2md \
  --url "https://www.xiaohongshu.com/search_result?keyword=ai+infra面经" \
  --user-data-dir ./xhs_profile \
  --force-playwright \
  --scroll \
  --provider openai \
  --prompt "提取AI Infra相关的面试问题和经验分享"
```

### 需要登录的网站通用方案

| 方案 | 适用场景 | 使用方式 |
|------|----------|----------|
| **持久化浏览器** | 扫码登录的网站（小红书、微信等） | `--user-data-dir ./profile --no-headless` |
| **Cookie 文件** | 可从浏览器导出 Cookie 的网站 | `--cookie-file cookies.json` |
| **API 拦截** | SPA 应用，内容通过 API 加载 | `--intercept-api` |

**Cookie 文件格式**（从浏览器 DevTools 导出）：

```json
[
  {
    "name": "session_id",
    "value": "xxx",
    "domain": ".example.com",
    "path": "/"
  }
]
```

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
