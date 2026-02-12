import re
import pandas as pd
import unicodedata


# 텍스트 비교 전에 형태를 통일하기 위한 정규화 유틸

def normalize_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""

    text = str(value)
    text = text.replace("\ufeff", "")  # BOM 제거
    text = text.replace("\u200b", "")  # zero-width space 제거
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00A0", " ")
    text = text.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    text = text.strip()
    text = re.sub(r"[ \t]+", " ", text)

    if len(text) >= 2 and text[0] == text[-1] and text[0] in ["'", '"']:
        text = text[1:-1].strip()

    return text


def canonical_key(value) -> str:
    text = normalize_text(value)
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


# 헤더 이름 매칭 정확도를 올리기 위한 정규화

def normalize_header_name(name: str) -> str:
    text = str(name).strip().lower()
    return re.sub(r"[^a-z0-9가-힣]+", "", text)
