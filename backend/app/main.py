import os
import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes import router
from app.core.config import VASP_API_KEY, CORS_ORIGINS, ALLOWED_HOSTS, MAX_UPLOAD_SIZE

app = FastAPI(
    title="VASP Agent",
    description="Automated VASP input file generation and calculation management",
    version="0.1.0",
)

# ── CORS ─────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Trusted host ──────────────────────────────────────────────────────────

if ALLOWED_HOSTS != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

# ── Upload size limit ─────────────────────────────────────────────────────


class _MaxUploadSizeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_UPLOAD_SIZE:
            return JSONResponse(
                {"detail": {"error": "上传文件过大", "suggestion": f"文件大小不能超过 {MAX_UPLOAD_SIZE // 1024 // 1024} MB"}},
                status_code=413,
            )
        return await call_next(request)


app.add_middleware(_MaxUploadSizeMiddleware)

# ── API key auth ──────────────────────────────────────────────────────────

SKIP_AUTH = {"/", "/api/v1/health", "/api/v1/calc-types", "/api/v1/potcar/status",
             "/api/v1/potcar/functionals"}


class _APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not VASP_API_KEY:
            return await call_next(request)

        path = request.url.path

        # Non-API paths → allow (frontend static files)
        if not path.startswith("/api/"):
            return await call_next(request)

        # Whitelisted API paths (read-only info, no resource consumption)
        if path in SKIP_AUTH:
            return await call_next(request)

        api_key = request.headers.get("X-API-Key", "")
        if not secrets.compare_digest(api_key, VASP_API_KEY):
            return JSONResponse(
                {"detail": {"error": "缺少或无效的 API Key", "suggestion": "在页面弹窗中输入有效的 API Key"}},
                status_code=401,
            )
        return await call_next(request)


app.add_middleware(_APIKeyMiddleware)

# ── Routes ────────────────────────────────────────────────────────────────

app.include_router(router, prefix="/api/v1")

frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"


@app.get("/")
async def serve_index():
    return FileResponse(frontend_dir / "index.html")


@app.get("/{filename:path}")
async def serve_static(filename: str):
    filepath = frontend_dir / filename
    if filepath.is_file() and filepath.suffix in (".js", ".css", ".html", ".svg", ".png", ".ico"):
        return FileResponse(filepath)
    return FileResponse(frontend_dir / "index.html")
