"""
reconciler.py — 对账引擎主流程

职责：
  串联 field_mapper → matcher → classifier → reporter，
  完成从原始CSV到最终报告的完整对账流程。

用法：
  python src/reconciler.py

数据流：
  data/raw/shopify_transactions.csv  ──┐
  data/raw/amazon_transactions.csv   ──┤── field_mapper → 统一标准字段
  data/raw/tiktok_transactions.csv   ──┘                        │
  data/raw/pingpong_settlements.csv  ───── matcher  ←───────────┤
                                                         │
                                             classifier  ←──┘
                                                         │
                                             reporter → output/对账结果_xxx.xlsx
"""

import os
import sys

# 将项目根目录加入 Python 路径，确保能 import src 下的模块
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

import pandas as pd

from field_mapper import load_and_normalize
from matcher import load_pingpong, match_orders
from classifier import classify_all, get_anomalies
from reporter import write_reconciliation_report, print_summary
from summarizer import generate_report
from alerter import send_alert


def run_reconciliation(
    data_dir: str = None,
    output_dir: str = None,
    threshold: float = 2.0,
) -> None:
    # 默认路径以项目根目录为基准
    if data_dir is None:
        data_dir = os.path.join(_PROJECT_ROOT, "data", "raw")
    if output_dir is None:
        output_dir = os.path.join(_PROJECT_ROOT, "output")
    """
    执行一次完整对账。

    参数：
      data_dir   — 原始CSV所在目录
      output_dir — 结果输出目录
      threshold  — 差异阈值（元）
    """
    print("=" * 50)
    print("🚀 开始对账流程")
    print("=" * 50)

    # ---------------------------------------------------------------
    # Step 1: 加载并归一化各平台数据
    # ---------------------------------------------------------------
    print("\n📂 第1步：读取平台数据...")

    platform_configs = [
        ("shopify", "shopify_transactions.csv"),
        ("amazon", "amazon_transactions.csv"),
        ("tiktok", "tiktok_transactions.csv"),
    ]

    all_details = []   # 所有平台的明细（保留多SKU）
    all_orders = []    # 所有平台的订单级数据（去重后）

    for platform, filename in platform_configs:
        filepath = os.path.join(data_dir, filename)
        if not os.path.exists(filepath):
            print(f"  ⚠️  {filepath} 不存在，跳过")
            continue

        detail, orders = load_and_normalize(filepath, platform)
        all_details.append(detail)
        all_orders.append(orders)
        print(f"  ✅ {platform}: {len(orders)} 笔订单, {len(detail)} 行SKU明细")

    if not all_orders:
        print("❌ 没有任何平台数据，终止。")
        return

    # 合并所有平台的订单级数据
    platform_df = pd.concat(all_orders, ignore_index=True)
    print(f"\n  📊 平台数据总计: {len(platform_df)} 笔订单")

    # ---------------------------------------------------------------
    # Step 2: 加载 PingPong 支付流水
    # ---------------------------------------------------------------
    print("\n💳 第2步：读取PingPong支付流水...")

    pingpong_path = os.path.join(data_dir, "pingpong_settlements.csv")
    if not os.path.exists(pingpong_path):
        print(f"  ❌ {pingpong_path} 不存在，终止。")
        return

    pingpong_df = load_pingpong(pingpong_path)
    print(f"  ✅ PingPong: {len(pingpong_df)} 笔流水记录")

    # ---------------------------------------------------------------
    # Step 3: 订单匹配
    # ---------------------------------------------------------------
    print("\n🔗 第3步：匹配订单...")

    matched_df, orphan_df = match_orders(platform_df, pingpong_df, threshold)
    print(f"  ✅ 匹配完成: {len(matched_df)} 笔")
    print(f"  🕊️  孤儿流水: {len(orphan_df)} 笔（支付侧无对应平台订单）")

    # ---------------------------------------------------------------
    # Step 4: 差异归类
    # ---------------------------------------------------------------
    print("\n🏷️  第4步：差异自动归类...")

    classified_df = classify_all(matched_df, threshold)
    print("  ✅ 归类完成")

    # ---------------------------------------------------------------
    # Step 5: 提取异常清单
    # ---------------------------------------------------------------
    print("\n🚨 第5步：提取异常清单...")

    anomaly_df = get_anomalies(classified_df, threshold)
    print(f"  ✅ 异常记录: {len(anomaly_df)} 笔（差异 > {threshold}元）")

    # ---------------------------------------------------------------
    # Step 6: 输出报告
    # ---------------------------------------------------------------
    print("\n📄 第6步：生成Excel报告...")

    output_path = write_reconciliation_report(
        matched_df=classified_df,
        orphan_df=orphan_df,
        anomaly_df=anomaly_df,
        output_dir=output_dir,
        threshold=threshold,
    )
    print(f"  ✅ 报告已生成: {output_path}")

    # ---------------------------------------------------------------
    # Step 7: 生成自然语言报告
    # ---------------------------------------------------------------
    print("\n📝 第7步：生成Agent报告...")

    from datetime import datetime
    report_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = generate_report(classified_df, orphan_df)
    report_path = os.path.join(output_dir, f"对账报告_{report_ts}.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  ✅ Agent报告已保存: {report_path}")
    print()
    print(report)

    # ---------------------------------------------------------------
    # Step 8: 发送告警
    # ---------------------------------------------------------------
    print("\n🔔 第8步：发送告警...")

    missing_df = classified_df[classified_df["classification"].str.contains("数据缺失", na=False)]
    missing_count = len(missing_df)
    missing_amount = round(missing_df["difference"].abs().sum(), 2) if missing_count > 0 else 0.0
    pending_count = len(classified_df[classified_df["classification"].str.contains("待查", na=False)])
    orphan_count = len(orphan_df)

    # 找最紧急的订单（数据缺失中差异最大的订单号）
    top_order = ""
    if missing_count > 0:
        top_idx = missing_df["difference"].abs().idxmax()
        top_order = str(classified_df.loc[top_idx, "order_id"])

    alert_result = send_alert(
        webhook_url=os.environ.get("FEISHU_WEBHOOK_URL", ""),
        total=len(classified_df),
        missing_count=missing_count,
        missing_amount=missing_amount,
        pending_count=pending_count,
        orphan_count=orphan_count,
        top_emergency_order=top_order,
        platform="feishu",
    )
    print(f"  ✅ 告警处理完成: {alert_result}")

    # ---------------------------------------------------------------
    # 汇总
    # ---------------------------------------------------------------
    print()
    print_summary(classified_df)
    print(f"\n📁 输出文件: {output_path}")
    print("✅ 对账流程结束")


if __name__ == "__main__":
    # 默认从 data/raw/ 读取，输出到 output/
    run_reconciliation()
