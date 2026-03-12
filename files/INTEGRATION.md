# P2 集成指南

## 文件清单与放置位置

将以下文件复制到你现有项目的对应路径：

```
webinfo2md-p2/
├── src/webinfo2md/
│   ├── pipeline.py                  # ⚠️ 替换现有文件
│   ├── cli_p2_additions.py          # 📖 参考文档，需手动合并到 cli.py
│   ├── crawler/
│   │   ├── playwright_crawler.py    # ✅ 新文件
│   │   └── factory.py               # ⚠️ 替换现有文件
│   ├── llm/
│   │   └── concurrent.py            # ✅ 新文件
│   └── utils/
│       └── config.py                # ⚠️ 替换现有文件
└── tests/
    ├── test_concurrent.py           # ✅ 新文件
    ├── test_playwright.py           # ✅ 新文件
    └── test_factory.py              # ✅ 新文件
```

## 合并步骤

### 1. 新依赖（加到 pyproject.toml）

```toml
[project]
dependencies = [
    # 已有的...
    "pyyaml>=6.0",       # config.yaml 支持
]

[project.optional-dependencies]
browser = [
    "playwright>=1.40",  # Playwright 爬虫引擎
]
```

### 2. 合并 CLI 参数

打开 `cli_p2_additions.py`，把以下 5 个 click option 加到你的 `cli.py`：

- `--concurrency / -j` → max_concurrency
- `--force-playwright` → 跳过 httpx
- `--cookie-file` → Playwright cookie 注入
- `--scroll / --no-scroll` → 无限滚动
- `--screenshot` → 调试截图

然后用 `build_playwright_config()` 构建 Playwright 配置，
传入 `PipelineConfig.playwright_config`。

### 3. 确保 import 链路

在 `crawler/__init__.py` 加：
```python
from webinfo2md.crawler.factory import smart_fetch, CrawlResult
```

在 `llm/__init__.py` 加：
```python
from webinfo2md.llm.concurrent import ConcurrentExtractor, merge_extracted_questions
```

### 4. Pipeline 接口变化

新 `pipeline.py` 的 `PipelineConfig` 增加了三个字段：
- `max_concurrency: int = 3`
- `force_playwright: bool = False`
- `playwright_config: Optional[dict] = None`

确保你的 CLI 构建 `PipelineConfig` 时传入这些字段。

## 验证

```bash
# 编译检查
python3 -m compileall src tests

# CLI 帮助（合并后）
PYTHONPATH=src python3 -m webinfo2md --help

# Dry-run 测试
PYTHONPATH=src python3 -m webinfo2md \
  --url "https://example.com" \
  --dry-run

# 运行新测试
PYTHONPATH=src pytest tests/test_concurrent.py tests/test_playwright.py tests/test_factory.py -v
```

## 新增 CLI 用法示例

```bash
# 并发提取（5 路并发）
webinfo2md --url "https://..." --api-key sk-xxx -j 5

# 强制 Playwright + 无限滚动（适合牛客帖子）
webinfo2md --url "https://www.nowcoder.com/discuss/xxx" \
  --force-playwright --scroll \
  --api-key sk-xxx

# 带 Cookie 访问需要登录的页面
webinfo2md --url "https://..." \
  --cookie-file ~/.webinfo2md/cookies.json \
  --force-playwright \
  --api-key sk-xxx

# 调试：保存页面截图
webinfo2md --url "https://..." \
  --force-playwright \
  --screenshot debug.png \
  --dry-run
```
