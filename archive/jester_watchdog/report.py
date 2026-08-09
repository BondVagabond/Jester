
import json, datetime, html
from typing import List, Dict, Any
from .checks import CheckResult

CSS = (
    "body{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:24px;}"
    "h1{font-size:22px;margin-bottom:8px}"
    "table{border-collapse:collapse;width:100%;margin:16px 0;}"
    "th,td{border:1px solid #ddd;padding:8px;font-size:14px}"
    "th{background:#f4f4f4;text-align:left}"
    ".badge{display:inline-block;padding:2px 8px;border-radius:8px;font-size:12px}"
    ".INFO{background:#e6f4ea;color:#1e7f43}"
    ".WARN{background:#fff6e5;color:#8a5a00}"
    ".ERROR{background:#fde8e8;color:#9b1c1c}"
    "pre{background:#f9f9f9;padding:8px;border:1px solid #eee;white-space:pre-wrap}"
    ".summary{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0}"
    ".card{border:1px solid #eee;padding:12px;border-radius:8px}"
    ".small{font-size:12px;color:#666}"
)

def render_html(results: List[CheckResult], meta: Dict[str,Any]) -> str:
    rows_html = []
    for r in results:
        extra = html.escape(json.dumps(r.extra, ensure_ascii=False, indent=2))
        row = (
            "<tr>"
            f"<td>{html.escape(r.name)}</td>"
            f"<td><span class='badge {r.level}'>{html.escape(r.level)}</span></td>"
            f"<td>{html.escape(r.message)}</td>"
            f"<td><pre>{extra}</pre></td>"
            "</tr>"
        )
        rows_html.append(row)

    meta_html = html.escape(json.dumps(meta, ensure_ascii=False, indent=2))

    parts = []
    parts.append("<!doctype html><meta charset='utf-8'>")
    parts.append("<title>Jester Watchdog Report</title>")
    parts.append(f"<style>{CSS}</style>")
    parts.append("<h1>Jester Watchdog Report</h1>")
    parts.append(f"<div class='small'>Generated at {html.escape(datetime.datetime.utcnow().isoformat())}Z</div>")
    parts.append("""
<div class="summary">
  <div class="card"><b>Total checks:</b> {total}</div>
  <div class="card"><b>Inputs analyzed:</b> {num}</div>
</div>
""".format(total=len(results), num=meta.get("num_records", 0)))
    parts.append("<h2>Results</h2>")
    parts.append("<table><tr><th>Check</th><th>Level</th><th>Message</th><th>Details</th></tr>")
    parts.append("".join(rows_html))
    parts.append("</table>")
    parts.append("<h2>Meta</h2>")
    parts.append(f"<pre>{meta_html}</pre>")
    return "".join(parts)
