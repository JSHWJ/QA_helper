# QA_helper
번역 딕셔너리와 JSON 언어 파일을 비교/검수/수정/내보내기 하는 Streamlit 기반 도구입니다.

## 기술 스택
- 백엔드/로직: Python (`app_modules/`)
- 프론트엔드: Streamlit (`app.py`)

## 실행
```bash
python.exe -m streamlit run app.py --server.port 8501
```

Windows:
```bat
run_streamlit.bat
```

접속:
- `http://127.0.0.1:8501`

## 전체 기능

### 1) 파일 입력/저장 경로
- 업로드 지원:
  - 딕셔너리: `xlsx/csv/tsv/txt`
  - JSON: `ko.json`, `ru.json`, `en.json(선택)`
- 저장 경로 UI:
  - `저장 폴더 경로` 입력
  - `폴더 적용`으로 즉시 반영
  - `자동 찾기`로 해당 폴더 latest 파일 자동 연결
- 저장 경로 우선순위:
  1. UI 적용 경로
  2. `AUTOMATIC_TOOL_STORAGE_DIR`
  3. `.automatic_tool_config.json`
  4. 기본 경로(`Desktop/automatic_tool_storage`)
- 업로드 파일 저장 방식:
  - `dictionary_latest.*`, `ko_latest.json`, `ru_latest.json`, `en_latest.json`
  - 재업로드 시 latest 파일 교체
- 앱 재시작/새로고침 시 저장 파일 자동 재사용

### 2) 비교 엔진
- 정규화:
  - 공백/줄바꿈/연속 공백/전체 따옴표 정리
- 딕셔너리 중복 처리:
  - English 기준 병합
  - Korean/Russian 쉼표 결합
- 생성 컬럼:
  - `순번`, `비교 Key`, `데이터출처`,
  - `Dictionary English/Korean/Russian`,
  - `en.json/ko.json/ru.json`,
  - `KO_Match/EN_Match/RU_Match/Overall_Match`
- 매치 상태값:
  - `Y`, `N`, `파일없음`

### 3) 메인 비교 화면
- 전체 화면 토글:
  - `비교결과 전체 화면` ON/OFF
  - 새로고침 후에도 상태 유지
- 테이블 구조:
  - 메인 테이블 1개
  - `수정 전 기준 테이블` 1개(expander)
- 페이지네이션:
  - `건수`, `쪽` 컨트롤
  - 메인/수정전 테이블 모두 동일 페이지 기준 적용
- 텍스트 표시:
  - 긴 셀 값 자동 줄바꿈

### 4) 검색/필터/정렬
- 상단 빠른 조건(한 줄):
  - `검색`
  - `KO`, `EN`, `RU`, `ALL` (`전체/Y/N/파일없음`)
  - `정렬`(순번 기준 오름차순/내림차순)
- 열 제어:
  - `숨길 열`, `숨김 해제`, `매치만`
- 추가 필터(expander):
  - 일반 컬럼 값 선택 필터
  - 매치 컬럼 필터는 상단 빠른 조건에서만 처리

### 5) 시각 강조
- `N` 상태 강조:
  - `KO/EN/RU/Overall_Match = N` 노란 배경
- 불일치 쌍 강조:
  - 예: `RU_Match = N`이면 `Dictionary Russian` + `ru.json` 빨간 테두리
- 행 선택 강조:
  - 선택 행의 미스매치 쌍 강조 강화

### 6) 편집 워크플로우
- 편집 작업바:
  - `시작`, `완료`, `취소`
- 절차:
  1. `시작`으로 편집 모드 진입
  2. 메인 테이블에서 값 수정
  3. `완료` 누르면 변경 내역 검토 표시
  4. `수락(적용)` / `이전(다시 수정)` / `모두 취소`
- 적용 시 매치 컬럼 재계산
- `수정 전 기준 테이블`로 변경 전 상태 비교 가능

### 7) 통계/상태
- 실시간 메트릭:
  - `전체 개수`, `KO 불일치`, `EN 불일치`, `RU 불일치`, `전체 불일치`
- 현재 필터/검색 결과 기준으로 즉시 동기화
- 파일 상태표:
  - 각 파일 연결 여부/경로/파일명 표시
- 비교 상태 메시지:
  - 로드 상태, 건수, 파일 유무 안내

### 8) 내보내기/리포트
- CSV 다운로드:
  - 현재 결과 데이터만 저장
- Excel 다운로드:
  - 매치 수식 포함
  - `N` 노란 조건부서식 포함
  - `파일없음` 회색 조건부서식 포함
- 변경점 비교 리포트:
  - 기준 CSV/XLSX 업로드 후 변경 행/컬럼 리포트

## 주요 파일
- `app.py`: Streamlit UI 및 상태 관리
- `app_modules/compare_logic.py`: 비교 데이터 생성
- `app_modules/matching_utils.py`: 매치 계산 로직
- `app_modules/storage_utils.py`: 저장 경로/파일 탐색
- `app_modules/exporters.py`: CSV/Excel 내보내기

## 빠른 점검 체크리스트
- 서버 응답: `http://127.0.0.1:8501`이 `200 OK`
- 파일 업로드 후 비교 결과 생성
- `N` 노란색/미스매치 쌍 빨간 강조 표시
- 페이지네이션/필터/검색 동작
- 편집 검토 플로우(`시작 -> 완료 -> 수락/이전/취소`) 동작
