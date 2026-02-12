# Dash AG Grid 버전 실행 안내

## 설치
```bash
pip install dash dash-ag-grid pandas openpyxl
```

## 실행
```bash
python dash_app.py
```

브라우저에서 `http://127.0.0.1:8050` 으로 접속하면 됩니다.

또는 Windows에서 `run_dash.bat` 실행.

## EXE 빌드 (Windows)
```bash
build_dash_exe.bat
```

## 핵심 기능
- 딕셔너리/JSON 업로드 + 데스크탑 저장본 자동 재사용
- 컬럼 자동 매핑(오탈자 `enlish` 포함)
- 비교 결과 테이블 직접 수정
- 헤더 필터 + 우클릭 메뉴(정렬/열 숨기기/숨김 해제)
- 여러 열 동시 숨기기(상단 `숨길 열 선택` + `선택 열 숨기기`)
- 기준 파일(이전 CSV/XLSX)과 변경점 비교 리포트
- 컬럼 헤더 아래 필터 입력으로 열별 검색
- CSV/Excel 다운로드
- Excel 내 수식 기반 `Y/N` 재계산 + `N` 노란색 조건부서식

## 트러블슈팅
- JSON 컬럼(`en.json`, `ko.json`, `ru.json`) 값이 비어 보이면 AG Grid 점 표기 필드 설정을 확인하세요.
  - `dashGridOptions.suppressFieldDotNotation = True`가 필요합니다.
  - 없으면 JSON 컬럼은 빈칸으로 보이고 Match만 표시되는 모순이 발생할 수 있습니다.
- Match 시각화 규칙
  - `N`은 노란색 배경
  - 미스매치 행에서 언어쌍 셀 클릭 시(한/영/러) 해당 비교 2개 컬럼에 빨간 테두리 표시
