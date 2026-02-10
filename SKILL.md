---
name: lets-go-rss
description: 轻量级全平台 RSS 订阅管理器。一键聚合 YouTube、Vimeo、Behance、B站、微博、抖音、小红书的内容更新，支持增量去重和 AI 智能分类。
---

# Let's Go RSS

全平台 RSS 内容聚合工具，支持增量更新、去重、AI 分类。

## 快速使用

### 添加订阅
```bash
python3 scripts/lets_go_rss.py --add "https://www.youtube.com/@MatthewEncina"
python3 scripts/lets_go_rss.py --add "https://vimeo.com/xkstudio"
python3 scripts/lets_go_rss.py --add "https://www.behance.net/yokohara6e48"
```

### 更新全部（耗时操作，建议用 crontab 后台跑）
```bash
python3 scripts/lets_go_rss.py --update --no-llm --digest
```

### 读取缓存报告（Bot 推送用，瞬间返回）
```bash
python3 scripts/lets_go_rss.py --status
```

### 查看订阅
```bash
python3 scripts/lets_go_rss.py --list
python3 scripts/lets_go_rss.py --stats
```

## Bot 推送最佳实践

**问题**：`--update` 需要 30-60 秒抓取全部订阅，Bot 定时任务可能超时。

**方案**：抓取和推送解耦——crontab 提前跑更新，Bot 只读缓存文件。

```bash
# crontab -e
# 每 2 小时的 55 分更新（提前 5 分钟准备好数据）
55 */2 * * * cd /path/to/lets-go-rss && python3 scripts/lets_go_rss.py --update --no-llm --digest

# Bot 在整点读缓存推送（瞬间完成）
# python3 scripts/lets_go_rss.py --status
```

Bot 只需调用 `--status`，该命令直接读取 `assets/latest_update.md` 并输出内容，无需网络请求、无需等待。

## 平台支持

| 平台 | 依赖 | 开箱即用 |
|------|------|:--------:|
| Vimeo | httpx | ✅ |
| Behance | httpx | ✅ |
| YouTube | yt-dlp | ✅ |
| 微博 | RSSHub | ⚠️ 需配置 |
| 抖音 | RSSHub | ⚠️ 需配置 |
| B站 | RSSHub | ⚠️ 需配置 |
| 小红书 | RSSHub | ⚠️ 实验性 |

## 安装依赖

```bash
# 基础（YouTube + Vimeo + Behance）
pip install httpx yt-dlp

# 可选：AI 分类
pip install anthropic
export ANTHROPIC_API_KEY="your-key"

# 可选：中国平台（需要 Docker）
docker run -d --name rsshub -p 1200:1200 diygod/rsshub:chromium-bundled
export RSSHUB_BASE_URL="http://localhost:1200"
```

## 输出格式

- `assets/latest_update.md` — Markdown 更新报告（`--status` 读取此文件）
- `assets/feed.xml` — 标准 RSS 2.0 XML
- `assets/summary.md` — 统计摘要
