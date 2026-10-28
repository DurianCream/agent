#!/usr/bin/env python3
"""Nonblocking context checkpoint reminder; never resets or edits a rollout."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
HEADINGS = ("Basic Information", "Objective and Acceptance Criteria", "Result Summary", "Work Performed", "Artifacts", "Verification Results", "Unresolved Issues and Next Actions")
LEGACY_HEADINGS = ("기본 정보", "목표와 완료 기준", "결과 요약", "수행 내용", "산출물", "검증 결과", "미해결 사항과 후속 조치")
MAX_AGE = 120
MAX_TAIL = 64 * 1024 * 1024  # Bounded scan for long tool-heavy turns.
MAX_MARKDOWN = 96 * 1024
MAX_REMINDERS = 3


def moment(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp needs a timezone")
    return parsed.timestamp()


def under(root, value):
    root = Path(root).resolve()
    value = Path(value).resolve()
    if not value.is_relative_to(root):
        raise ValueError("Path escaped expected directory")
    return value


def atomic_json(path, data):
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent,
                                     prefix=".state-", suffix=".tmp", delete=False) as handle:
        temp = Path(handle.name)
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


@contextmanager
def locked(directory):
    """Use an OS lock that releases on process exit; never unlink its inode."""
    lock = under(directory, directory / ".lock")
    with lock.open("a+b", buffering=0) as handle:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            acquire = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            release = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            acquire = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        try:
            acquire()
        except OSError:
            yield False
            return
        try:
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b"\0")
            yield True
        finally:
            handle.seek(0)
            release()

def directory_for(root, session_id):
    if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{7,127}", session_id):
        raise ValueError("Invalid session id")
    key = hashlib.sha256(session_id.encode()).hexdigest()[:24]
    candidate = Path(root) / "work/context-checkpoints" / key
    for attempt in range(4):
        try:
            directory = under(root, candidate)
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                # Windows can report access denied while another creator wins.
                if not directory.is_dir():
                    raise
            return under(root, directory)
        except (PermissionError, ValueError) as error:
            retryable = os.name == "nt" and (isinstance(error, PermissionError)
                         or str(error) == "Path escaped expected directory")
            if not retryable or attempt == 3:
                raise
            time.sleep(0.01 * (attempt + 1))


def validate_request_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
        raise ValueError("request_id must be 32 lowercase hexadecimal characters")


def load_state(path):
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        data = handle.read(64 * 1024 + 1)
    if len(data) > 64 * 1024:
        raise ValueError("Checkpoint state is too large")
    state = json.loads(data)
    valid_statuses = ("armed", "requested", "requested_exhausted", "committed", "unavailable")
    if (not isinstance(state, dict) or type(state.get("schema_version")) is not int or state.get("schema_version") != 1
            or state.get("status") not in valid_statuses):
        raise ValueError("Unsupported checkpoint state")
    if type(state.get("cycle", 1)) is not int or state.get("cycle", 1) < 1:
        raise ValueError("Invalid checkpoint cycle")
    if state.get("restore_confirmed", False) is not False:
        raise ValueError("A local checkpoint state cannot confirm native restoration")
    if state["status"] != "armed":
        validate_request_id(state.get("request_id"))
        for name in ("session_id", "turn_id"):
            if not isinstance(state.get(name), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{7,127}", state[name]):
                raise ValueError("Invalid checkpoint " + name)
        for name in ("used", "window"):
            if type(state.get(name)) is not int or state[name] < (1 if name == "window" else 0):
                raise ValueError("Invalid checkpoint measurement")
        for name in ("usage_at", "ratio"):
            if type(state.get(name)) not in (float, int) or not math.isfinite(state[name]) or state[name] < 0:
                raise ValueError("Invalid checkpoint " + name)
        count = state.get("reminder_count", 0)
        if type(count) is not int or not 0 <= count <= MAX_REMINDERS:
            raise ValueError("Invalid reminder count")
        turns = state.get("notified_turn_ids", [state["turn_id"]])
        if (not isinstance(turns, list) or len(turns) > MAX_REMINDERS + 1
                or any(not isinstance(turn, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{7,127}", turn) for turn in turns)
                or len(turns) != len(set(turns)) or state["turn_id"] not in turns):
            raise ValueError("Invalid notified turns")
    if "checkpoint_path" in state:
        under(path.parent, state["checkpoint_path"])
        if not isinstance(state.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", state["sha256"]):
            raise ValueError("Invalid checkpoint digest")
    return state

def measure(payload, root=ROOT, trusted_sessions=None, now=None):
    """Return only a fresh, matching main-session current-context measurement."""
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    if not isinstance(payload, dict):
        raise ValueError("Hook input must be an object")
    if payload.get("hook_event_name") != "PostToolUse":
        raise ValueError("Wrong hook event")
    cwd = Path(payload["cwd"])
    if not cwd.is_absolute():
        raise ValueError("cwd must be absolute")
    under(root, cwd)
    sessions = (Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "sessions"
                if trusted_sessions is None else Path(trusted_sessions))
    transcript = Path(payload["transcript_path"])
    if not transcript.is_absolute():
        raise ValueError("Transcript must be absolute")
    transcript = under(sessions, transcript)
    with transcript.open("rb") as handle:
        first = handle.readline(2 * 1024 * 1024)
        if not first.endswith(b"\n"):
            raise ValueError("Incomplete metadata")
        meta_record = json.loads(first)
        if not isinstance(meta_record, dict) or meta_record.get("type") != "session_meta":
            raise ValueError("Missing session metadata")
        meta = meta_record["payload"]
        if not isinstance(meta, dict):
            raise ValueError("Invalid session metadata")
        if (meta.get("session_id", meta.get("id")) != payload["session_id"]
                or Path(meta["cwd"]).resolve() != cwd.resolve()):
            raise ValueError("Session/cwd mismatch")
        if (not isinstance(meta.get("source"), str) or meta["source"] not in ("cli", "exec", "vscode", "mcp")
                or meta.get("thread_source", "user") != "user" or meta.get("parent_thread_id")):
            raise ValueError("Subagent or unknown session origin")
        handle.seek(0, 2)
        size = handle.tell()
        start = max(0, size - MAX_TAIL)
        handle.seek(start)
        chunks = handle.read(MAX_TAIL).splitlines()
    if start:
        chunks = chunks[1:]
    latest_turn = None
    usage = None
    for line in chunks:
        try:
            record = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            continue
        if not isinstance(record, dict):
            continue
        body = record.get("payload", {})
        if not isinstance(body, dict):
            continue
        if record.get("type") == "turn_context":
            latest_turn = body
            usage = None
        elif record.get("type") == "event_msg" and body.get("type") == "token_count":
            usage = record
    if not latest_turn or latest_turn.get("turn_id") != payload["turn_id"]:
        raise ValueError("Missing or mismatched current turn")
    if Path(latest_turn.get("cwd", "")).resolve() != cwd.resolve() or not usage:
        raise ValueError("Missing matching current usage")
    timestamp = moment(usage["timestamp"])
    if not -5 <= now - timestamp <= MAX_AGE:
        raise ValueError("Stale or future usage")
    info = usage["payload"]["info"]
    used = info["last_token_usage"]["total_tokens"]
    window = info["model_context_window"]
    if type(used) is not int or used < 0 or type(window) is not int or window <= 0:
        raise ValueError("Invalid context measurement")
    return dict(session_id=payload["session_id"], turn_id=payload["turn_id"], used=used, window=window,
                usage_at=timestamp, ratio=used / window, transcript_path=str(transcript))


def reminder(state, directory, root):
    draft = under(directory, directory / ("draft-" + state["request_id"] + ".md"))
    final = under(directory, directory / ("checkpoint-" + state["request_id"] + ".md"))
    base = [sys.executable, str(Path(root) / "runtime/context_checkpoint.py"), "commit",
            "--session-id", state["session_id"], "--turn-id", state["turn_id"],
            "--request-id", state["request_id"], "--checkpoint", str(draft)]
    command = subprocess.list2cmdline(base)
    retry_note = (f"Pending summary reminder {state['reminder_count']}/{MAX_REMINDERS}. "
                  if state.get("reminder_count", 0) else "")
    headings = " / ".join(f"## {i}. {title}" for i, title in enumerate(HEADINGS, 1))
    return (retry_note + "This checkpoint request began when usage first exceeded 80%. "
            f"Current context usage is {state['used']}/{state['window']} ({state['ratio']:.1%}). "
            "Write a checkpoint at a safe boundary so the current task is not lost. "
            f"Save your own English Markdown summary to {draft}. Do not present transcript excerpts or this request itself as a completed summary. "
            f"Use these seven headings in order: {headings}. "
            "Preserve user goals, authorization, constraints, decisions, changed files and evidence, work in progress, unverified claims, and exact next steps. Do not include secrets. "
            f"The final handoff path is {final}; successful commit creates it. "
            "Only if both new_context and native notes are actually available and notes can retain that final path across the transition, save notes successfully and then run " + command +
            " --new-context available --notes available --handoff-ref <actual-notes-reference>. "
            "Only after successful commit, invoke the actual new_context tool according to its schema. In the new context, recover the path from notes, read the Markdown, and continue the original task. "
            "Do not claim notes or transition success without verification. If either tool is unavailable or handoff is uncertain, run " + command +
            " --new-context unavailable --notes unavailable, record that limitation, and continue the original task in the current context. "
            "Never attempt hidden resets, rollout editing, or task duplication through a new Codex process.")



def on_hook(payload, root=ROOT, trusted_sessions=None, now=None):
    measured = measure(payload, root, trusted_sessions, now)
    directory = directory_for(root, measured["session_id"])
    state_path = directory / "state.json"
    with locked(directory) as acquired:
        if not acquired:
            return {}
        state = load_state(state_path)
        if (state and state.get("status") != "armed" and measured["ratio"] <= 0.5
                and measured["usage_at"] > state.get("usage_at", measured["usage_at"])):
            # Re-arm after measured reduction, including an exhausted request.
            atomic_json(state_path, dict(schema_version=1, status="armed",
                cycle=state.get("cycle", 1) + 1, previous_checkpoint={key: state[key] for key in
                ("checkpoint_path", "sha256", "status", "cycle") if key in state},
                rearm_reason="measured_current_usage_below_50_percent", restore_confirmed=False))
            return {}
        if state.get("status") in ("requested", "requested_exhausted"):
            notified = state.get("notified_turn_ids", [state["turn_id"]])
            if measured["turn_id"] in notified or state["status"] == "requested_exhausted":
                return {}
            count = state.get("reminder_count", 0) + 1
            state.update(measured, reminder_count=count, notified_turn_ids=notified + [measured["turn_id"]],
                         status="requested_exhausted" if count == MAX_REMINDERS else "requested")
            atomic_json(state_path, state)
            return {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                          "additionalContext": reminder(state, directory, root)}}
        if state and state.get("status") != "armed":
            return {}
        if measured["ratio"] <= 0.8:
            return {}
        state = dict(schema_version=1, status="requested", request_id=uuid.uuid4().hex,
                     cycle=state.get("cycle", 1), restore_confirmed=False, reminder_count=0,
                     notified_turn_ids=[measured["turn_id"]], **measured)
        atomic_json(state_path, state)
        return {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                      "additionalContext": reminder(state, directory, root)}}


def validate_markdown(data):
    if len(data) > MAX_MARKDOWN:
        raise ValueError("Checkpoint is too large")
    text = data.decode("utf-8-sig").replace("\r\n", "\n")
    found = re.findall(r"^## (.+)$", text, re.MULTILINE)
    allowed = [[f"{i}. {title}" for i, title in enumerate(titles, 1)]
               for titles in (HEADINGS, LEGACY_HEADINGS)]
    if found not in allowed:
        raise ValueError("Checkpoint requires exactly the seven ordered headings")
    pieces = re.split(r"^## [1-7]\. .+$", text, flags=re.MULTILINE)[1:]
    if len(text.strip()) < 200 or any(not piece.strip() for piece in pieces):
        raise ValueError("Checkpoint sections need substantive content")
    return text


def commit(root, session_id, turn_id, request_id, checkpoint, new_context, notes, handoff_ref=""):
    validate_request_id(request_id)
    directory = directory_for(root, session_id)
    state_path = directory / "state.json"
    with locked(directory) as acquired:
        if not acquired:
            raise ValueError("Checkpoint is busy; keep current context")
        state = load_state(state_path)
        if (state.get("session_id") != session_id or state.get("turn_id") != turn_id
                or state.get("request_id") != request_id
                or state.get("status") not in ("requested", "requested_exhausted")):
            raise ValueError("No matching pending checkpoint request")
        file = under(directory, checkpoint)
        with file.open("rb") as handle:
            data = handle.read(MAX_MARKDOWN + 1)
        text = validate_markdown(data)
        available = new_context == "available" and notes == "available" and bool(handoff_ref.strip())
        if new_context == "available" and notes == "available" and not handoff_ref.strip():
            raise ValueError("A successful native notes handoff reference is required")
        final = under(directory, directory / ("checkpoint-" + request_id + ".md"))
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=directory,
                                         prefix=".checkpoint-", suffix=".tmp", delete=False) as handle:
            temp = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, final)
        state.update(status="committed" if available else "unavailable", checkpoint_path=str(final),
                     sha256=hashlib.sha256(final.read_bytes()).hexdigest(),
                     validation="seven_section_structure_only", new_context=new_context, notes=notes,
                     handoff_ref=handoff_ref, transition_status="pending_native_tools" if available else "unavailable",
                     restore_confirmed=False, committed_at=datetime.now(timezone.utc).isoformat())
        atomic_json(state_path, state)
        return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command")
    commit_parser = subs.add_parser("commit")
    for name in ("session-id", "turn-id", "request-id", "checkpoint"):
        commit_parser.add_argument("--" + name, required=True)
    for name in ("new-context", "notes"):
        commit_parser.add_argument("--" + name, choices=("available", "unavailable"), required=True)
    commit_parser.add_argument("--handoff-ref", default="")
    args = parser.parse_args()
    if args.command == "commit":
        try:
            state = commit(ROOT, args.session_id, args.turn_id, args.request_id, args.checkpoint,
                           args.new_context, args.notes, args.handoff_ref)
            print(json.dumps({"ok": True, "status": state["status"], "checkpoint_path": state["checkpoint_path"],
                              "transition_status": state["transition_status"], "restore_confirmed": False}, ensure_ascii=True))
            return 0
        except (OSError, ValueError, KeyError, TypeError) as error:
            print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=True))
            return 2
    try:
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("Hook input is too large")
        result = on_hook(json.loads(raw))
    except (OSError, ValueError, KeyError, TypeError):
        result = {}
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
