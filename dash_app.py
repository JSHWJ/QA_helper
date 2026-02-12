from pathlib import Path
from datetime import datetime

import dash_ag_grid as dag
import pandas as pd
from dash import Dash, Input, Output, State, ctx, dcc, html, no_update

from app_modules.dash_logic import (
    build_compare_dataframe,
    guess_mapping_columns,
    read_dictionary,
    read_uploaded_table,
    read_json_map,
    save_upload_bytes,
)
from app_modules.exporters import dataframe_to_excel_bytes
from app_modules.grid_config import RESULT_GRID_ROW_CLASS_RULES
from app_modules.grid_locale import AGGRID_KO_LOCALE
from app_modules.matching_utils import recompute_match_columns
from app_modules.storage_utils import export_dir_path, get_saved_file_path, resolve_storage_dir, set_storage_dir
from app_modules.text_utils import normalize_text


APP_TITLE = "번역 정합성 검증 도구 (Dash AG Grid)"


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


def first_candidate(text: str) -> str:
    items = [normalize_text(x) for x in str(text).split(",")]
    items = [x for x in items if x]
    return items[0] if items else ""


def saved_paths_dict(storage_dir: str | None = None):
    base_dir = resolve_storage_dir(storage_dir)
    return {
        "dictionary": str(get_saved_file_path("dictionary_latest", base_dir) or ""),
        "ko": str(get_saved_file_path("ko_latest", base_dir) or ""),
        "ru": str(get_saved_file_path("ru_latest", base_dir) or ""),
        "en": str(get_saved_file_path("en_latest", base_dir) or ""),
    }


app = Dash(__name__, title=APP_TITLE, suppress_callback_exceptions=True)
server = app.server

app.layout = html.Div(
    [
        dcc.Interval(id="init-load", interval=200, n_intervals=0, max_intervals=1),
        dcc.Store(id="store-storage-dir", data=str(resolve_storage_dir())),
        dcc.Store(id="store-source-paths", data=saved_paths_dict(str(resolve_storage_dir()))),
        dcc.Store(id="store-result-records", data=[]),
        dcc.Store(id="store-hidden-columns", data=[]),
        dcc.Store(id="store-export-dir", data=str(export_dir_path())),
        dcc.Store(id="store-diff-records", data=[]),
        html.Div(
            [
                html.Div("MMIS Translation QA", className="app-kicker"),
                html.H2(APP_TITLE, className="app-title"),
                html.Div("딕셔너리 + JSON 비교/편집/내보내기를 한 번에 처리", className="app-subtitle"),
            ],
            className="app-header",
        ),
        dcc.RadioItems(
            id="view-mode",
            options=[
                {"label": "기본 화면", "value": "base"},
                {"label": "비교결과 전체 화면", "value": "full"},
            ],
            value="base",
            className="view-mode",
            inline=True,
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.H4("입력", className="panel-title"),
                        dcc.Upload(
                            id="upload-dictionary",
                            children=html.Button("딕셔너리 업로드", className="btn btn-upload"),
                            multiple=False,
                        ),
                        dcc.Upload(
                            id="upload-ko",
                            children=html.Button("ko.json 업로드", className="btn btn-upload"),
                            multiple=False,
                        ),
                        dcc.Upload(
                            id="upload-ru",
                            children=html.Button("ru.json 업로드", className="btn btn-upload"),
                            multiple=False,
                        ),
                        dcc.Upload(
                            id="upload-en",
                            children=html.Button("en.json 업로드", className="btn btn-upload"),
                            multiple=False,
                        ),
                        html.Br(),
                        dcc.Checklist(
                            id="option-checks",
                            options=[
                                {"label": "업로드 없으면 데스크탑 저장본 자동 사용", "value": "use_saved"},
                                {"label": "en.json 키도 비교 대상 키에 포함", "value": "include_en"},
                            ],
                            value=["use_saved"],
                            className="checklist",
                        ),
                        html.Button("저장본 다시 불러오기", id="btn-reload-saved", n_clicks=0, className="btn btn-ghost"),
                        html.Label("저장 폴더 경로", className="field-label"),
                        dcc.Input(
                            id="input-storage-dir",
                            type="text",
                            placeholder="저장 폴더 경로",
                            className="export-input",
                            value=str(resolve_storage_dir()),
                        ),
                        html.Button("저장 폴더 적용", id="btn-apply-storage-dir", n_clicks=0, className="btn btn-secondary"),
                        html.Div(id="source-status", className="source-status"),
                        html.Hr(),
                        html.H4("상세 설정", className="panel-title"),
                        html.Label("Main Module 컬럼", className="field-label"),
                        dcc.Dropdown(id="col-module", clearable=False),
                        html.Label("English 컬럼", className="field-label"),
                        dcc.Dropdown(id="col-english", clearable=False),
                        html.Label("Korean 컬럼", className="field-label"),
                        dcc.Dropdown(id="col-korean", clearable=False),
                        html.Label("Russian 컬럼", className="field-label"),
                        dcc.Dropdown(id="col-russian", clearable=False),
                        html.Br(),
                        html.Button("비교 실행", id="btn-run-compare", n_clicks=0, className="btn btn-primary"),
                    ],
                    id="input-panel-wrap",
                    className="panel input-panel",
                ),
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(
                                    [
                                        dcc.Input(
                                            id="global-search",
                                            type="text",
                                            placeholder="전체 검색",
                                            debounce=True,
                                            className="search-input",
                                        ),
                                        dcc.Dropdown(
                                            id="hide-columns-select",
                                            multi=True,
                                            placeholder="숨길 열 선택",
                                            className="column-picker",
                                        ),
                                        html.Button("선택 열 숨기기", id="btn-hide-selected", n_clicks=0, className="btn btn-ghost"),
                                        html.Button("숨김 해제(전체)", id="btn-show-all", n_clicks=0, className="btn btn-light"),
                                    ],
                                    className="toolbar-row",
                                ),
                            ],
                            className="toolbar",
                        ),
                        html.Div(
                            [
                                html.Div(id="summary-total", className="summary-box metric-1"),
                                html.Div(id="summary-view", className="summary-box metric-2"),
                                html.Div(id="summary-ko", className="summary-box metric-3"),
                                html.Div(id="summary-en", className="summary-box metric-4"),
                                html.Div(id="summary-ru", className="summary-box metric-5"),
                            ],
                            className="summary-grid",
                        ),
                        dag.AgGrid(
                            id="result-grid",
                            columnDefs=[],
                            rowData=[],
                            dangerously_allow_code=True,
                            rowClassRules=RESULT_GRID_ROW_CLASS_RULES,
                            defaultColDef={
                                "editable": False,
                                "filter": "agSetColumnFilter",
                                "floatingFilter": False,
                                "resizable": True,
                                "sortable": False,
                                "menuTabs": ["filterMenuTab"],
                            },
                            enableEnterpriseModules=True,
                            dashGridOptions={
                                "rowSelection": "single",
                                "animateRows": False,
                                "pagination": True,
                                "paginationPageSize": 120,
                                "suppressFieldDotNotation": True,
                                "suppressMovableColumns": False,
                                "suppressMenuHide": False,
                                "enableRangeSelection": True,
                                "localeText": AGGRID_KO_LOCALE,
                                "quickFilterText": "",
                                "getContextMenuItems": {
                                    "function": """
                                        function(params) {
                                            const colId = params.column ? params.column.getColId() : '';
                                            const items = [];
                                            if (colId === '순번') {
                                                items.push({
                                                    name: '순번 오름차순',
                                                    action: () => params.columnApi.applyColumnState({
                                                        state: [{colId: colId, sort: 'asc'}],
                                                        defaultState: {sort: null}
                                                    })
                                                });
                                                items.push({
                                                    name: '순번 내림차순',
                                                    action: () => params.columnApi.applyColumnState({
                                                        state: [{colId: colId, sort: 'desc'}],
                                                        defaultState: {sort: null}
                                                    })
                                                });
                                                items.push({name: '정렬 해제', action: () => params.columnApi.applyColumnState({defaultState: {sort: null}})});
                                                items.push('separator');
                                            }
                                            items.push({
                                                name: '이 열 숨기기',
                                                action: () => {
                                                    if (params.column) {
                                                        params.columnApi.setColumnVisible(params.column.getColId(), false);
                                                    }
                                                }
                                            });
                                            items.push({
                                                name: '숨긴 열 모두 표시',
                                                action: () => {
                                                    (params.columnApi.getColumns() || []).forEach(c => params.columnApi.setColumnVisible(c.getColId(), true));
                                                }
                                            });
                                            return items;
                                        }
                                    """
                                },
                                "onBodyScroll": {"function": "function(params){ if(params.api && params.api.hidePopupMenu){ params.api.hidePopupMenu(); } }"},
                                "onCellClicked": {
                                    "function": """
                                        function(params){
                                            if(params.api && params.api.hidePopupMenu){ params.api.hidePopupMenu(); }
                                            window.__mmisClicked = {
                                                key: String((params.data && params.data['비교 Key']) || ''),
                                                field: params.colDef && params.colDef.field ? params.colDef.field : ''
                                            };
                                            if (params.api && params.api.refreshCells) {
                                                params.api.refreshCells({force: true});
                                            }
                                        }
                                    """
                                },
                            },
                            style={"height": "72vh", "width": "100%"},
                            className="ag-theme-alpine result-grid",
                        ),
                        html.Div(
                            [
                                html.H4("내보내기", className="panel-title"),
                                html.Div(
                                    [
                                        dcc.Input(
                                            id="input-export-dir",
                                            type="text",
                                            placeholder="내보내기 폴더 경로",
                                            className="export-input",
                                        ),
                                        html.Button("내보내기 폴더 적용", id="btn-apply-export-dir", n_clicks=0, className="btn btn-secondary"),
                                        html.Button("CSV 다운로드", id="btn-download-csv", n_clicks=0, className="btn btn-light"),
                                        html.Button("Excel 다운로드", id="btn-download-xlsx", n_clicks=0, className="btn btn-excel"),
                                    ],
                                    className="export-toolbar",
                                ),
                                html.Div(id="export-status", className="status-line"),
                                dcc.Download(id="download-csv"),
                                dcc.Download(id="download-xlsx"),
                            ],
                            className="panel export-panel",
                        ),
                        html.Div(
                            [
                                html.H4("변경점 비교 리포트", className="panel-title"),
                                html.Div(
                                    [
                                        dcc.Upload(
                                            id="upload-baseline",
                                            children=html.Button("기준 파일 업로드(이전 CSV/XLSX)", className="btn btn-ghost"),
                                            multiple=False,
                                        ),
                                        html.Button("변경점 비교 실행", id="btn-run-diff", n_clicks=0, className="btn btn-light"),
                                    ],
                                    className="export-toolbar",
                                ),
                        dag.AgGrid(
                            id="diff-grid",
                            columnDefs=[],
                            rowData=[],
                            dangerously_allow_code=True,
                            defaultColDef={"resizable": True, "filter": True},
                            columnSize="sizeToFit",
                            className="ag-theme-alpine result-grid",
                                    style={"height": "260px", "width": "100%", "marginTop": "8px"},
                                ),
                                html.Div(id="diff-status", className="status-line"),
                            ],
                            className="panel export-panel",
                        ),
                        html.Div(id="compare-status", className="status-line"),
                    ],
                    id="result-panel-wrap",
                    className="panel result-panel",
                ),
            ],
            id="main-layout",
            className="app-main",
        ),
    ],
    className="app-shell",
)


@app.callback(
    Output("store-storage-dir", "data"),
    Input("btn-apply-storage-dir", "n_clicks"),
    State("input-storage-dir", "value"),
    prevent_initial_call=True,
)
def apply_storage_dir_setting(_clicks, storage_dir_input):
    return str(set_storage_dir(storage_dir_input or ""))


@app.callback(
    Output("input-storage-dir", "value"),
    Input("store-storage-dir", "data"),
)
def sync_storage_dir_input(storage_dir):
    return storage_dir or str(resolve_storage_dir())


@app.callback(
    Output("store-export-dir", "data"),
    Input("store-storage-dir", "data"),
)
def sync_export_dir_by_storage(storage_dir):
    return str(export_dir_path(storage_dir))


@app.callback(
    Output("store-source-paths", "data"),
    Output("source-status", "children"),
    Input("upload-dictionary", "contents"),
    Input("upload-ko", "contents"),
    Input("upload-ru", "contents"),
    Input("upload-en", "contents"),
    Input("btn-reload-saved", "n_clicks"),
    Input("init-load", "n_intervals"),
    Input("option-checks", "value"),
    Input("store-storage-dir", "data"),
    State("upload-dictionary", "filename"),
    State("upload-ko", "filename"),
    State("upload-ru", "filename"),
    State("upload-en", "filename"),
    State("store-source-paths", "data"),
)
def handle_sources(dict_content, ko_content, ru_content, en_content, _reload_clicks, _init_tick, options, storage_dir_text, dict_name, ko_name, ru_name, en_name, current_paths):
    storage_dir = resolve_storage_dir(storage_dir_text)
    use_saved = "use_saved" in (options or [])
    data = dict(current_paths or {"dictionary": "", "ko": "", "ru": "", "en": ""})

    triggered = ctx.triggered_id
    if triggered in ["btn-reload-saved", "init-load"]:
        data = saved_paths_dict(str(storage_dir))
    else:
        if dict_content:
            saved = save_upload_bytes(storage_dir, "dictionary_latest", dict_name or "dictionary.xlsx", dict_content)
            data["dictionary"] = str(saved or "")
        elif use_saved and (not data.get("dictionary") or not Path(str(data.get("dictionary"))).exists()):
            data["dictionary"] = str(get_saved_file_path("dictionary_latest", storage_dir) or "")

        if ko_content:
            saved = save_upload_bytes(storage_dir, "ko_latest", ko_name or "ko.json", ko_content)
            data["ko"] = str(saved or "")
        elif use_saved and (not data.get("ko") or not Path(str(data.get("ko"))).exists()):
            data["ko"] = str(get_saved_file_path("ko_latest", storage_dir) or "")

        if ru_content:
            saved = save_upload_bytes(storage_dir, "ru_latest", ru_name or "ru.json", ru_content)
            data["ru"] = str(saved or "")
        elif use_saved and (not data.get("ru") or not Path(str(data.get("ru"))).exists()):
            data["ru"] = str(get_saved_file_path("ru_latest", storage_dir) or "")

        if en_content:
            saved = save_upload_bytes(storage_dir, "en_latest", en_name or "en.json", en_content)
            data["en"] = str(saved or "")
        elif use_saved and (not data.get("en") or not Path(str(data.get("en"))).exists()):
            data["en"] = str(get_saved_file_path("en_latest", storage_dir) or "")

    text = (
        f"사용 파일: dictionary={Path(data.get('dictionary', '')).name or '없음'}, "
        f"ko={Path(data.get('ko', '')).name or '없음'}, "
        f"ru={Path(data.get('ru', '')).name or '없음'}, "
        f"en={Path(data.get('en', '')).name or '없음'} | 저장 경로: {storage_dir}"
    )
    return data, text


@app.callback(
    Output("col-module", "options"),
    Output("col-english", "options"),
    Output("col-korean", "options"),
    Output("col-russian", "options"),
    Output("col-module", "value"),
    Output("col-english", "value"),
    Output("col-korean", "value"),
    Output("col-russian", "value"),
    Input("store-source-paths", "data"),
)
def update_mapping_options(source_paths):
    dictionary_path = Path(source_paths.get("dictionary")) if source_paths and source_paths.get("dictionary") else None
    dictionary_df, _ = read_dictionary(dictionary_path)
    if dictionary_df is None or dictionary_df.empty:
        return [], [], [], [], None, None, None, None

    mapping = guess_mapping_columns(dictionary_df)
    options = [{"label": c, "value": c} for c in mapping["columns"]]
    return (
        options,
        options,
        options,
        options,
        mapping["module"] or mapping["columns"][0],
        mapping["english"] or mapping["columns"][0],
        mapping["korean"] or mapping["columns"][min(1, len(mapping["columns"]) - 1)],
        mapping["russian"] or mapping["columns"][min(2, len(mapping["columns"]) - 1)],
    )


@app.callback(
    Output("store-result-records", "data"),
    Output("compare-status", "children"),
    Input("btn-run-compare", "n_clicks"),
    Input("store-source-paths", "data"),
    Input("option-checks", "value"),
    Input("store-storage-dir", "data"),
    Input("col-module", "value"),
    Input("col-english", "value"),
    Input("col-korean", "value"),
    Input("col-russian", "value"),
)
def run_compare(_clicks, source_paths, options, storage_dir_text, module_col, english_col, korean_col, russian_col):
    use_saved = "use_saved" in (options or [])
    source_paths = dict(source_paths or {})
    storage_dir = resolve_storage_dir(storage_dir_text)

    if use_saved:
        if (not source_paths.get("dictionary")) or (not Path(str(source_paths.get("dictionary"))).exists()):
            source_paths["dictionary"] = str(get_saved_file_path("dictionary_latest", storage_dir) or "")
        if (not source_paths.get("ko")) or (not Path(str(source_paths.get("ko"))).exists()):
            source_paths["ko"] = str(get_saved_file_path("ko_latest", storage_dir) or "")
        if (not source_paths.get("ru")) or (not Path(str(source_paths.get("ru"))).exists()):
            source_paths["ru"] = str(get_saved_file_path("ru_latest", storage_dir) or "")
        if (not source_paths.get("en")) or (not Path(str(source_paths.get("en"))).exists()):
            source_paths["en"] = str(get_saved_file_path("en_latest", storage_dir) or "")

    if not source_paths or not source_paths.get("dictionary"):
        return [], "딕셔너리 파일이 필요합니다."

    dictionary_path = Path(source_paths.get("dictionary")) if source_paths.get("dictionary") else None
    ko_path = Path(source_paths.get("ko")) if source_paths.get("ko") else None
    ru_path = Path(source_paths.get("ru")) if source_paths.get("ru") else None
    en_path = Path(source_paths.get("en")) if source_paths.get("en") else None

    ko_loaded = bool(ko_path and ko_path.exists())
    ru_loaded = bool(ru_path and ru_path.exists())
    en_loaded = bool(en_path and en_path.exists())

    try:
        dictionary_df, _ = read_dictionary(dictionary_path)
        if dictionary_df is None or dictionary_df.empty:
            return [], "딕셔너리 파일을 읽지 못했거나 데이터가 비어 있습니다."

        required_cols = [module_col, english_col, korean_col, russian_col]
        if any(not c for c in required_cols):
            return [], "컬럼 매핑이 비어 있습니다. 상세 설정에서 컬럼을 확인하세요."

        for c in required_cols:
            if c not in dictionary_df.columns:
                return [], f"선택한 컬럼이 딕셔너리에 없습니다: {c}"

        include_en = "include_en" in (options or [])
        ko_map = read_json_map(ko_path)
        ru_map = read_json_map(ru_path)
        en_map = read_json_map(en_path)

        out_df, _ = build_compare_dataframe(
            dictionary_df=dictionary_df,
            ko_map=ko_map,
            ru_map=ru_map,
            en_map=en_map,
            include_en_keys=include_en,
            module_col=module_col,
            english_col=english_col,
            korean_col=korean_col,
            russian_col=russian_col,
        )
        # JSON 파일이 실제로 없으면 JSON 컬럼을 비워 비교불가 상태로 처리
        if not ko_loaded:
            out_df["ko.json"] = ""
        if not en_loaded:
            out_df["en.json"] = ""
        if not ru_loaded:
            out_df["ru.json"] = ""

        # 파일은 있어도 해당 컬럼 값이 전부 비어 있으면 사실상 비교 불가
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

        status_tail = []
        status_tail.append(f"ko.json={'로드됨' if ko_loaded else '없음'}{'(데이터없음)' if ko_loaded and not ko_has_data else ''}")
        status_tail.append(f"ru.json={'로드됨' if ru_loaded else '없음'}{'(데이터없음)' if ru_loaded and not ru_has_data else ''}")
        status_tail.append(f"en.json={'로드됨' if en_loaded else '없음'}{'(데이터없음)' if en_loaded and not en_has_data else ''}")
        ko_mapped = int(out_df["ko.json"].astype(str).str.strip().ne("").sum()) if "ko.json" in out_df.columns else 0
        ru_mapped = int(out_df["ru.json"].astype(str).str.strip().ne("").sum()) if "ru.json" in out_df.columns else 0
        en_mapped = int(out_df["en.json"].astype(str).str.strip().ne("").sum()) if "en.json" in out_df.columns else 0
        return out_df.to_dict("records"), (
            f"비교 완료: 총 {len(out_df):,}건 | "
            + ", ".join(status_tail)
            + f" | JSON키수 ko={len(ko_map):,}, ru={len(ru_map):,}, en={len(en_map):,}"
            + f" | 매핑건수 ko={ko_mapped:,}, ru={ru_mapped:,}, en={en_mapped:,}"
        )
    except Exception as error:
        return [], f"비교 중 오류: {error}"


@app.callback(
    Output("main-layout", "className"),
    Input("view-mode", "value"),
)
def switch_view_mode(view_mode):
    if view_mode == "full":
        return "app-main full-mode"
    return "app-main"


@app.callback(
    Output("store-hidden-columns", "data"),
    Input("btn-hide-selected", "n_clicks"),
    Input("btn-show-all", "n_clicks"),
    State("hide-columns-select", "value"),
    State("store-hidden-columns", "data"),
    prevent_initial_call=True,
)
def update_hidden_columns(_hide_clicks, _show_clicks, selected_cols, hidden_cols):
    current_hidden = set(hidden_cols or [])
    triggered = ctx.triggered_id
    if triggered == "btn-hide-selected":
        for col in selected_cols or []:
            current_hidden.add(col)
    elif triggered == "btn-show-all":
        current_hidden = set()
    return sorted(current_hidden)


@app.callback(
    Output("store-result-records", "data", allow_duplicate=True),
    Input("result-grid", "cellValueChanged"),
    State("result-grid", "rowData"),
    prevent_initial_call=True,
)
def apply_edit_and_recompute(changed, row_data):
    if not row_data:
        return no_update
    if isinstance(changed, list):
        changed = changed[-1] if changed else None
    if not changed or "rowIndex" not in changed:
        return row_data

    row_index = changed.get("rowIndex")
    if row_index is None or row_index < 0 or row_index >= len(row_data):
        return row_data

    # 전체 DataFrame 재생성/재계산 대신 변경된 행만 갱신하여 렉을 줄임
    records = list(row_data)
    row = dict(records[row_index])

    text_cols = [
        "비교 Key",
        "Main Module",
        "Dictionary English",
        "Dictionary Korean",
        "Dictionary Russian",
        "en.json",
        "ko.json",
        "ru.json",
    ]
    for col in text_cols:
        if col in row:
            row[col] = normalize_text(row.get(col, ""))

    row["수정상태"] = ""
    row["수정일시"] = row.get("수정일시", "")
    edited_col = changed.get("colId") if isinstance(changed, dict) else None
    if edited_col and edited_col not in ["수정상태", "수정일시"]:
        row["수정상태"] = "수정됨"
        row["수정일시"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    row_changed = False
    if str(row.get("KO_Match", "")).upper() == "Y":
        v = first_candidate(row.get("Dictionary Korean", ""))
        if normalize_text(row.get("ko.json", "")) != v:
            row["ko.json"] = v
            row_changed = True
    if str(row.get("EN_Match", "")).upper() == "Y":
        v = normalize_text(row.get("Dictionary English", ""))
        if normalize_text(row.get("en.json", "")) != v:
            row["en.json"] = v
            row_changed = True
    if str(row.get("RU_Match", "")).upper() == "Y":
        v = first_candidate(row.get("Dictionary Russian", ""))
        if normalize_text(row.get("ru.json", "")) != v:
            row["ru.json"] = v
            row_changed = True
    if row_changed:
        row["수정상태"] = "수정됨"
        row["수정일시"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    one_df = pd.DataFrame([row]).fillna("")
    one_df = recompute_matches(one_df)
    records[row_index] = one_df.iloc[0].to_dict()
    return records


@app.callback(
    Output("store-diff-records", "data"),
    Output("diff-status", "children"),
    Input("btn-run-diff", "n_clicks"),
    State("upload-baseline", "contents"),
    State("upload-baseline", "filename"),
    State("store-result-records", "data"),
    prevent_initial_call=True,
)
def run_diff_report(_clicks, baseline_content, baseline_name, current_records):
    if not current_records:
        return [], "현재 비교 결과가 없습니다."
    if not baseline_content or not baseline_name:
        return [], "기준 파일(CSV/XLSX)을 먼저 업로드하세요."

    baseline_df = read_uploaded_table(baseline_content, baseline_name)
    if baseline_df is None or baseline_df.empty:
        return [], "기준 파일을 읽을 수 없거나 비어 있습니다."

    current_df = pd.DataFrame(current_records).fillna("")
    key_col = "비교 Key" if "비교 Key" in current_df.columns else "Dictionary English"
    baseline_key_col = "비교 Key" if "비교 Key" in baseline_df.columns else "Dictionary English"
    if key_col not in current_df.columns or baseline_key_col not in baseline_df.columns:
        return [], "기준 파일과 현재 데이터에 키 컬럼(비교 Key 또는 Dictionary English)이 필요합니다."

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
    diff_rows = []
    for key in all_keys:
        before = baseline_map.get(key)
        after = current_map.get(key)
        if before is None and after is not None:
            diff_rows.append({"비교 Key": key, "변경유형": "추가", "변경컬럼": "-", "이전값": "", "현재값": "행 추가"})
            continue
        if before is not None and after is None:
            diff_rows.append({"비교 Key": key, "변경유형": "삭제", "변경컬럼": "-", "이전값": "행 존재", "현재값": ""})
            continue

        cols = sorted(set(before.keys()) | set(after.keys()))
        for col in cols:
            if col in ["순번", "수정상태"]:
                continue
            b = normalize_text(before.get(col, ""))
            a = normalize_text(after.get(col, ""))
            if b != a:
                diff_rows.append(
                    {
                        "비교 Key": key,
                        "변경유형": "변경",
                        "변경컬럼": col,
                        "이전값": b,
                        "현재값": a,
                    }
                )

    return diff_rows, f"변경점 비교 완료: {len(diff_rows):,}건"


@app.callback(
    Output("result-grid", "rowData"),
    Output("summary-total", "children"),
    Output("summary-view", "children"),
    Output("summary-ko", "children"),
    Output("summary-en", "children"),
    Output("summary-ru", "children"),
    Input("store-result-records", "data"),
)
def render_grid(
    records,
):
    if not records:
        return [], "총 단어 수: 0", "현재 표시 수: 0", "KO 불일치(N): 0", "EN 불일치(N): 0", "RU 불일치(N): 0"

    total_df = pd.DataFrame(records).fillna("")
    df = total_df.copy()

    return (
        df.to_dict("records"),
        f"총 단어 수: {len(total_df):,}",
        f"현재 표시 수: {len(df):,}",
        f"KO 불일치(N): {(df.get('KO_Match', pd.Series()).eq('N')).sum():,}",
        f"EN 불일치(N): {(df.get('EN_Match', pd.Series()).eq('N')).sum():,}",
        f"RU 불일치(N): {(df.get('RU_Match', pd.Series()).eq('N')).sum():,}",
    )


@app.callback(
    Output("result-grid", "columnDefs"),
    Output("hide-columns-select", "options"),
    Input("store-result-records", "data"),
    Input("store-hidden-columns", "data"),
)
def render_column_defs(records, hidden_cols):
    if not records:
        return [], []

    df = pd.DataFrame(records).fillna("")
    hidden_set = set(hidden_cols or [])
    all_cols = list(df.columns)
    options = [{"label": c, "value": c} for c in all_cols]

    style_fn = {
        "function": """
            function(params) {
                const field = params.colDef.field || '';
                const row = params.data || {};
                const clicked = window.__mmisClicked || null;
                let style = {};
                const matchCols = ['KO_Match', 'EN_Match', 'RU_Match', 'Overall_Match'];
                const isMatchCol = matchCols.includes(field);
                const raw = String(params.value == null ? '' : params.value).trim();
                const upper = raw.toUpperCase();

                if (isMatchCol) {
                    if (upper === 'N') {
                        return {
                            backgroundColor: '#ffd400',
                            color: '#111827',
                            fontWeight: '800'
                        };
                    }
                    if (raw === '파일없음') {
                        return {
                            backgroundColor: '#eceff1',
                            color: '#455a64',
                            fontWeight: '700'
                        };
                    }
                }

                const koMismatch = String(row['KO_Match'] == null ? '' : row['KO_Match']).trim().toUpperCase() === 'N';
                const enMismatch = String(row['EN_Match'] == null ? '' : row['EN_Match']).trim().toUpperCase() === 'N';
                const ruMismatch = String(row['RU_Match'] == null ? '' : row['RU_Match']).trim().toUpperCase() === 'N';
                const koMismatchPair = koMismatch && (field === 'Dictionary Korean' || field === 'ko.json');
                const enMismatchPair = enMismatch && (field === 'Dictionary English' || field === 'en.json');
                const ruMismatchPair = ruMismatch && (field === 'Dictionary Russian' || field === 'ru.json');
                const pairMismatch = koMismatchPair || enMismatchPair || ruMismatchPair;
                if (pairMismatch) {
                    style.backgroundColor = '#fff59d';
                    style.color = '#111827';
                }
                const sameClickedRow = clicked && String(clicked.key || '') === String(row['비교 Key'] || '');
                if (sameClickedRow) {
                    const clickedField = clicked.field || '';
                    const clickedKo = (clickedField === 'Dictionary Korean' || clickedField === 'ko.json');
                    const clickedEn = (clickedField === 'Dictionary English' || clickedField === 'en.json');
                    const clickedRu = (clickedField === 'Dictionary Russian' || clickedField === 'ru.json');
                    const shouldRed =
                        (clickedKo && koMismatchPair) ||
                        (clickedEn && enMismatchPair) ||
                        (clickedRu && ruMismatchPair);
                    if (shouldRed) {
                        style.border = '3px solid #d32f2f';
                        style.boxSizing = 'border-box';
                    }
                }
                return style;
            }
        """
    }
    match_renderer_fn = {
        "function": """
            function(params) {
                const raw = String(params.value == null ? '' : params.value).trim();
                const upper = raw.toUpperCase();
                if (upper === 'N') {
                    return '<div style=\"width:100%;height:100%;padding:0 6px;background:#ffd400;color:#111827;font-weight:800;\">N</div>';
                }
                if (raw === '파일없음') {
                    return '<div style=\"width:100%;height:100%;padding:0 6px;background:#eceff1;color:#455a64;font-weight:700;\">파일없음</div>';
                }
                return raw;
            }
        """
    }

    editable_cols = {
        "Main Module",
        "Dictionary Korean",
        "Dictionary Russian",
        "en.json",
        "ko.json",
        "ru.json",
        "KO_Match",
        "EN_Match",
        "RU_Match",
    }
    column_defs = []
    for col in all_cols:
        col_def = {
            "headerName": col,
            "field": col,
            "hide": col in hidden_set,
            "editable": col in editable_cols,
            "cellStyle": style_fn,
            "cellClassRules": {},
            "filter": "agSetColumnFilter",
            "filterParams": {"buttons": ["apply", "reset"], "closeOnApply": True, "excelMode": "windows"},
            "sortable": col == "순번",
        }
        if col == "순번":
            col_def["width"] = 90
            col_def["pinned"] = "left"
            col_def["sort"] = "asc"
        if col in ["KO_Match", "EN_Match", "RU_Match", "Overall_Match"]:
            col_def["cellRenderer"] = match_renderer_fn
            col_def["cellClassRules"] = {
                "value-n": {
                    "function": "params.value != null && String(params.value).trim().toUpperCase() === 'N'"
                },
                "value-missing": {
                    "function": "params.value != null && String(params.value).trim() === '파일없음'"
                },
            }
        column_defs.append(col_def)

    return column_defs, options


@app.callback(
    Output("diff-grid", "rowData"),
    Output("diff-grid", "columnDefs"),
    Input("store-diff-records", "data"),
)
def render_diff_grid(records):
    if not records:
        return [], []
    cols = list(pd.DataFrame(records).columns)
    defs = [
        {
            "headerName": c,
            "field": c,
            "filter": "agSetColumnFilter",
            "filterParams": {"buttons": ["apply", "reset"], "closeOnApply": True, "excelMode": "windows"},
            "resizable": True,
        }
        for c in cols
    ]
    return records, defs


@app.callback(
    Output("result-grid", "dashGridOptions"),
    Input("global-search", "value"),
    State("result-grid", "dashGridOptions"),
)
def apply_quick_filter(query, current_options):
    options = dict(current_options or {})
    next_query = (query or "").strip()
    if options.get("quickFilterText", "") == next_query:
        return no_update
    options["quickFilterText"] = next_query
    return options


@app.callback(
    Output("store-export-dir", "data"),
    Output("export-status", "children", allow_duplicate=True),
    Input("btn-apply-export-dir", "n_clicks"),
    State("input-export-dir", "value"),
    prevent_initial_call=True,
)
def apply_export_dir(_clicks, export_dir_input):
    try:
        target = Path(export_dir_input or "").expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        return str(target), f"내보내기 폴더 적용: {target}"
    except Exception as error:
        return no_update, f"폴더 적용 실패: {error}"


@app.callback(
    Output("input-export-dir", "value"),
    Input("store-export-dir", "data"),
)
def sync_export_input(export_dir):
    return export_dir or str(export_dir_path())


@app.callback(
    Output("download-csv", "data"),
    Output("download-xlsx", "data"),
    Output("export-status", "children"),
    Input("btn-download-csv", "n_clicks"),
    Input("btn-download-xlsx", "n_clicks"),
    State("store-result-records", "data"),
    State("store-export-dir", "data"),
    prevent_initial_call=True,
)
def export_outputs(_csv_clicks, _xlsx_clicks, records, export_dir):
    if not records:
        return no_update, no_update, "내보낼 데이터가 없습니다."
    df = pd.DataFrame(records)
    trig = ctx.triggered_id

    if trig == "btn-download-csv":
        return dcc.send_data_frame(df.to_csv, "translation_compare.csv", index=False, encoding="utf-8-sig"), no_update, "CSV 다운로드 준비 완료"

    if trig == "btn-download-xlsx":
        excel_bytes = dataframe_to_excel_bytes(df)
        return no_update, dcc.send_bytes(lambda buffer: buffer.write(excel_bytes), "translation_compare.xlsx"), "Excel 다운로드 준비 완료"

    return no_update, no_update, no_update


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050, use_reloader=False)
