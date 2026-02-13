import json
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from functools import lru_cache


# 로컬 저장 위치(데스크탑 우선)를 관리하는 모듈

CONFIG_FILE_NAME = ".automatic_tool_config.json"


@lru_cache(maxsize=1)
def _dotenv_values() -> dict[str, str]:
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key:
                values[key] = value
    except Exception:
        return {}
    return values


def _get_env(name: str) -> str | None:
    env_val = os.environ.get(name)
    if env_val:
        return env_val
    dotenv_val = _dotenv_values().get(name)
    return dotenv_val if dotenv_val else None


def _config_file_path() -> Path:
    env_path = _get_env("AUTOMATIC_TOOL_CONFIG")
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

    env_storage = _get_env("AUTOMATIC_TOOL_STORAGE_DIR")
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
    # 1) 내부 고정 별칭 파일 우선(dictionary_latest.*, ko_latest.* ...)
    matches = sorted(storage_dir.glob(f"{alias_name}.*"))
    if matches:
        return matches[-1]

    # 2) 폴더 내 일반 파일명도 자동 탐색(사용자가 폴더만 지정해도 자동 재사용)
    fallback_patterns: dict[str, list[str]] = {
        "dictionary_latest": ["dictionary*.xlsx", "dictionary*.csv", "dictionary*.tsv", "*.xlsx", "*.csv", "*.tsv"],
        "ko_latest": ["ko.json", "ko*.json"],
        "ru_latest": ["ru.json", "ru*.json"],
        "en_latest": ["en.json", "en*.json"],
    }

    patterns = fallback_patterns.get(alias_name, [])
    fallback_candidates: list[Path] = []
    for pattern in patterns:
        fallback_candidates.extend([p for p in storage_dir.glob(pattern) if p.is_file()])

    if not fallback_candidates:
        return None

    # 최근 수정 파일을 우선 사용
    fallback_candidates.sort(key=lambda p: p.stat().st_mtime)
    return fallback_candidates[-1]


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
