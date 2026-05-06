"""FAQ CRUD API."""
import logging
import os
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.db import get_faq_pool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/faq", tags=["faq"])

FAQ_CATEGORIES = [
    "开票", "收票", "鉴权登录", "接口参数", "进项发票采集", "性能超时", "faq-newtimeai-invoice"
]


class DraftSubmit(BaseModel):
    category: str
    type: Literal["qa", "section"] = "qa"
    question: str        # qa 类型为问题标题，section 类型为段落标题
    answer: str          # qa 类型为答案，section 类型为段落内容
    submitter: str
    sort_order: int | None = None


class DraftUpdate(BaseModel):
    question: str | None = None
    answer: str | None = None
    category: str | None = None
    sort_order: int | None = None


class DraftReview(BaseModel):
    action: Literal["approved", "rejected"]
    reviewer: str
    password: str
    comment: str = ""


def _check_password(password: str):
    expected = os.getenv("FAQ_REVIEW_PASSWORD", "")
    if expected and password != expected:
        raise HTTPException(status_code=403, detail="审核密码错误")


def _row_to_dict(row) -> dict:
    d = dict(row)
    for k, v in d.items():
        if hasattr(v, 'isoformat'):
            d[k] = v.isoformat() if v else None
    return d


@router.get("/categories")
async def list_categories():
    return {"categories": FAQ_CATEGORIES}


@router.get("/drafts")
async def list_drafts(status: str = "", category: str = "", page: int = 1, page_size: int = 20):
    pool = await get_faq_pool()
    conditions = []
    args = []
    if status:
        args.append(status)
        conditions.append(f"status = ${len(args)}")
    if category:
        args.append(category)
        conditions.append(f"category = ${len(args)}")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    offset = (page - 1) * page_size
    args_with_limit = args + [page_size, offset]
    sql = f"""
        SELECT * FROM faq_items {where}
        ORDER BY created_at DESC
        LIMIT ${len(args_with_limit)-1} OFFSET ${len(args_with_limit)}
    """
    count_sql = f"SELECT COUNT(*) FROM faq_items {where}"
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *args_with_limit)
        total = await conn.fetchval(count_sql, *args)
    return {"drafts": [_row_to_dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/drafts")
async def submit_draft(body: DraftSubmit):
    if body.category not in FAQ_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"无效分类，可选：{FAQ_CATEGORIES}")
    pool = await get_faq_pool()
    async with pool.acquire() as conn:
        if body.sort_order is None:
            max_order = await conn.fetchval(
                "SELECT COALESCE(MAX(sort_order), 0) FROM faq_items WHERE category = $1",
                body.category,
            )
            sort_order = max_order + 10
        else:
            sort_order = body.sort_order
        row = await conn.fetchrow(
            """INSERT INTO faq_items (category, type, question, answer, submitter, sort_order)
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING *""",
            body.category, body.type, body.question, body.answer, body.submitter, sort_order
        )
    return _row_to_dict(row)


@router.put("/drafts/{draft_id}")
async def update_draft(draft_id: int, body: DraftUpdate):
    pool = await get_faq_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM faq_items WHERE id = $1", draft_id)
        if not row:
            raise HTTPException(status_code=404, detail="条目不存在")
        if row["status"] != "pending":
            raise HTTPException(status_code=400, detail="只能修改待审核条目")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            return _row_to_dict(row)
        set_clause = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(updates))
        values = list(updates.values())
        row = await conn.fetchrow(
            f"UPDATE faq_items SET {set_clause}, updated_at = NOW() WHERE id = $1 RETURNING *",
            draft_id, *values
        )
    return _row_to_dict(row)


@router.delete("/drafts/{draft_id}")
async def delete_draft(draft_id: int, password: str = ""):
    _check_password(password)
    pool = await get_faq_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM faq_items WHERE id = $1", draft_id)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="条目不存在")
    return {"ok": True}


@router.post("/drafts/{draft_id}/review")
async def review_draft(draft_id: int, body: DraftReview):
    _check_password(body.password)
    pool = await get_faq_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM faq_items WHERE id = $1", draft_id)
        if not row:
            raise HTTPException(status_code=404, detail="条目不存在")
        if row["status"] != "pending":
            raise HTTPException(status_code=400, detail="该条目已审核")
        row = await conn.fetchrow(
            """UPDATE faq_items
               SET status=$2, reviewer=$3, comment=$4, updated_at=NOW()
               WHERE id=$1 RETURNING *""",
            draft_id, body.action, body.reviewer, body.comment
        )
    return _row_to_dict(row)


@router.get("/preview/{category}")
async def preview_category(category: str, password: str = ""):
    _check_password(password)
    if category not in FAQ_CATEGORIES:
        raise HTTPException(status_code=400, detail="无效分类")
    from api.services.faq_publisher import generate_category_content, _faq_filename
    content = await generate_category_content(category)
    return {"category": category, "filename": _faq_filename(category), "content": content}


@router.get("/download/{category}")
async def download_category(category: str, password: str = ""):
    _check_password(password)
    if category not in FAQ_CATEGORIES:
        raise HTTPException(status_code=400, detail="无效分类")
    from fastapi.responses import Response
    from urllib.parse import quote
    from api.services.faq_publisher import generate_category_content, _faq_filename
    content = await generate_category_content(category)
    filename = _faq_filename(category)
    encoded_filename = quote(filename)
    return Response(
        content=content.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
    )


@router.get("/download-all")
async def download_all(password: str = ""):
    _check_password(password)
    import io
    import zipfile
    from fastapi.responses import StreamingResponse
    from api.services.faq_publisher import generate_all_contents, _faq_filename

    contents = await generate_all_contents()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for category, content in contents.items():
            zf.writestr(_faq_filename(category), content.encode("utf-8"))
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=faq-all.zip"}
    )
