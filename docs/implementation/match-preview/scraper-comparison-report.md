# Scrapling vs Trafilatura 추출 비교 실험

작성: 2026-11-11 KST. 성격: 사용자 승인 범위의 **실험 전용** 구현. 제품 코드·테스트·설정·`requirements.txt`·`Plans.md`·정책 파일 수정 없음, git 스테이징/커밋 없음, DB 접근 없음, 유료 모델/API 호출 없음, 프록시/클라우드 스크래핑 서비스 없음, 서버 재시작/배포 없음.

## 판정 (먼저)

조정자 수용 시 한계 정리: 아래 결과는 저장 HTML 6개와 그중 Fulham의 렌더 후 HTML을 비교한 제한된 실험이다. Scrapling은 전체 페이지 텍스트/Markdown 경로를 사용했으며 사이트별 본문 선택자를 최적화한 비교가 아니다. Markdown 경로는 내부 메서드를 사용하므로 그대로 제품 연결 계약으로 채택하지 않는다. 따라서 Scrapling 자체가 기사 추출에 열등하다는 일반 판정이나 채택 확정은 하지 않는다. 브라우저 자손 RSS 합산은 공유 메모리가 중복 계상될 수 있어 실제 컨테이너 사용량/최소 RAM과 같지 않다. 로컬 약 2.2 GB 관측만으로 Koyeb 1 GB에서 실행 불가능하다고 확정하지 않으며, 현재 1 GB API 인스턴스에 함께 넣을 자원 근거가 없다는 판단으로 제한한다. 메타데이터 날짜 오류는 추출 도구의 한계이며 사용자 요구에 없는 기사/API 교차 검증 절차를 추가하는 근거가 아니다.

**세 후보 중 어느 것도 단독으로 만능이 아니다. 보수적으로 가장 나은 조합은 "Scrapling으로 가져오고(HTTP 또는 필요 시 브라우저) Trafilatura로 기사 본문을 뽑되, Trafilatura가 거의 비었을 때 Scrapling 텍스트로 폴백"이다.**

근거 요약:
- **실제 기사형 페이지에서는 Trafilatura가 같은 HTML에서 더 깨끗한 본문을 낸다.** Guardian 기사에서 Trafilatura 4,735자 vs Scrapling 텍스트 8,024자였고, Scrapling 쪽은 228줄 중 190줄이 내비게이션/보일러플레이트였다.
- **목록·표 중심 페이지에서는 Trafilatura가 본문을 대량으로 버린다.** 구단 스쿼드 페이지에서 Trafilatura는 163자만 남겨 스쿼드 명단을 사실상 전부 잃었고(원문 대비 7.8%), Scrapling 텍스트는 2,096자로 명단을 보존했다. `favor_precision`/`favor_recall`/기본값 **모두** 163자로 동일했다 — 모드 튜닝으로 해결되지 않는다.
- **브라우저 렌더링은 JS 셸에서만 필요하고 비용이 크다.** Fulham 기사는 정적 HTML에서 두 도구 모두 0자를 냈고, Scrapling 브라우저 렌더 1회(14.1초, 15.3초) 후에야 Trafilatura 579자 / Scrapling 1,529자가 나왔다. 렌더 프로세스 트리 RSS 피크는 약 2.2 GB였다.
- **파싱 속도 차이는 실사용 판단에 영향이 작다.** 오프라인 파싱 중앙값은 전부 0.1–102 ms 구간이고, 브라우저 렌더 1회(≈14–15초)나 네트워크 왕복에 비하면 무시할 수준이다. 즉 **추출기 선택 근거는 속도가 아니라 품질/커버리지다.**

이 실험은 추출 품질 비교이며 API/DB 사실 검증이 아니다. 기사 내용의 진위나 DB 충돌 여부는 판정하지 않았다.

## 1. 실행 환경 실제 확인

| 항목 | 관측값 | 근거 |
|---|---|---|
| 개발 모델 제공자 | `hive` | 세션 레코드 `model/selection` |
| 모델 ID | `deepseek-ai/deepseek-v4.1-flash-1017` | 같은 레코드 |
| 추론 강도 | `max` (사용자 설정 유지) | 같은 레코드 |
| DSH 프로필 | `dsh-tui` | `DSH_PROFILE`, `DSH_PROFILE_DIR` |
| 작업 디렉터리 | `/Users/woolee/benchmark` | 셸 `pwd`, 세션 `cwd` |

## 2. 실험 환경과 의존성 (격리, 정확한 값)

모든 설치·실행은 `/tmp/preview-scraper-compare.PRpmWn` 안에서만 했다. 제품 `.venv`와 시스템 전역 패키지는 변경하지 않았다(제품 venv에는 여전히 scrapling/trafilatura 없음).

| 패키지 | 버전 |
|---|---|
| Python | 3.11.4 |
| `scrapling` | 0.5.1 |
| `trafilatura` | 2.3.1 |
| `curl_cffi` | 0.17.0 |
| `playwright` | 1.65.0 |
| `patchright` | 1.64.4 |
| `browserforge` | 1.2.4 |
| `markdownify` | 1.2.3 |
| `lxml` | 6.1.3 |
| `lxml_html_clean` | 0.4.6 |
| `justext` | 3.0.2 |
| `htmldate` | 1.11.0 |
| `courlan` | 1.4.0 |
| `cssselect` | 1.6.0 |

설치 단계·크기·시간(별도 기록):

| 단계 | 명령 | 벽시계 | 크기 변화 |
|---|---|---|---|
| 1 | `pip install scrapling trafilatura` | 7.83 s | venv 102 MB |
| 2 | `pip install 'scrapling[fetchers]' markdownify` | 14.62 s | 103 → 417 MB (+314 MB) |
| 3 | `pip install lxml_html_clean` | 0.64 s | 변화 없음 |
| browser | `patchright install chromium` (격리 경로) | 42.01 s | 581 MB (`chromium-1248`, 156.0.8078.4) |

설치 중 마주친 실제 문제 1건: `trafilatura 2.3.1 → justext → lxml.html.clean`이 lxml 6.x에서 제거되어 `ImportError`가 났고, `lxml_html_clean` 설치로 해결했다(2회 이내 시도 규칙 내, 1회 시도). **이 조합을 제품에 넣으면 이 추가 의존성이 필요하다**는 뜻이다.

중량 ML 의존성 없음: `torch`/`transformers` 설치되지 않았고, Scrapling의 LLM/RAG 기능은 쓰지 않고 문서화된 비-LLM 텍스트 경로만 사용했다. 브라우저는 `camoufox`가 아니라 `patchright` chromium이며 격리 경로(`PLAYWRIGHT_BROWSERS_PATH`)에만 설치했다.

호스트: 10코어 / 32 GB. 실험 중 1분 부하평균 7.7→10.4로 **호스트가 붐볐다**. 그래서 모든 비교는 A/B를 **교대 실행**해 양쪽이 같은 잡음을 보게 했고, 아래 속도 수치는 이 조건의 값이다.

## 3. 입력과 방법

- 입력: 이전 조사에서 캡처한 6개 URL의 HTML을 **재다운로드 없이 그대로 재사용**했다(지시대로 기존 캡처가 실제로 존재해 재요청 생략). 파일 해시는 [`evidence/scraper-comparison/input-hashes.json`](evidence/scraper-comparison/input-hashes.json)에 있다.
- **동일 바이트 보장**: 한 파일을 한 번 읽어 만든 같은 `bytes` 객체를 모든 변형에 전달했다. 각 결과 JSON에 `html_sha256`을 남겼다.
- A/B 4변형:
  - `A_text` — Scrapling 문서화 텍스트 경로 `Adaptor.get_all_text(separator="\n", strip=True, ignore_tags=("script","style","noscript"))`
  - `A_md` — Scrapling 문서화 Markdown 경로(`Convertor._strip_noise_tags` → `_sanitize_for_ai` → `_convert_to_markdown`, `scrapling[rag]`의 markdownify). LLM/RAG 모델 호출 없음.
  - `B_default` — Trafilatura `extract(include_comments=False, include_tables=True, include_links=False)` 문서화 기본값
  - `B_precision` — 같은 호출 + `favor_precision=True`
- 절차: 변형 4개 각각 **워밍업 1회(비측정)** → **입력마다 5회 교대 실행**(홀수 회차는 순서 역전). 측정 구간 안에서 결과 텍스트 길이와 sha256을 계산해 **출력이 실제로 생성됐음**을 보장했고, 5회 모두 `output_stable=True`(동일 해시)였다.
- 시간: `time.perf_counter`(벽시계)·`time.process_time`(CPU). 메모리: 별도 프로세스에서 `resource.getrusage(RUSAGE_SELF).ru_maxrss`(워밍업 후 5회 실행, 프로세스 최고 수위).
- 네트워크: HTTP 캡처는 재사용했고, **브라우저 로드는 Fulham 1개 페이지만 총 2회**(최초 1회 + 비용 측정용 1회) 수행했다. 재귀 크롤 없음, CAPTCHA 해결/프록시 로테이션/페이월 우회 없음, Forebet 403은 **재시도하지 않고 실패로 기록**했다.

## 4. URL별 결과 (품질 + 파싱 시간)

파싱 시간은 오프라인 추출만의 **5회 교대 중앙값 [최소–최대] ms**다. 네트워크·브라우저 시간은 포함되지 않는다(§5에서 분리).

| # | URL (성격) | 변형 | 글자수 | 파싱 중앙값 [범위] ms | 품질 관측 |
|---|---|---|---|---|---|
| 1 | Forebet 경기 예측 (경기 프리뷰형) | A_text | 16 | 0.1 [0.0–0.1] | **차단**. 본문은 `Just a moment...` 뿐 |
| 1 | | A_md | 0 | 0.3 [0.2–5.0] | 차단, 빈 출력 |
| 1 | | B_default | 41 | 1.9 [1.7–2.2] | `Enable JavaScript and cookies to continue` — 차단 문구만 |
| 1 | | B_precision | 0 | 1.9 [1.7–2.0] | 차단, 빈 출력 |
| 2 | manchestercitynews 스쿼드 (**목록/표**) | A_text | 2,096 | 0.9 [0.7–5.8] | 26인 명단·등번호·출전/득점 보존. 머리말/내비 일부 포함 |
| 2 | | A_md | 5,303 | 7.3 [6.9–15.7] | 명단 보존 + 이미지/링크 마크업 다수 |
| 2 | | B_default | **163** | 32.6 [32.4–35.6] | **명단 전량 유실**. 제목·"26 players" 한 줄만 남음 |
| 2 | | B_precision | **163** | 19.2 [19.0–19.5] | 기본값과 동일 — 모드로 해결 안 됨 |
| 3 | Fulham 공식 기사 (**JS 셸**) | A_text | 0 | 2.5 [2.2–3.0] | 정적 HTML에는 기사 텍스트 없음(Nuxt SSR off) |
| 3 | | A_md | 0 | 2.0 [2.0–2.3] | 동일 |
| 3 | | B_default | 0 | 14.1 [13.0–14.3] | 동일 |
| 3 | | B_precision | 0 | 14.4 [14.2–15.0] | 동일 |
| 4 | plstats 선수 통계 (**표/스탯**) | A_text | 4,173 | 1.9 [1.8–8.1] | 수치 보존, 내비 415줄 중 167줄 |
| 4 | | A_md | 9,425 | 25.7 [24.9–26.6] | 수치+표 보존, 로고/링크 노이즈 |
| 4 | | B_default | 1,820 | 31.7 [31.4–32.6] | 스탯·최근 경기 표를 깔끔한 마크다운 표로 유지, 노이즈 거의 없음 |
| 4 | | B_precision | 1,820 | 40.0 [39.6–41.0] | 동일 출력 |
| 5 | Guardian 경기 리포트 (**기사**) | A_text | 8,024 | 2.9 [2.7–3.1] | 기사 포함하나 228줄 중 190줄이 내비/구독 보일러플레이트 |
| 5 | | A_md | 15,311 | 23.8 [22.4–30.3] | 마크업·링크 다량, 노이즈 최다 |
| 5 | | **B_default** | **4,735** | 13.2 [12.8–13.3] | **기사 본문만**. 첫 줄부터 리드, 표/내비 없음 |
| 5 | | B_precision | 4,735 | 18.6 [18.6–19.5] | 동일 출력 |
| 6 | Wikipedia 선수 문서 (**백과**) | A_text | 18,246 | 6.3 [6.0–6.8] | 본문 포함, 1,399줄 중 860줄이 사이드바/메뉴 |
| 6 | | A_md | 56,490 | 75.9 [75.7–77.1] | 각주·참조·링크 폭증, 노이즈 최다 |
| 6 | | B_default | 14,958 | 76.7 [74.9–77.1] | 인포박스를 표로 정리, 노이즈 적음 |
| 6 | | B_precision | 14,486 | 102.1 [99.1–118.0] | 유사 |
| 7 | Fulham **브라우저 렌더 후** (기사) | A_text | 1,529 | 3.8 [3.5–4.2] | 본문 포함, 머리말/파트너/푸터 혼입 |
| 7 | | A_md | 9,826 | 13.2 [13.0–13.9] | 본문 + 링크·이미지 노이즈 |
| 7 | | **B_default** | **579** | 31.0 [29.9–36.7] | **본문 단락만**. 머리말·푸터 제거됨 |
| 7 | | B_precision | 579 | 34.0 [33.5–34.7] | 동일 |

### 4.1 관측된 품질 패턴

- **기사형**(Guardian, Fulham 렌더): Trafilatura가 노이즈를 잘라 본문만 남긴다. Scrapling 텍스트는 본문을 포함하지만 앞뒤 보일러플레이트가 붙는다. Markdown 경로는 링크·이미지 때문에 노이즈가 가장 많다.
- **목록/표형**(스쿼드 명단): Trafilatura는 "기사 밀도" 기준으로 판단해 명단을 버린다. 100 KB HTML에서 163자만 남긴 것은 **조용한 대량 손실**이며, 200 응답이라도 유효 콘텐츠가 아니다. Scrapling은 명단을 보존한다.
- **스탯/백과**: Trafilatura가 표 구조를 보존하며 노이즈가 적다. Scrapling 텍스트는 값은 다 있으나 내비게이션 비중이 크다.
- **차단 페이지**: 200/403 모두 "본문 있음"으로 오판하면 안 된다. Forebet은 4변형 모두 의미 있는 본문 0이며, B_default가 낸 41자는 JS 요구 안내문이다.

### 4.2 메타데이터(Trafilatura `extract_metadata`)

| URL | title | date | 판정 |
|---|---|---|---|
| Guardian | `Erling Haaland settles thriller...` | `2026-11-04` | 페이지 기사일과 일치 |
| plstats | `Erling Haaland Stats, Goals & Assists...` | `2026-11-08` | 페이지 "Updated November 8, 2026"와 일치 |
| manchestercitynews | `Manchester City Players and Squad 2026-27...` | `2026-11-10` | 페이지 "Updated 2026-11-10"와 일치 |
| Fulham 렌더 | `Josh King called up to England squad` | **`2022-09-12`** | **틀림** — 페이지는 2026-11 기사 |

`date`는 4건 중 1건이 틀렸다. **메타데이터를 그대로 신뢰하면 안 되고, 표시 전 검증이 필요하다**는 관측이다(이 실험에서 수정하지 않았다).

## 5. 비용 분해 (콜드/웜, 네트워크/렌더/파싱 분리)

| 구간 | 관측값 | 방법·조건 |
|---|---|---|
| 콜드 임포트(도구 라이브러리 로드) | 프로세스 시작 직후 RSS 11 MB → 워밍업 후 42–67 MB | 별도 프로세스, `ru_maxrss` |
| 웜 파싱(오프라인) | 0.1–102 ms (§4 표) | 5회 교대 중앙값, 워밍업 제외 |
| HTTP 가져오기 | **재측정 안 함** — 기존 캡처 재사용 지시에 따름 | 이전 조사 캡처 |
| 브라우저 렌더 1회 (Fulham) | **14.05 s / 15.31 s** (2회 관측, status 200) | `StealthyFetcher.fetch(headless, network_idle, timeout 30s)` |
| 네트워크 요청 수 | **미측정** | 브라우저는 수십 개 서브리소스 요청을 내므로 HTTP 1회와 비교 불가. 캡처 안 함 |

**파싱 시간은 전체 지연의 극히 일부다.** 브라우저 경로에서 렌더 ≈14,000 ms 대 파싱 3.8–31 ms로, 파싱은 전체의 약 0.03–0.2%다. 따라서 "어느 추출기가 더 빠른가"는 이 워크로드에서 채택 결정의 근거가 되지 못한다.

## 6. 메모리 (방법과 한계 명시)

| 입력 / 도구 | 워밍업 후 MB | 피크 RSS MB | 기준선 대비 증가 | 방법 |
|---|---|---|---|---|
| fulham_rendered / A_text | 64.0 | 93.5 | +82.2 | `RUSAGE_SELF`, 5회 |
| fulham_rendered / B_default | 67.1 | 112.4 | +101.2 | 동일 |
| gredir3 / A_text | 48.8 | 69.5 | +58.6 | 동일 |
| gredir3 / B_default | 54.2 | 66.0 | +55.1 | 동일 |
| gredir1 / A_text | 42.7 | 47.9 | +36.6 | 동일 |
| gredir1 / B_default | 46.5 | 53.4 | +41.6 | 동일 |
| **브라우저 렌더(1.68 MB 페이지)** | — | **프로세스 트리 약 2,220 MB** | — | `ps` RSS를 python pid + 자손 합산, 초당 6–7회 샘플 |

- 오프라인 추출은 두 도구 모두 **수십 MB 규모**로 비슷하고, 1.68 MB HTML에서 Trafilatura가 약간 더 높았다.
- **브라우저는 부모 프로세스 RSS(90–115 MB)로 총량을 말할 수 없다.** 실제 비용은 chromium 자식 포함 트리 약 2.2 GB다. 이 값은 샘플링 근사이며 순간 피크를 놓칠 수 있다.
- 따라서 "브라우저 메모리 = 부모 RSS"라는 서술은 금지하며, 위 표의 트리 값도 **근사치**로만 인용해야 한다.

## 7. 리미터 판정 (왜 두 배가 아닌가)

- 측정된 모든 변형에서 **CPU 시간 / 벽시계 시간 ≈ 0.98–1.01**이다. 즉 오프라인 추출은 **단일 스레드 CPU-바운드 파싱**이며, 대기(I/O·락)가 거의 없다. 이것이 리미터다.
- 그래서 같은 입력에서 도구 간 차이는 CPU 효율 차이이고, 코어를 더 줘도 이 구간은 빨라지지 않는다.
- 재현성: 가장 큰 입력(Wikipedia)을 **추가로 5회씩 다시 측정**했을 때 Scrapling 71.84 / 70.83 ms, Trafilatura 159.23 / 160.17 ms로 1차 측정(71.79 / 160.61)과 1% 이내로 재현됐다. 반면 `citysquad`의 B_default(32.6 ms)와 B_precision(19.2 ms)은 **출력이 동일한데 1.7배 차이**가 났다 — 이 항목의 절대 시간은 잡음이 섞였을 수 있어 **속도 비교 근거로 쓰지 않는다**.
- 호스트 부하가 10코어에 부하평균 7.7–10.4로 높았으므로, **1–3 ms 수준의 차이는 측정 불가로 취급**한다. §4에서 큰 차이(예: Wikipedia A_md 75.9 vs B_precision 102.1)만 근거로 삼았다.

## 8. 상호보완성 판정

| 질문 | 관측에 근거한 답 |
|---|---|
| Scrapling 단독으로 쓸 만한 본문이 나오나? | **나온다.** 7개 입력 중 5개에서 텍스트 확보(차단 1, JS 셸 1 실패). 단 기사형에서 내비/보일러플레이트가 본문과 섞인다. |
| 같은 HTML에서 Trafilatura가 더 깨끗한가? | **기사형에서는 그렇다.** Guardian·Fulham 렌더 모두 본문 단락만 남고 노이즈가 제거됐다. 백과/스탯도 표 구조가 깔끔하다. |
| Trafilatura가 더 나쁜 경우가 있나? | **있다.** 목록/표 페이지(스쿼드)에서 163자만 남겨 명단을 잃었다. 모드 변경으로 해결되지 않았다. |
| Scrapling 브라우저가 필요한가? | **JS 셸 1건에서만 필요했다.** 그 1건은 정적 HTML로는 두 도구 모두 0자였고 렌더 후에야 본문이 나왔다. |
| 최선의 제한된 조합은? | **Scrapling(HTTP, 필요 시 브라우저)으로 HTML 확보 → Trafilatura로 기사 추출 → 출력이 임계 이하로 비면 Scrapling 텍스트로 폴백.** 두 도구는 경쟁이 아니라 역할이 다르다. |

부수 관측(설계 판단 아님): Trafilatura는 `title`/`date`/`sitename` 메타데이터를 주지만 `date`가 틀린 사례가 있었다. Scrapling 텍스트 경로는 메타데이터를 주지 않는다.

## 9. 배포 주의 (크기 주장 없음)

- 현재 Koyeb `benchmark-v3/api`는 **`small` 인스턴스(min/max 1, `tyo`)** 이고, 공개 표 기준 0.25 vCPU / 1 GB다. 이번 측정은 **로컬 10코어/32GB 호스트**에서 했다.
- 따라서 여기 수치를 근거로 "배포에서 이 정도 성능"이라고 주장할 수 없다. 특히:
  - 설치 용량: 브라우저 포함 시 +581 MB, 미포함 시 +314 MB 수준이 이 격리 venv에서 관측됐다.
  - 브라우저 트리 메모리 약 2.2 GB는 **1 GB 인스턴스에 들어가지 않는다.** 브라우저 경로를 배포에 넣으려면 실제 배포 측정과 자원 재산정이 선행돼야 한다(이번 범위 밖).
  - 오프라인 추출만이면 수십 MB·수십 ms 규모라 자원 부담은 작아 보이지만, 이 역시 **로컬 관측**이다.
- 실제 배포 측정 없이 사이징을 확정하지 않는다.

## 10. 남은 미지

1. 실제 축구 사이트 모집단에서 Trafilatura가 "목록/표 페이지를 버리는" 비율. 이번엔 목록 성격 1건에서 발생했다.
2. 브라우저가 실제로 필요한 URL 비율(이번 표본 1/7)과, 그 대안(Trafilatura만으로는 불가)의 일반화.
3. HTTP 가져오기 단계의 지연·차단율은 이번에 재측정하지 않았다(기존 캡처 재사용).
4. 브라우저의 실제 네트워크 요청 수·대역폭은 미측정.
5. Koyeb `small`에서의 실제 추출 성능·메모리(로컬 측정만 있음).
6. `date` 메타데이터 오류(4건 중 1건)의 원인과 신뢰 가능한 검증 방법.
7. 잡음이 큰 호스트에서 1–3 ms 구간 차이는 판정 불가로 남았다.

## 11. 산출물 경로

- 보고서: `docs/implementation/match-preview/scraper-comparison-report.md` (이 문서)
- 증거: `docs/implementation/match-preview/evidence/scraper-comparison/`
  - `setup.json` (버전·설치 시간/크기·호스트 조건)
  - `timing-results.json`, `timing-results.csv` (28행: 7입력 × 4변형, 5회 교대)
  - `memory-results.json` (RSS 프로브 원본)
  - `browser-render.json` (렌더 2회 관측·트리 RSS)
  - `input-hashes.json` (입력 7개 바이트·sha256·임시 경로)
  - `output-samples.json` (도구별 짧은 발췌·메타데이터)
- 격리 실험 디렉터리(임시, 저장소 밖): `/tmp/preview-scraper-compare.PRpmWn`
  - `probe_extract.py`, `bench_final.py`, `probe_rss.py`, `probe_browser.py`
  - `raw/` 원본 HTML 7개, `out/` 원시 측정 JSON, `venv/`(417 MB), `browsers/`(581 MB)
- 원본 HTML 전문은 저작권 문제로 저장소에 넣지 않았고 임시 경로에만 있다.

## 12. 실제 변경과 범위 준수

### 조정자 추가 확인 — Fulham 본문 보존

사용자 요청으로 저장된 `raw/fulham_rendered.html`의 기사 본문 DOM(`div.tiptap`)과 기존 Trafilatura CLI 출력(`--no-comments`, 표준입력으로 저장 HTML 전달)을 직접 대조했다. 기사 본문 4문단(대표팀 발탁, 상대 경기·감독, 시즌 출전/득점/도움, 이전 훈련 참가 및 데뷔 전망)이 추출 결과에 같은 순서로 모두 남아 있으며 관측된 본문 문단 누락은 없다. 메뉴·파트너·저작권 푸터는 제외됐다. 다만 본문 앞에 카테고리 `Men`과 상대 시각 `4일 전`이 남아 있어 완전히 순수한 본문만의 출력은 아니다. 제목과 저자는 본문 출력에 포함되지 않아 필요하면 별도 메타데이터로 연결해야 한다. 이 확인은 저장된 렌더 DOM 대비 추출 보존 확인이며 실제 페이지 전체의 추가 로딩/접힌 영역/사실 진위를 검증했다는 뜻은 아니다. 새 네트워크·모델 호출·DB 작업·제품 변경 없이 기존 CLI와 xmllint를 사용했다.

- 새로 만든 파일: 이 보고서 + `evidence/scraper-comparison/` 아래 7개 JSON/CSV.
- 제품 코드·테스트·스크립트·설정·`requirements.txt`·`Plans.md`·정책 파일: **수정 없음**.
- git 스테이징/커밋: 없음. 기존 808개 삭제와 다른 dirty 파일: 그대로 보존.
- DB 접근/쓰기: 없음. 유료 모델/API 호출: 없음. 서버 재시작/배포: 없음. 새 에이전트: 없음.
- 외부 요청: 브라우저 렌더 2회(Fulham 1페이지)만. Forebet 403은 재시도하지 않았다.

EDITING STOPPED
