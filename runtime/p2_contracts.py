"""Validation-only draft for a future isolated-host broker's typed requests.

This module performs no authentication, authorization, filesystem materialization,
credential access, test execution or publication. A trusted deployed service must
supply expected_binding from its protected enrollment store, authenticate its peer,
resolve opaque IDs, verify blob bytes and enforce replay/policy/host boundaries.
Passing this validator is not a P2 deployment or a grant to execute.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
import unicodedata
from uuid import UUID

from control_contracts import ControlContractError, canonical_digest, load_json

VERSION = "0.1.0"
MAX_FILES = 512
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
SCOPE_FIELDS = {"project", "service", "environment", "issue"}
BINDING_FIELDS = {"repository_id", "task_id", "scope", "enrollment_id", "base_commit", "policy_digest"}
ROOT_FIELDS = {"schema_version", "operation", "request_id", "idempotency_key", "binding", "payload"}
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,127}\Z")
SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
RESERVED = {"con", "prn", "aux", "nul", "conin$", "conout$"}
RESERVED.update(prefix + digit for prefix in ("com", "lpt") for digit in "0123456789¹²³")


def require(condition, code, message):
    if not condition:
        raise ControlContractError("p2_" + code, message)


def exact(value, keys, code):
    require(type(value) is dict and set(value) == keys, code, "P2 object fields are invalid.")


def identifier(value):
    require(type(value) is str and SLUG.fullmatch(value) is not None,
            "identifier", "P2 identifier is invalid.")


def uuid4(value):
    require(type(value) is str and len(value) == 36, "uuid", "P2 opaque identifier is invalid.")
    try:
        parsed = UUID(value)
    except ValueError:
        raise ControlContractError("p2_uuid", "P2 opaque identifier is invalid.") from None
    require(parsed.version == 4 and str(parsed) == value, "uuid", "P2 opaque identifier is invalid.")


def digest(value):
    require(type(value) is str and SHA256.fullmatch(value) is not None,
            "digest", "P2 SHA256 digest is invalid.")


def binding(value):
    exact(value, BINDING_FIELDS, "binding")
    identifier(value["repository_id"])
    identifier(value["task_id"])
    exact(value["scope"], SCOPE_FIELDS, "scope")
    for item in value["scope"].values():
        identifier(item)
    uuid4(value["enrollment_id"])
    require(type(value["base_commit"]) is str and GIT_OID.fullmatch(value["base_commit"]) is not None,
            "commit", "P2 baseline commit is invalid.")
    digest(value["policy_digest"])


def portable_path(value):
    """Check portable syntax only; never claim this resolves a safe host path."""
    require(type(value) is str, "path", "P2 artifact path is invalid.")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        raise ControlContractError("p2_path", "P2 artifact path is invalid.") from None
    require(0 < len(encoded) <= 1024,
            "path", "P2 artifact path is invalid.")
    require(unicodedata.normalize("NFC", value) == value and
            not any(ord(c) < 32 or ord(c) == 127 or c in '\\:<>"|?*' for c in value),
            "path", "P2 artifact path is invalid.")
    for part in value.split("/"):
        require(part not in ("", ".", "..") and part.casefold() != ".git" and
                not part.endswith((" ", ".")) and len(part.encode("utf-8")) <= 255 and
                part.split(".", 1)[0].casefold() not in RESERVED,
                "path", "P2 artifact path is invalid.")


def validate_manifest(files):
    require(type(files) is list and 0 < len(files) <= MAX_FILES,
            "manifest_count", "P2 artifact count is outside the supported bound.")
    paths, aliases, total = [], set(), 0
    for item in files:
        require(type(item) is dict and item.get("kind") in ("blob", "delete"),
                "artifact_kind", "P2 accepts only regular blobs or explicit deletions.")
        fields = {"path", "kind"} if item["kind"] == "delete" else {"path", "kind", "mode", "size", "digest"}
        exact(item, fields, "artifact_fields")
        portable_path(item["path"])
        path = item["path"]
        require(path.casefold() not in aliases, "path_alias", "P2 artifact paths conflict.")
        aliases.add(path.casefold())
        paths.append(path)
        if item["kind"] == "blob":
            require(item["mode"] in ("100644", "100755"), "mode", "P2 artifact mode is unsupported.")
            require(type(item["size"]) is int and 0 <= item["size"] <= MAX_FILE_BYTES,
                    "artifact_size", "P2 artifact size is outside the supported bound.")
            total += item["size"]
            require(total <= MAX_TOTAL_BYTES, "manifest_size", "P2 total artifact size exceeds the bound.")
            digest(item["digest"])
    require(paths == sorted(paths, key=lambda value: value.encode("utf-8")),
            "manifest_order", "P2 manifest paths must be ordered by UTF-8 bytes.")
    # A tree cannot contain a regular file and its descendant at the same time.
    aliases = set(path.casefold() for path in paths)
    for path in paths:
        parts = path.casefold().split("/")
        require(not any("/".join(parts[:i]) in aliases for i in range(1, len(parts))),
                "path_prefix", "P2 artifact file and directory paths conflict.")
    return canonical_digest(files)


@dataclass(frozen=True)
class ValidatedRequest:
    """Immutable validated bytes; neither this object nor its digest is authority."""

    payload_json: bytes
    request_digest: str
    manifest_digest: str | None

    @property
    def validation_only(self):
        return True

    @property
    def authorization(self):
        return False

    def as_dict(self):
        return {"validation_only": True, "authorization": False,
                "request_digest": self.request_digest, "manifest_digest": self.manifest_digest,
                "request": load_json(self.payload_json)}


def validate_request(raw, *, expected_binding):
    """Validate a request against an externally supplied expected enrollment.

    expected_binding must come from protected service state in a future broker,
    never from this request. This function does not establish that provenance.
    It deliberately accepts no peer identity, remote/ref, command, key, claimed
    test outcome or approval from request JSON. Replay/ID ownership is not checked.
    """
    require(type(raw) is bytes, "input_type", "P2 request input must be UTF-8 bytes.")
    value = load_json(raw)  # Reuse existing duplicate, UTF-8, size, depth and number bounds.
    exact(value, ROOT_FIELDS, "request_fields")
    require(value["schema_version"] == VERSION, "version", "P2 request version is unsupported.")
    require(value["operation"] in ("stage", "verify", "publish"), "operation", "P2 operation is unsupported.")
    uuid4(value["request_id"])
    uuid4(value["idempotency_key"])
    binding(expected_binding)
    binding(value["binding"])
    require(value["binding"] == expected_binding, "binding_mismatch", "P2 request does not match the expected enrollment.")
    payload = value["payload"]
    manifest_digest = None
    if value["operation"] == "stage":
        exact(payload, {"files", "manifest_digest"}, "stage_fields")
        digest(payload["manifest_digest"])
        manifest_digest = validate_manifest(payload["files"])
        require(payload["manifest_digest"] == manifest_digest, "manifest_digest", "P2 manifest digest does not match its descriptors.")
    else:
        fields = {"candidate_id", "candidate_digest"}
        if value["operation"] == "publish":
            fields.add("verification_id")
        exact(payload, fields, "candidate_fields")
        uuid4(payload["candidate_id"])
        digest(payload["candidate_digest"])
        if value["operation"] == "publish":
            uuid4(payload["verification_id"])
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return ValidatedRequest(encoded, canonical_digest(value), manifest_digest)
