"""
field_mapper.py — 字段归一化模块

职责：将各平台CSV的原始列名，统一映射为引擎内部标准字段。
      同时处理多SKU订单的金额去重。

为什么要这个模块？
  各平台导出格式不同（Total / total / Gross Amount），
  如果匹配、归类代码直接引用原始列名，
  每加一个新平台就要改3-4个文件。
  归一化后，后续模块只认标准字段，加平台只改这一个文件。
"""

import pandas as pd

# ============================================================
# 1. 标准内部字段定义
# ============================================================
# 这是引擎内部统一使用的字段名。
# 不管Shopify/Amazon/TikTok原始列名叫什么，进来都转成这套。
STANDARD_FIELDS = [
    "order_id",          # 订单号（匹配键）
    "platform",          # 平台来源（shopify/amazon/tiktok）
    "sku",               # 商品编码（SKU级明细）
    "item_total",        # 商品单价（SKU级）
    "shipping",          # 运费
    "tax",               # 税费
    "total",             # 订单应收总额（订单级，同一单各行相同！）
    "platform_fee",      # 平台收取的手续费
    "currency",          # 币种
    "created_at",        # 下单时间
]

# ============================================================
# 2. 各平台 → 标准字段 映射字典
# ============================================================
# 格式：{原始列名: 标准字段名}
# 各平台特有的字段（如 settlement-id）不映射，保留在 raw_ 前缀字段中

SHOPIFY_COLUMN_MAP = {
    "Order": "order_id",
    "Created At": "created_at",
    "SKU": "sku",
    "Item Total": "item_total",
    "Shipping": "shipping",
    "Tax": "tax",
    "Total": "total",
    "Transaction Fee": "platform_fee",
    "Gateway": "raw_gateway",
    "Payout ID": "raw_payout_id",
}

AMAZON_COLUMN_MAP = {
    "amazon-order-id": "order_id",
    "purchase-date": "created_at",
    "sku": "sku",
    "item-price": "item_total",
    "shipping-price": "shipping",
    "tax-price": "tax",
    "total": "total",
    "commission": "platform_fee",
    "fba-fees": "raw_fba_fees",
    "settlement-id": "raw_settlement_id",
}

TIKTOK_COLUMN_MAP = {
    "Order ID": "order_id",
    "Create Time": "created_at",
    "Product Code": "sku",
    "Subtotal": "item_total",
    "Delivery Fee": "shipping",
    "Sales Tax": "tax",
    "Gross Amount": "total",
    "Platform Fee": "platform_fee",
    "Order Status": "raw_order_status",
}

# ============================================================
# 3. 归一化函数
# ============================================================

def normalize_shopify(df: pd.DataFrame) -> pd.DataFrame:
    """将Shopify原始DataFrame映射为标准字段"""
    df = df.rename(columns=SHOPIFY_COLUMN_MAP)
    df["platform"] = "shopify"
    df["currency"] = "USD"
    # 只保留标准字段 + platform（其余raw_前缀字段暂丢弃，v1.0不处理）
    keep_cols = [c for c in STANDARD_FIELDS if c in df.columns]
    return df[keep_cols]


def normalize_amazon(df: pd.DataFrame) -> pd.DataFrame:
    """将Amazon原始DataFrame映射为标准字段"""
    df = df.rename(columns=AMAZON_COLUMN_MAP)
    df["platform"] = "amazon"
    df["currency"] = "USD"
    # Amazon: commission 映射为 platform_fee（v1.2精细化）
    keep_cols = [c for c in STANDARD_FIELDS if c in df.columns]
    return df[keep_cols]


def normalize_tiktok(df: pd.DataFrame) -> pd.DataFrame:
    """将TikTok Shop原始DataFrame映射为标准字段"""
    df = df.rename(columns=TIKTOK_COLUMN_MAP)
    df["platform"] = "tiktok"
    df["currency"] = "USD"
    keep_cols = [c for c in STANDARD_FIELDS if c in df.columns]
    return df[keep_cols]


# ============================================================
# 4. 多SKU订单去重
# ============================================================

def deduplicate_order_total(df: pd.DataFrame) -> pd.DataFrame:
    """
    核心问题：
      一笔订单有3个SKU = 3行，每行的 total 都是同一个数（订单总额）。
      如果直接用3行去匹配 PingPong，会把一笔账算成3倍。

    解决方案：
      按 order_id 分组，对 total 取 first()（反正每行都一样），
      然后合并回明细数据。

    参数：
      df — 已归一化的平台DataFrame
    返回：
      (明细数据, 订单级去重数据) 的元组
    """
    # Step 1: 从明细中提取订单级字段（total），去重
    order_level = (
        df[["order_id", "total", "platform_fee", "platform", "currency"]]
        .drop_duplicates(subset="order_id")
        .copy()
    )

    # Step 2: 重新合并回明细（去掉明细中冗余的 total，用订单级 total 替代）
    # 这一步看起来多余？其实是为了后面扩展做准备——
    # 当订单级字段越来越多时（如 shipping、tax），统一从这里管理
    detail = df.drop(columns=["total", "platform_fee"], errors="ignore")
    detail = detail.merge(
        order_level[["order_id", "total", "platform_fee"]],
        on="order_id",
        how="left",
    )

    return detail, order_level


# ============================================================
# 5. 统一入口：读CSV → 归一化 → 去重
# ============================================================

def load_and_normalize(filepath: str, platform: str) -> tuple:
    """
    统一入口函数。

    流程：
      读取CSV → 按平台选择映射规则 → 归一化 → 订单级金额去重

    参数：
      filepath — CSV文件路径
      platform — 平台标识: "shopify" / "amazon" / "tiktok"

    返回：
      (detail_df, order_df)
        detail_df — 行项目明细（保留所有SKU）
        order_df  — 订单级去重数据（每个订单一行，用于匹配）

    用法示例：
      detail, orders = load_and_normalize("data/raw/shopify_transactions.csv", "shopify")
    """
    # 读取原始CSV
    raw = pd.read_csv(filepath)

    # 按平台选择映射规则
    normalizers = {
        "shopify": normalize_shopify,
        "amazon": normalize_amazon,
        "tiktok": normalize_tiktok,
    }

    if platform not in normalizers:
        raise ValueError(f"不支持的平台: {platform}，可选: {list(normalizers.keys())}")

    # 归一化
    normalized = normalizers[platform](raw)

    # 确保数值列为浮点数（防止CSV读成字符串）
    numeric_cols = ["item_total", "shipping", "tax", "total", "platform_fee"]
    for col in numeric_cols:
        if col in normalized.columns:
            normalized[col] = pd.to_numeric(normalized[col], errors="coerce").fillna(0.0)

    # 多SKU去重
    detail, orders = deduplicate_order_total(normalized)

    return detail, orders
