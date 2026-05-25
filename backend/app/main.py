from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from app.api.routes import router

app = FastAPI(
    title="VASP Agent",
    description="Automated VASP input file generation and calculation management",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
