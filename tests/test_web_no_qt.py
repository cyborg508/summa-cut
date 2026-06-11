"""Strażnik chudego obrazu: web.app musi się importować BEZ PySide6.

W kontenerze nie instalujemy Qt. Test symuluje to, blokując import PySide6
w podprocesie i importując web.app — jeśli cokolwiek w ścieżce web → rdzeń
sięgnie po Qt, import padnie."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_web_app_imports_without_pyside6():
    code = (
        "import sys;"
        "sys.modules['PySide6'] = None;"   # każdy `import PySide6` → ImportError
        "import web.app;"
        "print('OK')"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 0, f"web.app nie zaimportował się bez PySide6:\n{r.stderr}"
    assert "OK" in r.stdout


def test_special_trim_imports_and_runs_without_pyside6():
    """Rdzeń trybu specjalnego (Shapely) nie może sięgać po Qt — działa w kontenerze."""
    code = (
        "import sys;"
        "sys.modules['PySide6'] = None;"   # każdy `import PySide6` → ImportError
        "import summa_cut.special_trim as st;"
        "assert hasattr(st, 'prepare_special_trim');"
        "print('OK')"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 0, f"special_trim nie zaimportował się bez PySide6:\n{r.stderr}"
    assert "OK" in r.stdout


def test_special_trim_source_has_no_qt_imports():
    """Źródło special_trim.py nie odwołuje się do PySide6/PyQt (poza komentarzem)."""
    src = (REPO / "summa_cut" / "special_trim.py").read_text(encoding="utf-8")
    assert "import PySide6" not in src and "import PyQt" not in src
    assert "from PySide6" not in src and "from PyQt" not in src
