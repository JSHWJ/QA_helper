from __future__ import annotations

import hashlib
import json
import math
from io import StringIO
from pathlib import Path

import pandas as pd
import streamlit as st

from app_modules.compare_logic import (
    build_compare_dataframe,
    guess_mapping_columns,
    read_dictionary,
    read_json_map,
)
from app_modules.exporters import dataframe_to_excel_bytes
from app_modules.matching_utils import recompute_match_columns
from app_modules.storage_utils import get_saved_file_path, resolve_storage_dir, set_storage_dir
from app_modules.text_utils import normalize_text


APP_TITLE = "번역 정합성 검증 도구"
MATCH_COLUMNS = ["KO_Match", "EN_Match", "RU_Match", "Overall_Match"]
CHANGE_COL_NAME = "변경컬럼"
OLD_VALUE_COL = "이전값"
NEW_VALUE_COL = "수정값"


def _to_bool_flag(v) -> bool:
    return str(v).strip().lower() in {"1", "true", "on", "yes", "y"}


def inject_table_wrap_css():
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 0.8rem !important;
            padding-bottom: 1rem !important;
        }
        header[data-testid="stHeader"] {
            display: none !important;
        }
        div[data-testid="stAppViewContainer"] {
            margin-top: 0 !important;
        }
        .app-title {
            font-size: clamp(1.4rem, 2.2vw, 2.05rem);
            line-height: 1.2;
            font-weight: 700;
            margin: 0 0 0.35rem 0;
            white-space: normal;
            overflow-wrap: anywhere;
            word-break: break-word;
        }
        h1, h2, h3 {
            letter-spacing: -0.01em;
        }
        .qa-toolbar {
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 6px 10px 0 10px;
            margin-bottom: 6px;
            background: #fafafa;
        }
        .qa-section-title {
            font-size: 0.86rem;
            font-weight: 700;
            margin: 1px 0 4px 0;
            color: #334155;
        }
        .stButton > button {
            border-radius: 10px !important;
            border: 1px solid #d1d5db !important;
            padding-top: 0.2rem !important;
            padding-bottom: 0.2rem !important;
            min-height: 2rem !important;
        }
        .pagination-row .stButton > button {
            border-radius: 8px !important;
            min-height: 1.85rem !important;
            height: 1.85rem !important;
            padding: 0 0.5rem !important;
            font-size: 0.76rem !important;
            line-height: 1 !important;
            border: 1px solid #cbd5e1 !important;
            background: #fff !important;
        }
        .pagination-row [data-testid="column"] {
            padding-left: 0.06rem !important;
            padding-right: 0.06rem !important;
        }
        .pg-current {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 1.85rem;
            min-width: 1.85rem;
            padding: 0 0.5rem;
            border-radius: 8px;
            border: 1px solid #0969da;
            background: #0969da;
            color: #fff;
            font-size: 0.76rem;
            font-weight: 600;
        }
        .pg-ellipsis {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 1.85rem;
            color: #64748b;
            font-size: 0.78rem;
        }
        .stTextInput label, .stSelectbox label, .stMultiSelect label {
            font-size: 0.78rem !important;
        }
        .stTextInput, .stSelectbox, .stMultiSelect {
            margin-bottom: 0.2rem !important;
        }
        div[data-testid="stMetric"] {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 6px 8px;
        }
        div[data-testid="stVerticalBlock"] > div:has(> div[data-testid="stDataFrame"]) {
            border-radius: 10px;
        }
        div[data-testid="stDataFrame"] [role="gridcell"] {
            white-space: pre-wrap !important;
            word-break: break-word !important;
            line-height: 1.35 !important;
            align-items: start !important;
        }
        div[data-testid="stDataFrame"] [role="columnheader"] {
            white-space: normal !important;
            line-height: 1.2 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def save_uploaded_file(uploaded, alias: str, storage_dir: Path) -> str:
    raw = uploaded.getvalue()
    ext = Path(uploaded.name).suffix
    latest = storage_dir / f"{alias}{ext}"
    latest.write_bytes(raw)
    return str(latest)


def saved_paths_dict(storage_dir: Path) -> dict[str, str]:
    return {
        "dictionary": str(get_saved_file_path("dictionary_latest", storage_dir) or ""),
        "ko": str(get_saved_file_path("ko_latest", storage_dir) or ""),
        "ru": str(get_saved_file_path("ru_latest", storage_dir) or ""),
        "en": str(get_saved_file_path("en_latest", storage_dir) or ""),
    }


def recompute_matches(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    required = [
        "Dictionary Korean",
        "Dictionary English",
        "Dictionary Russian",
        "ko.json",
        "en.json",
        "ru.json",
    ]
    for col in required:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").apply(normalize_text)
    return recompute_match_columns(df)


def compare_records_from_sources(
    source_paths: dict[str, str],
    include_en_keys: bool,
    module_col: str | None,
    english_col: str | None,
    korean_col: str | None,
    russian_col: str | None,
):
    source_paths = dict(source_paths or {})
    dictionary_path = Path(source_paths["dictionary"]) if source_paths.get("dictionary") else None
    ko_path = Path(source_paths["ko"]) if source_paths.get("ko") else None
    ru_path = Path(source_paths["ru"]) if source_paths.get("ru") else None
    en_path = Path(source_paths["en"]) if source_paths.get("en") else None

    ko_loaded = bool(ko_path and ko_path.exists())
    ru_loaded = bool(ru_path and ru_path.exists())
    en_loaded = bool(en_path and en_path.exists())

    dictionary_df, _ = read_dictionary(dictionary_path)
    if dictionary_df is None or dictionary_df.empty:
        return [], "딕셔너리 파일을 읽지 못했거나 데이터가 비어 있습니다."

    guessed = guess_mapping_columns(dictionary_df)
    module_col = module_col or guessed.get("module")
    english_col = english_col or guessed.get("english")
    korean_col = korean_col or guessed.get("korean")
    russian_col = russian_col or guessed.get("russian")

    required_cols = [module_col, english_col, korean_col, russian_col]
    if any(not c for c in required_cols):
        return [], "딕셔너리 컬럼 자동 매핑 실패. 컬럼명을 확인하세요."
    for c in required_cols:
        if c not in dictionary_df.columns:
            return [], f"선택한 컬럼이 딕셔너리에 없습니다: {c}"

    ko_map = read_json_map(ko_path)
    ru_map = read_json_map(ru_path)
    en_map = read_json_map(en_path)
    out_df, _ = build_compare_dataframe(
        dictionary_df=dictionary_df,
        ko_map=ko_map,
        ru_map=ru_map,
        en_map=en_map,
        include_en_keys=include_en_keys,
        module_col=module_col,
        english_col=english_col,
        korean_col=korean_col,
        russian_col=russian_col,
    )

    if not ko_loaded:
        out_df["ko.json"] = ""
    if not en_loaded:
        out_df["en.json"] = ""
    if not ru_loaded:
        out_df["ru.json"] = ""

    ko_has_data = out_df["ko.json"].astype(str).str.strip().ne("").any()
    en_has_data = out_df["en.json"].astype(str).str.strip().ne("").any()
    ru_has_data = out_df["ru.json"].astype(str).str.strip().ne("").any()
    if not ko_has_data:
        out_df["ko.json"] = ""
    if not en_has_data:
        out_df["en.json"] = ""
    if not ru_has_data:
        out_df["ru.json"] = ""

    out_df = recompute_matches(out_df)
    status = (
        f"비교 완료: 총 {len(out_df):,}건 | "
        f"ko.json={'로드됨' if ko_loaded else '없음'}{'(데이터없음)' if ko_loaded and not ko_has_data else ''}, "
        f"ru.json={'로드됨' if ru_loaded else '없음'}{'(데이터없음)' if ru_loaded and not ru_has_data else ''}, "
        f"en.json={'로드됨' if en_loaded else '없음'}{'(데이터없음)' if en_loaded and not en_has_data else ''}"
    )
    return out_df.to_dict("records"), status


def init_state():
    storage_dir = resolve_storage_dir()
    fullscreen_from_query = _to_bool_flag(st.query_params.get("fullscreen", "0"))
    st.session_state.setdefault("storage_dir", str(storage_dir))
    st.session_state.setdefault("storage_dir_input", str(storage_dir))
    st.session_state.setdefault("source_paths", saved_paths_dict(storage_dir))
    st.session_state.setdefault("result_records", [])
    st.session_state.setdefault("compare_status", "대기 중")
    st.session_state.setdefault("hidden_columns", [])
    st.session_state.setdefault("global_search", "")
    st.session_state.setdefault("last_upload_sig", {})
    st.session_state.setdefault("fullscreen_result", fullscreen_from_query)
    st.session_state.setdefault("show_input_in_fullscreen", False)
    st.session_state.setdefault("did_initial_autorun", False)
    st.session_state.setdefault("edit_mode", False)
    st.session_state.setdefault("pre_edit_records", [])
    st.session_state.setdefault("pending_edit_bundle", None)
    st.session_state.setdefault("focus_compare_key", "")
    st.session_state.setdefault("edited_language_marks", {})


@st.cache_data(show_spinner=False)
def dataframe_to_excel_bytes_cached(df_json: str) -> bytes:
    df = pd.read_json(StringIO(df_json), orient="split").fillna("")
    return dataframe_to_excel_bytes(df)


@st.cache_data(show_spinner=False)
def dataframe_to_csv_bytes_cached(df_json: str) -> bytes:
    df = pd.read_json(StringIO(df_json), orient="split").fillna("")
    return df.to_csv(index=False).encode("utf-8-sig")


def upload_sig(uploaded) -> str:
    if uploaded is None:
        return ""
    payload = uploaded.getvalue()
    digest = hashlib.md5(payload).hexdigest()
    return f"{uploaded.name}:{uploaded.size}:{digest}"


def apply_upload_and_reload(uploaded, alias: str, key_name: str, storage_dir: Path):
    if uploaded is None:
        return
    sig = upload_sig(uploaded)
    if st.session_state["last_upload_sig"].get(key_name) == sig:
        return
    path = save_uploaded_file(uploaded, alias, storage_dir)
    st.session_state["source_paths"][key_name] = path
    st.session_state["last_upload_sig"][key_name] = sig


def source_status_rows(source_paths: dict[str, str]) -> pd.DataFrame:
    rows = []
    label_map = {
        "dictionary": "Dictionary",
        "ko": "ko.json",
        "ru": "ru.json",
        "en": "en.json",
    }
    for key in ["dictionary", "ko", "ru", "en"]:
        p = Path(source_paths.get(key, "")) if source_paths.get(key) else None
        exists = bool(p and p.exists())
        rows.append(
            {
                "파일": label_map[key],
                "상태": "연결됨" if exists else "없음",
                "경로": str(p) if p else "",
                "파일명": p.name if p else "",
            }
        )
    return pd.DataFrame(rows)


def diff_report(baseline_df: pd.DataFrame, current_df: pd.DataFrame) -> pd.DataFrame:
    baseline_df = baseline_df.fillna("")
    current_df = current_df.fillna("")
    key_col = "비교 Key" if "비교 Key" in current_df.columns else "Dictionary English"
    baseline_key_col = "비교 Key" if "비교 Key" in baseline_df.columns else "Dictionary English"
    if key_col not in current_df.columns or baseline_key_col not in baseline_df.columns:
        return pd.DataFrame([{"오류": "기준 파일/현재 데이터에 키 컬럼(비교 Key 또는 Dictionary English)이 필요합니다."}])

    baseline_map = {
        normalize_text(r[baseline_key_col]): {k: normalize_text(v) for k, v in r.items()}
        for r in baseline_df.to_dict("records")
        if normalize_text(r.get(baseline_key_col, ""))
    }
    current_map = {
        normalize_text(r[key_col]): {k: normalize_text(v) for k, v in r.items()}
        for r in current_df.to_dict("records")
        if normalize_text(r.get(key_col, ""))
    }

    all_keys = sorted(set(baseline_map.keys()) | set(current_map.keys()))
    rows = []
    for key in all_keys:
        before = baseline_map.get(key)
        after = current_map.get(key)
        if before is None and after is not None:
            rows.append({"비교 Key": key, "변경유형": "추가", "변경컬럼": "-", "이전값": "", "현재값": "행 추가"})
            continue
        if before is not None and after is None:
            rows.append({"비교 Key": key, "변경유형": "삭제", "변경컬럼": "-", "이전값": "행 존재", "현재값": ""})
            continue
        cols = sorted(set(before.keys()) | set(after.keys()))
        for col in cols:
            if col in ["순번", "수정상태"]:
                continue
            b = normalize_text(before.get(col, ""))
            a = normalize_text(after.get(col, ""))
            if b != a:
                rows.append({"비교 Key": key, "변경유형": "변경", "변경컬럼": col, "이전값": b, "현재값": a})
    return pd.DataFrame(rows)


def style_match_highlight(df: pd.DataFrame, focus_key: str = "", edited_language_marks: dict[str, list[str]] | None = None) -> pd.io.formats.style.Styler:
    edited_language_marks = edited_language_marks or {}

    def style_row(row: pd.Series):
        styles = []
        ko_n = str(row.get("KO_Match", "")).strip() == "N"
        en_n = str(row.get("EN_Match", "")).strip() == "N"
        ru_n = str(row.get("RU_Match", "")).strip() == "N"
        row_key = normalize_text(row.get("비교 Key", ""))
        row_marks = set(edited_language_marks.get(row_key, []))
        is_focus = normalize_text(row.get("비교 Key", "")) == normalize_text(focus_key)
        for col, val in row.items():
            cell_styles = []
            if col in MATCH_COLUMNS and str(val).strip() == "N":
                cell_styles.append("background-color: #fff59d; font-weight: 700;")
            # 빨간 테두리 조건: mismatch(N) + 사용자 수정 언어
            if col in ["Dictionary Korean", "ko.json"] and "KO" in row_marks and ko_n:
                cell_styles.append("border: 1px solid red;")
            if col in ["Dictionary English", "en.json"] and "EN" in row_marks and en_n:
                cell_styles.append("border: 1px solid red;")
            if col in ["Dictionary Russian", "ru.json"] and "RU" in row_marks and ru_n:
                cell_styles.append("border: 1px solid red;")
            # 포커스 행은 가벼운 표시만 유지
            if is_focus and col == "비교 Key":
                cell_styles.append("font-weight: 700;")
            styles.append("; ".join(cell_styles))
        return styles

    return df.style.apply(style_row, axis=1)


def build_edited_language_marks(change_df: pd.DataFrame) -> dict[str, list[str]]:
    change_df = normalize_change_preview_columns(change_df)
    if change_df.empty:
        return {}
    col_to_lang = {
        "Dictionary Korean": "KO",
        "ko.json": "KO",
        "Dictionary English": "EN",
        "en.json": "EN",
        "Dictionary Russian": "RU",
        "ru.json": "RU",
    }
    marks: dict[str, set[str]] = {}
    for row in change_df.to_dict("records"):
        key = normalize_text(row.get("비교 Key", ""))
        col = normalize_text(row.get(CHANGE_COL_NAME, ""))
        lang = col_to_lang.get(col)
        if not key or not lang:
            continue
        marks.setdefault(key, set()).add(lang)
    return {k: sorted(list(v)) for k, v in marks.items()}


def apply_value_filters(df: pd.DataFrame, visible_cols: list[str]) -> pd.DataFrame:
    if df.empty:
        return df

    excluded = {"KO_Match", "EN_Match", "RU_Match", "Overall_Match"}
    candidate_cols = [c for c in visible_cols if c not in excluded]
    if not candidate_cols:
        return df

    with st.expander("추가 필터(선택)", expanded=False):
        filter_cols = st.multiselect(
            "추가 필터 열",
            options=candidate_cols,
            default=[],
            key="value_filter_cols",
            help="빠른 매치 필터(KO/EN/RU/ALL) 외에 필요한 열만 추가로 필터링합니다.",
        )
        filtered = df.copy()
        for col in filter_cols:
            options = sorted({str(v) for v in filtered[col].fillna("").tolist()})
            selected = st.multiselect(
                f"{col}",
                options=options,
                default=[],
                key=f"value_filter_{col}",
            )
            if selected:
                filtered = filtered[filtered[col].astype(str).isin(selected)]
        return filtered

def apply_seq_sort(df: pd.DataFrame, ascending: bool) -> pd.DataFrame:
    if "순번" not in df.columns:
        return df
    sorted_df = df.copy()
    seq_numeric = pd.to_numeric(sorted_df["순번"], errors="coerce")
    sorted_df["_seq_sort"] = seq_numeric
    sorted_df = sorted_df.sort_values(by=["_seq_sort"], ascending=[ascending], kind="stable").drop(columns=["_seq_sort"])
    return sorted_df


def apply_match_quick_filters(df: pd.DataFrame, ko: str, en: str, ru: str, overall: str) -> pd.DataFrame:
    filtered = df.copy()
    cond = {
        "KO_Match": ko,
        "EN_Match": en,
        "RU_Match": ru,
        "Overall_Match": overall,
    }
    for col, val in cond.items():
        if col in filtered.columns and val != "전체":
            filtered = filtered[filtered[col].astype(str) == val]
    return filtered


def get_pagination_state(total_count: int, key_prefix: str) -> tuple[int, int, int]:
    page_size = 40
    total_pages = max(1, math.ceil(total_count / page_size)) if total_count else 1
    state_key = f"{key_prefix}_page_no"
    current = int(st.session_state.get(state_key, 1))
    current = min(max(1, current), total_pages)
    st.session_state[state_key] = current
    return current, page_size, total_pages


def build_github_like_pages(total_pages: int, current: int) -> list[int | None]:
    if total_pages <= 7:
        return list(range(1, total_pages + 1))

    pages = {1, total_pages, current - 1, current, current + 1}
    pages = {p for p in pages if 1 <= p <= total_pages}
    ordered = sorted(pages)

    items: list[int | None] = []
    prev = None
    for p in ordered:
        if prev is not None and p - prev > 1:
            items.append(None)
        items.append(p)
        prev = p
    return items


def render_numeric_pagination_controls(total_count: int, current: int, total_pages: int, key_prefix: str):
    pages = build_github_like_pages(total_pages, current)
    state_key = f"{key_prefix}_page_no"
    new_page = current

    outer_l, outer_c, outer_r = st.columns([3.2, 3.6, 3.2], gap="small")
    with outer_c:
        st.markdown('<div class="pagination-row">', unsafe_allow_html=True)
        cols = st.columns(2 + len(pages), gap="small")
        with cols[0]:
            if st.button("Previous", use_container_width=True, key=f"{key_prefix}_prev", disabled=current <= 1):
                new_page = current - 1

        for idx, page_no in enumerate(pages, start=1):
            with cols[idx]:
                if page_no is None:
                    st.markdown('<div class="pg-ellipsis">...</div>', unsafe_allow_html=True)
                elif page_no == current:
                    st.markdown(f'<div class="pg-current">{page_no}</div>', unsafe_allow_html=True)
                else:
                    if st.button(str(page_no), use_container_width=True, key=f"{key_prefix}_page_{page_no}"):
                        new_page = page_no

        with cols[1 + len(pages)]:
            if st.button("Next", use_container_width=True, key=f"{key_prefix}_next", disabled=current >= total_pages):
                new_page = current + 1

    if new_page != current:
        st.session_state[state_key] = new_page
        st.rerun()

    with outer_c:
        st.caption(f"Page {current} of {total_pages} · 총 {total_count:,}건 (40건/페이지)")
        st.markdown("</div>", unsafe_allow_html=True)


def run_compare_from_saved_files(include_en_keys: bool = False):
    source_paths = st.session_state.get("source_paths", {})
    dictionary_path = Path(source_paths.get("dictionary", "")) if source_paths.get("dictionary") else None
    dictionary_df, _ = read_dictionary(dictionary_path)
    if dictionary_df is None or dictionary_df.empty:
        st.session_state["compare_status"] = "비교 실패: 딕셔너리 파일이 없거나 비어 있습니다."
        return

    mapping = guess_mapping_columns(dictionary_df)
    records, status = compare_records_from_sources(
        source_paths,
        include_en_keys=include_en_keys,
        module_col=mapping.get("module"),
        english_col=mapping.get("english"),
        korean_col=mapping.get("korean"),
        russian_col=mapping.get("russian"),
    )
    st.session_state["result_records"] = records
    st.session_state["compare_status"] = status
    st.session_state["pre_edit_records"] = []
    st.session_state["pending_edit_bundle"] = None
    st.session_state["edit_mode"] = False
    st.session_state["focus_compare_key"] = ""
    st.session_state["edited_language_marks"] = {}


def build_change_preview(before_df: pd.DataFrame, edited_df: pd.DataFrame, visible_cols: list[str]) -> pd.DataFrame:
    rows = []
    for idx in edited_df.index:
        for col in visible_cols:
            before_val = normalize_text(before_df.at[idx, col]) if col in before_df.columns else ""
            after_val = normalize_text(edited_df.at[idx, col]) if col in edited_df.columns else ""
            if before_val != after_val:
                seq_val = before_df.at[idx, "순번"] if "순번" in before_df.columns else ""
                key_val = before_df.at[idx, "비교 Key"] if "비교 Key" in before_df.columns else ""
                rows.append(
                    {
                        "순번": seq_val,
                        "비교 Key": key_val,
                        CHANGE_COL_NAME: col,
                        OLD_VALUE_COL: before_val,
                        NEW_VALUE_COL: after_val,
                    }
                )
    return pd.DataFrame(rows)


def normalize_change_preview_columns(change_df: pd.DataFrame) -> pd.DataFrame:
    if change_df is None or change_df.empty:
        return pd.DataFrame(columns=["순번", "비교 Key", CHANGE_COL_NAME, OLD_VALUE_COL, NEW_VALUE_COL])

    rename_map = {
        "변경 컬럼": CHANGE_COL_NAME,
        "이전 값": OLD_VALUE_COL,
        "현재값": NEW_VALUE_COL,
        "수정 값": NEW_VALUE_COL,
    }
    normalized = change_df.rename(columns={k: v for k, v in rename_map.items() if k in change_df.columns}).copy()
    for col in ["순번", "비교 Key", CHANGE_COL_NAME, OLD_VALUE_COL, NEW_VALUE_COL]:
        if col not in normalized.columns:
            normalized[col] = ""
    return normalized[["순번", "비교 Key", CHANGE_COL_NAME, OLD_VALUE_COL, NEW_VALUE_COL]]


def run_internal_sanity_checks_once():
    if st.session_state.get("_sanity_checked", False):
        return

    issues: list[str] = []

    legacy_change_df = pd.DataFrame([{"비교 Key": "k1", "변경 컬럼": "Dictionary Korean"}])
    marks = build_edited_language_marks(legacy_change_df)
    if marks.get("k1") != ["KO"]:
        issues.append("변경 컬럼 키 정규화 실패")

    style_df = pd.DataFrame(
        [
            {
                "비교 Key": "k1",
                "Dictionary Korean": "사전값",
                "ko.json": "json값",
                "KO_Match": "N",
                "EN_Match": "Y",
                "RU_Match": "Y",
                "Overall_Match": "N",
            }
        ]
    )
    html = style_match_highlight(style_df, edited_language_marks={"k1": ["KO"]}).to_html()
    if "#fff59d" not in html:
        issues.append("N 노란색 스타일 회귀")
    if "border: 1px solid red" not in html:
        issues.append("불일치 빨간 테두리 스타일 회귀")

    if issues:
        st.error("내부 무결성 점검 실패: " + ", ".join(issues))
    st.session_state["_sanity_checked"] = True


def mismatch_counts(df: pd.DataFrame) -> dict[str, int]:
    frame = df.fillna("")
    return {
        "KO": int((frame.get("KO_Match", pd.Series(dtype=str)).astype(str) == "N").sum()),
        "EN": int((frame.get("EN_Match", pd.Series(dtype=str)).astype(str) == "N").sum()),
        "RU": int((frame.get("RU_Match", pd.Series(dtype=str)).astype(str) == "N").sum()),
        "ALL": int((frame.get("Overall_Match", pd.Series(dtype=str)).astype(str) == "N").sum()),
    }


def render_input_panel(storage_dir: Path):
    st.subheader("입력")
    with st.container(border=True):
        st.caption("저장 위치")
        st.session_state["storage_dir_input"] = st.text_input("저장 폴더 경로", value=st.session_state["storage_dir_input"])
        i1, i2 = st.columns([1, 1])
        with i1:
            apply_storage_clicked = st.button("폴더 적용", use_container_width=True)
        with i2:
            auto_find_clicked = st.button("자동 찾기", use_container_width=True)

    if apply_storage_clicked:
        try:
            new_dir = set_storage_dir(st.session_state["storage_dir_input"])
            st.session_state["storage_dir"] = str(new_dir)
            st.session_state["storage_dir_input"] = str(new_dir)
            st.session_state["source_paths"] = saved_paths_dict(new_dir)
            st.session_state["result_records"] = []
            st.session_state["compare_status"] = f"저장 폴더 변경 완료: {new_dir}"
            st.session_state["did_initial_autorun"] = False
            st.session_state["edited_language_marks"] = {}
            st.rerun()
        except Exception as error:
            st.error(f"저장 폴더 적용 실패: {error}")
    if auto_find_clicked:
        st.session_state["source_paths"] = saved_paths_dict(storage_dir)

    with st.container(border=True):
        st.caption("업로드 및 옵션")
        include_en_keys = st.checkbox("en.json 키도 비교 대상 키에 포함", value=False)
        auto_compare = st.checkbox("업로드 즉시 자동 비교", value=True)

        dict_up = st.file_uploader("딕셔너리 업로드", type=["xlsx", "csv", "tsv", "txt"], key="up_dict")
        ko_up = st.file_uploader("ko.json 업로드", type=["json"], key="up_ko")
        ru_up = st.file_uploader("ru.json 업로드", type=["json"], key="up_ru")
        en_up = st.file_uploader("en.json 업로드(선택)", type=["json"], key="up_en")

    before = dict(st.session_state["source_paths"])
    apply_upload_and_reload(dict_up, "dictionary_latest", "dictionary", storage_dir)
    apply_upload_and_reload(ko_up, "ko_latest", "ko", storage_dir)
    apply_upload_and_reload(ru_up, "ru_latest", "ru", storage_dir)
    apply_upload_and_reload(en_up, "en_latest", "en", storage_dir)
    changed = before != st.session_state["source_paths"]

    with st.container(border=True):
        st.caption("파일 연결 상태")
        st.dataframe(source_status_rows(st.session_state["source_paths"]), use_container_width=True, height=190)

    dictionary_path = Path(st.session_state["source_paths"].get("dictionary", "")) if st.session_state["source_paths"].get("dictionary") else None
    dictionary_df, _ = read_dictionary(dictionary_path)
    module_col = english_col = korean_col = russian_col = None
    if dictionary_df is not None and not dictionary_df.empty:
        mapping = guess_mapping_columns(dictionary_df)
        cols = list(dictionary_df.columns)
        module_col = st.selectbox("Main Module 컬럼", cols, index=cols.index(mapping["module"]) if mapping["module"] in cols else 0)
        english_col = st.selectbox("English 컬럼", cols, index=cols.index(mapping["english"]) if mapping["english"] in cols else 0)
        korean_col = st.selectbox("Korean 컬럼", cols, index=cols.index(mapping["korean"]) if mapping["korean"] in cols else min(1, len(cols) - 1))
        russian_col = st.selectbox("Russian 컬럼", cols, index=cols.index(mapping["russian"]) if mapping["russian"] in cols else min(2, len(cols) - 1))

    run_now = st.button("비교 실행", type="primary", use_container_width=True)
    has_saved_dictionary = bool(st.session_state["source_paths"].get("dictionary"))
    should_initial_autorun = (
        auto_compare
        and not st.session_state["did_initial_autorun"]
        and has_saved_dictionary
        and not st.session_state["result_records"]
    )
    if should_initial_autorun:
        st.session_state["did_initial_autorun"] = True

    if (auto_compare and changed) or run_now or should_initial_autorun:
        records, status = compare_records_from_sources(
            st.session_state["source_paths"],
            include_en_keys=include_en_keys,
            module_col=module_col,
            english_col=english_col,
            korean_col=korean_col,
            russian_col=russian_col,
        )
        st.session_state["result_records"] = records
        st.session_state["compare_status"] = status
        st.session_state["pre_edit_records"] = []
        st.session_state["pending_edit_bundle"] = None
        st.session_state["edit_mode"] = False
        st.session_state["focus_compare_key"] = ""
        st.session_state["edited_language_marks"] = {}

    st.caption(f"상태: {st.session_state['compare_status']}")


def render_result_panel():
    pending = st.session_state.get("pending_edit_bundle")
    st.subheader("결과 검토" if pending else "비교 화면")
    df = pd.DataFrame(st.session_state["result_records"]).fillna("")
    if df.empty:
        st.info("비교 결과가 없습니다. 파일 업로드 후 비교를 실행하세요.")
        if st.button("저장된 파일로 비교 실행", type="primary", use_container_width=True, key="run_compare_from_saved_in_result"):
            run_compare_from_saved_files(include_en_keys=False)
            st.rerun()
        return

    if pending:
        st.markdown("#### 결과 검토")
        with st.container(border=True):
            st.caption("수정 완료 후 변경 사항을 확인하고 적용 여부를 선택하세요.")
            edited_df = pd.read_json(StringIO(pending["edited_json"]), orient="split").fillna("")
            base_df = pd.read_json(StringIO(pending["base_json"]), orient="split").fillna("")
            visible = list(pending.get("visible_cols", []))
            merged_preview = base_df.copy()
            for col in visible:
                merged_preview.loc[edited_df.index, col] = edited_df[col]
            merged_preview = recompute_matches(merged_preview.fillna(""))

            base_counts = mismatch_counts(base_df)
            new_counts = mismatch_counts(merged_preview)
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("KO 불일치", f"{new_counts['KO']:,}", delta=f"{new_counts['KO'] - base_counts['KO']:+d}")
            d2.metric("EN 불일치", f"{new_counts['EN']:,}", delta=f"{new_counts['EN'] - base_counts['EN']:+d}")
            d3.metric("RU 불일치", f"{new_counts['RU']:,}", delta=f"{new_counts['RU'] - base_counts['RU']:+d}")
            d4.metric("전체 불일치", f"{new_counts['ALL']:,}", delta=f"{new_counts['ALL'] - base_counts['ALL']:+d}")

            change_preview_df = normalize_change_preview_columns(
                pd.read_json(StringIO(pending["change_json"]), orient="split").fillna("")
            )
            st.dataframe(change_preview_df, use_container_width=True, height=360)
            p0, p1, p2, p3 = st.columns([2.4, 1, 1, 1], gap="small")
            with p0:
                st.caption(f"변경 항목 {len(change_preview_df):,}건")
            with p1:
                if st.button("수락", type="primary", use_container_width=True, key="accept_edit_btn"):
                    merged = merged_preview.copy()
                    merged["수정상태"] = merged.get("수정상태", "").astype(str)
                    merged["수정일시"] = merged.get("수정일시", "").astype(str)
                    st.session_state["result_records"] = merged.to_dict("records")
                    change_marks = build_edited_language_marks(change_preview_df)
                    existing_marks = dict(st.session_state.get("edited_language_marks", {}))
                    for k, langs in change_marks.items():
                        merged_langs = set(existing_marks.get(k, [])) | set(langs)
                        existing_marks[k] = sorted(list(merged_langs))
                    st.session_state["edited_language_marks"] = existing_marks
                    st.session_state["pending_edit_bundle"] = None
                    st.session_state["edit_mode"] = False
                    st.rerun()
            with p2:
                if st.button("이전", use_container_width=True, key="back_to_edit_btn"):
                    st.session_state["pending_edit_bundle"] = None
                    st.session_state["edit_mode"] = True
                    st.rerun()
            with p3:
                if st.button("취소", use_container_width=True, key="cancel_edit_popup_btn"):
                    st.session_state["pending_edit_bundle"] = None
                    st.session_state["edit_mode"] = False
                    st.rerun()
        return

    all_cols = list(df.columns)
    with st.container(border=True):
        st.markdown("#### 검색 조건")
        f1, f2, f3, f4, f5, f6 = st.columns([3.0, 0.9, 0.9, 0.9, 0.9, 1.0], gap="small")
        with f1:
            q = st.text_input("검색", value=st.session_state["global_search"], placeholder="전체 검색")
        with f2:
            ko_cond = st.selectbox("KO", ["전체", "Y", "N", "파일없음"], key="quick_filter_ko")
        with f3:
            en_cond = st.selectbox("EN", ["전체", "Y", "N", "파일없음"], key="quick_filter_en")
        with f4:
            ru_cond = st.selectbox("RU", ["전체", "Y", "N", "파일없음"], key="quick_filter_ru")
        with f5:
            overall_cond = st.selectbox("ALL", ["전체", "Y", "N", "파일없음"], key="quick_filter_overall")
        with f6:
            sort_order = st.selectbox("정렬", ["오름차순", "내림차순"], key="seq_sort_order")

        with st.expander("열 표시 설정", expanded=False):
            st.session_state["hidden_columns"] = st.multiselect(
                "숨길 열",
                options=all_cols,
                default=st.session_state["hidden_columns"],
            )
            c1, c2 = st.columns(2)
            with c1:
                if st.button("숨김 해제", use_container_width=True, key="reset_hidden_cols_btn"):
                    st.session_state["hidden_columns"] = []
                    st.rerun()
            with c2:
                if st.button("매치 열만", use_container_width=True, key="keep_match_cols_btn"):
                    keep = {"순번", "비교 Key", "데이터출처", "KO_Match", "EN_Match", "RU_Match", "Overall_Match"}
                    st.session_state["hidden_columns"] = [c for c in all_cols if c not in keep]
                    st.rerun()

    visible_cols = [c for c in all_cols if c not in set(st.session_state["hidden_columns"])]
    ascending = sort_order == "오름차순"

    st.session_state["global_search"] = q
    view_df = df.copy()
    if q.strip():
        mask = False
        qs = q.strip().lower()
        for col in visible_cols:
            mask = mask | view_df[col].astype(str).str.lower().str.contains(qs, na=False)
        view_df = view_df[mask]
    view_df = apply_match_quick_filters(view_df, ko_cond, en_cond, ru_cond, overall_cond)
    view_df = apply_seq_sort(view_df, ascending=ascending)
    view_df = apply_value_filters(view_df, visible_cols)

    total_count = len(view_df)
    ko_n = int((view_df.get("KO_Match", pd.Series(dtype=str)).astype(str) == "N").sum())
    en_n = int((view_df.get("EN_Match", pd.Series(dtype=str)).astype(str) == "N").sum())
    ru_n = int((view_df.get("RU_Match", pd.Series(dtype=str)).astype(str) == "N").sum())
    overall_n = int((view_df.get("Overall_Match", pd.Series(dtype=str)).astype(str) == "N").sum())
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("전체", f"{total_count:,}")
    m2.metric("KO 불일치", f"{ko_n:,}")
    m3.metric("EN 불일치", f"{en_n:,}")
    m4.metric("RU 불일치", f"{ru_n:,}")
    m5.metric("전체 불일치", f"{overall_n:,}")

    page_no, page_size, page_total = get_pagination_state(len(view_df), "result")
    start = (page_no - 1) * page_size
    end = start + page_size
    page_df = view_df.iloc[start:end]

    pending = st.session_state.get("pending_edit_bundle")
    edit_mode = bool(st.session_state.get("edit_mode", False))
    edited_marks = st.session_state.get("edited_language_marks", {})

    with st.container(border=True):
        h1, h2 = st.columns([2.7, 1.3], gap="small")
        with h1:
            st.caption("조회 후 편집이 필요하면 오른쪽 버튼으로 시작하세요.")
        with h2:
            b1, b2, b3 = st.columns(3, gap="small")
            with b1:
                if st.button(
                    "수정 시작",
                    type="primary" if not edit_mode else "secondary",
                    use_container_width=True,
                    key="start_edit_btn",
                    disabled=edit_mode or bool(pending),
                ):
                    st.session_state["edit_mode"] = True
                    st.session_state["pre_edit_records"] = pd.DataFrame(st.session_state["result_records"]).fillna("").to_dict("records")
                    st.session_state["pending_edit_bundle"] = None
                    st.rerun()
            with b2:
                finish_clicked = st.button(
                    "완료",
                    type="primary",
                    use_container_width=True,
                    key="finish_edit_btn_top",
                    disabled=(not edit_mode) or bool(pending),
                )
            with b3:
                if st.button(
                    "취소",
                    use_container_width=True,
                    key="cancel_all_edit_btn",
                    disabled=(not edit_mode) and (not bool(pending)),
                ):
                    st.session_state["edit_mode"] = False
                    st.session_state["pending_edit_bundle"] = None
                    st.rerun()

        editable_view = page_df[visible_cols].copy()
        focus_key = st.session_state.get("focus_compare_key", "")

    if edit_mode:
        edited = st.data_editor(editable_view, use_container_width=True, height=640, key="result_editor")
        if finish_clicked:
            change_df = build_change_preview(editable_view, edited.fillna(""), visible_cols)
            if change_df.empty:
                st.info("변경된 값이 없습니다.")
            else:
                st.session_state["pending_edit_bundle"] = {
                    "edited_json": edited.fillna("").to_json(orient="split", force_ascii=False),
                    "base_json": df.to_json(orient="split", force_ascii=False),
                    "visible_cols": visible_cols,
                    "change_json": change_df.to_json(orient="split", force_ascii=False),
                }
                st.rerun()
    else:
        st.dataframe(
            style_match_highlight(editable_view, focus_key=focus_key, edited_language_marks=edited_marks),
            use_container_width=True,
            height=640,
        )

        render_numeric_pagination_controls(len(view_df), page_no, page_total, "result")

    with st.expander("수정 전 기준 테이블", expanded=False):
        pre_edit_df = pd.DataFrame(st.session_state.get("pre_edit_records", [])).fillna("")
        if pre_edit_df.empty:
            pre_edit_df = df.copy()
        pre_view_df = pre_edit_df.copy()
        if q.strip():
            mask = False
            qs = q.strip().lower()
            for col in visible_cols:
                if col in pre_view_df.columns:
                    mask = mask | pre_view_df[col].astype(str).str.lower().str.contains(qs, na=False)
            pre_view_df = pre_view_df[mask]
        pre_view_df = apply_match_quick_filters(pre_view_df, ko_cond, en_cond, ru_cond, overall_cond)
        pre_view_df = apply_seq_sort(pre_view_df, ascending=ascending)
        pre_view_df = pre_view_df.iloc[start:end]
        if all(c in pre_view_df.columns for c in visible_cols):
            st.dataframe(
                style_match_highlight(
                    pre_view_df[visible_cols].copy(),
                    focus_key=st.session_state.get("focus_compare_key", ""),
                    edited_language_marks=edited_marks,
                ),
                use_container_width=True,
                height=300,
            )

    with st.container(border=True):
        st.markdown("#### 내보내기")
        export_target = view_df.copy()
        export_json = export_target.to_json(orient="split", force_ascii=False)
        csv_bytes = dataframe_to_csv_bytes_cached(export_json)
        excel_bytes = dataframe_to_excel_bytes_cached(export_json)
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "CSV 다운로드",
                data=csv_bytes,
                file_name="translation_compare.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with c2:
            st.download_button(
                "Excel 다운로드(수식/노란강조)",
                data=excel_bytes,
                file_name="translation_compare.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

    with st.container(border=True):
        st.markdown("#### 변경점 비교 리포트")
        baseline = st.file_uploader("기준 파일 업로드(CSV/XLSX)", type=["csv", "xlsx"], key="baseline")
        if baseline is not None and st.button("변경점 비교 실행", use_container_width=True):
            try:
                if baseline.name.lower().endswith(".xlsx"):
                    baseline_df = pd.read_excel(baseline, dtype=str).fillna("")
                else:
                    baseline_df = pd.read_csv(baseline, dtype=str, keep_default_na=False).fillna("")
                diff_df = diff_report(baseline_df, pd.DataFrame(st.session_state["result_records"]).fillna(""))
                st.dataframe(diff_df, use_container_width=True, height=260)
            except Exception as error:
                st.error(f"기준 파일 처리 실패: {error}")


def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    inject_table_wrap_css()
    init_state()
    run_internal_sanity_checks_once()

    st.markdown(f'<div class="app-title">{APP_TITLE}</div>', unsafe_allow_html=True)
    st.caption("딕셔너리와 JSON 언어 파일을 비교하고, 불일치를 편집/검토한 뒤 내보낼 수 있습니다.")

    storage_dir = resolve_storage_dir(st.session_state["storage_dir"])
    st.session_state["storage_dir"] = str(storage_dir)

    if not st.session_state["did_initial_autorun"] and not st.session_state["result_records"]:
        st.session_state["source_paths"] = saved_paths_dict(storage_dir)
        if st.session_state["source_paths"].get("dictionary"):
            run_compare_from_saved_files(include_en_keys=False)
        st.session_state["did_initial_autorun"] = True

    st.session_state["fullscreen_result"] = st.toggle("결과 전체 화면", value=st.session_state["fullscreen_result"])
    st.query_params["fullscreen"] = "1" if st.session_state["fullscreen_result"] else "0"

    if st.session_state["fullscreen_result"]:
        t1, t2 = st.columns([1, 4])
        with t1:
            if st.button(
                "입력 패널 열기" if not st.session_state["show_input_in_fullscreen"] else "입력 패널 닫기",
                use_container_width=True,
                key="toggle_input_panel_in_fullscreen",
            ):
                st.session_state["show_input_in_fullscreen"] = not st.session_state["show_input_in_fullscreen"]
                st.rerun()
        with t2:
            st.caption("전체 화면에서는 비교 결과 중심으로 표시됩니다.")
        if st.session_state["show_input_in_fullscreen"]:
            with st.container(border=True):
                render_input_panel(storage_dir)
        render_result_panel()
    else:
        left, right = st.columns([1, 2], gap="large")
        with left:
            render_input_panel(storage_dir)
        with right:
            render_result_panel()


if __name__ == "__main__":
    main()
