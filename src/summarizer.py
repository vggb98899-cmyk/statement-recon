"""
summarizer.py — 对账结果自然语言报告生成

职责：
  把对账结果（数字+分类）翻译成一段财务主管可以直接转发给老板的话。
  不需要大模型，用模板 + 数据填充。

v3.0 需求：
  "Agent自己看完数据，给我一段'人话'报告"
"""

import pandas as pd


def _summarize_missing(df: pd.DataFrame) -> dict:
    """
    分析"数据缺失"订单：有几笔？涉及多少金额？集中在哪些平台？
    
    df 是 classify_all() 之后的完整对账结果 DataFrame。
    """
    missing = df[df["classification"].str.contains("数据缺失", na=False)]

    if missing.empty:
        return {"count": 0, "total_amount": 0.0, "platforms": []}

    count = len(missing)
    total_amount = round(missing["difference"].abs().sum(), 2)
    platforms = missing["platform"].unique().tolist()

    return {
        "count": count,
        "total_amount": total_amount,
        "platforms": platforms,
    }


def _summarize_pending(df: pd.DataFrame) -> dict:
    """
    分析"待查"订单：有几笔？最异常的那笔是什么情况？
    """
    pending = df[df["classification"].str.contains("待查", na=False)]

    if pending.empty:
        return {"count": 0, "top_order": None}

    count = len(pending)

    # 找差异绝对值最大的那笔
    top_idx = pending["difference"].abs().idxmax()
    top = pending.loc[top_idx]

    return {
        "count": count,
        "top_order": str(top.get("order_id", "")),
        "top_diff": round(top.get("difference", 0), 2),
        "top_platform": str(top.get("platform", "")),
        "top_total": round(top.get("total", 0), 2),
    }


def _build_conclusion(missing: dict, pending: dict, orphan_count: int) -> str:
    """
    生成"综合判断"——告诉财务主管最该干什么。
    
    判断逻辑：
      1. 有数据缺失 → 最紧急，建议当天处理
      2. 有孤儿流水 → 次紧急，建议联系支付渠道
      3. 有待查但没缺失 → 需要关注但不紧急
      4. 全部匹配 → 今日正常
    """
    if missing["count"] > 0:
        return (
            f"最紧急的是{missing['count']}笔数据缺失订单，"
            f"涉及{missing['total_amount']}元，建议今天内处理。"
        )
    elif orphan_count > 0:
        return "存在孤儿流水，建议联系支付渠道（PingPong）获取原始凭证。"
    elif pending["count"] > 0:
        return (
            f"存在{pending['count']}笔待查差异，需进一步核实，"
            "建议优先核查差异最大的订单。"
        )
    else:
        return "今日对账正常，无需人工干预。"


def _find_matched_orders(matched_df: pd.DataFrame) -> int:
    """
    找有多少笔"✅ 匹配"的订单。
    这个纯粹是让报告更好看——告诉用户"正常的有几笔"。
    """
    return len(matched_df[matched_df["classification"].str.contains("✅", na=False)])


def generate_report(matched_df: pd.DataFrame, orphan_df: pd.DataFrame) -> str:
    """
    生成自然语言对账报告。

    参数：
      matched_df — classify_all() 的输出（含 classification 列）
      orphan_df  — matcher.match_orders() 的孤儿流水

    返回：
      一段可以直接读给老板听的中文报告
    """
    # ---- 1. 统计数据 ----
    total = len(matched_df)
    matched_count = _find_matched_orders(matched_df)
    missing = _summarize_missing(matched_df)
    pending = _summarize_pending(matched_df)
    orphan_count = len(orphan_df)
    orphan_amount = round(orphan_df["Settlement Amount"].sum(), 2) if orphan_count > 0 else 0

    # 列出涉及的所有平台
    platforms = matched_df["platform"].unique()
    platform_str = "、".join(platforms)

    # ---- 2. 按模板组装报告 ----
    lines = []
    lines.append(f"本次共对账{total}笔订单，来自{platform_str}三个平台。其中：")
    lines.append("")

    # 数据缺失段落
    if missing["count"] > 0:
        platform_detail = "、".join(missing["platforms"])
        lines.append(
            f"- {missing['count']}笔数据缺失，涉及金额约{missing['total_amount']}元，"
            f"集中在{platform_detail}，建议优先联系支付渠道核实。"
        )
    else:
        lines.append("- 无数据缺失，所有订单均有支付记录。")

    # 待查段落
    if pending["count"] > 0:
        lines.append(
            f"- {pending['count']}笔待查，"
            f"其中{pending['top_order']}到账比预期多{abs(pending['top_diff'])}元"
            f"（{pending['top_platform']}，总额{pending['top_total']}元），"
            f"建议核对相关平台报表。"
        )
    else:
        lines.append("- 无待查差异。")

    # 孤儿流水段落
    if orphan_count > 0:
        lines.append(
            f"- {orphan_count}笔孤儿流水（{orphan_amount}元），"
            f"平台无此订单号，建议联系PingPong提供原始凭证。"
        )
    else:
        lines.append("- 无孤儿流水。")

    # ---- 3. 综合判断 ----
    lines.append("")
    conclusion = _build_conclusion(missing, pending, orphan_count)
    lines.append(f"综合判断：{conclusion}")

    # 如果有匹配订单，加一句快速总结
    if matched_count > 0:
        lines.append(f"（其中{matched_count}笔对账匹配正常，无需关注。）")

    return "\n".join(lines)
