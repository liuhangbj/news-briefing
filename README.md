# News Briefing

> 半自动化新闻简报生成系统。脚本负责技术流程，AI 负责内容理解。
>
> 详细分级标准、操作流程、常见错误清单见《简报生成指南》。

## 数据流

```
FreshRSS → rss-curation/cache/freshrss_briefing.json
         → news-briefing/scripts/news_briefing.py (读取 → 过滤 → 打分 → 候选列表)
         → AI 逐条筛选 → 组织话题 → 写综述 → 最终简报
```

## 脚本职责（自动化）

1. **读取缓存** — 从 `rss-curation/cache/freshrss_briefing.json` 读取
2. **时间过滤** — 保留昨天 8:00 到今天 8:00（Asia/Shanghai）
3. **URL 去重** — 去除重复链接
4. **话题去重** — 相似标题去重（Jaccard 0.45）
5. **关键词打分** — 命中词组加分，**仅用于排序，不做内容判断**
6. **生成候选列表** — Markdown 格式，含命中词组详情

## 简报生成流程（四阶段）

| 阶段 | 执行者 | 输入 | 输出 | 说明 |
|------|--------|------|------|------|
| **0** 脚本自动化 | 脚本 | 缓存 JSON | 候选列表 Markdown | 技术流程，不做内容判断 |
| **1** AI 筛选 | AI | 候选列表（700-800 篇） | 保留列表（50-150 篇） | **逐条阅读全部文章**，按 S/A/B/C 分级 |
| **2** AI 组织话题 | AI | 保留列表 | 话题结构（3-8 个） | 事件级别聚类，写综述（≤600 字） |
| **3** 生成简报 | 脚本 | 话题结构 + 保留列表 | HTML + 自动推送 | GitHub Pages + Cubox + 飞书通知 |

**详细操作标准**（S/A/B/C 分级、九步流程、输出模板、常见错误）→ 见《简报生成指南》。

## 关键文件

| 文件 | 说明 |
|------|------|
| `scripts/news_briefing.py` | 主脚本：读取缓存、过滤、打分、生成候选列表、推送 |
| `scripts/news_briefing_feedback.py` | 反馈脚本：飞书通知（密钥从 `.env` 读取） |
| `scripts/file-guard.sh` | 文件监控辅助脚本 |
| `config/keyword_groups.json` | 100 组关键词词组（required 已合并入 keywords） |
| `简报生成指南.md` | **AI 操作手册**：分级标准、九步流程、模板、常见错误 |
| `output/candidates_YYYYMMDD.md` | 候选列表输出 |
| `output/news_briefing_YYYYMMDD.html` | 最终简报输出（需人工筛选后生成） |

## 配置

环境变量（`.env`）：
- `KIMI_API_KEY` / `DEEPSEEK_API_KEY` — LLM API
- `CUBOX_API_URL` — Cubox 推送
- `GITHUB_TOKEN` — GitHub 推送
- `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_USER_ID` — 飞书通知

## 已知问题

- 关键词打分实用性不高，分数拉不开差距（体育类泛滥、误命中）
- 来源质量权重未启用（Bloomberg/FT/Reuters 等）
- 话题级去重阈值（交集 ≥ 3 个关键词）可能过于严格

## 待办

- [x] `.env` 配置已就位（GITHUB_TOKEN / CUBOX_API_URL）
- [x] `update_index_page()` 已恢复，推送后自动更新索引
- [x] 最终简报生成流程（人工筛选 → AI 组织话题 → 自动推送）已跑通
- [x] 指南结构优化：已移到项目根目录，README 精简，格式规范已写进模板
- [x] 格式规范已写进《简报生成指南》模板（6项：来源栏、数据栏、信息限制、综述标题、相关阅读书名号、其他快读前缀、空板块、底部精简）
- [x] WORKFLOW.md 已生成：核心流程（4阶段）、数据流总图、文件位置、配置、常见排查、监控查询、快速命令
- [ ] 修复正则误删：相关阅读/其他新闻标题丢失（`[****](URL)`）
- [ ] 补读漏读文章：今日只读 190 篇，漏掉 656 篇，需补读并更新简报
- [ ] 自动更新关键词机制（A/B/C/D 方案待选）
- [ ] 评估是否需要同时读取 `深度` 和 `行业` 缓存
- [ ] 确认 `rss-curation/scripts/score.py` 是否需要调整

## 版本

- v4.2：候选列表模式（脚本只出列表，AI 人工筛选）
- 分类功能已删除（category 固定为 `未分类`）
- 死代码已清理（fetch_rss、parse_rss、fetch_hotnews、translate_and_summarize、llm_score_articles 等）

---

*2026-06-06 · 项目持续迭代中*
