"""그리드 표시 규칙을 한 곳에서 관리하는 모듈."""

MATCH_COLUMNS = ["KO_Match", "EN_Match", "RU_Match", "Overall_Match"]

RESULT_GRID_ROW_CLASS_RULES = {
    "row-ko-n": {
        "function": "params.data && String(params.data.KO_Match || '').trim().toUpperCase() === 'N'"
    },
    "row-en-n": {
        "function": "params.data && String(params.data.EN_Match || '').trim().toUpperCase() === 'N'"
    },
    "row-ru-n": {
        "function": "params.data && String(params.data.RU_Match || '').trim().toUpperCase() === 'N'"
    },
    "row-overall-n": {
        "function": "params.data && String(params.data.Overall_Match || '').trim().toUpperCase() === 'N'"
    },
    "row-ko-missing": {
        "function": "params.data && String(params.data.KO_Match || '').trim() === '파일없음'"
    },
    "row-en-missing": {
        "function": "params.data && String(params.data.EN_Match || '').trim() === '파일없음'"
    },
    "row-ru-missing": {
        "function": "params.data && String(params.data.RU_Match || '').trim() === '파일없음'"
    },
    "row-overall-missing": {
        "function": "params.data && String(params.data.Overall_Match || '').trim() === '파일없음'"
    },
}
