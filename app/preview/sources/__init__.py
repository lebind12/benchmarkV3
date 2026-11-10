"""MP-03 자료 출처 계층.

이 패키지에는 두 가지만 있다.

- `api_football`: API-Football v3 요청 명세와 응답 해석. 전송 계층이 없다.
- `fixtures`: 기존 DB에 저장된 경기 자료를 **읽기 전용**으로 쓰는 조회기.

실제 HTTP 전송·재시도·예산·시도 기록은 MP-04의 공통 실행기(`execute_request`)가
맡는다. 이 패키지는 `httpx`·`requests`·`socket`을 import하지 않는다.
"""

from __future__ import annotations

__all__: list[str] = []
