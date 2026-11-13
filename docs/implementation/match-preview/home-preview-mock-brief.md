# 홈 프리뷰 디자인 목업 범위

사용자 선택: 기존 benchmark 추천 홈을 유지·정돈하는 안. 실제 홈 이식 전 디자인 확인용 목업을 먼저 만든다. 이는 독립 목업(spike) 승인이며 운영 홈·관리자 라우트 교체나 최종 API 계약 승인을 뜻하지 않는다.

## 화면

### 최신 표시 합의

- 주목·부상 팀 머리글은 36px 로고, 큰 팀 이름, 홈·원정 표시 순서로 둔다.
- 선수 사진은 정사각형으로 세로 가운데 정렬하고 네 모서리 라운딩을 통일한다.
- 배당 API 경로의 화면 이름은 API-Football이며 보충 안내 문장은 표시하지 않는다. 원 북메이커와 수집 경로는 데이터에서 보존한다.
- 전망과 전망 근거의 팀명·선수명은 굵게 표시한다. JSON의 기존 문자열 필드를 유지하고 이름 구간만 Markdown 굵게 표기로 감싸는 방식으로 정식 생성 연결을 설계한다. HTML은 출력 계약에 넣지 않는다. 현재 목업은 이 표기를 안전한 텍스트/strong 요소로 표시하며 HTML 삽입은 하지 않는다.
- 사용자 확정 후 실제 forecast 생성 프롬프트에도 이름 강조 지침을 반영했다(`mp11-bundle-forecast-prompt-4`). 기존 문자열 JSON과 스코어/근거ID 계약은 유지하며 새 실제 모델 호출은 하지 않았다. 홈 목업은 강조 표시를 지원한다. 제품 관리자 기존 텍스트 뷰는 정식 연결 때 강조 렌더를 지원해야 하며 이번 요청 변경만으로 모든 화면이 연결됐다고 간주하지 않는다.

- 원래 Git 소스 c4d7d32의 루트 홈은 UiReviewHomeView → HomeDashboardCandidate → HomeRecommendedSection이다. HomeView의 옛3패널 대신 이 추천경기 홈과 AppHeader·Pretendard·라이트/다크 문맥을 기준으로 한다.
- 현재 관리자 frontend5173/backend8000을 유지한다. 원본 frontend를 out/home-preview-mock/original-frontend에 격리 복사해 원본 화면을 먼저 띄운다. 삭제된 원본 파일을 현행 frontend에 복원하거나 인덱스/브랜치를 바꾸지 않는다.
- 원본 대진·추천선택 흐름을 유지하고 별도 목업 경로에 맨체스터 시티–풀럼 한 경기 데이터를 넣는다. 표시 순서는 AI 경기 전망/AI 예상2-0 → 팀별 주목선수2명 → 부상선수 → 외부 뉴스·매체전망3곳 → 배당이다.
- 배당은 실제 응답에 없으므로 목업에서도 값을 만들지 않는다. 프리뷰 본문에는 내부 수집/검증/재시도 진단을 넣지 않는다. 제목/선수이름·선정이유·매체이름·스코어·근거문장을 각각 데이터 필드로 다루고 전체Markdown을붙여보여주는것으로대체하지않는다.
- 직접 자료는 docs/implementation/match-preview/evidence/ps05-live/reader-preview-9c079eea.json 및동일실행live증거다. 외부매체는최신v2 사용,원문과모델판단은디자인목업용자료로보존한다. 새로운 경기/예측/통계·성공지표·사진을 만들어 채우지 않는다.

## 선수 이미지

공식 문서 https://www.api-football.com/documentation_v3 의 정적 URL: https://media.api-sports.io/football/players/{player_id}.png . DB internal player.id가 아니라 public.player.external_id(API-Football ID)를 쓴다.

기존 이름 읽기전용조회기로 경기두팀만조회해확인한매핑:

| 선수 | DB 내부 ID | API-Football ID |
|---|---:|---:|
| 엘링 홀란드 | 533 | 1100 |
| 라얀 셰르키 | 541 | 156477 |
| 조슈아 킹 | 139 | 389315 |
| 오스카 보브 | 144 | 278133 |
| 앙투안 세메뇨 | 88 | 19281 |
| 마크 게히 | 549 | 67971 |
| 톰 케어니 | 132 | 19025 |

홀란드1100/셰르키156477 URL을HEAD로확인해둘다200/image/png를받았다. 나머지는기존외부ID로주소를구성하고목업렌더에서확인한다. 사진이없거나실패하면동일선수의정직한이름fallback을사용한다. 다른선수사진으로대체하지않는다.

## 구현·확인

실제DeepSeek만목업코드를작성한다. Hallmark fast/kept-context 적용, 기존홈콘텐츠/토큰문맥을유지하고정보순서·가독성·이미지배치에집중한다. Hallmark Floor·토큰·focus·reduced-motion·이미지grid·sloplint/render는유지한다. 불필요한마케팅hero/목업성능수치/차트/테마전체갈아엎기없음.

격리원본화면과목업을별도포트(5174우선,충돌시비어있는포트)에두고비교가능하게한다. 기존추천API는이목업에서호출하지않고실생성단일경기fixture JSON으로보여준다. 저장데이터와이미지정적GET외모델/API-Football데이터API/DB쓰기/권한/승인/배포없음. 디자인판단용이므로pytest/vitest/전체빌드없음. 필요한typecheck와Hallmark렌더확인만,정확실행URL/파일/미완성UI·실제이미지로드결과보고.

최종JSON스키마·홈API이식은사용자가목업디자인을확인한뒤진행한다. 목업의JSON은그계약을논의하기위한초안이며운영계약으로단정하지않는다.
