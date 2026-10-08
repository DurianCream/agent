#!/usr/bin/env python3
"""실행 기록의 구조와 파일 정합성을 읽기 전용으로 검사한다."""

import argparse
import errno
import hashlib
import json
import os
import re
import stat
import sys


DOCUMENTS = ("request.json", "plan.json", "work.json", "critique.json")
EXIT_CODES = {"PASS": 0, "REWORK": 1, "NEEDS_EVIDENCE": 2}
PRIORITY = {"PASS": 0, "NEEDS_EVIDENCE": 1, "REWORK": 2}
HEX_DIGEST = re.compile(r"[0-9a-fA-F]{64}\Z")
JSON_LIMIT = 8 * 1024 * 1024


class EvidenceError(Exception):
    def __init__(self, verdict, reason):
        self.verdict = verdict
        self.reason = reason


class Store:
    """각 경로 요소를 O_NOFOLLOW로 열어 링크와 특수 파일을 거부한다."""

    def __init__(self, run_dir):
        absolute = os.path.abspath(run_dir)
        self.fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        try:
            for component in absolute.split("/")[1:]:
                if not component:
                    continue
                next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                  dir_fd=self.fd)
                os.close(self.fd)
                self.fd = next_fd
        except OSError:
            os.close(self.fd)
            raise

    def close(self):
        os.close(self.fd)

    def read(self, relative, collect=False):
        if (not isinstance(relative, str) or not relative or relative.startswith("/")
                or "\\" in relative or "\x00" in relative
                or re.match(r"^[A-Za-z]:", relative)
                or any(p in ("", ".", "..") for p in relative.split("/"))):
            raise EvidenceError("REWORK", "허용되지 않은 증거 경로가 있습니다.")
        parts = relative.split("/")
        directory = os.dup(self.fd)
        file_fd = None
        try:
            for part in parts[:-1]:
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                  dir_fd=directory)
                os.close(directory)
                directory = next_fd
            file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                              dir_fd=directory)
            before = os.fstat(file_fd)
            if not stat.S_ISREG(before.st_mode):
                raise EvidenceError("REWORK", "증거와 입력 문서는 일반 파일이어야 합니다.")
            digest = hashlib.sha256()
            chunks = []
            size = 0
            while True:
                block = os.read(file_fd, 65536)
                if not block:
                    break
                digest.update(block)
                if collect:
                    size += len(block)
                    if size > JSON_LIMIT:
                        raise EvidenceError("REWORK", "입력 JSON이 허용 크기 8 MiB를 초과했습니다.")
                    chunks.append(block)
            after = os.fstat(file_fd)
            attributes = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            if any(getattr(before, key) != getattr(after, key) for key in attributes):
                raise EvidenceError("REWORK", "읽는 동안 파일이 변경되어 재검사가 필요합니다.")
            return b"".join(chunks), digest.hexdigest()
        except OSError as error:
            if error.errno in (errno.ELOOP, errno.ENOTDIR):
                raise EvidenceError("REWORK", "심볼릭 링크 또는 잘못된 경로 요소를 거부했습니다.")
            raise EvidenceError("NEEDS_EVIDENCE", "필요한 입력 또는 증거 파일을 읽을 수 없습니다.")
        finally:
            if file_fd is not None:
                os.close(file_fd)
            os.close(directory)


class Gate:
    def __init__(self):
        self.verdict = "PASS"
        self.reasons = []
        self.hashes = {}

    def note(self, verdict, reason):
        if PRIORITY[verdict] > PRIORITY[self.verdict]:
            self.verdict = verdict
        if reason not in self.reasons:
            self.reasons.append(reason)

    def require(self, condition, reason):
        if not condition:
            self.note("REWORK", reason)
        return condition

    def result(self):
        return {"verdict": self.verdict, "reasons": self.reasons,
                "input_sha256": self.hashes}


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def id_list(gate, value, label):
    if not gate.require(type(value) is list and all(nonempty(v) for v in value),
                        label + "는 비어 있지 않은 문자열 ID의 배열이어야 합니다."):
        return False
    return gate.require(len(value) == len(set(value)), label + "에 중복 ID가 있습니다.")


def records(gate, value, label, rules, minimum=0):
    if not gate.require(type(value) is list and len(value) >= minimum,
                        label + "의 배열 형식 또는 최소 항목 수가 잘못되었습니다."):
        return False
    valid = True
    ids = []
    for record in value:
        if type(record) is not dict:
            gate.note("REWORK", label + "의 항목은 JSON 객체여야 합니다.")
            valid = False
            continue
        for key, rule in rules.items():
            if key not in record or not rule(record[key]):
                gate.note("REWORK", label + "." + key + "의 필수 필드 또는 형식이 잘못되었습니다.")
                valid = False
        if "id" in rules and nonempty(record.get("id")):
            ids.append(record["id"])
    if len(ids) != len(set(ids)):
        gate.note("REWORK", label + "에 중복 ID가 있습니다.")
        valid = False
    return valid


def validate(gate, name, document):
    if not gate.require(type(document) is dict, name + "은 JSON 객체여야 합니다."):
        return False
    valid = True

    def field(key, rule):
        nonlocal valid
        if key not in document or not rule(document[key]):
            gate.note("REWORK", name + "." + key + "의 필수 필드 또는 형식이 잘못되었습니다.")
            valid = False

    def collection(key, rules, minimum=0):
        nonlocal valid
        if not records(gate, document.get(key), name + "." + key, rules, minimum):
            valid = False

    string = lambda value: type(value) is str
    digest = lambda value: type(value) is str and bool(HEX_DIGEST.fullmatch(value))
    ids = lambda value: id_list(gate, value, name + "의 ID 참조")
    if name == "request.json":
        field("goal", nonempty)
        collection("criteria", {"id": nonempty, "description": nonempty}, 1)
        field("required_checks", ids)
    elif name == "plan.json":
        collection("tasks", {"id": nonempty, "description": nonempty, "depends_on": ids}, 1)
        field("criteria_ids", ids)
        field("required_checks", ids)
    elif name == "work.json":
        field("status", lambda value: value in ("COMPLETE", "BLOCKED", "FAILED"))
        field("summary", string)
        collection("evidence", {"id": nonempty, "path": nonempty, "sha256": digest})
        collection("checks", {"id": nonempty,
                               "status": lambda value: value in ("PASS", "FAIL", "NOT_RUN"),
                               "exit_code": lambda value: value is None or type(value) is int,
                               "evidence_ids": ids})
        collection("criteria", {"id": nonempty,
                                 "status": lambda value: value in ("VERIFIED", "UNVERIFIED", "FAILED"),
                                 "evidence_ids": ids, "explanation": string})
    elif name == "critique.json":
        field("verdict", lambda value: value in ("PASS", "REWORK", "NEEDS_EVIDENCE"))
        field("summary", string)
        field("work_sha256", digest)
        collection("findings", {"blocking": lambda value: type(value) is bool,
                                 "description": nonempty})
    return valid


def check_plan(gate, request, plan):
    if set(plan["criteria_ids"]) != {item["id"] for item in request["criteria"]}:
        gate.note("REWORK", "계획의 기준 ID 집합이 요청과 일치하지 않습니다.")
    if set(plan["required_checks"]) != set(request["required_checks"]):
        gate.note("REWORK", "계획의 필수 검사 ID 집합이 요청과 일치하지 않습니다.")
    tasks = {item["id"]: item for item in plan["tasks"]}
    visited, active = set(), set()

    def visit(task_id):
        if task_id in active:
            gate.note("REWORK", "계획 작업의 의존성에 순환이 있습니다.")
            return
        if task_id in visited:
            return
        active.add(task_id)
        for dependency in tasks[task_id]["depends_on"]:
            if dependency not in tasks:
                gate.note("REWORK", "계획에 존재하지 않는 작업 의존성이 있습니다.")
            else:
                visit(dependency)
        active.remove(task_id)
        visited.add(task_id)

    for task_id in tasks:
        visit(task_id)


def check_work(gate, store, request, work, critique):
    if work["status"] == "FAILED":
        gate.note("REWORK", "작업이 실패 상태로 기록되어 있습니다.")
    elif work["status"] == "BLOCKED":
        gate.note("NEEDS_EVIDENCE", "작업이 차단 상태이며 완료를 확인할 수 없습니다.")
    evidence_ids = {item["id"] for item in work["evidence"]}
    available = set()
    for item in work["evidence"]:
        try:
            _, actual = store.read(item["path"])
            if actual != item["sha256"].lower():
                gate.note("REWORK", "기록된 해시와 증거 파일이 일치하지 않습니다.")
            else:
                available.add(item["id"])
        except EvidenceError as error:
            gate.note(error.verdict, error.reason)

    criteria = {item["id"]: item for item in work["criteria"]}
    required_criteria = {item["id"] for item in request["criteria"]}
    if required_criteria - set(criteria):
        gate.note("NEEDS_EVIDENCE", "요청한 기준의 작업 평가가 누락되었습니다.")
    if set(criteria) - required_criteria:
        gate.note("REWORK", "요청에 없는 기준 ID가 작업 평가에 있습니다.")
    checks = {item["id"]: item for item in work["checks"]}
    if set(request["required_checks"]) - set(checks):
        gate.note("NEEDS_EVIDENCE", "필수 검사의 실행 기록이 누락되었습니다.")
    for item in work["criteria"] + work["checks"]:
        references = set(item["evidence_ids"])
        if references - evidence_ids:
            gate.note("REWORK", "등록되지 않은 증거 ID를 참조하는 평가 또는 검사가 있습니다.")
        if not references or references - available:
            gate.note("NEEDS_EVIDENCE", "평가 또는 검사에 필요한 일치하는 증거가 부족합니다.")
        if item["status"] in ("FAILED", "FAIL"):
            gate.note("REWORK", "실패한 기준 평가 또는 검사가 있습니다.")
        elif item["status"] in ("UNVERIFIED", "NOT_RUN"):
            gate.note("NEEDS_EVIDENCE", "확인되지 않은 기준 또는 실행하지 않은 검사가 있습니다.")
        elif item["status"] == "PASS":
            if item["exit_code"] is None:
                gate.note("NEEDS_EVIDENCE", "통과 검사의 실제 종료 코드가 기록되지 않았습니다.")
            elif item["exit_code"] != 0:
                gate.note("REWORK", "통과로 기록된 검사의 종료 코드가 0이 아닙니다.")
    if critique["work_sha256"].lower() != gate.hashes["work.json"]:
        gate.note("REWORK", "비평이 확인한 작업 파일과 현재 작업 파일의 해시가 다릅니다.")
    if critique["verdict"] != "PASS":
        gate.note(critique["verdict"], "비평 단계가 통과 판정을 내리지 않았습니다.")
    if any(item["blocking"] for item in critique["findings"]):
        gate.note("REWORK", "비평에 작업을 막는 지적이 남아 있습니다.")


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def reject_constant(_):
    raise ValueError("non-finite JSON number")


def evaluate(run_dir):
    gate = Gate()
    try:
        store = Store(run_dir)
    except (OSError, ValueError) as error:
        verdict = "REWORK" if getattr(error, "errno", None) in (errno.ELOOP, errno.ENOTDIR) else "NEEDS_EVIDENCE"
        gate.note(verdict, "실행 디렉터리를 안전하게 열 수 없습니다.")
        return gate.result()
    try:
        documents = {}
        valid = True
        for name in DOCUMENTS:
            try:
                data, digest = store.read(name, collect=True)
                gate.hashes[name] = digest
                value = json.loads(data.decode("utf-8"), object_pairs_hook=unique_object,
                                   parse_constant=reject_constant)
                if validate(gate, name, value):
                    documents[name] = value
                else:
                    valid = False
            except EvidenceError as error:
                gate.note(error.verdict, name + ": " + error.reason)
                valid = False
            except (UnicodeError, ValueError, RecursionError):
                gate.note("REWORK", name + "의 UTF-8 또는 JSON 형식이 잘못되었습니다.")
                valid = False
        if valid and len(documents) == len(DOCUMENTS):
            check_plan(gate, documents["request.json"], documents["plan.json"])
            check_work(gate, store, documents["request.json"], documents["work.json"], documents["critique.json"])
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        gate.note("REWORK", "입력을 일관되게 검사할 수 없어 재작업이 필요합니다.")
    finally:
        store.close()
    return gate.result()


def main(argv=None):
    parser = argparse.ArgumentParser(description="실행 기록과 증거를 읽기 전용으로 검사합니다.")
    parser.add_argument("run_dir", help="request.json 등 네 문서가 있는 실행 디렉터리")
    args = parser.parse_args(argv)
    result = evaluate(args.run_dir)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return EXIT_CODES[result["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
