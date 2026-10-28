"""Human/operator entry point; no worker-facing approve or mark-done tool."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import uuid

from .controller import Controller
from .process import run_codex
from .requirements import (CONTRACT_SCHEMA, ContractError, contract_hash,
                           planning_prompt, readiness_issues, validate_contract)


def read(path):
    return sys.stdin.read() if path == "-" else Path(path).expanduser().read_text()


def write_new(path, value):
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def parser():
    p = argparse.ArgumentParser(description="원문 요구사항과 실행 증거를 보존하는 외부 개발 하네스")
    p.add_argument("--workspace", default=str(Path.cwd()), help="개발할 별도 worktree; 기본 현재 디렉터리")
    p.add_argument("--state-root", default=os.environ.get("BENCHMARK_HARNESS_STATE_ROOT"),
                   help="작업 디렉터리 밖의 비공개 상태 저장소")
    p.add_argument("--model", default="gpt-6.1-sol", help="개발/검토 모델 (기본 gpt-6.1-sol)")
    p.add_argument("--json", action="store_true", help="전체 상태를 JSON으로 출력")
    sub = p.add_subparsers(dest="command", required=True)
    draft = sub.add_parser("draft", help="읽기 전용 기획: 모호한 요청을 명세·질문으로 구체화")
    draft.add_argument("--request", required=True, help="사용자 원문 UTF-8 파일 또는 -")
    draft.add_argument("--context", help="기존 결정·정책·계획 파일 (선택)")
    draft.add_argument("--mode", choices=["QUICK", "FULL"], required=True)
    draft.add_argument("--output", required=True, help="새 초안 JSON 경로; 기존 파일 덮어쓰지 않음")
    draft.add_argument("--timeout", type=int, default=900)
    check = sub.add_parser("check-contract", help="명세의 구조·원문 연결·미정 사항 확인 (AI 의미 검토 아님)")
    check.add_argument("--request", required=True)
    check.add_argument("--contract", required=True)
    init = sub.add_parser("init", help="원문과 명세를 저장해 작업 생성; 아직 구현하지 않음")
    init.add_argument("--request", required=True)
    init.add_argument("--contract", required=True)
    for name, help_text in (("review-spec", "독립된 읽기 전용 원문·명세 누락 검토"),
                            ("run", "명세 검토 → 개발 → 검증 → 제한 재작업 실행"),
                            ("status", "현재 상태와 미완료 이유 확인"),
                            ("show", "원문·명세·실행 근거 전체 출력"),
                            ("cancel", "실행 중단 요청; 파일 변경은 보존"),
                            ("resume", "중단·해결된 환경 오류 이후 명시적으로 재개"),
                            ("events", "엔진이 실제 기록한 이벤트와 실행 이력")):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("work_id")
    sub.add_parser("list", help="이 workspace의 작업 목록")
    change = sub.add_parser("change", help="실제 사용자 결정으로 명세 새 버전 작성; 이전 PASS 무효화")
    change.add_argument("work_id")
    change.add_argument("--contract", required=True)
    change.add_argument("--receipt", required=True, help="message/source/old_hash/new_hash JSON")
    feedback = sub.add_parser("feedback", help="사용 중 이상현상·사용자 평가 기록 (자동 하네스 수정 없음)")
    feedback.add_argument("work_id")
    feedback.add_argument("--message", required=True)
    feedback.add_argument("--category", choices=["unclassified", "code", "environment", "harness"], default="unclassified")
    feedback.add_argument("--evidence", action="append", default=[], help="원본 근거 파일 경로; 내용은 복제하지 않음")
    return p


def display(value, full=False):
    if isinstance(value, dict) and "status" in value and not full:
        fields = ("id", "status", "revision", "contract_version", "contract_hash", "workspace", "issues", "repairs", "cancel_requested")
        value = {key: value[key] for key in fields if key in value}
    print(json.dumps(value, ensure_ascii=False, indent=2))


def isolated(workspace):
    source = Path(os.environ.get("BENCHMARK_HARNESS_SOURCE_ROOT", __file__)).resolve()
    if source == workspace or source.is_relative_to(workspace):
        raise ValueError("개발 workspace에는 설치된 제어 코드를 포함할 수 없습니다. 별도 worktree를 지정하세요. "
                         "원본에서 stash/reset/브랜치 전환을 하지 말고 새 worktree를 준비하세요.")


def main(argv=None):
    args = parser().parse_args(argv)
    workspace = Path(args.workspace).expanduser().resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError("workspace must be a directory")
    if not args.state_root:
        key = hashlib.sha256(str(workspace).encode()).hexdigest()[:20]
        args.state_root = str(Path.home() / ".local/state/benchmark-harness" / key)
    root = Path(args.state_root).expanduser().resolve()
    if root == workspace or root.is_relative_to(workspace):
        raise ValueError("State must be outside workspace")
    if args.command == "draft":
        request = read(args.request)
        if not request.strip() or not 1 <= args.timeout <= 14400:
            raise ValueError("Nonempty request and timeout between 1 and 14400 required")
        if Path(args.output).expanduser().exists():
            raise ValueError("Draft output already exists; choose a new version path")
        context = f"선택한 모드: {args.mode}\n" + (read(args.context) if args.context else "")
        result = run_codex(workspace, planning_prompt(request, context), root / "drafts" / uuid.uuid4().hex,
                           model=args.model, read_only=True, schema=CONTRACT_SCHEMA, timeout=args.timeout)
        if not result["transport_ok"]:
            display({"status": "BLOCKED", "issues": ["Planner execution failed; no implementation started"],
                     "receipt": result["receipt"]}, True)
            return 2
        contract = validate_contract(json.loads(result["response"]), request)
        if contract["mode"] != args.mode:
            raise ValueError("Planner changed the selected development mode")
        write_new(args.output, contract)
        display({"draft": str(Path(args.output).expanduser().resolve()), "contract_hash": contract_hash(contract),
                 "issues": readiness_issues(contract, request), "implementation_started": False,
                 "receipt": result["receipt"]}, True)
        return 0
    if args.command == "check-contract":
        request, contract = read(args.request), json.loads(read(args.contract))
        issues = readiness_issues(contract, request)
        display({"ready_for_semantic_review": not issues, "issues": issues,
                 "contract_hash": contract_hash(contract)}, True)
        return 2 if issues else 0
    if args.command in ("init", "run", "resume"):
        isolated(workspace)
    controller = Controller(root, workspace)
    if args.command == "init":
        result = controller.create(read(args.request), json.loads(read(args.contract)))
    elif args.command == "review-spec":
        result = controller.review_spec(args.work_id, model=args.model)
    elif args.command in ("run", "resume"):
        result = getattr(controller, args.command)(args.work_id, model=args.model)
    elif args.command in ("status", "show"):
        result = controller.status(args.work_id)
    elif args.command == "cancel":
        result = controller.cancel(args.work_id)
    elif args.command == "change":
        result = controller.record_scope_change(args.work_id, json.loads(read(args.contract)), json.loads(read(args.receipt)))
    elif args.command == "list":
        with sqlite3.connect(controller.database) as db:
            result = [{key: state.get(key) for key in ("id", "status", "workspace", "updated_at")}
                      for row in db.execute("SELECT state FROM work ORDER BY rowid DESC")
                      if (state := json.loads(row[0]))["workspace"] == str(workspace)]
    elif args.command == "events":
        controller.status(args.work_id)
        with sqlite3.connect(controller.database) as db:
            result = [{"sequence": row[0], "at": row[1], "kind": row[2], "payload": json.loads(row[3])}
                      for row in db.execute("SELECT sequence,at,kind,payload FROM events WHERE work_id=? ORDER BY sequence", (args.work_id,))]
    elif args.command == "feedback":
        state = controller.status(args.work_id)
        evidence = []
        for name in args.evidence:
            path = Path(name).expanduser().resolve(strict=True)
            evidence.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        result = {"id": uuid.uuid4().hex, "work_id": state["id"], "at": time.time(),
                  "category_hypothesis": args.category, "message": args.message,
                  "evidence": evidence, "contract_hash": state["contract_hash"],
                  "source": "explicit operator/user observation", "automatically_applied": False}
        write_new(root / args.work_id / "feedback" / (result["id"] + ".json"), result)
    else:
        raise ValueError("Unknown command")
    display(result, args.json or args.command in ("show", "events", "feedback", "list"))
    if args.command in ("run", "resume"):
        return 0 if result["status"] == "VERIFIED" else 2
    if args.command == "review-spec":
        return 0 if result["status"] == "READY" else 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, sqlite3.Error) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
