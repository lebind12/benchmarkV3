> **기획 참고 원문 · 2026-11-09 정리**
> 출처: `main` 워크트리의 `docs/ax/feature-research/research.md`.
> 요구·설계·결정의 맥락을 보존한 자료입니다. 본문의 구현 완료, 검증 수치, 실행 명령, 작업 경로, 배포 승인은 당시 기록이며 현재 상태나 새 실행 승인이 아닙니다. 현재는 네 워크트리의 개발 코드가 삭제된 기획 보관 상태입니다. 상충하는 과거안은 상위 기획 요약과 최신 결정 기록을 따릅니다.

# 추가 AX 기능 연구 — 축구·스포츠 사례 보강과 후보 평가

작성 2026-10-29. 상태: 조사·제안. 기능 확정, 구현, 정확도 검증이 아니다. 조사·제안과 실제 개발 착수는 구분한다.

## 1. 목적과 범위

- 기존 조사 `outputs/01a176fb-…/AX_사례_238건_유형별_조사.xlsx`(2026-10-26)를 보강하고, 서비스에 붙일 추가 AX 기능 후보를 실제 DB·코드·정책 기준으로 평가한다.
- 기존 238건은 산업 전반 사례다. 스포츠·축구 키워드로 검색한 결과 해당 사례는 0건이었다. 키워드에 걸린 8건(AX019 한국언론진흥재단 등)도 뉴스 검색이나 업무 도구 사례였다. 이번 문서는 이 도메인 공백을 메운다.
- 근거는 리그, 공급사, 언론의 공개 자료다. 공급사가 발표한 성과 수치는 독립적으로 재현된 결과가 아니다. 일부 항목은 2차 보도에만 근거하며 표에 그렇게 표시했다. 이번 조사에서 유료 모델 호출, 운영 DB 조회, 코드 변경은 하지 않았다.

## 2. 축구·스포츠 AX 사례 (2023–2026)

| # | 주체·기능 | 입력 → AI의 역할 → 결과 | 시점·단계 | 근거 수준 |
|---|---|---|---|---|
| S1 | Premier League × Microsoft — Premier League Companion | 30시즌 통계·기사 30만 건·영상 9천 건 → Copilot 기반 질의응답 → 통계·기사·영상 탐색 | 2025-07 발표. 출시 초기에는 미리 작성된 질문만 제공했고, 자유 질문과 다국어는 후속으로 계획 | 공식 발표 [1], 비판적 리뷰 [2] |
| S2 | Premier League × Microsoft — FPL Companion | 공식 경기 통계와 FPL 이적·성적 추세 → 대화형 조언 → 판타지 팀 구성 보조. 최종 결정은 사용자 | 2025/26 시즌 이후 출시 | 2차 보도 [3] |
| S3 | Bundesliga × AWS — Captain | 1963년 이후 통계와 라이브 이벤트·트래킹 데이터 → 질문 라우팅, 개체명 인식으로 ID 확정, 질문→SQL 템플릿 벡터 검색(없으면 SQL 생성 후 템플릿에 추가), 영상 에이전트, 입·출력 가드레일 → 통계·영상 답변과 선제적 기록 알림 | 2026-06 블로그 | 공식 기술 블로그 [4] |
| S4 | Bundesliga × AWS — Data Story Finder, 경기 리포트, Stories | 경기 데이터 → 스토리 템플릿과 대조해 이야깃거리 발견 → 편집자에게 전달. 경기 리포트는 사람이 검수하며, 사례 보고에 따르면 작성 시간이 약 90% 줄었음. 기사를 숏폼 슬라이드로 변환 | 2024–2026 | 공식 블로그 [5], 사례 정리 [6] |
| S5 | LaLiga × Microsoft — Beyond Stats, 동시통역 | Mediacoach 경기 데이터 → ML 지표(골 확률 등 50여 종) → 팬 대상 분석 포털. Azure OpenAI로 해설 동시통역·자막 추진 | 2021 포털, 2025-02 통역 발표 | 공식 [7] |
| S6 | IBM × Wimbledon·US Open — Catch Me Up, Match Chat, Key Points | 경기·선수 데이터와 기사 → 경기 전후 선수 카드, 경기 중 질의응답, 기사 3줄 요약 | 2023–2025 | 공식·보도 [8][9]. 2024년 선수 카드 오류와 문체 불일치가 지적됨 [10] |
| S7 | ESPN — 생성형 경기 리캡, FACTS 아바타 | 경기 데이터 → 리캡 자동 작성 + 편집자 검수 + "ESPN Generative AI Services" 바이라인. 취재 공백 종목에 우선 적용 | 2024. FACTS는 시험 단계 | 보도 [11]. 알렉스 모건 은퇴 경기에서 핵심 맥락이 누락돼 비판받음 [12] |
| S8 | MLB × Google Cloud — Scout Insights | 피치 단위 라이브 데이터 → Gemini 2.5 Flash/Gemma가 주요 순간 해설 생성. 지연을 피하려 사전 생성 | 2026-03 | 공식 [13] |
| S9 | Sofascore — Analyst (AI Insights) | 최근 폼·상대 전적·부상·핵심 선수 → 경기 전 AI 분석(득점·코너 예상). 유료 구독이며 "정보·오락 목적"으로 고지 | 운영 중 | 공식 도움말 [14] |
| S10 | Stats Perform — Opta Automated Insights, OptaAI Studio, Opta Pulse | Opta DB → 경기 전·중·후 다국어 서술 생성, 자연어 검색(Opta Search), 하이라이트 제작 | 2024-08 Studio, 2026-05 Pulse | 공식 [15][16] |
| S11 | 쿠팡플레이 — K리그 AI 중계 데이터 | 선수 움직임 추적 → 실시간 분석 데이터를 중계에 제공 | 2025-03 | 국내 보도 [17]. 네이버 스포츠는 KBO AI 득점 하이라이트(2019)만 확인됨 |

국내 사례가 적다. 축구 텍스트·데이터 AX에 대한 국내 공식 사례는 이번 검색에서 확인되지 않았다.

## 3. 사례에서 얻은 설계 교훈

1. **답은 구조화 데이터 조회에서 만든다.** S3는 모델이 기억한 내용으로 답하지 않고 DB 질의 결과로 답을 조립한다. 출력 가드레일로 근거 일치도 검사한다. 우리 자연어 검색 계획(SQL 게이트, 사전)과 방향이 같다.
2. **검증된 질의 템플릿을 쌓는다.** S3는 성공한 질문→SQL 쌍을 템플릿으로 승격한다. 우리 평가셋(`output/evaluation/ax-accuracy-v1`)의 기준 SQL을 같은 자산으로 쓸 수 있다.
3. **사전 생성과 저장본 제공.** S8은 지연을 피하려 해설을 미리 만든다. 우리 홈 프리뷰의 "수집 후 생성 → DB 저장 → 일반 GET은 DB만" 구조와 같고, 6시간 정책과도 맞는다.
4. **서술형 콘텐츠의 주된 위험은 중요도 판단이다.** S7(모건 누락)과 S6(선수 카드 오류)은 수치 오류보다 "무엇이 중요한가"를 놓친 사례다. 사실 검증과 별도로 **필수 포함 사실**(기록·이정표·결장·퇴장 등)을 결정론적으로 뽑아 생성 입력에 강제해야 한다.
5. **사람 검수와 AI 표기.** S4, S7은 편집자 검수와 AI 바이라인을 둔다. 우리 STREAMER/ADMIN 검수 권한과 연결할 수 있다.
6. **좁게 시작한다.** S1은 미리 작성된 질문으로 출시한 뒤 자유 질문으로 넓혔다. 다만 우리 검색 계획은 "정해진 예시로 질문을 제한하지 않음"으로 결정돼 있으므로, 이 교훈은 질문 추천 UI로만 참고한다.
7. **비용 라우팅.** S3는 질문을 분류해 약 45%를 저가 모델로 보내 비용을 35% 줄였다(공급사 발표). 정확도 평가가 확보된 뒤 적용할 최적화 단계다.
8. **예측과 사실을 분리한다.** S9는 AI 분석을 "정보·오락 목적"으로 고지한다. 우리 프리뷰의 "AI 예측 구분" 정책과 같다.

## 4. 현재 서비스의 AX 자산

| 기능 | 상태(2026-10-29 확인 기준) | 재사용 가능한 자산 |
|---|---|---|
| 자연어 검색 | 목업·계획·평가셋 v1 완료. BE 미구현, 모델 평가 미실행 | 사전 규칙, SQL 게이트 설계, 평가 방법론 |
| 홈 추천 경기 AI 프리뷰 | 메인 worktree에서 로컬 구현·실제 호출 검증. PRE-12 독립 인수 미완 | Vertex 구조화 출력, 근거·출처 저장, 재시도·checkpoint, 연속 기록 계산(`home_preview_players.py`) |
| 뉴스·커뮤니티 글 호버 | 로컬 통합 브랜치 VERIFIED. main 미반영 | 언급 추출 + 서버 DB 후보 검증, 원문 근거 대조 |
| 방송 AI 해설 | `broadcast_ai_commentary.py`(컨텍스트·프롬프트·출력 검증) | 경기 국면·이벤트 기반 컨텍스트 |
| 수집 로그 분석 | `sync_log_analysis.py`(규칙 기반 분류) | 이벤트 코드·심각도 분류 |
| 이름 번역 | 운영 중 | 번역명 조회, 사람 수정 보호 |

DB에 있는 원천 자료: `fixture`, `fixture_detail`(events, statistics, lineups, players JSON), `player_season_stat`, `standings`, `h2h_fixture`, `injury`, `transfer`, `coach`, `news_article`(제목·요약·URL만, 본문 없음), `home_preview`, `worker_sync_log`. 모두 최신 2시즌이다.

## 5. 추가 기능 후보 평가

평가 기준: ① 사례 근거, ② 현재 DB만으로 가능한지, ③ AGENTS.md 정책 적합성(일반 페이지 DB 전용·6시간 갱신, LLM이 숫자·ID를 만들지 않음, 사실과 예측 분리), ④ 재사용 자산, ⑤ 평가 가능성.

| 후보 | 사례 | 데이터 | 정책 적합성 | 재사용 | 주요 위험 | 제안 순위 |
|---|---|---|---|---|---|---|
| **A. 경기 후 AI 리뷰** — 종료 경기의 events·statistics·lineups → 핵심 장면, 승부처, 선수 기록을 근거와 함께 저장한 리뷰 | S4, S7, S10 | **보유**(`fixture_detail`) | 수집 후 생성·저장, 일반 페이지는 DB만 조회 → 적합. 결정 기록상 "경기 후 리뷰"는 필수 범위 밖 후보 | 프리뷰 파이프라인 전체 | 중요도 누락(S7), 수치 환각 → 필수 사실 추출 + 숫자는 DB 값만 사용 | **1** |
| **B. 기록·이정표 발견** — 연속 득점, 통산·시즌 기록 도달, 첫 골, 무패 행진 등을 규칙으로 감지 → AI는 문장화만 | S3 선제 알림, S4 Story Finder | 보유(2시즌 범위). 통산 기록은 2시즌 밖 자료가 없어 불가 | 감지가 결정론적이므로 적합. "2시즌 내 기준"을 반드시 표기 | `home_preview_players.py` 연속 기록 계산 | 보관 범위 밖 기록을 통산으로 오해할 수 있음 | **2** (A·홈·선수 상세에 공통 부품으로 사용) |
| **C. 뉴스 사건 묶음·엔티티 연결** — 저장된 기사 → 동일 사건 군집, 팀·선수 ID 연결 → 팀·선수 페이지 관련 뉴스 | 238건 #03·#04, S6 Key Points | 보유(제목·요약만) | 기존 `research.md` 권고안과 같음. 이번 호버 MVP에서 제외했던 자동 처리 | 호버 기능의 추출·검증 로직 | 다른 사건 병합, 루머·부정문 처리 | **3** |
| D. 팀·선수 비교 분석 서술 | S1, S10 | 보유 | 자연어 검색 결과에 붙는 해설로 위치시키면 적합 | 검색 SQL 게이트, 평가셋 | 출전 시간·대회 차이 미통제, 과도한 인과 해석 | 검색 AX-12 이후 |
| E. 수집 이상 검토 (운영자용) — 로그·누락 → 원인 후보 | 238건 #10 | 보유(`worker_sync_log`) | 결정 기록상 "AI 실패 원인 설명"은 필수 범위 밖이었음 | `sync_log_analysis.py` | 정상 변화를 오류로 판정, 자동 수정 금지 | 4 |
| F. 관심 팀 개인화 | S1, 238건 #08 | **없음**(사용자 선호 저장 없음) | 신규 테이블·FE 필요 | 적음 | 추천 근거 설명 | 보류 |
| G. 판타지·베팅성 예측 | S2, S9 | 일부 | 배당·예측은 프리뷰 범위 안에서만. 별도 기능은 서비스 성격과 맞지 않음 | — | 규제·책임 | 제외 |
| H. 방송 해설 사전 생성 강화 | S8 | 라이브(방송 endpoint) | 방송 페이지만 라이브 허용 → 적합 | `broadcast_ai_commentary.py` | 지연, 라이브 데이터 정확도 | 방송 쪽 별도 판단 |

### 5.1 1순위 후보 A의 최소 구조 (제안)

1. 종료(FT/AET/PEN) 경기가 수집되면 결정론적 단계에서 **필수 사실 목록**을 만든다. 득점자·시간, 퇴장, PK, 역전 여부, 후보 B의 이정표, 주요 결장이 포함된다.
2. Vertex 구조화 출력이 필수 사실을 모두 다루는 서술을 생성한다. 모든 문장은 사실 ID를 참조하며 숫자는 서버가 채운다.
3. 서버 검증: 필수 사실 누락, 근거 없는 문장, 숫자 불일치 중 하나라도 있으면 게시하지 않고 기존 상태를 유지한다.
4. 프리뷰와 같은 publication 모델로 저장하고, 생성 시각과 자료 기준 시각을 표시한다. 일반 GET은 DB만 조회한다. 선택적으로 STREAMER/ADMIN 검수 후 게시(S4, S7)할 수 있다.
5. 평가: `ax-accuracy-v1`의 "필수 조건 결합" 원칙을 적용한다. 필수 사실 포함률, 근거 없는 주장 0건, 숫자 불일치 0건, 중요도 판정(사람 검수)을 고정 경기 표본으로 측정한다.

### 5.2 재검토 (2026-10-29 사용자 피드백): 기존 AX와 겹치지 않는 후보

사용자 지적대로 A~H는 진행 중인 AX의 변형이다. A·B는 홈 프리뷰와 방송 `ai-review`/`match-preview`, C는 뉴스 호버, D는 자연어 검색, H는 방송 해설과 같은 파이프라인을 쓴다. 이 후보들은 신규 기능이 아니라 **기존 AX의 확장 항목**으로 분류한다.

238건 분류 기준으로 진행 중인 AX가 덮는 유형은 01·03·06·07·09다. 아직 비어 있는 유형은 04·05·08·10·11·12·14·15다. 이 중 서비스 사용자(USER/STREAMER/ADMIN)와 현재 데이터에 맞는 후보를 고르면 다음과 같다.

| 후보 | 유형 | 무엇이 새로운가 | 사례 | 데이터·정책 | 위험·평가 | 제안 |
|---|---|---|---|---|---|---|
| **N1. 수집 데이터 정합성 검토** — 순위표↔경기 결과, 선수 시즌 합계↔경기별 기록, 중복 선수, 이적↔현재 팀, 번역 의심 표기를 교차 검사 → AI가 원인 후보와 영향 범위를 정리 → 관리 화면의 검토 목록 | 10 이상 탐지 | 기존 `sync_log_analysis.py`는 **실행 로그**를 분류한다. 이 후보는 **적재된 데이터 내용**의 모순을 찾는다. 기존 AX는 모두 데이터를 사용자에게 보여주는 쪽이고, 데이터 품질 자체를 다루는 것은 없음 | 238건 #10(롯데쇼핑, Datadog), FOX "Connie"(피드 감시 에이전트) [18] | DB만 사용. 자동 수정 금지, STREAMER/ADMIN 검토. post-MVP 목록의 "AI 번역 의심 표기 추천"을 흡수 | 정상 변화(이적·시즌 전환)를 오류로 판정할 수 있음. 평가는 오류를 심은 고정 snapshot으로 재현율·오탐률 측정 | **1** |
| **N2. 축구 퀴즈 생성** — DB 사실 → 정답이 하나로 확정되는 문항과 오답 보기 생성 → 일반 페이지 퀴즈 또는 방송 시청자 참여 화면 | 14 교육·연습 / 12 | 출력물이 글이 아니라 **상호작용 항목**이다. 핵심 검증이 "정답의 유일성"으로, 기존 AX의 검증 기준과 다름 | Bundesliga Captain 인앱 퀴즈 [4], 238건 #14(Khan Academy 등) | 정답·수치는 DB에서 결정론적으로 생성하고 AI는 문장과 오답 보기만 생성. 2시즌 범위를 문항에 명시 | 오답 보기가 사실상 정답인 문제, 동률. 평가: 정답 유일성 자동 검사 + 표본 사람 검수 | **2** |
| **N3. 방송 진행 보조 에이전트** — STREAMER의 자연어 지시("하프타임에 조 순위표", "득점 나면 득점자 카드") → 허용된 방송 화면 동작 예약·실행 | 11 업무 실행 | 자연어 검색은 읽기 전용 답변이다. 이 후보는 **시스템 상태를 바꾸는 행동**이다 | FOX Foresight(중계석 실시간 질의) [18], 238건 #11(Workato, Qonto) | 방송 페이지와 STREAMER 권한 안에서만 동작. 현재 방송 화면에 외부에서 제어할 수 있는 상태가 있는지 **미확인** | 생방송 오작동. 허용 동작 목록 제한 + 실행 전 미리보기·확인 필요. 평가: 지시→동작 매핑 정확도, 거부해야 할 지시 처리 | 3 (방송 제어 구조 확인 후) |
| N4. 방송·SNS 소재 생성 — DB 데이터 → 템플릿 선택과 레이아웃 구성 → 경기 카드, 세로형 요약 슬라이드 이미지 | 12 콘텐츠·디자인 | 텍스트가 아닌 **시각 산출물** | Bundesliga Stories [6], OptaAI Studio Graphics [16] | 결정 기록상 "방송 소재"는 필수 범위 밖 후보. AGENTS §11: 공식 로고·엠블럼 임의 생성 금지, `assets/generated/` 저장 | 브랜드·초상권, 수치 오기. 평가: 데이터 일치 + 디자인 사람 평가 | 4 |
| N5. 관심 팀·선수 맞춤 피드 | 08 추천 | 사용자별 순위화 | PL Companion 개인화 [1], Spotify | 사용자 선호를 저장하는 곳이 없어 신규 테이블 필요 | 추천 근거 설명. 평가: 적합성·다양성 | 보류 |

인접하지만 겹치는 것으로 판단해 제외한 것:
- 기사 주장 팩트체크(05): 뉴스 호버와 입력이 같다.
- 스트리머 채팅 Q&A 봇(02): 자연어 검색 엔진에 채널만 추가하는 것이다.
- AI 음성 해설: 방송 해설에 출력 형식만 추가하는 것이다.

## 6. 정리

- 사례의 공통 방향: **구조화 데이터로 근거를 만들고, AI는 해석과 문장화를 맡으며, 서버가 검증하고, 미리 생성해 저장한다.** 우리 서비스의 기존 정책(DB 전용, LLM 숫자 생성 금지, 사실·예측 분리)과 잘 맞는다.
- A~H(§5)는 진행 중인 AX의 확장 항목으로 각 기능 계획에서 다룬다.
- 기존 AX와 겹치지 않는 신규 후보(§5.2)는 **N1 데이터 정합성 검토 → N2 퀴즈 생성 → N3 방송 진행 에이전트** 순으로 제안한다. N1·N2는 현재 DB만으로 가능하다. N3는 방송 화면 제어 구조를 먼저 확인해야 한다.

## 7. 한계와 미확인

- 공식 1차 자료로 확인한 항목: S1, S3, S4, S5, S8, S9, S10. 나머지는 보도나 사례 정리에 의존한다. S2 출시일, S4의 90% 수치, S10 Pulse 성능 주장은 원문을 재확인하지 않았다.
- 검색은 사례 확보용 비체계적 조사다. 238건처럼 수집 기준과 전수 목록을 갖추지 않았다. 국내 축구 AX 사례는 사실상 확인되지 못했다.
- 후보별 비용, 토큰 사용량, 실제 데이터 coverage(`fixture_detail` 채움률 등)는 측정하지 않았다. 후보 A 착수 전에 읽기 전용 coverage 조사가 필요하다.

## 출처 (2026-10-29 확인)

1. Microsoft, Premier League and Microsoft announce five-year strategic partnership, 2025-07-01 — https://news.microsoft.com/source/2025/07/01/premier-league-and-microsoft-announce-five-year-strategic-partnership-to-personalize-the-fan-experience-with-ai-for-1-8-billion-people/
2. TechRadar, The Premier League Companion … useless – at least for now — https://www.techradar.com/computing/artificial-intelligence/the-premier-league-companion-is-a-new-ai-powered-tool-for-soccer-fans-but-its-useless-at-least-for-now
3. AI Magazine, How the Premier League with Microsoft AI Guides FPL Managers — https://aimagazine.com/news/how-premier-league-uses-microsoft-ai-to-guide-fpl-managers
4. AWS M&E Blog, How Bundesliga built Captain, an AI agent for fans using Amazon Bedrock, 2026-06 — https://aws.amazon.com/blogs/media/how-bundesliga-built-captain-an-ai-agent-for-fans-using-amazon-bedrock/
5. AWS M&E Blog, Bundesliga Data Story Finder — https://aws.amazon.com/blogs/media/bundesliga-data-story-finder-delivering-fans-the-stories-they-love/
6. ZenML LLMOps DB, Scaling content production and fan engagement with GenAI (Bundesliga) — https://www.zenml.io/llmops-database/scaling-content-production-and-fan-engagement-with-gen-ai
7. Microsoft, LALIGA transforma la experiencia futbolística … con la IA de Microsoft, 2025-02 — https://news.microsoft.com/source/emea/2025/02/laliga-transforma-la-experiencia-futbolistica-y-su-gestion-interna-con-la-ia-de-microsoft/?lang=es
8. AELTC/IBM, New AI features for real-time Wimbledon fan engagement, 2025-06 — https://www.aap.com.au/aapreleases/cision20250617ae11031
9. IBM/USTA, AI-powered fan experiences for 2025 US Open — https://www.barchart.com/story/news/34214143/ibm-and-the-usta-roll-out-ai-powered-fan-experiences-for-2025-us-open
10. ITPro, Wimbledon's new Catch Me Up AI feature … wrinkles — https://www.itpro.com/technology/artificial-intelligence/wimbledons-new-catch-me-up-ai-feature-promises-to-help-cover-all-areas-of-the-tournament-after-it-irons-out-some-of-the-wrinkles
11. TheWrap, ESPN Testing Generative AI Avatar FACTS — https://www.thewrap.com/espn-sec-nation-generative-ai-avatar-facts
12. The Present Age, ESPN's AI fumble: how robot recaps … — https://www.readtpa.com/p/espns-ai-fumble-how-robot-recaps
13. MLB.com, MLB Scout Insights in Gameday powered by Google Cloud, 2026-03 — https://www.mlb.com/news/mlb-scout-insights-gameday-powered-by-google-cloud
14. Sofascore Help, What is Sofascore Analyst (AI Insights)? — https://sofascore.helpscoutdocs.com/article/231-what-is-sofascore-analyst-ai-insights
15. Stats Perform, Automated Insights — https://statsperform.com/automated-insights
16. Sportcal, Stats Perform announces OptaAI Studio — https://www.sportcal.com/news/stats-perform-announces-optaai-studio-media-data-solution/
17. 한국경제, 쿠팡플레이 K리그 중계 AI 적용, 2025-03 — https://www.hankyung.com/article/202503210386i
18. Google, How AI is pitching in at this year's World Series (FOX Sports), 2025-10 — https://blog.google/products/google-cloud/fox-sports-major-league-baseball/ (세부 내용은 2차 보도 https://www.androidcentral.com/apps-software/ai/how-google-cloud-and-gemini-are-powering-foxs-world-series-coverage 기준)
