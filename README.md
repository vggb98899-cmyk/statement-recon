# 多平台对账引擎

> **自动核对 Shopify、Amazon、TikTok Shop 三平台订单与 PingPong 支付流水，输出差异归类报表 + 自然语言报告 + 飞书告警。**
>
> 纯本地 CSV 模拟，零 API 依赖，面试可直接演示。

## 项目亮点

| 维度 | 内容 |
|------|------|
| **业务理解** | 模拟真实跨境电商对账场景，覆盖多 SKU 去重、净额比对、孤儿流水等真实业务痛点 |
| **工程习惯** | Git 按功能点迭代（v1.0 → v3.0），每轮交付独立可验证的功能 |
| **技术选型** | 模板引擎替代大模型生成报告（精确定位可追溯），Pandas 处理异构 CSV 数据 |
| **全链路闭环** | CSV 读取 → 字段映射 → 订单匹配 → 差异归类 → Excel/报告/告警三路输出 |

## 运行演示

```cmd
D:
cd D:\Reasonix\statement-recon
python src\reconciler.py
```

输出示例：

```
📂 第1步：读取平台数据...
  ✅ shopify: 3 笔订单, 4 行SKU明细
  ✅ amazon: 2 笔订单, 2 行SKU明细
  ✅ tiktok: 2 笔订单, 2 行SKU明细
...
📝 第7步：生成Agent报告...

本次共对账7笔订单，来自shopify、amazon、tiktok三个平台。其中：
- 3笔数据缺失，涉及金额约296.04元...
- 3笔待查，其中AMZ-9987-USA到账比预期多13.9元...
- 1笔孤儿流水（74.6元）...
综合判断：最紧急的是3笔数据缺失订单...建议今天内处理。

🔔 第8步：发送飞书告警...
  ✅ 告警已推送
```

## 架构设计

```
┌──────────────────────────────────────────────────────────┐
│                    src/reconciler.py                      │
│                      主流程编排                            │
├──────────┬──────────┬──────────┬──────────┬──────────────┤
│ Step 1-2 │ Step 3   │ Step 4   │ Step 5-6 │ Step 7-8     │
│ 读取CSV  │ 订单匹配 │ 差异归类 │ 输出报表 │ 报告+告警    │
├──────────┼──────────┼──────────┼──────────┼──────────────┤
│ field_   │ matcher  │ classifier│ reporter │ summarizer   │
│ mapper   │ .py      │ .py      │ .py      │ .py          │
│ .py      │          │          │          │ alerter.py   │
│          │          │          │          │ report_      │
│          │          │          │          │ server.py    │
└──────────┴──────────┴──────────┴──────────┴──────────────┘
         ▲          ▲           ▲          ▲
         │          │           │          │
       CSV数据   LEFT JOIN   if-elif    模板+Webhook
      归一化     匹配        优先级分类   推送
```

## 核心设计决策

### 字段归一化（field_mapper.py）

各平台 CSV 列名不同（`Total` / `total` / `Gross Amount`），通过映射字典统一为标准字段。后续模块只认标准字段，加新平台只需新增一段映射。

```python
SHOPIFY_COLUMN_MAP = {"Order": "order_id", "Total": "total", ...}
AMAZON_COLUMN_MAP = {"amazon-order-id": "order_id", "total": "total", ...}
TIKTOK_COLUMN_MAP = {"Order ID": "order_id", "Gross Amount": "total", ...}
```

### 多 SKU 去重

同一订单多行商品，`Total` 字段每行相同，直接匹配会把 100 元算成 200 元。按订单号去重：每个订单只取一条 Total 用于匹配，明细行保留供后续分析。

### 差异归类的优先级（classifier.py）

按业务严重程度自上而下判断，命中即停：

```python
if not has_settlement:     return "❌ 数据缺失"   # 最严重，优先报
if abs_diff > threshold:   return "❌ 待查"       # 大额异常
if abs_diff ≈ pingpong_fee: return "⚠️ 手续费差异" # 常规损耗
if abs_diff < threshold:   return "✅ 匹配"        # 正常
```

### 净额对账公式

```
差异 = (平台应收总额 - 平台手续费) - PingPong 实际到账净额
```

相比简单比对的 `总额 - 到账`，这个公式反映了真实结算链路——平台先扣佣金再结算给支付渠道。

### 自然语言报告（summarizer.py）

模板引擎 + 数据填充，零 API 成本。每一句结论都能追溯到具体数据行：

```python
f"- {count}笔数据缺失，涉及金额约{amount}元，集中在{platforms}..."
```

### 告警推送（alerter.py）

支持飞书/钉钉 Webhook，未配置时仅打印日志不报错。Webhook URL 通过环境变量读取，不硬编码。

## 快速开始

### 环境要求

- Python 3.11+
- pandas, openpyxl, flask

```bash
pip install pandas openpyxl flask
```

### 运行对账

```bash
python src/reconciler.py
```

### 查看历史报告

```bash
python src/report_server.py
# 浏览器访问 http://127.0.0.1:5000
```

### 配置飞书告警（可选）

```bash
# Windows
set FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/你的token

# 或创建 .env 文件（参考 .env.example）
python src/reconciler.py
```

## 项目目录

```
statement-recon/
├── data/raw/              ← 模拟 CSV 数据
│   ├── shopify_transactions.csv
│   ├── amazon_transactions.csv
│   ├── tiktok_transactions.csv
│   └── pingpong_settlements.csv
├── src/
│   ├── reconciler.py      ← 主流程（8步编排）
│   ├── field_mapper.py    ← 字段归一化 + 多SKU去重
│   ├── matcher.py         ← 订单匹配 + 孤儿流水检测
│   ├── classifier.py      ← 差异归类 + 子标签
│   ├── reporter.py        ← Excel输出（3Sheet + 颜色）
│   ├── summarizer.py      ← 自然语言报告
│   ├── alerter.py         ← 飞书/钉钉告警
│   └── report_server.py   ← Web 报告查看器
├── output/                ← 运行结果
├── .env.example           ← 环境变量模板
├── README.md
└── 面试准备.md
```

## 项目迭代

```
dceedf1 feat: v1.0 多平台对账引擎初始版本
bc19a79 feat: v1.1 差异子标签 + 孤儿流水建议 + 汇总统计
e5a3559 feat: v1.2 精细化手续费计算（净额对账公式）
5f5b7ca fix: 阈值逻辑 <= 改为 <（等于阈值也进待查）
c33beff feat: v3.0-1 Agent 自然语言报告
e800e81 feat: v3.0-2 飞书告警推送
30f0fa4 docs: 项目文档 + 网页查看器 + 环境变量配置
```

## 技术栈

| 技术 | 用途 |
|------|------|
| Python 3.14 | 开发语言 |
| Pandas | CSV 读取、merge、groupby 聚合 |
| openpyxl | Excel 多 Sheet 输出（颜色标记） |
| Flask | Web 报告查看器 |
| Git | 版本管理，按功能点迭代 |
