"""
alerter.py — 飞书/钉钉告警推送

职责：
  对账完成后，如果有严重异常（数据缺失/待查），自动推送到群机器人。
  用户只需配置 Webhook URL，系统自动决定发什么内容。

v3.0 需求：
  "异常主动推给我，别等我去看"
"""

import json
import urllib.request
import urllib.error


# ============================================================
# 配置
# ============================================================

# 飞书群机器人 Webhook URL
# 格式: https://open.feishu.cn/open-apis/bot/v2/hook/{token}
# 使用前请替换为真实的 webhook 地址
WEBHOOK_URL = ""

# 钉钉群机器人 Webhook URL（备用，格式不同）
# WEBHOOK_URL = "https://oapi.dingtalk.com/robot/send?access_token={token}"


# ============================================================
# 告警内容生成
# ============================================================

def build_alert_message(
    total: int,
    missing_count: int,
    missing_amount: float,
    pending_count: int,
    orphan_count: int,
    top_emergency_order: str,
) -> str:
    """
    生成告警消息正文。

    原则：简炼，一行结论，财务扫一眼就知道要不要打开飞书。
    - 有数据缺失 → 报缺失笔数+金额+最紧急的订单号
    - 没缺失但有待查 → 报待查笔数
    - 正常 → 报"今日对账正常"
    """
    if missing_count > 0:
        return (
            f"🚨 对账异常告警\n"
            f"数据缺失{missing_count}笔，涉及{missing_amount}元\n"
            f"最紧急订单：{top_emergency_order}\n"
            f"待查{pending_count}笔，孤儿流水{orphan_count}笔\n"
            f"请登录系统查看完整报告。"
        )
    elif pending_count > 0:
        return (
            f"⚠️ 对账提醒\n"
            f"待查差异{pending_count}笔，孤儿流水{orphan_count}笔\n"
            f"建议登录系统查看详情。"
        )
    elif orphan_count > 0:
        return (
            f"⚠️ 对账提醒\n"
            f"存在孤儿流水{orphan_count}笔\n"
            f"建议联系PingPong获取原始凭证。"
        )
    else:
        return f"✅ 今日对账正常，{total}笔订单全部匹配。"


# ============================================================
# 推送
# ============================================================

def send_feishu(webhook_url: str, message: str) -> str:
    """
    推送文本消息到飞书群机器人。

    参数：
      webhook_url — 飞书机器人的 Webhook 地址
      message     — 消息正文

    返回：
      成功 → "ok"
      失败 → 错误描述
    """
    payload = {
        "msg_type": "text",
        "content": {
            "text": message,
        },
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            result = json.loads(body)
            if result.get("StatusCode") == 0 or result.get("code") == 0:
                return "ok"
            else:
                return f"飞书返回错误: {body}"
    except urllib.error.HTTPError as e:
        return f"HTTP错误: {e.code} {e.reason}"
    except urllib.error.URLError as e:
        return f"网络错误: {e.reason}"
    except Exception as e:
        return f"发送失败: {e}"


def send_dingtalk(webhook_url: str, message: str) -> str:
    """
    推送文本消息到钉钉群机器人。

    钉钉的消息格式跟飞书不同，需要包在 text.content 里。
    """
    payload = {
        "msg_type": "text",
        "content": {
            "text": message,
        },
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            result = json.loads(body)
            if result.get("errcode") == 0:
                return "ok"
            else:
                return f"钉钉返回错误: {body}"
    except Exception as e:
        return f"发送失败: {e}"


def send_alert(
    webhook_url: str,
    total: int,
    missing_count: int,
    missing_amount: float,
    pending_count: int,
    orphan_count: int,
    top_emergency_order: str,
    platform: str = "feishu",
) -> str:
    """
    统一告警入口。

    自动判断：
      - webhook_url 为空 → 只打印日志，不发送
      - webhook_url 有值 → 按 platform 选择发送方式

    参数：
      webhook_url          — Webhook 地址
      total                — 总订单数
      missing_count        — 数据缺失笔数
      missing_amount       — 数据缺失总金额
      pending_count        — 待查笔数
      orphan_count         — 孤儿流水笔数
      top_emergency_order  — 最紧急的订单号
      platform             — "feishu" 或 "dingtalk"

    返回：
      发送结果描述
    """
    message = build_alert_message(
        total=total,
        missing_count=missing_count,
        missing_amount=missing_amount,
        pending_count=pending_count,
        orphan_count=orphan_count,
        top_emergency_order=top_emergency_order,
    )

    if not webhook_url:
        # 未配置 Webhook，只打印日志
        print(f"  📋 告警已生成（未配置Webhook，未推送）")
        print(f"     {message}")
        return "未配置Webhook"

    if platform == "dingtalk":
        return send_dingtalk(webhook_url, message)
    else:
        return send_feishu(webhook_url, message)
