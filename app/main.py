"""FastAPI 應用：REST API（所有寫入操作）＋ WebSocket（推送角色視圖快照）。

啟動：python -m app.main
"""
from __future__ import annotations

import asyncio
import os
import secrets
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.activity import Activity, ActivityError, Identity
from app.guided_notes import GuidedNotesError, fill_answers
from app.reporting import results_csv, view_for
from app.sheets_url import SheetsUrlError, download_xlsx

STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class LoginBody(BaseModel):
    passcode: str = ""


class JoinBody(BaseModel):
    name: str = ""
    group: int = 0


class UrlBody(BaseModel):
    url: str = ""


class SettingsBody(BaseModel):
    group_count: int | None = None
    fair_mode: bool | None = None
    fair_delay: int | None = None
    time_limit: int | None = None


class MarkBody(BaseModel):
    number: int
    mark: str | None = None  # "correct"、"wrong" 或 null（取消標記）


class SubmitBody(BaseModel):
    number: int
    answers: list[str]


class Hub:
    """管理所有 WebSocket 連線；狀態改變時對每條連線推送該身分可見的快照。"""

    def __init__(self, activity: Activity):
        self.activity = activity
        self.connections: dict[WebSocket, str] = {}

    async def send_snapshot(self, ws: WebSocket, token: str) -> None:
        identity = self.activity.identity(token)
        if identity is not None:
            await ws.send_json({"type": "state", "state": view_for(self.activity, identity)})

    async def broadcast(self) -> None:
        for ws, token in list(self.connections.items()):
            try:
                await self.send_snapshot(ws, token)
            except Exception:  # 連線已斷，移除即可；前端會自動重連
                self.connections.pop(ws, None)


def generate_passcode() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def create_app(passcode: str | None = None, fetch: Callable[[str], bytes] | None = None) -> FastAPI:
    activity = Activity(teacher_passcode=passcode or os.environ.get("TEACHER_PASSCODE") or generate_passcode())
    hub = Hub(activity)
    timers: set[asyncio.Task] = set()  # 保留倒數工作的參照，避免被回收
    app = FastAPI(title="課堂搶答系統")
    app.state.activity = activity
    app.state.hub = hub

    @app.exception_handler(ActivityError)
    async def activity_error(_request: Request, exc: ActivityError):
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    @app.exception_handler(GuidedNotesError)
    @app.exception_handler(SheetsUrlError)
    async def input_error(_request: Request, exc: ValueError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    # ---------- 身分相依 ----------

    def current_identity(request: Request) -> Identity:
        header = request.headers.get("authorization", "")
        token = header[7:] if header.lower().startswith("bearer ") else request.query_params.get("token")
        identity = activity.identity(token)
        if identity is None:
            raise ActivityError("請先登入", 401)
        return identity

    def require_teacher(identity: Identity = Depends(current_identity)) -> Identity:
        if identity.role != "teacher":
            raise ActivityError("權限不足：只有老師可以執行此操作", 403)
        return identity

    def require_student(identity: Identity = Depends(current_identity)) -> Identity:
        if identity.role != "student":
            raise ActivityError("權限不足：只有學生可以送出答案", 403)
        return identity

    def ok() -> dict:
        return {"ok": True, "version": activity.version}

    # ---------- 頁面 ----------

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/teacher", include_in_schema=False)
    async def teacher_page():
        return FileResponse(STATIC_DIR / "teacher.html")

    @app.get("/student", include_in_schema=False)
    async def student_page():
        return FileResponse(STATIC_DIR / "student.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # ---------- 身分 ----------

    @app.post("/api/teacher/login")
    async def teacher_login(body: LoginBody):
        identity = activity.login_teacher(body.passcode)
        return {"token": identity.token, "role": identity.role}

    @app.post("/api/student/join")
    async def student_join(body: JoinBody):
        identity = activity.join_student(body.name, body.group)
        await hub.broadcast()  # 讓老師看到新成員
        return {"token": identity.token, "role": identity.role}

    @app.get("/api/me")
    async def me(identity: Identity = Depends(current_identity)):
        return {"role": identity.role, "name": identity.name, "group": identity.group}

    @app.get("/api/groups")
    async def groups():
        return {"groups": list(range(1, activity.group_count + 1))}

    @app.get("/api/state")
    async def state(identity: Identity = Depends(current_identity)):
        return view_for(activity, identity)

    # ---------- 老師 ----------

    @app.post("/api/teacher/import/file")
    async def import_file(file: UploadFile = File(...), _t: Identity = Depends(require_teacher)):
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise ActivityError("檔案太大（超過 20 MB）")
        activity.import_notes(data, file.filename or "guided-notes.xlsx")
        await hub.broadcast()
        return {**ok(), "question_count": len(activity.questions)}

    @app.post("/api/teacher/import/url")
    async def import_url(body: UrlBody, _t: Identity = Depends(require_teacher)):
        if fetch is None:
            data = await run_in_threadpool(download_xlsx, body.url)
        else:
            data = await run_in_threadpool(download_xlsx, body.url, fetch)
        activity.import_notes(data, "google-sheets.xlsx")
        await hub.broadcast()
        return {**ok(), "question_count": len(activity.questions)}

    @app.post("/api/teacher/settings")
    async def settings(body: SettingsBody, _t: Identity = Depends(require_teacher)):
        activity.update_settings(body.group_count, body.fair_mode, body.fair_delay, body.time_limit)
        await hub.broadcast()
        return ok()

    @app.post("/api/teacher/open")
    async def open_buzzer(_t: Identity = Depends(require_teacher)):
        round_id = activity.open()
        if activity.time_limit:
            # 倒數計時：時間到由伺服器自動結束；回合不同（已手動結束或重設）就不做事
            task = asyncio.create_task(expire_later(round_id, activity.time_limit))
            timers.add(task)
            task.add_done_callback(timers.discard)
        await hub.broadcast()
        return ok()

    async def expire_later(round_id: int, seconds: float) -> None:
        await asyncio.sleep(seconds)
        while activity.remaining_seconds():  # 時鐘誤差保險：還沒到就再等一下
            await asyncio.sleep(activity.remaining_seconds())
        if activity.expire(round_id):
            await hub.broadcast()

    @app.post("/api/teacher/mark")
    async def mark(body: MarkBody, _t: Identity = Depends(require_teacher)):
        activity.mark(body.number, body.mark)
        await hub.broadcast()
        return ok()

    @app.post("/api/teacher/close")
    async def close_buzzer(_t: Identity = Depends(require_teacher)):
        activity.close()
        await hub.broadcast()
        return ok()

    @app.post("/api/teacher/reset")
    async def reset(_t: Identity = Depends(require_teacher)):
        activity.reset()
        await hub.broadcast()
        return ok()

    def attachment(suffix: str, ascii_suffix: str, ext: str) -> dict:
        """中文檔名放 filename*，另給一個純英文的備用檔名，避免舊瀏覽器亂碼。"""
        stem = Path(activity.source_name or "guided-notes").stem
        ascii_stem = "".join(c for c in stem if c.isascii() and (c.isalnum() or c in "-_")) or "guided-notes"
        name = f"{stem}-{suffix}.{ext}"
        return {"Content-Disposition":
                f"attachment; filename=\"{ascii_stem}-{ascii_suffix}.{ext}\"; filename*=UTF-8''{quote(name)}"}

    @app.get("/api/teacher/export/guided-notes")
    async def export_notes(_t: Identity = Depends(require_teacher)):
        if activity.source_bytes is None:
            raise ActivityError("尚未匯入題目", 409)
        data = fill_answers(activity.source_bytes, activity.export_answers())
        return Response(
            data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=attachment("搶答答案", "answers", "xlsx"),
        )

    @app.get("/api/teacher/export/csv")
    async def export_csv(_t: Identity = Depends(require_teacher)):
        if not activity.questions:
            raise ActivityError("尚未匯入題目", 409)
        return Response(results_csv(activity).encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers=attachment("搶答結果", "results", "csv"))

    # ---------- 學生 ----------

    @app.post("/api/student/submit")
    async def submit(body: SubmitBody, student: Identity = Depends(require_student)):
        before = activity.version
        try:
            activity.submit(student, body.number, body.answers)
        except ActivityError:
            if activity.version != before:  # 送出時剛好時間到而自動結束，也要同步所有畫面
                await hub.broadcast()
            raise
        await hub.broadcast()
        return ok()

    # ---------- 即時推送 ----------

    @app.websocket("/ws")
    async def websocket(ws: WebSocket, token: str = ""):
        if activity.identity(token) is None:
            await ws.close(code=4401)
            return
        await ws.accept()
        hub.connections[ws] = token
        try:
            await hub.send_snapshot(ws, token)
            while True:
                await ws.receive_text()  # 前端只送心跳，內容不處理
        except WebSocketDisconnect:
            pass
        finally:
            hub.connections.pop(ws, None)

    return app


def main() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    passcode = os.environ.get("TEACHER_PASSCODE") or generate_passcode()
    app = create_app(passcode)
    print("=" * 52)
    print(f"  課堂搶答系統已啟動：http://127.0.0.1:{port}")
    print(f"  老師通行碼：{passcode}")
    print("  （可用環境變數 TEACHER_PASSCODE 自訂；請勿寫進 repo）")
    print("=" * 52, flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
