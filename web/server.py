from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.responses import Response as RawResponse

from summa_cut.export import generate_output_docs, save_output_docs
from summa_cut.layout import compute_layout
from web.job_builder import JobParams, build_job
from web.preview_render import render_output_png
from web.sessions import Session, SessionStore


class GenerateParams(BaseModel):
    base_name: str = "wynik"


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

    @app.post("/api/job")
    def set_job(params: JobParams, session: Session = Depends(current_session)) -> dict:
        try:
            job = build_job(params, session)
            layout = compute_layout(job)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        session.job_params = params.model_dump()
        return {
            "count": layout.count,
            "capacity_count": layout.capacity_count,
            "requested_count": layout.requested_count,
            "rows": layout.rows,
            "columns": layout.columns,
            "used_rotation": layout.used_rotation,
        }

    def _job_and_layout(session: Session):
        if session.job_params is None:
            raise HTTPException(status_code=400, detail="Najpierw ustaw zlecenie (/api/job).")
        clean = {k: v for k, v in session.job_params.items() if not k.startswith("_")}
        job = build_job(JobParams(**clean), session)
        return job, compute_layout(job)

    @app.get("/api/preview/{which}.png")
    def preview(which: str, session: Session = Depends(current_session)) -> RawResponse:
        if which not in ("print", "cut"):
            raise HTTPException(status_code=404, detail="Nieznany podgląd.")
        job, layout = _job_and_layout(session)
        png = render_output_png(job, layout, which=which, max_px=900)
        return RawResponse(content=png, media_type="image/png")

    @app.post("/api/generate")
    def generate(body: GenerateParams, session: Session = Depends(current_session)) -> dict:
        job, layout = _job_and_layout(session)
        docs = generate_output_docs(job, layout)
        try:
            print_path, cut_path = save_output_docs(docs, session.workdir, base_name=body.base_name)
        finally:
            docs.print_doc.close()
            docs.cut_doc.close()
        session.job_params["_print_name"] = print_path.name
        session.job_params["_cut_name"] = cut_path.name
        return {"print_name": print_path.name, "cut_name": cut_path.name}

    @app.get("/api/download/{which}")
    def download(which: str, session: Session = Depends(current_session)) -> FileResponse:
        if which not in ("print", "cut"):
            raise HTTPException(status_code=404, detail="Nieznany plik.")
        key = "_print_name" if which == "print" else "_cut_name"
        name = (session.job_params or {}).get(key)
        if not name:
            raise HTTPException(status_code=404, detail="Najpierw wygeneruj wynik (/api/generate).")
        path = Path(session.workdir) / name
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Plik wyniku nie istnieje.")
        return FileResponse(path, media_type="application/pdf", filename=name)

    return app
