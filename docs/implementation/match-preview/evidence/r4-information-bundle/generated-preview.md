# R4 주목 선수 — 실제 생성 결과 (시험)

- 성격: `experimental-prototype-not-product` · run `a32f3ed4-df88-4ce3-939f-702c357ef7b2`
- **작업 전체 실제 Vertex 전송: 최소 2회** (1차는 후처리 롤백으로 응답 유실, 2차가 이 run)
  · 이 run의 전송: 1회 · 이 재처리 파일 생성 시 새 전송: 0회
- 아래 본문은 **2차 전송 응답의 오프라인 재처리 결과(파일)** 이다. 저장된 섹션 결과 행
  `4d5b51c2-0fcc-4055-a788-44b6c27d0e30`은 v1·`insufficient`·본문 0으로 **본문이 저장돼 있지 않다**
- 이 파일 기준 quality `ready` (저장 행 기준 quality `insufficient`)

## 본문

이번 경기의 주목 선수 3명입니다.

선정 선수: 엘링 홀란드
선정 이유: 이번 시즌 리그 10경기에서 9골을 기록 중이며, 최근 챔피언스리그 라이프치히전에서도 결승골을 터뜨리며 핵심 공격수로서의 득점 감각을 유지하고 있습니다.

선정 선수: 오스카 보브
선정 이유: 과거 맨체스터 시티에서 활약했으나 현재는 풀럼 소속의 윙어로 활약 중이며, 친정팀을 상대로 어떤 경기력을 보여줄지 기대를 모읍니다.

선정 선수: 루벤 디아스
선정 이유: 이번 시즌 15경기에 출전했으나 최근 라이프치히전에서는 엔초 마레스카 감독의 선택을 받지 못하고 선발 제외되었기에, 이번 풀럼전 선발 복귀 여부가 주목됩니다.

## 출처 (관리자 영역)

조립 계약이 넘기는 공통 라벨은 `web_article`이지만, 실제 출처 성격은 아래와 같다.
**이번 경기 프리뷰 성격 기사 본문은 0건**이다.

- Manchester City Players and Squad 2026-27: Numbers &amp; Stats · https://manchestercitynews.co.uk/squad
  · 계약 라벨 `web_article` · 실제 성격 `stats`(팀 명단·출전 기록, 기사 아님)
- Erling Haaland Stats, Goals &amp; Assists | Premier League 2026-2027 | PLStats.uk · https://plstats.uk/players/erling-haaland/
  · 계약 라벨 `web_article` · 실제 성격 `stats`(선수 개인 기록, 기사 아님)
- Erling Haaland settles thriller for Manchester City to end RB Leipzig resistance | Champions League | The Guardian · https://www.theguardian.com/football/2026/nov/04/rb-leipzig-manchester-city-champions-league-match-report
  · 계약 라벨 `web_article` · 실제 성격 `past_match_report`(**지난 경기 리포트**, 이번 경기 프리뷰 아님)
- Oscar Bobb - Wikipedia · https://en.wikipedia.org/wiki/Oscar_Bobb
  · 계약 라벨 `web_article` · 실제 성격 `profile`(백과 프로필, 기사 아님)
- 저장된 경기·순위 자료 · (URL 없음) · `api`(읽기 전용 DB)
