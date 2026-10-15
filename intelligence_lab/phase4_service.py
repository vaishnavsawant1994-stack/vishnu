from __future__ import annotations

import html
import json
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse


def create_phase4_app(lab: Any) -> FastAPI:
    if not hasattr(lab, "phase3") or not hasattr(lab.phase3, "phase4"):
        raise RuntimeError("Phase 4 is not attached")
    phase4 = lab.phase3.phase4
    app = FastAPI(title="Vishnu Intelligence Lab Phase 4")

    @app.get("/phase4/status")
    def status():
        return phase4.status()

    @app.get("/phase4/observability")
    def observability():
        return phase4.observability()

    @app.get("/phase4/recommendation")
    def recommendation(task_class: str = "general", minimum_quality: float = 0.8):
        return phase4.recommended_next_configuration(
            task_class=task_class,
            minimum_quality=minimum_quality,
        )

    @app.get("/phase4/dashboard", response_class=HTMLResponse)
    def dashboard():
        snapshot = phase4.observability()
        perf = snapshot.get("phase3", {}).get("operations", {})
        rows = []
        for name, data in sorted(perf.items()):
            rows.append(
                "<tr>"
                f"<td>{html.escape(str(name))}</td>"
                f"<td>{int(data.get('samples', 0))}</td>"
                f"<td>{float(data.get('p95_latency_ms', 0.0)):.1f}</td>"
                f"<td>{float(data.get('success_rate', 0.0)):.3f}</td>"
                f"<td>{html.escape(str(data.get('mean_quality')))}</td>"
                f"<td>{html.escape(str(data.get('mean_cost')))}</td>"
                "</tr>"
            )
        qualification_counts = []
        for kind, items in snapshot.get("phase4", {}).items():
            qualification_counts.append(
                f"<li><strong>{html.escape(str(kind))}</strong>: {len(items)} recent evidence records</li>"
            )
        payload = html.escape(json.dumps(snapshot, default=str)[:12000])
        return (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<title>Vishnu Intelligence Lab Phase 4</title>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<style>"
            "body{font-family:system-ui,sans-serif;margin:32px;max-width:1200px}"
            "table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:8px;text-align:left}"
            "th{background:#f5f5f5}.ok{padding:12px;border:1px solid #bbb;border-radius:10px}"
            "pre{white-space:pre-wrap;word-break:break-word;background:#f6f6f6;padding:12px;border-radius:10px}"
            "</style></head><body>"
            "<h1>Vishnu Intelligence Lab Phase 4</h1>"
            "<p class='ok'>Read-only qualification and observability surface. "
            "No tool execution, approval, credential, or security-policy endpoint is exposed here.</p>"
            "<h2>Performance</h2><table><thead><tr>"
            "<th>Operation</th><th>Samples</th><th>P95 ms</th><th>Success</th><th>Quality</th><th>Cost</th>"
            "</tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table><h2>Qualification evidence</h2><ul>"
            + "".join(qualification_counts)
            + "</ul><h2>Bounded snapshot</h2><pre>"
            + payload
            + "</pre></body></html>"
        )

    return app
