import base64
import json
from io import BytesIO
from pathlib import Path
from datetime import datetime

import pandas as pd

from app_modules.matching_utils import guess_column, recompute_match_columns, unique_join
from app_modules.text_utils import canonical_key, normalize_text


def decode_upload_content(content: str | None) -> bytes | None:
    if not content:
        return None
    _, encoded = content.split(",", 1)
    return base64.b64decode(encoded)


def read_uploaded_table(content: str | None, filename: str | None):
    raw = decode_upload_content(content)
    if raw is None or not filename:
        return None
    name = filename.lower()
    if name.endswith(".xlsx"):
        return pd.read_excel(BytesIO(raw), dtype=str).fillna("")
    if name.endswith(".csv"):
        try:
            return pd.read_csv(BytesIO(raw), dtype=str, keep_default_na=False, encoding="utf-8-sig").fillna("")
        except Exception:
            return pd.read_csv(BytesIO(raw), dtype=str, keep_default_na=False, encoding="cp949").fillna("")
    return None


def save_upload_bytes(storage_dir: Path, alias: str, filename: str, content: str | None) -> Path | None:
    raw = decode_upload_content(content)
    if raw is None:
        return None
    ext = Path(filename).suffix if filename else ""
    # 항상 최신 고정본도 유지(저장본 자동 사용용)
    latest_target = storage_dir / f"{alias}{ext}"
    latest_target.write_bytes(raw)

    # 업로드 시마다 고유 파일로도 저장해 경로 변경을 강제(갱신 누락 방지)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    unique_target = storage_dir / f"{alias}_{ts}{ext}"
    unique_target.write_bytes(raw)
    return unique_target


def read_dictionary(source_path: Path | None):
    if source_path is None or not source_path.exists():
        return None, None
    file_name = source_path.name
    raw_bytes = source_path.read_bytes()

    if file_name.lower().endswith(".xlsx"):
        return pd.read_excel(BytesIO(raw_bytes), dtype=str), file_name

    if file_name.lower().endswith(".csv"):
        try:
            return pd.read_csv(BytesIO(raw_bytes), dtype=str, keep_default_na=False, encoding="utf-8-sig"), file_name
        except Exception:
            return pd.read_csv(BytesIO(raw_bytes), dtype=str, keep_default_na=False, encoding="cp949"), file_name

    try:
        return pd.read_csv(BytesIO(raw_bytes), sep="\t", dtype=str, keep_default_na=False, encoding="utf-8-sig"), file_name
    except Exception:
        return pd.read_csv(BytesIO(raw_bytes), sep="\t", dtype=str, keep_default_na=False, encoding="cp949"), file_name


def read_json_map(source_path: Path | None):
    if source_path is None or not source_path.exists():
        return {}
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return {normalize_text(k): normalize_text(v) for k, v in payload.items()}


def build_compare_dataframe(
    dictionary_df: pd.DataFrame,
    ko_map: dict,
    ru_map: dict,
    en_map: dict,
    include_en_keys: bool,
    module_col: str,
    english_col: str,
    korean_col: str,
    russian_col: str,
):
    # JSON 키 매칭 강화: 원본/정규화/소문자/캐노니컬 인덱스를 모두 사용
    def build_lookup_index(source_map: dict) -> dict:
        index = {}
        for raw_k, raw_v in source_map.items():
            v = normalize_text(raw_v)
            k0 = str(raw_k)
            k1 = normalize_text(raw_k)
            keys = {
                k0,
                k1,
                k0.strip(),
                k1.strip(),
                k0.lower(),
                k1.lower(),
                canonical_key(k0),
                canonical_key(k1),
            }
            keys = {x for x in keys if x}
            for kk in keys:
                if kk not in index:
                    index[kk] = v
        return index

    en_lookup = build_lookup_index(en_map)
    ko_lookup = build_lookup_index(ko_map)
    ru_lookup = build_lookup_index(ru_map)

    def get_json_value(source_map: dict, lookup: dict, key: str) -> str:
        k0 = str(key)
        k1 = normalize_text(key)
        candidates = [
            k0,
            k1,
            k0.strip(),
            k1.strip(),
            k0.lower(),
            k1.lower(),
            canonical_key(k0),
            canonical_key(k1),
        ]
        for c in candidates:
            if c in source_map:
                return normalize_text(source_map.get(c, ""))
            if c in lookup:
                return normalize_text(lookup.get(c, ""))
        return ""

    base_df = dictionary_df.copy()
    base_df[english_col] = base_df[english_col].apply(normalize_text)
    base_df[korean_col] = base_df[korean_col].apply(normalize_text)
    base_df[russian_col] = base_df[russian_col].apply(normalize_text)
    base_df[module_col] = base_df[module_col].apply(normalize_text)
    base_df = base_df[base_df[english_col] != ""].copy()

    dictionary_order = list(dict.fromkeys(base_df[english_col].tolist()))
    dictionary_key_set = set(dictionary_order)
    grouped_df = (
        base_df.groupby(english_col, dropna=False, sort=False)
        .agg({module_col: unique_join, korean_col: unique_join, russian_col: unique_join})
        .reset_index()
        .rename(
            columns={
                module_col: "Main Module",
                english_col: "Dictionary English",
                korean_col: "Dictionary Korean",
                russian_col: "Dictionary Russian",
            }
        )
    )

    ordered_keys = []
    seen = set()

    def append_order(keys):
        for key in keys:
            k = normalize_text(key)
            if k and k not in seen:
                seen.add(k)
                ordered_keys.append(k)

    append_order(dictionary_order)
    append_order(ko_map.keys())
    append_order(ru_map.keys())
    if include_en_keys:
        append_order(en_map.keys())

    fixed_seq_map = {k: i + 1 for i, k in enumerate(ordered_keys)}
    out = pd.DataFrame({"비교 Key": ordered_keys})
    out = out.merge(grouped_df, left_on="비교 Key", right_on="Dictionary English", how="left")
    out["순번"] = out["비교 Key"].map(fixed_seq_map).astype("Int64")

    if "Dictionary English" not in out.columns:
        out["Dictionary English"] = ""
    out["Dictionary English"] = out["Dictionary English"].fillna("").apply(normalize_text)

    for col_name in ["Main Module", "Dictionary Korean", "Dictionary Russian"]:
        if col_name not in out.columns:
            out[col_name] = ""
        out[col_name] = out[col_name].fillna("").apply(normalize_text)

    out["en.json"] = out["비교 Key"].apply(lambda k: get_json_value(en_map, en_lookup, k))
    out["ko.json"] = out["비교 Key"].apply(lambda k: get_json_value(ko_map, ko_lookup, k))
    out["ru.json"] = out["비교 Key"].apply(lambda k: get_json_value(ru_map, ru_lookup, k))

    def source_label(row):
        key = normalize_text(row.get("비교 Key", ""))
        if key in dictionary_key_set:
            return "양쪽"
        return "JSON만"

    out["데이터출처"] = out.apply(source_label, axis=1)
    out = recompute_match_columns(out)
    out["수정상태"] = ""
    out["수정일시"] = ""

    out["_module_norm"] = out["Main Module"].apply(normalize_text)
    out["_module_blank"] = out["_module_norm"].eq("")
    out = out.sort_values(
        by=["_module_blank", "_module_norm", "순번"],
        ascending=[True, True, True],
        kind="stable",
    ).drop(columns=["_module_norm", "_module_blank"])

    final_columns = [
        "순번",
        "비교 Key",
        "데이터출처",
        "Main Module",
        "Dictionary English",
        "Dictionary Korean",
        "Dictionary Russian",
        "en.json",
        "ko.json",
        "ru.json",
        "KO_Match",
        "EN_Match",
        "RU_Match",
        "Overall_Match",
        "수정상태",
        "수정일시",
    ]
    return out[final_columns].copy(), ordered_keys


def guess_mapping_columns(dictionary_df: pd.DataFrame):
    cols = list(dictionary_df.columns)
    return {
        "module": guess_column(dictionary_df, ["Main Module", "MainModule", "main module", "Module", "모듈", "Main"]),
        "english": guess_column(dictionary_df, ["English", "Enlish", "Englsh", "EN", "en", "영어", "영문"]),
        "korean": guess_column(dictionary_df, ["Korean", "KO", "ko", "한국어", "국문", "KOR"]),
        "russian": guess_column(dictionary_df, ["Russian", "RU", "ru", "러시아어", "러문", "RUS"]),
        "columns": cols,
    }
