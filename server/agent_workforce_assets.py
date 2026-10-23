from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response


ENTRY_SCRIPTS = (
    '<script src="/iphone/first-run.js" defer></script>',
    '<script src="/iphone/first-run-actions.js" defer></script>',
    '<script src="/iphone/agent-workforce-entry.js" defer></script>',
    '<script src="/iphone/our-products-entry.js" defer></script>',
    '<link rel="stylesheet" href="/iphone/vishnu-os-workspaces.css">',
    '<script src="/iphone/vishnu-os-workspaces.js" defer></script>',
)


def agent_workforce_assets_router(settings) -> APIRouter:
    """Serve approved isolated workspace assets without replacing canonical PWA routes.

    The root shell is served here only to inject isolated navigation scripts;
    every other existing Vishnu PWA asset/API remains owned by its original
    router. No generic filesystem route is exposed.
    """

    router = APIRouter(prefix="/iphone", tags=["workspace-assets"])
    web_dir = Path(settings.base_dir) / "pwa"

    def read(name: str) -> str:
        return (web_dir / name).read_text(encoding="utf-8")

    def shell() -> str:
        html = read("index.html")
        for script in ENTRY_SCRIPTS:
            if script not in html:
                html = html.replace("</body>", f"  {script}\n</body>")
        return html

    @router.get("", response_class=HTMLResponse, include_in_schema=False)
    @router.get("/", response_class=HTMLResponse, include_in_schema=False)
    def iphone_home_with_workspace_entries():
        return HTMLResponse(shell(), headers={"Cache-Control": "no-store"})

    @router.get("/agents.html", response_class=HTMLResponse, include_in_schema=False)
    def agents_page():
        return HTMLResponse(read("agents.html"), headers={"Cache-Control": "no-store"})

    @router.get("/capabilities.html", response_class=HTMLResponse, include_in_schema=False)
    def capabilities_page():
        return HTMLResponse(read("capabilities.html"), headers={"Cache-Control": "no-store"})

    @router.get("/agents-workforce.css", include_in_schema=False)
    def agents_styles():
        return Response(read("agents-workforce.css"), media_type="text/css", headers={"Cache-Control": "no-cache"})

    @router.get("/agents-workforce.js", include_in_schema=False)
    def agents_script():
        return Response(read("agents-workforce.js"), media_type="application/javascript", headers={"Cache-Control": "no-cache"})

    @router.get("/agents-workforce-work-mode.js", include_in_schema=False)
    def agents_work_mode_script():
        return Response(read("agents-workforce-work-mode.js"), media_type="application/javascript", headers={"Cache-Control": "no-cache"})

    @router.get("/agent-workforce-entry.js", include_in_schema=False)
    def agents_entry_script():
        return Response(read("agent-workforce-entry.js"), media_type="application/javascript", headers={"Cache-Control": "no-cache"})

    @router.get("/our-products.html", response_class=HTMLResponse, include_in_schema=False)
    def products_page():
        return HTMLResponse(read("our-products.html"), headers={"Cache-Control": "no-store"})

    @router.get("/our-products.css", include_in_schema=False)
    def products_styles():
        return Response(read("our-products.css"), media_type="text/css", headers={"Cache-Control": "no-cache"})

    @router.get("/our-products.js", include_in_schema=False)
    def products_script():
        return Response(read("our-products.js"), media_type="application/javascript", headers={"Cache-Control": "no-cache"})

    @router.get("/our-products-build-lifecycle.js", include_in_schema=False)
    def products_build_lifecycle_script():
        return Response(read("our-products-build-lifecycle.js"), media_type="application/javascript", headers={"Cache-Control": "no-cache"})

    @router.get("/our-products-distribution.js", include_in_schema=False)
    def products_distribution_script():
        return Response(read("our-products-distribution.js"), media_type="application/javascript", headers={"Cache-Control": "no-cache"})

    @router.get("/our-products-entry.js", include_in_schema=False)
    def products_entry_script():
        return Response(read("our-products-entry.js"), media_type="application/javascript", headers={"Cache-Control": "no-cache"})

    return router
