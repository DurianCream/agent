#!/usr/bin/env python3
"""Local module registry, pinned task records, and common result submission.

No LLM, shell executor, credential broker, or operating-system sandbox is included.
The schema validator deliberately supports only the keywords used in this repo.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.2.0"
ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SCHEMA_KEYS = {
    "$schema", "$id", "title", "description", "type", "required", "properties",
    "additionalProperties", "items", "minItems", "minLength", "pattern",
    "enum", "const", "format",
}
HEADINGS = (
    "기본 정보", "목표와 완료 기준", "결과 요약", "수행 내용", "산출물",
    "검증 결과", "미해결 사항과 후속 조치",
)
LABELS = {
    "completed": "완료", "partial": "부분 완료", "blocked": "차단", "failed": "실패",
    "passed": "통과", "not_run": "미실행", "not_applicable": "해당 없음",
}


class ContractError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def now():
    return datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identifier(value):
    require(isinstance(value, str) and bool(ID.fullmatch(value)), f"Invalid ID: {value!r}")
    reserved = {"con", "prn", "aux", "nul"} | {f"{p}{i}" for p in ("com", "lpt") for i in range(1, 10)}
    require(value not in reserved, f"Reserved filesystem ID: {value}")
    return value


def relative(base, value, *, file=False):
    """Resolve canonical portable paths and reject traversal, drives, and escapes."""
    require(isinstance(value, str) and bool(value), "A relative path is required")
    require("\\" not in value and ":" not in value and "\0" not in value,
            f"Non-canonical path: {value}")
    parts = value.rstrip("/").split("/")
    require(all(p not in ("", ".", "..") for p in parts), f"Unsafe path: {value}")
    require(not value.startswith("/"), f"Absolute path is not allowed: {value}")
    base = Path(base).resolve()
    current = base
    for part in parts:
        current = current / part
        require(not current.is_symlink() and not getattr(current, "is_junction", lambda: False)(),
                f"Linked paths are not supported: {value}")
    dest = current.resolve()
    require(dest.is_relative_to(base) and dest != base, f"Path escapes root: {value}")
    if file:
        require(not value.endswith("/"), f"File path must not end with /: {value}")
        require(dest.is_file(), f"Missing file: {value}")
    return dest


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(file):
    def invalid_constant(value):
        raise ContractError(f"Invalid JSON constant: {value}")
    return json.loads(Path(file).read_text(encoding="utf-8-sig"),
                      object_pairs_hook=unique_pairs, parse_constant=invalid_constant)


def atomic_text(file, text):
    file = Path(file)
    file.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".agentctl-", dir=file.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temp, file)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def write_json(file, value):
    atomic_text(file, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


@contextmanager
def lock(file):
    file = Path(file)
    file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with file.open("x", encoding="utf-8") as stream:
            stream.write(str(os.getpid()))
    except FileExistsError:
        raise ContractError(f"Another operation holds {file.name}; inspect the owner before removing it")
    try:
        yield
    finally:
        file.unlink()


def check_schema(schema, at="$"):
    require(isinstance(schema, dict), f"{at}: schema must be an object")
    require(not (set(schema) - SCHEMA_KEYS),
            f"{at}: unsupported schema keywords: {sorted(set(schema) - SCHEMA_KEYS)}")
    if "format" in schema:
        require(schema["format"] == "date-time", f"{at}: unsupported format")
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        require(types and all(t in ("object", "array", "string", "boolean", "integer", "number", "null")
                              for t in types), f"{at}: unsupported type")
    if "additionalProperties" in schema:
        require(isinstance(schema["additionalProperties"], bool), f"{at}: boolean additionalProperties required")
    if "pattern" in schema:
        re.compile(schema["pattern"])
    for key, child in schema.get("properties", {}).items():
        check_schema(child, f"{at}.{key}")
    if "items" in schema:
        check_schema(schema["items"], f"{at}[]")


def validate_data(value, schema, at="$"):
    check_schema(schema, at)
    if "const" in schema:
        require(type(value) is type(schema["const"]) and value == schema["const"], f"{at}: unexpected constant")
    if "enum" in schema:
        require(any(type(value) is type(v) and value == v for v in schema["enum"]), f"{at}: invalid enum value")
    tests = {
        "object": lambda v: isinstance(v, dict),
        "array": lambda v: isinstance(v, list),
        "string": lambda v: isinstance(v, str),
        "boolean": lambda v: isinstance(v, bool),
        "integer": lambda v: type(v) is int,
        "number": lambda v: type(v) in (int, float),
        "null": lambda v: v is None,
    }
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        require(any(tests[t](value) for t in types), f"{at}: expected {types}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        missing = set(schema.get("required", [])) - set(value)
        require(not missing, f"{at}: missing fields {sorted(missing)}")
        if schema.get("additionalProperties") is False:
            require(not (set(value) - set(props)), f"{at}: unknown fields {sorted(set(value) - set(props))}")
        for key, item in value.items():
            if key in props:
                validate_data(item, props[key], f"{at}.{key}")
    if isinstance(value, list):
        require(len(value) >= schema.get("minItems", 0), f"{at}: too few items")
        if "items" in schema:
            for i, item in enumerate(value):
                validate_data(item, schema["items"], f"{at}[{i}]")
    if isinstance(value, str):
        require(len(value.strip()) >= schema.get("minLength", 0), f"{at}: empty or too short")
        if "pattern" in schema:
            require(re.search(schema["pattern"], value) is not None, f"{at}: invalid pattern")
        if schema.get("format") == "date-time":
            try:
                require(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
                                     value) is not None, f"{at}: invalid date-time format")
                stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
                require("T" in value and stamp.utcoffset() is not None, f"{at}: timezone is required")
            except ValueError:
                raise ContractError(f"{at}: invalid timezone-aware date-time")


def validate_named(value, name, root=ROOT):
    validate_data(value, read_json(relative(root, f"shared/schemas/{name}.schema.json", file=True)))


def skill_inventory(root):
    inventory = read_json(relative(root, "shared/skills/skills.json", file=True))
    require(set(inventory) == {"schema_version", "skills"} and inventory["schema_version"] == "1.0.0",
            "Invalid skill inventory")
    items = {}
    for skill in inventory["skills"]:
        require(set(skill) == {"id", "version", "path"}, "Invalid skill reference")
        identifier(skill["id"])
        require(skill["id"] not in items, f"Duplicate skill: {skill['id']}")
        require(re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", skill["version"]), "Invalid skill version")
        text = relative(root, skill["path"], file=True).read_text(encoding="utf-8")
        match = re.match(r"\A---\r?\nname: ([a-z0-9-]+)\r?\ndescription: ([^\r\n]+)\r?\n---(?:\r?\n|$)", text)
        require(match is not None and match[1] == skill["id"], f"Invalid skill frontmatter: {skill['id']}")
        require(bool(match[2].strip()) and len(match[2]) <= 1024, "Invalid skill description")
        require("[TODO:" not in text, f"Unfinished skill: {skill['id']}")
        items[skill["id"]] = skill
    return items


def load_registry(root=ROOT, candidate=None):
    root = Path(root)
    registry = candidate if candidate is not None else read_json(relative(root, "registry.json", file=True))
    validate_named(registry, "registry", root)
    inventory = skill_inventory(root)
    modules = {}
    paths = set()
    for entry in registry["modules"]:
        require(entry["id"] not in modules, f"Duplicate module: {entry['id']}")
        require(entry["path"] not in paths, f"Duplicate module path: {entry['path']}")
        require(entry["path"].startswith(("core/", "modules/")) and entry["path"].endswith("/module.json"),
                "Module must live in core/<id>/ or modules/<id>/")
        paths.add(entry["path"])
        manifest = read_json(relative(root, entry["path"], file=True))
        validate_named(manifest, "module", root)
        require(manifest["id"] == entry["id"], "Registry ID differs from manifest")
        expected = f"{'core' if manifest['kind'] == 'system' else 'modules'}/{manifest['id']}/"
        require(entry["path"] == expected + "module.json", "Module path differs from kind/ID")
        require(manifest["instructions"].startswith(expected), "Instructions must belong to their module")
        relative(root, manifest["instructions"], file=True)
        for group in manifest["scope"].values():
            for scope in group:
                relative(root, scope)
        require(len({s["id"] for s in manifest["skills"]}) == len(manifest["skills"]), "Duplicate module skill")
        for skill in manifest["skills"]:
            require(inventory.get(skill["id"]) == skill, f"Skill version/path mismatch: {skill['id']}")
        require(any(s["id"] == "submit-result" for s in manifest["skills"]), "Common submission skill required")
        require(len({p["id"] for p in manifest["policies"]}) == len(manifest["policies"]), "Duplicate policy")
        require(any(p["id"] == "common" for p in manifest["policies"]), "Common policy required")
        for policy_ref in manifest["policies"]:
            if policy_ref["id"] == "common":
                require(policy_ref["path"] == "shared/policies/common.json", "Common policy path must be canonical")
            policy = read_json(relative(root, policy_ref["path"], file=True))
            validate_named(policy, "policy", root)
            require((policy["id"], policy["version"]) == (policy_ref["id"], policy_ref["version"]),
                    "Policy version/path mismatch")
            require(policy["result_contract"] == manifest["result_contract"], "Result contract conflicts with policy")
        contract = manifest["result_contract"]
        require(contract["version"] == "1.0.0" and contract["path"] == "shared/schemas/result.schema.json",
                "Unsupported result contract version")
        check_schema(read_json(relative(root, contract["path"], file=True)))
        modules[entry["id"]] = {"entry": entry, "manifest": manifest}
    visited, stack = set(), set()

    def visit(name):
        require(name not in stack, f"Cyclic module dependency: {name}")
        if name in visited:
            return
        stack.add(name)
        refs = modules[name]["manifest"]["dependencies"]
        require(len({r["id"] for r in refs}) == len(refs), "Duplicate dependency")
        for dep in refs:
            require(dep["id"] in modules, f"Missing dependency: {dep['id']}")
            target = modules[dep["id"]]
            require(target["manifest"]["version"] == dep["version"], "Dependency version mismatch")
            if modules[name]["entry"]["enabled"]:
                require(target["entry"]["enabled"], "Enabled module has a disabled dependency")
            visit(dep["id"])
        stack.remove(name)
        visited.add(name)
    for name in modules:
        visit(name)
    return registry, modules


def doctor(root=ROOT):
    for name in ("module", "registry", "policy", "result"):
        check_schema(read_json(relative(root, f"shared/schemas/{name}.schema.json", file=True)))
    _, modules = load_registry(root)
    return {"modules": len(modules), "skills": len(skill_inventory(root)),
            "result_contract": "1.0.0", "runtime_version": VERSION,
            "execution": "host", "schema_validation": "repository-supported-keywords"}


def event(run, kind, **fields):
    with (run / "events.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps({"at": now(), "event": kind, **fields}, ensure_ascii=False) + "\n")


def init_task(module, task_id, objective, criteria, root=ROOT):
    root = Path(root).resolve()
    identifier(task_id)
    require(bool(objective.strip()) and criteria and all(c.strip() for c in criteria),
            "Objective and at least one nonempty criterion are required")
    registry, modules = load_registry(root)
    require(module in modules and modules[module]["entry"]["enabled"], "Module is not enabled")
    selected = modules[module]["manifest"]
    require(selected["lifecycle"] != "deprecated", "Cannot start a deprecated module")
    sources = {"AGENTS.md", "registry.json", "shared/skills/skills.json"}
    sources.update(f"shared/schemas/{name}.schema.json" for name in ("module", "registry", "policy", "result"))
    collected = set()

    def collect(name):
        if name in collected:
            return
        collected.add(name)
        manifest = modules[name]["manifest"]
        sources.update((modules[name]["entry"]["path"], manifest["instructions"]))
        sources.update(s["path"] for s in manifest["skills"])
        sources.update(p["path"] for p in manifest["policies"])
        for dep in manifest["dependencies"]:
            require(modules[dep["id"]]["manifest"]["lifecycle"] != "deprecated", "Deprecated dependency")
            collect(dep["id"])
    collect(module)
    contents = {name: relative(root, name, file=True).read_bytes() for name in sorted(sources)}
    run = relative(root, f"runs/{task_id}")
    output = relative(root, f"outputs/{task_id}")
    require(not run.exists() and not output.exists(), "Task/output ID already exists; use a new ID")
    run.mkdir(parents=True)
    output.mkdir(parents=True)
    (run / "evidence").mkdir()
    criteria_spec = [{"id": f"criterion-{i+1}", "description": c, "required": True}
                     for i, c in enumerate(criteria)]
    module_spec = {"id": module, "version": selected["version"]}
    snapshot = {"schema_version": "1.0.0", "report_paths": "repository-relative-v1", "module": module, "created_at": now(), "files": [],
                "task_spec": {"module": module_spec, "objective": objective, "criteria": criteria_spec},
                "versions": {
                    "modules": [{"id": name, "version": modules[name]["manifest"]["version"]}
                                for name in sorted(collected)],
                    "skills": sorted({(ref["id"], ref["version"]) for name in collected
                                      for ref in modules[name]["manifest"]["skills"]}),
                    "policies": sorted({(ref["id"], ref["version"]) for name in collected
                                        for ref in modules[name]["manifest"]["policies"]}),
                }}
    for name, data in contents.items():
        dest = relative(run, "snapshot/files/" + name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        snapshot["files"].append({"path": name, "sha256": digest(data)})
    write_json(run / "snapshot.json", snapshot)
    record = {
        "schema_version": "1.0.0", "task_id": task_id,
        "module": module_spec,
        "objective": objective, "created_at": now(), "state": "queued", "runtime_version": VERSION,
        "criteria": criteria_spec,
        "snapshot_sha256": digest((run / "snapshot.json").read_bytes()),
    }
    write_json(run / "task.json", record)
    result = {
        "schema_version": "1.0.0", "task_id": task_id, "module": record["module"],
        "created_at": now(), "objective": objective,
        "acceptance_criteria": [{**c, "verification_ids": []} for c in record["criteria"]],
        "status": "partial", "summary": "작업 진행 중.", "work": ["작업을 초기화했다."],
        "artifacts": [],
        "verification": [{"id": "check-1", "name": "완료 기준 검증", "method": "작업에 맞는 실제 검증",
                          "outcome": "not_run", "evidence": [], "notes": "아직 실행하지 않음"}],
        "sources": [], "limitations": ["완료 기준 검증 전"], "next_actions": ["작업과 검증 수행"],
    }
    write_json(run / "result.json", result)
    event(run, "created", module=module)
    return {"task_id": task_id, "state": "queued", "run": str(run), "output": str(output)}


def control_gate_call(action, task_id, root=ROOT, **kwargs):
    """Load optional P1 checks without making legacy framework copies depend on them.

    Local enrollment is a cooperative CLI boundary, not host authentication.
    Missing code must never turn an enrolled task back into a legacy task.
    """
    root = Path(root).resolve()
    identifier(task_id)
    run = relative(root, f"runs/{task_id}")
    task_file = relative(run, "task.json", file=True)
    task = read_json(task_file)
    signals = [run / "controls.json", root / "runs/control-enrollments" / (task_id + ".json")]
    enrolled = "control_enrollment" in task or any(p.exists() or p.is_symlink() for p in signals)
    configured = action == "enroll" and ((root / ".agent-work/gates.json").exists()
                                        or (root / ".agent-work/gates.json").is_symlink())
    def retain_pending():
        if configured:
            current = read_json(task_file)
            if "control_enrollment" not in current:
                current["control_enrollment"] = "pending"
                write_json(task_file, current)
    try:
        import control_gate
    except Exception as error:
        retain_pending()
        require(not enrolled and not configured, "P1 gate module unavailable; selected task is blocked")
        return None
    try:
        return getattr(control_gate, action)(task_id, root=root, **kwargs)
    except ContractError:
        retain_pending()
        raise
    except Exception as error:
        retain_pending()
        # Gate failures are blocking; do not expose arbitrary child exception text.
        raise ContractError("P1 gate check failed: " + type(error).__name__) from error


def load_task(task_id, root=ROOT):
    identifier(task_id)
    root = Path(root).resolve()
    run = relative(root, f"runs/{task_id}")
    task = read_json(relative(run, "task.json", file=True))
    require(task.get("task_id") == task_id and task.get("schema_version") == "1.0.0", "Task identity mismatch")
    snapfile = relative(run, "snapshot.json", file=True)
    require(digest(snapfile.read_bytes()) == task["snapshot_sha256"], "Snapshot manifest changed")
    snapshot = read_json(snapfile)
    require(snapshot["module"] == task["module"]["id"], "Snapshot module mismatch")
    require(snapshot["task_spec"] == {key: task[key] for key in ("module", "objective", "criteria")},
            "Task inputs differ from the pinned snapshot")
    paths = set()
    for item in snapshot["files"]:
        require(item["path"] not in paths, "Duplicate snapshot path")
        paths.add(item["path"])
        file = relative(run, "snapshot/files/" + item["path"], file=True)
        require(digest(file.read_bytes()) == item["sha256"], f"Snapshot file changed: {item['path']}")
    control_gate_call("check_enrollment", task_id, root)
    return run, task, snapshot


def transition(task_id, state, root=ROOT):
    run = relative(root, f"runs/{identifier(task_id)}")
    relative(run, "task.json", file=True)
    allowed = {"queued": {"running", "cancelled"}, "running": {"waiting", "cancelled"},
               "waiting": {"running", "cancelled"}, "submitted": set(), "cancelled": set()}
    with lock(run / ".operation.lock"):
        run, task, _ = load_task(task_id, root)
        require(state in allowed.get(task["state"], set()), f"Invalid transition: {task['state']} -> {state}")
        task["state"] = state
        write_json(run / "task.json", task)
        event(run, "transition", state=state)
    return {"task_id": task_id, "state": state}


def validate_result(task_id, root=ROOT, value=None):
    root = Path(root).resolve()
    run, task, snapshot = load_task(task_id, root)
    result = copy.deepcopy(value) if value is not None else read_json(relative(run, "result.json", file=True))
    pinned = run / "snapshot/files"
    validate_named(result, "result", pinned)
    require(result["task_id"] == task_id and result["module"] == task["module"], "Result identity/version mismatch")
    require(result["objective"] == task["objective"], "Result objective differs from task")
    baseline = [{k: c[k] for k in ("id", "description", "required")} for c in result["acceptance_criteria"]]
    require(baseline == task["criteria"], "Acceptance criteria differ from the task; start a new task to revise them")
    checks = {check["id"]: check for check in result["verification"]}
    require(len(checks) == len(result["verification"]), "Duplicate verification ID")
    criterion_ids = [c["id"] for c in result["acceptance_criteria"]]
    require(len(set(criterion_ids)) == len(criterion_ids), "Duplicate criterion ID")
    require(any(c["required"] for c in result["acceptance_criteria"]), "At least one required criterion is needed")
    for check in checks.values():
        if check["outcome"] in ("passed", "failed"):
            require(bool(check["evidence"]), f"Evidence required for {check['id']}")
        else:
            require(bool(check["notes"].strip()), f"Reason required for {check['id']}")
        require(len(set(check["evidence"])) == len(check["evidence"]), "Duplicate evidence")
        for evidence in check["evidence"]:
            file = relative(root, evidence, file=True)
            allowed = (f"runs/{task_id}/evidence/", f"outputs/{task_id}/")
            require(evidence.startswith(allowed), "Evidence must belong to this task")
            require(file.stat().st_size > 0, "Empty evidence file")
    for criterion in result["acceptance_criteria"]:
        refs = criterion["verification_ids"]
        require(len(set(refs)) == len(refs), "Duplicate criterion verification reference")
        require(all(ref in checks for ref in refs), "Unknown verification reference")
        if result["status"] == "completed" and criterion["required"]:
            require(refs and all(checks[ref]["outcome"] == "passed" for ref in refs),
                    f"Required criterion is not verified: {criterion['id']}")
    if result["status"] == "completed":
        require(not any(c["outcome"] in ("failed", "not_run") for c in checks.values()),
                "Completed result contains failed/unrun verification")
    else:
        require(bool(result["limitations"]), "Incomplete results must explain their limitations")
    policy = read_json(relative(pinned, "shared/policies/common.json", file=True))
    artifact_paths = set()
    reserved = {f"outputs/{task_id}/result.json", f"outputs/{task_id}/result.md"}
    for artifact in result["artifacts"]:
        name = artifact["path"]
        file = relative(root, name, file=True)
        require(name not in reserved, "Generated reports cannot list themselves as artifacts")
        require(any(name.startswith(prefix) for prefix in policy["allowed_artifact_roots"]),
                "Artifact is outside the allowed output roots")
        require(name not in artifact_paths, "Duplicate artifact")
        artifact_paths.add(name)
        if artifact["sha256"] is not None:
            require(digest(file.read_bytes()) == artifact["sha256"], f"Artifact hash mismatch: {name}")
    if result["status"] == "completed":
        require(bool(result["artifacts"]), "Completed artifact-producing task must include an artifact")
    for source in result["sources"]:
        url = urlsplit(source["url"])
        require(url.scheme in ("http", "https") and bool(url.netloc), "Source must be an HTTP(S) URL")
    if task["state"] == "submitted":
        receipt = task["submission"]
        require(digest((run / "result.json").read_bytes()) == receipt["result_sha256"],
                "Submitted result was changed")
        for name, expected in (("result.json", receipt["result_sha256"]), ("result.md", receipt["report_sha256"])):
            published = relative(root, f"outputs/{task_id}/{name}", file=True)
            require(digest(published.read_bytes()) == expected, f"Published {name} was changed")
        for evidence in receipt["evidence"]:
            file = relative(root, evidence["path"], file=True)
            require(digest(file.read_bytes()) == evidence["sha256"], "Submitted evidence was changed")
    control_gate_call("check_submission", task_id, root, result=result)
    return result, task, snapshot


def md(value):
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    for char in ("\\", "*", "_", "[", "]", "#", "|", chr(96), "<", ">"):
        text = text.replace(char, "\\" + char)
    return text.replace("\n", "<br>")


def file_link(root, name, portable=False):
    path = relative(root, name, file=True)
    # Both render destinations are two levels below the framework root.
    location = "../../" + path.relative_to(Path(root).resolve()).as_posix() if portable else path.as_posix()
    target = quote(location, safe="/:")
    return f"[{md(name)}](<{target}>)"


def report_text(result, task, snapshot, root=ROOT):
    portable = snapshot.get("report_paths") == "repository-relative-v1"
    lines = ["# 작업 결과", "", f"## 1. {HEADINGS[0]}", "",
             f"- 작업 ID: {md(result['task_id'])}",
             f"- 담당 모듈: {md(result['module']['id'])} / {md(result['module']['version'])}",
             f"- 결과 규격: {result['schema_version']}",
             f"- 작성 시각: {md(result['created_at'])}",
             f"- 고정 버전: snapshot {task['snapshot_sha256']} ({len(snapshot['files'])}개 파일)",
             "- 스킬 버전: " + ", ".join(md(f"{name}@{version}") for name, version in snapshot["versions"]["skills"]),
             "- 정책 버전: " + ", ".join(md(f"{name}@{version}") for name, version in snapshot["versions"]["policies"]),
             "", f"## 2. {HEADINGS[1]}", "", md(result["objective"]), ""]
    for criterion in result["acceptance_criteria"]:
        refs = ", ".join(criterion["verification_ids"]) or "미확인"
        lines.append(f"- {md(criterion['description'])} (검증: {md(refs)})")
    lines += ["", f"## 3. {HEADINGS[2]}", "",
              f"- 상태: {LABELS[result['status']]}", f"- 요약: {md(result['summary'])}",
              "", f"## 4. {HEADINGS[3]}", ""]
    lines += ["- " + md(item) for item in result["work"]]
    lines += ["", f"## 5. {HEADINGS[4]}", ""]
    lines += [f"- {file_link(root, a['path'], portable)}: {md(a['description'])}"
              + (f" (SHA-256: {a['sha256']})" if a["sha256"] else "") for a in result["artifacts"]] or ["해당 없음"]
    lines += ["", f"## 6. {HEADINGS[5]}", ""]
    for check in result["verification"]:
        lines.append(f"- {md(check['id'])} · {md(check['name'])}: {LABELS[check['outcome']]}")
        lines.append(f"  - 방법: {md(check['method'])}")
        links = ", ".join(file_link(root, name, portable) for name in check["evidence"]) or "미실행 또는 해당 없음"
        lines.append(f"  - 증거: {links}")
        lines.append(f"  - 비고: {md(check['notes']) if check['notes'] else '해당 없음'}")
    if result["sources"]:
        lines += ["", "**출처와 주장 구분**", ""]
        for source in result["sources"]:
            lines.append(f"- {md(source['title'])}: <{quote(source['url'], safe=':/?=&%#')}>"
                         f" ({source['claim_kind']}, {md(source['accessed_at'])})")
    lines += ["", f"## 7. {HEADINGS[6]}", "", "**미해결 사항·한계**", ""]
    lines += ["- " + md(item) for item in result["limitations"]] or ["해당 없음"]
    lines += ["", "**후속 조치**", ""]
    lines += ["- " + md(item) for item in result["next_actions"]] or ["해당 없음"]
    return "\n".join(lines) + "\n"


def render(task_id, root=ROOT):
    run = relative(root, f"runs/{identifier(task_id)}")
    relative(run, "task.json", file=True)
    with lock(run / ".operation.lock"):
        result, task, snapshot = validate_result(task_id, root)
        require(task["state"] not in ("submitted", "cancelled"), "Task is closed")
        atomic_text(run / "result.md", report_text(result, task, snapshot, root))
    return {"task_id": task_id, "report": str(run / "result.md"), "published": False}


def submit(task_id, root=ROOT):
    root = Path(root).resolve()
    run = relative(root, f"runs/{identifier(task_id)}")
    relative(run, "task.json", file=True)
    with lock(run / ".operation.lock"):
        result, task, snapshot = validate_result(task_id, root)
        require(task["state"] in ("running", "submitted"), "Submission requires a running task")
        for artifact in result["artifacts"]:
            artifact["sha256"] = digest(relative(root, artifact["path"], file=True).read_bytes())
        # Revalidate sealed content before any published write.
        validate_result(task_id, root, result)
        control_gate_call("check_submission", task_id, root, result=result, persist=True)
        text = report_text(result, task, snapshot, root)
        output = relative(root, f"outputs/{task_id}")
        require(output.is_dir(), "Task output directory is missing")
        publications = {
            "result.json": json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            "result.md": text,
        }
        for name, expected in publications.items():
            target = relative(output, name)
            if target.exists():
                require(target.read_text(encoding="utf-8") == expected,
                        "Published report differs; start a new task to change a submitted result")
            elif task["state"] == "submitted":
                raise ContractError("Submitted report is missing")
        if task["state"] == "submitted":
            return {"task_id": task_id, "state": "submitted", "result_status": result["status"],
                    "report": str(output / "result.md"), "idempotent": True}
        write_json(run / "result.json", result)
        atomic_text(run / "result.md", text)
        write_json(output / "result.json", result)
        atomic_text(output / "result.md", text)
        task["state"] = "submitted"
        task["result_status"] = result["status"]
        task["submission"] = {
            "result_sha256": digest((run / "result.json").read_bytes()),
            "report_sha256": digest(text.encode("utf-8")),
            "evidence": [{"path": name, "sha256": digest(relative(root, name, file=True).read_bytes())}
                         for name in sorted({name for check in result["verification"] for name in check["evidence"]})],
        }
        write_json(run / "task.json", task)
        event(run, "submitted", status=result["status"])
    return {"task_id": task_id, "state": "submitted", "result_status": result["status"],
            "report": str(output / "result.md")}


def register(manifest_path, root=ROOT):
    root = Path(root)
    with lock(relative(root, "work/registry.lock")):
        registry, modules = load_registry(root)
        manifest = read_json(relative(root, manifest_path, file=True))
        validate_named(manifest, "module", root)
        require(manifest["id"] not in modules, "Module ID is already registered")
        candidate = copy.deepcopy(registry)
        candidate["modules"].append({"id": manifest["id"], "path": manifest_path, "enabled": True})
        load_registry(root, candidate)
        write_json(relative(root, "registry.json", file=True), candidate)
    return {"registered": manifest["id"], "version": manifest["version"]}


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    sub.add_parser("list")
    init = sub.add_parser("init")
    init.add_argument("--repo", help="Registered repository ID for durable work records")
    for name in ("project", "service", "environment", "issue"):
        init.add_argument("--" + name)
    init.add_argument("--module", required=True)
    init.add_argument("--task", required=True)
    init.add_argument("--objective", required=True)
    init.add_argument("--criterion", action="append", required=True)
    step = sub.add_parser("transition")
    step.add_argument("task")
    step.add_argument("state", choices=("running", "waiting", "cancelled"))
    for name in ("validate", "render", "submit"):
        command = sub.add_parser(name)
        command.add_argument("task")
    reg = sub.add_parser("register")
    reg.add_argument("manifest")
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "doctor":
            data = doctor()
        elif args.command == "list":
            _, modules = load_registry()
            data = [{"id": k, "version": v["manifest"]["version"], "name": v["manifest"]["name"],
                     "kind": v["manifest"]["kind"], "enabled": v["entry"]["enabled"]}
                    for k, v in modules.items()]
        elif args.command == "init":
            if args.repo:
                import repoctl
                repoctl.repo(args.repo)
                scope = repoctl.validate_scope(repoctl.scope_args(args))
            else:
                require(not any(getattr(args, key) for key in ("project", "service", "environment", "issue")), "Scope requires --repo")
            data = init_task(args.module, args.task, args.objective, args.criterion)
            if args.repo:
                data["repository"] = repoctl.bind(args.repo, args.task, scope=scope, new_task=True)
        elif args.command == "transition":
            data = transition(args.task, args.state)
        elif args.command == "register":
            data = register(args.manifest)
        elif args.command == "validate":
            result, _, _ = validate_result(args.task)
            data = {"task_id": args.task, "valid": True, "result_status": result["status"]}
        else:
            data = {"render": render, "submit": submit}[args.command](args.task)
            if args.command == "submit" and relative(ROOT, f"runs/{args.task}/repository.json").exists():
                import repoctl
                data["repository"] = repoctl.checkpoint(args.task)
        print(json.dumps({"ok": True, "command": args.command, "data": data, "errors": []}, ensure_ascii=False))
        return 0
    except (ContractError, OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"ok": False, "command": args.command, "data": None,
                          "errors": [str(error)]}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
