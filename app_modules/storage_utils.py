import json
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path


# 로컬 저장 위치(데스크탑 우선)를 관리하는 모듈

CONFIG_FILE_NAME = ".automatic_tool_config.json"


def _config_file_path() -> Path:
    env_path = os.environ.get("AUTOMATIC_TOOL_CONFIG")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return Path.cwd() / CONFIG_FILE_NAME


def _load_config() -> dict:
    path = _config_file_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_config(payload: dict):
    path = _config_file_path()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def set_storage_dir(path_text: str | None) -> Path:
    if not path_text:
        return resolve_storage_dir()
    target = Path(path_text).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    cfg = _load_config()
    cfg["storage_dir"] = str(target)
    _save_config(cfg)
    return target


def resolve_storage_dir(preferred: str | Path | None = None) -> Path:
    if preferred:
        target = Path(preferred).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        return target

    env_storage = os.environ.get("AUTOMATIC_TOOL_STORAGE_DIR")
    if env_storage:
        target = Path(env_storage).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        return target

    cfg = _load_config()
    cfg_storage = cfg.get("storage_dir")
    if cfg_storage:
        target = Path(cfg_storage).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        return target

    home = Path.home()
    candidates = [
        home / "Desktop" / "automatic_tool_storage",
    ]
    for candidate in candidates:
        if candidate.parent.exists():
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate

    fallback = home / "automatic_tool_storage"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def export_dir_path(storage_dir: str | Path | None = None) -> Path:
    folder = resolve_storage_dir(storage_dir) / "exports"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def save_uploaded_file(uploaded_file, alias_name: str, storage_dir: str | Path | None = None):
    if uploaded_file is None:
        return
    storage_dir = resolve_storage_dir(storage_dir)
    ext = Path(uploaded_file.name).suffix
    target_path = storage_dir / f"{alias_name}{ext}"
    target_path.write_bytes(uploaded_file.getvalue())


def get_saved_file_path(alias_name: str, storage_dir: str | Path | None = None):
    storage_dir = resolve_storage_dir(storage_dir)
    matches = sorted(storage_dir.glob(f"{alias_name}.*"))
    if not matches:
        return None
    return matches[-1]


def current_timestamp_text() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# 내보내기 버전을 1.0부터 0.1씩 증가시키는 상태 파일 관리

def _version_state_path(storage_dir: str | Path | None = None) -> Path:
    return resolve_storage_dir(storage_dir) / "export_version.json"


def reserve_next_version(storage_dir: str | Path | None = None) -> str:
    state_path = _version_state_path(storage_dir)
    current = Decimal("0.9")

    if state_path.exists():
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            current = Decimal(str(payload.get("current", "0.9")))
        except Exception:
            current = Decimal("0.9")

    next_version = (current + Decimal("0.1")).quantize(Decimal("0.0"))
    state_path.write_text(json.dumps({"current": str(next_version)}, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(next_version)
