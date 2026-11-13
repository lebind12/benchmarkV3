"""프리뷰 관리자 접근 경계 (통합 앱용).

원래 benchmark 앱의 JWT 인증(`app.core.sessions.current_user`)을 그대로 쓰고,
그 결과가 **ADMIN**일 때만 프리뷰 관리 API를 통과시킨다. 새 세션 저장소나
별도 토큰 형식을 만들지 않는다.

경계:

- 비인증은 401(`WWW-Authenticate: Bearer`), 인증됐지만 ADMIN이 아닌 경우는 403이다.
  STREAMER는 ADMIN의 대체 권한이 아니다. 기존 관리 화면의 STREAMER 권한은 원래
  `manager_user` 정책대로 보존하며, 이 모듈은 그것을 넓히지 않는다.
- `PreviewPrincipal`에는 실제로 확인된 `user_id`·`email`·`role`만 담는다.
  preview API가 필요로 하지 않는 `session_id`·`expires_at` 같은 값을 채우지 않는다.
  확인되지 않은 값을 만들어 넣으면 감사 기록이 사실과 달라진다.
- 계정 행은 읽기만 한다. 여기서 `last_login_at`·role·비밀번호를 갱신하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status

from app.core.sessions import current_user
from app.models.app_user import AppUser

ADMIN_ROLE = "ADMIN"

__all__ = ["ADMIN_ROLE", "PreviewPrincipal", "require_preview_admin"]


@dataclass(frozen=True)
class PreviewPrincipal:
    """프리뷰 관리 API가 쓰는 인증 주체. 비밀값은 담지 않는다."""

    user_id: int
    email: str
    role: str


def require_preview_admin(user: AppUser = Depends(current_user)) -> PreviewPrincipal:
    """원래 JWT 인증 결과에 ADMIN 역할을 요구한다.

    `current_user`가 이미 비활성·부재 계정을 401로 처리하므로, 여기서는 역할만
    판정한다. 역할은 요청 시점의 기존 계정 값이다(개발 세션 사본이 아니다).
    """
    if user.role != ADMIN_ROLE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="admin role required"
        )
    return PreviewPrincipal(user_id=user.id, email=user.email, role=user.role)
