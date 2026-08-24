"""
Nexus Ops — multi-tool automation command center.
Run:  python -m web_console.app
   or CHAY_WEB.bat
"""

from __future__ import annotations

import asyncio
import json
import sys
import webbrowser
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_console import __version__
from web_console.job_manager import JobManager
from web_console.plugins import all_plugins, get_plugin

STATIC = Path(__file__).resolve().parent / "static"
TEMPLATES = Path(__file__).resolve().parent / "templates"

app = FastAPI(title="Nexus Ops", version=__version__)
jobs = JobManager(ROOT)

if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


class StartBody(BaseModel):
    tool_id: str = "grok"
    params: dict[str, Any] = Field(default_factory=dict)


class StopBody(BaseModel):
    job_id: Optional[str] = None


class Sub2ConfigBody(BaseModel):
    enabled: bool = True
    mode: str = "auto"
    url: str = ""
    group: str = "grok free"
    name_prefix: str = "grok free"
    user: str = ""
    password: Optional[str] = None
    api_token: Optional[str] = None


class GoogleSheetsConfigBody(BaseModel):
    enabled: bool = False
    spreadsheet_id: str = ""
    webapp_url: Optional[str] = None


class ConfigUpdateBody(BaseModel):
    sub2api: Sub2ConfigBody
    google_sheets: GoogleSheetsConfigBody
    force_guest_on_start: bool = True
    open_grok_after_success: bool = True
    fixed_password: Optional[str] = None


class HotmailImportBody(BaseModel):
    text: str = ""
    mode: str = "append"  # append | replace


def resolve_brand_icon(tool_id: str, explicit: str = "") -> str:
    """Official publisher icon. Drop brands/{id}.svg|png|webp — future tools inherit."""
    if explicit:
        return str(explicit)
    brands = STATIC / "img" / "brands"
    for ext in (".svg", ".png", ".webp"):
        if (brands / f"{tool_id}{ext}").is_file():
            return f"/static/img/brands/{tool_id}{ext}"
    return ""


def _tool_public(p) -> dict[str, Any]:
    m = p.meta
    return {
        "id": m.id,
        "name": m.name,
        "description": m.description,
        "icon": m.icon,
        "brand_icon": resolve_brand_icon(m.id, getattr(m, "brand_icon", "") or ""),
        "status": m.status,
        "color": m.color,
        "fields": [
            {
                "key": f.key,
                "label": f.label,
                "type": f.type,
                "default": f.default,
                "hint": f.hint,
                "min": f.min,
                "max": f.max,
                "options": [
                    {"value": o.value, "label": o.label, "hint": o.hint}
                    for o in (f.options or [])
                ],
            }
            for f in (m.fields or [])
        ],
    }


@app.get("/", response_class=HTMLResponse)
def index():
    html = TEMPLATES / "index.html"
    if not html.exists():
        return HTMLResponse("<h1>Missing templates/index.html</h1>", status_code=500)
    return HTMLResponse(html.read_text(encoding="utf-8"))


@app.get("/api/health")
def health():
    return {"ok": True, "version": __version__, "root": str(ROOT)}


@app.get("/api/tools")
def list_tools():
    return {"tools": [_tool_public(p) for p in all_plugins().values()]}


@app.get("/api/tools/{tool_id}")
def tool_detail(tool_id: str):
    try:
        p = get_plugin(tool_id)
    except KeyError:
        raise HTTPException(404, "tool not found")
    return _tool_public(p)


@app.get("/api/tools/{tool_id}/stats")
def tool_stats(tool_id: str):
    try:
        p = get_plugin(tool_id)
    except KeyError:
        raise HTTPException(404, "tool not found")
    return p.stats(ROOT)


@app.get("/api/tools/{tool_id}/results")
def tool_results(tool_id: str, limit: int = Query(100, ge=1, le=2000)):
    try:
        p = get_plugin(tool_id)
    except KeyError:
        raise HTTPException(404, "tool not found")
    return {"results": p.parse_results(ROOT, limit=limit)}


@app.get("/api/tools/{tool_id}/hotmails")
def tool_hotmails(tool_id: str):
    try:
        p = get_plugin(tool_id)
    except KeyError:
        raise HTTPException(404, "tool not found")
    fn = getattr(p, "hotmail_pool", None)
    if not callable(fn):
        raise HTTPException(404, "tool không hỗ trợ Hotmail pool")
    return fn(ROOT)


@app.post("/api/tools/{tool_id}/hotmails")
def tool_hotmails_import(tool_id: str, body: HotmailImportBody):
    try:
        p = get_plugin(tool_id)
    except KeyError:
        raise HTTPException(404, "tool not found")
    fn = getattr(p, "import_hotmails", None)
    if not callable(fn):
        raise HTTPException(404, "tool không hỗ trợ nhập Hotmail")
    try:
        return fn(ROOT, body.text or "", body.mode or "append")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/api/jobs")
def list_jobs():
    return {"jobs": jobs.list_jobs(), "current": (jobs.current().snapshot() if jobs.current() else None)}


@app.get("/api/jobs/current")
def current_job(tool_id: Optional[str] = None, log_from: int = 0):
    if tool_id:
        j = jobs.get_latest_for_tool(tool_id)
        if j:
            return j.snapshot(log_from=log_from)
        return {"status": "idle", "tool_id": tool_id, "logs": [], "running": False}
    j = jobs.current()
    if not j:
        allj = jobs.list_jobs(1)
        if allj:
            last = jobs.get(allj[0]["id"])
            if last:
                return last.snapshot(log_from=log_from)
        return {"status": "idle", "logs": [], "running": False}
    return j.snapshot(log_from=log_from)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, log_from: int = 0):
    j = jobs.get(job_id)
    if not j:
        raise HTTPException(404, "job not found")
    return j.snapshot(log_from=log_from)


@app.post("/api/jobs/start")
def start_job(body: StartBody):
    try:
        job = jobs.start(body.tool_id, body.params)
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "job": job.snapshot()}


@app.post("/api/jobs/stop")
def stop_job(body: StopBody = StopBody()):
    return jobs.stop(body.job_id)


@app.delete("/api/jobs/{job_id}/logs")
def clear_job_logs(job_id: str):
    try:
        job, removed = jobs.clear_logs(job_id)
    except KeyError as e:
        raise HTTPException(404, "job not found") from e
    return {"ok": True, "removed": removed, "job": job.snapshot()}


@app.delete("/api/tools/{tool_id}/logs")
def clear_tool_logs(tool_id: str):
    removed = jobs.clear_tool_logs(tool_id)
    latest = jobs.get_latest_for_tool(tool_id)
    return {"ok": True, "removed": removed, "tool_id": tool_id, "job": (latest.snapshot() if latest else None)}


@app.get("/api/logs/stream")
async def log_stream(tool_id: Optional[str] = None):
    """SSE stream of job logs (optionally filtered by tool_id)."""

    async def gen():
        last_seq = 0
        last_status = ""
        while True:
            j = jobs.get_latest_for_tool(tool_id) if tool_id else jobs.current()
            if j is None:
                if not tool_id:
                    allj = jobs.list_jobs(1)
                    if allj:
                        j = jobs.get(allj[0]["id"])
            if j:
                cur_seq = j._log_seq
                cur_status = j.status
                if cur_seq != last_seq or cur_status != last_status:
                    last_seq = cur_seq
                    last_status = cur_status
                    payload = j.snapshot()
                    yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(0.8)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/config/summary")
def get_config_summary():
    from grokreg.core.config import load_config

    cfg = load_config()
    return {
        "sub2api": {
            "enabled": cfg.get("enable_sub2api", True),
            "mode": cfg.get("sub2api_mode", "auto"),
            "url": cfg.get("sub2api_url", ""),
            "group": cfg.get("sub2api_group", "grok free"),
            "name_prefix": cfg.get("sub2api_name_prefix", "grok free"),
            "user": cfg.get("sub2api_user", ""),
            "has_password": bool(cfg.get("sub2api_password")),
            "has_token": bool(cfg.get("sub2api_token")),
        },
        "google_sheets": {
            "enabled": cfg.get("enable_google_sheets", False),
            "spreadsheet_id": cfg.get("google_sheets_spreadsheet_id", ""),
            "has_webapp": bool(cfg.get("google_sheets_webapp_url")),
        },
        "force_guest_on_start": cfg.get("force_guest_on_start", True),
        "open_grok_after_success": cfg.get("open_grok_after_success", True),
        "fixed_password": cfg.get("fixed_password"),
    }


@app.put("/api/config")
def update_config_api(body: ConfigUpdateBody):
    from grokreg.core.config import load_config, save_config

    cfg = load_config()
    cfg["enable_sub2api"] = body.sub2api.enabled
    cfg["sub2api_mode"] = body.sub2api.mode
    cfg["sub2api_url"] = body.sub2api.url
    cfg["sub2api_group"] = body.sub2api.group
    cfg["sub2api_name_prefix"] = body.sub2api.name_prefix
    cfg["sub2api_user"] = body.sub2api.user
    if body.sub2api.password is not None:
        cfg["sub2api_password"] = body.sub2api.password
    if body.sub2api.api_token is not None:
        cfg["sub2api_token"] = body.sub2api.api_token

    cfg["enable_google_sheets"] = body.google_sheets.enabled
    cfg["google_sheets_spreadsheet_id"] = body.google_sheets.spreadsheet_id
    if body.google_sheets.webapp_url is not None:
        cfg["google_sheets_webapp_url"] = body.google_sheets.webapp_url

    cfg["force_guest_on_start"] = body.force_guest_on_start
    cfg["open_grok_after_success"] = body.open_grok_after_success
    cfg["fixed_password"] = body.fixed_password

    save_config(cfg)
    return {"ok": True, "message": "Đã lưu cấu hình"}


def main():
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="Nexus Ops Web Console")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}"
    print(f"=== Nexus Ops Console v{__version__} ===")
    print(f"Server: {url}")
    print(f"Root:   {ROOT}")

    if not args.no_browser:

        def _open():
            import time

            time.sleep(1.0)
            webbrowser.open(url)

        import threading

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
