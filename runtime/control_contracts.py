"""P0 structural control contracts: bounded JSON, local schemas, and RFC 8785 digests.

Validation never authenticates a signature or grants execution authority. This module
does not execute tools, enroll tasks, issue approvals, or contact a network service.
"""
from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "shared/schemas/control-envelope.schema.json"
SCHEMA_VERSION = "0.1.0"
DIALECT = "https://json-schema.org/draft/2020-12/schema"
MAX_INPUT_BYTES = 128 * 1024
MAX_DEPTH = 32
MAX_NODES = 10000
MAX_SAFE_INTEGER = (1 << 53) - 1


class ControlContractError(ValueError):
    """Stable classification and safe message; never includes request values."""

    def __init__(self, code: str, safe_message: str):
        self.code = code
        self.safe_message = safe_message
        super().__init__(safe_message)


def _fail(code, message):
    raise ControlContractError(code, message) from None


def _dependencies():
    try:
        jcs = importlib.import_module("rfc8785")
        schema = importlib.import_module("jsonschema")
        referencing = importlib.import_module("referencing")
        exceptions = importlib.import_module("referencing.exceptions")
    except ImportError:
        _fail("dependency_missing", "P0 dependencies are unavailable. Install runtime/control-requirements.txt in the selected Python environment; no automatic installation is performed.")
    return jcs, schema, referencing, exceptions


def _profile_copy(value):
    """Reject non-JSON/cyclic/oversized data before recursion or canonicalization."""
    budget = {"nodes": 0, "bytes": 0}
    active = set()

    def add(size=0):
        budget["nodes"] += 1
        budget["bytes"] += size
        if budget["nodes"] > MAX_NODES:
            _fail("input_nodes", "JSON node limit exceeded.")
        if budget["bytes"] > MAX_INPUT_BYTES:
            _fail("input_too_large", "JSON byte limit exceeded.")

    def text_size(text):
        if len(text) > MAX_INPUT_BYTES:
            _fail("input_too_large", "JSON byte limit exceeded.")
        try:
            return len(json.dumps(text, ensure_ascii=False).encode("utf-8"))
        except UnicodeEncodeError:
            _fail("invalid_unicode", "JSON contains an invalid Unicode scalar value.")

    def visit(item, depth):
        if depth > MAX_DEPTH:
            _fail("input_depth", "JSON nesting limit exceeded.")
        kind = type(item)
        if item is None or kind is bool:
            add(5)
            return item
        if kind is int:
            if abs(item) > MAX_SAFE_INTEGER:
                _fail("unsafe_integer", "Integer exceeds the P0 safe-integer profile.")
            add(len(str(item)))
            return item
        if kind is float:
            _fail("number_profile", "Floating-point values are outside the P0 profile.")
        if kind is str:
            add(text_size(item))
            return item
        if kind not in (dict, list):
            _fail("json_type", "Only JSON objects, arrays, strings, booleans, null, and safe integers are supported.")
        identity = id(item)
        if identity in active:
            _fail("json_cycle", "Cyclic data is not JSON.")
        add(2 + len(item))
        active.add(identity)
        try:
            if kind is list:
                return [visit(child, depth + 1) for child in item]
            output = {}
            for key, child in item.items():
                if type(key) is not str:
                    _fail("json_key", "JSON object keys must be strings.")
                add(text_size(key) + 1)
                output[key] = visit(child, depth + 1)
            return output
        finally:
            active.remove(identity)

    return visit(value, 1)


def _check_text_depth(text):
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > MAX_DEPTH:
                _fail("input_depth", "JSON nesting limit exceeded.")
        elif char in "]}":
            depth -= 1


def load_json(data):
    """Parse UTF-8 bytes or text with duplicate-key and resource-limit rejection."""
    if type(data) is bytes:
        if len(data) > MAX_INPUT_BYTES:
            _fail("input_too_large", "JSON byte limit exceeded.")
        try:
            text = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            _fail("invalid_utf8", "Input is not valid UTF-8.")
    elif type(data) is str:
        if len(data) > MAX_INPUT_BYTES:
            _fail("input_too_large", "JSON byte limit exceeded.")
        try:
            encoded = data.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            _fail("invalid_unicode", "JSON contains an invalid Unicode scalar value.")
        if len(encoded) > MAX_INPUT_BYTES:
            _fail("input_too_large", "JSON byte limit exceeded.")
        text = data
    else:
        _fail("input_type", "JSON input must be UTF-8 bytes or text.")
    _check_text_depth(text)

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                _fail("duplicate_key", "Duplicate JSON object key.")
            result[key] = value
        return result

    def number(_):
        _fail("number_profile", "Non-integer or non-finite numbers are outside the P0 profile.")

    def integer(token):
        if len(token.lstrip("-")) > 16:
            _fail("unsafe_integer", "Integer exceeds the P0 safe-integer profile.")
        value = int(token)
        if abs(value) > MAX_SAFE_INTEGER:
            _fail("unsafe_integer", "Integer exceeds the P0 safe-integer profile.")
        return value

    try:
        result = json.loads(text, object_pairs_hook=pairs, parse_constant=number,
                            parse_float=number, parse_int=integer)
    except (json.JSONDecodeError, RecursionError):
        _fail("invalid_json", "Input is not valid bounded JSON.")
    return _profile_copy(result)


def read_json(path):
    """Read only the explicit file, at most MAX_INPUT_BYTES + 1 bytes."""
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(MAX_INPUT_BYTES + 1)
    except (OSError, ValueError, TypeError):
        _fail("input_unreadable", "The requested JSON file cannot be read.")
    return load_json(data)


def canonical_digest(value):
    """Hash full JSON using maintained RFC 8785 canonicalization, not sort_keys."""
    value = _profile_copy(value)
    jcs, _, _, _ = _dependencies()
    try:
        canonical = jcs.dumps(value)
    except (ValueError, TypeError, UnicodeError):
        _fail("canonicalization_failed", "Value cannot be canonicalized under the P0 profile.")
    if len(canonical) > MAX_INPUT_BYTES:
        _fail("input_too_large", "Canonical JSON byte limit exceeded.")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def envelope_digest(envelope):
    """Hash precisely the envelope core; does not validate or authenticate it."""
    value = _profile_copy(envelope)
    if type(value) is not dict or not all(key in value for key in ("record_type", "schema_version", "payload")):
        _fail("envelope_core", "Envelope core fields are missing.")
    return canonical_digest({key: value[key] for key in ("record_type", "schema_version", "payload")})


def _schema_nodes(schema):
    """Visit schemas, not annotation/default payloads with schema-like keys."""
    stack = [schema]
    seen = set()
    mappings = ("$defs", "definitions", "properties", "patternProperties", "dependentSchemas")
    arrays = ("allOf", "anyOf", "oneOf", "prefixItems")
    singles = ("items", "contains", "additionalProperties", "unevaluatedProperties",
               "propertyNames", "not", "if", "then", "else", "unevaluatedItems", "contentSchema")
    while stack:
        node = stack.pop()
        if type(node) is not dict:
            continue
        if id(node) in seen:
            continue
        seen.add(id(node))
        yield node
        pointer = node.get("$ref")
        if type(pointer) is str and pointer.startswith("#/"):
            target = schema
            try:
                for part in pointer[2:].split("/"):
                    target = target[part.replace("~1", "/").replace("~0", "~")]
            except (KeyError, TypeError):
                pass  # The local-reference check reports this safely.
            else:
                stack.append(target)
        for name in mappings:
            if type(node.get(name)) is dict:
                stack.extend(node[name].values())
        for name in arrays:
            if type(node.get(name)) is list:
                stack.extend(node[name])
        for name in singles:
            if type(node.get(name)) in (dict, bool):
                stack.append(node[name])


def _format_checker(library, schema):
    """Explicit offline coverage; optional jsonschema discovery is never trusted."""
    try:
        dates = importlib.import_module("rfc3339_validator")
        uris = importlib.import_module("rfc3986_validator")
    except ImportError:
        _fail("dependency_missing", "P0 format dependencies are unavailable. Install runtime/control-requirements.txt in the selected Python environment; no automatic installation is performed.")
    supported = {"date-time", "uri", "uuid"}
    for node in _schema_nodes(schema):
        if "format" in node and node["format"] not in supported:
            _fail("schema_format", "The selected schema uses an unsupported required format.")
    checker = library.FormatChecker(formats=())

    @checker.checks("date-time")
    def utc_timestamp(value):
        if not isinstance(value, str):
            return True
        # P0 is UTC-only with at most microsecond precision; no silent truncation.
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z", value):
            return False
        try:
            return bool(dates.validate_rfc3339(value)) and datetime.fromisoformat(value[:-1] + "+00:00") is not None
        except (ValueError, OverflowError):
            return False

    @checker.checks("uri")
    def absolute_uri(value):
        if not isinstance(value, str):
            return True
        if any(ord(char) <= 32 or ord(char) == 127 for char in value):
            return False
        return bool(uris.validate_rfc3986(value, rule="URI"))

    @checker.checks("uuid")
    def canonical_uuid(value):
        if not isinstance(value, str):
            return True
        try:
            return str(UUID(value)) == value.lower()
        except (ValueError, AttributeError):
            return False

    if set(checker.checkers) != supported:
        _fail("dependency_incompatible", "P0 format checker registration failed; check the pinned dependency environment.")
    return checker


def _local_schema(schema):
    schema = _profile_copy(schema)
    if type(schema) is not dict or schema.get("$schema") != DIALECT:
        _fail("schema_invalid", "A local Draft 2020-12 schema is required.")

    def visit(node, root=False):
        if type(node) is dict:
            if "$schema" in node and node["$schema"] != DIALECT:
                _fail("schema_invalid", "Only the selected Draft 2020-12 dialect is supported.")
            if "$dynamicRef" in node or "$recursiveRef" in node:
                _fail("schema_reference", "Only fixed local JSON-pointer schema references are supported.")
            if "$id" in node and not root:
                _fail("schema_reference", "Nested schema identifiers are not supported.")
            if "$ref" in node:
                pointer = node["$ref"]
                if type(pointer) is not str or not pointer.startswith("#/"):
                    _fail("schema_reference", "External schema references are not permitted.")
                target = schema
                try:
                    for part in pointer[2:].split("/"):
                        target = target[part.replace("~1", "/").replace("~0", "~")]
                except (KeyError, TypeError):
                    _fail("schema_reference", "Local schema reference cannot be resolved.")
                if type(target) not in (dict, bool):
                    _fail("schema_reference", "Local reference is not a schema.")
    for node in _schema_nodes(schema):
        visit(node, root=node is schema)
    return schema


def validate_schema_data(data, schema=None):
    """Validate with caller-selected local schema; never fetch remote resources."""
    value = _profile_copy(data)
    spec = _local_schema(read_json(SCHEMA_PATH) if schema is None else schema)
    _, library, referencing, exceptions = _dependencies()

    def no_network(uri):
        raise exceptions.NoSuchResource(ref=uri)

    registry = referencing.Registry(retrieve=no_network)
    try:
        # A local $ref may target a dictionary stored under an annotation or
        # extension keyword. Root meta-validation does not inspect such a target.
        for subschema in _schema_nodes(spec):
            library.Draft202012Validator.check_schema(subschema)
        checker = _format_checker(library, spec)
        validator = library.Draft202012Validator(spec, format_checker=checker, registry=registry)
        if not validator.is_valid(value):
            _fail("schema_violation", "Data does not match the selected control schema.")
    except (library.exceptions.SchemaError, library.exceptions.UnknownType,
            library.exceptions.UndefinedTypeCheck):
        _fail("schema_invalid", "The selected control schema is malformed.")
    except (exceptions.Unresolvable, RecursionError):
        _fail("schema_reference", "Schema references cannot be safely resolved.")
    return value


def _ordered_unique(items, field, code):
    values = [item[field] for item in items]
    if len(values) != len(set(values)) or values != sorted(values):
        _fail(code, "Referenced items must have unique identifiers in canonical order.")


def _timestamp(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail("timestamp_invalid", "Timestamp cannot be interpreted as a valid UTC instant.")


def _path(value):
    if (not value or value.startswith("/") or "\\" in value or ":" in value
            or any(ord(char) < 32 for char in value)
            or any(part in ("", ".", "..") for part in value.split("/"))):
        _fail("path_invalid", "A canonical repository-relative file path is required.")


def _semantics(value):
    kind, payload = value["record_type"], value["payload"]
    if "issued_at" in payload and _timestamp(payload["expires_at"]) <= _timestamp(payload["issued_at"]):
        _fail("timestamp_order", "Expiry must be later than issuance.")
    if kind == "execution_receipt" and _timestamp(payload["finished_at"]) < _timestamp(payload["started_at"]):
        _fail("timestamp_order", "Finish time must not precede start time.")
    for name in ("artifacts", "evidence"):
        if name in payload:
            _ordered_unique(payload[name], "id", "artifact_order")
    for name in ("approval_digests", "standing_grant_ids"):
        if name in payload and len(payload[name]) != len(set(payload[name])):
            _fail("duplicate_reference", "Duplicate binding reference is not permitted.")
    if kind == "action_request":
        duration = (_timestamp(payload["expires_at"]) - _timestamp(payload["issued_at"])).total_seconds()
        if payload["budget"]["timeout_seconds"] > duration:
            _fail("request_limits", "Requested timeout exceeds the request validity interval.")
        params, adapter = payload["parameters"], payload["adapter"]
        artifacts = {item["id"]: item["digest"] for item in payload["artifacts"]}
        for field in ("patch_artifact_id", "desired_state_artifact_id", "artifact_id"):
            if field in params and params[field] not in artifacts:
                _fail("artifact_link", "Action references an artifact absent from its bound artifact set.")
        if "preimages" in params:
            _ordered_unique(params["preimages"], "path", "path_order")
            for item in params["preimages"]:
                _path(item["path"])
        if "paths" in params:
            if params["paths"] != sorted(set(params["paths"])):
                _fail("path_order", "Paths must be unique and in canonical order.")
            for item in params["paths"]:
                _path(item)
        if adapter == "repo.publish":
            if params["owned_manifest_digest"] not in artifacts.values():
                _fail("artifact_link", "Publication manifest is absent from its bound artifact set.")
            try:
                remote = urlsplit(params["remote_url"])
            except ValueError:
                _fail("target_invalid", "Publication URL cannot be interpreted as a valid destination.")
            if remote.scheme != "https" or not remote.hostname or remote.username or remote.password or remote.query or remote.fragment:
                _fail("target_invalid", "Publication URL must be an uncredentialed HTTPS destination.")
            branch = params["branch"]
            if (branch.startswith(("-", "/")) or branch.endswith(("/", ".")) or branch == "@"
                    or ".." in branch or "@{" in branch or any(char.isspace() or ord(char) < 32 or char in "~^:?*[\\" for char in branch)
                    or any(not part or part.startswith(".") or part.endswith(".lock") for part in branch.split("/"))):
                _fail("target_invalid", "Publication branch is not a valid bounded ref name.")
    if kind == "evaluation_attestation":
        checks = [item["case_id"] for item in payload["checks"]]
        if len(checks) != len(set(checks)):
            _fail("duplicate_reference", "Duplicate evaluation case is not permitted.")
        if payload["producer"] == "independent_evaluator" and (payload["issuer"]["subject_id"] == payload["author_subject_id"] or payload["issuer"]["session_id"] == payload["author_session_id"]):
            _fail("identity_conflict", "Declared evaluator and author identities must differ; this check does not authenticate either identity.")


def validate_envelope(value):
    """Check shape, digest, and internal semantics; authenticity remains unverified."""
    value = validate_schema_data(value)
    expected = envelope_digest(value)
    if not hmac.compare_digest(value["digest"], expected):
        _fail("digest_mismatch", "Envelope digest does not match its canonical core.")
    _semantics(value)
    return {"envelope": value, "schema_version": SCHEMA_VERSION,
            "authenticity": "not_verified", "executable": False}
