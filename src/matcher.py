"""
matcher.py — 订单匹配模块

职责：
  1. 加载 PingPong 支付流水（CSV）
  2. 左连接：平台订单 ← PingPong 流水
  3. 计算差异金额
  4. 找出"孤儿流水"（支付侧有但平台侧找不到）

数据流：
  platform_orders (来自 field_mapper) → 按 order_id 左连接 PingPong
  PingPong 流水                            → 反查平台，找不到的进"孤儿"
"""

import pandas as pd


def load_pingpong(filepath: str) -> pd.DataFrame:
    """
    加载 PingPong 资金流水 CSV，并做基础清洗。

    关键字段映射：
      Related Order ID → order_id（匹配键）
      Settlement Amount → 实际到账净额
      Fee → 支付渠道手续费

    参数：
      filepath — pingpong_settlements.csv 路径
    返回：
      清洗后的 DataFrame
    """
    df = pd.read_csv(filepath)

    # 重命名匹配键，与平台数据统一
    df = df.rename(columns={"Related Order ID": "order_id"})

    # 确保数值列为浮点数
    numeric_cols = ["Income", "Outlay", "Fee", "Exchange Rate", "Settlement Amount"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    return df


def match_orders(
    platform_orders: pd.DataFrame,
    pingpong_df: pd.DataFrame,
    threshold: float = 2.0,
) -> tuple:
    """
    核心匹配函数。

    逻辑：
      LEFT JOIN：platform_orders（左表）← pingpong_df（右表）
      - 平台有单 + 支付侧有记录 → 正常匹配，计算差异
      - 平台有单 + 支付侧无记录 → has_settlement = False（后续classifier标"数据缺失"）
    
    同时找出"孤儿流水"：
      支付侧有记录 + 平台侧找不到 → 另存为孤儿清单

    参数：
      platform_orders — field_mapper 输出的订单级 DataFrame
      pingpong_df    — load_pingpong 加载的支付流水
      threshold      — 差异阈值（默认2元）

    返回：
      (matched_df, orphan_df)
        matched_df — 合并后的对账结果（每平台订单一行）
        orphan_df  — 支付侧孤儿流水清单
    """
    # ---- 1. 左连接 ----
    merged = platform_orders.merge(
        pingpong_df,
        on="order_id",
        how="left",
        suffixes=("_platform", "_pingpong"),
    )

    # ---- 2. 标记是否有支付记录 ----
    merged["has_settlement"] = merged["Settlement Amount"].notna()

    # ---- 3. 计算差异金额 ----
    # v1.2 精细化公式：
    #   预期净到账 = 平台应收总额 - 平台手续费（平台扣完佣金后该给PingPong结算的金额）
    #   差异 = 预期净到账 - PingPong 实际到账净额
    merged["expected_net"] = merged["total"] - merged["platform_fee"].fillna(0.0)
    merged["difference"] = merged["expected_net"] - merged["Settlement Amount"].fillna(0.0)

    # 保留关键字段用于下游
    keep_cols = [
        "order_id", "platform", "total", "platform_fee",
        "expected_net", "Settlement Amount", "Fee", "Exchange Rate",
        "Transaction ID", "has_settlement", "difference",
    ]
    present_cols = [c for c in keep_cols if c in merged.columns]
    matched = merged[present_cols].copy()

    # ---- 4. 找出孤儿流水 ----
    # 用 PingPong 的 order_id 反查 platform_orders
    orphan = pingpong_df.merge(
        platform_orders[["order_id"]],
        on="order_id",
        how="left",
        indicator=True,  # 添加 _merge 列标记匹配结果
    )
    orphan = orphan[orphan["_merge"] == "left_only"].drop(columns=["_merge"])

    return matched, orphan
