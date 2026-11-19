# README·간단 도식 설명력 검토 (Opus)

목표: 처음 방문한 독자가 root README만 보고 무엇을 하는 프로젝트인지 알 수 있는지 판정한다. 기능 README가 목적·구현·근거를 전달하는지, 새 간단 도식 세 장이 실제 연결을 오해 없이 보여주는지도 확인한다. 원본은 수정하지 않고 최소 개선안만 제안한다.

기준: 제품 `017bca2ae67bb4957e81964ae1c9ca3b3edd422d`, 검토일 2026-11-19. 문서·시각 설명력 평가이며 제품 코드 검토나 보안 감사를 대체하지 않는다.

## 요약

| 대상 | 판정 | 필수 수정 |
| --- | --- | --- |
| root `README.md` | 조건부 적합 | 기술 구조 부재, 서비스 주소 위치, 구현 브랜치 README 불일치 안내, 뉴스 상태 문구 |
| `docs/portfolio/README.md` | 적합 | 없음 (선택 개선만) |
| 기능·배포 README 9개 | 적합 | 방송 README 19행 한 문장 |
| `match-data-architecture.png` | 통과 | 없음 |
| `auth-session-architecture.png` | 통과 | 없음 |
| `broadcast-architecture.png` | 수정 필요 | 스냅샷 경로의 DB 쓰기를 부정하는 캡션·라벨 |

---

## 1. 메인 README: 프로젝트 소개 적합성

판정: 조건부 적합. 첫 문단과 기능 표만으로 "축구 경기 프리뷰 생성 서비스"라는 정체는 전달된다. 내부 작업 보고서로 읽히지는 않는다. 다만 프로젝트 README가 보통 답하는 "무엇으로 만들었나", "어디서 써보나", "소스는 어디 있고 어떻게 실행하나"가 초반에 없거나 뒤에 묻혀 있다.

### 평가 질문별 결과

1. **무엇을 누구에게, 어떤 문제를.** 3행이 "수집 → 근거 기반 프리뷰 생성 → 홈·관리자 화면 확인"을 한 문장으로 말한다. 대상 사용자(경기 전에 프리뷰를 읽는 축구 팬, 운영 관리자, 방송 진행자)와 해결하는 문제(흩어진 근거를 모아 경기 전 읽을거리를 만든다)는 명시되지 않는다. 독자가 추론할 수는 있다.
2. **주요 기능·이용 흐름·접근 위치.** 기능 표(7~18행)는 좋다. 서비스 주소는 30행, "구현 기준과 저장소 상태" 절 세 번째 문단에 있다. 써보고 싶은 독자가 SHA·브랜치 설명을 지나야 링크를 찾는다.
3. **기술 스택·전체 구조.** root에 없다. Vue·FastAPI·PostgreSQL·LangGraph·Vertex AI·Vercel·Koyeb는 `docs/portfolio/deployment/README.md` 표에만 있다. 전체 구조 그림(`preview-system-architecture.png`)도 root에서 직접 보이지 않는다.
4. **소스·실행 진입점.** 26행이 "구현은 `lebind12/preview-api-migration` 브랜치, main에 병합되지 않음"을 숨기지 않고 말한다. 28행이 "main은 기획·문서 보관 위치"라고 밝힌다. 둘 다 좋다. 문제는 두 가지다.
   - 28행 "기능 README가 가리키는 구현 리비전과 환경 설정을 확인해야 한다"는 막다른 안내다. 기능 README 어디에도 환경 설정이나 실행 절차가 없다.
   - 구현 브랜치 `017bca2`의 `README.md`는 2026-11-09 문구 "개발 코드 삭제 / 재개발 미착수 … 실행할 로컬 앱은 없다"를 그대로 갖고 있다(`git show 017bca2:README.md`로 확인). 같은 트리에 `app/`, `frontend/`, `.env.example`, `pyproject.toml`이 있다. root 링크를 따라간 독자는 "앱이 없다"는 README를 먼저 본다.
5. **내부 SHA·이력의 비중.** 전체 SHA 두 개와 브랜치·병합 상태 설명이 기능 표 바로 뒤에 온다. 2026-11-09 기존 README 보존 블록(39~63행)은 `<details>`로 접혀 있어 분량 문제는 작다. 그러나 그 안의 로컬 절대 경로 `/Users/woolee/benchmark`와 "이번 파일 변경은 커밋하지 않은 로컬 상태다"는 GitHub 독자에게 의미가 없고 시점이 지난 문장이다. `Plans.md`(현재 작업 상태) 링크도 외부 독자용이 아니다.
6. **미구현 기능·과장.** 22행 "뉴스 관리·문맥 연결과 자연어 검색은 이번 기능 문서 범위에서 제외했다"는 "구현됐지만 문서만 안 썼다"로도 읽힌다. 한편 제품 `app/api/v1/general.py`에는 `GET /api/v1/news` 라우트가 있어 "미구현"이라고만 쓰기도 어렵다. 성능·보안·운영 성공을 과장한 문장은 없다. 30행 운영 주소에 "상시 가용성 보증 아님"을 붙인 처리는 적절하다.

### 필수 수정

| 위치 | 독자가 놓치거나 오해하는 내용 | 최소 개선안 |
| --- | --- | --- |
| 3행 뒤 (신규 짧은 절) | 무엇으로 만들었는지, 전체 구조가 어떤지 root에서 알 수 없다 | "기술 구성" 한 줄 또는 3행 표를 추가한다. 예: "프론트 Vue·TypeScript (Vercel) · API FastAPI (Koyeb) · 생성 LangGraph + Vertex AI · 저장 PostgreSQL". 값은 `deployment/README.md` 표에서 그대로 옮긴다. 그 아래 `docs/portfolio/assets/preview-system-architecture.png` 한 장과 "프리뷰 범위 그림" 한 줄을 둔다 |
| 30행 운영 주소 | 써볼 위치가 기술 상태 절 끝에 묻혀 있다 | 주소 문장을 첫 문단 바로 아래로 올린다. "11월 19일 배포 확인, 상시 보증 아님" 단서는 그대로 붙인다 |
| 28행 "환경 설정을 확인해야 한다" | 따라갈 곳이 없다 | "검증된 실행 안내는 아직 문서화하지 않았다. 소스는 [구현 리비전 트리](…/tree/017bca2…)에서 볼 수 있고 환경 변수 목록은 해당 트리의 `.env.example`이다"로 바꾼다. 설치·실행 명령은 확인 전까지 쓰지 않는다 |
| 구현 브랜치 README (root 밖, 참고) | 링크를 따라가면 "앱 없음" README가 나온다 | root에 "구현 브랜치의 README.md는 11월 9일 정리 문구가 남아 있어 현재 소스 상태와 다르다" 한 문장을 둔다. 근본 해결은 브랜치 README 교체이며 이번 범위 밖이다 |
| 22행 뉴스·자연어 검색 | 구현 여부가 모호하다 | 실제 상태를 확인한 뒤 "뉴스 관리·문맥 연결은 설계 문서 단계이며 기능 목록에 포함하지 않는다. 자연어 검색은 미구현이다" 식으로 상태어를 명시한다. 상태 판정은 조정자·사용자가 확인한다(이번 검토는 `/news` 라우트 존재만 확인) |

### 선택 개선

- 첫 문단에 대상 사용자를 한 구절 넣는다. 예: "경기 전에 읽을 프리뷰를 원하는 축구 팬과, 수집·생성을 운영하는 관리자를 위한 서비스다."
- `docs/portfolio/README.md`의 "포트폴리오에서 설명할 기여" 절(코딩 에이전트 구현, 사용자의 방향·수용 기준 결정)을 root에도 한두 문장 요약한다. 처음 보는 독자가 작성 주체를 오해하지 않는다.
- "구현 기준과 저장소 상태" 절은 짧은 SHA 한 개와 브랜치 링크로 줄이고, 두 커밋의 역할 설명은 `docs/portfolio/README.md`의 "구현을 읽는 기준" 절에 맡긴다(이미 같은 내용이 있다).
- 2026-11-09 보존 블록은 `docs/planning/cleanup-record.md` 또는 `docs/decisions/2026-11-09-planning-only-worktrees.md`로 옮기고 root에는 링크 한 줄만 남긴다. 로컬 절대 경로와 "커밋하지 않은 로컬 상태" 문장은 옮길 때 과거 시점 표시를 붙인다.
- `Plans.md` 링크는 "개발 기록" 아래로 내리거나 "내부 작업 진행표"라고 성격을 밝힌다.

### 권장 목차 (제안만, 직접 수정하지 않음)

1. 한 문단 소개: 무엇·누구·어떤 문제.
2. 서비스 주소와 단서 한 줄.
3. 주요 기능 표 (현재 표 유지).
4. 기술 구성 한 줄 + 전체 구조 그림 한 장.
5. 소스와 실행: 구현 리비전 링크, main에 앱 소스가 없다는 사실, 검증된 실행 안내 부재와 `.env.example` 위치.
6. 범위 밖 기능과 상태 (뉴스·자연어 검색).
7. 문서 기준 시점 (짧은 SHA).
8. 기획·개발 기록 링크 (과거 README 보존본은 별도 문서로).

---

## 2. 기능별 README

### 포트폴리오 목차 `docs/portfolio/README.md`

판정: 적합. root와 역할이 잘 나뉜다. root는 기능 표, 이 문서는 읽는 순서·근거 상태·코드 확인과 연동 확인의 의미 구분을 맡는다. "근거 상태" 열이 각 기능의 검증 수준을 정직하게 표시한다.

선택 개선:

- "읽는 순서"(7행 절)가 경기 조회·인증·방송을 빠뜨린다. 끝에 "일반 조회·인증·방송은 독립적으로 읽는다" 한 문장을 덧붙인다.
- 5행 "사용자 지정에 따라 제외했다"와 35행 "Excalidraw 스킬의 표현 원칙을 따라"는 작업 과정 용어다. 각각 "이번 문서 범위가 아니다", "도식은 진입점·처리 책임·저장 경계·실제 API 이름을 연결한다"로 바꾸면 외부 독자에게 자연스럽다.

### 기능·배포 README 공통

판정: 적합. 9개 문서 모두 같은 골격(목적 한 문단 → 기준 시점과 검증 수준 → 처리 흐름 → 설계 선택 → 소스 링크 → 근거와 한계 → 면접 질문)을 따른다. 처음 읽는 사람이 "무엇을 왜, 어디서 확인하나"를 따라갈 수 있다. "코드 확인"과 "연동 확인"을 문서마다 구분하고, 두 경기 결과를 일반 성공률로 확대하지 않는다는 단서가 일관된다. 측정하지 않은 수치를 주장한 곳은 찾지 못했다.

공통 선택 개선:

- 상단 이동 링크가 문서마다 다르다. `home`만 root 프로젝트 링크를 갖는다. 모든 기능 README 첫 줄을 "기능 목차 · 프로젝트" 두 링크로 맞추면 GitHub에서 들어온 독자가 돌아갈 곳을 찾기 쉽다.

### 문서별 메모

| 문서 | 판정 | 필수 | 선택 개선 (위치 · 이유 · 최소안) |
| --- | --- | --- | --- |
| `home/README.md` | 적합 | 없음 | 13행 "구형 MP-10 실행"은 설명 없는 내부 식별자다. "이전 생성 방식(MP-10) 실행"처럼 한 단어 풀이를 붙인다 |
| `match-data/README.md` | 적합 | 없음 | 19행 "경기 상세는 별도 `app/api/fixture_detail.py`가 담당 … 통계 조회를 나눴다". 통계는 `app/api/v1/fixture_detail_analytics.py`의 `/{external_id}/statistics`가 제공한다. 해당 파일명과 링크를 덧붙인다 |
| `auth/README.md` | 적합 | 없음 | 없음. 로그인 4단계와 개발 저장 경계가 소스(`auth.py:41,108,118,160,186`)와 일치한다 |
| `broadcast/README.md` | 수정 필요 | 19행 (아래 도식 절 참조) | 없음 |
| `preview-generation/README.md` | 적합 | 없음 | 15행 `D0`가 처음 등장할 때 "그림의 첫 노드"라는 풀이가 없다. "`D0`(입력 준비 노드)"로 쓴다 |
| `vertex-ai/README.md` | 적합 | 없음 | 마지막 한계 절 "일부 옛 표시 필드는 24를 기록한다"는 무엇이 24인지 알 수 없다. "옛 HTTP 예산 표시 필드는 이전 상한 24를 보여준다"처럼 대상을 밝힌다 (사실관계는 작성자가 확인) |
| `collection/README.md` | 적합 | 없음 | 없음. 두 POST 경로의 계약 차이와 "55는 생성 경기 수가 아님" 단서가 오해를 잘 막는다 |
| `player-storage/README.md` | 적합 | 없음 | 없음. 기존 번역 편집과 새 후보 검수를 분리한 설명이 명확하다 |
| `deployment/README.md` | 적합 | 없음 | 없음. "배포 지침이 아님"을 첫 문단에 밝혀 실행 안내로 오해하지 않게 한다. root의 기술 구성 한 줄은 이 표에서 가져오면 된다 |
| `assets/README.md` | 적합 | 없음 | 방송 도식 수정 후 표의 "방송 화면·스냅샷" 설명 범위에 "모멘텀 상태 저장"을 덧붙인다 |

---

## 3. 도식

### 3.1 경기·팀·선수·기록 조회 (`match-data-architecture.png`)

판정: 통과.

잘 설명되는 점: 화면 → 라우터 → 서비스 → PostgreSQL 한 줄 요청과 아래쪽 응답 귀환선이 분리되어, "조회 시 외부 호출 없음"을 30초 안에 말할 수 있다.

소스 대조: `app/services/general.py`, `app/services/fixture_detail.py`는 SQLAlchemy `text` 조회만 import하고 외부 클라이언트가 없다. 단방향 화살표와 별도 응답선 표현이 실제와 맞다.

필수 수정: 없음.

선택 개선:

- 하단 경로 줄의 "통계"는 `fixture_detail_analytics.py` 라우터가 제공한다. 도식은 경로만 적었으므로 그대로 두어도 된다. README 쪽 보완은 2절 표 참조.
- 오른쪽 PostgreSQL 타원이 캔버스 오른쪽 끝에 거의 붙어 있다(렌더 기준 x≈1985/2000). 잘림은 없으나 export 여백을 20~40px 늘리면 안정적이다.
- 화살표 위 "GET" 라벨이 다른 글자보다 작다. 판독은 가능하다.

### 3.2 로그인·권한과 개발 세션 분리 (`auth-session-architecture.png`)

판정: 통과.

잘 설명되는 점: auth.py에서 위로는 `public.app_user` 읽기("로그인 시각 미갱신"), 아래로는 `preview_dev.preview_admin_sessions` 쓰기("세션만 쓰기")로 갈라져, 계정 읽기와 세션 쓰기 경계가 한눈에 구분된다.

소스 대조:

- `app/api/v1/auth.py:41` 계정 조회가 `db.get_auth_db_session`, `:108` `touch_last_login=not local_profile`. 도식의 "로그인 시각 미갱신"과 부제 "로컬 개발 프로필 기준"이 일치한다.
- `:118`, `:160`, `:186`에서 `benchmark_sessions.issue/rotate/revoke_session`. `app/auth/benchmark_sessions.py` 모듈 설명이 쓰기 대상을 `preview_dev.preview_admin_sessions` 한 테이블로 명시한다.
- `:129` refresh 쿠키 `set_cookie`, `:191` `delete_cookie`. 응답 라벨 "access token + HttpOnly refresh 쿠키"와 맞다.

필수 수정: 없음.

선택 개선:

- 저장소 표기 규칙이 섞여 있다. `app_user`는 초록 타원(저장소), `preview_admin_sessions`는 파란 둥근 사각형(서비스와 같은 모양)이다. 개발 세션 상자도 타원으로 바꾸거나 테두리만 초록으로 바꾸면 "둘 다 같은 DB 저장소"가 시각적으로 맞는다.
- "세션만 쓰기" 라벨이 화살표 수평 구간(y≈740)보다 아래(y≈805)에 떨어져 있다. 화살표 바로 위로 옮기면 라벨 소속이 분명해진다.

### 3.3 방송 오버레이와 프로그램 화면 (`broadcast-architecture.png`)

판정: 수정 필요 (문구 수준).

잘 설명되는 점: 별도 HTML 진입점 → 방송 API → 스냅샷 서비스가 저장 자료·블록별 캐시·외부 API를 조립한다는 구조와, TTL이 "코드 정책이지 지연 보장이 아님"이라는 단서가 잘 드러난다.

#### 필수 수정: 스냅샷 경로의 DB 쓰기 부정

위치:

- 도식 하단 캡션 "화살표는 요청·응답 관계."와 PostgreSQL 화살표 라벨 "저장 조회".
- `docs/portfolio/broadcast/README.md` 19행 "양방향 화살표는 요청·응답 관계이며, DB에 방송 데이터가 쓰인다는 표시가 아니다."

이유: `app/services/broadcast_program.py:1062-1104`에서 `program-snapshot` 조립 중 모멘텀을 계산한 뒤 `persist_broadcast_momentum_from_cache(...)`와 `self.session.commit()`을 호출한다. `app/services/broadcast_momentum_persistence.py:73`은 `INSERT INTO broadcast_momentum_state`(upsert)다. 즉 방송 스냅샷 GET은 PostgreSQL에 모멘텀 상태를 쓴다. 현재 문구를 따르면 독자는 "방송 경로는 DB를 읽기만 한다"고 설명하게 된다.

최소 수정안:

- 도식 PostgreSQL 화살표 라벨: "저장 조회" → "저장 조회 · 모멘텀 상태 저장".
- 도식 PostgreSQL 타원에 "모멘텀 상태" 한 줄을 추가하거나, 캡션 첫 문장을 "화살표는 요청·응답 관계. DB 쓰기는 모멘텀 상태뿐이다."로 바꾼다. 둘 중 하나면 충분하다.
- README 19행: "양방향 화살표는 요청·응답 관계다. 프로그램 스냅샷은 계산한 모멘텀 상태를 `broadcast_momentum_state`에 저장하며, 그 밖의 경기 자료는 읽기만 한다."

참고: 25행 "일반 홈 문서 GET은 저장본만 읽지만 방송 경로는 외부 갱신과 주기적 요청을 포함한다"는 이미 맞다. 이 쓰기는 의도된 영속화(migration `0014_broadcast_momentum_state`)로 보이며 제품 버그로 다루지 않는다. 문서 표현만 문제다.

#### 선택 개선

- "캐시 미사용 시 / 외부 조회" → "캐시 없음·만료 시 / 외부 조회". `app/services/broadcast.py:354`의 `make_broadcast_cache()`는 Upstash 설정이 있으면 Redis 캐시, 없으면 `NoopBroadcastCache`를 쓴다. "미사용"은 "캐시를 끈 경우"로만 읽힐 수 있다.
- 캐시 상자 제목 "블록별 캐시 / TTL"에 "(Redis, 미설정 시 없음)"을 붙이면 저장 위치가 분명해진다.
- FastAPI 상자에 `overlay`와 `program-snapshot`이 함께 있고 아래로 화살표 하나가 스냅샷 서비스로 간다. 소스상 오버레이는 `broadcast.py` 오버레이 서비스, 프로그램 화면은 `BroadcastProgramSnapshotService`를 쓴다. 정확히 하려면 아래 화살표 라벨에 "program-snapshot 기준"을 붙인다.
- 하단 인증 차이 각주와 README "현재 인증 경계" 절은 일치한다. 추가 조치 불필요.

### 도식 공통

- 가독성: 세 장 모두 글자 잘림·겹침이 없다. 상자당 3~4줄, 요소 18~26개로 "간단한 도식" 요구에 맞는다.
- 범위·상태: 세 장 모두 하단에 "소스 확인 / E2E를 뜻하지 않음" 단서가 있어 README 한계 서술과 일치한다.
- 리디자인 필요 없음. 방송 도식의 라벨 한 곳·캡션 한 줄과 README 한 문장만 고치면 된다.

---

## 검토 기록

- PNG 세 장을 이미지로 직접 열어 육안 확인했다: `docs/portfolio/assets/match-data-architecture.png`, `auth-session-architecture.png`, `broadcast-architecture.png`. 기존 프리뷰 PNG 세 장은 재심사하지 않았다.
- Excalidraw 원본 세 개의 텍스트 요소를 추출해 PNG 문구와 동일함을 확인했다.
- 문서: root `README.md`, `docs/portfolio/README.md`, `docs/portfolio/{home,match-data,auth,broadcast,preview-generation,vertex-ai,collection,player-storage,deployment,assets}/README.md`, `docs/portfolio/simple-diagrams-review-brief.md`.
- 제품 소스(`017bca2` 고정, `git show`·`git grep`·`git ls-tree`로 읽기만 함): `README.md`, 최상위 파일 목록, `app/api/v1/general.py`, `app/services/general.py`, `app/api/fixture_detail.py`, `app/services/fixture_detail.py`, `app/api/v1/fixture_detail_analytics.py`(grep), `app/api/v1/auth.py`, `app/auth/benchmark_sessions.py`, `app/api/v1/broadcast.py`, `app/services/broadcast.py`, `app/services/broadcast_program.py`, `app/services/broadcast_momentum_persistence.py`.
- 서버·브라우저·DB·테스트·웹 검색·모델 호출은 하지 않았다. 설치·실행 명령은 확인하지 않았으므로 제안하지 않았다.
- 실행 모델: Claude Opus 5.5 (`claude-opus-5-5`, 시스템 프롬프트 기준). 추론 effort 값은 세션에서 노출되지 않아 확인할 수 없다.
