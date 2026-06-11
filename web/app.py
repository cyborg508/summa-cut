"""Punkt wejścia ASGI dla uvicorna: `uvicorn web.app:app`.

Domyślny magazyn sesji w katalogu tymczasowym; nasłuch tylko lokalny/sieciowy
(bez publicznego wystawienia) konfigurujemy na poziomie kontenera w Fazie 4."""
from __future__ import annotations

import tempfile
from pathlib import Path

from web.server import create_app
from web.sessions import SessionStore

_BASE = Path(tempfile.gettempdir()) / "summa-cut-web"
app = create_app(store=SessionStore(base_dir=_BASE))
