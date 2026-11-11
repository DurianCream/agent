"""Checkpoint trigger, session trust, transaction and no-reset safety tests."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tempfile
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("context_checkpoint", SOURCE / "runtime/context_checkpoint.py")
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.scratch = (SOURCE / "work").resolve()
        self.scratch.mkdir(exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix="checkpoint-test-", dir=self.scratch)).resolve()
        self.addCleanup(self.cleanup)
        self.sessions = self.root / "trusted-sessions"
        self.sessions.mkdir()
        self.transcript = self.sessions / "rollout.jsonl"
        self.now = datetime(2026, 10, 27, 9, tzinfo=timezone.utc).timestamp()
        self.input = dict(hook_event_name="PostToolUse", session_id="session-1234", turn_id="turn-1234",
                          cwd=str(self.root), transcript_path=str(self.transcript))
        self.write_rollout(801)

    def cleanup(self):
        resolved = self.root.resolve()
        if not resolved.is_relative_to(self.scratch) or not resolved.name.startswith("checkpoint-test-"):
            raise RuntimeError("Unsafe cleanup")
        shutil.rmtree(resolved)

    def write_rollout(self, used, window=1000, cumulative=400000000, age=0, source="cli", turn="turn-1234"):
        stamp = datetime.fromtimestamp(self.now - age, timezone.utc).isoformat()
        self.records = [
            {"type": "session_meta", "payload": {"id": "session-1234", "cwd": str(self.root),
                                                 "source": source, "thread_source": "user"}},
            {"type": "turn_context", "payload": {"turn_id": turn, "cwd": str(self.root)}},
            {"timestamp": stamp, "type": "event_msg", "payload": {"type": "token_count", "info": {
                "last_token_usage": {"total_tokens": used}, "model_context_window": window,
                "total_token_usage": {"total_tokens": cumulative}}}},
        ]
        self.save_records()

    def save_records(self):
        self.transcript.write_text("".join(json.dumps(r) + "\n" for r in self.records), encoding="utf-8")

    def run_hook(self, payload=None):
        return hook.on_hook(self.input if payload is None else payload, self.root, self.sessions, self.now)

    def pending(self):
        self.run_hook()
        directory = hook.directory_for(self.root, self.input["session_id"])
        return directory, hook.load_state(directory / "state.json")

    def markdown(self):
        return "# Context checkpoint\n\n" + "\n\n".join(
            f"## {i}. {title}\n\nCurrent task, decisions, evidence and exact next steps for section {i}."
            for i, title in enumerate(hook.HEADINGS, 1)) + "\n"

    def do_commit(self, directory, state, new_context="unavailable", notes="unavailable", ref=""):
        draft = directory / "draft.md"
        draft.write_text(self.markdown(), encoding="utf-8")
        return hook.commit(self.root, state["session_id"], state["turn_id"], state["request_id"],
                           draft, new_context, notes, ref)

    def test_uses_latest_current_window_not_cumulative_usage(self):
        self.write_rollout(30, cumulative=999999999)
        self.assertEqual(self.run_hook(), {})
        self.write_rollout(801, cumulative=10)
        output = self.run_hook()["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PostToolUse")
        self.assertIn("801/1000", output["additionalContext"])

    def test_exactly_eighty_percent_does_not_trigger(self):
        self.write_rollout(800)
        self.assertEqual(self.run_hook(), {})
        self.write_rollout(801)
        self.assertIn("hookSpecificOutput", self.run_hook())

    def test_denominator_is_measured_not_configured(self):
        self.write_rollout(206721, window=258400)
        self.assertIn("206721/258400", self.run_hook()["hookSpecificOutput"]["additionalContext"])

    def test_repeated_and_concurrent_hooks_request_once(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            outputs = list(pool.map(lambda _: self.run_hook(), range(8)))
        self.assertEqual(sum("hookSpecificOutput" in result for result in outputs), 1)
        self.assertEqual(self.run_hook(), {})

    def test_session_cwd_turn_and_transcript_path_must_match(self):
        for update in ({"session_id": "different-session"}, {"turn_id": "different-turn"},
                       {"cwd": str(self.root / "other")}, {"transcript_path": str(self.root / "outside.jsonl")}):
            with self.subTest(update=update), self.assertRaises((ValueError, OSError)):
                self.run_hook(dict(self.input, **update))

    def test_subagents_unknown_origins_and_stale_counts_are_rejected(self):
        for source in ("subagent", {"subagent": {"parent_thread_id": "parent"}}, "unknown"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.write_rollout(900, source=source)
                self.run_hook()
        self.write_rollout(900, age=121)
        with self.assertRaises(ValueError):
            self.run_hook()
        self.write_rollout(900, age=-6)
        with self.assertRaises(ValueError):
            self.run_hook()

    def test_missing_current_usage_does_not_reuse_previous_turn(self):
        self.records.append({"type": "turn_context", "payload": {"turn_id": "turn-1234", "cwd": str(self.root)}})
        self.save_records()
        with self.assertRaises(ValueError):
            self.run_hook()

    def test_invalid_measurements_are_rejected(self):
        for used, window in ((True, 1000), (900, False), (-1, 1000), (900, 0), (900.0, 1000)):
            with self.subTest(used=used, window=window), self.assertRaises(ValueError):
                self.write_rollout(used, window)
                self.run_hook()

    def test_commit_unavailable_preserves_markdown_and_current_work(self):
        directory, state = self.pending()
        before = self.transcript.read_bytes()
        committed = self.do_commit(directory, state)
        self.assertEqual(committed["status"], "unavailable")
        self.assertEqual(committed["transition_status"], "unavailable")
        self.assertFalse(committed["restore_confirmed"])
        file = Path(committed["checkpoint_path"])
        self.assertEqual(committed["sha256"], hashlib.sha256(file.read_bytes()).hexdigest())
        self.assertEqual(self.transcript.read_bytes(), before)
        self.assertEqual(self.run_hook(), {})

    def test_native_transition_requires_notes_handoff_and_never_claims_restore(self):
        directory, state = self.pending()
        with self.assertRaises(ValueError):
            self.do_commit(directory, state, "available", "available")
        committed = self.do_commit(directory, state, "available", "available", "native-note-123")
        self.assertEqual(committed["transition_status"], "pending_native_tools")
        self.assertFalse(committed["restore_confirmed"])

    def test_new_context_without_native_notes_is_unavailable(self):
        directory, state = self.pending()
        committed = self.do_commit(directory, state, "available", "unavailable")
        self.assertEqual(committed["status"], "unavailable")

    def test_commit_rejects_outside_file_and_mismatched_request(self):
        directory, state = self.pending()
        outside = self.root / "outside.md"
        outside.write_text(self.markdown(), encoding="utf-8")
        with self.assertRaises(ValueError):
            hook.commit(self.root, state["session_id"], state["turn_id"], state["request_id"],
                        outside, "unavailable", "unavailable")
        with self.assertRaises(ValueError):
            hook.commit(self.root, state["session_id"], state["turn_id"], "wrong", outside,
                        "unavailable", "unavailable")
        self.assertEqual(hook.load_state(directory / "state.json")["status"], "requested")

    def test_markdown_structure_size_and_crlf(self):
        valid = self.markdown()
        self.assertIn("Basic Information", hook.validate_markdown(valid.replace("\n", "\r\n").encode()))
        invalid = [valid.replace("## 2.", "## 1."), valid + "\n## Extra\nText",
                   valid.replace("Current task, decisions, evidence and exact next steps for section 3.", ""),
                   "raw transcript", "x" * (hook.MAX_MARKDOWN + 1)]
        for value in invalid:
            with self.subTest(size=len(value)), self.assertRaises(ValueError):
                hook.validate_markdown(value.encode())

    def test_usage_reduction_rearms_but_is_not_restore_confirmation(self):
        directory, state = self.pending()
        self.do_commit(directory, state)
        self.now += 10
        self.write_rollout(200)
        self.assertEqual(self.run_hook(), {})
        armed = hook.load_state(directory / "state.json")
        self.assertEqual(armed["status"], "armed")
        self.assertFalse(armed["restore_confirmed"])
        self.now += 1
        self.write_rollout(900)
        self.assertIn("hookSpecificOutput", self.run_hook())

    def test_corrupt_state_and_existing_lock_fail_safe(self):
        directory = hook.directory_for(self.root, self.input["session_id"])
        with hook.locked(directory) as acquired:
            self.assertTrue(acquired)
            self.assertEqual(self.run_hook(), {})
        self.assertTrue((directory / ".lock").exists())
        (directory / "state.json").write_text("{broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.run_hook()

    def test_hook_cli_invalid_json_and_non_object_input_are_nonblocking(self):
        for value in ("{broken", "[]", "null", "42"):
            with self.subTest(value=value):
                completed = subprocess.run([sys.executable, str(SOURCE / "runtime/context_checkpoint.py")],
                                           input=value, text=True, encoding="utf-8", capture_output=True)
                self.assertEqual(completed.returncode, 0)
                self.assertEqual(json.loads(completed.stdout), {})

    def test_reminder_handoff_uses_final_checkpoint_path(self):
        output = self.run_hook()["hookSpecificOutput"]["additionalContext"]
        directory = hook.directory_for(self.root, self.input["session_id"])
        state = hook.load_state(directory / "state.json")
        final = directory / ("checkpoint-" + state["request_id"] + ".md")
        self.assertIn("The final handoff path is " + str(final), output)
        self.assertIn("Only after successful commit", output)

    def test_pending_summary_reminds_new_turn_once_and_commit_uses_latest_notice(self):
        directory, initial = self.pending()
        self.now += 1
        self.input["turn_id"] = "turn-0002"
        self.write_rollout(850, turn="turn-0002")
        reminder = self.run_hook()["hookSpecificOutput"]["additionalContext"]
        self.assertIn("reminder 1/3", reminder)
        self.assertIn("--turn-id turn-0002", reminder)
        self.assertEqual(self.run_hook(), {})
        with self.assertRaises(ValueError):
            self.do_commit(directory, initial)
        latest = hook.load_state(directory / "state.json")
        self.assertEqual(latest["turn_id"], "turn-0002")
        self.assertEqual(self.do_commit(directory, latest)["status"], "unavailable")

    def test_pending_summary_stops_after_three_reminders_with_explicit_state(self):
        directory, state = self.pending()
        for count in range(1, 4):
            self.now += 1
            turn = f"turn-{count + 1:04d}"
            self.input["turn_id"] = turn
            self.write_rollout(900, turn=turn)
            self.assertIn("hookSpecificOutput", self.run_hook())
            self.assertEqual(self.run_hook(), {})
        state = hook.load_state(directory / "state.json")
        self.assertEqual(state["reminder_count"], 3)
        self.assertEqual(state["status"], "requested_exhausted")
        self.now += 1
        self.input["turn_id"] = "turn-0005"
        self.write_rollout(950, turn="turn-0005")
        self.assertEqual(self.run_hook(), {})
        self.assertEqual(self.do_commit(directory, state)["status"], "unavailable")

    def test_tampered_state_and_matching_cli_request_cannot_escape_directory(self):
        directory, state = self.pending()
        draft = directory / "draft.md"
        draft.write_text(self.markdown(), encoding="utf-8")
        for malicious in ("../outside", "../" * 12 + "outside", "a" * 31, "g" * 32):
            with self.subTest(request=malicious):
                changed = dict(state, request_id=malicious)
                hook.atomic_json(directory / "state.json", changed)
                with self.assertRaises(ValueError):
                    hook.load_state(directory / "state.json")
                with self.assertRaises(ValueError):
                    hook.commit(self.root, state["session_id"], state["turn_id"], malicious,
                                draft, "unavailable", "unavailable")
        self.assertFalse((self.root / "outside.md").exists())
        for update in ({"cycle": True}, {"status": "unknown"}, {"usage_at": float("nan")},
                       {"notified_turn_ids": [state["turn_id"], state["turn_id"]]},
                       {"reminder_count": 4}, {"checkpoint_path": str(self.root / "outside.md"), "sha256": "a" * 64}):
            with self.subTest(update=update):
                hook.atomic_json(directory / "state.json", dict(state, **update))
                with self.assertRaises(ValueError):
                    hook.load_state(directory / "state.json")

    def test_os_lock_releases_after_process_is_forcefully_terminated(self):
        directory = hook.directory_for(self.root, self.input["session_id"])
        marker = directory / "lock-held"
        child = (
            "import importlib.util,os,pathlib,sys,time\n"
            "s=importlib.util.spec_from_file_location('lock_child',sys.argv[1])\n"
            "m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\n"
            "with m.locked(pathlib.Path(sys.argv[2])) as acquired:\n"
            " pathlib.Path(sys.argv[3]).write_text(str(acquired)+':'+str(os.getpid()));time.sleep(30)\n")
        # Windows venv launchers have a different PID from the lock-holder.
        # Kill/wait must target the actual interpreter for the release assertion.
        interpreter = getattr(sys, "_base_executable", sys.executable) if os.name == "nt" else sys.executable
        process = subprocess.Popen([interpreter, "-c", child, str(SOURCE / "runtime/context_checkpoint.py"),
                                    str(directory), str(marker)], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            deadline = time.monotonic() + 10
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(marker.exists(), process.stderr.read().decode() if process.poll() is not None else "Lock child timed out")
            self.assertEqual(marker.read_text(), "True:" + str(process.pid))
            with hook.locked(directory) as acquired:
                self.assertFalse(acquired)
            process.kill()
            process.wait(timeout=5)
            self.assertTrue((directory / ".lock").exists())
            with hook.locked(directory) as acquired:
                self.assertTrue(acquired)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            process.stderr.close()

    def test_long_turn_older_than_four_mib_is_measured_within_bounded_scan(self):
        self.records.insert(2, {"type": "response_item", "payload": {"text": "x" * (8 * 1024 * 1024)}})
        self.save_records()
        measured = hook.measure(self.input, self.root, self.sessions, self.now)
        self.assertEqual((measured["used"], measured["window"]), (801, 1000))
        self.assertEqual(hook.MAX_TAIL, 64 * 1024 * 1024)

    @unittest.skipUnless(hook.os.name == "nt", "Windows mkdir race handling")
    def test_windows_directory_creation_retries_transient_access_denied(self):
        original = Path.mkdir
        target = self.root / "work/context-checkpoints" / hashlib.sha256(self.input["session_id"].encode()).hexdigest()[:24]
        seen = []
        def once(path, *args, **kwargs):
            if path == target:
                seen.append(path)
                if len(seen) == 1:
                    raise PermissionError(13, "concurrent creation")
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, "mkdir", new=once), mock.patch.object(hook.time, "sleep") as sleep:
            self.assertEqual(hook.directory_for(self.root, self.input["session_id"]), target)
        self.assertGreaterEqual(len(seen), 2)
        sleep.assert_called_once_with(0.01)

    @unittest.skipUnless(hook.os.name == "nt", "Windows mkdir race handling")
    def test_windows_existing_directory_is_accepted_after_access_denied(self):
        target = hook.directory_for(self.root, self.input["session_id"])
        original = Path.mkdir
        def denied(path, *args, **kwargs):
            if path == target:
                raise PermissionError(13, "another creator won")
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, "mkdir", new=denied), mock.patch.object(hook.time, "sleep") as sleep:
            self.assertEqual(hook.directory_for(self.root, self.input["session_id"]), target)
        sleep.assert_not_called()

    @unittest.skipUnless(hook.os.name == "nt", "Windows mkdir race handling")
    def test_windows_real_directory_permission_error_is_not_hidden(self):
        denied = PermissionError(13, "actual permission denied")
        with mock.patch.object(Path, "mkdir", side_effect=denied) as mkdir, mock.patch.object(hook.time, "sleep") as sleep:
            with self.assertRaises(PermissionError) as result:
                hook.directory_for(self.root, self.input["session_id"])
        self.assertIs(result.exception, denied)
        self.assertEqual(mkdir.call_count, 4)
        self.assertEqual(sleep.call_count, 3)

    def test_low_current_usage_rearms_pending_and_exhausted_requests_first(self):
        directory, initial = self.pending()
        for status in ("requested", "requested_exhausted"):
            with self.subTest(status=status):
                state = dict(initial, status=status)
                if status == "requested_exhausted":
                    state.update(reminder_count=3, turn_id="turn-0004", notified_turn_ids=["turn-1234", "turn-0002", "turn-0003", "turn-0004"])
                hook.atomic_json(directory / "state.json", state)
                self.now += 1
                self.input["turn_id"] = "turn-0005"
                self.write_rollout(200, turn="turn-0005")
                self.assertEqual(self.run_hook(), {})
                armed = hook.load_state(directory / "state.json")
                self.assertEqual(armed["status"], "armed")
                self.assertFalse(armed["restore_confirmed"])

    def test_retry_separates_initial_threshold_from_current_lower_ratio(self):
        self.pending()
        self.now += 1
        self.input["turn_id"] = "turn-0002"
        self.write_rollout(700, turn="turn-0002")
        message = self.run_hook()["hookSpecificOutput"]["additionalContext"]
        self.assertIn("first exceeded 80%", message)
        self.assertIn("700/1000 (70.0%)", message)
        self.assertNotIn("current usage exceeds 80%", message)

    def test_english_prompt_and_legacy_checkpoint_compatibility(self):
        message = self.run_hook()["hookSpecificOutput"]["additionalContext"]
        self.assertIn("English Markdown", message)
        self.assertIn("## 7. Unresolved Issues and Next Actions", message)
        legacy = self.markdown()
        for current, old in zip(hook.HEADINGS, hook.LEGACY_HEADINGS):
            legacy = legacy.replace(current, old)
        self.assertEqual(hook.validate_markdown(legacy.encode("utf-8")), legacy)
        mixed = legacy.replace(hook.LEGACY_HEADINGS[0], hook.HEADINGS[0])
        with self.assertRaises(ValueError):
            hook.validate_markdown(mixed.encode("utf-8"))

    def test_cp949_stdout_preserves_hook_and_commit_json_unicode(self):
        project = self.root / "한글프로젝트"
        (project / "runtime").mkdir(parents=True)
        script = project / "runtime/context_checkpoint.py"
        shutil.copyfile(SOURCE / "runtime/context_checkpoint.py", script)
        native_home = self.root / "native-home"
        sessions = native_home / "sessions"
        sessions.mkdir(parents=True)
        self.now = datetime.now(timezone.utc).timestamp()
        self.write_rollout(801)
        self.records[0]["payload"]["cwd"] = str(project)
        self.records[1]["payload"]["cwd"] = str(project)
        self.save_records()
        transcript = sessions / "rollout.jsonl"
        shutil.copyfile(self.transcript, transcript)
        payload = dict(self.input, cwd=str(project), transcript_path=str(transcript))
        environment = dict(os.environ, CODEX_HOME=str(native_home), PYTHONIOENCODING="cp949", PYTHONUTF8="0")
        completed = subprocess.run([sys.executable, str(script)], input=json.dumps(payload).encode("ascii"),
                                   capture_output=True, env=environment)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        response = json.loads(completed.stdout.decode("ascii"))
        directory = hook.directory_for(project, payload["session_id"])
        state = hook.load_state(directory / "state.json")
        self.assertEqual(response["hookSpecificOutput"]["additionalContext"], hook.reminder(state, directory, project))
        self.assertIn("한글프로젝트", response["hookSpecificOutput"]["additionalContext"])
        arguments = [sys.executable, str(script), "commit", "--session-id", state["session_id"],
                     "--turn-id", state["turn_id"], "--request-id", state["request_id"],
                     "--new-context", "unavailable", "--notes", "unavailable", "--checkpoint"]
        missing = directory / "없는요약.md"
        failed = subprocess.run(arguments + [str(missing)], capture_output=True, env=environment)
        self.assertEqual(failed.returncode, 2)
        error = json.loads(failed.stdout.decode("ascii"))
        self.assertIn("없는요약.md", error["error"])
        draft = directory / "모델요약.md"
        markdown = self.markdown() + "\n다음 단계와 결정 보존 😀\n"
        draft.write_text(markdown, encoding="utf-8")
        committed = subprocess.run(arguments + [str(draft)], capture_output=True, env=environment)
        self.assertEqual(committed.returncode, 0, committed.stderr)
        result = json.loads(committed.stdout.decode("ascii"))
        self.assertEqual(Path(result["checkpoint_path"]).read_text(encoding="utf-8"), markdown)


if __name__ == "__main__":
    unittest.main()
