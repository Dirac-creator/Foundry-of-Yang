"""Authenticated browser/API entry point for a small research team."""
import os
import sqlite3
from urllib.parse import quote
from starlette.concurrency import run_in_threadpool
from importlib.resources import files
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .models import PARAMETERS, PROCESS_TYPES, ProcessType, RecordInput, SampleInput
from .store import Conflict, Store


def create_app(database_path=None):
    store = Store(database_path or os.environ.get("FOUNDRY_DB", "data/local/foundry.sqlite3"))
    app = FastAPI(title="Foundry 工艺记录", version="0.4.0", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store
    bearer = HTTPBearer(auto_error=False)

    @app.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self' https://api.github.com; frame-ancestors 'none'; base-uri 'none'"
        return response

    def user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        account = store.authenticate(credentials.credentials) if credentials else None
        if not account:
            raise HTTPException(401, "请输入有效的个人访问令牌", headers={"WWW-Authenticate": "Bearer"})
        return account

    def editor(account=Depends(user)):
        if account["role"] != "editor":
            raise HTTPException(403, "当前账号只有查看权限")
        return account

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(sqlite3.OperationalError)
    async def database_busy(request, exc):
        return JSONResponse(status_code=503, content={"detail": "数据库暂不可用，请保留表单并稍后重试"})

    @app.get("/", response_class=HTMLResponse)
    def index():
        return files("foundry.service").joinpath("static/index.html").read_text(encoding="utf-8")

    @app.get("/assets/{name}")
    def asset(name: str):
        types = {"app.js": "text/javascript", "app.css": "text/css", "github-store.js": "text/javascript", "catalog.json": "application/json"}
        if name not in types:
            raise HTTPException(404)
        return Response(files("foundry.service").joinpath("static", name).read_text(encoding="utf-8"), media_type=types[name])

    @app.get("/api/me")
    def me(account=Depends(user)):
        return account

    @app.get("/api/catalog")
    def catalog(account=Depends(user)):
        return {"process_types": PROCESS_TYPES, "parameters": PARAMETERS}

    @app.get("/api/samples")
    def samples(account=Depends(user)):
        return store.list_samples()

    @app.post("/api/samples", status_code=201)
    def add_sample(data: SampleInput, account=Depends(editor)):
        return store.add_sample(data, account["name"])

    @app.post("/api/records", status_code=201)
    def add_record(data: RecordInput, account=Depends(editor)):
        return store.add_record(data, account["name"])

    @app.get("/api/records")
    def records(sample_id: str | None = None, process_type: ProcessType | None = None,
                limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                include_history: bool = False, account=Depends(user)):
        return store.list_records(sample_id, process_type, limit, offset, include_history)

    @app.get("/api/records/{record_id}/attachments")
    def attachments(record_id: str, account=Depends(user)):
        if not store.record_exists(record_id):
            raise HTTPException(404, "工艺记录不存在")
        return store.list_attachments(record_id)

    @app.post("/api/records/{record_id}/attachments", status_code=201)
    async def upload_attachment(record_id: str, request: Request,
                                filename: str = Query(min_length=1, max_length=240), account=Depends(editor)):
        if not await run_in_threadpool(store.record_exists, record_id):
            raise HTTPException(404, "工艺记录不存在")
        limit = 50 * 1024 * 1024
        length = request.headers.get("content-length")
        if length:
            try:
                declared = int(length)
            except ValueError:
                raise HTTPException(400, "Content-Length 无效")
            if declared < 0:
                raise HTTPException(400, "Content-Length 无效")
            if declared > limit:
                raise HTTPException(413, "每个附件不能超过50 MiB")
        content = bytearray()
        async for chunk in request.stream():
            if len(content) + len(chunk) > limit:
                raise HTTPException(413, "每个附件不能超过50 MiB")
            content.extend(chunk)
        return await run_in_threadpool(store.add_attachment, record_id, filename, bytes(content), account["name"])

    @app.get("/api/attachments/{attachment_id}/download")
    def download_attachment(attachment_id: str, account=Depends(user)):
        item = store.get_attachment(attachment_id)
        if not item:
            raise HTTPException(404, "附件不存在")
        return Response(item["content"], media_type="application/octet-stream", headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(item["filename"], safe=""),
            "X-Content-SHA256": item["sha256"],
        })

    return app
