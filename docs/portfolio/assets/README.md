# Excalidraw 아키텍처 도식

[기능 목차](../README.md)

2026-11-19 포트폴리오 작업에서 제작·렌더링·육안 확인한 프리뷰 도식 세 장을 저장소에 복사하고, 경기 조회·개발 인증·방송의 간단 도식 세 장을 추가했다. 코드 기준은 `017bca2`다. 개인 Documents 디렉터리가 없어도 README에서 그림을 볼 수 있고 `.excalidraw` 파일을 편집기에 열 수 있다.

| 도식 | PNG | 편집 원본 | 설명 범위 |
|---|---|---|---|
| 서비스 전체 경계 | [이미지](preview-system-architecture.png) | [Excalidraw](preview-system-architecture.excalidraw) | 프리뷰 프론트·API·Vertex·PostgreSQL |
| 생성 엔진 상세 | [이미지](preview-pipeline-architecture.png) | [Excalidraw](preview-pipeline-architecture.excalidraw) | 조사 분기·수집 합류·섹션 작성·저장 |
| 모델 호출 확대 | [이미지](vertex-call-architecture.png) | [Excalidraw](vertex-call-architecture.excalidraw) | 단일 호출 통로·재시도·전송 장부 |
| 경기·선수 조회 | [이미지](match-data-architecture.png) | [Excalidraw](match-data-architecture.excalidraw) | 화면→API→서비스→DB와 응답 흐름 |
| 개발 로그인·세션 | [이미지](auth-session-architecture.png) | [Excalidraw](auth-session-architecture.excalidraw) | 계정 원장 읽기와 개발 세션 쓰기 분리 |
| 방송 화면·스냅샷 | [이미지](broadcast-architecture.png) | [Excalidraw](broadcast-architecture.excalidraw) | 별도 화면·스냅샷 조립·캐시·외부 조회·모멘텀 상태 저장 |

프리뷰 원 도식은 두 차례 설명력 평가를 거쳤다. 두 번째 평가에서 발견한 장부 텍스트 잘림은 높이를 늘려 재출력하고 확인했다. 이번 작업에서 기존 프리뷰 원본·PNG는 변경하지 않았다. 새 간단 도식은 [Opus 설명력 평가](../simple-diagrams-opus-review.md)를 받았다. 경기·인증은 통과했고, 방송의 DB 쓰기 누락 지적은 모멘텀 상태 저장 라벨과 README에 반영했다. 후속 수정은 조정자의 확인이며 Opus 재평가를 받았다는 뜻은 아니다. 도식 평가는 제품 동작 검증을 대신하지 않는다.

그림의 수치는 코드가 적용한 정책이다. 동시성 2는 실행별 모듈 슬롯이고 전역 Vertex 할당량 제한이 아니다. 429 대기 60·300·600초는 고정 구간이며 최적값을 측정했다는 뜻이 아니다. 자세한 한계는 [Vertex AI README](../vertex-ai/README.md)를 따른다.
