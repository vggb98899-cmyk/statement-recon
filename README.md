# 多平台对账引擎

自动核对 Shopify、Amazon、TikTok Shop 三个平台的订单与 PingPong 支付流水，输出差异化归类报表，并支持飞书告警推送。

## 功能特性

| 特性 | 说明 |
|------|------|
| **多平台支持** | Shopify / Amazon / TikTok Shop，CSV 格式各异，自动字段归一化 |
| **多 SKU 去重** | 同一订单多行商品，Total 自动去重，避免重复计算 |
| **差异自动归类** | 按优先级判断：数据缺失 → 待查 → 手续费差异 → 匹配 |
| **差异子标签** | 区分"支付渠道手续费"、"平台佣金扣费"、"复合扣费" |
| **净额对账** | 差异 = (平台总额 - 平台手续费) - 支付到账，反映真实结算链路 |
| **自然语言报告** | 模板引擎生成可直接转发给老板的中文报告 |
| **飞书告警推送** | 数据缺失/待查时，自动推送到飞书群机器人 |
| **网页查看器** | 浏览器查看所有历史报告，支持展开全文和下载 Excel |

## 目录结构

```
statement-recon/
├── data/raw/            ← 原始 CSV 数据（各平台交易明细 + PingPong 流水）
├── output/              ← 输出结果（Excel 对账表 + 文本报告）
├── src/
│   ├── reconciler.py    ← 主流程编排（8步一键跑通）
│   ├── field_mapper.py  ← 字段归一化 + 多 SKU 去重
│   ├── matcher.py       ← 订单匹配 + 孤儿流水检测
│   ├── classifier.py    ← 差异归类 + 子标签
│   ├── reporter.py      ← Excel 输出（3个Sheet + 颜色标记）
│   ├── summarizer.py    ← 自然语言报告生成
│   ├── alerter.py       ← 飞书/钉钉告警推送
│   └── report_server.py ← 网页查看器
└── .git
```

## 快速开始

### 环境要求

- Python 3.11+
- pandas
- openpyxl（Excel输出）
- flask（网页查看器）

### 运行对账

```cmd
D:
cd D:\Reasonix\statement-recon
python src\reconciler.py
```

### 启动网页查看器

```cmd
python src\report_server.py
```

浏览器访问 `http://127.0.0.1:5000`

## 数据说明

项目使用模拟 CSV 数据，包含：

- `shopify_transactions.csv` — 3 笔订单（含 1 笔多 SKU）
- `amazon_transactions.csv` — 2 笔订单
- `tiktok_transactions.csv` — 2 笔订单
- `pingpong_settlements.csv` — 5 笔流水（含 1 笔孤儿订单）

模拟数据覆盖了多 SKU 去重、数据缺失、手续费差异、孤儿流水等典型对账场景。

## 项目迭代

| 版本 | 迭代内容 |
|------|---------|
| v1.0 | 基础对账引擎：字段归一化 → 匹配 → 归类 → Excel 输出 |
| v1.1 | 差异子标签 + 孤儿流水处理建议 + 底部汇总统计 |
| v1.2 | 精细化手续费计算：净额对账公式（扣除平台佣金后比对） |
| v1.3 | 阈值严格化：`<=` 改为 `<`，等于阈值也标记为待查 |
| v3.0 | Agent 自然语言报告 + 飞书告警推送 + Web 报告查看器 |

## 技术栈

- **Python 3.14** — 开发语言
- **Pandas** — 数据处理（CSV 读取、merge、groupby 聚合）
- **openpyxl** — Excel 输出（多 Sheet、颜色标记）
- **Flask** — 网页报告查看器
- **Git** — 版本管理，按功能点迭代
