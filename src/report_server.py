"""
report_server.py — 对账报告网页查看器

启动后，浏览器打开 http://127.0.0.1:5000 即可查看所有历史报告。
按日期排列，点开看完整内容，也可以下载Excel。

用法：
  python src/report_server.py
  然后浏览器访问 http://127.0.0.1:5000
"""

import os
import sys
import glob

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(_PROJECT_ROOT, "output")

from flask import Flask, render_template_string, send_from_directory

app = Flask(__name__)


def get_reports():
    """
    扫描 output 目录，找出所有对账结果文件，按时间分组。
    返回列表，每个元素是一轮对账的完整记录。
    """
    reports = {}

    # 匹配所有对账结果文件
    excel_files = glob.glob(os.path.join(OUTPUT_DIR, "对账结果_*.xlsx"))
    txt_files = glob.glob(os.path.join(OUTPUT_DIR, "对账报告_*.txt"))

    for excel_path in excel_files:
        basename = os.path.basename(excel_path)
        # 从文件名提取时间戳：对账结果_20260728_054040.xlsx
        ts = basename.replace("对账结果_", "").replace(".xlsx", "")

        # 找对应的 txt 报告
        txt_path = os.path.join(OUTPUT_DIR, f"对账报告_{ts}.txt")
        report_content = ""
        if os.path.exists(txt_path):
            with open(txt_path, "r", encoding="utf-8") as f:
                report_content = f.read()

        # 文件修改时间
        mtime = os.path.getmtime(excel_path)

        reports[ts] = {
            "timestamp": ts,
            "excel": basename,
            "report": report_content,
            "mtime": mtime,
        }

    # 按时间倒序排列（最新的排最前）
    sorted_reports = sorted(reports.values(), key=lambda r: r["mtime"], reverse=True)
    return sorted_reports


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>对账报告</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, "Microsoft YaHei", sans-serif;
            background: #f5f6fa;
            color: #2c3e50;
            padding: 30px;
        }
        h1 {
            font-size: 24px;
            margin-bottom: 10px;
            color: #1a1a2e;
        }
        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
        }
        .report-card {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            margin-bottom: 20px;
            overflow: hidden;
        }
        .report-header {
            padding: 16px 20px;
            background: #f8f9fc;
            border-bottom: 1px solid #eee;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .report-time {
            font-weight: bold;
            color: #2c3e50;
        }
        .report-links a {
            color: #3498db;
            text-decoration: none;
            font-size: 13px;
            margin-left: 15px;
        }
        .report-links a:hover {
            text-decoration: underline;
        }
        .report-body {
            padding: 20px;
            white-space: pre-wrap;
            font-size: 14px;
            line-height: 1.8;
            color: #444;
        }
        .empty {
            text-align: center;
            padding: 60px;
            color: #999;
        }
        .badge {
            display: inline-block;
            background: #e74c3c;
            color: white;
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 10px;
            margin-left: 8px;
        }
        .badge.ok {
            background: #27ae60;
        }
    </style>
</head>
<body>
    <h1>📊 对账报告</h1>
    <p class="subtitle">共 {{ reports|length }} 次对账记录，按时间倒序排列</p>

    {% if reports %}
        {% for r in reports %}
        <div class="report-card">
            <div class="report-header">
                <span class="report-time">{{ r.timestamp[:4] }}-{{ r.timestamp[4:6] }}-{{ r.timestamp[6:8] }} {{ r.timestamp[9:11] }}:{{ r.timestamp[11:13] }}</span>
                <span class="report-links">
                    <a href="/download/{{ r.excel }}">📥 下载Excel</a>
                    <a href="#" onclick="toggleReport('report-{{ loop.index }}'); return false;">📄 展开报告</a>
                </span>
            </div>
            <div id="report-{{ loop.index }}" class="report-body" style="display: none;">{{ r.report }}</div>
        </div>
        {% endfor %}
    {% else %}
        <div class="empty">
            <p>暂无对账报告</p>
            <p style="font-size: 13px; margin-top: 10px;">请先运行 <code>python src/reconciler.py</code> 完成一次对账</p>
        </div>
    {% endif %}

    <script>
        function toggleReport(id) {
            var el = document.getElementById(id);
            if (el.style.display === 'none') {
                el.style.display = 'block';
            } else {
                el.style.display = 'none';
            }
        }
    </script>
</body>
</html>
"""


@app.route("/")
def index():
    reports = get_reports()
    return render_template_string(HTML_TEMPLATE, reports=reports)


@app.route("/download/<filename>")
def download(filename):
    """下载 Excel 报告"""
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    print("=" * 50)
    print("=== 对账报告查看器 ===")
    print("=" * 50)
    print(f"  输出目录: {OUTPUT_DIR}")
    print(f"  浏览器访问: http://127.0.0.1:5000")
    print("  Ctrl+C 停止")
    print("=" * 50)
    app.run(debug=False, host="127.0.0.1", port=5000)
