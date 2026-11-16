# R4 정보 원문 묶음 (읽기용)

- 성격: `experimental-prototype-not-product` · 스크립트 `r4-information-bundle-trial-1`
- 묶음 ID: `r4-bundle-20261111T001550Z` · 기준 시각(as_of): 2026-11-11T00:15:50.644214+00:00
- 경기: 외부 ID 1557474 · 브라우저 사용: 아니오

## DB 스냅샷 (읽기 전용)

- Manchester City vs Fulham · 리그 Premier League 2026 · 킥오프 2026-11-21T12:30:00+00:00 · 상태 NS
- 팀 4 Fulham → 한국어 표기 `풀럼` (출처: public.team + public.team_translation)
- 팀 13 Manchester City → 한국어 표기 `맨체스터 시티` (출처: public.team + public.team_translation)

### 구조화 사실 (모델 입력)

- `api:fixture-identity` 경기 Manchester City vs Fulham · 리그 Premier League(1) · 시즌 2026 · 킥오프(UTC) 2026-11-21T12:30:00+00:00 · 상태 NS
- `api:standings-13` team_id 13: 리그 3위, 10경기 7승 0무 3패, 승점 21, 득점 21 실점 13, 최근 5경기 폼 LLLWW
- `api:standings-4` team_id 4: 리그 15위, 10경기 2승 4무 4패, 승점 10, 득점 10 실점 12, 최근 5경기 폼 DDWWL
- `api:past-1557465` 지난 경기 1557465(2026-11-07T17:30:00+00:00): team 18 3-1 team 13 (FT)
- `api:past-1557461` 지난 경기 1557461(2026-11-07T15:00:00+00:00): team 4 1-1 team 2 (FT)
- `api:past-1635710` 지난 경기 1635710(2026-11-04T20:00:00+00:00): team 132518 2-3 team 13 (FT)
- `api:past-1557447` 지난 경기 1557447(2026-10-31T20:00:00+00:00): team 19 1-1 team 4 (FT)
- `api:past-1557454` 지난 경기 1557454(2026-10-31T15:00:00+00:00): team 13 0-1 team 14 (FT)
- `api:past-1640387` 지난 경기 1640387(2026-10-28T19:45:00+00:00): team 4 0-1 team 15 (FT)
- `api:past-1557440` 지난 경기 1557440(2026-10-24T14:00:00+00:00): team 2100 0-1 team 4 (FT)
- `api:past-1557438` 지난 경기 1557438(2026-10-24T11:30:00+00:00): team 19 2-1 team 13 (FT)
- `api:past-1635693` 지난 경기 1635693(2026-10-20T19:00:00+00:00): team 13 5-1 team 102850 (FT)
- `api:past-1557431` 지난 경기 1557431(2026-10-17T14:00:00+00:00): team 4 1-0 team 2075 (FT)

## 수집한 웹 출처

### `src:-predictions-tips-manchester-city-fulham-1925345` (unavailable) — 실패 — HTTP 403
- 발견: https://www.forebet.com/en/predictions-tips-manchester-city-fulham-1925345
- 최종 URL: https://www.forebet.com/en/predictions-tips-manchester-city-fulham-1925345 · 방법 `fresh_http` · 수집 시각 2026-11-11T00:15:50.644214+00:00
- 성격: 본문을 확보하지 못했다. 후보로만 남는다. · 추출기 trafilatura-2.3.1/defaults · 본문 0자 · sha256 `None`
### `src:https-manchestercitynews-co-uk-squad` (stats) — 본문 확보
- 발견: https://manchestercitynews.co.uk/squad
- 최종 URL: https://manchestercitynews.co.uk/squad · 방법 `fresh_http` · 수집 시각 2026-11-11T00:15:50.644214+00:00
- 성격: 팀 스쿼드/명단 자료(통계 성격). · 추출기 scrapling-0.5.1/get_all_text(list_page_fallback) · 본문 2096자 · sha256 `3a1a268a9d1c45984e2ef790b234c15d24b0147e2d7c96ce3fc131fc40e526bc`

> #3 Rúben Dias Defender 15 Apps · 0 Goals

> #27 Matheus Nunes Midfielder 10 Apps · 0 Goals

> #75 F. Samba Attacker 3 Apps · 2 Goals Citizens Press Independent Manchester City fan hub - all the latest from the club based at Etihad Stadium, since 1880. Updated daily. Next up: → Fulham · 21 Nov 2026 12:30 Explore Home

### `src:november-06-josh-king-called-up-to-england-squad` (unavailable) — 실패 — 본문 추출 0자(정적 HTML에 기사 텍스트 없음 또는 JS 셸)
- 발견: https://www.fulhamfc.com/news/2026/november/06/josh-king-called-up-to-england-squad/
- 최종 URL: https://www.fulhamfc.com/news/2026/november/06/josh-king-called-up-to-england-squad/ · 방법 `fresh_http` · 수집 시각 2026-11-11T00:15:50.644214+00:00
- 성격: 본문을 확보하지 못했다. 후보로만 남는다. · 추출기 None · 본문 0자 · sha256 `None`
### `src:to27vvfzzlihudsj5vhg0h-xzef3kjtfrhdrmr5qagko3x3n` (stats) — 본문 확보
- 발견: https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHXooPbQJUqz6WpyDk89tY3c4zKYCbkVYP90-bibzZ2CbJNHjIltN2Zo1_1jegURJ7jXjIwQE3LSEccSY0S-jeoto27vvfzzlIHuDsJ5vHG0h-XzEf3KJTFRHdRMR5QAgko3X3N
- 최종 URL: https://plstats.uk/players/erling-haaland/ · 방법 `fresh_http` · 수집 시각 2026-11-11T00:15:50.644214+00:00
- 성격: 선수 개인 기록/통계 페이지. · 추출기 trafilatura-2.3.1/defaults · 본문 1820자 · sha256 `1ecb8f9b0c70d9653f4539294ffd8539a2c69b4233a1430dd7577186861f4b5e`

> Premier League 2026-2027 · Updated Erling Haaland (26, Norway) is a striker at Manchester City. Premier League 2026-2027: 10 appearances (890 minutes), 9 goals and 0 assists. Appearances 10 Minutes 890 Goals 9 Assists 0 xG

> 6.87 Avg rating 7.69 Scores shown with Manchester City's goals first. | Match | Date | Result | G | A | Mins | Rating | |---|---|---|---|---|---|---| | Nottingham 3–1 Manchester City | 7 Nov 2026 | L | 0 | 0 | 90 |  | | Manchester City 0–1 Brighton | 31 Oct 2026 | L | 0 | 0 | 90 |  |

> Player data covers the Premier League from 2010-11; detailed stats from 2024-25. ~ Minutes before 2024-25 are estimated from lineups and substitutions (added time not counted).

### `src:7eah234vjvk7tmusorx1kbmoddyqlo-tdndvvknjumbllvx1` (past_match_report) — 본문 확보
- 발견: https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQG4Cn2GkY4-v-xku29pjvjHZEugvyg-ECRyW-yXRmee5JOP0G1OawZgEDhVt_5bpq20E5rd5H7AC6I8SMRIYUQ7R_btl9nPebffe8wPrEKKL2ahtf1WxdToHNn2N4uBksLUaZqv3lrmGwSLX4t1bCKhoTq5QoMZwRWT7zHWlUNe7Eah234vJVk7tMuSORX1KbmODDYqlO-tDndvVKNjUmblLVx1
- 최종 URL: https://www.theguardian.com/football/2026/nov/04/rb-leipzig-manchester-city-champions-league-match-report · 방법 `fresh_http` · 수집 시각 2026-11-11T00:15:50.644214+00:00
- 성격: 지난 경기 보도(리포트). 이번 경기 프리뷰가 아니다. · 추출기 trafilatura-2.3.1/defaults · 본문 4735자 · sha256 `771fae16bb151bf188a755053656d127874a1752851bd45e359ec04a06c4170b`

> Feed Erling Haaland and Manchester City’s totemic No 9 will score. The problem, recently, has been a paucity of openings for him. This was true again before Elliot Anderson crossed and Haaland slid home a priceless winner for Enzo Maresca’s disjointed unit, Rayan Cherki hitting a post late on.

> City’s quest to return to victorious ways featured an XI of four changes from Saturday’s Brighton reverse. Noteworthy was Maresca’s dropping of Rúben Dias as Abdukodir Khusanov’s pace was preferred at centre-back to the captain, Haaland taking the armband.

> The Brighton defeat featured close to zero service for Haaland and City’s 13-goal man was again hard to find, Matheus Nunes’s loose cross, when the captain lurked, emblematic. So, too, as a sign of Leipzig’s ascendancy, was Marc Guéhi scrambling to clear danger, Nusa firing in the ball from the left, and Christoph Baumgartner having space to shoot marginally wide of Donnarumma’s left post.

### `src:fxy9bqp3cqvgjx0yunt00jcttaa6jtgpexqpwfd7dqoktfqa` (profile) — 본문 확보
- 발견: https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQE6xKuFVuMdNU2z2GSYevkJCxBPzx5LDHPLiZCZq8FOe_N86wNF0YdtYijZJvEmn9qqANEaTWZRDc-b2FZCOdfxY9bqP3CQVgjx0yUNt00JCTTAA6JTGpExQPWfD7dQOkTfQA==
- 최종 URL: https://en.wikipedia.org/wiki/Oscar_Bobb · 방법 `fresh_http` · 수집 시각 2026-11-11T00:15:50.644214+00:00
- 성격: 백과 선수 소개(프로필). · 추출기 trafilatura-2.3.1/defaults · 본문 14958자 · sha256 `1bb6f705938f22b51f1aef1679268636a54206e409cd081faf406bfe0f4ab701`

> Oscar Bobb (born 12 July 2003) is a Norwegian professional footballer who plays as a right winger for Premier League club Fulham and the Norway national team. Early life [edit] Bobb was born in Oslo on 12 July 2003.[3][4] He has Gambian and Norwegian heritage.[5][6][7] His father is Abdou Bobb,[8] a Gambian-Norwegian.[citation needed] Bobb was largely raised by his mother, Norwegian actress Turid Gunnes, who had sole

> On 2 September 2023, Bobb was given his Premier League debut against Fulham coming on as an 88th minute substitute for Phil Foden, where he was involved in the buildup leading to the 5th goal scored by fellow Norwegian Erling Haaland.[17] On 19 September, he made his Champions League debut against Red Star Belgrade, replacing Phil Foden in the 83rd minute in a 3–1 win.[18] On 13 December also against Red Star Belgrad

> Manchester City - Premier League: 2023–24[2] - FA Community Shield: 2024[37] - UEFA Super Cup: 2023[38] - FIFA Club World Cup: 2023[39] - FA Cup runner-up: 2023–24[40] Individual [edit] [edit] - Profile at the Fulham F.C. website


## 생성 결과

- run `a32f3ed4-df88-4ce3-939f-702c357ef7b2` · mode `None` · quality `ready` · 실제 전송 0회

```
이번 경기의 주목 선수 3명입니다.

선정 선수: 엘링 홀란드
선정 이유: 이번 시즌 리그 10경기에서 9골을 기록 중이며, 최근 챔피언스리그 라이프치히전에서도 결승골을 터뜨리며 핵심 공격수로서의 득점 감각을 유지하고 있습니다.

선정 선수: 오스카 보브
선정 이유: 과거 맨체스터 시티에서 활약했으나 현재는 풀럼 소속의 윙어로 활약 중이며, 친정팀을 상대로 어떤 경기력을 보여줄지 기대를 모읍니다.

선정 선수: 루벤 디아스
선정 이유: 이번 시즌 15경기에 출전했으나 최근 라이프치히전에서는 엔초 마레스카 감독의 선택을 받지 못하고 선발 제외되었기에, 이번 풀럼전 선발 복귀 여부가 주목됩니다.
```
