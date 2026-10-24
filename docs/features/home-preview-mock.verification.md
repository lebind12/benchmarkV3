# 메인 추천·프리뷰 목업 검증

2026-10-25. root 자체 로컬 검증. 사용자 평가 대기이며 BE/운영 연동 완료를 의미하지 않는다.

## 검증한 사용자 흐름

`/home/mock` → 로컬 샘플 추천 선정 → 화살표/목록/좌우 키 경기 전환 → 같은 fixture의 인라인 사전 프리뷰 → 자료 누락·실패·이전본·오늘 결과 확인.

| 경계 | 결과 | 근거 |
|---|---|---|
| 추천 정책 | 통과 | Vitest 5개: 진행 중 우선, 전체 대회 순서, 킥오프·ID 동률, 중복 제거, 미정 라운드 제외, 다음 날짜·빈 상태 |
| 화면 전환 | 통과 | Playwright: 추천 9개 순환, 동일 fixture 프리뷰, 이전/키보드 전환, 단일 비활성, 종료 결과 분리 |
| 자료 상태 | 통과 | 일부 자료 부족, 준비 중/실패 후 로컬 재확인, 이전 유효본, 로고 fallback |
| 인증/네트워크 | 통과 | 기존 authUser를 보존하며 목업 진입과 조작에서 `/api/` 요청 0, pageerror 0. 실제 인증·축구·AI API 호출 없음 |
| 화면/스크롤 | 통과 | desktop 1280×720, mobile 390×844, dark, reduced-motion. 가로 넘침 없음, 하단 출처까지 스크롤·표시, 감소 모션 애니메이션 없음 |
| 빌드 | 통과 | vue-tsc 및 Vite production build. 목업 route는 DEV 조건부 |
| 기존 개발 서버 | 확인 | `http://127.0.0.1:5173/home/mock` HTTP 200 |
| BE/DB/배포 | 대상 아님 | 가상 샘플 평가 단계. endpoint 응답 요구는 초안만 작성 |

## 실행 결과

```text
npm run test:unit -- tests/unit/home-preview/recommendations.spec.ts
5 passed

./node_modules/.bin/playwright test -c playwright.home-preview.config.ts
8 passed (9.1s)

npm run build
vue-tsc -b && vite build: success
```

브라우저 검증은 `VITE_USE_MOCK=false`, 포트 5187의 로컬 Vite에서 실행했다. 기존 개발 서버는 변경·재시작하지 않았다. Playwright가 실행한 임시 서버는 테스트 종료 시 정리된다.

## 캡처

`out/home-preview/{desktop,mobile,dark,reduced-motion}.png`, 각 `-preview.png`, `-sources.png`: 총 12개. 데스크톱/모바일/다크 첫 화면과 데스크톱/모바일 프리뷰·출처 화면을 이미지 도구로 직접 확인했다. 나머지는 브라우저 assertion과 캡처 생성으로 검증했다.

## 발견·수정

- 평가 select의 명시적 접근성 이름 추가.
- 최근 경기 표본 부족(3경기) 표시와 폼 색상/결과 정합 반영.
- 기존 로그인 정보가 있을 때 DefaultLayout의 세션 검증이 실 API를 호출할 수 있어, 해당 개발 목업 route의 `meta.localMock`에서만 자동 검증을 생략. 실제 페이지의 인증 동작은 기존 조건을 유지한다.
- 최종 타입 검사에서 사용하지 않는 template 반복 변수를 제거한 뒤 빌드 통과.

## 남은 범위

사용자 목업 평가 후 실제 `/` 적용 여부와 endpoint-request를 확정한다. 상세 링크는 샘플 fixture를 실경기에 연결하지 않기 위해 목업에서 제공하지 않는다. 부상/전술/예측/배당은 가상이며 실제 coverage·출처·생성 품질을 검증한 결과가 아니다. 기존 관리 변경을 보존해 브랜치/하네스 전환·커밋·원격 push·배포는 수행하지 않았다.

## 후속 디자인 수정 검증

`오늘의 매치` 제목, 스크롤 프리뷰 점진 노출·글래스 표면 적용 후 vue-tsc/Vite 빌드 통과. 브라우저 테스트에 스크롤 진입 시 선명해짐과 재방문 시 가독성 유지 확인을 추가했다. 최종 E2E는 9개다. 감소 모션, 모바일, 다크 검증은 유지한다.

## 누락 자료 동적 상태 후속 검증

- vue-tsc/Vite 빌드 통과, E2E 10개 통과(12.5s).
- 추가 브라우저 검증: 초기 미제공 2/일부 1 → 영역별 수정으로 미제공 4/일부 0, 자동 문구/직접 문구, 본문 데이터/출처 동기화, 누락 항목 클릭·포커스 이동, fixture별 편집 격리, 초기화, 전체 자료 제공 시 안내 숨김.
- `data-summary-desktop.png`, `data-summary-mobile.png`를 추가 캡처한다. 원격 API/운영 변경은 없다.

## JSON 계약 기반 목업 후속 검증

- 단위 테스트 12개(추천 5, JSON 계약 7), E2E 11개(16.3s), vue-tsc 포함 Vite 빌드 통과.
- JSON의 분석/스코어 편집을 화면에 반영하고, 다른 fixture의 출처를 넣은 잘못된 JSON은 오류와 함께 거부·직전 유효 화면을 보존한다. 기존 누락 상태 조작·경기별 격리·모바일·다크·감소 모션 검증 유지.
- 10개 샘플 JSON을 검증한다. 구조화된 facts/external/analysis, null 누락, 근거 참조, 시각, 표본 수, 배당 시장, AI 영역에 사실 필드를 추가하는 오류를 검사했다.
- `home-preview-analysis.schema.json`, Vertex 지원 형식과 generation 요청 예제는 로컬 계약 산출물이다. 실제 provider schema 수용/검색·생성·DB 저장/공개 GET을 검증한 결과가 아니다. 실제 생성 경로의 Markdown 반환은 유지한다.


## PRE-01 재검증 — 2026-10-25

- 경로 `/Users/woolee/benchmark-main`, branch `feat/home-preview-json`, 브라우저 테스트 5192/백엔드 proxy 8017. 기존 공용 checkout의 브랜치/HEAD/실제 index/작업 파일 변경 없음.
- `npm run test:unit -- tests/unit/home-preview`: 3 files / 23 tests PASS.
- `./node_modules/.bin/playwright test --config playwright.home-preview.config.ts`: 13 tests PASS, API request 0 / page error 0.
- `npm run build`: vue-tsc + Vite PASS.
- `out/home-preview/mobile-preview.png` 시각 확인: 제목/본문/카드/모바일 폭 유지. 데스크톱/모바일/다크/reduced-motion 회귀 테스트 PASS.
- 생성 전/실패/24h 전 상태의 null publication, 사실만 있는 본문의 null generated_at, 실패 후 이전 저장본의 시각 유지, PEN 미확인·확인 결과, 동적 컵 분류·정렬·날짜/중복/출처 오류 차단 검증.
- 테스트는 로컬 목업/계약 검증이며 실 DB·Vertex·API-Football·Redis·스케줄러/배포 검증이 아니다. PRE-03에서 Pydantic 의미 검증 parity가 필요하다.
