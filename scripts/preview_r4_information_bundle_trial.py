"""R4 정보 원문 묶음 시험 — **실험용 프로토타입 스크립트**(제품 기본 경로 아님).

이 파일이 답하려는 질문은 하나다.

    브라우저 없는 실제 본문 수집 + 읽기 전용 DB 자료로, Google grounding_chunks/supports
    없이도 근거가 붙은 R4(주목 선수) 프리뷰를 만들 수 있는가.

그래서 이 스크립트는 **제품 모듈이 아니다.** 섹션 등록부·프롬프트 계약·검증 경계를
바꾸지 않고, 저장된 검색 후보 URL에서 실제 본문을 모아 정보 원문 묶음을 만든 뒤 한 번만
생성 모델을 부른다.

재사용 경계(정확히 무엇을 그대로 쓰는가):

- 그대로 씀: `provider.request_model`/`execute_request`(예산·시도·원문 아티팩트),
  `players.load_prompt`/`build_prompt`(제품 R4 프롬프트), `players.parse_model_output`,
  `players.model_players`, `players.resolve_selection_names` + DB 한국어 이름 해석기,
  `players.compose_players_body`(두 표시 필드 분리), `runner.run_section_workflow`
  (노드 실행·모듈 결과 저장), `store`/`artifacts`(preview_dev 기록).
- 대체함(프로토타입 전용, 명시적으로 미승인): `form.validate_response`의
  grounding URL 정확 일치 + API 문자열 사실 대조 경계 → 아래
  `validate_bundle_references`로 교체. `google_search` 도구도 끈다. 이 대체 검증기는
  제품/승인 모듈이 아니며, 통과가 사실 진위 검증을 뜻하지 않는다.

경계:

- 유료 모델 전송은 **정확히 1회**다(`model_requests=1`, `normal_model_calls=1`,
  `attempts_per_call=1`). 429·오류·빈 응답에도 재전송하지 않고 멈춘다.
- DB는 기존 좁은 읽기 역할만 쓴다. 쓰기는 `preview_dev`의 이 실행 소유 행뿐이다.
- 비밀값은 읽기만 하고 출력하지 않는다.
- 본문 전문은 저장소에 넣지 않는다. 저장소에는 해시·짧은 발췌·출처만 남기고 전문은
  `/tmp`와 `preview_dev` 아티팩트에 둔다.

사용:

    .venv/bin/python scripts/preview_r4_information_bundle_trial.py --phase all
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

PROTOTYPE_LABEL = "experimental-prototype-not-product"
SCRIPT_VERSION = "r4-information-bundle-trial-1"

DEV_CREDENTIALS = Path.home() / ".config" / "match-preview" / "preview-dev.env"
MODEL_CREDENTIALS = Path.home() / ".config" / "match-preview" / "model-live.env"
MODEL_ENV_PREFIX = "PREVIEW_MODEL_"

ISOLATED_VENV = Path("/tmp/preview-scraper-compare.PRpmWn/venv")
SCRATCH_ROOT = Path("/tmp")
EXTRACTOR_HELPER = SCRATCH_ROOT / "preview-r4-information-bundle.extract.py"

FIXTURE_EXTERNAL_ID = 1557474
SEARCH_EVIDENCE_DIR = (
    REPO_ROOT / "docs" / "implementation" / "match-preview" / "evidence" / "korean-fallback"
)
EVIDENCE_DIR = (
    REPO_ROOT / "docs" / "implementation" / "match-preview" / "evidence" / "r4-information-bundle"
)
STORED_CAPTURE_DIR = Path("/tmp/preview-scraper-compare.PRpmWn/raw")

HTTP_TIMEOUT_SECONDS = 25.0
HTTP_MAX_REDIRECTS = 5
MAX_CANDIDATE_FETCHES = 6
MAX_FULHAM_API_ATTEMPTS = 3
MAX_SOURCE_PASSAGES = 3
MAX_PASSAGE_CHARS = 1_500
MAX_WEB_EVIDENCE_CHARS = 16_000
# Trafilatura가 이보다 적게 남기면 목록/표 페이지로 보고 텍스트 경로로 폴백한다
# (비교 보고서: 스쿼드 100KB HTML → 163자로 명단 전량 유실).
LIST_PAGE_FALLBACK_CHARS = 400
# 각주·외부 링크·인용 목록 줄. 본문 발췌에서 뺀다(근거가 아니라 참조 목록이다).
_REFERENCE_LINE = re.compile(
    r"^(?:-\s*)?(?:↑|External links|References|See also|Further reading|Bibliography)\b"
    r"|^-\s*↑"
    r"|^Retrieved \d"
    # "- 1 2 Banerjee, Apratim (13 January 2024). ..." 같은 각주 번호 줄
    r"|^-\s*\d+(?:\s+\d+)*\s+\S"
)
MAX_ROSTER_ROWS = 40
EXCERPT_CHARS_IN_EVIDENCE = 420
MAX_PAST_MATCHES = 10

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


# --------------------------------------------------------------------------
# 환경
# --------------------------------------------------------------------------


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise SystemExit(f"missing credentials file: {path}")
    mode = oct(path.stat().st_mode)[-3:]
    if mode != "600":
        raise SystemExit(f"refusing credentials file with mode {mode} (expected 600): {path}")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key] = _unquote(value)
    return values


def _load_environment() -> dict[str, Any]:
    """개발·모델 설정을 환경으로 올린다. 값은 돌려주지 않고 키 존재만 보고한다."""
    dev = _read_env_file(DEV_CREDENTIALS)
    os.environ.setdefault("PREVIEW_DATABASE_URL", dev.get("PREVIEW_DEV_DATABASE_URL", ""))
    os.environ.setdefault(
        "PREVIEW_IDENTITY_DATABASE_URL", dev.get("PREVIEW_IDENTITY_DATABASE_URL", "")
    )
    os.environ.setdefault(
        "PREVIEW_FIXTURES_DATABASE_URL", dev.get("PREVIEW_FIXTURES_DATABASE_URL", "")
    )
    os.environ.setdefault("PREVIEW_NAMES_DATABASE_URL", dev.get("PREVIEW_NAMES_DATABASE_URL", ""))
    os.environ.setdefault("PREVIEW_ALLOW_NONLOCAL_DB", dev.get("PREVIEW_ALLOW_NONLOCAL_DB", "0"))
    os.environ.setdefault(
        "PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB",
        dev.get("PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB", "0"),
    )
    os.environ.setdefault("PREVIEW_ENV", "dev")

    model = _read_env_file(MODEL_CREDENTIALS)
    for key, value in model.items():
        if key.startswith(MODEL_ENV_PREFIX):
            os.environ.setdefault(key, value)
    return {
        "dev_keys": sorted(k for k in dev if k.startswith("PREVIEW_")),
        "model_keys": sorted(k for k in model if k.startswith(MODEL_ENV_PREFIX)),
    }


# --------------------------------------------------------------------------
# 저장된 검색 후보 목록
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SavedCandidate:
    """저장된 검색 응답에서 뽑은 URL 후보. 새 검색 호출 없이 재사용한다."""

    url: str
    label: str
    origin: str
    note: str | None = None


def _candidate_urls_from_saved() -> tuple[list[SavedCandidate], list[dict[str, Any]]]:
    """저장된 두 응답에서 후보 URL을 뽑는다. 파일 내용은 읽기만 한다."""
    out: list[SavedCandidate] = []
    notes: list[dict[str, Any]] = []
    for name in ("latest-full-response.json", "previous-success-full-response.json"):
        path = SEARCH_EVIDENCE_DIR / name
        if not path.exists():
            notes.append({"file": name, "status": "missing"})
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        candidate = (payload.get("candidates") or [{}])[0]
        metadata = candidate.get("grounding_metadata") or {}
        notes.append(
            {
                "file": name,
                "response_id": payload.get("response_id"),
                "create_time": payload.get("create_time"),
                "model_version": payload.get("model_version"),
                "grounding_keys": sorted(metadata.keys()),
                "has_chunks": "grounding_chunks" in metadata,
                "chunk_count": len(metadata.get("grounding_chunks") or ()),
                "queries": len(metadata.get("web_search_queries") or ()),
            }
        )
        for index, chunk in enumerate(metadata.get("grounding_chunks") or ()):
            web = (chunk or {}).get("web") or {}
            uri = web.get("uri")
            if not uri:
                continue
            out.append(
                SavedCandidate(
                    url=str(uri),
                    label=str(web.get("title") or web.get("domain") or f"chunk-{index}"),
                    origin=f"{name}#grounding_chunks[{index}]",
                    note="provider grounding redirect URL",
                )
            )
        # 공급자가 chunks를 주지 않은 응답은 모델이 쓴 evidence URL만 남는다.
        text = json.dumps(candidate.get("content") or {}, ensure_ascii=False)
        for url in sorted(set(re.findall(r"https?://[^\s\"'\\]+", text))):
            if "vertexaisearch.cloud.google.com" in url or url.endswith("/svg"):
                continue
            if any(item.url == url for item in out):
                continue
            out.append(
                SavedCandidate(
                    url=url,
                    label=url,
                    origin=f"{name}#model_evidence",
                    note="모델 응답 본문에 적힌 URL(공급자 metadata 아님)",
                )
            )
    return out, notes


# --------------------------------------------------------------------------
# 원문 수집 (브라우저 없음)
# --------------------------------------------------------------------------


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_extractor_helper() -> None:
    """추출 헬퍼를 격리 venv용 스크래치 경로에 쓴다(제품 venv 변경 없음)."""
    body = '''"""Extraction helper (scratch). Reads {"html_path": ...} on argv[2]."""
import json
import sys

path = sys.argv[1]
html = open(path, "rb").read()
text = html.decode("utf-8", "replace")
result = {"trafilatura": "", "fallback": "", "extractor": None, "error": None}
try:
    import trafilatura

    extracted = trafilatura.extract(
        text, include_comments=False, include_tables=True, include_links=False
    ) or ""
    result["trafilatura"] = extracted
    if extracted.strip():
        result["extractor"] = "trafilatura-2.3.1/defaults"
except Exception as exc:  # noqa: BLE001
    result["error"] = f"{type(exc).__name__}: {exc}"
if len(result["trafilatura"].strip()) < {fallback_threshold}:
    # 목록·표 페이지는 Trafilatura가 본문을 거의 다 버린다. 그 경우에만 텍스트 경로를
    # 계산해 호출자가 비교·폴백할 수 있게 함께 돌려준다(짧은 기사도 여기 들어오지만,
    # 폴백은 텍스트가 2배 이상 길 때만 쓴다).
    try:
        from scrapling.parser import Adaptor

        page = Adaptor(html, url="")
        fallback = str(page.get_all_text(
            separator="\\n", strip=True, ignore_tags=("script", "style", "noscript")
        ))
        result["fallback"] = fallback
        if fallback.strip() and not result["trafilatura"].strip():
            result["extractor"] = "scrapling-0.5.1/get_all_text(fallback)"
    except Exception as exc:  # noqa: BLE001
        result["error"] = (result["error"] or "") + f" | fallback {type(exc).__name__}: {exc}"
print(json.dumps(result))
'''
    # 헬퍼는 별도 프로세스(격리 venv)에서 돌므로 이 모듈의 이름을 볼 수 없다.
    # 상수는 문자열에 직접 넣는다.
    body = body.replace("{fallback_threshold}", str(LIST_PAGE_FALLBACK_CHARS))
    EXTRACTOR_HELPER.write_text(body, encoding="utf-8")


def _extract_body(html: bytes) -> dict[str, Any]:
    """격리 venv에서 본문을 추출한다. 제품 venv에는 추출 라이브러리가 없다."""
    python = ISOLATED_VENV / "bin" / "python"
    if not python.exists():
        return {
            "text": "",
            "extractor": None,
            "error": f"isolated venv python missing: {python}",
        }
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as handle:
        handle.write(html)
        temp_path = handle.name
    try:
        completed = subprocess.run(
            [str(python), str(EXTRACTOR_HELPER), temp_path],
            capture_output=True,
            text=True,
            timeout=120,
        )
    finally:
        Path(temp_path).unlink(missing_ok=True)
    if completed.returncode != 0:
        return {
            "text": "",
            "extractor": None,
            "error": f"extractor exit {completed.returncode}: {completed.stderr.strip()[:400]}",
        }
    try:
        payload = json.loads(completed.stdout or "{}")
    except ValueError:
        return {"text": "", "extractor": None, "error": "extractor produced non-JSON output"}
    text = str(payload.get("trafilatura") or "")
    fallback = str(payload.get("fallback") or "")
    chosen = text
    extractor = payload.get("extractor") if text.strip() else None
    # 목록·표 페이지에서 Trafilatura가 본문을 거의 다 버리는 사례가 관측됐다
    # (비교 보고서: 스쿼드 100KB HTML → 163자). 그때만 텍스트 경로로 폴백한다.
    if len(text.strip()) < LIST_PAGE_FALLBACK_CHARS and len(fallback.strip()) > len(text.strip()) * 2:
        chosen = fallback
        extractor = "scrapling-0.5.1/get_all_text(list_page_fallback)"
    return {
        "text": chosen.strip(),
        "extractor": extractor,
        "error": payload.get("error"),
        "trafilatura_chars": len(text),
        "fallback_chars": len(fallback),
    }


def _looks_like_block_page(text: str, status: int) -> str | None:
    lowered = text.lower()
    markers = ("just a moment", "enable javascript and cookies", "attention required",
               "access denied", "captcha")
    for marker in markers:
        if marker in lowered:
            return f"차단/챌린지 문구 감지('{marker}')"
    if status in (401, 403, 429):
        return f"HTTP {status}"
    return None


def _fetch_candidate(client: Any, candidate: SavedCandidate) -> dict[str, Any]:
    """후보 URL 하나를 실제 HTTP로 가져와 본문을 뽑는다. 실패도 기록한다."""
    started = time.perf_counter()
    record: dict[str, Any] = {
        "requested_url": candidate.url,
        "discovered_from": candidate.origin,
        "discovery_note": candidate.note,
        "method": "fresh_http",
        "http_status": None,
        "final_url": None,
        "redirects": 0,
        "html_bytes": 0,
        "html_sha256": None,
        "title": None,
        "body": "",
        "body_chars": 0,
        "extractor": None,
        "failure": None,
        "elapsed_ms": 0,
    }
    try:
        response = client.get(candidate.url)
    except Exception as exc:  # noqa: BLE001 - 실패를 숨기지 않고 기록한다
        record["failure"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        record["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        return record
    record["http_status"] = response.status_code
    record["final_url"] = str(response.url)
    record["redirects"] = len(response.history)
    html = response.content or b""
    record["html_bytes"] = len(html)
    record["html_sha256"] = _sha256_bytes(html) if html else None
    extracted = _extract_body(html) if html else {"text": "", "error": "empty body", "extractor": None}
    body = str(extracted.get("text") or "")
    record["body"] = body
    record["body_chars"] = len(body)
    record["extractor"] = extracted.get("extractor")
    record["extractor_error"] = extracted.get("error")
    match = re.search(r"<title[^>]*>(.*?)</title>", html.decode("utf-8", "replace"), re.S | re.I)
    record["title"] = re.sub(r"\s+", " ", match.group(1)).strip() if match else None
    blocked = _looks_like_block_page(body or html.decode("utf-8", "replace")[:20000],
                                     response.status_code)
    if response.status_code >= 400:
        record["failure"] = f"HTTP {response.status_code}"
    elif not body.strip():
        record["failure"] = "본문 추출 0자(정적 HTML에 기사 텍스트 없음 또는 JS 셸)"
    elif blocked:
        record["failure"] = blocked
    record["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    return record


def _reuse_stored_capture(candidate: SavedCandidate, capture_name: str) -> dict[str, Any]:
    """이전 조사에서 저장한 **일반 HTTP** 캡처를 명시 시각과 함께 재사용한다.

    브라우저 렌더 캡처(`fulham_rendered.html`)는 여기서 쓰지 않는다. 브라우저 없이
    얻은 본문이라는 주장에 렌더 결과를 섞지 않기 위해서다.
    """
    path = STORED_CAPTURE_DIR / capture_name
    started = time.perf_counter()
    record: dict[str, Any] = {
        "requested_url": candidate.url,
        "discovered_from": candidate.origin,
        "discovery_note": candidate.note,
        "method": "stored_http_replay",
        "http_status": None,
        "final_url": None,
        "redirects": 0,
        "html_bytes": 0,
        "html_sha256": None,
        "title": None,
        "body": "",
        "body_chars": 0,
        "extractor": None,
        "failure": None,
        "elapsed_ms": 0,
    }
    if not path.exists():
        record["failure"] = f"저장 캡처 없음: {path.name}"
        return record
    html = path.read_bytes()
    captured_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    record.update(
        {
            "stored_capture_path": str(path),
            "stored_capture_at": captured_at.isoformat(),
            "stored_capture_note": (
                "이전 조사에서 같은 URL을 일반 HTTP로 받아 저장한 HTML이다. 새 요청이"
                " 아니라 저장본 재사용이며, 수집 시각은 파일 기록 시각이다."
            ),
            "html_bytes": len(html),
            "html_sha256": _sha256_bytes(html),
        }
    )
    extracted = _extract_body(html)
    body = str(extracted.get("text") or "")
    record["body"] = body
    record["body_chars"] = len(body)
    record["extractor"] = extracted.get("extractor")
    record["extractor_error"] = extracted.get("error")
    match = re.search(r"<title[^>]*>(.*?)</title>", html.decode("utf-8", "replace"), re.S | re.I)
    record["title"] = re.sub(r"\s+", " ", match.group(1)).strip() if match else None
    if not body.strip():
        record["failure"] = "본문 추출 0자"
    record["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    return record


def _fulham_static_probe(client: Any, article_url: str) -> list[dict[str, Any]]:
    """Fulham JS 기사의 좁은 대안 탐색: 정적 JSON/공개 본문 API만 직접 확인한다.

    전체 사이트 크롤·인증 우회·CAPTCHA 해결은 하지 않는다. 시도 상한을 넘으면 멈추고
    실패를 기록한 뒤 다른 자료로 넘어간다(끝없는 역설계 금지).
    """
    attempts: list[dict[str, Any]] = []
    base = article_url.rstrip("/")
    candidates = [f"{base}/_payload.json", f"{base}/payload.json", "https://www.fulhamfc.com/_payload.json"]
    for url in candidates[:MAX_FULHAM_API_ATTEMPTS]:
        started = time.perf_counter()
        row: dict[str, Any] = {"url": url, "method": "public_api_probe", "http_status": None,
                               "content_type": None, "bytes": 0, "body_chars": 0,
                               "failure": None, "elapsed_ms": 0, "excerpt": ""}
        try:
            response = client.get(url, headers={"Accept": "application/json,*/*"})
            row["http_status"] = response.status_code
            row["content_type"] = response.headers.get("content-type")
            payload = response.content or b""
            row["bytes"] = len(payload)
            text = payload.decode("utf-8", "replace")
            row["body_chars"] = len(text)
            row["excerpt"] = text[:EXCERPT_CHARS_IN_EVIDENCE]
            if response.status_code >= 400:
                row["failure"] = f"HTTP {response.status_code}"
            elif text.lstrip()[:1] not in ("{", "["):
                row["failure"] = "JSON이 아닌 응답"
        except Exception as exc:  # noqa: BLE001
            row["failure"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        row["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        attempts.append(row)
        if not row["failure"]:
            break
    return attempts


# --------------------------------------------------------------------------
# 출처 성격 라벨 (기사 원문을 프리뷰로 부르지 않는다)
# --------------------------------------------------------------------------


SOURCE_TYPE_RULES: tuple[tuple[str, str, str], ...] = (
    ("match-report", "past_match_report", "지난 경기 보도(리포트). 이번 경기 프리뷰가 아니다."),
    ("match_report", "past_match_report", "지난 경기 보도(리포트)."),
    ("/squad", "stats", "팀 스쿼드/명단 자료(통계 성격)."),
    ("/players/", "stats", "선수 개인 기록/통계 페이지."),
    ("/wiki/", "profile", "백과 선수 소개(프로필)."),
    ("predictions", "preview", "경기 예측/프리뷰 성격 페이지."),
)


def _classify_source(url: str, title: str | None, body: str) -> tuple[str, str]:
    haystack = f"{url} {title or ''}".lower()
    for needle, kind, note in SOURCE_TYPE_RULES:
        if needle in haystack:
            return kind, note
    if re.search(r"\b(match report|player ratings|report:)", (title or "").lower()):
        return "past_match_report", "지난 경기 보도(리포트)."
    head = body[:600].lower()
    if any(token in head for token in ("match report", "full-time", "full time")):
        return "past_match_report", "본문 머리에 경기 종료/리포트 표지가 있다."
    if "*" not in url and len(body) > 1200:
        return "article", "성격 표지가 불명확한 일반 기사 본문."
    return "unknown", "성격을 확정하지 못했다(프리뷰라고 단정하지 않는다)."


# --------------------------------------------------------------------------
# DB 스냅샷 (읽기 전용)
# --------------------------------------------------------------------------


def _collect_db_snapshot(*, moment: datetime) -> dict[str, Any]:
    """저장된 경기·순위·부상·이름 자료를 읽기 전용으로 모은다."""
    from sqlalchemy import text

    from app.auth.identity import build_read_only_engine
    from app.preview.localized_names import DbNameLookup, load_name_index
    from app.preview.sources.fixtures import StoredFixtureReader

    started = time.perf_counter()
    fixtures_url = os.environ.get("PREVIEW_FIXTURES_DATABASE_URL") or ""
    names_url = os.environ.get("PREVIEW_NAMES_DATABASE_URL") or ""
    snapshot: dict[str, Any] = {
        "collected_at": moment.isoformat(),
        "prototype": PROTOTYPE_LABEL,
        "fixture": None,
        "teams": [],
        "standings": [],
        "injuries": {"rows": [], "state": "unknown", "note": None},
        "past_matches": {"rows": [], "state": "not_run", "statement": None},
        "roles": {},
        "failures": [],
        "elapsed_ms": 0,
    }
    if not fixtures_url:
        snapshot["failures"].append("PREVIEW_FIXTURES_DATABASE_URL 없음")
        return snapshot

    reader = StoredFixtureReader.from_url(fixtures_url)
    try:
        access = reader.access()
        snapshot["roles"]["fixtures"] = access.role
        if not access.readable:
            snapshot["failures"].append(f"경기 자료 읽기 권한 없음: {list(access.missing)}")
            return snapshot
        stored = reader.get_fixture(fixture_id=FIXTURE_EXTERNAL_ID)
        if stored is None:
            snapshot["failures"].append(f"경기 {FIXTURE_EXTERNAL_ID} 없음")
            return snapshot
        identity = stored.identity()
        snapshot["fixture"] = stored.to_dict()
        snapshot["fixture"]["id_space_note"] = (
            "internal_id는 DB 행, fixture_id는 API-Football 외부 ID다."
            " 저장 경기의 팀 ID(13/4)는 DB 내부 키다."
        )
        standings = reader.standings_for_league(league_id=identity.league_id, season=identity.season)
        snapshot["standings"] = [
            dict(row) for row in standings if int(row["team_id"]) in {13, 4}
        ]
        snapshot["standings_source"] = {
            "table": "public.standings",
            "reader": "StoredFixtureReader.standings_for_league",
            "role": access.role,
            "rows_total": len(standings),
        }
        injuries = reader.injuries_for_fixture(identity.fixture_id)
        snapshot["injuries"] = {
            "rows": [row.__dict__ | {} for row in injuries],
            "state": "available" if injuries else "unknown",
            "note": (
                "저장된 부상 행이 없다. 이것은 '부상자 없음'의 증거가 아니다."
                if not injuries
                else "저장된 부상 행을 그대로 옮겼다(결장 확정으로 승격하지 않음)."
            ),
            "source": {"table": "public.injury", "role": access.role},
        }

        engine = build_read_only_engine(fixtures_url)
        statement = """
            SELECT f.external_id, f.kickoff_at, f.home_team_id, f.away_team_id,
                   f.goals_home, f.goals_away, f.status_short
            FROM public.fixture f
            WHERE (f.home_team_id = ANY(:team_ids) OR f.away_team_id = ANY(:team_ids))
              AND f.status_short = 'FT'
              AND f.kickoff_at < :as_of
            ORDER BY f.kickoff_at DESC
            LIMIT :limit
        """
        try:
            with engine.connect() as conn:
                role = conn.execute(text("SELECT current_user")).scalar()
                snapshot["roles"]["past_matches"] = role
                rows = [
                    dict(row)
                    for row in conn.execute(
                        text(statement),
                        {"team_ids": [13, 4], "as_of": moment, "limit": MAX_PAST_MATCHES},
                    ).mappings()
                ]
            snapshot["past_matches"] = {
                "rows": [
                    {
                        **row,
                        "kickoff_at": row["kickoff_at"].isoformat()
                        if hasattr(row["kickoff_at"], "isoformat")
                        else str(row["kickoff_at"]),
                    }
                    for row in rows
                ],
                "state": "available" if rows else "not_run",
                "statement": " ".join(statement.split()),
                "source": {"table": "public.fixture", "role": role},
                "note": "지난 완료 경기(FT)만. 이번 경기 예측 근거가 아니라 배경 자료다.",
            }
        except Exception as exc:  # noqa: BLE001
            snapshot["failures"].append(f"지난 경기 읽기 실패: {type(exc).__name__}")
            snapshot["past_matches"]["state"] = "call_error"
        finally:
            engine.dispose()
    finally:
        reader.close()

    if not names_url:
        snapshot["failures"].append("PREVIEW_NAMES_DATABASE_URL 없음(한국어 표기 미확인)")
        snapshot["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        return snapshot

    lookup = DbNameLookup.from_url(names_url)
    try:
        with lookup._engine.connect() as conn:  # noqa: SLF001 - 역할 이름만 확인한다
            snapshot["roles"]["names"] = conn.execute(text("SELECT current_user")).scalar()
        teams = lookup.load_teams(team_ids=[13, 4])
        snapshot["teams"] = [
            {
                "team_id": row.team_id,
                "external_id": row.external_id,
                "english_name": row.english_name,
                "name_ko": row.name_ko,
                "short_name_ko": row.short_name_ko,
                "source": {"table": "public.team + public.team_translation",
                           "role": snapshot["roles"].get("names")},
            }
            for row in teams
        ]
        index = load_name_index(lookup, team_ids=[13, 4], include_rosters=True)
        roster: list[dict[str, Any]] = []
        for row in index.players[:MAX_ROSTER_ROWS]:
            roster.append(
                {
                    "player_id": row.player_id,
                    "english_name": row.english_name,
                    "name_ko": getattr(row, "name_ko", None),
                    "team_id": getattr(row, "current_team_id", None)
                    or getattr(row, "team_id", None),
                }
            )
        snapshot["roster"] = roster
        snapshot["roster_source"] = {
            "reader": "DbNameLookup.load_players",
            "role": snapshot["roles"].get("names"),
            "rows": len(index.players),
        }
        snapshot["_name_index"] = index  # 같은 실행 안에서만 쓰는 메모리 객체
    except Exception as exc:  # noqa: BLE001
        snapshot["failures"].append(f"이름/로스터 읽기 실패: {type(exc).__name__}")
    finally:
        lookup.close()
    snapshot["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    return snapshot


def _db_fact_rows(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    """DB 스냅샷에서 모델에 전달할 구조화 사실 행을 만든다(값을 만들지 않고 옮긴다)."""
    rows: list[dict[str, Any]] = []
    fixture = snapshot.get("fixture") or {}
    if fixture:
        rows.append(
            {
                "fact_id": "api:fixture-identity",
                "text": (
                    f"경기 {fixture.get('label')} · 리그 {fixture.get('league_name')}"
                    f"({fixture.get('league_id')}) · 시즌 {fixture.get('season')} ·"
                    f" 킥오프(UTC) {fixture.get('kickoff_at')} · 상태 {fixture.get('status_short')}"
                ),
                "source": "public.fixture",
            }
        )
    for row in snapshot.get("standings") or ():
        rows.append(
            {
                "fact_id": f"api:standings-{row['team_id']}",
                "text": (
                    f"team_id {row['team_id']}: 리그 {row.get('rank')}위, {row.get('played')}경기"
                    f" {row.get('win')}승 {row.get('draw')}무 {row.get('loss')}패,"
                    f" 승점 {row.get('points')}, 득점 {row.get('goals_for')}"
                    f" 실점 {row.get('goals_against')}, 최근 5경기 폼 {row.get('form')}"
                ),
                "source": "public.standings",
            }
        )
    for row in snapshot.get("past_matches", {}).get("rows") or ():
        rows.append(
            {
                "fact_id": f"api:past-{row['external_id']}",
                "text": (
                    f"지난 경기 {row['external_id']}({row['kickoff_at']}):"
                    f" team {row['home_team_id']} {row['goals_home']}-{row['goals_away']}"
                    f" team {row['away_team_id']} ({row['status_short']})"
                ),
                "source": "public.fixture",
            }
        )
    injuries = snapshot.get("injuries") or {}
    if injuries.get("rows"):
        rows.append(
            {
                "fact_id": "api:injury-count",
                "text": f"저장된 부상·출전 불확실 행 {len(injuries['rows'])}건.",
                "source": "public.injury",
            }
        )
    return rows


# --------------------------------------------------------------------------
# 정보 원문 묶음
# --------------------------------------------------------------------------


def _group_lines(body: str, *, keywords: Sequence[str] = ()) -> list[str]:
    """줄 단위 추출본을 의미 있는 구간으로 묶는다.

    선수 명단은 이름·포지션·출전 기록이 각각 다른 줄로 나온다. `#번호` 줄을 경계로
    삼아 한 선수 기록을 한 구간으로 묶고, 그 밖의 줄은 문장 길이 기준으로 이어 붙인다.
    묶음이 문단 경계를 넘지 않게 원문 순서를 유지한다.
    """
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    blocks: list[str] = []
    buffer: list[str] = []
    for line in lines:
        # 각주·외부 링크·인용 목록은 기사/문서 본문이 아니다. 묶기 전에 버린다.
        if _REFERENCE_LINE.match(line):
            continue
        if line.startswith("#"):
            if buffer:
                blocks.append(" ".join(buffer))
            buffer = [line]
            continue
        buffer.append(line)
        if len(" ".join(buffer)) >= 220:
            blocks.append(" ".join(buffer))
            buffer = []
    if buffer:
        blocks.append(" ".join(buffer))
    # 너무 긴 구간은 문장 경계에서 나눈다(중간 절단 금지).
    split: list[str] = []
    for block in blocks:
        if len(block) <= MAX_PASSAGE_CHARS:
            split.append(block)
            continue
        chunk = ""
        for sentence in re.split(r"(?<=[.!?])\s+", block):
            if len(chunk) + len(sentence) + 1 > MAX_PASSAGE_CHARS:
                if chunk:
                    split.append(chunk)
                chunk = sentence
            else:
                chunk = f"{chunk} {sentence}".strip()
        if chunk:
            split.append(chunk)
    return [block for block in split if block.strip()]


def _has_content_signal(block: str) -> bool:
    """발췌로 쓸 만한 신호(수치·선수 기록·문장)가 있는지 본다. 판정이 아니라 정렬용."""
    if re.search(r"\d+\s*(Apps|Goals|goals|minutes|apps)\b", block):
        return True
    if block.startswith("#") and re.search(r"[A-Za-zÀ-ÿ]{3,}", block):
        return True
    return len(re.findall(r"[.!?]\s", block)) >= 1 and len(block) >= 120


def _is_reference_block(block: str) -> bool:
    """각주·인용 목록은 근거 본문이 아니다. 발췌 우선순위에서 뒤로 보낸다."""
    stripped = block.strip()
    if stripped.startswith("- ↑") or stripped.startswith("↑"):
        return True
    # 표 칸이 대부분 비어 있는 인포박스/각주 형태
    if stripped.count("|") >= 6 and stripped.count("|  |") >= 1:
        return True
    return stripped.startswith("|") and "Retrieved" in stripped and len(stripped) > 200


def _passages(body: str, *, keywords: Sequence[str] = ()) -> list[str]:
    """문단 경계를 유지한 채 상한 안에서 발췌를 고른다(중간 절단 금지).

    선택 기준(설계 §6.1): 질의·팀·선수 표기가 있는 문단을 먼저 고르고, 같은 구간은
    합쳐 중복을 제거한다. 남은 길이에 맞추려고 문장을 중간에서 자르지 않는다.
    """
    raw_blocks = [chunk.strip() for chunk in re.split(r"\n{2,}", body) if chunk.strip()]
    if len(raw_blocks) <= 1:
        # 단일 줄 덩어리로만 추출된 경우(텍스트 경로) 한 줄씩 쪼개지 않고 **묶는다**.
        # 명단은 `#9 / Erling Haaland / Attacker / 14 Apps · 14 Goals`처럼 한 줄씩
        # 떨어져 나오므로, 한 줄씩 자르면 의미 있는 구간이 사라진다.
        raw_blocks = _group_lines(body, keywords=keywords)
    # 표 구분선만 있는 줄은 문단으로 세지 않는다.
    blocks = [block for block in raw_blocks if not re.fullmatch(r"[|\-\s]+", block)]
    keys = [k.casefold() for k in keywords if k and len(k) > 2]

    def relevance(block: str) -> int:
        low = block.casefold()
        hits = sum(1 for key in keys if key in low)
        # 작은 탐색 메뉴가 긴 본문 구간보다 먼저 뽑히지 않게 길이로 정규화한다.
        return hits * 1000 // (len(block) + 400)

    def is_table(block: str) -> bool:
        return block.count("|") >= 4

    # 산문을 먼저 채운다. 표·인포박스·각주는 산문이 모자랄 때만 보탠다.
    prose = [b for b in blocks if not is_table(b) and not _is_reference_block(b)]
    other = [b for b in blocks if b not in prose]

    picked: list[str] = []
    seen: set[str] = set()
    total = 0
    for pool in (prose, other):
        order = sorted(
            range(len(pool)),
            key=lambda i: (-relevance(pool[i]), 0 if _has_content_signal(pool[i]) else 1, i),
        )
        for index in order:
            if len(picked) >= MAX_SOURCE_PASSAGES:
                break
            block = pool[index]
            if len(block) > MAX_PASSAGE_CHARS:
                # 긴 문단은 문장 경계에서만 자른다(중간 절단 금지).
                chunk = ""
                for sentence in re.split(r"(?<=[.!?])\s+", block):
                    if len(chunk) + len(sentence) + 1 > MAX_PASSAGE_CHARS:
                        break
                    chunk = f"{chunk} {sentence}".strip()
                if not chunk:
                    continue
                block = chunk
            key = block.casefold()
            if key in seen:
                continue
            if total + len(block) > MAX_PASSAGE_CHARS * MAX_SOURCE_PASSAGES:
                continue
            seen.add(key)
            picked.append(block)
            total += len(block)
    # 원문 순서로 되돌려 인용 구간이 뒤섞이지 않게 한다.
    return sorted(picked, key=lambda item: blocks.index(item))


def _build_bundle(
    *,
    moment: datetime,
    db_snapshot: Mapping[str, Any],
    collected: Sequence[Mapping[str, Any]],
    discovery_notes: Sequence[Mapping[str, Any]],
    fulham_probes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    sources: list[dict[str, Any]] = []
    used_chars = 0
    # 발췌 우선순위에 쓰는 표기: 이 경기의 두 팀 이름과 DB 로스터 표기.
    bundle_keywords: list[str] = []
    for team in db_snapshot.get("teams") or ():
        for key in ("english_name", "name_ko", "short_name_ko"):
            if team.get(key):
                bundle_keywords.append(str(team[key]))
    for row in db_snapshot.get("roster") or ():
        for key in ("english_name", "name_ko"):
            if row.get(key):
                bundle_keywords.append(str(row[key]))
    for record in collected:
        body = str(record.get("body") or "")
        # 실패로 판정된 후보는 본문 글자가 남아 있어도 근거로 쓰지 않는다.
        # (Forebet 403은 "Enable JavaScript and cookies to continue" 41자를 낸다.)
        if not body.strip() or record.get("failure"):
            sources.append(
                {
                    "source_id": f"src:{_slug(record.get('requested_url'))}",
                    "source_type": "unavailable",
                    "source_type_note": "본문을 확보하지 못했다. 후보로만 남는다.",
                    "requested_url": record.get("requested_url"),
                    "final_url": record.get("final_url"),
                    "title": record.get("title"),
                    "capture_time": moment.isoformat(),
                    "method": record.get("method"),
                    "stored_capture_at": record.get("stored_capture_at"),
                    "collector": record.get("extractor"),
                    "http_status": record.get("http_status"),
                    "html_sha256": record.get("html_sha256"),
                    "body_chars": 0,
                    "body": "",
                    "passages": [],
                    "failure": record.get("failure") or "본문 없음",
                    "elapsed_ms": record.get("elapsed_ms"),
                }
            )
            continue
        source_type, type_note = _classify_source(
            str(record.get("final_url") or record.get("requested_url")),
            record.get("title"),
            body,
        )
        passages = _passages(body, keywords=bundle_keywords)
        budget = max(0, MAX_WEB_EVIDENCE_CHARS - used_chars)
        trimmed: list[str] = []
        for passage in passages:
            if budget <= 0:
                break
            if len(passage) > budget:
                break
            trimmed.append(passage)
            budget -= len(passage)
            used_chars += len(passage)
        sources.append(
            {
                "source_id": f"src:{_slug(record.get('requested_url'))}",
                "source_type": source_type,
                "source_type_note": type_note,
                "requested_url": record.get("requested_url"),
                "final_url": record.get("final_url"),
                "title": record.get("title"),
                "capture_time": moment.isoformat(),
                "method": record.get("method"),
                "stored_capture_at": record.get("stored_capture_at"),
                "collector": record.get("extractor"),
                "http_status": record.get("http_status"),
                "redirects": record.get("redirects"),
                "html_sha256": record.get("html_sha256"),
                "body_chars": len(body),
                "body_sha256": _sha256_text(body),
                "body": body,
                "passages": trimmed,
                "failure": record.get("failure"),
                "elapsed_ms": record.get("elapsed_ms"),
            }
        )
    return {
        "prototype": PROTOTYPE_LABEL,
        "script_version": SCRIPT_VERSION,
        "bundle_id": f"r4-bundle-{moment.strftime('%Y%m%dT%H%M%SZ')}",
        "built_at": moment.isoformat(),
        "as_of": moment.isoformat(),
        "fixture_external_id": FIXTURE_EXTERNAL_ID,
        "search_discovery": {
            "reused_saved_responses": [dict(item) for item in discovery_notes],
            "new_paid_search_calls": 0,
            "note": (
                "새 검색 호출을 하지 않았다. 저장된 응답의 URL 후보만 재사용했다."
                " 후보 URL의 '발견'과 실제 본문 '수집'은 다른 단계이며, 실패한 후보도"
                " 남긴다."
            ),
        },
        "fulham_static_probe": [dict(item) for item in fulham_probes],
        "db_snapshot": {
            key: value
            for key, value in db_snapshot.items()
            if not key.startswith("_")
        },
        "db_facts": _db_fact_rows(db_snapshot),
        "sources": sources,
        "limits": {
            "max_candidate_fetches": MAX_CANDIDATE_FETCHES,
            "http_timeout_seconds": HTTP_TIMEOUT_SECONDS,
            "http_max_redirects": HTTP_MAX_REDIRECTS,
            "max_source_passages": MAX_SOURCE_PASSAGES,
            "max_passage_chars": MAX_PASSAGE_CHARS,
            "max_web_evidence_chars": MAX_WEB_EVIDENCE_CHARS,
            "web_evidence_chars_used": used_chars,
        },
        "browser_used": False,
        "browser_note": (
            "브라우저 실행·렌더 캡처를 쓰지 않았다. 렌더 HTML(fulham_rendered.html)은"
            " 이 묶음에서 제외했다."
        ),
    }


def _slug(value: Any) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "")).strip("-").lower()
    return (text[-48:] if len(text) > 48 else text) or "unknown"


def _collect_sources(moment: datetime) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """후보 URL을 실제 HTTP로 수집한다. 브라우저는 쓰지 않는다."""
    import httpx

    candidates, discovery_notes = _candidate_urls_from_saved()
    by_domain: dict[str, SavedCandidate] = {}
    for candidate in candidates:
        key = _candidate_key(candidate)
        by_domain.setdefault(key, candidate)
    ordered = list(by_domain.values())
    # 우선순위: 최신 응답의 모델 evidence(프리뷰 성격) → 스쿼드/통계 → 과거 경기 리포트 → 프로필
    priority = ("forebet", "manchestercitynews", "fulhamfc", "plstats", "theguardian", "wikipedia")
    ordered.sort(key=lambda item: next(
        (index for index, token in enumerate(priority) if token in item.url.lower()), 99
    ))
    selected = ordered[:MAX_CANDIDATE_FETCHES]
    replay_plan = {
        "wikipedia": "gredir3.html",
    }

    results: list[dict[str, Any]] = []
    fulham_probes: list[dict[str, Any]] = []
    _write_extractor_helper()
    with httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(HTTP_TIMEOUT_SECONDS),
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en;q=0.9"},
        max_redirects=HTTP_MAX_REDIRECTS,
    ) as client:
        for candidate in selected:
            lowered = candidate.url.lower()
            replay_name = next(
                (name for token, name in replay_plan.items() if token in lowered), None
            )
            if replay_name:
                results.append(_reuse_stored_capture(candidate, replay_name))
                continue
            record = _fetch_candidate(client, candidate)
            results.append(record)
            if "fulhamfc.com" in (record.get("final_url") or candidate.url) and record.get("body_chars", 0) < 400:
                fulham_probes = _fulham_static_probe(client, candidate.url)
    return results, discovery_notes, fulham_probes


def _candidate_key(candidate: SavedCandidate) -> str:
    haystack = candidate.url.lower()
    for token in ("forebet", "manchestercitynews", "fulhamfc", "plstats", "theguardian",
                  "wikipedia", "skysports", "thescore", "manchestereveningnews"):
        if token in haystack:
            return token
    return candidate.url


# --------------------------------------------------------------------------
# 프롬프트 · 프로토타입 검증 · 조립
# --------------------------------------------------------------------------


def _evidence_block(bundle: Mapping[str, Any]) -> str:
    lines: list[str] = []
    for source in bundle.get("sources") or ():
        passages = source.get("passages") or ()
        if not passages:
            continue
        lines.append(
            f"### 출처 {source['source_id']} ({source.get('source_type')})"
            f" — {source.get('title') or source.get('final_url')}"
        )
        lines.append(
            f"- 수집 방법: {source.get('method')} · 수집 시각: {source.get('capture_time')}"
            + (f" · 저장본 기록 시각: {source.get('stored_capture_at')}"
               if source.get("stored_capture_at") else "")
        )
        lines.append(f"- 성격: {source.get('source_type_note')}")
        for index, passage in enumerate(passages):
            lines.append(f"[{source['source_id']}#p{index}] {passage}")
        lines.append("")
    for probe in bundle.get("fulham_static_probe") or ():
        outcome = probe.get("failure") or f"HTTP {probe.get('http_status')}"
        lines.append(f"- 정적/API 시도 {probe.get('url')}: {outcome}")
    return "\n".join(lines).strip()


def _build_trial_prompt(bundle: Mapping[str, Any], *, today: datetime) -> tuple[str, dict[str, Any]]:
    """제품 R4 프롬프트를 그대로 쓰고, 웹 근거 블록만 덧붙인다(프로토타입)."""
    from app.preview.modules import form, players

    fixture = (bundle.get("db_snapshot") or {}).get("fixture") or {}
    db_facts = bundle.get("db_facts") or []
    team_names = {
        int(team["team_id"]): (team.get("name_ko") or team.get("english_name"))
        for team in (bundle.get("db_snapshot") or {}).get("teams") or ()
    }
    facts = form.FormFacts(
        fixture_id=int(fixture.get("fixture_id") or 0),
        league_id=int(fixture.get("league_id") or 0),
        season=int(fixture.get("season") or 0),
        home_team_id=int(fixture.get("home_team_id") or 0),
        away_team_id=int(fixture.get("away_team_id") or 0),
        kickoff_at=_parse_moment(fixture.get("kickoff_at")) or today,
        home_team=team_names.get(int(fixture.get("home_team_id") or 0))
        or str(fixture.get("home_team_name") or "home"),
        away_team=team_names.get(int(fixture.get("away_team_id") or 0))
        or str(fixture.get("away_team_name") or "away"),
        league=fixture.get("league_name"),
        facts=tuple(
            form.Fact(
                fact_id=str(row["fact_id"]),
                text=str(row["text"]),
                snapshot_id="bundle-db",
            )
            for row in db_facts
        ),
        collected_at=today,
    )
    roster = [
        {
            "player_id": row.get("player_id"),
            "display_name": row.get("name_ko") or row.get("english_name"),
            "english_name": row.get("english_name"),
            "team_display_name": team_names.get(int(row.get("team_id") or 0)),
        }
        for row in (bundle.get("db_snapshot") or {}).get("roster") or ()
    ]
    base = players.build_prompt(
        template=players.load_prompt(), facts=facts, roster=roster, today=today
    )
    evidence = _evidence_block(bundle)
    source_ids = [
        source["source_id"] for source in bundle.get("sources") or () if source.get("passages")
    ]
    addition = f"""

## 이번 요청의 추가 규칙 (정보 원문 묶음 시험)

이번 입력에는 **검색 엔진이 준 인용 metadata가 없다.** 대신 아래 "수집한 기사 원문"이
실제로 수집된 본문이다. `google_search` 도구도 쓰지 않는다.

- 웹 사실을 이유에 쓰려면 아래 출처 id(`src:...`)를 `evidence`에 적는다.
- DB 사실은 위 "인용 가능한 API 사실 id" 값을 그대로 적는다.
- 수집하지 못한 기사(원문 없음)를 읽은 것처럼 인용하지 않는다.
- 지난 경기 리포트는 **이번 경기 프리뷰가 아니다.** 그 기사의 내용을 이번 경기 전망으로
  바꿔 쓰지 말고, 확인된 배경 사실로만 쓴다.

### 인용 가능한 웹 출처 id

{(chr(10).join(f"- `{item}`" for item in source_ids)) or "- 수집된 웹 본문이 없습니다. DB 사실과 판단만 쓴다."}

### 수집한 기사 원문 (브라우저 없이 수집한 실제 본문)

{evidence or "수집된 본문이 없습니다."}
"""
    return base + addition, {"facts": facts, "roster": roster, "evidence_chars": len(evidence)}


def _parse_moment(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def validate_bundle_references(
    items: Sequence[Mapping[str, Any]], *, bundle: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    """프로토타입 검증기. 제품/승인 모듈이 아니다.

    검사하는 것(이 셋뿐이다):

    1. `evidence`의 참조가 **이번 입력 묶음에 실제로 있는** 출처 id·DB 사실 id인가.
    2. `selected_player` 표기가 제공된 자료(로스터·DB·수집 본문)에 실제로 있는가.
    3. 이유 문장의 숫자가 제공된 자료 어딘가에 있는가(없으면 지어낸 사실로 본다).

    검사하지 않는 것: 문장이 출처를 실제로 뒷받침하는지, 주체·시즌·대회 일치, 기사와
    DB의 충돌. 그래서 통과는 사실 진위 검증이 아니다.
    """
    # 출처 id와 **실제로 전달한 구간 id**(`src:...` + `#p<번호>`)를 모두 인정한다.
    # 프롬프트가 구간 단위로 인용하라고 표기했으므로 구간 참조를 거부하면 안 된다
    # (첫 실행에서 그 실수로 세 항목이 전부 탈락했다).
    allowed_refs: set[str] = {str(row["fact_id"]) for row in bundle.get("db_facts") or ()}
    for source in bundle.get("sources") or ():
        if not source.get("passages"):
            continue
        source_id = str(source["source_id"])
        allowed_refs.add(source_id)
        for index in range(len(source["passages"])):
            allowed_refs.add(f"{source_id}#p{index}")
    corpus = " ".join(
        [str(row.get("text") or "") for row in bundle.get("db_facts") or ()]
        + [str(source.get("body") or "") for source in bundle.get("sources") or ()]
        + [
            f"{row.get('english_name') or ''} {row.get('name_ko') or ''}"
            for row in (bundle.get("db_snapshot") or {}).get("roster") or ()
        ]
    ).casefold()

    accepted: list[dict[str, Any]] = []
    notes: list[str] = []
    rejected: list[dict[str, Any]] = []
    for item in items:
        player = str(item.get("selected_player") or "").strip()
        reason = str(item.get("selection_reason") or "").strip()
        refs = [str(ref) for ref in item.get("evidence") or ()]
        unknown = [ref for ref in refs if ref not in allowed_refs]
        if unknown:
            rejected.append(
                {"selected_player": player, "reason": "reference_not_in_bundle",
                 "detail": ", ".join(unknown)}
            )
            notes.append(f"{player}: 입력 묶음에 없는 근거 참조 {unknown}")
            continue
        if player and player.casefold() not in corpus:
            # 모델이 적은 표기가 자료에 없으면 이름을 만들어낸 것으로 본다.
            notes.append(f"{player}: 제공 자료에서 표기를 찾지 못했습니다(이름 미확인).")
        missing_numbers = [
            number
            for number in re.findall(r"\d+(?:\.\d+)?", reason)
            if number not in corpus
        ]
        if missing_numbers:
            rejected.append(
                {"selected_player": player, "reason": "number_not_in_supplied_inputs",
                 "detail": ", ".join(sorted(set(missing_numbers)))}
            )
            notes.append(f"{player}: 입력에 없는 수치 {sorted(set(missing_numbers))} — 항목 제외")
            continue
        accepted.append(dict(item))
    return accepted, notes, rejected


def _compose_from_payload(payload: Mapping[str, Any]) -> Any:
    from app.preview.modules import players

    return players.compose_players_body(payload)


# --------------------------------------------------------------------------
# 노드 구현 (기존 runner에 주입)
# --------------------------------------------------------------------------


def _research_node(
    *,
    bundle: Mapping[str, Any],
    transport: Any,
    model_name: str,
    state_box: dict[str, Any],
):
    """R4 조사 노드(프로토타입). 전송은 한 번, 실패해도 묶음은 이미 저장된다."""
    from app.preview import artifacts as artifact_store
    from app.preview import provider
    from app.preview import runner as runner_module
    from app.preview.contracts import QualityStatus, RunMode
    from app.preview.modules import players

    def run(ctx: runner_module.SectionNodeContext, state) -> runner_module.NodeOutcome:
        from app.preview.modules import form

        moment = datetime.now(timezone.utc)
        prompt_text, prompt_meta = _build_trial_prompt(bundle, today=moment)
        state_box["prompt_chars"] = len(prompt_text)
        state_box["prompt_sha256"] = _sha256_text(prompt_text)

        # 1) 묶음을 먼저 저장한다. 뒤 단계가 깨져도 유료 응답·입력이 남는다.
        bundle_artifact = artifact_store.save_artifact(
            ctx.session,
            run_id=ctx.context.run_id,
            kind=artifact_store.ArtifactKind.NORMALIZED_TRANSFORM,
            content={**dict(bundle), "prompt_sha256": state_box["prompt_sha256"]},
            actor_id=ctx.actor_id,
            now=moment,
        )
        state_box["bundle_artifact_id"] = str(bundle_artifact.id)
        ctx.session.flush()

        # 2) 정확히 한 번 전송한다(재시도·대체 모델·검색 도구 없음).
        send_started = time.perf_counter()
        result = provider.request_model(
            logical_call_id=players.LOGICAL_CALL_ID + "/bundle-trial",
            contents=[{"role": "user", "parts": [{"text": prompt_text}]}],
            context=ctx.context,
            transport=transport,
            budget=ctx.budget,
            session=ctx.session,
            module_id=players.PLAYERS_MODULE_ID,
            operation="research_players_bundle_trial",
            prompt_version=f"{players.PROMPT_VERSION}+{SCRIPT_VERSION}",
            generation_config={
                "temperature": 0.2,
                "response_mime_type": "application/json",
            },
            model_name=model_name,
            module_execution_id=ctx.context.module_execution_id,
            actor_id=ctx.actor_id,
            now=lambda: moment,
        )
        send_ms = int((time.perf_counter() - send_started) * 1000)
        state_box["send_elapsed_ms"] = send_ms
        state_box["attempts"] = [attempt.to_dict() for attempt in result.attempts]
        state_box["external_calls"] = provider.sent_attempt_count(result, transport.mode)
        state_box["stopped_reason"] = result.stopped_reason
        state_box["missing_configuration"] = result.missing_configuration

        # 3) 유료 응답을 **즉시 확정 저장**한다. 이 실행의 run·시도·원문·묶음은 이
        # 실행이 소유한 preview_dev 행이다. 뒤 후처리가 깨져 예외가 나도 이미 받은
        # 응답이 함께 롤백되지 않게 여기서 커밋한다(직전 시도에서 실제로 겪은 손실).
        raw = _read_artifact_json(ctx.session, result.response.raw_artifact_id)
        state_box["raw_artifact_id"] = (
            str(result.response.raw_artifact_id) if result.response.raw_artifact_id else None
        )
        state_box["raw_response_saved"] = raw is not None
        _persist_paid_response(
            session=ctx.session,
            run_id=ctx.context.run_id,
            state_box=state_box,
            result=result,
            moment=moment,
        )
        grounding = form.parse_grounding(raw)
        state_box["grounding_keys"] = sorted(grounding.keys())
        state_box["grounding_source_count"] = len(grounding.get("sources") or ())

        try:
            return _postprocess(
                state_box=state_box,
                result=result,
                bundle=bundle,
                grounding=grounding,
                runner_module=runner_module,
            )
        except Exception as exc:  # noqa: BLE001 - 유료 응답을 잃지 않는다
            # 후처리 실패는 본문 없음으로 기록하고, 이미 저장한 원문·묶음은 그대로 둔다.
            state_box["postprocess_error"] = f"{type(exc).__name__}: {exc}"[:600]
            return runner_module.NodeOutcome(
                payload={
                    "module_id": "R4",
                    "prototype": PROTOTYPE_LABEL,
                    "raw_model_text": (result.text or "")[:8000],
                    "bundle_artifact_id": state_box.get("bundle_artifact_id"),
                },
                quality=QualityStatus.INSUFFICIENT,
                diagnostics=(
                    "후처리에서 예외가 발생했습니다. 원문 응답과 정보 묶음은 저장돼 있습니다:"
                    f" {state_box['postprocess_error']}",
                ),
                unavailable_reason=(
                    "후처리 실패로 이번 시험의 본문을 만들지 않았습니다. 원문 응답은"
                    " 보존했습니다."
                ),
                external_calls=state_box["external_calls"],
            )


    return runner_module.NodeImplementation(
        module_id="R4",
        implementation_version=f"{players.IMPLEMENTATION_VERSION}+bundle-trial",
        prompt_version=f"{players.PROMPT_VERSION}+{SCRIPT_VERSION}",
        mode=getattr(transport, "mode", RunMode.LIVE),
        run=run,
    )


def _read_artifact_json(session: Any, artifact_id: uuid.UUID | None) -> Any:
    if artifact_id is None:
        return None
    from app.preview.models import PreviewArtifact

    row = session.get(PreviewArtifact, artifact_id)
    if row is None or row.body is None:
        return None
    try:
        return json.loads(row.body)
    except ValueError:
        return None


def _persist_paid_response(
    *,
    session: Any,
    run_id: uuid.UUID,
    state_box: dict[str, Any],
    result: Any,
    moment: datetime,
) -> None:
    """유료 응답을 후처리 **전에** 확정 저장한다.

    전송 실패·빈 응답이면 여기서 아무것도 하지 않는다(원 시도 행이 이미 있다).
    성공한 응답은 이 실행이 소유한 preview_dev 행으로 즉시 커밋한다. 그래야 뒤
    후처리가 예외를 내도 이미 지불한 응답이 함께 롤백되지 않는다.
    """
    from app.preview import artifacts as artifact_store
    from app.preview.models import PreviewArtifact

    if not result.ok:
        return
    # 가림 저장된 원문 텍스트를 별도 아티팩트로 한 번 더 고정한다(응답 본문이 곧 증거).
    if result.text:
        saved = artifact_store.save_artifact(
            session,
            run_id=run_id,
            kind=artifact_store.ArtifactKind.RAW_RESPONSE,
            content={
                "prototype": PROTOTYPE_LABEL,
                "note": (
                    "이번 시험의 실제 모델 응답 텍스트(가림 저장). 전송 1회의 결과이며"
                    " 재전송하지 않는다."
                ),
                "attempts": [attempt.to_dict() for attempt in result.attempts],
                "model": getattr(result.spec, "model", None),
                "usage": (
                    result.response.usage.to_dict()
                    if result.response.usage is not None
                    else None
                ),
                "text": result.text,
            },
            actor_id=0,
            now=moment,
        )
        state_box["paid_text_artifact_id"] = str(saved.id)
    state_box["persisted_before_postprocess"] = True
    session.commit()
    # 커밋 뒤에도 이 세션에서 원문을 읽을 수 있게 참조를 남긴다.
    if state_box.get("raw_artifact_id"):
        row = session.get(PreviewArtifact, uuid.UUID(state_box["raw_artifact_id"]))
        state_box["raw_artifact_after_commit"] = row is not None


def _postprocess(
    *,
    state_box: dict[str, Any],
    result: Any,
    bundle: Mapping[str, Any],
    grounding: Mapping[str, Any],
    runner_module: Any,
) -> Any:
    """전송 성공 뒤의 파싱·검증·이름 해석·조립. 제품 함수를 그대로 재사용한다."""
    from app.preview import store
    from app.preview.contracts import QualityStatus as QS

    from app.preview.modules import players

    if not result.text:
        coverage_note = "모델이 빈 텍스트를 반환했습니다."
        state_box["empty_text"] = True
        return runner_module.NodeOutcome(
            payload={"module_id": "R4", "prototype": PROTOTYPE_LABEL},
            quality=QS.INSUFFICIENT,
            diagnostics=(coverage_note,),
            unavailable_reason="모델 응답이 비어 있어 본문을 만들지 않았습니다.",
            external_calls=state_box["external_calls"],
        )

    state_box["raw_text_chars"] = len(result.text)
    usage = result.response.usage
    state_box["usage"] = usage.to_dict() if usage is not None else None

    payload = players.parse_model_output(result.text)
    if payload is None:
        state_box["parse_failed"] = True
        return runner_module.NodeOutcome(
            payload={
                "module_id": "R4",
                "prototype": PROTOTYPE_LABEL,
                "raw_model_text": result.text[:8000],
            },
            quality=QS.INSUFFICIENT,
            diagnostics=("R4 응답을 JSON으로 해석하지 못했습니다.",),
            unavailable_reason="모델 응답을 JSON으로 해석하지 못했습니다.",
            external_calls=state_box["external_calls"],
        )

    raw_items = players.model_players(payload)
    accepted, notes, rejected = validate_bundle_references(raw_items, bundle=bundle)
    state_box["model_item_count"] = len(raw_items)
    state_box["accepted_item_count"] = len(accepted)
    state_box["rejected_items"] = rejected
    state_box["validation_notes"] = notes

    # 이름 해석: 이 실행에서 읽은 DB 이름 인덱스를 그대로 쓴다(새 연결·권한 없음).
    names = state_box.get("_names")
    labels = list(payload.get("korean_labels") or ())
    if names is not None and labels:
        try:
            state_box["korean_labels_applied"] = names.register_model_labels(labels)
        except Exception as exc:  # noqa: BLE001 - 표기 반영 실패로 응답을 잃지 않는다
            state_box["korean_labels_error"] = f"{type(exc).__name__}: {exc}"[:300]
    rows, unmapped = players.resolve_selection_names(
        accepted,
        resolver=names,
        scope_team_ids=[13, 4],
        id_space="internal",
        id_is_hint=True,
    )
    state_box["unmapped"] = [dict(item) for item in unmapped]

    reader_sources = []
    for source in bundle.get("sources") or ():
        if not source.get("passages"):
            continue
        reader_sources.append(
            {
                "label": str(source.get("title") or source.get("final_url")),
                "url": str(source.get("final_url") or source.get("requested_url")),
                "kind": "web_article",
                "note": (
                    f"{source.get('source_type')} · 브라우저 없이 수집한 본문"
                    f"({source.get('method')})"
                ),
            }
        )
    db_sources = [
        {
            "label": "저장된 경기·순위 자료",
            "url": None,
            "kind": "api",
            "note": "읽기 전용 DB(public.fixture/standings/injury)",
        }
    ]

    module_payload = {
        "module_id": "R4",
        "prototype": PROTOTYPE_LABEL,
        "output_contract_version": players.contract.OUTPUT_CONTRACT_VERSION,
        "implementation_version": f"{players.IMPLEMENTATION_VERSION}+bundle-trial",
        "prompt_version": f"{players.PROMPT_VERSION}+{SCRIPT_VERSION}",
        "mode": "live",
        "display_labels": dict(players.contract.DISPLAY_LABELS),
        "players": rows,
        "unmapped": state_box["unmapped"],
        "mapping": {
            "resolved": sum(1 for row in rows if row.get("mapping_status") == "resolved"),
            "total": len(rows),
        },
        "claims": [],
        "coverage": [],
        "diagnostics": list(notes),
        "uncertainties": list(payload.get("uncertainties") or ()),
        "korean_labels": labels,
        "search_note": payload.get("search_note"),
        "raw_grounding": {
            "note": "이번 호출에는 google_search 도구를 쓰지 않았다.",
            "provider_metadata_keys": sorted((grounding or {}).keys()),
        },
        "raw_model_text": result.text[:8000],
        "reader_sources": reader_sources + db_sources,
        "selection_rule_note": players.contract.SELECTION_RULE_NOTE,
        "attempt_count": len(result.attempts),
        "external_calls": state_box["external_calls"],
        "bundle_artifact_id": state_box.get("bundle_artifact_id"),
        "paid_text_artifact_id": state_box.get("paid_text_artifact_id"),
    }
    state_box["payload"] = module_payload
    composed = _compose_from_payload(module_payload)
    state_box["composed"] = composed.to_dict()
    quality = QS.READY if composed.body.strip() else QS.INSUFFICIENT
    return runner_module.NodeOutcome(
        payload=module_payload,
        sources=tuple(reader_sources) + tuple(db_sources),
        quality=quality,
        diagnostics=tuple(notes) + tuple(composed.diagnostics),
        unavailable_reason=(
            None
            if composed.body.strip()
            else "검증을 통과한 선정 항목이 없어 이번 시험의 본문을 만들지 않았습니다."
        ),
        external_calls=state_box["external_calls"],
    )


# --------------------------------------------------------------------------
# 오프라인 preflight
# --------------------------------------------------------------------------


SYNTHETIC_RESPONSE = {
    "players": [
        {
            "selected_player": "Erling Haaland",
            "team": "Manchester City",
            "player_ref": None,
            "selection_reason": "리그 9골로 팀 득점을 이끄는 공격수입니다(시험용 합성 응답).",
            "evidence": [],
            "superlative_basis": None,
        }
    ],
    "korean_labels": [
        {"original": "Erling Haaland", "korean": "엘링 홀란", "kind": "player"}
    ],
    "search_note": "preflight 합성 응답",
    "uncertainties": [],
}


def run_preflight(*, bundle: Mapping[str, Any]) -> dict[str, Any]:
    """전송 전에 파서·검증·이름·조립 인터페이스가 깨지지 않는지 확인한다(호출 0회)."""
    from app.preview.modules import players

    started = time.perf_counter()
    prompt_text, meta = _build_trial_prompt(bundle, today=datetime.now(timezone.utc))
    parsed = players.parse_model_output(json.dumps(SYNTHETIC_RESPONSE, ensure_ascii=False))
    items = players.model_players(parsed)
    accepted, notes, rejected = validate_bundle_references(items, bundle=bundle)
    payload = {
        "module_id": "R4",
        "output_contract_version": players.contract.OUTPUT_CONTRACT_VERSION,
        "players": accepted,
        "reader_sources": [
            {"label": "preflight", "url": "https://example.invalid", "kind": "web_article"}
        ],
    }
    composed = _compose_from_payload(payload)
    rehearsal = _rehearse_postprocess(bundle=bundle)
    return {
        "prompt_chars": len(prompt_text),
        "prompt_sha256": _sha256_text(prompt_text),
        "parsed_ok": parsed is not None,
        "model_items": len(items),
        "accepted_items": len(accepted),
        "rejected_items": rejected,
        "notes": notes,
        "compose_body_chars": len(composed.body or ""),
        "compose_body_lines": len((composed.body or "").splitlines()),
        "compose_quality": composed.quality.value,
        # 전송 없이 **전송 뒤 경로 전체**를 한 번 돌려 본 결과(스키마·이름·조립·커밋).
        "full_path_rehearsal": rehearsal,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "note": (
            "합성 응답으로 파서·검증·이름 해석·조립과 후처리 경로를 확인했다. 실제"
            " 모델 호출은 0회이며, 사실 진위나 모델 품질을 확인한 것이 아니다."
        ),
        "evidence_chars": meta["evidence_chars"],
        "external_calls": 0,
    }


def _rehearse_postprocess(*, bundle: Mapping[str, Any]) -> dict[str, Any]:
    """전송 없이 `_persist_paid_response` + `_postprocess` 경로를 그대로 실행한다.

    직전 실행에서 후처리 한 줄이 예외를 내 유료 응답이 롤백됐다. 같은 실패를 전송
    전에 잡기 위한 리허설이다. `RecordedTransport`는 네트워크를 열지 않고 기록에
    `mode=replay`로 남으므로 실제 전송으로 세지 않는다.
    """
    import uuid as _uuid

    from app.preview import provider
    from app.preview.contracts import (
        ExecutionContext,
        Environment,
        OperationKind,
        RunMode as _RunMode,
    )
    from app.preview.retry import RunBudget, plan_limits

    started = time.perf_counter()
    result_box: dict[str, Any] = {}
    try:
        synthetic = {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [
                            {"text": json.dumps(SYNTHETIC_RESPONSE, ensure_ascii=False)}
                        ],
                    },
                    "finish_reason": "STOP",
                }
            ],
            "usage_metadata": {"prompt_token_count": 1, "candidates_token_count": 1},
        }
        transport = provider.RecordedTransport(
            script=[
                provider.TransportResult(
                    http_status=200,
                    raw_request={"preflight": True},
                    raw_response=synthetic,
                    usage={"input_tokens": 1, "output_tokens": 1},
                )
            ],
            provider="preflight-synthetic",
            mode=_RunMode.REPLAY,
        )
        limits = plan_limits(attempts_per_call=1, model_requests=1, normal_model_calls=1)
        budget = RunBudget.for_run(limits)
        context = ExecutionContext(
            run_id=_uuid.uuid4(),
            operation_kind=OperationKind.MODULE,
            environment=Environment.DEV,
            mode=_RunMode.REPLAY,
            actor_id=0,
            config_version="preflight",
        )
        result = provider.request_model(
            logical_call_id="preflight/synthetic",
            contents=[{"role": "user", "parts": [{"text": "preflight"}]}],
            context=context,
            transport=transport,
            budget=budget,
            session=None,
            module_id="R4",
            operation="preflight",
            generation_config={"response_mime_type": "application/json"},
            model_name="synthetic",
        )
        result_box["ok"] = result.ok
        result_box["sent_attempts"] = provider.sent_attempt_count(result, transport.mode)
        payload = result.text and json.loads(result.text)
        items = payload.get("players") if payload else []
        accepted, notes, rejected = validate_bundle_references(items or [], bundle=bundle)
        composed = _compose_from_payload(
            {
                "module_id": "R4",
                "output_contract_version": "mp05p-r4-players-output-2",
                "players": accepted,
            }
        )
        result_box["accepted"] = len(accepted)
        result_box["rejected"] = len(rejected)
        result_box["body_chars"] = len(composed.body or "")
        result_box["body_lines"] = (composed.body or "").splitlines()
        result_box["usage_readable"] = (
            result.response.usage.to_dict() if result.response.usage else None
        )
        result_box["ok_path"] = True
    except Exception as exc:  # noqa: BLE001 - 리허설 실패를 숨기지 않는다
        result_box["ok_path"] = False
        result_box["error"] = f"{type(exc).__name__}: {exc}"[:500]
    result_box["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    result_box["note"] = (
        "합성 기록 응답으로 전송 뒤 경로(응답 읽기·usage·검증·조립)를 실행했다."
        " 실제 모델 전송 0회."
    )
    return result_box


# --------------------------------------------------------------------------
# 실행
# --------------------------------------------------------------------------


def _open_names() -> Any:
    """이 실행에서 읽은 DB 이름 인덱스로 해석기를 만든다. 실패하면 `None`(원문 유지)."""
    try:
        from app.preview.localized_names import (
            DbNameLookup,
            DisplayNames,
            load_name_index,
        )

        dsn = os.environ.get("PREVIEW_NAMES_DATABASE_URL") or ""
        if not dsn:
            return None
        lookup = DbNameLookup.from_url(dsn)
        try:
            index = load_name_index(lookup, team_ids=[13, 4], include_rosters=True)
        finally:
            lookup.close()
        return DisplayNames(index)
    except Exception:  # noqa: BLE001 - 이름 해석 실패는 원문 표기 유지로 흡수한다
        return None


def run_trial(*, bundle: Mapping[str, Any], model_name: str, project: str, location: str,
              credentials_json: str, limits: Any) -> dict[str, Any]:
    """기존 runner를 주입 노드로 실행한다. 전송은 한 번이다."""
    from app.preview.db import get_session_factory
    from app.preview import runner, sections, store
    from app.preview.contracts import Environment, RunMode
    from app.preview.provider import GoogleGenAIHttpTransport
    from app.preview.sources.fixtures import StoredFixtureReader

    transport = GoogleGenAIHttpTransport(
        project=project,
        location=location,
        model=model_name,
        credentials_json=credentials_json,
        mode=RunMode.LIVE,
    )
    fixture = (bundle.get("db_snapshot") or {}).get("fixture") or {}
    fixture_payload = {
        "fixture_id": int(fixture["fixture_id"]),
        "league_id": int(fixture["league_id"]),
        "season": int(fixture["season"]),
        "home_team_id": int(fixture["home_team_id"]),
        "away_team_id": int(fixture["away_team_id"]),
        "kickoff_at": fixture["kickoff_at"],
    }
    reader = StoredFixtureReader.from_url(os.environ["PREVIEW_FIXTURES_DATABASE_URL"])
    state_box: dict[str, Any] = {"_names": _open_names()}
    implementations = runner.WorkflowImplementations(
        prepare_data=sections._prepare_implementation(  # noqa: SLF001 - 제품 D0 노드 재사용
            transport=transport, reader=reader, now=None
        ),
        research=(
            _research_node(
                bundle=bundle, transport=transport, model_name=model_name, state_box=state_box
            ),
        ),
        compose_body=_compose_node(),
    )
    factory = get_session_factory()
    started = datetime.now(timezone.utc)
    with factory() as session:
        result = runner.run_section_workflow(
            session,
            workflow_id="section_players",
            implementations=implementations,
            actor_id=0,
            environment=Environment.DEV,
            fixture=fixture_payload,
            fixture_label=str(fixture.get("label")),
            transport=transport,
            label=f"R4 정보 원문 묶음 시험 ({PROTOTYPE_LABEL})",
            limits=limits,
            now=started,
        )
        session.commit()
        detail = store.get_run_detail(session, result.run_id)
        attempts = list(detail.attempts)
        summary = {
            "run_id": str(result.run_id),
            "workflow_id": result.workflow_id,
            "workflow_version": result.workflow_version,
            "mode": result.mode.value,
            "status": result.status.value,
            "quality": result.quality.value,
            "external_calls": result.external_calls,
            "attempt_count": len(attempts),
            "attempts": attempts,
            "section_result_id": str(result.section_result_id) if result.section_result_id else None,
            "section_result_version": result.section_result_version,
            "body": result.body,
            "sources": [dict(item) for item in result.sources],
            "diagnostics": list(result.diagnostics),
            "unavailable_reason": result.unavailable_reason,
            "budget": dict(result.budget),
            "module_execution_ids": [str(item) for item in result.module_execution_ids],
            "result_ids": [str(item) for item in result.result_ids],
            "step_log": [dict(item) for item in result.step_log],
            "started_at": started.isoformat(),
        }
    reader.close()

    # 정확한 요청에 실제 묶음·DB 사실이 들어갔는지 저장된 요청 아티팩트로 확인한다.
    request_check = _verify_request_artifact(summary, bundle=bundle)
    summary["request_check"] = request_check
    # 메모리 객체(이름 해석기)는 기록에 넣지 않는다.
    summary["node_state"] = {
        key: value for key, value in state_box.items() if not key.startswith("_")
    }
    return summary


def _compose_node():
    """제품 조립 노드를 그대로 쓴다(두 표시 필드 분리·진단 미노출)."""
    from app.preview.modules import players

    return players.players_compose_node(mode=None)


def reprocess_saved_run(*, run_id: str, bundle: Mapping[str, Any]) -> dict[str, Any]:
    """이미 저장된 **지불 완료** 응답으로 후처리만 다시 실행한다. 새 전송은 없다.

    첫 실행에서 검증기 결함으로 세 항목이 탈락했다. 같은 응답을 다시 사지 않고
    고친 검증기·이름 해석·조립을 적용해 결과를 확인하기 위한 경로다. 원 시도의
    전송 횟수·원문 아티팩트는 그대로 두고, 후처리 산출만 새로 남긴다.
    """
    import uuid as _uuid

    from app.preview.db import get_session_factory
    from app.preview import store
    from app.preview.contracts import QualityStatus
    from app.preview.models import PreviewArtifact

    started = datetime.now(timezone.utc)
    run_uuid = _uuid.UUID(str(run_id))
    node_state: dict[str, Any] = {}
    factory = get_session_factory()
    with factory() as session:
        detail = store.get_run_detail(session, run_uuid)
        attempts = list(detail.attempts)
        raw_id = None
        for attempt in attempts:
            artifacts = _artifacts_of(session, attempt.get("response_artifact_id"))
            if artifacts and artifacts.get("body"):
                raw_id = attempt.get("response_artifact_id")
                break
        if raw_id is None:
            raise SystemExit("저장된 응답 아티팩트를 찾지 못했습니다(새로 보내지 않습니다).")
        body = session.get(PreviewArtifact, _uuid.UUID(str(raw_id))).body or "{}"
        raw = json.loads(body)
        text = _text_from_raw(raw)
        if not text:
            raise SystemExit("저장된 응답에 모델 텍스트가 없습니다.")
        from app.preview.modules import form

        grounding = form.parse_grounding(raw)
        from app.preview.provider import ExecuteRequestResult
        from app.preview.contracts import AttemptOutcome, ProviderResponse

        first = attempts[0]
        synthetic_result = ExecuteRequestResult(
            spec=_SpecProxy(model=first.get("model")),
            response=ProviderResponse(
                attempt_id=_uuid.UUID(str(first["attempt_id"])),
                outcome=AttemptOutcome.OK,
                http_status=first.get("http_status"),
                raw_artifact_id=_uuid.UUID(str(raw_id)),
                usage=None,
            ),
            attempts=(),
            budget={},
            text=text,
        )
        node_state["_names"] = _open_names()
        node_state["external_calls"] = 0
        node_state["bundle_artifact_id"] = _find_bundle_artifact(session, run_uuid)
        node_state["raw_artifact_id"] = str(raw_id)
        node_state["reprocessed_from_run"] = str(run_uuid)
        outcome = _postprocess(
            state_box=node_state,
            result=synthetic_result,
            bundle=bundle,
            grounding=grounding,
            runner_module=_runner_module(),
        )
        composed = node_state.get("composed") or {}
        summary = {
            "run_id": str(run_uuid),
            "reprocessed": True,
            "new_send": False,
            "body": composed.get("body") or "",
            "title": composed.get("title"),
            "sources": [dict(item) for item in outcome.sources],
            "diagnostics": list(outcome.diagnostics),
            "unavailable_reason": outcome.unavailable_reason,
            "quality": (outcome.quality or QualityStatus.PENDING).value,
            "external_calls": 0,
            "attempt_count": len(attempts),
            "attempts": attempts,
            "node_state": {k: v for k, v in node_state.items() if not k.startswith("_")},
            # 원 실행이 실제로 보낸 요청을 그대로 검사한다(재처리는 새 요청을 만들지 않는다).
            "request_check": {
                **_verify_saved_request(attempts, bundle=bundle),
                "new_request_in_reprocess": False,
            },
            "duration_ms": {"reprocess_started_at": started.isoformat()},
        }
    summary["node_state"]["payload_players"] = (
        (node_state.get("payload") or {}).get("players")
    )
    return summary


def _verify_saved_request(
    attempts: Sequence[Mapping[str, Any]], *, bundle: Mapping[str, Any]
) -> dict[str, Any]:
    """원 실행의 첫 시도 요청 아티팩트에서 묶음·DB 사실이 전송됐는지 확인한다."""
    if not attempts:
        return {"checked": False, "reason": "시도 기록이 없습니다."}
    artifact_id = attempts[0].get("request_artifact_id")
    if not artifact_id:
        return {"checked": False, "reason": "요청 아티팩트 ID가 없습니다."}
    text = _load_artifact_body(artifact_id) or ""
    source_ids = [
        source["source_id"] for source in bundle.get("sources") or () if source.get("passages")
    ]
    db_fact_ids = [str(row["fact_id"]) for row in bundle.get("db_facts") or ()]
    fixture_id = str((bundle.get("db_snapshot") or {}).get("fixture", {}).get("fixture_id"))
    return {
        "checked": bool(text),
        "request_artifact_id": str(artifact_id),
        "request_chars": len(text),
        "source_ids_in_request": {sid: (sid in text) for sid in source_ids},
        "db_fact_ids_in_request": {fid: (fid in text) for fid in db_fact_ids[:8]},
        "fixture_id_in_request": fixture_id in text if fixture_id else None,
        "google_search_tool_absent": '"google_search"' not in text,
        "note": "요청 아티팩트 본문에서 문자열 존재를 확인한 것이다(실제 전송 본문).",
    }


def _runner_module() -> Any:
    from app.preview import runner

    return runner


def _SpecProxy(**kwargs: Any) -> Any:  # noqa: N802 - 재처리용 최소 대역
    class _Proxy:
        def __init__(self, **values: Any) -> None:
            self.__dict__.update(values)

    return _Proxy(**kwargs)


def _artifacts_of(session: Any, artifact_id: Any) -> dict[str, Any] | None:
    if not artifact_id:
        return None
    from app.preview.models import PreviewArtifact

    row = session.get(PreviewArtifact, uuid.UUID(str(artifact_id)))
    if row is None:
        return None
    return {"artifact_id": str(row.id), "kind": row.kind, "body": row.body}


def _find_bundle_artifact(session: Any, run_id: uuid.UUID) -> str | None:
    from sqlalchemy import select

    from app.preview.models import PreviewArtifact

    row = session.execute(
        select(PreviewArtifact)
        .where(PreviewArtifact.run_id == run_id)
        .where(PreviewArtifact.kind == "normalized_transform")
    ).scalars().first()
    return str(row.id) if row else None


def _text_from_raw(raw: Any) -> str | None:
    """저장된 원문(제공자 응답)에서 모델 텍스트만 꺼낸다."""
    from app.preview.provider import extract_text

    return extract_text(raw)


def _verify_request_artifact(summary: Mapping[str, Any], *, bundle: Mapping[str, Any]) -> dict[str, Any]:
    """첫 시도의 요청 아티팩트에서 출처 id·DB 사실이 실제로 전송됐는지 확인한다."""
    source_ids = [
        source["source_id"]
        for source in bundle.get("sources") or ()
        if source.get("passages")
    ]
    db_fact_ids = [str(row["fact_id"]) for row in bundle.get("db_facts") or ()]
    fixture_id = str((bundle.get("db_snapshot") or {}).get("fixture", {}).get("fixture_id"))
    attempts = summary.get("attempts") or []
    if not attempts:
        return {"checked": False, "reason": "시도 기록이 없습니다."}
    first = attempts[0]
    request_artifact_id = first.get("request_artifact_id")
    if not request_artifact_id:
        return {"checked": False, "reason": "요청 아티팩트 ID가 없습니다."}
    body = _load_artifact_body(request_artifact_id)
    text = body or ""
    return {
        "checked": bool(text),
        "request_artifact_id": str(request_artifact_id),
        "request_chars": len(text),
        "source_ids_in_request": {
            source_id: (source_id in text) for source_id in source_ids
        },
        "db_fact_ids_in_request": {
            fact_id: (fact_id in text) for fact_id in db_fact_ids[:8]
        },
        "fixture_id_in_request": fixture_id in text if fixture_id else None,
        "google_search_tool_absent": '"google_search"' not in text,
        "note": "요청 아티팩트 본문에서 문자열 존재를 확인한 것이다(실제 전송 본문).",
    }


def _load_artifact_body(artifact_id: Any) -> str | None:
    from app.preview.db import get_session_factory
    from app.preview.models import PreviewArtifact

    factory = get_session_factory()
    with factory() as session:
        row = session.get(PreviewArtifact, uuid.UUID(str(artifact_id)))
        return row.body if row is not None else None


# --------------------------------------------------------------------------
# 산출물
# --------------------------------------------------------------------------


def _evidence_view(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """저장소에 남길 축약본. 본문 전문 대신 해시·짧은 발췌만 둔다."""
    return {
        "prototype": PROTOTYPE_LABEL,
        "bundle_id": bundle.get("bundle_id"),
        "script_version": bundle.get("script_version"),
        "built_at": bundle.get("built_at"),
        "as_of": bundle.get("as_of"),
        "fixture_external_id": bundle.get("fixture_external_id"),
        "browser_used": False,
        "browser_note": bundle.get("browser_note"),
        "search_discovery": bundle.get("search_discovery"),
        "fulham_static_probe": bundle.get("fulham_static_probe"),
        "limits": bundle.get("limits"),
        "db_snapshot": bundle.get("db_snapshot"),
        "db_facts": bundle.get("db_facts"),
        "sources": [
            {
                key: value
                for key, value in source.items()
                if key not in {"body"}
            }
            | {
                "excerpts": [
                    passage[:EXCERPT_CHARS_IN_EVIDENCE] for passage in source.get("passages") or ()
                ]
            }
            for source in bundle.get("sources") or ()
        ],
        "fulltext_note": (
            "기사 본문 전문은 저장소에 넣지 않았다. /tmp 스크래치와 preview_dev"
            " 아티팩트에만 있으며, 여기에는 해시와 짧은 발췌만 있다."
        ),
    }


def _write_markdown(path: Path, *, bundle: Mapping[str, Any], summary: Mapping[str, Any] | None) -> None:
    lines = [
        "# R4 정보 원문 묶음 (읽기용)",
        "",
        f"- 성격: `{PROTOTYPE_LABEL}` · 스크립트 `{SCRIPT_VERSION}`",
        f"- 묶음 ID: `{bundle.get('bundle_id')}` · 기준 시각(as_of): {bundle.get('as_of')}",
        f"- 경기: 외부 ID {bundle.get('fixture_external_id')} · 브라우저 사용: 아니오",
        "",
        "## DB 스냅샷 (읽기 전용)",
        "",
    ]
    fixture = (bundle.get("db_snapshot") or {}).get("fixture") or {}
    lines.append(
        f"- {fixture.get('label')} · 리그 {fixture.get('league_name')} {fixture.get('season')}"
        f" · 킥오프 {fixture.get('kickoff_at')} · 상태 {fixture.get('status_short')}"
    )
    for team in (bundle.get("db_snapshot") or {}).get("teams") or ():
        lines.append(
            f"- 팀 {team.get('team_id')} {team.get('english_name')} → 한국어 표기"
            f" `{team.get('name_ko')}` (출처: {team.get('source', {}).get('table')})"
        )
    lines += ["", "### 구조화 사실 (모델 입력)", ""]
    for row in bundle.get("db_facts") or ():
        lines.append(f"- `{row['fact_id']}` {row['text']}")
    lines += ["", "## 수집한 웹 출처", ""]
    for source in bundle.get("sources") or ():
        status = "본문 확보" if source.get("passages") else f"실패 — {source.get('failure')}"
        lines.append(
            f"### `{source.get('source_id')}` ({source.get('source_type')}) — {status}"
        )
        lines.append(
            f"- 발견: {source.get('requested_url')}"
        )
        lines.append(
            f"- 최종 URL: {source.get('final_url')} · 방법 `{source.get('method')}`"
            f" · 수집 시각 {source.get('capture_time')}"
            + (f" · 저장본 기록 시각 {source.get('stored_capture_at')}"
               if source.get("stored_capture_at") else "")
        )
        lines.append(
            f"- 성격: {source.get('source_type_note')} · 추출기 {source.get('collector')}"
            f" · 본문 {source.get('body_chars')}자 · sha256 `{source.get('body_sha256')}`"
        )
        if source.get("excerpts"):
            lines.append("")
            for excerpt in source["excerpts"]:
                lines.append(f"> {excerpt[:EXCERPT_CHARS_IN_EVIDENCE]}")
                lines.append("")
    if summary:
        lines += ["", "## 생성 결과", ""]
        lines.append(f"- run `{summary.get('run_id')}` · mode `{summary.get('mode')}`"
                     f" · quality `{summary.get('quality')}` · 실제 전송 {summary.get('external_calls')}회")
        lines.append("")
        lines.append("```")
        lines.extend((summary.get("body") or "(본문 없음)").splitlines())
        lines.append("```")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _repo_safe_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    """저장소에 남길 요약. 요청 전문·기사 발췌는 빼고 해시·식별자만 남긴다."""
    safe = {k: v for k, v in summary.items() if k != "attempts"}
    attempts = []
    for attempt in summary.get("attempts") or ():
        row = {k: v for k, v in attempt.items() if k != "request_spec"}
        spec = attempt.get("request_spec") or {}
        rows = spec.get("parameters", {}).get("contents") if isinstance(spec, Mapping) else None
        text = ""
        if rows and isinstance(rows, list):
            parts = (rows[0] or {}).get("parts") or []
            if parts and isinstance(parts[0], Mapping):
                text = str(parts[0].get("text") or "")
        row["request_chars"] = len(text)
        row["request_sha256"] = _sha256_text(text) if text else None
        attempts.append(row)
    safe["attempts"] = attempts
    node_state = dict(safe.get("node_state") or {})
    node_state.pop("payload", None)
    safe["node_state"] = node_state
    return safe


def _write_preflight_only(preflight: Mapping[str, Any]) -> None:
    """preflight 증거만 쓴다. 생성 결과·묶음 파일을 덮어쓰지 않는다."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "preflight.json").write_text(
        json.dumps(preflight, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _write_outputs(
    *,
    bundle: Mapping[str, Any],
    preflight: Mapping[str, Any],
    summary: Mapping[str, Any] | None,
    timings: Mapping[str, Any],
) -> dict[str, str]:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    evidence = _evidence_view(bundle)
    (EVIDENCE_DIR / "source-bundle.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    paths["source_bundle_json"] = str(EVIDENCE_DIR / "source-bundle.json")
    _write_markdown(EVIDENCE_DIR / "source-bundle.md", bundle=evidence, summary=summary)
    paths["source_bundle_md"] = str(EVIDENCE_DIR / "source-bundle.md")

    # preflight를 넘기지 않은 실행(collect·reprocess)이 기존 preflight 증거를
    # 빈 객체로 덮어쓰지 않게 한다.
    if preflight:
        (EVIDENCE_DIR / "preflight.json").write_text(
            json.dumps(preflight, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if (EVIDENCE_DIR / "preflight.json").exists():
        paths["preflight"] = str(EVIDENCE_DIR / "preflight.json")

    if summary:
        preview_md = EVIDENCE_DIR / "generated-preview.md"
        preview_md.write_text(
            "\n".join(
                [
                    "# R4 주목 선수 — 실제 생성 결과 (시험)",
                    "",
                    f"- 성격: `{PROTOTYPE_LABEL}` · run `{summary.get('run_id')}`",
                    (
                        f"- 이 재처리에서 새 전송: {summary.get('external_calls')}회"
                        f" (원 실행의 실제 전송은 attempt {summary.get('attempt_count')}건 중"
                        " 1회 성공, 재전송 없음)"
                        if summary.get("reprocessed")
                        else f"- 실제 모델 전송: {summary.get('external_calls')}회"
                        f" · attempt {summary.get('attempt_count')}건"
                    ),
                    f"- quality `{summary.get('quality')}`",
                    "",
                    "## 본문",
                    "",
                    summary.get("body") or "(본문 없음)",
                    "",
                    "## 출처 (관리자 영역)",
                    "",
                    *[
                        f"- {item.get('label')} · {item.get('url') or '(URL 없음)'}"
                        f" · {item.get('kind')}"
                        for item in summary.get("sources") or ()
                    ],
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        paths["generated_preview_md"] = str(preview_md)
        # 저장소 증거에는 요청 본문(기사 발췌 포함)을 넣지 않는다.
        (EVIDENCE_DIR / "generated-preview.json").write_text(
            json.dumps(_repo_safe_summary(summary), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths["generated_preview_json"] = str(EVIDENCE_DIR / "generated-preview.json")
        (EVIDENCE_DIR / "run-summary.json").write_text(
            json.dumps(
                {
                    "prototype": PROTOTYPE_LABEL,
                    "run_id": summary.get("run_id"),
                    "section_result_id": summary.get("section_result_id"),
                    "section_result_version": summary.get("section_result_version"),
                    "mode": summary.get("mode"),
                    "status": summary.get("status"),
                    "quality": summary.get("quality"),
                    "external_calls": summary.get("external_calls"),
                    "attempt_count": summary.get("attempt_count"),
                    "attempts": summary.get("attempts"),
                    "module_execution_ids": summary.get("module_execution_ids"),
                    "result_ids": summary.get("result_ids"),
                    "budget": summary.get("budget"),
                    "bundle_artifact_id": (summary.get("node_state") or {}).get(
                        "bundle_artifact_id"
                    ),
                    "raw_artifact_id": (summary.get("node_state") or {}).get("raw_artifact_id"),
                    "request_check": summary.get("request_check"),
                    "validation_notes": (summary.get("node_state") or {}).get(
                        "validation_notes"
                    ),
                    "rejected_items": (summary.get("node_state") or {}).get("rejected_items"),
                    "korean_labels_applied": (summary.get("node_state") or {}).get(
                        "korean_labels_applied"
                    ),
                    "unmapped": (summary.get("node_state") or {}).get("unmapped"),
                    "players": (summary.get("node_state") or {}).get("payload_players"),
                    # 재처리 실행이면 "새 전송 없음"을 기록에 남긴다.
                    "reprocessed": summary.get("reprocessed"),
                    "new_send": summary.get("new_send"),
                    "reprocessed_from_run": (summary.get("node_state") or {}).get(
                        "reprocessed_from_run"
                    ),
                    "duration_ms": dict(timings),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        paths["run_summary"] = str(EVIDENCE_DIR / "run-summary.json")
    return paths


# --------------------------------------------------------------------------
# 진입점
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--phase", choices=("collect", "preflight", "run", "reprocess", "all"), default="all"
    )
    parser.add_argument("--bundle-json", type=Path, default=None)
    # 이미 지불한 응답을 **다시 보내지 않고** 후처리만 재실행할 때 쓴다.
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--keep-scratch", action="store_true")
    args = parser.parse_args(argv)

    env_report = _load_environment()
    moment = datetime.now(timezone.utc)
    timings: dict[str, Any] = {"started_at": moment.isoformat()}

    from app.preview.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    print("=== 설정 (값 미출력) ===")
    print(f"model: {settings.model_name} | location: {settings.model_location}")
    print(f"live_enabled: {settings.model_live_enabled}")
    print(f"fixtures_reader: {'set' if settings.fixtures_database_url else 'missing'}")
    print(f"names_reader: {'set' if settings.names_database_url else 'missing'}")
    print(f"dev_env_keys: {', '.join(k for k in env_report['dev_keys'])}")

    if args.phase == "reprocess":
        if not args.run_id:
            print("blocked: --run-id 가 필요합니다.")
            return 1
        if args.bundle_json is None:
            args.bundle_json = SCRATCH_ROOT / "preview-r4-information-bundle.json"
        bundle = json.loads(Path(args.bundle_json).read_text(encoding="utf-8"))
        summary = reprocess_saved_run(run_id=args.run_id, bundle=bundle)
        paths = _write_outputs(
            bundle=bundle, preflight={}, summary=summary, timings=summary.get("duration_ms") or {}
        )
        print("\n=== 재처리 본문 (전송 0회) ===")
        print(summary.get("body") or "(본문 없음)")
        print("\n=== 산출물 ===")
        for name, path in paths.items():
            print(f"- {name}: {path}")
        return 0 if (summary.get("body") or "").strip() else 4

    if args.phase in ("preflight", "all") and (
        not settings.model_live_enabled or not settings.model_name
    ):
        print("blocked: 모델 설정이 없어 전송 전에 멈춥니다.")
        return 1

    # 1) 수집
    if args.phase in ("collect", "all"):
        collect_started = time.perf_counter()
        db_snapshot = _collect_db_snapshot(moment=moment)
        db_ms = int((time.perf_counter() - collect_started) * 1000)
        http_started = time.perf_counter()
        collected, discovery_notes, fulham_probes = _collect_sources(moment)
        http_ms = int((time.perf_counter() - http_started) * 1000)
        bundle = _build_bundle(
            moment=moment,
            db_snapshot=db_snapshot,
            collected=collected,
            discovery_notes=discovery_notes,
            fulham_probes=fulham_probes,
        )
        timings.update({"collect_db_ms": db_ms, "collect_http_ms": http_ms})
        print("\n=== 수집 ===")
        print(f"db_snapshot_ms: {db_ms} | http_ms: {http_ms}")
        for source in bundle["sources"]:
            print(
                f"- {source['source_id']}: {source['source_type']} · {source['method']}"
                f" · 본문 {source['body_chars']}자"
                + (f" · 실패: {source['failure']}" if source["failure"] else "")
            )
        for row in bundle["db_facts"]:
            print(f"- DB 사실 {row['fact_id']}")
        scratch_bundle = SCRATCH_ROOT / "preview-r4-information-bundle.json"
        scratch_bundle.write_text(
            json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"scratch bundle: {scratch_bundle}")
        args.bundle_json = scratch_bundle
        # 수집 단계는 **절대 전송하지 않는다.** 여기서 끝내지 않으면 수집만 확인하려던
        # 실행이 preflight·유료 전송까지 진행된다(실제로 한 번 그렇게 나갔다).
        if args.phase == "collect":
            usable_now = [
                source for source in bundle.get("sources") or () if source.get("passages")
            ]
            print(f"\ncollect: 브라우저 없이 본문 확보 {len(usable_now)}건. 전송하지 않았습니다.")
            _write_outputs(bundle=bundle, preflight={}, summary=None, timings=timings)
            return 0
    else:
        if args.bundle_json is None:
            print("blocked: --bundle-json 이 필요합니다.")
            return 1
        bundle = json.loads(args.bundle_json.read_text(encoding="utf-8"))

    usable = [source for source in bundle.get("sources") or () if source.get("passages")]
    if not usable:
        print("\nblocked: 브라우저 없이 본문을 확보한 웹 출처가 0건입니다.")
        _write_outputs(bundle=bundle, preflight={}, summary=None, timings=timings)
        return 2

    # 2) 오프라인 preflight
    preflight = run_preflight(bundle=bundle)
    timings["preflight_ms"] = preflight["elapsed_ms"]
    print("\n=== preflight (전송 0회) ===")
    print(json.dumps(preflight, ensure_ascii=False, indent=2)[:2000])
    if not preflight["parsed_ok"] or preflight["compose_body_chars"] <= 0:
        print("blocked: preflight 실패. 전송하지 않습니다.")
        _write_outputs(bundle=bundle, preflight=preflight, summary=None, timings=timings)
        return 3
    if args.phase == "preflight":
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        _write_preflight_only(preflight)
        print(f"preflight written: {EVIDENCE_DIR / 'preflight.json'}")
        return 0

    # 3) 실제 1회 전송
    from app.preview.retry import plan_limits

    limits = plan_limits(
        attempts_per_call=1,
        model_requests=1,
        normal_model_calls=1,
        deadline_seconds=900,
    )
    print(
        f"\n=== 전송 상한 === attempts_per_call={limits.attempts_per_call}"
        f" model_requests={limits.model_requests} normal_model_calls={limits.normal_model_calls}"
    )
    run_started = time.perf_counter()
    summary = run_trial(
        bundle=bundle,
        model_name=settings.model_name or "",
        project=settings.model_project or "",
        location=settings.model_location,
        credentials_json=settings.model_credentials_json or "",
        limits=limits,
    )
    timings["run_ms"] = int((time.perf_counter() - run_started) * 1000)
    timings["send_ms"] = (summary.get("node_state") or {}).get("send_elapsed_ms")
    timings["finished_at"] = datetime.now(timezone.utc).isoformat()

    print("\n=== 실행 요약 ===")
    for key in ("run_id", "section_result_id", "mode", "status", "quality",
                "external_calls", "attempt_count"):
        print(f"{key}: {summary.get(key)}")
    print(f"timings: {json.dumps(timings, ensure_ascii=False)}")
    print("\n=== 본문 ===")
    print(summary.get("body") or "(본문 없음)")
    request_check = summary.get("request_check") or {}
    print("\n=== 요청 확인 ===")
    print(json.dumps(request_check, ensure_ascii=False, indent=2)[:1500])
    if summary.get("diagnostics"):
        print("\n=== 관리자 진단 ===")
        for line in summary["diagnostics"]:
            print(f"- {line}")
    if summary.get("unavailable_reason"):
        print(f"\nunavailable_reason: {summary['unavailable_reason']}")

    paths = _write_outputs(
        bundle=bundle, preflight=preflight, summary=summary, timings=timings
    )
    print("\n=== 산출물 ===")
    for name, path in paths.items():
        print(f"- {name}: {path}")
    return 0 if (summary.get("body") or "").strip() else 4


if __name__ == "__main__":
    sys.exit(main())
