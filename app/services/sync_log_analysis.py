"""Read-only interpretation of observed sync log formats; raw messages stay intact."""

from __future__ import annotations
import re

CATEGORIES = {
    "run": "실행 제어",
    "preparation": "수집 준비",
    "catalog": "카탈로그",
    "teams": "팀",
    "fixtures": "경기 목록",
    "standings": "순위",
    "players": "선수 기록",
    "events": "경기 이벤트",
    "lineups": "라인업",
    "statistics": "경기 통계",
    "fixture_players": "경기 선수 기록",
    "details": "경기 상세 처리",
    "error": "요청·저장 오류",
    "unclassified": "미분류",
}
EVENTS = {
    "API_TIMEOUT": (
        "외부 API 응답 지연",
        "응답 제한 시간을 초과했습니다. 재시도 결과와 실패 대상을 확인하세요.",
    ),
    "API_RATE_LIMIT": ("외부 API 호출 한도 초과", "호출 한도 회복 후 실패 대상을 다시 실행하세요."),
    "API_PLAN_RESTRICTED": (
        "요금제·시즌 접근 제한",
        "당시 외부 API 응답이 해당 시즌 접근을 제한했습니다. 실행 당시 API 계정·요금제와 지원 시즌을 확인하세요.",
    ),
    "API_AUTH_FAILED": ("외부 API 인증 실패", "외부 API 인증 설정을 확인하세요."),
    "API_UPSTREAM_ERROR": ("외부 API 서버 오류", "재시도 결과와 실패 대상을 확인하세요."),
    "API_REQUEST_FAILED": ("외부 API 요청 실패", "요청 경로와 응답 원문을 확인하세요."),
    "DB_RETRY": ("DB 잠금 충돌 재시도", "일시적인 잠금 충돌로 저장 작업을 재시도합니다."),
    "DB_WRITE_FAILED": ("데이터 저장 실패", "저장 제약 조건과 오류 원문을 확인하세요."),
    "RUN_STARTED": ("수집 시작", ""),
    "RUN_COMPLETED": ("수집 완료", ""),
    "RUN_FINISHED": ("수집 실행 종료", ""),
    "RUN_FAILED": ("수집 실행 실패", "오류 원문과 실행 설정을 확인하세요."),
    "TARGET_FAILED": ("대상 수집 실패", "실패 단계와 오류 원문을 확인하세요."),
    "RUN_INTERRUPTED": (
        "수집 프로세스 중단",
        "저장된 자료는 유지됩니다. 미완료 대상을 다시 실행하세요.",
    ),
    "RUN_CANCELLED": ("수집 취소 완료", "이미 저장한 자료는 유지됩니다."),
}
ENDPOINTS = {
    "events": "events",
    "lineups": "lineups",
    "statistics": "statistics",
    "players": "fixture_players",
}


def classify_log(log):
    message = str(log.get("message", ""))
    code = log.get("code")
    level = log.get("level")
    target = None
    category = "unclassified"
    prefix = re.fullmatch(r"(.+?) \(#(\d+)\)(?: season (\d+))?: (.+)", message)
    body = message
    if prefix:
        name, external_id, year, body = prefix.groups()
        target = f"{name} · {year} 시즌" if year else name
    else:
        generic = re.fullmatch(
            r"(.+): ((?:teams|fixtures|standings|players)(?: page=\d+/\d+)? failed: .+)", message
        )
        if generic:
            target, body = generic.groups()

    def emit(event_code, title, category="run", action="", severity="info", classified=True):
        return dict(
            code=event_code,
            title=title,
            action=action,
            category=category,
            category_label=CATEGORIES[category],
            level=level or severity,
            stage=CATEGORIES.get(log.get("stage"), log.get("stage"))
            or (CATEGORIES[category] if category not in ("run", "unclassified", "error") else None),
            target=target,
            classified=classified,
        )

    if code in EVENTS:
        title, action = EVENTS[code]
        category = "error" if code.startswith(("API_", "DB_")) else "run"
        return emit(
            code,
            title,
            category,
            action,
            severity="warning"
            if code == "DB_RETRY"
            else "error"
            if category == "error" or code in ("RUN_FAILED", "TARGET_FAILED", "RUN_INTERRUPTED")
            else "info",
        )
    if code not in (None, "PROGRESS", "LEGACY_FAILURE"):
        return emit(
            "UNCLASSIFIED", "알 수 없는 이벤트 · 원문 확인 필요", "unclassified", classified=False
        )

    failed = re.fullmatch(
        r"(teams|fixtures|standings|players)(?: page=(\d+)/(\d+))? failed: (.+)", body
    )
    endpoint = re.fullmatch(
        r"(detail|players): (/fixtures/(events|lineups|statistics|players)|/players)(?: fixture=(\d+))?(?: page=(\d+))? (done|failed)",
        body,
    )
    failure = bool(
        failed
        or (endpoint and endpoint[6] == "failed")
        or level == "error"
        or code == "LEGACY_FAILURE"
    )
    if failure:
        category = (
            failed[1]
            if failed
            else (ENDPOINTS.get(endpoint[3], "players") if endpoint else "error")
        )
        reason = failed[4] if failed else message
        cause = None
        if re.search(
            r"api_football_errors=.*['\"]plan['\"].*(?:do not have access to this season|not.*access.*season)",
            reason,
            re.I,
        ):
            cause = "API_PLAN_RESTRICTED"
        elif re.search(
            r"\b(?:ReadTimeout|ConnectTimeout|PoolTimeout|TimeoutException)\b|timed out",
            reason,
            re.I,
        ):
            cause = "API_TIMEOUT"
        elif re.search(r"\bHTTP(?:StatusError)?[ :]*429\b|\b429 Too Many Requests\b", reason, re.I):
            cause = "API_RATE_LIMIT"
        elif re.search(r"\bHTTP(?:StatusError)?[ :]*(401|403)\b", reason, re.I):
            cause = "API_AUTH_FAILED"
        elif re.search(r"\bHTTP(?:StatusError)?[ :]*5\d\d\b", reason, re.I):
            cause = "API_UPSTREAM_ERROR"
        elif re.search(
            r"\b(?:IntegrityError|ForeignKeyViolation|UniqueViolation|DeadlockDetected)\b|violates (?:foreign key|unique|check) constraint",
            reason,
            re.I,
        ):
            cause = "DB_WRITE_FAILED"
        title, action = (
            EVENTS[cause]
            if cause
            else (
                f"{CATEGORIES[category]} 실패 · 원인 미분류",
                "원문에서 구체적인 원인을 확인하세요.",
            )
        )
        return emit(
            cause or "UNCLASSIFIED",
            title,
            category,
            action,
            severity="error",
            classified=bool(cause or failed or endpoint),
        )

    if prefix:
        match = re.fullmatch(r"(teams|fixtures|standings)=(\d+)", body)
        if match:
            return emit(
                "DATA_PROCESSED", f"{CATEGORIES[match[1]]} 데이터 처리 · {match[2]}개", match[1]
            )
        match = re.fullmatch(r"players page=(\d+)/(\d+) (?:rows=(\d+)|(fetched))", body)
        if match:
            title = f"선수 기록 {'조회 완료' if match[4] else '처리'} · {match[1]}/{match[2]}페이지"
            if match[3] is not None:
                title += f" · {match[3]}개"
            return emit("PLAYER_PAGE_PROCESSED", title, "players")
        if endpoint:
            category = ENDPOINTS.get(endpoint[3], "players")
            suffix = (
                f" · 경기 #{endpoint[4]}"
                if endpoint[4]
                else f" · {endpoint[5]}페이지"
                if endpoint[5]
                else ""
            )
            return emit(
                "API_RESPONSE_RECEIVED", f"{CATEGORIES[category]} 조회 완료{suffix}", category
            )
        match = re.fullmatch(r"details fixture=(\d+)", body)
        if match:
            return emit("FIXTURE_PROCESSED", f"경기 상세 처리 · 경기 #{match[1]}", "details")
        if re.fullmatch(r"catalog synced, seasons=\[[\d, ]*\]", body):
            return emit("CATALOG_SYNCED", "리그·시즌 카탈로그 반영", "catalog")
        if body == "start":
            return emit("TARGET_STARTED", "대상 시즌 수집 시작")
        if body == "complete":
            return emit("TARGET_COMPLETED", "대상 시즌 수집 완료")

    if re.fullmatch(r"daily-sync: run started origin=.+", message):
        return emit("RUN_STARTED", "수집 실행 시작")
    if message == "daily-sync: skipped because distributed lock is held":
        return emit("RUN_SKIPPED", "다른 수집이 실행 중이어서 이번 실행을 건너뜀")
    if re.fullmatch(r"daily-sync: acquired advisory lock key=\d+", message):
        return emit("LOCK_ACQUIRED", "중복 실행 방지 확인 · 수집 실행 허용")
    if message == "daily-sync: measuring update size":
        return emit("PLAN_MEASURING", "수집할 처리 범위 확인 중", "preparation")
    match = re.fullmatch(r"daily-sync: loaded (\d+) configured specs", message)
    if match:
        return emit("CONFIG_LOADED", f"수집 대상 설정 불러옴 · {match[1]}개", "preparation")
    match = re.fullmatch(r"daily-sync: (start|measuring) (.+) seasons=(\[[\d, ]*\])", message)
    if match:
        target = match[2]
        return emit(
            "PLAN_MEASURING" if match[1] == "measuring" else "TARGET_STARTED",
            f"{'수집 범위 확인 중' if match[1] == 'measuring' else '대상 수집 시작'} · 시즌 {match[3]}",
            "preparation" if match[1] == "measuring" else "run",
        )
    match = re.fullmatch(r"daily-sync: measured (.+) units=(\d+)", message)
    if match:
        target = match[1]
        return emit("PLAN_MEASURED", f"수집 범위 확인 · {match[2]}개 처리 단계", "preparation")
    match = re.fullmatch(
        r"daily-sync: measured total_units=(\d+) leagues=(\d+) concurrency=(\d+) requests_per_minute=(\d+)",
        message,
    )
    if match:
        return emit(
            "PLAN_MEASURED",
            f"전체 수집 범위 확인 · {match[2]}개 리그 · {match[1]}개 처리 단계",
            "preparation",
        )
    match = re.fullmatch(r"daily-sync: complete (.+)", message)
    if match:
        target = match[1]
        return emit("TARGET_COMPLETED", "대상 리그 수집 완료")
    match = re.fullmatch(
        r"daily-sync: run finished status=(succeeded|failed|cancelled|interrupted) duration=(\d+(?:\.\d+)?)s",
        message,
    )
    if match:
        status = {
            "succeeded": "성공",
            "failed": "실패",
            "cancelled": "취소",
            "interrupted": "중단",
        }[match[1]]
        return emit("RUN_FINISHED", f"수집 실행 종료 · {status} · {match[2]}초")
    return emit(
        "UNCLASSIFIED" if level in ("error", "warning") else "INFO",
        "분류되지 않은 처리 기록 · 원문 확인 필요",
        "unclassified",
        classified=False,
    )


def analyze_logs(logs):
    enriched = []
    stats = {}
    for log in logs:
        analysis = classify_log(log)
        enriched.append({**log, "analysis": analysis})
        if analysis["level"] not in ("error", "warning"):
            continue
        code = analysis["code"]
        group = stats.setdefault(code, dict(code=code, errors=0, warnings=0, target_ids=[]))
        group["errors" if analysis["level"] == "error" else "warnings"] += 1
        if log.get("target_id") is not None and log["target_id"] not in group["target_ids"]:
            group["target_ids"].append(log["target_id"])
    return enriched, stats
