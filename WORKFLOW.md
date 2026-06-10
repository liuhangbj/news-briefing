# News Briefing Workflow

## 核心流程（4阶段）

```
① 脚本读取缓存 → ② 时间/URL/话题过滤 → ③ 关键词打分 → ④ 候选列表输出
  ↓
⑤ AI 逐条阅读（全部）→ ⑥ S/A/B/C 分级 → ⑦ 保留列表（50-150篇）
  ↓
⑧ 事件级别聚类 → ⑨ 热点话题筛选 → ⑩ 写综述（≤600字）→ ⑪ 推荐2-3篇
  ↓
⑫ 组装 Markdown → ⑬ 转 HTML → ⑭ 推送到 GitHub + Cubox + 飞书通知
```

## 阶段0：脚本自动化（news_briefing.py）

### 1. 读取缓存

- **输入**：`rss-curation/cache/freshrss_briefing.json`（FreshRSS 快讯缓存）
- **数据量**：通常 5000-8000 条（24h 滚动窗口）
- **时间范围**：昨天 8:00 ~ 今天 8:00（Asia/Shanghai）

### 2. 时间过滤

- **过滤后**：~900 条（24h 窗口）
- **过滤逻辑**：保留 `published` 在昨天 8:00 到今天 8:00 之间的条目

### 3. URL 去重

- **去重后**：~900 条（URL 完全相同的只保留一条）
- **去重键**：`url`

### 4. 话题去重

- **去重后**：~800 条（相似标题去重）
- **算法**：Jaccard 相似度，阈值 `SIMILARITY_THRESHOLD = 0.35`
- **去重键**：标题分词后的交集 ≥ 3 个关键词

### 5. 关键词打分

- **评分逻辑**：100 组关键词词组，命中一组加 1 分
- **用途**：仅用于排序，不做内容判断依据
- **已知问题**：分数拉不开差距（体育类泛滥、误命中）

### 6. 生成候选列表

- **输出**：`output/candidates_YYYYMMDD.md`（Markdown 格式）
- **内容**：全部文章按分数降序排列，附带命中词组详情
- **数据量**：~800 篇，约 250KB Markdown

---

## 阶段1：AI 筛选（人工逐条判断）

### 输入

`output/candidates_YYYYMMDD.md`（全部文章，逐条阅读）

### 操作要求

- **必须逐条阅读全部文章**，不能跳过、不能分批终止、不能因数量大而中途停止
- 每篇文章独立阅读：标题 + 摘要 + 来源 + 命中词组
- 禁止用批量脚本替代人工判断

### 判断维度

对每篇文章判断：
- **国内/国际**：是否涉及中国或中国机构/企业/政策？
- **板块**：政治、宏观、企业、社会（国内/国际）；基础科学、AI、其他（科技）；文化、体育、娱乐、生活方式（文体）
- **事件**：属于哪个具体事件？（如"非农就业报告""美伊冲突升级"）
- **评级**：S / A / B / C（按标准判断）

### 输出

- **保留列表**：S/A/B 直接入选，C 级二次筛选后部分保留
- **数据量**：通常 50-150 篇
- **记录文件**：`output/judgment_batch1.md`（第 1-50 篇）、`judgment_batch2.md`（第 51-100 篇）...

---

## 阶段2：AI 组织话题（写综述）

### 1. 事件级别聚类

从保留列表中提取事件：
- **事件定义**：有明确时间锚点（具体日期）+ 主体（谁）+ 结果（发生了什么）
- **分类 vs 事件**：“芯片行业”是分类，不是事件；“芯片暴跌（2026年6月）”是事件

### 2. 热点话题筛选

- **筛选标准**：文章数量 ≥ 3 且事件级别（有时间锚点）
- **优先原则**：S 级密集 > 有核心数据 > 有明确市场/政策影响
- **输出**：3-8 个热点话题

### 3. 撰写综述（每话题 ≤600字）

- **结构**：首段（事件概述）+ 中段（关键数据）+ 尾段（影响判断）
- **数据来源**：缓存中的 desc（中文源完整）+ 标题推断
- **标注限制**：如果 Bloomberg/Reuters 被 Cloudflare 拦截，标注“部分来源全文受限，基于中文源完整描述 + 标题推断”

### 4. 推荐必读文章（每话题 2-3 篇）

- **格式**：`[**标题**](URL)（来源）`
- **要求**：必须嵌入完整 URL，附带核心数据/关键信息摘要

### 5. 非热点文章分类罗列

- **分类体系**：国内（政治/宏观/企业/社会）、国际（政治/宏观/企业/社会）、科技（基础科学/AI/其他）、文体（文化/体育/娱乐/生活方式）
- **格式**：`[来源] 标题（超链接）`
- **空板块**：完全省略（无内容的板块不保留标题）

### 输出

- **文件**：`output/briefing_YYYYMMDD.md`（Markdown 格式）
- **内容**：热点话题综述 + 非热点分类罗列

---

## 阶段3：生成最终简报（脚本 + 推送）

### 1. 转 HTML

- **输入**：`briefing_YYYYMMDD.md`
- **输出**：`output/news_briefing_YYYYMMDD.html`
- **格式**：Cubox 可解析的 HTML，含标题、时间、导语、话题块、数据卡、来源脚注

### 2. 推送到 GitHub

- **API**：`https://api.github.com/repos/liuhangbj/news-briefing/contents/`
- **文件**：`news_briefing_YYYYMMDD.html`
- **URL**：`https://liuhangbj.github.io/news-briefing/news_briefing_YYYYMMDD.html`
- **认证**：`GITHUB_TOKEN`（从 `.env` 读取）

### 3. 更新索引页

- **函数**：`update_index_page()`（在 `news_briefing.py` 中）
- **逻辑**：读取仓库所有文件 → 提取 `news_briefing_YYYYMMDD.html` → 按日期倒序 → 只列出实际存在的文件 → 上传覆盖 `index.html`
- **URL**：`https://liuhangbj.github.io/news-briefing/`

### 4. 推送到 Cubox

- **API**：`CUBOX_API_URL`（从 `.env` 读取）
- **内容**：GitHub Pages URL
- **文件夹**：`0 - 每日新闻简报`
- **标签**：`['news', 'briefing']`

### 5. 飞书通知（可选）

- **脚本**：`scripts/news_briefing_feedback.py`
- **功能**：从日志读取最后运行状态 → 生成汇报文本 → 飞书消息通知
- **认证**：`FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_USER_ID`（从 `.env` 读取）

---

## 数据流总图

```
FreshRSS 快讯缓存
  │
  ▼
rss-curation/cache/freshrss_briefing.json (~5000-8000条)
  │
  ▼
news_briefing.py 阶段0
  ├── 时间过滤 → ~900条
  ├── URL去重 → ~900条
  ├── 话题去重 → ~800条
  └── 关键词打分（排序用）
  │
  ▼
output/candidates_YYYYMMDD.md (~800篇, 250KB)
  │
  ▼
AI 阶段1（人工逐条判断）
  ├── 逐条阅读全部 ~800篇
  ├── S/A/B/C 分级
  └── 保留 ~50-150篇
  │
  ▼
AI 阶段2（组织话题）
  ├── 事件级别聚类 → 3-8个热点话题
  ├── 写综述（每话题≤600字）
  ├── 推荐2-3篇必读（含URL）
  └── 非热点文章分类罗列
  │
  ▼
output/briefing_YYYYMMDD.md
  │
  ▼
news_briefing.py 阶段3
  ├── 转 HTML → output/news_briefing_YYYYMMDD.html
  ├── 推送到 GitHub Pages
  ├── 更新索引页 index.html
  ├── 推送到 Cubox
  └── 飞书通知（可选）
```

---

## 文件位置

```
projects/news-briefing/
├── scripts/
│   ├── news_briefing.py            # 主脚本：阶段0 + 阶段3（读取 → 过滤 → 打分 → 候选列表 → 推送）
│   ├── news_briefing_feedback.py   # 飞书通知脚本
│   └── file-guard.sh               # 文件监控辅助
├── config/
│   └── keyword_groups.json         # 100组关键词词组（仅用于排序）
├── output/
│   ├── candidates_YYYYMMDD.md      # 候选列表（阶段0输出）
│   ├── judgment_batch*.md          # AI判断记录（阶段1中间文件）
│   ├── briefing_YYYYMMDD.md        # 最终简报 Markdown（阶段2输出）
│   └── news_briefing_YYYYMMDD.html # 最终简报 HTML（阶段3输出）
├── .env                            # 密钥配置（GITHUB_TOKEN / CUBOX_API_URL / FEISHU_*）
├── README.md                       # 项目概述
├── 简报生成指南.md                 # AI操作手册：分级标准、九步流程、模板、常见错误
└── WORKFLOW.md                     # 本文档：数据流向与流程说明
```

---

## 配置

环境变量（`.env`）：
- `GITHUB_TOKEN` — GitHub 推送（格式 `ghp_` 或 `gho_`）
- `CUBOX_API_URL` — Cubox 推送
- `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_USER_ID` — 飞书通知
- `KIMI_API_KEY` / `DEEPSEEK_API_KEY` — 预留（当前未使用）

---

## 常见排查

### 候选列表为空或过少
1. 检查 `rss-curation/cache/freshrss_briefing.json` 是否存在、时间范围是否覆盖
2. 检查 `news_briefing.py` 中的时间窗口逻辑（昨天 8:00 ~ 今天 8:00）
3. 检查 FreshRSS 缓存是否被 `rss-curation` 正确更新

### 简报推送失败
1. 检查 `.env` 中 `GITHUB_TOKEN` 是否存在（文件路径：`projects/news-briefing/.env`）
2. 检查 GitHub API 返回码（401=token 无效，404=仓库不存在，422=sha 不匹配）
3. 检查 `news_briefing.py` 日志中的 `push_to_github` 输出

### Cubox 推送失败
1. 检查 `.env` 中 `CUBOX_API_URL` 是否配置
2. 检查 Cubox API 返回的 `code` 和 `status`
3. 检查网络连通性（curl 测试 `cubox.pro`）

### 索引页未更新
1. 检查 `update_index_page()` 是否在 `news_briefing.py` 中存在（之前曾被误删）
2. 检查 GitHub API 是否有权限修改 `index.html`
3. 检查仓库中是否有 `news_briefing_YYYYMMDD.html` 文件（索引页只列出实际存在的文件）

### 关键词打分问题
1. 体育类泛滥：检查 `keyword_groups.json` 中是否过度匹配体育关键词
2. 误命中：如 "naval" 匹配 "nm"（芯片纳米）→ 检查关键词是否有前缀/后缀保护
3. 分数拉不开：当前所有词组 bonus=1，没有权重区分 → 待优化

---

## 监控查询

```bash
# 查看候选列表文件大小（判断数据量是否正常）
ls -lh ~/projects/news-briefing/output/candidates_*.md

# 查看简报 HTML 文件大小
ls -lh ~/projects/news-briefing/output/news_briefing_*.html

# 查看 .env 配置（确认密钥存在）
cat ~/projects/news-briefing/.env

# 查看新闻简报脚本日志（检查推送状态）
grep -i "github\|cubox\|index" ~/.kimi_openclaw/workspace/logs/news_briefing.log

# 手动验证 GitHub 推送（token 检查）
curl -s -H "Authorization: token $(grep GITHUB_TOKEN ~/projects/news-briefing/.env | cut -d= -f2)" \
  "https://api.github.com/repos/liuhangbj/news-briefing/contents/" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print([f['name'] for f in d])"
```

---

## 快速命令

```bash
# 手动执行阶段0（生成候选列表）
cd ~/projects/news-briefing
python3 scripts/news_briefing.py

# 手动执行阶段3（生成简报并推送，需先完成阶段1+2）
# 在 Python 交互中调用：
# from scripts.news_briefing import save_final_briefing
# save_final_briefing('20260606', '...markdown内容...')

# 检查 GitHub 仓库文件列表
curl -s "https://api.github.com/repos/liuhangbj/news-briefing/contents/" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print('\n'.join([f['name'] for f in d]))"

# 检查索引页内容
curl -s "https://raw.githubusercontent.com/liuhangbj/news-briefing/main/index.html"
```

---

## 版本

- v4.2：候选列表模式（脚本只出列表，AI 人工筛选）
- 分类功能已删除（category 固定为 `未分类`）
- 死代码已清理（fetch_rss、parse_rss、fetch_hotnews、translate_and_summarize、llm_score_articles 等）
- `update_index_page()` 已恢复（2026-06-06）

---

*2026-06-06 · 数据流向与流程说明*
