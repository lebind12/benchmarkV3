# 자연어 검색 화면 목업 — 2026-10-25

사용자의 검색창 목업 요청에 따라 `plan.md` §6의 화면 흐름을 먼저 검토할 수 있도록 구현했다. 관리 우선 개발 이력을 변경하거나 실제 데이터 coverage 조사를 완료한 것으로 간주하지 않는다.

목업 이후 조사·현재 컨텍스트는 [자연어 검색 AX 디렉터리](../ax/natural-language-search/README.md), 후속 구현 순서는 [검색 전용 plan.md](../ax/natural-language-search/plan.md)를 따른다. 이 문서는 화면 구현과 FE API 초안의 근거로 유지한다.

후속 사용자 결정으로 실제 검색은 로그인 필수이며 서버에서도 인증을 검증한다. Vertex AI `gemini-4-argon`과 기존 API-Football 기반 DB를 사용한다. 현재 공개 목업의 동작은 검색 인증/실제 API 구현 완료를 의미하지 않는다. [결정 기록](../decisions/2026-10-25-natural-language-search.md) 참조.

## 화면

- 진입: 헤더 `검색` → `/search`.
- 넓은 질문 입력창, 빈 입력 제출 방지, Enter 제출, Shift+Enter 줄바꿈, 한글 조합 중 Enter 제출 방지.
- 2026-10-25 후속 디자인: 블루·라벤더 배경과 반투명 유리 표면, 배경 블러·포커스 강조·포인터 반사광을 적용했다. 검색창은 한 줄로 시작하고 자동 줄바꿈/Shift+Enter에 따라 아래로 확장된다. 삭제 시 다시 축소되며 최대 7줄 이후 내부 스크롤로 전환한다. 화면 폭 변경·예시 질문 삽입에도 높이를 재계산한다. 모션 줄이기 설정을 따른다.
- 후속 인터랙션: 높이는 현재 표시 높이에서 260ms 동안 확장·축소한다. 예시 검색은 900ms의 로컬 대기 상태로 전송 아이콘 회전·파형·스켈레톤을 표시한다. 검색 중 중복 제출을 차단하며 새 검색과 페이지 이탈은 예약된 완료를 취소한다. 완료 시 결과 패널은 페이드/슬라이드로, 표의 행은 짧은 시차로 나타난다. 같은 질문 재검색에도 적용되며 모션 줄이기 설정에서는 전환·반복 애니메이션을 생략한다. 이 대기는 실제 API 실행을 의미하지 않는다.
- 장시간 검색에서는 로딩 문구 6개를 2.8초마다 순환하고 문구 전환에 짧은 페이드를 적용한다. 실제 내부 처리 단계나 완료 시간을 추정하는 문구는 사용하지 않는다. 완료·취소·페이지 이탈 시 순환 타이머를 정리하고 새 검색은 첫 문구부터 시작한다. 기본 900ms 예시는 유지하며 하단 `긴 검색 미리보기 (18초)`를 켜면 전체 순환을 확인할 수 있다. 모션 줄이기 설정에서는 문구만 즉시 교체한다.
- 세 예시 질문은 도움 순위·조건별 선수 목록·팀 비교 화면으로 연결된다.
- 임의 질문도 입력할 수 있지만 실제 해석은 연결되지 않았음을 알린다. 예시 문장으로 검색 지원 범위를 제한하는 계약이 아니다.
- 결과에는 적용 조건·집계/정렬·예시 기준 시각·부분 수집 상태를 표시한다. 시즌 수정은 화면 상태에만 반영한다.
- 하단 `목업 상태 살펴보기`에서 조건 확인·0건·미수집·미지원·조회 제한·실패를 각각 확인한다.
- 예시 선수/팀/수치이며 실제 통계가 아니다. 실제 entity ID를 검증하지 않았으므로 가짜 상세 링크를 생성하지 않았다.
- 프론트엔드 로컬 상태만 사용한다. 검색용 서버·외부 API·DB 호출·polling은 없다.

## 화면에서 도출한 endpoint 요청 초안

정식 구현 전에 AX-9 coverage 조사와 지표/정답 정의 및 화면 검토가 필요하다. 백엔드 구현은 이번 범위에 포함하지 않는다.

`POST /api/v1/search/query`

```typescript
type SearchRequest = {
  question: string
  selections?: { season?: number; league_id?: number; metric?: string }
  clarification_id?: string
  context_token?: string
}

type SearchResponse = {
  status: 'results' | 'clarification_required' | 'no_matches' |
    'data_unavailable' | 'unsupported' | 'limited' | 'failed'
  request_id: string
  result_type?: 'players' | 'teams' | 'fixtures' | 'ranking' | 'comparison'
  applied?: {
    seasons: number[]
    leagues: number[]
    filters: { key: string; label: string; value: string | number }[]
    group_by: string[]
    sort: { key: string; direction: 'asc' | 'desc' }[]
    metric_definitions: { key: string; label: string; definition: string }[]
  }
  columns?: { key: string; label: string; unit?: string }[]
  rows?: {
    entity_type?: 'player' | 'team' | 'fixture'
    entity_id?: number
    href?: string
    values: Record<string, string | number | null>
  }[]
  clarification?: { id: string; question: string; options?: { value: string; label: string }[] }[]
  coverage?: {
    status: 'complete' | 'partial' | 'missing' | 'unknown'
    data_as_of: string | null
    limitations: string[]
  }
  page?: { has_more: boolean; next_token: string | null }
  context_token?: string
  reason_code?: string
}
```

조건 수정·재질문 시 입력과 선택 조건을 유지한다. 실제 조건·기준 시각·순위·수치는 응답에서 렌더링하며 AI 설명문에서 추출하지 않는다. 미수집은 NULL/누락 상태로 구분한다. SQL과 내부 오류는 공개하지 않는다.

## 검증

`npm run build`, `npm run type-check`, `playwright test e2e/search-mock.spec.ts`.

화면 입력·자유 질문 안내·순위·조건 수정·재질문·미수집/0건 구분·비교·모바일 가로 넘침·다크 모드를 확인한다. 실제 검색 정확도·운영 데이터 coverage·DB/권한/비용 제한은 검증하지 않은 상태다.
