"""Audit channel plugin entry point."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse

from api.plugins.api import PluginAPI
from api.plugins.channel import ChannelPlugin, ChannelCapabilities, ChannelMeta

from plugins.bundled.audit import file_manager, rule_store
from plugins.bundled.audit.handler import AuditHandler
from plugins.bundled.audit.models import AuditQueryRequest, AuditRule, RulesPayload, TenantConfig

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def _search_text(page, value: str) -> list:
    """Search for text on a PDF page with fallback strategies."""
    import re
    # 1. Exact match
    rects = page.search_for(value)
    if rects:
        return rects
    # 2. Strip whitespace
    cleaned = value.strip().replace("\u3000", "").replace(" ", "")
    if cleaned != value:
        rects = page.search_for(cleaned)
        if rects:
            return rects
    # 3. For numbers: try without commas
    if re.match(r"^[\d,]+\.?\d*$", value.replace(",", "")):
        no_commas = value.replace(",", "")
        rects = page.search_for(no_commas)
        if rects:
            return rects
    # 4. Substring: try first 10 chars for long values
    if len(value) > 10:
        rects = page.search_for(value[:10])
        if rects:
            return rects
    return []


def _digits_only(s: str) -> str:
    """Extract only digits from a string."""
    return "".join(c for c in s if c.isdigit())


def _fuzzy_match(ocr_text: str, target: str) -> bool:
    """Check if OCR text fuzzy-matches the target value."""
    import re
    from difflib import SequenceMatcher
    ocr_clean = ocr_text.strip()
    target_clean = target.strip()
    # 1. Exact
    if ocr_clean == target_clean:
        return True
    # 2. Numeric: compare digits only (handles commas, spaces, OCR errors on dots)
    target_digits = _digits_only(target_clean)
    if len(target_digits) >= 3:
        ocr_digits = _digits_only(ocr_clean)
        if ocr_digits and target_digits:
            # Allow partial match: one contains the other, or high overlap
            if target_digits in ocr_digits or ocr_digits in target_digits:
                return True
            # Digit similarity >= 0.8
            if SequenceMatcher(None, ocr_digits, target_digits).ratio() >= 0.8:
                return True
    # 3. Chinese/text: similarity >= 0.7
    if SequenceMatcher(None, ocr_clean, target_clean).ratio() >= 0.7:
        return True
    # 4. Substring
    if len(target_clean) > 3 and (target_clean in ocr_clean or ocr_clean in target_clean):
        return True
    return False


def _run_ocr(page, dpi: int = 150) -> list:
    """Run OCR on a PDF page, return list of (fitz.Rect_in_pdf_coords, text)."""
    import fitz
    try:
        import numpy as np
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return []
    pix = page.get_pixmap(dpi=dpi)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
    # Convert RGBA to RGB if needed
    if pix.n == 4:
        img = img[:, :, :3]
    ocr = RapidOCR()
    result, _ = ocr(img)
    if not result:
        return []
    # Convert pixel coords to PDF coords using actual dimensions
    page_rect = page.rect
    scale_x = page_rect.width / pix.w
    scale_y = page_rect.height / pix.h
    # For rotated pages, convert from visual coords to internal coords
    derot = page.derotation_matrix if page.rotation else None
    items = []
    for bbox, text, conf in result:
        # bbox is [[x0,y0],[x1,y1],[x2,y2],[x3,y3]] (4 corners)
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        pdf_rect = fitz.Rect(
            min(xs) * scale_x, min(ys) * scale_y,
            max(xs) * scale_x, max(ys) * scale_y,
        )
        if derot:
            pdf_rect = pdf_rect * derot
        items.append((pdf_rect, text))
    return items


def _ocr_find_rects(page, value: str, ocr_cache: dict = None) -> list:
    """Find text rects via OCR with fuzzy matching. Uses cache to avoid re-OCR."""
    cache_key = page.number
    if ocr_cache is not None and cache_key in ocr_cache:
        ocr_items = ocr_cache[cache_key]
    else:
        ocr_items = _run_ocr(page)
        if ocr_cache is not None:
            ocr_cache[cache_key] = ocr_items
    return [rect for rect, text in ocr_items if _fuzzy_match(text, value)]


def _rect_distance(r1, r2) -> float:
    """Euclidean distance between centers of two rects."""
    cx1, cy1 = (r1.x0 + r1.x1) / 2, (r1.y0 + r1.y1) / 2
    cx2, cy2 = (r2.x0 + r2.x1) / 2, (r2.y0 + r2.y1) / 2
    return ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5


def _find_field_rect(page, value: str, label: str = "", ocr_cache: dict = None) -> list:
    """Find the best rect for a field value, using label proximity to disambiguate.

    If label is provided and found, returns only the value rect closest to the label.
    Otherwise returns all value rects.
    Falls back to OCR for image-based PDFs.
    """
    # 1. Try PyMuPDF native search (text PDFs)
    value_rects = _search_text(page, value)
    use_ocr = False
    if not value_rects:
        # 2. Fallback: OCR search (image PDFs)
        value_rects = _ocr_find_rects(page, value, ocr_cache)
        use_ocr = True
    if not value_rects:
        return []
    if len(value_rects) == 1 or not label:
        return value_rects
    # Try to find the label on the page
    if use_ocr:
        label_rects = _ocr_find_rects(page, label, ocr_cache)
    else:
        label_rects = _search_text(page, label)
    if not label_rects and not use_ocr:
        # Try shorter label variants (last 4-6 chars)
        for trim_len in [6, 4]:
            if len(label) > trim_len:
                label_rects = _search_text(page, label[-trim_len:])
                if label_rects:
                    break
    if not label_rects:
        return value_rects
    # Pick the value rect closest to any label rect
    best_rect = min(
        value_rects,
        key=lambda vr: min(_rect_distance(vr, lr) for lr in label_rects),
    )
    return [best_rect]


class AuditChannelPlugin(ChannelPlugin):
    """Audit demo channel plugin."""

    def __init__(self, api: PluginAPI):
        self.api = api
        self.config = api.config
        self.handler = AuditHandler(
            agent_service=api.agent_service,
            session_service=api.session_service,
            config=self.config,
        )

    def get_meta(self) -> ChannelMeta:
        return ChannelMeta(
            id="audit",
            name="Financial Audit Demo",
            webhook_path="/audit/query",
            description="AI-native financial document audit",
        )

    def get_capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            send_text=True,
            send_images=True,
            send_cards=False,
            receive_webhook=True,
            session_management=True,
        )

    def create_router(self) -> APIRouter:
        """Create the /audit/* router."""
        router = APIRouter(tags=["audit"])
        handler = self.handler
        config = self.config

        # --- SPA serving ---

        @router.get("/audit/")
        async def serve_spa():
            """Serve the audit SPA."""
            index = STATIC_DIR / "index.html"
            if index.exists():
                return FileResponse(str(index), media_type="text/html")
            return JSONResponse({"error": "Frontend not found"}, status_code=404)

        # --- File management ---

        @router.post("/audit/upload")
        async def upload_file(
            file: UploadFile = File(...),
            tenant_id: str = Form(...),
        ):
            """Upload a file for audit."""
            try:
                max_size = config.get("max_upload_size_mb", 20)
                info = await file_manager.save_upload(tenant_id, file, max_size)
                return info.model_dump()
            except ValueError as e:
                return JSONResponse({"error": str(e)}, status_code=400)
            except Exception as e:
                logger.error(f"[Audit] Upload error: {e}", exc_info=True)
                return JSONResponse({"error": "Upload failed"}, status_code=500)

        @router.get("/audit/files/{tenant_id}")
        async def list_files(tenant_id: str):
            """List uploaded files for a tenant."""
            files = file_manager.list_files(tenant_id)
            return [f.model_dump() for f in files]

        @router.delete("/audit/files/{tenant_id}/{filename}")
        async def delete_file(tenant_id: str, filename: str):
            """Delete an uploaded file."""
            ok = file_manager.delete_file(tenant_id, filename)
            return {"deleted": ok}

        @router.get("/audit/files/{tenant_id}/{filename}/preview")
        async def preview_file(tenant_id: str, filename: str):
            """Serve a file for browser preview."""
            path = file_manager.get_file_path(tenant_id, filename)
            if not path:
                return JSONResponse({"error": "File not found"}, status_code=404)
            media = "application/pdf" if filename.lower().endswith(".pdf") else "image/png"
            return FileResponse(str(path), media_type=media)

        # --- PDF page preview (PyMuPDF) ---

        @router.get("/audit/files/{tenant_id}/{filename}/pages/{page}")
        async def pdf_page_preview(tenant_id: str, filename: str, page: int):
            """Render a PDF page as PNG image."""
            path = file_manager.get_file_path(tenant_id, filename)
            if not path or not filename.lower().endswith(".pdf"):
                return JSONResponse({"error": "PDF not found"}, status_code=404)
            try:
                def _render():
                    import fitz
                    doc = fitz.open(str(path))
                    if page < 1 or page > len(doc):
                        doc.close()
                        raise ValueError(f"Page {page} out of range (1-{len(doc)})")
                    pg = doc[page - 1]
                    pix = pg.get_pixmap(dpi=150)
                    png_bytes = pix.tobytes("png")
                    doc.close()
                    return png_bytes

                loop = asyncio.get_event_loop()
                png_bytes = await loop.run_in_executor(None, _render)
                from fastapi.responses import Response
                return Response(content=png_bytes, media_type="image/png")
            except ValueError as e:
                return JSONResponse({"error": str(e)}, status_code=400)
            except ImportError:
                return JSONResponse({"error": "PyMuPDF not installed"}, status_code=501)
            except Exception as e:
                logger.error(f"[Audit] PDF render error: {e}", exc_info=True)
                return JSONResponse({"error": str(e)}, status_code=500)

        @router.get("/audit/files/{tenant_id}/{filename}/pages/{page}/highlighted")
        async def pdf_page_highlighted(
            tenant_id: str, filename: str, page: int,
            highlights: str = Query("[]"),
        ):
            """Render a PDF page as PNG with highlighted text regions."""
            path = file_manager.get_file_path(tenant_id, filename)
            if not path or not filename.lower().endswith(".pdf"):
                return JSONResponse({"error": "PDF not found"}, status_code=404)
            try:
                def _render_highlighted():
                    import fitz
                    doc = fitz.open(str(path))
                    if page < 1 or page > len(doc):
                        doc.close()
                        raise ValueError(f"Page {page} out of range (1-{len(doc)})")
                    pg = doc[page - 1]

                    try:
                        hl_list = json.loads(highlights)
                    except Exception:
                        hl_list = []

                    misses = []
                    ocr_cache = {}
                    for hl in hl_list:
                        value = hl.get("value", "")
                        label = hl.get("label", "")
                        color_hex = hl.get("color", "#FBBF24")
                        if not value:
                            continue

                        rects = _find_field_rect(pg, value, label, ocr_cache)
                        if not rects:
                            misses.append(value)
                            continue

                        ch = color_hex.lstrip("#")
                        r, g, b = int(ch[0:2], 16) / 255, int(ch[2:4], 16) / 255, int(ch[4:6], 16) / 255

                        for rect in rects:
                            padded = fitz.Rect(rect.x0 - 2, rect.y0 - 2, rect.x1 + 2, rect.y1 + 2)
                            pg.draw_rect(padded, color=(r, g, b), width=1.5, overlay=True)
                            if label:
                                label_pt = fitz.Point(rect.x0, rect.y0 - 4)
                                pg.insert_text(label_pt, label, fontsize=6, color=(r, g, b),
                                               fontname="china-s", overlay=True)

                    pix = pg.get_pixmap(dpi=150)
                    png_bytes = pix.tobytes("png")
                    doc.close()
                    return png_bytes, misses

                loop = asyncio.get_event_loop()
                png_bytes, misses = await loop.run_in_executor(None, _render_highlighted)
                from fastapi.responses import Response
                headers = {}
                if misses:
                    headers["X-Highlight-Misses"] = ",".join(misses)
                return Response(content=png_bytes, media_type="image/png", headers=headers)
            except ValueError as e:
                return JSONResponse({"error": str(e)}, status_code=400)
            except ImportError:
                return JSONResponse({"error": "PyMuPDF not installed"}, status_code=501)
            except Exception as e:
                logger.error(f"[Audit] PDF highlight render error: {e}", exc_info=True)
                return JSONResponse({"error": str(e)}, status_code=500)

        @router.get("/audit/files/{tenant_id}/{filename}/page-count")
        async def pdf_page_count(tenant_id: str, filename: str):
            """Get the number of pages in a PDF."""
            path = file_manager.get_file_path(tenant_id, filename)
            if not path or not filename.lower().endswith(".pdf"):
                return JSONResponse({"error": "PDF not found"}, status_code=404)
            try:
                def _count():
                    import fitz
                    doc = fitz.open(str(path))
                    count = len(doc)
                    doc.close()
                    return count

                loop = asyncio.get_event_loop()
                count = await loop.run_in_executor(None, _count)
                return {"pages": count}
            except ImportError:
                return {"pages": -1, "error": "PyMuPDF not installed"}

        # --- Rules management ---

        @router.get("/audit/rules/{tenant_id}")
        async def get_rules(tenant_id: str):
            """Get all rules for a tenant."""
            rules = rule_store.get_rules(tenant_id)
            return [r.model_dump() for r in rules]

        @router.put("/audit/rules/{tenant_id}")
        async def update_rules(tenant_id: str, payload: RulesPayload):
            """Replace all rules for a tenant."""
            rule_store.save_rules(tenant_id, payload.rules)
            return {"saved": len(payload.rules)}

        # --- Tenant config ---

        @router.get("/audit/config/{tenant_id}")
        async def get_config(tenant_id: str):
            """Get tenant config."""
            from api.constants import TENANTS_DIR
            config_path = TENANTS_DIR / tenant_id / "audit-config.json"
            if config_path.exists():
                return json.loads(config_path.read_text(encoding="utf-8"))
            return {"tenant_id": tenant_id, "display_name": tenant_id, "settings": {}}

        @router.put("/audit/config/{tenant_id}")
        async def update_config(tenant_id: str, config_data: TenantConfig):
            """Update tenant config."""
            from api.constants import TENANTS_DIR
            config_path = TENANTS_DIR / tenant_id / "audit-config.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                json.dumps(config_data.model_dump(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return {"saved": True}

        # --- Audit query ---

        @router.post("/audit/query")
        async def audit_query(request: Request):
            """Run audit and stream results via SSE."""
            try:
                body = await request.json()
                audit_request = AuditQueryRequest(**body)

                return EventSourceResponse(
                    handler.process_audit(audit_request),
                    media_type="text/event-stream",
                )
            except Exception as e:
                logger.error(f"[Audit] Query error: {e}", exc_info=True)
                return JSONResponse({"error": str(e)}, status_code=500)

        return router

    async def send_text(
        self,
        recipient_id: str,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Not used for audit (web-based, not messaging channel)."""
        return False

    async def on_start(self) -> None:
        logger.info("[Audit] Audit plugin started")

    async def on_stop(self) -> None:
        logger.info("[Audit] Audit plugin stopped")


def register(api: PluginAPI) -> AuditChannelPlugin:
    """Plugin entry point."""
    plugin = AuditChannelPlugin(api)
    router = plugin.create_router()
    api.register_router(router)
    logger.info(f"[Audit] Audit plugin registered")
    return plugin
