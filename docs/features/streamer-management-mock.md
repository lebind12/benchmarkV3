---
feature_id: streamer-management-mock
title: 관리 네 하위 탭 평가용 인터랙티브 목업
created: 2026-10-24
priority: MVP
status: in-fe-pipeline
---

# 관리 화면 평가용 목업

## 1. 목적

사용자 최신 지시: 백엔드 전에 목업을 만들어 직접 평가하고, 평가 이후 BE를 진행한다. `수집 대상 / 수집 실행 / 실행 이력 / 번역 검수` 네 하위 탭을 모두 클릭하고 샘플 상태를 변경할 수 있게 한다. 상위 요구는 [streamer-management.md](streamer-management.md), 실제 기능 범위는 `plan.md` §4/11이다. 이번 결과는 실제 서버 인증/작업 실행/DB 저장 완료가 아니다.

## 2. 사용자

- STREAMER/ADMIN의 향후 공통 관리 화면을 평가하는 사용자.
- 평가 경로는 개발/명시적 mock 모드에서만 제공. 실제 권한을 바꾸거나 mockRole/authUser를 조작하지 않는다.
- 별도 로그인 없이 샘플 화면을 평가할 수 있게 하되 운영 `/admin`의 현재 역할 검사와 실제 API는 유지한다.

## 3. 흐름

- 목업 진입 → 공유 설정·샘플 데이터 안내 → 대상 목록 검색/필터 → 추가/편집·제한 해제/활성/대상 제외.
- 선택 target을 수집 실행 탭으로 전달 → 최초/갱신 선택 → 실행 확인 → 샘플 진행 → 취소/완료/부분 실패 → 재접속 복원.
- 실행 이력 검색·상태 필터 → 상세/로그/대상별 저장·실패·미처리 → 실패 재실행을 실행 탭으로 전달.
- 번역 유형·번역/미번역·이름 검색 → 두 한글 필드 편집·이력 → 충돌 시 내 값/최신값 비교.
- 샘플 초기화는 목업 데이터만 초기화한다.

## 4. URL

- 제안 경로 `/admin/mock?tab=targets|execution|history|translations`.
- `import.meta.env.DEV` 또는 명시적 `VITE_USE_MOCK=true`에서만 route/진입 링크 노출. production 기본 빌드에서 평가 경로를 제공하지 않는다.
- 기존 `/admin`과 backend 파일은 변경하지 않는다. AppHeader에는 개발용 `관리 목업` 진입점을 추가할 수 있다.
- 방송용 아님.

## 5. 표시 데이터

- 원본 UI의 국가/대회/시즌·설정·초기/마지막 수집 상태를 활용한 샘플. 시즌은 리그별 실제 개최 시즌의 최신 2개라는 정책을 샘플에서도 표현.
- 종료 실행 7일 이력, 진행/성공/부분 실패/취소/중단의 샘플, 대상별 처리 결과·사용자용 한국어 로그.
- 리그·팀·선수·감독 번역 원문/한글 두 필드·version·검수/누락·편집자/시각·이력.
- 숫자는 샘플임을 명시하고 UI 요약은 목업 데이터에서 계산한다.

## 6. 인터랙션

- 실제 API를 사용하지 않는 MSW 전용 `/api/_mock/management/*` namespace로 fetch하며 컴포넌트의 직접 mock JSON import를 피한다.
- MSW handler 상태는 목업 전용 localStorage key에만 저장해 새로고침에도 복원. 실제 인증/서비스 key와 분리한다.
- 진행 모의 상태를 시간 기반으로 갱신하고 unmount 시 UI polling을 종료한다. 취소 후 저장된 일부와 미처리 데이터를 구분한다.
- 선택·편집·제외 확인·실행 확인·이력 상세·번역 편집/충돌은 읽기 쉬운 패널/다이얼로그로 제공. 오류·빈 결과·충돌의 평가 수단 제공.
- form validation·성공/실패 feedback·실행 중 중복 방지·범위별 필터는 실제 동작.

## 7. 비기능

- 기존 Vue 3/Pinia·lucide·Pretendard·light/dark 토큰을 활용. 새 의존성 설치 없이 구현하는 방향.
- 키보드·모바일·스크롤·명확한 포커스, 확인 다이얼로그 Escape/포커스 복귀를 검증.
- Vitest/Playwright로 대상 편집·취소/복원·이력·번역 충돌을 검증하고 type-check/build 및 실제 화면을 확인.
- 백엔드/운영 DB/API-Football/OpenAI/Redis 호출·배포 없음. 목업 네트워크는 전용 namespace로 한정.

## 8. 디자인

`frontend-design` 지침과 기존 사이트 토큰을 사용한다. 대회/시즌과 작업 상태가 잘 읽히는 운영 화면. 상단 작은 목업 표시, 제목·공유 영향 안내·실행 상태 바로가기, 네 탭, 주 콘텐츠/편집 패널. 파랑을 주요 조작색으로, 상태색은 의미에 맞게 절제한다. 가짜 로고·장식적 지표·구현 기술명 노출을 피한다.

## 9. 우선순위

이번 turn에서 완성할 결과는 로컬 평가 가능한 네 탭 목업이다. 사용자 평가 전 backend를 시작하지 않는다. 기존 전체 개발계획의 인증 BE 선행 순서는 이번 전체 목업 평가를 막지 않는다.

## 10. FE 결정 가능

컴포넌트 분해·반응형 배치·샘플 개수·mock 전용 handler와 storage 구성·empty/error/conflict 시나리오 UI·테스트 세부.

## 11. FE 결정 불가

- 실제 서버 권한을 완성한 것처럼 표시하거나 기존 auth role을 수정하지 않음.
- 원본 DB/외부 API 변경, 주기·모델·2시즌 정책 변경, 실제 데이터 삭제, 뉴스 번역/AI 의심 추천 추가 금지.
- 작업물 commit/push/merge·자동 배포·BE lifecycle 시작은 이번 범위 아님. 기존 사용자 변경/seed 보존, 현재 task branch 유지.

## 12. 산출물과 평가 지점

- spec/devplan/testplan, FE 코드/MSW 샘플, unit/E2E 결과, 평가 URL·시나리오와 이후 API 응답 후보.
- 하네스는 실제 단계만 기록. 사용자의 화면 평가 전 BE 요청 lifecycle을 트리거하거나 backend 구현을 하지 않는다. 미커밋 로컬 결과를 IMPL_PUSHED/MERGED로 표시하지 않는다.
