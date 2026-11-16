# 경기 프리뷰의 LangGraph·모듈 승인 선택

상태: 사용자 기술 선택 확정. 구현·설치 완료를 의미하지 않는다.

사용자는 LangGraph로 프리뷰를 만들고 새 항목은 모듈 추가로 확장하며, 모듈별 실행 결과를 화면에서 확인·조정한 다음 승인하는 방식을 선택했다.

## 비교와 선택 근거

LangGraph는 명시적 단계 실행·분기·상태 저장·재개를 프리뷰의 조사/검증/종합 흐름에 적용하는 선택이다. ADK도 그래프·재개를 제공하지만 로컬 ADK와 배포 LangGraph로 나누면 실행 구조가 이원화된다. 직접 실행기는 초기 의존성이 작지만 중단·재개·버전·분기 관리를 직접 유지해야 한다. 사용자가 LangGraph를 선택했고, 조정자는 Google Gen AI SDK 호출 어댑터를 제안했다. SDK 연결 성공과 지원 버전은 아직 별도 확인 사항이다.

참고: [LangGraph 공식 개요](https://docs.langchain.com/oss/python/langgraph/overview), [체크포인터](https://docs.langchain.com/oss/python/langgraph/checkpointers), [재실행의 의미](https://docs.langchain.com/oss/python/langgraph/use-time-travel), [ADK 그래프](https://adk.dev/graphs/), [ADK 재개](https://adk.dev/runtime/resume/), [Google의 검색·종합 공개 예제](https://github.com/google-gemini/gemini-fullstack-langgraph-quickstart).

## 적용 경계

프레임워크는 단계·상태·재개를 맡고, 제품은 원문·변환·근거·지표·사용자 승인과 개발 쓰기 취소를 관리한다. SDK·노드 재시도는 하나의 호출 예산과 실제 시도 기록으로 연결한다. 무료 저장 응답 재생과 프레임워크의 재실행을 구분한다. 기존 운영 자료는 읽기 전용, 신규 기록·체크포인트·승인은 preview_dev에 저장한다.

사용자의 후속 구체화에 따라 사용자 테스트·승인 단위는 섹션 본문을 생성하는 워크플로우다. 개별 노드·모듈이 아니라 경기별 섹션 워크플로우를 실행해 실제 본문과 근거를 확인·조정한 후 승인한다. 승인에는 워크플로우 버전·구성 버전 집합·검토한 실행과 섹션 결과를 연결한다. 노드 입출력 검사는 보조 진단으로 유지한다. 승인된 워크플로우 버전은 이후 경기에서 재사용하고, 결과 의미를 바꾸는 변경만 새 버전으로 재확인한다. 개발 워커는 스스로 사용자 승인을 만들지 않는다. 내부 모듈 구현은 병렬화할 수 있으며 기본 전체 생성은 승인된 섹션 워크플로우를 조합한다.
