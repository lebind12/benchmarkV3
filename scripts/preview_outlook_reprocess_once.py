"""outlook 섹션 재처리 결과를 **새 버전으로 실제 저장**한다 (모델 호출 0회).

무엇을 하는가:

1. run `9c079eea…`의 **저장된** outlook 응답 원문(artifact)과 그 실행의 정보 원문 묶음을 읽는다.
2. 저장된 응답을 **새 매체 URL 허용 규칙**(`_source_urls(..., search_material=...)`)으로 다시
   파싱·정리한다. 실패한 출처(403)로 버려졌던 검색 근거 매체 항목이 복원된다.
3. 기존 `_save_draft`로 **새 모듈 결과 + 새 섹션 결과 버전**을 append 저장한다.
   기존 v1·원문 응답·시도·승인 행은 건드리지 않는다.

하지 않는 것:

- 모델·HTTP 호출 0. 저장 원문만 쓴다(`RecordedTransport`도 쓰지 않는다 — 요청을 재구성하지 않음).
- 새 범용 replay 엔진, 새 테이블, 코드 일반 개선 없음.
- 기존 행 UPDATE 없음(append만).

사용:

    ./.venv/bin/python scripts/preview_outlook_reprocess_once.py --run 9c079eea-... --confirm-write
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import uuid
from datetime import datetime, timezone

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SCRIPT_VERSION = "sf01-outlook-reprocess-1"
CREDENTIALS = pathlib.Path.home() / ".config" / "match-preview" / "preview-dev.env"
SECTION_ID = "section_outlook"
MODULE_ID = "R3"


def _load_env_file(path: pathlib.Path) -> dict[str, str]:
    mode = path.stat().st_mode & 0o777
    if mode != 0o600:
        raise SystemExit(f"refusing {path.name} with mode {oct(mode)}")
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def _prepare_environment() -> None:
    dev = _load_env_file(CREDENTIALS)
    mapping = {
        "PREVIEW_DATABASE_URL": dev.get("PREVIEW_DEV_DATABASE_URL"),
        "PREVIEW_IDENTITY_DATABASE_URL": dev.get("PREVIEW_IDENTITY_DATABASE_URL"),
        "PREVIEW_FIXTURES_DATABASE_URL": dev.get("PREVIEW_FIXTURES_DATABASE_URL"),
        "PREVIEW_NAMES_DATABASE_URL": dev.get("PREVIEW_NAMES_DATABASE_URL"),
        "PREVIEW_STATS_DATABASE_URL": dev.get("PREVIEW_STATS_DATABASE_URL"),
        "PREVIEW_ALLOW_NONLOCAL_DB": dev.get("PREVIEW_ALLOW_NONLOCAL_DB", "1"),
        "PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB": dev.get(
            "PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB", "1"
        ),
        "PREVIEW_ENV": "dev",
    }
    for key, value in mapping.items():
        if value:
            os.environ[key] = str(value)
    # live 실행이 아니어도 모델 전송이 없다는 사실을 명시한다.
    os.environ.setdefault("PREVIEW_MODEL_LIVE_ENABLED", "0")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", required=True, help="재처리할 원본 실행 ID")
    parser.add_argument(
        "--confirm-write",
        action="store_true",
        help="preview_dev append 쓰기를 승인한다. 없으면 미리보기만 한다.",
    )
    args = parser.parse_args(argv)

    _prepare_environment()
    from app.preview.config import get_settings

    get_settings.cache_clear()

    from sqlalchemy import select

    from app.preview.db import get_session_factory
    from app.preview import bundle_pipeline, information_bundle as bundle_contract, store
    from app.preview.contracts import QualityStatus, RunMode
    from app.preview.models import PreviewArtifact, PreviewAttempt
    from app.preview.modules import bundle_sections, outlook as outlook_module

    run_id = uuid.UUID(args.run)
    factory = get_session_factory()

    with factory() as probe:
        # 1) 저장된 요청·응답 원문 (읽기 전용)
        attempt = probe.scalars(
            select(PreviewAttempt)
            .where(
                PreviewAttempt.run_id == run_id,
                PreviewAttempt.logical_call_id == SECTION_ID,
            )
            .order_by(PreviewAttempt.attempt_ordinal.desc())
            .limit(1)
        ).first()
        if attempt is None:
            print("이 실행에 outlook 시도가 없습니다.", file=sys.stderr)
            return 2
        if attempt.response_artifact_id is None:
            print("저장된 응답 원문이 없어 재처리할 수 없습니다.", file=sys.stderr)
            return 2
        response_row = probe.get(PreviewArtifact, attempt.response_artifact_id)
        if response_row is None or response_row.body is None:
            print("응답 원문 아티팩트를 읽을 수 없습니다.", file=sys.stderr)
            return 2
        raw_response = json.loads(response_row.body)

        # 2) 그 실행의 정보 원문 묶음(전달된 검색 자료 포함)
        record = store.load_information_bundle(probe, run_id)
        if not record.get("available"):
            print(f"정보 원문 묶음이 없습니다: {record.get('reason')}", file=sys.stderr)
            return 2
        bundle = bundle_contract.InformationBundle.from_dict(record["bundle"])

    payload = bundle.to_dict()
    search = bundle_sections._search_material(payload, SECTION_ID)  # noqa: SLF001
    selection = bundle_sections._select_passages(payload, SECTION_ID)  # noqa: SLF001
    text_out = ""
    for candidate in raw_response.get("candidates") or ():
        content = candidate.get("content") or {}
        for part in content.get("parts") or ():
            if part.get("text"):
                text_out += str(part["text"])
    parsed_rows, parse_reason = outlook_module.parse_media_response(text_out)
    allowed_urls = bundle_sections._source_urls(  # noqa: SLF001
        payload, SECTION_ID, search_material=search
    )
    allowed_evidence = set(selection.passage_ids) | set(search.finding_ids)
    rows, row_diagnostics = bundle_sections._media_rows(  # noqa: SLF001
        parsed_rows, allowed_urls=allowed_urls, allowed_evidence=allowed_evidence
    )
    body = bundle_sections._compose_media_body(rows)  # noqa: SLF001

    structured = {
        "media": [
            {
                "publisher": row.get("publisher"),
                "url": row.get("url"),
                "published_at": row.get("published_at"),
                "statement": row["statement"],
                "predicted_score": row.get("predicted_score"),
                "evidence": list(row["evidence"]),
            }
            for row in rows
        ]
    }
    print(f"script {SCRIPT_VERSION}")
    print(f"run {run_id} / {SECTION_ID}")
    print(f"원본 응답 artifact: {attempt.response_artifact_id}")
    print(f"재처리 매체 항목: {len(rows)}건 -> {[r.get('publisher') for r in rows]}")
    print(f"허용 주소: {len(allowed_urls)}개 (검색 자료 {len(search.rows)}줄 전달)")
    print(f"본문 {len(body)}자")

    if not body:
        print(
            "재처리 본문이 비어 있습니다. 빈 본문을 성공으로 저장하지 않습니다.",
            file=sys.stderr,
        )
        return 2

    diagnostics = tuple(
        [
            f"저장 응답 재처리({SCRIPT_VERSION}): 새 매체 URL 허용 규칙으로 다시 정리했습니다.",
            f"원본 실행 {run_id}의 outlook 응답 artifact {attempt.response_artifact_id}를 사용했습니다.",
            "이 결과는 모델·HTTP 호출 없이 나온 새 버전입니다(원본 v1은 그대로).",
        ]
        + [str(item) for item in row_diagnostics]
        + (list(search.diagnostics) if hasattr(search, "diagnostics") else [])
    )

    delivery = bundle_sections._delivery(  # noqa: SLF001
        section_id=SECTION_ID,
        call=None,
        selection=selection,
        model_delivered=False,
        prompt_version=bundle_sections.PROMPT_VERSION_OUTLOOK,
        note=(
            "저장된 응답 재처리입니다. 모델·수집 호출 0회이며, 이 섹션의 실제 모델 전달은"
            " 원본 v1의 기록을 봅니다."
        ),
        search_finding_ids=search.finding_ids,
    )
    draft = bundle_sections.SectionDraft(
        section_id=SECTION_ID,
        module_id=MODULE_ID,
        title="외부 매체 전망",
        body=body,
        sources=tuple(bundle_sections._reader_sources(selection)),  # noqa: SLF001
        structured=structured,
        quality=QualityStatus.READY,
        prompt_version=bundle_sections.PROMPT_VERSION_OUTLOOK,
        diagnostics=diagnostics,
        delivery=delivery,
        mode="replay",
        external_calls=0,
    )

    if not args.confirm_write:
        print("미리보기만 했습니다. 실제 append 저장은 --confirm-write가 필요합니다.")
        return 0

    # 3) append 저장 — 기존 store/_save_draft 재사용
    with factory() as session:
        result_id = bundle_pipeline._save_draft(  # noqa: SLF001
            session,
            run_id=run_id,
            draft=draft,
            mode=RunMode.REPLAY,
            actor_id=1,
            now=datetime.now(timezone.utc),
        )
        store.save_information_bundle(
            session,
            run_id=run_id,
            bundle=bundle.with_section_delivery(delivery),
            actor_id=1,
            now=datetime.now(timezone.utc),
        )
        session.commit()
        row = store.get_section_result(session, run_id, result_id)
        print(f"저장 완료: section_result_id={result_id} version={row.version} chars={len(row.body)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
