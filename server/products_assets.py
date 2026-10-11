from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, Response


def products_assets_router(settings) -> APIRouter:
    """Serve the isolated Our Products owner workspace assets."""
    router = APIRouter(prefix="/iphone", tags=["our-products-assets"])
    web_dir = Path(settings.base_dir) / "pwa"

    def read(name: str) -> str:
        return (web_dir / name).read_text(encoding="utf-8")

    @router.get("/our-products.html", response_class=HTMLResponse, include_in_schema=False)
    def products_page():
        return HTMLResponse(read("our-products.html"), headers={"Cache-Control": "no-store"})

    @router.get("/our-products.css", include_in_schema=False)
    def products_styles():
        return Response(read("our-products.css"), media_type="text/css", headers={"Cache-Control": "no-cache"})

    @router.get("/our-products.js", include_in_schema=False)
    def products_script():
        return Response(read("our-products.js"), media_type="application/javascript", headers={"Cache-Control": "no-cache"})

    @router.get("/our-products-entry.js", include_in_schema=False)
    def products_entry_script():
        return Response(read("our-products-entry.js"), media_type="application/javascript", headers={"Cache-Control": "no-cache"})

    return router
