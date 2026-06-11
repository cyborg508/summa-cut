from __future__ import annotations

import secrets
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from summa_cut.pdf_io import PdfInfo, PdfReadError, read_pdf_info


@dataclass
class Session:
    id: str
    workdir: Path
    created: float
    last_seen: float
    uploads: dict[str, PdfInfo] = field(default_factory=dict)
    job_params: dict | None = None


class SessionStore:
    """Sesje w pamięci + katalog roboczy na dysku. Bez bazy danych.

    Każda sesja ma własny katalog `base_dir/<id>` na wgrane PDF-y i wyniki.
    `sweep()` usuwa sesje starsze niż TTL wraz z katalogiem."""

    def __init__(self, base_dir: str | Path, ttl_seconds: int = 6 * 3600) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, Session] = {}

    def create(self) -> Session:
        sid = secrets.token_urlsafe(16)
        workdir = self.base_dir / sid
        workdir.mkdir(parents=True, exist_ok=True)
        now = time.time()
        session = Session(id=sid, workdir=workdir, created=now, last_seen=now)
        self._sessions[sid] = session
        return session

    def get(self, sid: str | None) -> Session | None:
        if not sid:
            return None
        session = self._sessions.get(sid)
        if session is None:
            return None
        session.last_seen = time.time()
        return session

    def save_upload(self, session: Session, filename: str, data: bytes) -> PdfInfo:
        safe_name = Path(filename).name or "plik.pdf"
        target = session.workdir / safe_name
        target.write_bytes(data)
        try:
            info = read_pdf_info(str(target))
        except PdfReadError as exc:
            target.unlink(missing_ok=True)
            raise ValueError(str(exc)) from exc
        info.name = safe_name
        session.uploads[safe_name] = info
        return info

    def sweep(self) -> None:
        cutoff = time.time() - self.ttl_seconds
        for sid in list(self._sessions):
            session = self._sessions[sid]
            if session.last_seen <= cutoff:
                shutil.rmtree(session.workdir, ignore_errors=True)
                del self._sessions[sid]
