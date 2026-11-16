> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `news-context` 워크트리의 `docs/ax/news-context/query-catalog-v1.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 문맥 조회 의도·지표·DB 근거 사전 v1

설계안. R05/R06을 기본정보 카드로 축소하지 않고 조회·검증 가능한 계약으로 구체화한다. 실제 ORM 컬럼은 확인했고, JSON 경로별 coverage·이력 적재·실제 수치 정답은 아직 준비 중이다. API 경로/DDL/미확인 외부 응답 모델은 이 문서에서 구현하지 않는다.

## 1. 모든 조회에 필요한 조건

`intent, entity_ids, metric_keys, reference_time, timezone, competition_ids, seasons, window, counting_unit, source_span, applied_decisions`를 명시한다. 미확정 조건은 비워 둔 채 확인 대상으로 반환하고 모델이 채운 조건을 사용자 제공 사실로 표시하지 않는다.

- 시간 기준: 원문 명시 시각·사용자 확인 기준일을 사용한다. '어제'는 기준일과 시간대가 있어야 한다. 경기 조회는 킥오프 시각과 종료 상태를 함께 적용한다.
- 최근 N경기: `팀 경기`와 `선수 출전 경기`를 구분한다. 표기가 없으면 확인 대상으로 두며 집계 단위를 조용히 선택하지 않는다.
- 최신 2시즌: 대회별 실제 현재·직전 시즌과 대조한다. 수집의 활성 상태와 DB에 수록된 대회 범위는 별개로 기록한다. 연도만 보고 2022를 일괄 제외하지 않는다.
- 값 의미: 0/NULL/미수집/범위 밖을 구분한다. 경기 목록·출전 판단·지표 표본 수를 함께 반환하며 부분 표본 합계를 전체 N경기 합계로 표시하지 않는다.
- 사실 기준: `updated_at/fetched_at`은 자료 시각이고 사건 발생일/기준일과 다르다. 현재 프로필·시즌 합계·순위를 과거 시점의 값으로 제시하지 않는다.
- 종료 경기: FT/AET/PEN을 구분하고 정규시간/연장/승부차기를 표시한다. 승부차기 득점을 선수 득점이나 정규시간 스코어에 합치지 않는다. DB score 필드의 실제 의미는 정답 작성 시 검증한다.

## 2. 의도 목록

| 의도 ID | 문맥/출력 | DB 근거 | 집계·확인 기준 / 현재 준비 |
|---|---|---|---|
| Q01 entity_profile | 팀·선수·감독·리그 기본정보 | 해당 entity와 4종 translation, team_season/team_coach | 현재 정보와 당시 정보를 구분. 감독 번역은 기존 테이블 활용 |
| Q02 player_match_metrics | 특정 경기의 선수 기록 | fixture_detail.players + fixture | 실제 선수 external ID, 해당 경기·팀, games/goals/cards 등 검증 경로. NULL 보존. JSON coverage 필요 |
| Q03 player_recent_metrics | 최근 N경기/출전의 득점·도움·분·카드 등 | Q02 + fixture + 시즌/소속 관계 | 출전 인정과 팀 경기 단위를 구분. 골/도움이 0이어도 출전할 수 있음. 누락 경기·분모 표시 |
| Q04 player_season_metrics | 대회·시즌의 선수 합계 | player_season_stat | grain=선수×팀×대회×시즌. 이적 선수의 복수 팀 행을 명시적으로 합치며 중복/다른 대회 합산 금지 |
| Q05 period_comparison | 지난 시즌/직전 기간보다 증가 | Q02~Q04의 같은 지표·단위 | 시즌 전체 vs 같은 경기 수/같은 시점 구분. 평균·비율의 분모와 비교 기간 명시 |
| Q06 fixture_result | 특정 대진·승패·관련 경기 | fixture + league/team 번역, fixture_detail | 대진·날짜·대회 후보를 좁힘. 정규시간/연장/승부차기와 원문 주장 구분 |
| Q07 head_to_head | 두 팀 상대전적 | 수록 범위 내 fixture | 같은 범위의 종료 경기 목록과 승/무/패. 수록 2시즌 기록을 역대 전체 전적으로 표현하지 않음 |
| Q08 standings | 대회·그룹 순위·승점 | standings | league/season/group/team grain. 현재 저장 순위만 있는 경우 과거 순위라고 표시하지 않음 |
| Q09 team_form | 최근 흐름·연승·득실 | fixture + 필요 시 fixture_detail.statistics | 기간·대회·홈/원정·종료 상태·알려진 경기 수. 미수집/진행 중 경기를 건너뛰어 연속 기록을 부풀리지 않음 |
| Q10 team_match_metrics | 경기 점유율·슈팅·패스 등 | fixture_detail.statistics | type/팀/단위/%/NULL을 명시 매핑. 평균·비율 합산 금지. JSON coverage 필요 |
| Q11 affiliation_observation | 해당 시즌 소속·감독 관측 | player_season_stat/team_season, fixture_detail.lineups, team_coach | 현재 팀으로 과거 소속 덮어쓰기 금지. first_seen/last_seen은 관측 시각이며 공식 취임/퇴임일이 아님 |
| Q12 transfer_history | 이적 날짜·전/후 팀·유형 | transfer + player/team | 현재 0행: 적재 선행 작업 필수. transfer에 season/league 컬럼이 없어 기존 시즌 정책에 맞는 날짜·대회 관계의 판정 근거도 준비 |
| Q13 injury_history | 경기/시즌의 부상·결장 근거 | injury + fixture/player/team/league | 현재 0행: 적재 선행 작업 필수. reported_at을 부상 발생일로 바꾸거나 player.injured 하나로 원인·기간 창작 금지 |

Q02~Q05, Q10의 지표는 득점·도움만으로 닫지 않는다. 아래 사전에 현재 확인 가능한 항목을 명시하고 실제 JSON/외부 coverage가 확인된 지표를 추가한다. 문장에 필요한 지표를 발견하면 대응·데이터 의존성을 기록하고 필수 검증에서 조용히 제외하지 않는다.

## 3. 지표 사전과 집계

| 지표 묶음 | DB 경로/컬럼 | 의미·집계 규칙 |
|---|---|---|
| 시즌 출전·분 | player_season_stat.appearances/minutes | 해당 대회·팀·시즌 합계. 전체 출전과 선발/교체는 같지 않음 |
| 시즌 득점·도움·카드 | goals/assists/yellow_cards/red_cards | 같은 grain에서 합산. NULL 포함 시 불완전 상태와 알려진 부분값을 구분 |
| 시즌 평점 | rating, raw_stats | 관측 평균. 여러 팀/경기 평균을 단순 평균해 합산하지 않음. 가중 근거가 없으면 행별 표시 |
| 경기 출전·분·득점·도움 | fixture_detail.players의 player.id 및 statistics[].games/goals | 현재 코드에서 읽는 경로: games.minutes, goals.total/assists. 출전 여부는 lineups·bench/선발·분 필드 의미를 검증하며 득점>0을 출전 조건으로 쓰지 않음 |
| 공격포인트 | 검증된 득점+도움 | 같은 경기·대회·시점·분모에서만 더함. 어느 항목이 NULL이면 완전 합계처럼 표시하지 않음 |
| 슈팅·유효슈팅·패스·태클·드리블·카드·세이브 등 | fixture_detail.players 및 player_season_stat.raw_stats | 외부 실제 payload와 적재 JSON의 경로/단위/coverage를 조사해 명시 매핑. 모델의 임의 JSON 탐색을 실행하지 않음 |
| 팀 경기 통계 | fixture_detail.statistics | type별 값·백분율·대상 팀을 검증. 알려지지 않은 type을 모델이 기존 지표로 바꾸지 않음 |
| xG 등 새 지표 | 실제 DB/수집 근거 확인 후 결정 | DB에 없으면 '해당 기록 없음'을 명시. 사용자 목표의 필수 지표로 확정되면 의존성을 해결하기 전 미완료 |

같은 단위의 완전한 표본만 전체 합계·평균·증감이라고 표시한다. 표본 일부의 값을 제시할 때는 '자료가 확인된 M경기 합계, 요청 N경기 중 K경기 누락'처럼 범위를 드러낸다. 자동 생성한 한국어 해석에 DB로 확인되지 않은 수치/날짜를 추가하지 않는다.

## 4. 선행 데이터 작업과 판정

- DATA-1: 활성 리그·실제 시즌·endpoint coverage와 실제 payload를 API-Football MCP로 확인한 뒤 워커 변경을 별도 작업 계약으로 정의한다. 이 뉴스 화면의 API에서 API-Football을 직접 호출하지 않는다.
- DATA-2: transfer/injury 적재·외부 ID 관계·누락/중복/재시작·최신 2시즌 정책을 검증한다. 대상은 전체 1,250개 팀 수로 단정하지 않고 활성 수집 대상에서 산정한다. 호출 semaphore는 기존 6, 재시도 규칙은 기존 워커 정책을 따른다.
- DATA-3: fixture_detail/player_season_stat의 지표별 `present/null/missing` 및 실제 출전/팀/대회/시즌 범위를 관찰한다. JSON non-NULL 행수만으로 충족 처리하지 않는다.
- DATA-4: 과거 시점의 기록·순위·소속을 재구성할 수 있는 범위를 구분한다. 재구성이 불가능한 값은 해당 시점 자료 없음으로 표시하고 현재 값을 과거 사실로 사용하지 않는다.

필수 의도별로 자료 있는 실제 사례의 정상 연결과 누락 사례를 모두 검증한다. '비어 있으므로 자료 없음 화면이 동작함'만으로 이력 요구를 완료 처리하지 않는다. 이적 전 경력 전체 보관 등 2시즌 예외 정책은 이번 설계에서 추가하지 않는다.
