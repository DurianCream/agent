"""Display the current Codex turn's local tool events. Python 3.11+, stdlib only."""

import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import re
import sys
import time
from uuid import UUID


MAX_LINE = 8 * 1024 * 1024
SIGNALS = {"pending": "🟡 결과 대기", "returned": "🟢 반환", "error": "🔴 오류",
           "loaded": "🔵 도구 선언", "unknown": "⚪ 결과 미확인"}


def name(value):
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,159}", value):
        return value
    return ""


def object_or_empty(value):
    return value if isinstance(value, dict) else {}


def session_file(thread_id):
    try:
        if not thread_id or str(UUID(thread_id)) != thread_id:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("현재 채팅 ID를 확인할 수 없습니다. --thread에 Codex 채팅 UUID를 지정하세요.") from None
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    base = (home / "sessions").resolve()
    files = list(base.glob(f"*/*/*/rollout-*-{thread_id}.jsonl"))
    if len(files) != 1 or not files[0].resolve().is_relative_to(base):
        raise ValueError("이 채팅과 일치하는 로컬 세션 기록 한 개를 찾을 수 없습니다.")
    return files[0]


def group(tool):
    if tool.startswith("mcp__"):
        return "MCP"
    if tool.startswith("collaboration.") or tool.rsplit(".", 1)[-1] in {
        "spawn_agent", "wait_agent", "send_input", "close_agent", "resume_agent",
    }:
        return "서브에이전트 도구"
    return "도구"


class Activity:
    def __init__(self, thread):
        self.thread = thread
        self.declared = set()
        self.calls = {}
        self.agents = set()
        self.usage = None
        self.turn = None
        self.skipped = 0
        self.previous = None
        self.inherited = False

    def consume(self, record):
        p = object_or_empty(record.get("payload"))
        typ = p.get("type")
        if record.get("type") == "session_meta":
            self.inherited = p.get("id") != self.thread
            return
        if self.inherited:
            if record.get("type") != "event_msg" or p.get("thread_id") != self.thread:
                return
            self.inherited = False
        if record.get("type") == "response_item":
            self.response(p, typ)
            return
        if record.get("type") != "event_msg" or p.get("thread_id", self.thread) != self.thread:
            return
        if typ in ("task_started", "turn_started"):
            if not p.get("turn_id") or self.turn != p["turn_id"]:
                if self.turn:
                    self.previous = (self.calls, self.usage, self.declared.copy(), self.agents, self.skipped)
                self.calls = {}
                self.agents = set()
                self.usage = None
                self.skipped = 0
            self.turn = p.get("turn_id")
        elif p.get("turn_id") and self.turn and p["turn_id"] != self.turn:
            return
        elif typ in ("task_complete", "turn_aborted"):
            for key, (tool, state) in self.calls.items():
                if state == "pending":
                    self.calls[key] = tool, "unknown"
        elif typ == "token_count":
            info = object_or_empty(p.get("info"))
            count = object_or_empty(info.get("last_token_usage")).get("input_tokens")
            if type(count) is int and count >= 0:
                self.usage = count
        elif typ in ("exec_command_end", "mcp_tool_call_end") and name(p.get("call_id")):
            key = p["call_id"]
            if typ == "exec_command_end":
                label = "exec_command"
                failed = type(p.get("exit_code")) is int and p["exit_code"] != 0
            else:
                invocation = object_or_empty(p.get("invocation"))
                if not name(invocation.get("server")) or not name(invocation.get("tool")):
                    return
                label = f"mcp__{invocation['server']}__{invocation['tool']}"
                result = object_or_empty(p.get("result"))
                failed = "Err" in result or object_or_empty(result.get("Ok")).get("isError") is True
            self.calls[key] = self.calls.get(key, (label,))[0], "error" if failed else "returned"
        elif typ in ("item_started", "item_completed"):
            item = object_or_empty(p.get("item"))
            category = name(item.get("type"))
            if category == "SubAgentActivity":
                path = item.get("agent_path")
                if isinstance(path, str) and len(path) <= 160 and re.fullmatch(r"(?:/[A-Za-z0-9_-]+)+", path):
                    self.agents.add(path)
                return
            label = {"CommandExecution": "exec_command", "FileChange": "apply_patch",
                     "WebSearch": "web_search"}.get(category)
            if category == "McpToolCall" and name(item.get("server")) and name(item.get("tool")):
                label = f"mcp__{item['server']}__{item['tool']}"
            if label and name(item.get("id")):
                state = "pending" if typ == "item_started" else "returned"
                if item.get("status") in ("failed", "declined", "denied", "error") or (
                    type(item.get("exit_code")) is int and item["exit_code"] != 0
                ) or item.get("error") or object_or_empty(item.get("result")).get("isError") is True:
                    state = "error"
                self.calls[item["id"]] = label, state

    def response(self, p, typ):
        if typ == "additional_tools" and isinstance(p.get("tools"), list):
            for tool in map(object_or_empty, p["tools"]):
                ns = name(tool.get("name"))
                if ns and isinstance(tool.get("tools"), list):
                    for member in map(object_or_empty, tool["tools"]):
                        if name(member.get("name")):
                            self.declared.add(f"{ns}.{member['name']}")
                elif ns:
                    self.declared.add(ns)
            return
        attrib = object_or_empty(p.get("internal_chat_message_metadata_passthrough"))
        if self.turn and attrib.get("turn_id") and self.turn != attrib["turn_id"]:
            return
        key = name(p.get("call_id"))
        if not key:
            return
        if typ in ("function_call", "custom_tool_call") and name(p.get("name")):
            tool = p["name"]
            ns = name(p.get("namespace"))
            if ns:
                tool = f"{ns}.{tool}"
            else:
                matches = [n for n in self.declared if n.endswith("." + tool)]
                if len(matches) == 1:
                    tool = matches[0]
            self.calls.setdefault(key, (tool, "pending"))
        elif typ in ("function_call_output", "custom_tool_call_output") and key in self.calls:
            tool, old_state = self.calls[key]
            result = object_or_empty(p.get("output"))
            state = "error" if result.get("isError") is True or old_state == "error" else "returned"
            self.calls[key] = tool, state

    def render(self, expand=False, previous=False):
        if previous and not self.previous:
            return "직전 턴의 도구 신호등\n\n직전 턴 기록 없음"
        calls, usage, declared, agents, skipped = self.previous if previous else (
            self.calls, self.usage, self.declared, self.agents, self.skipped)
        counts = defaultdict(Counter)
        for tool, status in calls.values():
            counts[tool][status] += 1
        lines = ["직전 턴의 도구 신호등" if previous else "현재 턴의 도구 신호등", ""]
        if not counts:
            lines.append("관측된 호출 없음")
        for tool in sorted(counts, key=lambda t: (group(t), t)):
            states = " · ".join(f"{signal} {counts[tool][key]}" for key, signal in SIGNALS.items()
                                if counts[tool][key])
            lines.append(f"{group(tool)}  {tool}  {states}")
        idle = sorted(declared - counts.keys())
        lines.append(f"🔵 선언이 관측된 도구 중 이번 턴 호출 미관측 {len(idle)}개")
        if expand:
            lines.extend(f"  {tool}" for tool in idle)
        if agents:
            lines.append("활동이 관측된 서브에이전트  " + ", ".join(sorted(agents)))
        lines += ["", "최근 모델 요청 입력 토큰  " +
                  (f"{usage:,}" if usage is not None else "미확인"),
                  "스킬·플러그인별 사용 여부 및 도구별 토큰 비용  미확인"]
        if skipped:
            lines.append(f"읽지 못한 이벤트 {skipped}개 · 일부 집계 누락 가능")
        return "\n".join(lines)


def consume_available(stream, model):
    while True:
        start = stream.tell()
        line = stream.readline(MAX_LINE + 1)
        if not line:
            return
        oversized = len(line) > MAX_LINE
        while oversized and line and not line.endswith(b"\n"):
            line = stream.readline(MAX_LINE + 1)
        if not line.endswith(b"\n"):
            stream.seek(start)  # The writer may still be appending this record.
            return
        if oversized:
            model.skipped += 1
            continue
        try:
            record = json.loads(line)
        except (ValueError, RecursionError):
            model.skipped += 1
            continue
        if isinstance(record, dict):
            model.consume(record)


def main():
    parser = argparse.ArgumentParser(description="현재 Codex 채팅의 도구 신호등")
    parser.add_argument("--thread", default=os.environ.get("CODEX_THREAD_ID"), help="조회할 채팅 UUID")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--watch", action="store_true", help="기록 추가 시 갱신 (Ctrl+C로 종료)")
    mode.add_argument("--previous", action="store_true", help="직전 턴 보기")
    parser.add_argument("--all", action="store_true", help="선언만 관측된 도구 이름 펼치기")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure") and not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        with session_file(args.thread).open("rb") as stream:
            header = object_or_empty(json.loads(stream.readline(MAX_LINE + 1)))
            if (header.get("type") != "session_meta" or
                    object_or_empty(header.get("payload")).get("id") != args.thread):
                raise ValueError("세션 기록의 채팅 ID가 일치하지 않습니다.")
            model = Activity(args.thread)
            previous = None
            while True:
                consume_available(stream, model)
                frame = model.render(args.all, args.previous)
                if frame != previous:
                    if previous is not None and sys.stdout.isatty():
                        print("\033[H\033[2J", end="")
                    print(frame, flush=True)
                    previous = frame
                if not args.watch:
                    return 0
                time.sleep(1)
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, RecursionError) as exc:
        reason = str(exc) if type(exc) is ValueError else "세션 파일을 읽을 수 없습니다."
        print(f"도구 신호등 · {reason}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
