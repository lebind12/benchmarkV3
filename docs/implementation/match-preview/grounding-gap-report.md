# MP05 인용(grounding) 공백 진단 보고: 저장 원문·SDK·공식 문서 대조

**범위.** `section_form` 실제 실행 1건(`6e59041a-3767-4756-a412-991008873f50`)의 **이미 저장된**
원문 요청·응답·변환 결과를 읽기 전용으로 대조해, 검색 인용 `chunks`가 **제공자 응답에
없었는지**, 아니면 **SDK 직렬화·가림(redaction)·전송·모듈 파서**가 잃어버린 것인지 판정한다.
이 작업에서 유료 모델 호출 0회, API-Football 호출 0회, 새 live 재시도 0회다.

**한 줄 결론.** 인용 chunks는 **제공자 응답에 실제로 없었다.** 저장된 원문 응답의
`grounding_metadata`에는 `web_search_queries`(8건)·`search_entry_point`만 있고
`grounding_chunks`/`grounding_supports` 키 자체가 없다. SDK(google-genai 3.0.0)는 같은 자리에
chunks가 오면 그대로 보존하며(아래 §4 재현), 우리 파서도 그 값을 정상적으로 읽는다.
따라서 **로컬 파서·직렬화·가림 버그가 아니다.** 프레임워크는 정상 동작했고, 미달한 것은
**실질 조사 내용 범위**(관전 포인트·주목 선수)다. 코드 수정·회귀 테스트 추가는 하지 않았다.

## 0. 진단 환경 (실제 실행 모델 확인)

| 항목 | 값 | 확인 방법 |
|---|---|---|
| 에이전트 / 모델 | hive / `deepseek-ai/deepseek-v4.1-flash-1017` | 세션 로그 `model/selection` 레코드(`provider=hive`, `reasoningEffort=max`) |
| 프로필 | `dsh-tui` | `DSH_PROFILE=dsh-tui`, 세션 `74d10890-…` |
| 설정 변경 | **없음** | `~/.config/match-preview/*.env` 둘 다 mode `600`, mtime 불변(21:17 / 20:30) |
| 하위 워커 | **없음** | 작업 지시(no subworkers) 준수 |

## 1. 저장된 실행·아티팩트 (정확한 경로·개수)

`preview_dev`(개발 DB)에서 **readonly 트랜잭션**으로만 읽었다. 기존 행 수정·삭제 없음.

| 대상 | 식별자 | 값 |
|---|---|---|
| 실행 | `preview_runs.id` | `6e59041a-3767-4756-a412-991008873f50` · `section` · `dev` · `live` · `succeeded` / `ready` |
| 시도 | `preview_attempts.id` | `2b1fe55b-9d0e-466c-88ba-160902008ecc` · `R1`/`R1-form` · `vertex` · `gemini-3.5-flash` · `ok` / `200` |
| 요청 원문 | `preview_artifacts.id` | `98027c14-e988-48ee-acfd-137a86c5a7a6` · 4,887 B |
| 응답 원문 | `preview_artifacts.id` | `305d1f89-9940-4edf-8305-92a5d4c5b6a3` · 15,578 B · sha256 `c3253074…` |
| 섹션 결과 | `preview_section_results` | v1 502자 / v2 454자 / v3 442자, 각 `sources` 1건(API 스냅샷) |
| 승인 | `preview_section_approvals` | **0행**(전체 0, `section_form` 0) — 사용자 승인 없음 |
| 사용량 | `usage_metadata` | prompt 1,340 · candidates 2,954 · thoughts 9,670 · total 13,964 |

## 2. 제공자 응답의 실제 모양 (핵심 증거)

저장된 응답 원문의 `candidates[0]`:

```
candidates[0] keys      = [content, finish_reason, grounding_metadata]
finish_reason           = STOP
grounding_metadata keys = [retrieval_metadata, search_entry_point, web_search_queries]
  web_search_queries    = 8건
  retrieval_metadata    = {}            ← 빈 객체
  search_entry_point    = {rendered_content: 5,903자}   ← 검색 질의 chip 4개
  grounding_chunks      = 키 없음
  grounding_supports    = 키 없음
```

- 8건 질의: `"Manchester City" "Fulham" November 2026`, `Manchester City vs Fulham 2026`,
  `… November 21 2026`, `… 2026-11-21`, `"Antoine Semenyo" …`, `"Erling Haaland" …`,
  `"Alex Iwobi" …`, `"Rodrigo Muniz" …`.
- 본문 텍스트 7,658 B 안에 URL 9회 등장, **서로 다른 redirect URL 4개**.
- `search_entry_point.rendered_content`의 링크 4개는 **질의 chip**이며, 본문에 쓴 4개 URL과
  **겹치는 것이 0개**다(교집합 0/4). 즉 chip은 "무엇을 검색했는지"이고 "무엇을 인용했는지"가 아니다.
- 원문 전체에서 문자열 `chunk`는 **1회**만 나오고, 그 1회는 HTTP 헤더
  `transfer-encoding: chunked`다. 즉 grounding chunk 데이터는 원문 어디에도 없다.

## 3. 가림(redaction)·전송·파서가 잃었는지 검사

| 의심 지점 | 검사 | 결과 |
|---|---|---|
| 비밀값 가림이 chunks를 지웠나 | 저장본 `[REDACTED]` 출현 **1회**, 위치는 `thought_signature` | **아니오** |
| 가림 키 규칙이 chunks를 지웠나 | `_is_secret_key("grounding_chunks"/"uri"/"title"/"domain")` → 모두 `False` | **아니오** |
| 저장본이 잘렸나 | 저장 `byte_size` 15,578 = 실제 직렬화 길이, sha256 재계산 일치 | **아니오** |
| 전송 요청이 검색을 뺐나 | 저장 요청 원문 `generation_config` = `{temperature:0.2, response_mime_type:"application/json", tools:[{"google_search":{}}]}`. 같은 설정을 현행 SDK로 직렬화하면 wire에 `tools:[{"googleSearch":{}}]` + `generationConfig.responseMimeType` | 정상 포함 |
| 모듈 파서가 놓쳤나 | 저장 원문을 HEAD `form.parse_grounding`에 그대로 재생 → `queries 8 / sources 0 / supports 0`, `citation_chunks_missing=True` | **정상 해석** |

파서는 snake_case(`grounding_chunks`)와 camelCase(`groundingChunks`)를 모두 보고,
chunk의 `web.uri`를 출처로 옮긴다. 저장 원문에는 그 키가 없으므로 옮길 값이 없었다.

## 4. SDK가 chunks를 보존하는지 재현 (오프라인, 네트워크·유료 호출 없음)

설치본 `google-genai==3.0.0`(requirements.txt·pyproject 동일 고정)에서 확인:

1. `types.GroundingMetadata` 필드에 `grounding_chunks`, `grounding_supports`가 **존재**한다
   (설명: "A list of supporting references retrieved from the grounding source … populated when
   the grounding source is Google Search …").
2. 실제 운영 경로와 같은 변환(`_GenerateContentResponse_from_vertex` → `_from_response`)에
   camelCase `groundingChunks`/`groundingSupports` 1건씩을 넣으면, `model_dump_json(exclude_none=True)`
   결과에 `grounding_chunks` 1건·`grounding_supports` 1건이 **그대로 남는다**.
3. `Models.generate_content` 전체 경로를 stub transport로 재현해도 chunks가 보존된다.
4. **빈 배열과 키 없음의 구분**: `grounding_chunks=[]`는 `"grounding_chunks": []`로 남고,
   `null` 또는 키 없음만 dump에서 사라진다(`exclude_none=True`).
   따라서 "키 없음"은 **제공자가 non-empty 목록을 준 뒤 SDK가 지운 경우일 수 없다.**
5. `_common._remove_extra_fields`는 모델에 없는 필드만 지운다. `grounding_chunks`는 모델 필드이므로
   지워지지 않는다(미래 필드가 지워지는 것은 맞지만, 이번 케이스의 필드는 아니다).

**잔여 모호성 1가지(정직하게 남김).** `exclude_none=True` 때문에 `groundingChunks: null`(명시적 null)과
"키 자체 없음"이 저장본에서 **구분되지 않는다.** 둘 다 "제공자가 인용을 주지 않았다"는 뜻이지만,
"검색은 했으나 인용을 못 만들었다"와 "인용 필드를 null로 채웠다"를 저장본만으로는 가를 수 없다.
이것은 진단 해상도 한계이며 인용 손실 원인은 아니다.

## 5. 공식 문서 대조 (1차 출처)

- [Grounding with Google Search (Agent Platform)](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/grounding/grounding-with-google-search)
  - `groundingMetadata`는 `webSearchQueries` · `searchEntryPoint` · `groundingChunks` ·
    `groundingSupports` · `retrievalMetadata`로 구성된다(문서 예시 응답 그대로).
  - "…If your model prompt successfully uses Grounding with Google Search … then the responses
    include metadata with source links (web URLs). **However, there are several reasons this
    metadata might not be provided, and the prompt response won't be grounded. These reasons
    include low source relevance or incomplete information within the model's response.**" ← 이번 관측과
    같은 계열의 서술된 동작이다(질의는 실행·인용은 미제공).
- [Structured output / control generated output (Agent Platform)](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/control-generated-output)
  - "Setting `response_mime_type` to `application/json` (JSON mode) **without specifying a
    `response_schema`** acts only as a strong hint to the model and doesn't ensure 100% valid JSON."
  - 이번 요청이 정확히 그 형태다(스키마 없이 mime type만). 문서에 "grounding과 함께 쓰면 인용이
    빠진다"는 명시는 **없다.** 즉 JSON 모드가 원인이라는 주장은 문서로 뒷받침되지 않는다.
- [Structured outputs (Gemini API)](https://ai.google.dev/gemini-api/docs/structured-output)
  - Gemini 3 계열에서 "Structured Outputs with tools"가 **preview**로 소개되며 Grounding with
    Google Search가 포함된다. Vertex `generateContent` 경로의 동일 보장은 이 문서 범위가 아니다.
- [Grounding with Google Search (Gemini API)](https://ai.google.dev/gemini-api/docs/grounding)
  - 최신 interactions 표면은 `url_citation` annotation으로 인용을 준다. 이번 경로(Vertex
    `generateContent` + `google_search`)와는 다른 표면이므로 원인 판정 근거로 쓰지 않았다.

**1차 사실 vs 가설 구분.**
- 사실: 질의 8건·`search_entry_point` 존재, chunks/supports 부재, 저장본 무손실, SDK·파서 보존 확인.
- 가설(미검증): `responseMimeType=application/json`(스키마 없음) 조합이 chunk 반환을 억제했을 수 있다.
  문서에 근거가 없고, 이 작업은 유료 호출 0회 조건이라 **검증하지 않았다.**

## 6. 프레임워크 동작 vs 실질 내용 범위 (분리 판정)

| 층 | 판정 | 근거 |
|---|---|---|
| 요청·예산·시도 기록 | **정상** | 시도 1회·200·예산 `model_used=1/8`, `api_used=0/24` |
| 검색 실행 | **정상(질의 8건)** | `web_search_queries` 8건, `search_entry_point` 존재 |
| 인용 수신 | **제공자 미제공** | chunks/supports 키 없음(§2·§4) |
| 근거 검증·창작 차단 | **정상** | 모델이 쓴 redirect URL은 `grounding_chunks`에 없으므로 채택 거부, 사유 기록 |
| API-only 대체 경로 | **정상** | 저장 순위 사실 2건 + 모델 사실/해석 3건 채택, 본문 생성 |
| 실질 조사 범위 | **미달** | 관전 포인트 0건, 주목 선수 0건, 최근 흐름 2건(순위·폼 수준) |

즉 `status=succeeded`/`quality=ready`는 **워크플로우 완주**를 뜻하며, 관전 포인트·주목 선수
리서치 품질의 달성을 뜻하지 않는다. 조정자가 이 품질을 아직 수용하지 않은 것은 타당하다.

거부된 항목은 6건(관전 포인트 3, 주목 선수 3)이며 사유는 모두
"근거 식별자(snapshot 또는 검색 출처 URL)가 없어 채택하지 않았습니다"로, **창작 차단이 의도대로
동작한 결과**다. 본문에 선수·부상 단정이 들어가지 않은 것도 같은 이유다.

## 7. 런타임 코드 드리프트 1건 (수정 불필요, 기록만)

저장된 결과 payload의 `coverage`는 `매체·맥락 검색 = search_not_found`이고 `grounding`에
`citation_chunks_missing` 키가 없다. 저장된 `grounding.note`는
"검색 질의는 있었지만 인용 출처가 없습니다…"인데, 이 문구는 **어떤 커밋에도 없다**
(`git log -S`·`git grep` 전 리비전·dangling blob 검사 모두 0건). 실행 시점(22:14 KST)의
작업 트리에는 이후 커밋(22:43 KST, `6326a5f`)과 다른 중간 버전이 있었고, 그 버전이
빈 인용을 `search_not_found`로 적었다는 뜻이다.

**HEAD는 이미 개선되어** 같은 저장 원문을 재생하면 `citation_chunks_missing=True` →
`UNKNOWN`("질의는 있었지만 인용 없음")으로 구분한다. 즉 진단 표기는 현재 코드에서 이미
정확해졌고, 추가 수정 대상이 아니다. 문구·상태 이름만 달랐을 뿐 "질의 8건은 있었고 인용은
없었다"는 판정 자체는 실행 시점에도 같았으며, 그 판정이 인용을 만들지는 않는다.

## 8. 변경 사항

**소스 코드 변경 없음. 테스트 추가 없음.** 근거:

- 원인은 로컬 파서·직렬화·가림·전송 중 어디에도 없고, 제공자 응답 자체에 인용이 없다(§2~§4).
- 따라서 저장 응답 재생 기반 회귀 테스트를 새로 만들 대상(관측된 결함)이 없다. 기존
  `tests/preview/test_form_module.py`의 `test_grounding_metadata_preserved`,
  `test_api_facts_remain_without_search`가 이미 이 두 경우(인용 있음/없음)를 덮는다.
- `app/preview/`, `tests/preview/`, `scripts/preview_section_live_run.py` 모두 HEAD와 동일(변경 0).
- 사용자 화면에 "인용 없음" 진단을 노출하는 변경도 하지 않았다(금지 조건). 진단은 관리자 경로에만 있다.
- 이 문서만 추가했다. 커밋하지 않았다(코드 수정이 없으므로 경로 한정 커밋 대상 없음).

## 9. 남은 다음 단계 (조정자 배정 필요, 아직 실행 안 함)

**경계가 정해진 실험 1회.** 같은 모델·같은 프롬프트·같은 경기로, 요청에서
`response_mime_type: "application/json"`만 제거한 1회 호출(= 프롬프트가 이미 "JSON 객체 하나만"을
지시하므로 본문 파싱 계약은 유지)로 `grounding_chunks`가 오는지 본다.

- 확인하려는 것: JSON 모드(스키마 없음)가 인용 반환을 억제하는가. 오면 §5 가설이 지지되고,
  안 오면 "제공자가 이 프롬프트·이 주제에 인용을 주지 않는다"로 결론이 좁혀진다.
- 필요한 것: 조정자의 명시적 배정(유료 호출 1회), 그리고 이 변경이 **출력 계약·프롬프트·생성
  설정을 바꾸므로 새 섹션 워크플로우 버전**으로 기록되어야 한다는 점(기존 승인 버전 보존).
- 하지 않을 것: 프롬프트 반복 튜닝, 모델 교체, 재시도 루프, 자동 재실행.

**별개 축(인용과 무관).** 선수 단위 사실(출전·부상)은 여전히 읽기 경계 밖(`public.player*`)이다.
인용이 와도 이 축은 열리지 않는다. 필요하면 읽기 경계 승인이 별도로 필요하다.

## 10. 데이터 경계 준수

- 기존 운영 자료(경기·계정)는 읽기 전용으로만 조회했고, `preview_dev` 조회는 **readonly 트랜잭션**이었다.
- 공개 DDL/DML·권한 부여·새 DB 복사·상승된 런타임 DSN 사용은 **없다**.
- 비밀값(서비스 계정, API 키, 토큰 해시, 이메일)은 보고서·출력에 넣지 않았다. 원문 아티팩트는
  기존 가림 경로를 그대로 통과했고 수정하지 않았다.
- 사용자 프로세스(백엔드 8000, 프론트 5173)를 재시작·종료하지 않았다. 이번 진단은 코드 수정이
  없어 재시작이 필요 없다.
