from difflib import SequenceMatcher
from functools import lru_cache

import pandas as pd

from app_modules.text_utils import normalize_text, normalize_header_name


# 컬럼 추정, 값 병합, 매치 계산 등 비교 핵심 로직 모듈

def guess_column(df: pd.DataFrame, candidates):
    columns = list(df.columns)
    lower_map = {str(c).strip().lower(): c for c in columns}
    normalized_map = {normalize_header_name(c): c for c in columns}

    for candidate in candidates:
        if candidate in columns:
            return candidate

    for candidate in candidates:
        lowered = candidate.strip().lower()
        if lowered in lower_map:
            return lower_map[lowered]

    for candidate in candidates:
        normalized_candidate = normalize_header_name(candidate)
        if normalized_candidate in normalized_map:
            return normalized_map[normalized_candidate]

    scored = []
    for candidate in candidates:
        normalized_candidate = normalize_header_name(candidate)
        if not normalized_candidate:
            continue
        for col in columns:
            normalized_col = normalize_header_name(col)
            if not normalized_col:
                continue
            score = SequenceMatcher(None, normalized_candidate, normalized_col).ratio()
            scored.append((score, col))

    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_col = scored[0]
        if best_score >= 0.78:
            return best_col

    return None


def unique_join(series: pd.Series) -> str:
    merged = []
    for value in series:
        normalized = normalize_text(value)
        if normalized and normalized not in merged:
            merged.append(normalized)
    return ", ".join(merged)


def map_get_value(data_map: dict, key: str) -> str:
    if not key:
        return ""
    return normalize_text(data_map.get(key, ""))


def evaluate_binary_match(dictionary_value_joined: str, json_value: str) -> str:
    left = normalize_text(dictionary_value_joined)
    right = normalize_text(json_value)

    # JSON 값이 비어 있으면 비교불가로 처리
    if right == "":
        return "파일없음"
    if left == "":
        return "N"

    return "Y" if right in _candidate_tuple(left) else "N"


@lru_cache(maxsize=50000)
def _candidate_tuple(joined: str) -> tuple[str, ...]:
    candidates = [normalize_text(x) for x in str(joined).split(",")]
    candidates = [x for x in candidates if x]
    return tuple(candidates)


def evaluate_overall_match(row) -> str:
    states = [row["KO_Match"], row["EN_Match"], row["RU_Match"]]
    if "파일없음" in states:
        return "파일없음"
    return "Y" if states[0] == "Y" and states[1] == "Y" and states[2] == "Y" else "N"


def recompute_match_columns(df: pd.DataFrame) -> pd.DataFrame:
    ko_left = df["Dictionary Korean"].fillna("").tolist()
    ko_right = df["ko.json"].fillna("").tolist()
    en_left = df["Dictionary English"].fillna("").tolist()
    en_right = df["en.json"].fillna("").tolist()
    ru_left = df["Dictionary Russian"].fillna("").tolist()
    ru_right = df["ru.json"].fillna("").tolist()

    ko_match = [evaluate_binary_match(l, r) for l, r in zip(ko_left, ko_right)]
    en_match = [evaluate_binary_match(l, r) for l, r in zip(en_left, en_right)]
    ru_match = [evaluate_binary_match(l, r) for l, r in zip(ru_left, ru_right)]

    overall_match = []
    for k, e, r in zip(ko_match, en_match, ru_match):
        if "파일없음" in (k, e, r):
            overall_match.append("파일없음")
        elif k == "Y" and e == "Y" and r == "Y":
            overall_match.append("Y")
        else:
            overall_match.append("N")

    df["KO_Match"] = ko_match
    df["EN_Match"] = en_match
    df["RU_Match"] = ru_match
    df["Overall_Match"] = overall_match
    return df
