#!/usr/bin/env python3
"""Record operator-led work handoffs. Identity is a convention, not authentication.

This command never starts agents, merges Git, or deploys. MERGED recording requires
an ancestry-preserving merge (fast-forward/merge commit); squash/rebase is unsupported.
"""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import jsonschema

STATES = ['PLANNED', 'DEVELOPING', 'MERGE_REQUESTED', 'TESTING', 'TEST_REPORTED', 'CHANGES_REQUESTED', 'MERGE_APPROVED', 'MERGED', 'ESCALATED']
SCRIPT_ROOT = Path(__file__).resolve().parents[1]


def fail(message):
    raise ValueError(message)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json(path):
    with path.open(encoding='utf-8') as handle:
        return json.load(handle)


def schema(name):
    return load_json(SCRIPT_ROOT / '.codex/schemas' / name)


def validate_shape(value, name):
    jsonschema.Draft202012Validator(schema(name)).validate(value)


def file_record(value, root, markdown=False):
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.is_file():
        fail(f'File does not exist: {path}')
    if markdown and path.suffix.lower() not in ('.md', '.markdown'):
        fail(f'Markdown report required: {path}')
    data = path.read_bytes()
    if not data.strip():
        fail(f'Empty file: {path}')
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest()}


def verify_record(record, root):
    if file_record(record['path'], root)['sha256'] != record['sha256']:
        fail(f'Content changed: {record["path"]}; create a new work item for requirement changes')


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)
    if result.returncode:
        fail('Git verification failed: ' + result.stderr.strip())
    return result.stdout.strip()


def commit_sha(root, value):
    if not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', value):
        fail('A full lowercase Git commit SHA is required')
    resolved = git(root, 'rev-parse', '--verify', value + '^{commit}')
    if resolved != value:
        fail('Commit SHA must identify the commit itself')
    return resolved


def check_brief(brief, root):
    validate_shape(brief, 'work-brief.schema.json')
    ids = [item['id'] for item in brief['acceptance_criteria']]
    if len(ids) != len(set(ids)):
        fail('Acceptance criterion IDs must be unique')
    file_record(brief['service_plan'], root)


def verify_brief(state, root):
    verify_record(state['brief_file'], root)
    if load_json(Path(state['brief_file']['path'])) != state['brief']:
        fail('Work brief differs from the recorded snapshot')
    check_brief(state['brief'], root)
    verify_record(state['service_plan_file'], root)


def verify_current(state, root):
    verify_brief(state, root)
    submission = state.get('submission')
    if submission:
        commit_sha(root, submission['commit'])
        verify_record(submission['report'], root)
        if submission['revision'] != state['revision']:
            fail('Stale submission revision')
    if state.get('test_brief'):
        verify_record(state['test_brief'], root)
    test = state.get('test')
    if test:
        if not submission or test['commit'] != submission['commit'] or test['revision'] != state['revision']:
            fail('Test report does not match current submission')
        verify_record(test['report'], root)
        for evidence in test['evidence']:
            verify_record(evidence, root)
        check_test_report(load_json(Path(test['report']['path'])), state, root)
    if state.get('approval'):
        approval = state['approval']
        if not test or test['verdict'] != 'PASS' or approval['commit'] != submission['commit'] or approval['revision'] != state['revision']:
            fail('Approval does not match current passing test')
        verify_record(approval['review'], root)
    if state.get('merge_commit'):
        merge = commit_sha(root, state['merge_commit'])
        git(root, 'merge-base', '--is-ancestor', submission['commit'], merge)


def check_test_report(report, state, root):
    validate_shape(report, 'work-test-report.schema.json')
    if report['revision'] != state['revision']:
        fail('Test report revision must match the current revision')
    if report['commit'] != state['submission']['commit']:
        fail('Test report commit must match submitted commit')
    required = {item['id'] for item in state['brief']['acceptance_criteria']}
    covered = {item['criterion_id'] for item in report['scenarios']}
    if covered - required:
        fail('Test report contains unknown acceptance criterion IDs')
    evidence = [file_record(item['evidence'], root) for item in report['scenarios']]
    statuses = {item['status'] for item in report['scenarios']}
    if report['verdict'] == 'PASS' and (covered != required or statuses != {'PASS'}):
        fail('PASS requires every acceptance criterion covered and every scenario PASS')
    if report['verdict'] == 'FAIL' and 'FAIL' not in statuses:
        fail('FAIL verdict requires a failed scenario')
    if report['verdict'] == 'BLOCKED' and 'BLOCKED' not in statuses:
        fail('BLOCKED verdict requires a blocked scenario')
    return evidence


def validate_state(state, root, current=True):
    validate_shape(state, 'work-flow.schema.json')
    actors = state['actors']
    if len(set(actors.values())) != 3:
        fail('Operator, developer, and tester must be different identities')
    events = state['events']
    if any(event['sequence'] != i + 1 for i, event in enumerate(events)):
        fail('Invalid event sequence')
    previous, revision, failures = None, 0, 0
    transitions = {
        'init': ('operator', [None], ['PLANNED']),
        'start': ('operator', ['PLANNED', 'CHANGES_REQUESTED'], ['DEVELOPING']),
        'submit': ('developer', ['DEVELOPING'], ['MERGE_REQUESTED']),
        'test-start': ('operator', ['MERGE_REQUESTED'], ['TESTING']),
        'test-report': ('tester', ['TESTING'], ['TEST_REPORTED']),
        'decide': ('operator', ['MERGE_REQUESTED', 'TEST_REPORTED'], ['MERGE_APPROVED', 'CHANGES_REQUESTED', 'ESCALATED']),
        'merged': ('operator', ['MERGE_APPROVED'], ['MERGED']),
    }
    for item in events:
        role, sources, targets = transitions[item['command']]
        if item['from_state'] != previous or previous not in sources or item['to_state'] not in targets or item['by'] != actors[role]:
            fail('Invalid handoff history or actor identity')
        if item['command'] == 'init' and item['sequence'] != 1:
            fail('Initialization must be the first event')
        if item['command'] == 'start':
            revision += 1
        if item['revision'] != revision:
            fail('Invalid event revision')
        if item['command'] == 'decide':
            verdict = item['details'].get('verdict')
            if verdict == 'REQUEST_CHANGES':
                failures += 1
                expected = 'ESCALATED' if failures >= 3 else 'CHANGES_REQUESTED'
            elif verdict == 'APPROVE' and previous == 'TEST_REPORTED':
                expected = 'MERGE_APPROVED'
            else:
                fail('Invalid decision history')
            if item['to_state'] != expected:
                fail('Decision history has incorrect resulting status')
        previous = item['to_state']
    if previous != state['status'] or revision != state['revision'] or failures != state['failed_attempts']:
        fail('Latest event does not match current state')
    if current:
        verify_current(state, root)


def save(path, state, root):
    validate_state(state, root)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.stem + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(state, handle, indent=2, ensure_ascii=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def event(state, command, actor, previous, details=None):
    state['updated_at'] = now()
    state['events'].append({'sequence': len(state['events']) + 1, 'at': state['updated_at'], 'command': command, 'by': actor, 'from_state': previous, 'to_state': state['status'], 'revision': state['revision'], 'details': copy.deepcopy(details or {})})


def require(state, actor, role, statuses):
    if actor != state['actors'][role]:
        fail(f'Only assigned {role} may perform this operation')
    if state['status'] not in statuses:
        fail(f'Invalid transition from {state["status"]}; expected {", ".join(statuses)}')


def parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''Brief JSON: goal, acceptance_criteria [{id, description}], owned_paths,
constraints, service_plan (existing file). Dedicated test brief: goal and
scenarios [{criterion_id, description}], covering every acceptance ID.
Test report JSON: commit, revision, verdict (PASS|FAIL|BLOCKED), summary,
scenarios [{criterion_id, status (PASS|FAIL|BLOCKED), evidence (file path)}].
All file paths resolve relative to --project-root; absolute paths are allowed.
Place global options before the command. Every mutation requires --by.
Requirement or service plan changes require a new work item. Rework requires
REQUEST_CHANGES then start; the third rejection escalates with no force bypass.
State history records decisions and hashes; identities are caller assertions.
Use guard-task-completed ID to require MERGED before marking a task complete.''')
    p.add_argument('--project-root', default=os.environ.get('HARNESS_PROJECT_ROOT', str(SCRIPT_ROOT)))
    p.add_argument('--state-root', default=os.environ.get('HARNESS_STATE_ROOT'))
    sub = p.add_subparsers(dest='command', required=True)
    for name in ['init', 'start', 'submit', 'test-start', 'test-report', 'decide', 'merged', 'status', 'validate', 'guard-task-completed']:
        cmd = sub.add_parser(name)
        cmd.add_argument('id')
        if name not in ['status', 'validate', 'guard-task-completed']:
            cmd.add_argument('--by', required=True)
        if name == 'init':
            for arg in ['service-id', 'brief', 'developer', 'tester']:
                cmd.add_argument('--' + arg, required=True)
            cmd.add_argument('--task-id')
        if name == 'submit':
            cmd.add_argument('--commit', required=True)
            cmd.add_argument('--report', required=True)
        if name == 'test-start':
            cmd.add_argument('--brief', required=True)
        if name == 'test-report':
            cmd.add_argument('--report', required=True)
        if name == 'decide':
            cmd.add_argument('--verdict', required=True, choices=['APPROVE', 'REQUEST_CHANGES'])
            cmd.add_argument('--review', required=True)
        if name == 'merged':
            cmd.add_argument('--merge-commit', required=True)
    sub.add_parser('list')
    sub.add_parser('validate-all')
    return p


def run(args):
    if args.command not in {'status', 'list', 'validate', 'validate-all', 'guard-task-completed'}:
        fail('Legacy work-flow is read-only. Use scripts/harness-run.sh; see docs/harness/external-control.md.')
    root = Path(args.project_root).resolve()
    state_root = Path(args.state_root).expanduser() if args.state_root else root / '.codex/state/work-flow'
    if not state_root.is_absolute():
        state_root = root / state_root
    state_root.mkdir(parents=True, exist_ok=True)
    # One lock serializes all readers/writers; state + history is a single atomic document.
    with (state_root / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        command = args.command
        if command in ['list', 'validate-all']:
            output = []
            for path in sorted(state_root.glob('*.json')):
                state = load_json(path)
                if command == 'validate-all':
                    validate_state(state, root)
                output.append({'id': state['id'], 'status': state['status'], 'revision': state['revision']})
            print(json.dumps(output, indent=2))
            return
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', args.id):
            fail('ID must contain only letters, digits, underscores or hyphens (max 128)')
        path = state_root / (args.id + '.json')
        if command == 'init':
            if path.exists():
                fail('Work item already exists')
            record = file_record(args.brief, root)
            brief = load_json(Path(record['path']))
            check_brief(brief, root)
            state = {'schema_version': 1, 'id': args.id, 'service_id': args.service_id, 'task_id': args.task_id or args.id, 'status': 'PLANNED', 'revision': 0, 'failed_attempts': 0, 'actors': {'operator': args.by, 'developer': args.developer, 'tester': args.tester}, 'brief': brief, 'brief_file': record, 'service_plan_file': file_record(brief['service_plan'], root), 'created_at': now(), 'updated_at': now(), 'events': []}
            event(state, command, args.by, None, {'brief': record})
        else:
            if not path.is_file():
                fail('Unknown work item')
            state = load_json(path)
            recovering = command == 'start' or (command == 'decide' and args.verdict == 'REQUEST_CHANGES')
            validate_state(state, root, current=not recovering)
            if recovering:
                verify_brief(state, root)
            if state['id'] != args.id:
                fail('State ID does not match filename')
            if command in ['status', 'validate', 'guard-task-completed']:
                if command == 'guard-task-completed' and state['status'] != 'MERGED':
                    fail('Task completion requires operator-recorded MERGED state')
                print(json.dumps(state if command == 'status' else {'id': state['id'], 'valid': True, 'status': state['status']}, indent=2, ensure_ascii=False))
                return
            previous = state['status']
            details = {}
            if command == 'start':
                require(state, args.by, 'operator', ['PLANNED', 'CHANGES_REQUESTED'])
                state['revision'] += 1
                for key in ['submission', 'test_brief', 'test', 'approval']:
                    state.pop(key, None)
                state['status'] = 'DEVELOPING'
            elif command == 'submit':
                require(state, args.by, 'developer', ['DEVELOPING'])
                state['submission'] = {'commit': commit_sha(root, args.commit), 'report': file_record(args.report, root, True), 'revision': state['revision']}
                state['status'] = 'MERGE_REQUESTED'
                details = state['submission']
            elif command == 'test-start':
                require(state, args.by, 'operator', ['MERGE_REQUESTED'])
                record = file_record(args.brief, root)
                brief = load_json(Path(record['path']))
                if 'acceptance_criteria' in brief:
                    check_brief(brief, root)
                    ids = {item['id'] for item in brief['acceptance_criteria']}
                else:
                    validate_shape(brief, 'work-test-brief.schema.json')
                    ids = {item['criterion_id'] for item in brief['scenarios']}
                if ids != {item['id'] for item in state['brief']['acceptance_criteria']}:
                    fail('Test brief must cover exactly the work acceptance criterion IDs')
                state['test_brief'] = record
                state['status'] = 'TESTING'
                details = {'test_brief': record, 'commit': state['submission']['commit']}
            elif command == 'test-report':
                require(state, args.by, 'tester', ['TESTING'])
                record = file_record(args.report, root)
                report = load_json(Path(record['path']))
                evidence = check_test_report(report, state, root)
                state['test'] = {'commit': report['commit'], 'revision': state['revision'], 'verdict': report['verdict'], 'report': record, 'evidence': evidence}
                state['status'] = 'TEST_REPORTED'
                details = state['test']
            elif command == 'decide':
                require(state, args.by, 'operator', ['TEST_REPORTED', 'MERGE_REQUESTED'])
                review = file_record(args.review, root, True)
                details = {'verdict': args.verdict, 'review': review, 'commit': state['submission']['commit']}
                if args.verdict == 'APPROVE':
                    if state['status'] != 'TEST_REPORTED' or state['test']['verdict'] != 'PASS':
                        fail('Approval requires current independent PASS test report')
                    state['approval'] = {'review': review, 'commit': state['submission']['commit'], 'revision': state['revision']}
                    state['status'] = 'MERGE_APPROVED'
                else:
                    state['failed_attempts'] += 1
                    details['rejected_artifacts'] = {key: state[key] for key in ['submission', 'test_brief', 'test', 'approval'] if key in state}
                    for key in ['submission', 'test_brief', 'test', 'approval']:
                        state.pop(key, None)
                    state['status'] = 'ESCALATED' if state['failed_attempts'] >= 3 else 'CHANGES_REQUESTED'
            elif command == 'merged':
                require(state, args.by, 'operator', ['MERGE_APPROVED'])
                merge = commit_sha(root, args.merge_commit)
                git(root, 'merge-base', '--is-ancestor', state['submission']['commit'], merge)
                state['merge_commit'] = merge
                state['status'] = 'MERGED'
                details = {'merge_commit': merge, 'submitted_commit': state['submission']['commit']}
            event(state, command, args.by, previous, details)
        save(path, state, root)
        print(json.dumps({'id': state['id'], 'status': state['status'], 'revision': state['revision']}, ensure_ascii=False))


if __name__ == '__main__':
    try:
        run(parser().parse_args())
    except (ValueError, OSError, jsonschema.ValidationError, KeyError, TypeError) as exc:
        print(f'work-flow: {exc}', file=sys.stderr)
        sys.exit(1)
