"""
classifier.py — 差异自动归类模块

职责：
  对 matched_df 中每一行的差异金额，按优先级自动归类。

归类优先级（命中即停）：
  1. ❌ 数据缺失  — 平台有单、支付侧无记录（最严重）
  2. ❌ 待查      — 差异 > 阈值（2元）且两边都有单
  3. ⚠️ 手续费差异 — 差异 ≈ PingPong Fee ± 0.01
  4. ✅ 匹配      — 差异 ≤ 阈值且无以上情况

为什么按这个顺序？
  - "数据缺失"是系统性问题（钱可能根本没到），必须最优先报
  - "待查"是大额差异，需要人工介入
  - "手续费差异"是常规业务损耗，标记即可不需要人工处理
  - 汇率差异 v1.0 暂不单独分，归入"待查"
"""

import pandas as pd

# 默认差异阈值（元）
DEFAULT_THRESHOLD = 2.0

# 手续费匹配容差（元）——判断"差异 ≈ 支付手续费"时的精度
FEE_TOLERANCE = 0.01
# 子标签容差（元）——v1.1 放宽到 ±0.02
SUBTAG_TOLERANCE = 0.02


def classify_row(
    has_settlement: bool,
    difference: float,
    pingpong_fee: float,
    threshold: float = DEFAULT_THRESHOLD,
) -> str:
    """
    对一笔订单的差异进行分类。

    优先级判断逻辑（从上到下，命中即停）：
      1. 没有支付记录 → ❌ 数据缺失
      2. 差异 > 阈值  → ❌ 待查（大额异常，需要人工）
      3. 差异 ≈ PingPong Fee → ⚠️ 手续费差异（常规损耗）
      4. 其他         → ✅ 匹配

    参数：
      has_settlement — 是否有支付记录（bool）
      difference     — 差异金额（平台总额 - 支付到账）
      pingpong_fee   — 支付渠道手续费
      threshold      — 差异阈值（默认2元）

    返回：
      分类标签字符串
    """
    # 优先级1：数据缺失（最严重）
    if not has_settlement:
        return "❌ 数据缺失"

    abs_diff = abs(difference)

    # 优先级2：大额差异，需人工核查
    if abs_diff > threshold:
        return "❌ 待查"

    # 优先级3：差异是否 ≈ 支付渠道手续费
    # 含手续费时，expected 到账 = 总额 - 手续费，差异应该接近手续费
    if pingpong_fee > 0 and abs(abs_diff - pingpong_fee) <= FEE_TOLERANCE:
        return "⚠️ 手续费差异"

    # 优先级4：匹配成功（严格小于阈值才算匹配，等于阈值也进待查）
    if abs_diff < threshold:
        return "✅ 匹配"

    # 保底（理论上不会走到这里）
    return "❌ 待查"


def classify_subtag(
    classification: str,
    difference: float,
    pingpong_fee: float,
    platform_fee: float,
) -> str:
    """
    判断差异的子标签——扣费到底来自哪一方。

    规则：
      - 只有主标签为"⚠️ 手续费差异"时才需要判断子标签
      - 差异 ≈ PingPong Fee ± 0.02 → "支付渠道手续费"
      - 差异 ≈ 平台手续费 ± 0.02 → "平台佣金扣费"
      - 差异同时≈两者之和 → "复合扣费"（两边都收了钱）

    参数：
      classification — 主标签（classify_row 的结果）
      difference     — 差异金额
      pingpong_fee   — PingPong 手续费
      platform_fee   — 平台手续费（Shopify Transaction Fee / TikTok Platform Fee）

    返回：
      子标签字符串，非手续费差异时返回空字符串 ""
    """
    # 只有手续费类型才需要子标签
    if "手续费" not in classification:
        return ""

    abs_diff = abs(difference)
    pp_match = pingpong_fee > 0 and abs(abs_diff - pingpong_fee) <= SUBTAG_TOLERANCE
    pf_match = platform_fee > 0 and abs(abs_diff - platform_fee) <= SUBTAG_TOLERANCE

    if pp_match and pf_match:
        return "复合扣费"
    elif pp_match:
        return "支付渠道手续费"
    elif pf_match:
        return "平台佣金扣费"
    else:
        # 属于手续费差异但匹配不上已知费率 → 还是标记为支付渠道手续费
        return "支付渠道手续费"


def classify_all(matched_df: pd.DataFrame, threshold: float = DEFAULT_THRESHOLD) -> pd.DataFrame:
    """
    批量归类 matched_df 中所有行。

    参数：
      matched_df — matcher.match_orders() 的输出
      threshold  — 差异阈值

    返回：
      新增 classification 列的同结构 DataFrame
    """
    df = matched_df.copy()

    df["classification"] = df.apply(
        lambda row: classify_row(
            has_settlement=row["has_settlement"],
            difference=row["difference"],
            pingpong_fee=row.get("Fee", 0.0) or 0.0,
            threshold=threshold,
        ),
        axis=1,
    )

    # v1.1: 增加子标签列
    df["subtag"] = df.apply(
        lambda row: classify_subtag(
            classification=row["classification"],
            difference=row["difference"],
            pingpong_fee=row.get("Fee", 0.0) or 0.0,
            platform_fee=row.get("platform_fee", 0.0) or 0.0,
        ),
        axis=1,
    )

    return df


def get_anomalies(df: pd.DataFrame, threshold: float = DEFAULT_THRESHOLD) -> pd.DataFrame:
    """
    提取异常清单：差异 > 阈值的所有记录。

    你要求的"标红并汇总到异常清单"。
    注意：异常清单应该包含"差异金额 > 阈值"的记录，
    即使归类为"数据缺失"的也包含（数据缺失本质上差异 = 总额 - 0 = 总额，肯定 > 阈值）。

    参数：
      df — classify_all() 的输出
    返回：
      异常记录 DataFrame
    """
    anomalies = df[abs(df["difference"]) > threshold].copy()

    # 按差异金额降序排列（最大的异常排最前面）
    anomalies = anomalies.sort_values("difference", key=abs, ascending=False)

    return anomalies
