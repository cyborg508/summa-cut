from __future__ import annotations

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import Response as RawResponse

from summa_cut.layout import compute_layout
from web.job_builder import JobParams, build_job
from web.preview_render import render_output_png
from web.sessions import Session, SessionStore


def create_app(store: SessionStore) -> FastAPI:
    app = FastAPI(title="summa-cut web")
    app.state.store = store

    def current_session(request: Request) -> Session:
        session = store.get(request.cookies.get("sid"))
        if session is None:
            raise HTTPException(status_code=401, detail="Brak aktywnej sesji.")
        return session

    @app.post("/api/session")
    def create_session(response: Response) -> dict:
        session = store.create()
        response.set_cookie("sid", session.id, httponly=True, samesite="lax")
        return {"session_id": session.id}

    @app.post("/api/upload")
    async def upload(session: Session = Depends(current_session), file: UploadFile = File(...)) -> dict:
        data = await file.read()
        try:
            info = store.save_upload(session, file.filename or "plik.pdf", data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {
            "name": info.name,
            "page_count": info.page_count,
            "page_sizes_mm": info.page_sizes_mm,
            "page_content_sizes_mm": info.page_content_sizes_mm,
        }

    return app
