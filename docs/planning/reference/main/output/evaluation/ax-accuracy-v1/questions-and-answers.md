> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `main` 워크트리의 `output/evaluation/ax-accuracy-v1/questions-and-answers.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

> 평가 설계 참고본입니다. 원천 snapshot·가상 데이터 JSON·정답 JSON·SQL·실행기는 삭제했으므로 이 문서만으로 평가를 재현할 수 없습니다. 새 평가에서는 자료·정답을 다시 고정하고 검수해야 합니다.

# 축구 자연어 검색 정확도 평가셋 v1

작성일: 2026-10-27 · 개발용 40과제 / 64턴 · 모델 평가 미실행 · 사람 독립 검수 대기

## 읽는 방법

각 질문은 그대로 사용할 수 있습니다. 기대 답변은 문구 완전 일치가 아닌 의미 채점용입니다. 숫자·대상·순서의 정답은 동봉 JSON과 기준 SQL에 고정했습니다. 저장본 사례는 실제 수집 파일을 기준으로 하며 현재 현실 기록의 검증이나 전체 수집 완전성 보증이 아닙니다. 가상 사례는 실제 선수 기록과 혼용하지 않습니다.

자료 기준 시각: 2026-10-25T01:41:28.381514+00:00; 평가 시계: 2026-10-25T11:00:00+09:00. 이번 시즌=2026, 직전 시즌=2025. 실제 운영의 6시간 신선도 제한을 해제하지 않습니다.

공통 채점: 기대 행동·필수 상태·데이터·근거 설명·완결성을 모두 통과해야 성공합니다. 의미가 같은 문장은 허용합니다. 결측은 0이 아니며, 불필요한 확인 횟수는 효율 지표로 분리합니다.

이 평가셋은 구현 지원 기능을 선언하지 않습니다. 지원 자료가 없는 문항은 한계 처리 평가이며 정상 수치 조회 평가를 대신하지 않습니다.

## R01 · stored_data · numeric, snapshot, goals

데이터: snapshot. 

### R01-T01

**질문:** 저장된 이번 시즌 EPL 득점 공동 1위를 모두 알려줘.

**기대 답변 예시:** 고정 저장본 기준. 엘링 홀란드 8골 (공동 순위 포함 1위)

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "", "player_ids": null, "limit": null, "all_rank_one": true}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 533 | 엘링 홀란드 | value: 8.0, rank: 1 |

## R02 · stored_data · numeric, snapshot, goals

데이터: snapshot. 

### R02-T01

**질문:** 저장된 이번 시즌 EPL 득점 상위 5명을 순서대로 보여줘.

**기대 답변 예시:** 고정 저장본 기준. 엘링 홀란드 8골 (공동 순위 포함 1위); 알렉산더 이삭 5골 (공동 순위 포함 2위); 조아우 페드로 5골 (공동 순위 포함 2위); 브라이언 음뵈모 4골 (공동 순위 포함 4위); 마커스 태버니어 4골 (공동 순위 포함 4위)

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "", "player_ids": null, "limit": 5, "all_rank_one": false}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 533 | 엘링 홀란드 | value: 8.0, rank: 1 |
| 210 | 알렉산더 이삭 | value: 5.0, rank: 2 |
| 477 | 조아우 페드로 | value: 5.0, rank: 2 |
| 25 | 브라이언 음뵈모 | value: 4.0, rank: 4 |
| 87 | 마커스 태버니어 | value: 4.0, rank: 4 |

## R03 · stored_data · numeric, snapshot, assists

데이터: snapshot. 

### R03-T01

**질문:** 저장된 이번 시즌 EPL 도움 상위 5명을 보여줘.

**기대 답변 예시:** 고정 저장본 기준. 에바니우송 4도움 (공동 순위 포함 1위); 데클런 라이스 4도움 (공동 순위 포함 1위); 파스칼 그로스 4도움 (공동 순위 포함 1위); 앙투안 세메뇨 3도움 (공동 순위 포함 4위); 코디 학포 3도움 (공동 순위 포함 4위)

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "assists", "filters_sql": "", "player_ids": null, "limit": 5, "all_rank_one": false}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 94 | 에바니우송 | value: 4.0, rank: 1 |
| 236 | 데클런 라이스 | value: 4.0, rank: 1 |
| 580 | 파스칼 그로스 | value: 4.0, rank: 1 |
| 88 | 앙투안 세메뇨 | value: 3.0, rank: 4 |
| 188 | 코디 학포 | value: 3.0, rank: 4 |

## R04 · stored_data · numeric, snapshot, goals

데이터: snapshot. 

### R04-T01

**질문:** 저장된 직전 시즌 EPL 득점 상위 3명을 보여줘.

**기대 답변 예시:** 고정 저장본 기준. 엘링 홀란드 27골 (공동 순위 포함 1위); 이고르 티아구 22골 (공동 순위 포함 2위); 앙투안 세메뇨 17골 (공동 순위 포함 3위)

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2025, "metric": "goals", "filters_sql": "", "player_ids": null, "limit": 3, "all_rank_one": false}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 533 | 엘링 홀란드 | value: 27.0, rank: 1 |
| 646 | 이고르 티아구 | value: 22.0, rank: 2 |
| 88 | 앙투안 세메뇨 | value: 17.0, rank: 3 |

## R05 · stored_data · numeric, snapshot, assists

데이터: snapshot. 

### R05-T01

**질문:** 저장된 직전 시즌 EPL 도움 상위 3명을 보여줘.

**기대 답변 예시:** 고정 저장본 기준. 브루노 페르난데스 21도움 (공동 순위 포함 1위); 라얀 셰르키 12도움 (공동 순위 포함 2위); 재러드 보언 11도움 (공동 순위 포함 3위)

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2025, "metric": "assists", "filters_sql": "", "player_ids": null, "limit": 3, "all_rank_one": false}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 6 | 브루노 페르난데스 | value: 21.0, rank: 1 |
| 541 | 라얀 셰르키 | value: 12.0, rank: 2 |
| 420 | 재러드 보언 | value: 11.0, rank: 3 |

## R06 · stored_data · numeric, snapshot, goals

데이터: snapshot. 

### R06-T01

**질문:** 저장본에서 이번 시즌 EPL 엘링 홀란드의 득점·도움·출전 시간을 보여줘.

**기대 답변 예시:** 고정 저장본 기준. 엘링 홀란드: goals=8.0, assists=0.0, minutes=620.0

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "", "player_ids": [533], "limit": null, "all_rank_one": false, "columns": ["goals", "assists", "minutes"]}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 533 | 엘링 홀란드 | goals: 8.0, assists: 0.0, minutes: 620.0 |

## R07 · stored_data · numeric, snapshot, goals

데이터: snapshot. 

### R07-T01

**질문:** 이번 시즌 EPL 기록에서 알렉산더 이삭의 득점과 도움을 보여줘.

**기대 답변 예시:** 고정 저장본 기준. 알렉산더 이삭: goals=5.0, assists=0.0

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "", "player_ids": [210], "limit": null, "all_rank_one": false, "columns": ["goals", "assists"]}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 210 | 알렉산더 이삭 | goals: 5.0, assists: 0.0 |

## R08 · stored_data · numeric, snapshot, goals

데이터: snapshot. 

### R08-T01

**질문:** 이번 시즌 EPL 홀란드와 이삭의 득점·도움을 같은 범위로 비교해줘.

**기대 답변 예시:** 고정 저장본 기준. 알렉산더 이삭: goals=5.0, assists=0.0; 엘링 홀란드: goals=8.0, assists=0.0

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "", "player_ids": [533, 210], "limit": null, "all_rank_one": false, "columns": ["goals", "assists"]}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 210 | 알렉산더 이삭 | goals: 5.0, assists: 0.0 |
| 533 | 엘링 홀란드 | goals: 8.0, assists: 0.0 |

## R09 · stored_data · numeric, snapshot, contributions

데이터: snapshot. 

### R09-T01

**질문:** 저장본에서 이번 시즌 EPL 공격포인트를 골+도움으로 계산해 상위 5명을 보여줘.

**기대 답변 예시:** 고정 저장본 기준. 조아우 페드로 8공격포인트 (공동 순위 포함 1위); 엘링 홀란드 8공격포인트 (공동 순위 포함 1위); 파스칼 그로스 7공격포인트 (공동 순위 포함 3위); 에바니우송 6공격포인트 (공동 순위 포함 4위); 라얀 셰르키 6공격포인트 (공동 순위 포함 4위)

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "contributions", "filters_sql": "", "player_ids": null, "limit": 5, "all_rank_one": false}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 477 | 조아우 페드로 | value: 8.0, rank: 1 |
| 533 | 엘링 홀란드 | value: 8.0, rank: 1 |
| 580 | 파스칼 그로스 | value: 7.0, rank: 3 |
| 94 | 에바니우송 | value: 6.0, rank: 4 |
| 541 | 라얀 셰르키 | value: 6.0, rank: 4 |

## R10 · stored_data · numeric, snapshot, goals

데이터: snapshot. 

### R10-T01

**질문:** 이번 시즌 EPL에서 600분 이상 뛴 선수의 득점 상위 5명은?

**기대 답변 예시:** 고정 저장본 기준. 엘링 홀란드 8골 (공동 순위 포함 1위); 브라이언 음뵈모 4골 (공동 순위 포함 2위); 모건 로저스 4골 (공동 순위 포함 2위); 브루노 페르난데스 3골 (공동 순위 포함 4위); 파스칼 그로스 3골 (공동 순위 포함 4위)

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "minutes >= 600", "player_ids": null, "limit": 5, "all_rank_one": false}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 533 | 엘링 홀란드 | value: 8.0, rank: 1 |
| 25 | 브라이언 음뵈모 | value: 4.0, rank: 2 |
| 745 | 모건 로저스 | value: 4.0, rank: 2 |
| 6 | 브루노 페르난데스 | value: 3.0, rank: 4 |
| 580 | 파스칼 그로스 | value: 3.0, rank: 4 |

## R11 · stored_data · numeric, snapshot, goals

데이터: snapshot. 

### R11-T01

**질문:** 이번 시즌 EPL에서 450분 이상 뛰고 3골 이상 넣은 선수 상위 5명을 득점순으로 보여줘.

**기대 답변 예시:** 고정 저장본 기준. 엘링 홀란드 8골 (공동 순위 포함 1위); 알렉산더 이삭 5골 (공동 순위 포함 2위); 조아우 페드로 5골 (공동 순위 포함 2위); 브라이언 음뵈모 4골 (공동 순위 포함 4위); 마커스 태버니어 4골 (공동 순위 포함 4위)

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "minutes >= 450 AND goals >= 3", "player_ids": null, "limit": 5, "all_rank_one": false}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 533 | 엘링 홀란드 | value: 8.0, rank: 1 |
| 210 | 알렉산더 이삭 | value: 5.0, rank: 2 |
| 477 | 조아우 페드로 | value: 5.0, rank: 2 |
| 25 | 브라이언 음뵈모 | value: 4.0, rank: 4 |
| 87 | 마커스 태버니어 | value: 4.0, rank: 4 |

## R12 · stored_data · numeric, snapshot, per90

데이터: snapshot. 

### R12-T01

**질문:** 이번 시즌 EPL에서 450분 이상 뛴 선수의 90분당 득점 상위 5명은?

**기대 답변 예시:** 고정 저장본 기준. 엘링 홀란드 1.16129골/90분 (공동 순위 포함 1위); 알렉산더 이삭 0.910931골/90분 (공동 순위 포함 2위); 조아우 페드로 0.863724골/90분 (공동 순위 포함 3위); 마커스 태버니어 0.622837골/90분 (공동 순위 포함 4위); 모건 로저스 0.587276골/90분 (공동 순위 포함 5위)

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "per90", "filters_sql": "minutes >= 450", "player_ids": null, "limit": 5, "all_rank_one": false}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 533 | 엘링 홀란드 | value: 1.1612903225806452, rank: 1 |
| 210 | 알렉산더 이삭 | value: 0.9109311740890689, rank: 2 |
| 477 | 조아우 페드로 | value: 0.8637236084452975, rank: 3 |
| 87 | 마커스 태버니어 | value: 0.6228373702422145, rank: 4 |
| 745 | 모건 로저스 | value: 0.5872756933115824, rank: 5 |

## R13 · stored_data · numeric, snapshot, per90

데이터: snapshot. 

### R13-T01

**질문:** 직전 시즌 EPL에서 900분 이상 뛴 선수의 90분당 득점 상위 5명은?

**기대 답변 예시:** 고정 저장본 기준. 엘링 홀란드 0.821501골/90분 (공동 순위 포함 1위); 엘리 주니어 크루피 0.692308골/90분 (공동 순위 포함 2위); 벤야민 세슈코 0.605134골/90분 (공동 순위 포함 3위); 이고르 티아구 0.60091골/90분 (공동 순위 포함 4위); 빅토르 요케레스 0.559006골/90분 (공동 순위 포함 5위)

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2025, "metric": "per90", "filters_sql": "minutes >= 900", "player_ids": null, "limit": 5, "all_rank_one": false}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 533 | 엘링 홀란드 | value: 0.821501014198783, rank: 1 |
| 115 | 엘리 주니어 크루피 | value: 0.6923076923076923, rank: 2 |
| 27 | 벤야민 세슈코 | value: 0.6051344743276283, rank: 3 |
| 646 | 이고르 티아구 | value: 0.6009104704097117, rank: 4 |
| 255 | 빅토르 요케레스 | value: 0.5590062111801242, rank: 5 |

## R14 · stored_data · numeric, snapshot, goals

데이터: snapshot. 

### R14-T01

**질문:** 이번 시즌 EPL에서 900분 이상 뛰고 3골 이상 넣은 선수 5명을 보여줘.

**기대 답변 예시:** 고정 저장본 기준. 지정한 저장 자료와 조건에 맞는 선수가 없습니다.

**기대 행동:** no_matches

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "minutes >= 900 AND goals >= 3", "player_ids": null, "limit": 5, "all_rank_one": false}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| - | 해당 없음 | 결과 0건 |

## R15 · stored_data · numeric, snapshot, assists

데이터: snapshot. 

### R15-T01

**질문:** 이번 시즌 EPL 도움 공동 1위를 모두 보여줘.

**기대 답변 예시:** 고정 저장본 기준. 에바니우송 4도움 (공동 순위 포함 1위); 데클런 라이스 4도움 (공동 순위 포함 1위); 파스칼 그로스 4도움 (공동 순위 포함 1위)

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "assists", "filters_sql": "", "player_ids": null, "limit": null, "all_rank_one": true}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 94 | 에바니우송 | value: 4.0, rank: 1 |
| 236 | 데클런 라이스 | value: 4.0, rank: 1 |
| 580 | 파스칼 그로스 | value: 4.0, rank: 1 |

## R16 · stored_data · numeric, snapshot, goals

데이터: snapshot. 

### R16-T01

**질문:** 이번 시즌 EPL 득점 순위를 최대 100명 보여줘. 같은 득점이면 ID 오름차순으로 표시해줘.

**기대 답변 예시:** 고정 저장본 기준. 엘링 홀란드 8골 (공동 순위 포함 1위); 알렉산더 이삭 5골 (공동 순위 포함 2위); 조아우 페드로 5골 (공동 순위 포함 2위); 브라이언 음뵈모 4골 (공동 순위 포함 4위); 마커스 태버니어 4골 (공동 순위 포함 4위); 라얀 셰르키 4골 (공동 순위 포함 4위); 모건 로저스 4골 (공동 순위 포함 4위); 브루노 페르난데스 3골 (공동 순위 포함 8위); 부카요 사카 3골 (공동 순위 포함 8위); 티에르노 바리 3골 (공동 순위 포함 8위); 페드로 네토 3골 (공동 순위 포함 8위); 잭 힌셜우드 3골 (공동 순위 포함 8위); 코스툴라스 3골 (공동 순위 포함 8위); 파스칼 그로스 3골 (공동 순위 포함 8위); 케빈 샤데 3골 (공동 순위 포함 8위); 도미닉 칼버트르윈 3골 (공동 순위 포함 8위); 브라이언 브로비 3골 (공동 순위 포함 8위); 모하메드 엘바시르 벨루미 3골 (공동 순위 포함 8위); 브루노 기마랑이스 2골 (공동 순위 포함 19위); 안토니 엘랑가 2골 (공동 순위 포함 19위); 조 윌록 2골 (공동 순위 포함 19위); 앙투안 세메뇨 2골 (공동 순위 포함 19위); 에바니우송 2골 (공동 순위 포함 19위); 조슈아 킹 2골 (공동 순위 포함 19위); 마르틴 외데고르 2골 (공동 순위 포함 19위); 카이 하베르츠 2골 (공동 순위 포함 19위); 지안 플레밍 2골 (공동 순위 포함 19위); 키어넌 프랭크 듀스버리-홀 2골 (공동 순위 포함 19위); 콜 파머 2골 (공동 순위 포함 19위); 니콜라스 잭슨 2골 (공동 순위 포함 19위); 막심 더카이퍼 2골 (공동 순위 포함 19위); 야신 아야리 2골 (공동 순위 포함 19위); 타이릭 미첼 2골 (공동 순위 포함 19위); 키언 윌리엄 루이스-포터 2골 (공동 순위 포함 19위); 조던 헨더슨 2골 (공동 순위 포함 19위); 비탈리 야넬트 2골 (공동 순위 포함 19위); 제이든 보글 2골 (공동 순위 포함 19위); 디오 운도예 2골 (공동 순위 포함 19위); 빅토르 무뇨스 2골 (공동 순위 포함 19위); 요한 만잠비 2골 (공동 순위 포함 19위); 라이프 데이비스 2골 (공동 순위 포함 19위); 말릭 준니어 알쿠예 2골 (공동 순위 포함 19위); 잭 에드워드 루도니 2골 (공동 순위 포함 19위); 에메르송 2골 (공동 순위 포함 19위); 마테우스 쿠냐 1골 (공동 순위 포함 45위); 벤야민 세슈코 1골 (공동 순위 포함 45위); 하비어 바른스 1골 (공동 순위 포함 45위); 제이콥 램지 1골 (공동 순위 포함 45위); 스벤 보트만 1골 (공동 순위 포함 45위); 요안 위사 1골 (공동 순위 포함 45위); 루이스 홀 1골 (공동 순위 포함 45위); 저스틴 클라위버르트 1골 (공동 순위 포함 45위); 알렉스 스콧 1골 (공동 순위 포함 45위); 알렉산더 츄카 이워비 1골 (공동 순위 포함 45위); 라이언 세시니온 1골 (공동 순위 포함 45위); 예르겐 스트란드 라르센 1골 (공동 순위 포함 45위); 코디 학포 1골 (공동 순위 포함 45위); 도미니크 소보슬러이 1골 (공동 순위 포함 45위); 리카르도 칼라피오리 1골 (공동 순위 포함 45위); 노니 마두에케 1골 (공동 순위 포함 45위); 제이던 앤서니 1골 (공동 순위 포함 45위); 제임스 타코우스키 1골 (공동 순위 포함 45위); 타이릭 조지 1골 (공동 순위 포함 45위); 벤 데이비스 1골 (공동 순위 포함 45위); 제임스 매디슨 1골 (공동 순위 포함 45위); 도미닉 솔란케 1골 (공동 순위 포함 45위); 루카 부슈코비치 1골 (공동 순위 포함 45위); 코너 갤러거 1골 (공동 순위 포함 45위); 엔소 페르난데스 1골 (공동 순위 포함 45위); 로메오 라비아 1골 (공동 순위 포함 45위); 리암 델랍 1골 (공동 순위 포함 45위); 요슈코 그바르디올 1골 (공동 순위 포함 45위); 필 포든 1골 (공동 순위 포함 45위); 제레미 도쿠 1골 (공동 순위 포함 45위); 오마르 마르무쉬 1골 (공동 순위 포함 45위); 마크 게히 1골 (공동 순위 포함 45위); 스티븐 엠푸니 1골 (공동 순위 포함 45위); 디에고 고메스 1골 (공동 순위 포함 45위); 루이스 덩크 1골 (공동 순위 포함 45위); 얀 폴 판헤케 1골 (공동 순위 포함 45위); 헤페르손 레르마 1골 (공동 순위 포함 45위); 카마다 다이치 1골 (공동 순위 포함 45위); 예레미 피노 1골 (공동 순위 포함 45위); 크리스토페르 아예르 1골 (공동 순위 포함 45위); 파비우 카르발류 1골 (공동 순위 포함 45위); 이고르 티아구 1골 (공동 순위 포함 45위); 예호르 야르몰류크 1골 (공동 순위 포함 45위); 마이클 카요데 1골 (공동 순위 포함 45위); 안톤 스타흐 1골 (공동 순위 포함 45위); 제임스 저스틴 1골 (공동 순위 포함 45위); 노아 오카포 1골 (공동 순위 포함 45위); 이고르 제주스 1골 (공동 순위 포함 45위); 모건 깁스화이트 1골 (공동 순위 포함 45위); 네코 윌리엄스 1골 (공동 순위 포함 45위); 존 맥긴 1골 (공동 순위 포함 45위); 에밀리아노 부엔디아 1골 (공동 순위 포함 45위); 알리송 1골 (공동 순위 포함 45위); 엔조 르 페 1골 (공동 순위 포함 45위); 윌슨 이시도르 1골 (공동 순위 포함 45위); 닐손 앙굴로 1골 (공동 순위 포함 45위)

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "", "player_ids": null, "limit": 100, "all_rank_one": false}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 533 | 엘링 홀란드 | value: 8.0, rank: 1 |
| 210 | 알렉산더 이삭 | value: 5.0, rank: 2 |
| 477 | 조아우 페드로 | value: 5.0, rank: 2 |
| 25 | 브라이언 음뵈모 | value: 4.0, rank: 4 |
| 87 | 마커스 태버니어 | value: 4.0, rank: 4 |
| 541 | 라얀 셰르키 | value: 4.0, rank: 4 |
| 745 | 모건 로저스 | value: 4.0, rank: 4 |
| 6 | 브루노 페르난데스 | value: 3.0, rank: 8 |
| 253 | 부카요 사카 | value: 3.0, rank: 8 |
| 335 | 티에르노 바리 | value: 3.0, rank: 8 |

표는 처음 10행만 표시. 전체 100행과 순서는 cases.json에 수록.

## S01 · edge_fixture · synthetic, boundary, goals

데이터: synthetic. 

### S01-T01

**질문:** 가상 리그 L의 이번 시즌 득점 공동 1위를 모두 보여줘.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 A 10골 (공동 순위 포함 1위); 선수 B 10골 (공동 순위 포함 1위). 해당 지표가 불명인 2명은 순위/해당 지표 산출에서 제외하거나 자료 없음으로 표시합니다.

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "", "player_ids": null, "limit": null, "all_rank_one": true}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 101 | 선수 A | value: 10.0, rank: 1 |
| 102 | 선수 B | value: 10.0, rank: 1 |

## S02 · edge_fixture · synthetic, boundary, per90

데이터: synthetic. 

### S02-T01

**질문:** 가상 리그 L에서 이번 시즌 900분 이상 뛴 선수의 90분당 득점 상위 2명을 보여줘.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 A 1골/90분 (공동 순위 포함 1위); 선수 B 1골/90분 (공동 순위 포함 1위). 해당 지표가 불명인 2명은 순위/해당 지표 산출에서 제외하거나 자료 없음으로 표시합니다.

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "per90", "filters_sql": "minutes >= 900", "player_ids": null, "limit": 2, "all_rank_one": false}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 101 | 선수 A | value: 1.0, rank: 1 |
| 102 | 선수 B | value: 1.0, rank: 1 |

## S03 · edge_fixture · synthetic, boundary, goals

데이터: synthetic. 

### S03-T01

**질문:** 가상 리그 L에서 이번 시즌 900분을 초과해 뛴 선수의 득점 순위를 보여줘.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 H 8골 (공동 순위 포함 1위)

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "minutes > 900", "player_ids": null, "limit": 5, "all_rank_one": false}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 108 | 선수 H | value: 8.0, rank: 1 |

## S04 · edge_fixture · synthetic, boundary, goals

데이터: synthetic. 

### S04-T01

**질문:** 가상 리그 L의 이번 시즌 선수 E는 몇 골이야?

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 E: goals=자료 없음

**기대 행동:** data_unavailable

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "", "player_ids": [105], "limit": null, "all_rank_one": false, "columns": ["goals"]}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 105 | 선수 E | goals: None |

## S05 · edge_fixture · synthetic, boundary, goals

데이터: synthetic. 

### S05-T01

**질문:** 가상 리그 L의 이번 시즌 선수 G는 두 팀을 합쳐 정확히 몇 골이야?

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 G: goals=자료 없음

**기대 행동:** data_unavailable

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "", "player_ids": [107], "limit": null, "all_rank_one": false, "columns": ["goals"]}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 일부 팀의 득점이 NULL이라 정확한 총합은 불명; 알려진 2골을 전체 합계로 단정 금지; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 107 | 선수 G | goals: None |

## S06 · edge_fixture · synthetic, boundary, goals

데이터: synthetic. 

### S06-T01

**질문:** 가상 리그 L의 이번 시즌 선수 A의 두 팀 기록을 합친 골·도움·출전 시간은?

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 A: goals=10.0, assists=6.0, minutes=900.0

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "", "player_ids": [101], "limit": null, "all_rank_one": false, "columns": ["goals", "assists", "minutes"]}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 101 | 선수 A | goals: 10.0, assists: 6.0, minutes: 900.0 |

## S07 · edge_fixture · synthetic, boundary, per90

데이터: synthetic. 

### S07-T01

**질문:** 가상 리그 L에서 이번 시즌 출전 시간이 0보다 큰 선수의 per90 득점 순위를 보여줘.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 C 3골/90분 (공동 순위 포함 1위); 선수 A 1골/90분 (공동 순위 포함 2위); 선수 B 1골/90분 (공동 순위 포함 2위); 선수 D 0.901001골/90분 (공동 순위 포함 4위); 선수 H 0.799112골/90분 (공동 순위 포함 5위). 해당 지표가 불명인 2명은 순위/해당 지표 산출에서 제외하거나 자료 없음으로 표시합니다.

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "per90", "filters_sql": "minutes > 0", "player_ids": null, "limit": 8, "all_rank_one": false}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 103 | 선수 C | value: 3.0, rank: 1 |
| 101 | 선수 A | value: 1.0, rank: 2 |
| 102 | 선수 B | value: 1.0, rank: 2 |
| 104 | 선수 D | value: 0.9010011123470523, rank: 4 |
| 108 | 선수 H | value: 0.7991120976692564, rank: 5 |

## S08 · edge_fixture · synthetic, boundary, goals

데이터: synthetic. 

### S08-T01

**질문:** 가상 리그 L에서 이번 시즌 22세 이하 선수의 득점 순위를 보여줘.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 A 10골 (공동 순위 포함 1위); 선수 D 9골 (공동 순위 포함 2위); 선수 H 8골 (공동 순위 포함 3위). 해당 지표가 불명인 1명은 순위/해당 지표 산출에서 제외하거나 자료 없음으로 표시합니다.

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "age <= 22", "player_ids": null, "limit": 5, "all_rank_one": false}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 101 | 선수 A | value: 10.0, rank: 1 |
| 104 | 선수 D | value: 9.0, rank: 2 |
| 108 | 선수 H | value: 8.0, rank: 3 |

## S09 · edge_fixture · synthetic, boundary, goals

데이터: synthetic. 

### S09-T01

**질문:** 가상 리그 L의 이번 시즌에서 100골 이상인 선수를 찾아줘.

**기대 답변 예시:** 가상 시험 데이터 기준. 지정한 저장 자료와 조건에 맞는 선수가 없습니다.

**기대 행동:** no_matches

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "goals >= 100", "player_ids": null, "limit": 5, "all_rank_one": false}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| - | 해당 없음 | 결과 0건 |

## B01 · behavior · behavior, ambiguity_or_coverage

데이터: snapshot. data_unavailable refers to this packaged evaluation dataset, not a claim about every production table

### B01-T01

**질문:** 요새 가장 폼 좋은 선수 누구야?

**기대 답변 예시:** 어느 리그와 기간을 볼까요? 폼은 득점·도움 등 어떤 기준으로 비교할까요?

**기대 행동:** clarification_required

**필수 상태:** `{}`

**확인할 정보:** league, window, metric

**통과 조건:** 리그·기간·지표의 미확정 상태 인식; 공통 필수 채점 통과.

**실패 조건:** 근거 없는 선수·수치·시즌 확정.

## B02 · behavior · behavior, ambiguity_or_coverage

데이터: snapshot. data_unavailable refers to this packaged evaluation dataset, not a claim about every production table

### B02-T01

**질문:** 수비가 제일 단단한 팀은?

**기대 답변 예시:** 어느 대회와 기간을 볼까요? 실점, 클린시트 등 어떤 기준인지 정해야 합니다. 이 평가 자료에는 팀 수비 기록이 없습니다.

**기대 행동:** clarification_required

**필수 상태:** `{}`

**확인할 정보:** league, window, defensive_metric

**통과 조건:** 모호한 수비 정의; 팀 수비 자료 미제공; 공통 필수 채점 통과.

**실패 조건:** xGA나 실점을 창작; 공격 지표로 몰래 대체.

## B03 · behavior · behavior, ambiguity_or_coverage

데이터: snapshot. data_unavailable refers to this packaged evaluation dataset, not a claim about every production table

### B03-T01

**질문:** 이번 시즌 EPL에서 xG보다 실제 골이 훨씬 많은 선수는?

**기대 답변 예시:** 현재 평가 자료에는 xG가 없어 차이를 계산할 수 없습니다. 또한 훨씬 많다는 차이 기준이 필요합니다.

**기대 행동:** data_unavailable

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals_minus_xg"}`

**통과 조건:** xG 미제공; 차이 임계값 미정; 공통 필수 채점 통과.

**실패 조건:** 선수/수치 창작; 운 또는 결정력 원인 단정.

## B04 · behavior · behavior, alias

데이터: snapshot. data_unavailable refers to this packaged evaluation dataset, not a claim about every production table

### B04-T01

**질문:** 흥민이 골 몇 개?

**기대 답변 예시:** 손흥민 선수를 말씀하시는 건가요? 어느 시즌과 대회의 득점을 원하시나요?

**기대 행동:** clarification_required

**필수 상태:** `{}`

**확인할 정보:** season, league

**통과 조건:** 이름 확인 또는 검증된 별칭 연결; 시즌·대회 확인; 공통 필수 채점 통과.

**실패 조건:** 현재 팀/시즌 자동 확정; 0골이라고 추측.

## B05 · behavior · behavior, alias

데이터: snapshot. data_unavailable refers to this packaged evaluation dataset, not a claim about every production table

### B05-T01

**질문:** 할란드 이번 시즌 EPL 득점은?

**기대 답변 예시:** 고정 저장본 기준. 엘링 홀란드: goals=8.0

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "", "player_ids": [533], "limit": null, "all_rank_one": false, "columns": ["goals"]}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 533 | 엘링 홀란드 | goals: 8.0 |

## B06 · behavior · behavior, ambiguity_or_coverage

데이터: snapshot. data_unavailable refers to this packaged evaluation dataset, not a claim about every production table

### B06-T01

**질문:** 손흥민 다음 시즌 몇 골 넣을까?

**기대 답변 예시:** 미래 득점은 저장된 기록에서 확정 조회할 수 없습니다. 이 검색 평가 범위는 기록 조회이며 예측 수치를 제공하지 않습니다.

**기대 행동:** unsupported

**필수 상태:** `{}`

**통과 조건:** 미래 예측과 기록 조회 구별; 공통 필수 채점 통과.

**실패 조건:** 예측을 사실처럼 제시; 임의 숫자 생성.

## B07 · behavior · behavior, ambiguity_or_coverage

데이터: snapshot. data_unavailable refers to this packaged evaluation dataset, not a claim about every production table

### B07-T01

**질문:** 2030 월드컵 우승팀은?

**기대 답변 예시:** 평가 기준 시점인 2026년 10월에는 2030 월드컵 우승팀이 확정되지 않았습니다.

**기대 행동:** unsupported

**필수 상태:** `{"reference_year": 2026}`

**통과 조건:** 아직 결정되지 않은 미래 사실; 공통 필수 채점 통과.

**실패 조건:** 특정 팀을 우승팀으로 확정.

## B08 · behavior · behavior, ambiguity_or_coverage

데이터: snapshot. data_unavailable refers to this packaged evaluation dataset, not a claim about every production table

### B08-T01

**질문:** 아르테타 부임 전후로 아스날 실점이 얼마나 줄었어?

**기대 답변 예시:** 이 평가 자료에는 부임 전후를 비교할 역사 자료와 팀 실점 기록이 없습니다. 비교 기간과 경기당 기준도 필요하며 차이를 감독 효과로 단정할 수 없습니다.

**기대 행동:** data_unavailable

**필수 상태:** `{}`

**통과 조건:** 역사 자료 및 팀 지표 부재; 비교 범위 확인 필요; 공통 필수 채점 통과.

**실패 조건:** 최신 2시즌만으로 부임 전후를 대체; 인과 효과 단정.

## M01 · multi_turn · coreference, old_result, ambiguity, partial_data

데이터: synthetic. 

### M01-T01

**질문:**  가상 리그 L 이번 시즌 득점 상위 3명을 표시해줘.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 A 10골 (공동 순위 포함 1위); 선수 B 10골 (공동 순위 포함 1위); 선수 D 9골 (공동 순위 포함 3위). 해당 지표가 불명인 2명은 순위/해당 지표 산출에서 제외하거나 자료 없음으로 표시합니다.

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "", "player_ids": null, "limit": 3, "all_rank_one": false}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 101 | 선수 A | value: 10.0, rank: 1 |
| 102 | 선수 B | value: 10.0, rank: 1 |
| 104 | 선수 D | value: 9.0, rank: 3 |

### M01-T02

**질문:** 표에서 두 번째와 세 번째 선수만 골과 도움을 비교해줘.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 B: goals=10.0, assists=5.0; 선수 D: goals=9.0, assists=2.0

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "", "player_ids": [102, 104], "limit": null, "all_rank_one": false, "columns": ["goals", "assists"]}`

**상태 변경:** `{"refer": "turn1.display_rows[2,3]"}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 102 | 선수 B | goals: 10.0, assists: 5.0 |
| 104 | 선수 D | goals: 9.0, assists: 2.0 |

### M01-T03

**질문:** 둘 중 최근 5경기 폼이 더 좋은 선수는?

**기대 답변 예시:** 선수 B와 D를 비교하는 요청으로 이해했습니다. 폼의 지표를 정해야 하고, 이 시험 자료에는 최근 5경기 기록이 없습니다.

**기대 행동:** clarification_required

**필수 상태:** `{"player_ids": [102, 104], "window": "last_5_matches"}`

**확인할 정보:** form_metric

**통과 조건:** 선수 B·D 유지; 지표 확인; 경기별 자료 없음; 공통 필수 채점 통과.

**실패 조건:** 시즌 합계로 최근 5경기를 대체; 승자 추측.

### M01-T04

**질문:** 그럼 시즌 도움으로 비교해줘.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 B: assists=5.0; 선수 D: assists=2.0

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "", "player_ids": [102, 104], "limit": null, "all_rank_one": false, "columns": ["assists"]}`

**상태 변경:** `{"replace": "window=season, metric=assists", "preserve": "players=[102,104]"}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 102 | 선수 B | assists: 5.0 |
| 104 | 선수 D | assists: 2.0 |

### M01-T05

**질문:** 처음 표의 첫 번째 선수도 넣어줘.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 A: assists=6.0; 선수 B: assists=5.0; 선수 D: assists=2.0

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "", "player_ids": [101, 102, 104], "limit": null, "all_rank_one": false, "columns": ["assists"]}`

**상태 변경:** `{"add_player_from": "turn1.display_row[1]"}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 101 | 선수 A | assists: 6.0 |
| 102 | 선수 B | assists: 5.0 |
| 104 | 선수 D | assists: 2.0 |

## M02 · multi_turn · filter_accumulation, unavailable_sort

데이터: synthetic. 

### M02-T01

**질문:** 가상 리그 L 이번 시즌 도움 상위 8명 보여줘.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 A 6도움 (공동 순위 포함 1위); 선수 B 5도움 (공동 순위 포함 2위); 선수 H 4도움 (공동 순위 포함 3위); 선수 G 3도움 (공동 순위 포함 4위); 선수 D 2도움 (공동 순위 포함 5위); 선수 E 1도움 (공동 순위 포함 6위); 선수 C 0도움 (공동 순위 포함 7위); 선수 F 0도움 (공동 순위 포함 7위)

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "assists", "filters_sql": "", "player_ids": null, "limit": 8, "all_rank_one": false}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 101 | 선수 A | value: 6.0, rank: 1 |
| 102 | 선수 B | value: 5.0, rank: 2 |
| 108 | 선수 H | value: 4.0, rank: 3 |
| 107 | 선수 G | value: 3.0, rank: 4 |
| 104 | 선수 D | value: 2.0, rank: 5 |
| 105 | 선수 E | value: 1.0, rank: 6 |
| 103 | 선수 C | value: 0.0, rank: 7 |
| 106 | 선수 F | value: 0.0, rank: 7 |

### M02-T02

**질문:** 미드필더만 남겨줘.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 A 6도움 (공동 순위 포함 1위); 선수 B 5도움 (공동 순위 포함 2위); 선수 H 4도움 (공동 순위 포함 3위); 선수 E 1도움 (공동 순위 포함 4위); 선수 F 0도움 (공동 순위 포함 5위)

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "assists", "filters_sql": "position='미드필더'", "player_ids": null, "limit": 8, "all_rank_one": false}`

**상태 변경:** `{"add": "position=midfielder"}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 101 | 선수 A | value: 6.0, rank: 1 |
| 102 | 선수 B | value: 5.0, rank: 2 |
| 108 | 선수 H | value: 4.0, rank: 3 |
| 105 | 선수 E | value: 1.0, rank: 4 |
| 106 | 선수 F | value: 0.0, rank: 5 |

### M02-T03

**질문:** 25세 이하로 좁혀줘.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 A 6도움 (공동 순위 포함 1위); 선수 B 5도움 (공동 순위 포함 2위); 선수 H 4도움 (공동 순위 포함 3위); 선수 E 1도움 (공동 순위 포함 4위); 선수 F 0도움 (공동 순위 포함 5위)

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "assists", "filters_sql": "position='미드필더' AND age <= 25", "player_ids": null, "limit": 8, "all_rank_one": false}`

**상태 변경:** `{"add": "age<=25", "preserve": "position"}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 101 | 선수 A | value: 6.0, rank: 1 |
| 102 | 선수 B | value: 5.0, rank: 2 |
| 108 | 선수 H | value: 4.0, rank: 3 |
| 105 | 선수 E | value: 1.0, rank: 4 |
| 106 | 선수 F | value: 0.0, rank: 5 |

### M02-T04

**질문:** 시험 데이터의 빅6 소속 표시가 있는 선수는 제외해줘.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 B 5도움 (공동 순위 포함 1위); 선수 H 4도움 (공동 순위 포함 2위); 선수 E 1도움 (공동 순위 포함 3위)

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "assists", "filters_sql": "position='미드필더' AND age <= 25 AND big6=0", "player_ids": null, "limit": 8, "all_rank_one": false}`

**상태 변경:** `{"add": "big6=false", "preserve": "position,age"}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 102 | 선수 B | value: 5.0, rank: 1 |
| 108 | 선수 H | value: 4.0, rank: 2 |
| 105 | 선수 E | value: 1.0, rank: 3 |

### M02-T05

**질문:** 남은 선수들을 이적료 순으로 정렬해줘.

**기대 답변 예시:** 선수 B, H, E의 필터 범위는 유지됩니다. 이적료가 제공되지 않아 이적료 순으로 정렬할 수 없습니다.

**기대 행동:** data_unavailable

**필수 상태:** `{"player_ids": [102, 108, 105], "position": "미드필더", "age_lte": 25, "big6": false, "requested_sort": "transfer_fee"}`

**통과 조건:** 남은 후보 보존; 이적료 미제공; 공통 필수 채점 통과.

**실패 조건:** 도움순을 이적료순이라고 표시; 필터 초기화.

## M03 · multi_turn · partial_edit, remove, old_result, reset_selection

데이터: synthetic. 

### M03-T01

**질문:** 가상 리그 L 이번 시즌 900분 이상 선수의 득점 상위 5명.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 A 10골 (공동 순위 포함 1위); 선수 B 10골 (공동 순위 포함 1위); 선수 H 8골 (공동 순위 포함 3위). 해당 지표가 불명인 2명은 순위/해당 지표 산출에서 제외하거나 자료 없음으로 표시합니다.

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "minutes >= 900", "player_ids": null, "limit": 5, "all_rank_one": false}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 101 | 선수 A | value: 10.0, rank: 1 |
| 102 | 선수 B | value: 10.0, rank: 1 |
| 108 | 선수 H | value: 8.0, rank: 3 |

### M03-T02

**질문:** 그중 22세 이하만.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 A 10골 (공동 순위 포함 1위); 선수 H 8골 (공동 순위 포함 2위). 해당 지표가 불명인 1명은 순위/해당 지표 산출에서 제외하거나 자료 없음으로 표시합니다.

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "minutes >= 900 AND age <= 22", "player_ids": null, "limit": 5, "all_rank_one": false}`

**상태 변경:** `{"add": "age<=22"}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 101 | 선수 A | value: 10.0, rank: 1 |
| 108 | 선수 H | value: 8.0, rank: 2 |

### M03-T03

**질문:** 나이 조건만 빼고 도움순으로 바꿔줘.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 A 6도움 (공동 순위 포함 1위); 선수 B 5도움 (공동 순위 포함 2위); 선수 H 4도움 (공동 순위 포함 3위); 선수 G 3도움 (공동 순위 포함 4위); 선수 E 1도움 (공동 순위 포함 5위)

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "assists", "filters_sql": "minutes >= 900", "player_ids": null, "limit": 5, "all_rank_one": false}`

**상태 변경:** `{"remove": "age", "replace": "metric=assists", "preserve": "minutes>=900"}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 101 | 선수 A | value: 6.0, rank: 1 |
| 102 | 선수 B | value: 5.0, rank: 2 |
| 108 | 선수 H | value: 4.0, rank: 3 |
| 107 | 선수 G | value: 3.0, rank: 4 |
| 105 | 선수 E | value: 1.0, rank: 5 |

### M03-T04

**질문:** 아까 22세 이하 득점 표의 첫 번째 선수 골·도움은?

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 A: goals=10.0, assists=6.0

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "", "player_ids": [101], "limit": null, "all_rank_one": false, "columns": ["goals", "assists"]}`

**상태 변경:** `{"refer": "turn2.display_row[1]"}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 101 | 선수 A | goals: 10.0, assists: 6.0 |

### M03-T05

**질문:** 선수 제한을 없애고 출전 시간 조건도 빼서 전체 득점 상위 5명으로 돌아가자.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 A 10골 (공동 순위 포함 1위); 선수 B 10골 (공동 순위 포함 1위); 선수 D 9골 (공동 순위 포함 3위); 선수 H 8골 (공동 순위 포함 4위); 선수 C 3골 (공동 순위 포함 5위). 해당 지표가 불명인 2명은 순위/해당 지표 산출에서 제외하거나 자료 없음으로 표시합니다.

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "", "player_ids": null, "limit": 5, "all_rank_one": false}`

**상태 변경:** `{"remove": "player_ids,minutes", "replace": "metric=goals", "preserve": "league,season"}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 101 | 선수 A | value: 10.0, rank: 1 |
| 102 | 선수 B | value: 10.0, rank: 1 |
| 104 | 선수 D | value: 9.0, rank: 3 |
| 108 | 선수 H | value: 8.0, rank: 4 |
| 103 | 선수 C | value: 3.0, rank: 5 |

## M04 · multi_turn · entity_transition, no_antecedent, coverage

데이터: synthetic. Unsupported-path test. Does not establish positive team→fixture→player traversal capability; a fixture-event dataset is required for that.

### M04-T01

**질문:** 토트넘 최근 경기 결과 알려줘.

**기대 답변 예시:** 이 평가 자료에는 토트넘 경기 목록과 결과가 없습니다.

**기대 행동:** data_unavailable

**필수 상태:** `{"team": "토트넘"}`

**통과 조건:** 경기 자료 없음; 공통 필수 채점 통과.

**실패 조건:** 가상 경기 생성.

### M04-T02

**질문:** 그 경기 득점자는?

**기대 답변 예시:** 앞서 특정 경기를 제공하지 못했습니다. 어느 경기를 뜻하나요? 이 평가 자료에는 득점 이벤트도 없습니다.

**기대 행동:** clarification_required

**필수 상태:** `{}`

**확인할 정보:** fixture

**통과 조건:** 참조할 경기 없음; 이벤트 자료 미제공; 공통 필수 채점 통과.

**실패 조건:** 경기를 임의 선택; 득점자 창작.

### M04-T03

**질문:** 그 선수 이번 시즌 몇 골이야?

**기대 답변 예시:** 앞선 대화에서 특정 득점자가 확정되지 않았습니다. 선수와 대회를 알려주세요.

**기대 행동:** clarification_required

**필수 상태:** `{}`

**확인할 정보:** player, league

**통과 조건:** 선수 미확정; 공통 필수 채점 통과.

**실패 조건:** 유명 토트넘 선수를 자동 선택.

## M05 · multi_turn · vague_metric, clarification, metric_change

데이터: synthetic. 

### M05-T01

**질문:** 가상 리그 L 이번 시즌 잘나가는 선수 누구야?

**기대 답변 예시:** 잘나간다는 기준을 득점, 도움 등 어떤 지표로 볼까요?

**기대 행동:** clarification_required

**필수 상태:** `{"league_id": 1, "season_year": 2026}`

**확인할 정보:** metric

**통과 조건:** 평가 지표 확인; 공통 필수 채점 통과.

**실패 조건:** 승자 임의 선택.

### M05-T02

**질문:** 도움 기준으로 미드필더만 봐줘.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 A 6도움 (공동 순위 포함 1위); 선수 B 5도움 (공동 순위 포함 2위); 선수 H 4도움 (공동 순위 포함 3위); 선수 E 1도움 (공동 순위 포함 4위); 선수 F 0도움 (공동 순위 포함 5위)

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "assists", "filters_sql": "position='미드필더'", "player_ids": null, "limit": 8, "all_rank_one": false}`

**상태 변경:** `{"set": "metric=assists,position=midfielder"}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 101 | 선수 A | value: 6.0, rank: 1 |
| 102 | 선수 B | value: 5.0, rank: 2 |
| 108 | 선수 H | value: 4.0, rank: 3 |
| 105 | 선수 E | value: 1.0, rank: 4 |
| 106 | 선수 F | value: 0.0, rank: 5 |

### M05-T03

**질문:** 도움 말고 골과 도움을 더한 공격포인트 상위 3명으로.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 A 16공격포인트 (공동 순위 포함 1위); 선수 B 15공격포인트 (공동 순위 포함 2위); 선수 H 12공격포인트 (공동 순위 포함 3위). 해당 지표가 불명인 1명은 순위/해당 지표 산출에서 제외하거나 자료 없음으로 표시합니다.

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "contributions", "filters_sql": "position='미드필더'", "player_ids": null, "limit": 3, "all_rank_one": false}`

**상태 변경:** `{"replace": "metric=goals+assists,limit=3", "preserve": "position"}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 101 | 선수 A | value: 16.0, rank: 1 |
| 102 | 선수 B | value: 15.0, rank: 2 |
| 108 | 선수 H | value: 12.0, rank: 3 |

### M05-T04

**질문:** 기간을 최근 10경기로 바꿔줘.

**기대 답변 예시:** 미드필더와 골+도움 기준은 유지하지만 경기별 기록이 없어 최근 10경기를 계산할 수 없습니다.

**기대 행동:** data_unavailable

**필수 상태:** `{"position": "미드필더", "metric": "contributions", "window": "last_10_matches"}`

**통과 조건:** 기존 지표·포지션 보존; 경기별 자료 없음; 공통 필수 채점 통과.

**실패 조건:** 시즌 합계를 최근 10경기로 표시.

## M06 · multi_turn · comparison, season_change, add_remove

데이터: synthetic. 

### M06-T01

**질문:** 가상 리그 L 이번 시즌 선수 A와 B의 득점·도움 비교.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 A: goals=10.0, assists=6.0; 선수 B: goals=10.0, assists=5.0

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "", "player_ids": [101, 102], "limit": null, "all_rank_one": false, "columns": ["goals", "assists"]}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 101 | 선수 A | goals: 10.0, assists: 6.0 |
| 102 | 선수 B | goals: 10.0, assists: 5.0 |

### M06-T02

**질문:** 직전 시즌은?

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 A: goals=12.0, assists=3.0; 선수 B: goals=8.0, assists=7.0

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2025, "metric": "goals", "filters_sql": "", "player_ids": [101, 102], "limit": null, "all_rank_one": false, "columns": ["goals", "assists"]}`

**상태 변경:** `{"replace": "season=2025", "preserve": "players,metrics"}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 101 | 선수 A | goals: 12.0, assists: 3.0 |
| 102 | 선수 B | goals: 8.0, assists: 7.0 |

### M06-T03

**질문:** 선수 H도 추가해줘.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 A: goals=12.0, assists=3.0; 선수 B: goals=8.0, assists=7.0; 선수 H: goals=9.0, assists=6.0

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2025, "metric": "goals", "filters_sql": "", "player_ids": [101, 102, 108], "limit": null, "all_rank_one": false, "columns": ["goals", "assists"]}`

**상태 변경:** `{"add": "player=108", "preserve": "season=2025"}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 101 | 선수 A | goals: 12.0, assists: 3.0 |
| 102 | 선수 B | goals: 8.0, assists: 7.0 |
| 108 | 선수 H | goals: 9.0, assists: 6.0 |

### M06-T04

**질문:** B는 빼고 둘의 도움만 보여줘.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 A: assists=3.0; 선수 H: assists=6.0

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2025, "metric": "goals", "filters_sql": "", "player_ids": [101, 108], "limit": null, "all_rank_one": false, "columns": ["assists"]}`

**상태 변경:** `{"remove": "player=102", "replace": "columns=assists", "preserve": "season=2025"}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 101 | 선수 A | assists: 3.0 |
| 108 | 선수 H | assists: 6.0 |

## M07 · multi_turn · correction, unsupported_metric, fallback_with_consent

데이터: synthetic. Explicit user correction, not a measured model-failure recovery score.

### M07-T01

**질문:** 가상 선수 A와 B 중 누구 도움 기록이야?

**기대 답변 예시:** A와 B 중 어느 선수이며 어느 시즌을 뜻하나요?

**기대 행동:** clarification_required

**필수 상태:** `{}`

**확인할 정보:** player, season

**통과 조건:** 선수와 시즌 확인; 공통 필수 채점 통과.

**실패 조건:** 대상을 임의 확정.

### M07-T02

**질문:** 선수 A, 이번 시즌 리그 L이야.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 A: assists=6.0

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "", "player_ids": [101], "limit": null, "all_rank_one": false, "columns": ["assists"]}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 101 | 선수 A | assists: 6.0 |

### M07-T03

**질문:** 아니, A 말고 선수 B로 정정할게.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 B: assists=5.0

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "", "player_ids": [102], "limit": null, "all_rank_one": false, "columns": ["assists"]}`

**상태 변경:** `{"replace": "player=102", "preserve": "season,league,metric"}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 102 | 선수 B | assists: 5.0 |

### M07-T04

**질문:** B의 기대 도움은?

**기대 답변 예시:** 선수 B의 같은 시즌·리그 요청입니다. 기대 도움(xA)은 이 자료에 없습니다.

**기대 행동:** data_unavailable

**필수 상태:** `{"player_ids": [102], "season_year": 2026, "league_id": 1, "metric": "xA"}`

**통과 조건:** 대상·범위 보존; xA 미제공; 공통 필수 채점 통과.

**실패 조건:** 실제 도움을 기대 도움이라고 표시.

### M07-T05

**질문:** 그럼 실제 도움으로 돌아가줘.

**기대 답변 예시:** 가상 시험 데이터 기준. 선수 B: assists=5.0

**기대 행동:** results

**필수 상태:** `{"league_id": 1, "season_year": 2026, "metric": "goals", "filters_sql": "", "player_ids": [102], "limit": null, "all_rank_one": false, "columns": ["assists"]}`

**상태 변경:** `{"replace": "metric=assists", "preserve": "player=102,season,league"}`

**통과 조건:** 기준 자료의 범위; 정답의 대상·수치·단위·요청 순서; 공통 필수 채점 통과.

**실패 조건:** 다른 시즌/대회로 대체; NULL을 0으로 처리; 생성 문구로 수치를 대체.

**정답 데이터:**

| ID | 선수 | 값 |
|---|---|---|
| 102 | 선수 B | assists: 5.0 |

