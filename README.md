# 东方财富实盘选手爬虫

爬取东方财富实盘组合榜单数据，包括选手信息、持仓明细和历史调仓记录。

## 功能特性

- **异步并发爬取** - 使用 asyncio + Playwright，单选手内三类数据真正并行
- **浏览器连接池** - 浏览器实例复用，避免频繁创建/销毁开销
- **SQLite 高效存储** - 支持 SQL 查询分析，批量写入优化
- **断点续传** - Ctrl+C 中断后可继续，自动保存检查点
- **代理池支持** - 可配置代理避免被封

## 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖：
- `requests` - HTTP 请求
- `playwright` - 动态页面渲染
- `beautifulsoup4` - HTML 解析
- `aiohttp` - 异步 HTTP

安装 Playwright 浏览器：
```bash
playwright install chromium
```

## 快速开始

```bash
# 默认爬取（每榜单 500 名，并发 20）
python main.py

# 测试模式（只处理 10 个选手）
python main.py --test

# 指定每榜单 100 名，并发 30
python main.py --limit 100 --workers 30
```

## 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--limit` | 500 | 每榜单爬取数量 |
| `--workers` | 20 | 并发数 |
| `--test` | false | 测试模式，只处理 10 个选手 |
| `--no-skip` | false | 不跳过已存在的选手数据 |
| `--checkpoint-reset` | false | 重置检查点 |
| `--analyze` | false | 运行持仓分析 |

## 数据存储

数据存储在 `data/crawl_data.db`（SQLite）：

```sql
-- 选手表
players (
    zh_id TEXT PRIMARY KEY,
    name, followers, total_return, daily_return,
    net_value, max_drawdown, win_rate, days, concept, ...
)

-- 持仓表
positions (
    zh_id, stock_code, stock_name,
    cost_price, current_price, profit_ratio, position_ratio
)

-- 调仓表
trades (
    zh_id, stock_code, stock_name, trade_date,
    direction, position_change, ...
)
```

## 持仓分析

```bash
# 分析最新数据
python main.py --analyze
```

分析报告包含：
- **持仓最多的股票 Top 20** - 被多少选手持有、平均仓位、平均盈利
- **选手仓位分布** - 空仓、3成以下、3-5成、5-7成、7-9成、9成以上
- **股票盈亏分布** - 按盈利区间分类
- **当日盈利最高的选手 Top 10**

## 使用代理池

在 `proxies.txt` 中添加代理：

```txt
# proxies.txt
http://127.0.0.1:7890
http://user:password@192.168.1.1:8080
```

启用代理池：
```bash
export USE_PROXY_POOL=true
python main.py
```

## 项目结构

```
dfcfshipan/
├── main.py                      # 入口文件
├── requirements.txt             # 依赖列表
├── proxies.txt                  # 代理列表（可选）
├── data/
│   ├── checkpoint.json         # 爬取检查点
│   └── crawl_data.db           # SQLite 数据库
└── src/
    ├── config.py              # 配置（URL、路径等）
    ├── spiders/              # 爬虫模块
    │   ├── base.py           # 异步基础爬虫类
    │   ├── player_list.py    # 选手列表爬虫（API）
    │   ├── player_detail.py   # 选手详情爬虫
    │   ├── position.py        # 持仓数据爬虫
    │   └── trade.py          # 调仓记录爬虫
    ├── storage/              # 存储模块
    │   ├── interface.py      # 存储接口抽象
    │   ├── sqlite_storage.py  # SQLite 存储实现
    │   └── storage_factory.py # 存储工厂
    ├── analysis/              # 分析模块
    │   └── position_analyzer.py  # 持仓分析器
    └── utils/                 # 工具模块
        ├── logger.py           # 日志配置
        ├── proxy_pool.py      # 代理池管理
        └── async_playwright_pool.py  # 异步 Playwright 连接池
```

## 技术架构

### 异步爬取流程

```
1. 获取选手列表 (API)
       ↓
2. 创建 AsyncPlaywrightPool (复用浏览器)
       ↓
3. 对每个选手：
   ┌─────────────────────────────────────┐
   │  asyncio.gather() 并行执行:          │
   │    - fetch_player_detail (详情)       │
   │    - fetch_positions (持仓)          │
   │    - fetch_trades (调仓)            │
   └─────────────────────────────────────┘
       ↓
4. 批量存入 SQLite (每 50 个选手)
       ↓
5. 每 50 个选手保存检查点
```

### 浏览器连接池

- 单个 Playwright + Browser 实例启动一次
- 多个 BrowserContext 组成连接池
- 使用 Semaphore 控制并发，无需额外锁

### 断点续传

```
1. 启动爬虫，加载 checkpoint.json
2. 跳过 completed_ids 中的选手
3. Ctrl+C 中断 → 自动保存检查点 + 批量数据
4. 重新启动 → 从断点继续
```

## 注意事项

1. **并发数建议 10-20**，过高可能被网站限流
2. **自动重试机制**，失败自动重试 3 次
3. **调仓记录需要滚动加载**，爬取较慢
4. **建议使用代理池**避免被封

## 榜单 API 映射

| 榜单标签 | rankType | rateTitle |
|----------|----------|-----------|
| 总榜 | 10004 | 总收益 |
| 年榜 | 10003 | 250日收益 |
| 月榜 | 10001 | 20日收益 |
| 周榜 | 10000 | 5日收益 |
| 日榜 | 10005 | 日收益 |