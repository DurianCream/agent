import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "shared/skills/traffic-light/scripts/traffic_light.py"
spec = importlib.util.spec_from_file_location("traffic_light", SCRIPT)
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)
THREAD = "12345678-1234-1234-1234-123456789012"


def event(kind, **fields):
    return {"type": "event_msg", "payload": {"type": kind, **fields}}


def item(kind, **fields):
    return {"type": "response_item", "payload": {"type": kind, **fields}}


def data(*rows):
    return b"".join(json.dumps(row).encode() + b"\n" for row in rows)


class TrafficLightTests(unittest.TestCase):
    def test_correlates_states_and_previous_turn(self):
        m = monitor.Activity(THREAD)
        rows = [
            event("task_started", turn_id="first"),
            item("additional_tools", tools=[{"name": "functions", "tools": [{"name": "run"}, {"name": "wait"}]}]),
            item("function_call", call_id="a", name="run", arguments="PRIVATE_COMMAND"),
            event("exec_command_end", call_id="a", exit_code=1),
            item("function_call_output", call_id="a", output="PRIVATE_RESULT"),
            item("custom_tool_call", call_id="b", name="read"),
            item("function_call", call_id="c", name="read"),
            item("function_call_output", call_id="c", output="done"),
            event("token_count", info={"last_token_usage": {"input_tokens": 4500}}),
            event("item_completed", item={"type": "SubAgentActivity", "agent_path": "/root/review"}),
        ]
        for row in rows:
            m.consume(row)
        self.assertEqual(m.calls, {"a": ("functions.run", "error"), "b": ("read", "pending"), "c": ("read", "returned")})
        m.consume(event("turn_aborted", turn_id="first"))
        m.consume(event("task_started", turn_id="second"))
        rendered = m.render(expand=True, previous=True)
        for piece in ("직전 턴", "functions.wait", "🔴 오류 1", "🟢 반환 1", "⚪ 결과 미확인 1", "4,500", "/root/review"):
            self.assertIn(piece, rendered)
        self.assertNotIn("PRIVATE", rendered)
        self.assertNotIn("4,500", m.render())
        self.assertNotIn("/root/review", m.render())
        self.assertEqual(m.calls, {})

    def test_structured_events_and_foreign_inherited_history(self):
        m = monitor.Activity(THREAD)
        for row in [
            {"type": "session_meta", "payload": {"id": "parent"}},
            item("function_call", call_id="parent", name="foreign"),
            event("thread_settings_applied", thread_id=THREAD),
            event("task_started", turn_id="own"),
            event("item_completed", item={"id": "cmd", "type": "CommandExecution", "exit_code": 3}),
            event("item_completed", item={"id": "mcp", "type": "McpToolCall", "server": "demo", "tool": "list",
                                          "result": {"isError": True}}),
            event("item_completed", thread_id="other", item={"id": "other", "type": "CommandExecution"}),
            item("function_call", call_id="bad", name="line\nbreak"),
        ]:
            m.consume(row)
        self.assertEqual(m.calls, {"cmd": ("exec_command", "error"), "mcp": ("mcp__demo__list", "error")})
        self.assertIsNone(m.previous)

    def test_appended_partial_record_and_invalid_line(self):
        m = monitor.Activity(THREAD)
        row = data(item("custom_tool_call", call_id="demo", name="safe_tool"))
        stream = io.BytesIO(b"malformed\n" + row[:-2])
        monitor.consume_available(stream, m)
        self.assertEqual((m.calls, m.skipped), ({}, 1))
        pos = stream.tell()
        stream.seek(0, 2)
        stream.write(row[-2:])
        stream.seek(pos)
        monitor.consume_available(stream, m)
        self.assertEqual(m.calls["demo"], ("safe_tool", "pending"))

    def test_cli_selects_only_requested_thread_and_rejects_mismatched_header(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "sessions/2030/01/01"
            folder.mkdir(parents=True)
            path = folder / f"rollout-now-{THREAD}.jsonl"
            env = dict(os.environ, CODEX_HOME=directory, CODEX_THREAD_ID=THREAD, PYTHONIOENCODING="utf-8")
            def run(*args):
                return subprocess.run([sys.executable, str(SCRIPT), *args], env=env,
                                      capture_output=True, encoding="utf-8", timeout=10)
            meta = {"type": "session_meta", "payload": {"id": THREAD}}
            path.write_bytes(data(meta, event("task_started", turn_id="one"),
                                  item("function_call", call_id="one", name="example")))
            self.assertIn("example", run().stdout)
            self.assertEqual(run("--thread", "../..").returncode, 2)
            meta["payload"]["id"] = "wrong"
            path.write_bytes(data(meta, item("function_call", call_id="one", name="PRIVATE")))
            invalid = run()
            self.assertEqual(invalid.returncode, 2)
            self.assertNotIn("PRIVATE", invalid.stdout + invalid.stderr)
