import json
from pathlib import Path

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.json"
DEFAULT_SETTINGS = {
    "sheet_width_mm": 330.0,
    "sheet_height_mm": 480.0,
    "item_width_mm": 0.0,
    "item_height_mm": 0.0,
    "gap_enabled": True,
    "gap_mm": 3.0,
    "rotation_allowed": True,
    "split_horizontal_groups": False,
    "split_max_spread": False,
    "manual_grid_enabled": False,
    "manual_columns": 1,
    "manual_rows": 1,
    "last_output_dir": str(Path.home()),
}


def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return DEFAULT_SETTINGS.copy()
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_SETTINGS.copy()
    result = DEFAULT_SETTINGS.copy()
    result.update(data)
    return result


def save_settings(settings: dict) -> None:
    SETTINGS_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
