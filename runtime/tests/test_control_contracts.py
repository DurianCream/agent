"""P0 contract behavior, malformed input, and external canonicalization vectors."""
import copy
import hashlib
import io
import json
import sys
import traceback
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "runtime"))
import control_contracts as c

FIXTURES = ROOT / "runtime/tests/fixtures/control-contracts"


class ControlContractTests(unittest.TestCase):
    def setUp(self):
        self.request = c.read_json(FIXTURES / "action-request.json")

    def reject(self, code, callback, *args):
        with self.assertRaises(c.ControlContractError) as caught:
            callback(*args)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), caught.exception.safe_message)
        return caught.exception

    def seal(self, value):
        value["digest"] = c.envelope_digest(value)
        return value

    def receipt(self):
        request = self.request["payload"]
        digest = "sha256:" + "b" * 64
        body = {"execution_id": "00000000-0000-4000-8000-000000000005",
                "request_digest": self.request["digest"], "decision_digest": digest,
                "approval_digests": [], "task_id": request["task_id"], "scope": request["scope"],
                "policy_ref": request["policy_ref"],
                "adapter_ref": {"id": "fixture-adapter", "version": "0.1.0", "digest": digest},
                "executor": {"subject_id": "fixture-executor", "host_id": "fixture-host",
                             "session_id": "fixture-session", "role": "executor"},
                "status": "succeeded", "effects": "applied", "readback_status": "passed",
                "before_state_digest": digest, "after_state_digest": digest,
                "evidence": [{"id": "fixture-evidence", "digest": digest, "media_type": "application/json"}],
                "revocation_epoch": 1, "started_at": "2026-10-28T06:30:00Z",
                "finished_at": "2026-10-28T06:30:05Z", "reason_codes": ["fixture.readback"]}
        return self.seal({"record_type": "execution_receipt", "schema_version": "0.1.0", "payload": body,
                          "digest": digest, "signature": {"algorithm": "Ed25519",
                          "key_id": "fixture-not-trusted", "value": "A" * 86 + "=="}})

    def test_valid_request_is_structural_only_and_defensive_copy(self):
        result = c.validate_envelope(self.request)
        self.assertEqual(result["authenticity"], "not_verified")
        self.assertFalse(result["executable"])
        result["envelope"]["payload"]["task_id"] = "changed"
        self.assertNotEqual(self.request["payload"]["task_id"], "changed")

    def test_signed_shape_is_not_signature_authentication(self):
        result = c.validate_envelope(self.receipt())
        self.assertEqual(result["authenticity"], "not_verified")
        self.assertFalse(result["executable"])

    def test_all_six_draft_record_types_remain_structurally_compatible(self):
        records = c.read_json(FIXTURES / "all-envelopes.json")["records"]
        self.assertEqual(len({record["record_type"] for record in records}), 6)
        for record in records:
            with self.subTest(record_type=record["record_type"]):
                result = c.validate_envelope(record)
                self.assertEqual(result["authenticity"], "not_verified")
                self.assertFalse(result["executable"])

    def test_declared_evaluator_identity_conflict_is_rejected_not_authenticated(self):
        records = c.read_json(FIXTURES / "all-envelopes.json")["records"]
        value = next(record for record in records if record["record_type"] == "evaluation_attestation"
                     and record["payload"]["producer"] == "independent_evaluator")
        value["payload"]["issuer"]["subject_id"] = value["payload"]["author_subject_id"]
        self.reject("identity_conflict", c.validate_envelope, self.seal(value))

    def test_duplicate_attestation_cases_rejected(self):
        records = c.read_json(FIXTURES / "all-envelopes.json")["records"]
        value = next(record for record in records if record["record_type"] == "evaluation_attestation")
        value["payload"]["checks"].append(copy.deepcopy(value["payload"]["checks"][0]))
        self.reject("duplicate_reference", c.validate_envelope, self.seal(value))

    def test_duplicate_json_keys_rejected_without_value_leak(self):
        error = self.reject("duplicate_key", c.load_json,
                            '{"secret-marker": 1, "secret-marker": 2}')
        self.assertNotIn("secret-marker", str(error))

    def test_invalid_utf8_and_lone_surrogates(self):
        self.reject("invalid_utf8", c.load_json, b'"\xff"')
        self.reject("invalid_unicode", c.load_json, b'"\\ud800"')
        self.reject("invalid_unicode", c.load_json, '"\ud800"')
        self.assertEqual(c.load_json(b'"\\ud83d\\ude00"'), "😀")

    def test_nonfinite_and_float_json_tokens_rejected(self):
        for token in ("NaN", "Infinity", "-Infinity", "1.0", "1e2", "-0.0"):
            with self.subTest(token=token):
                self.reject("number_profile", c.load_json, token)
        self.reject("number_profile", c.canonical_digest, {"value": 1.0})

    def test_safe_integer_boundaries(self):
        for value in (c.MAX_SAFE_INTEGER, -c.MAX_SAFE_INTEGER):
            self.assertEqual(c.load_json(str(value)), value)
        for value in (c.MAX_SAFE_INTEGER + 1, -c.MAX_SAFE_INTEGER - 1):
            self.reject("unsafe_integer", c.load_json, str(value))
            self.reject("unsafe_integer", c.canonical_digest, value)
        self.reject("unsafe_integer", c.load_json, "9" * 2000)

    def test_size_limit_for_raw_and_direct_object(self):
        self.reject("input_too_large", c.load_json, b" " * (c.MAX_INPUT_BYTES + 1))
        self.reject("input_too_large", c.canonical_digest, "a" * c.MAX_INPUT_BYTES)

    def test_read_is_bounded_and_read_errors_are_safe(self):
        data = io.BytesIO(b" " * (c.MAX_INPUT_BYTES + 100))
        with mock.patch.object(Path, "open", return_value=data):
            self.reject("input_too_large", c.read_json, "unused")
        self.reject("input_unreadable", c.read_json, FIXTURES / "missing-secret-marker.json")

    def test_depth_and_node_limits(self):
        self.reject("input_depth", c.load_json, "[" * 40 + "0" + "]" * 40)
        self.reject("input_nodes", c.canonical_digest, [0] * c.MAX_NODES)
        self.assertEqual(c.load_json('{"text":"[[[escaped \\\" brackets]]]"}')["text"],
                         '[[[escaped " brackets]]]')

    def test_cyclic_and_non_json_direct_values(self):
        value = []
        value.append(value)
        self.reject("json_cycle", c.canonical_digest, value)
        self.reject("json_key", c.canonical_digest, {1: "bad"})
        self.reject("json_type", c.canonical_digest, (1, 2))

    def test_invalid_json_is_safe(self):
        self.reject("invalid_json", c.load_json, '{"secret-marker":')
        self.reject("input_type", c.load_json, 123)

    def test_rfc8785_utf16_property_order_known_bytes(self):
        vector = c.read_json(FIXTURES / "unicode-vector.json")
        expected = vector["expected_canonical_utf8"].encode("utf-8")
        self.assertEqual(c.canonical_digest(vector["input"]), "sha256:" + hashlib.sha256(expected).hexdigest())
        self.assertEqual(c.canonical_digest(vector["input"]), vector["expected_sha256"])
        python_sorted = json.dumps(vector["input"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        self.assertNotEqual(expected, python_sorted, "Vector must catch Python scalar-order JCS substitutes")

    def test_unicode_is_not_normalized(self):
        self.assertNotEqual(c.canonical_digest({"text": "é"}), c.canonical_digest({"text": "e\u0301"}))

    def test_envelope_digest_excludes_signature_and_digest(self):
        expected = c.envelope_digest(self.request)
        self.request["digest"] = "irrelevant"
        self.request["signature"] = {"untrusted": "data"}
        self.assertEqual(c.envelope_digest(self.request), expected)
        self.reject("envelope_core", c.envelope_digest, {})

    def test_unknown_field_version_and_adapter_parameter_mismatch(self):
        for change in (lambda x: x.update(unexpected=True),
                       lambda x: x.update(schema_version="9.0.0"),
                       lambda x: x["payload"].update(adapter="external.export")):
            value = copy.deepcopy(self.request)
            change(value)
            self.reject("schema_violation", c.validate_envelope, value)

    def test_format_checker_rejects_malformed_uuid(self):
        self.request["payload"]["request_id"] = "not-a-uuid"
        self.reject("schema_violation", c.validate_envelope, self.seal(self.request))

    def test_every_timestamp_field_has_guaranteed_format_assertions(self):
        records = c.read_json(FIXTURES / "all-envelopes.json")["records"]
        checked = set()
        for original in records:
            for field in ("issued_at", "expires_at", "started_at", "finished_at", "enrolled_at"):
                if field not in original["payload"]:
                    continue
                value = copy.deepcopy(original)
                value["payload"][field] = "secret-marker-invalid-dateZ"
                with self.subTest(record=original["record_type"], field=field):
                    error = self.reject("schema_violation", c.validate_envelope, self.seal(value))
                    self.assertNotIn("secret-marker", str(error))
                checked.add(field)
        self.assertEqual(checked, {"issued_at", "expires_at", "started_at", "finished_at", "enrolled_at"})

    def test_formats_work_without_optional_jsonschema_auto_registration(self):
        _, library, _, _ = c._dependencies()
        schema = {"$schema": c.DIALECT, "type": "string", "format": "date-time"}
        with mock.patch.dict(library.FormatChecker.checkers, {}, clear=True):
            self.assertEqual(c.validate_schema_data("2028-02-29T06:30:00.123456Z", schema),
                             "2028-02-29T06:30:00.123456Z")
            for value in ("20261028T063000Z", "2026-02-30T06:30:00Z", "2026-10-28T24:00:00Z",
                          "2026-10-28T06:30:00+00:00", "2026-10-28T06:30:00.1234567Z"):
                self.reject("schema_violation", c.validate_schema_data, value, schema)
            schema["format"] = "uri"
            self.assertEqual(c.validate_schema_data("https://example.invalid/path", schema), "https://example.invalid/path")
            for value in ("secret-marker-not-a-uri", "https://[invalid", "https://example.invalid/%ZZ", "https://example.invalid/\n"):
                error = self.reject("schema_violation", c.validate_schema_data, value, schema)
                self.assertNotIn("secret-marker", str(error))

    def test_unsupported_schema_formats_fail_closed(self):
        self.reject("schema_format", c.validate_schema_data, "anything",
                    {"$schema": c.DIALECT, "type": "string", "format": "uninstalled-custom-format"})
        # Schema-like annotation values are data unless reached through a reference.
        schema = {"$schema": c.DIALECT, "type": "string", "default": {"format": "annotation-only"}}
        self.assertEqual(c.validate_schema_data("valid", schema), "valid")
        schema["$ref"] = "#/default"
        self.reject("schema_format", c.validate_schema_data, "valid", schema)

    def test_missing_explicit_format_dependency_is_not_silent(self):
        original = c.importlib.import_module

        def missing(name):
            if name == "rfc3339_validator":
                raise ImportError("secret-marker-installation-path")
            return original(name)

        with mock.patch.object(c.importlib, "import_module", side_effect=missing):
            error = self.reject("dependency_missing", c.validate_envelope, self.request)
        self.assertNotIn("secret-marker", str(error))
        self.assertIn("runtime/control-requirements.txt", str(error))

    def test_digest_detects_payload_mutation(self):
        self.request["payload"]["scope"]["issue"] = "changed-issue"
        self.reject("digest_mismatch", c.validate_envelope, self.request)

    def test_scope_fields_must_be_exact_shape(self):
        del self.request["payload"]["scope"]["environment"]
        self.reject("schema_violation", c.validate_envelope, self.seal(self.request))

    def test_timestamp_order_and_budget_validity(self):
        self.request["payload"]["expires_at"] = self.request["payload"]["issued_at"]
        self.reject("timestamp_order", c.validate_envelope, self.seal(self.request))
        self.request = c.read_json(FIXTURES / "action-request.json")
        self.request["payload"]["budget"]["timeout_seconds"] = 301
        self.reject("request_limits", c.validate_envelope, self.seal(self.request))

    def test_request_budget_schema_limits(self):
        self.request["payload"]["budget"]["max_attempts"] = 4
        self.reject("schema_violation", c.validate_envelope, self.seal(self.request))

    def test_artifact_ids_unique_and_ordered(self):
        artifact = self.request["payload"]["artifacts"][0]
        self.request["payload"]["artifacts"].append(copy.deepcopy(artifact))
        self.reject("artifact_order", c.validate_envelope, self.seal(self.request))
        self.request["payload"]["artifacts"][1]["id"] = "a-before-fixture"
        self.reject("artifact_order", c.validate_envelope, self.seal(self.request))

    def test_parameters_must_reference_bound_artifacts(self):
        self.request["payload"]["parameters"]["owned_manifest_digest"] = "sha256:" + "a" * 64
        self.reject("artifact_link", c.validate_envelope, self.seal(self.request))
        self.request["payload"].update(adapter="external.export", parameters={
            "destination_id": "fixture-destination", "artifact_id": "missing-artifact", "data_classification": "internal"})
        self.reject("artifact_link", c.validate_envelope, self.seal(self.request))

    def test_canonical_paths_and_unique_order(self):
        self.request["payload"].update(adapter="workspace.inspect", parameters={"paths": ["b", "a"]})
        self.reject("path_order", c.validate_envelope, self.seal(self.request))
        self.request["payload"]["parameters"]["paths"] = ["a//b"]
        self.reject("path_invalid", c.validate_envelope, self.seal(self.request))

    def test_branch_is_not_option_or_invalid_ref(self):
        for branch in ("--force", "main..other", "refs/.hidden", "main.lock"):
            self.request["payload"]["parameters"]["branch"] = branch
            self.reject("target_invalid", c.validate_envelope, self.seal(self.request))

    def test_success_requires_postcondition_and_digest(self):
        value = self.receipt()
        value["payload"]["readback_status"] = "failed"
        self.reject("schema_violation", c.validate_envelope, self.seal(value))
        value = self.receipt()
        value["payload"]["after_state_digest"] = None
        self.reject("schema_violation", c.validate_envelope, self.seal(value))

    def test_receipt_time_order(self):
        value = self.receipt()
        value["payload"]["finished_at"] = "2026-10-28T06:29:59Z"
        self.reject("timestamp_order", c.validate_envelope, self.seal(value))

    def test_malformed_schema_fails_safely(self):
        self.reject("schema_invalid", c.validate_schema_data, {}, {"$schema": c.DIALECT, "type": "nonsense"})
        self.reject("schema_invalid", c.validate_schema_data, {}, {"type": "object"})

    def test_referenced_extension_subschema_is_meta_validated_safely(self):
        marker = "synthetic-private-marker-not-email"
        schema = {"$schema": c.DIALECT, "extension": {"type": "not-a-real-type"}, "$ref": "#/extension"}
        try:
            c.validate_schema_data(marker, schema)
        except c.ControlContractError as error:
            self.assertEqual(error.code, "schema_invalid")
            self.assertNotIn(marker, str(error))
            self.assertNotIn(marker, "".join(traceback.format_exception(error)))
        else:
            self.fail("Malformed referenced schema must be rejected")

    def test_referenced_external_ref_and_dialect_cannot_hide_in_annotations(self):
        schema = {"$schema": c.DIALECT, "extension": {"$ref": "https://example.invalid/schema"}, "$ref": "#/extension"}
        self.reject("schema_reference", c.validate_schema_data, {}, schema)
        schema["extension"] = {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object"}
        self.reject("schema_invalid", c.validate_schema_data, {}, schema)

    def test_external_refs_never_retrieve(self):
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("Network must not be used")), \
             mock.patch("socket.create_connection", side_effect=AssertionError("Network must not be used")):
            self.reject("schema_reference", c.validate_schema_data, {}, {"$schema": c.DIALECT, "$ref": "https://example.invalid/private"})
            self.reject("schema_reference", c.validate_schema_data, {}, {"$schema": c.DIALECT, "$dynamicRef": "#scope"})
            self.reject("schema_reference", c.validate_schema_data, {}, {"$schema": c.DIALECT, "$ref": "#/$defs/missing"})

    def test_supplied_local_schema_dictionary_works(self):
        schema = {"$schema": c.DIALECT, "$id": "urn:fixture:schema", "$defs": {"value": {"type": "integer"}}, "$ref": "#/$defs/value"}
        self.assertEqual(c.validate_schema_data(3, schema), 3)
        self.reject("schema_violation", c.validate_schema_data, "three", schema)

    def test_missing_dependency_has_actionable_safe_message(self):
        original = c.importlib.import_module

        def missing(name):
            if name == "rfc8785":
                raise ImportError("secret installation path")
            return original(name)

        with mock.patch.object(c.importlib, "import_module", side_effect=missing):
            error = self.reject("dependency_missing", c.canonical_digest, {})
        self.assertIn("runtime/control-requirements.txt", str(error))
        self.assertNotIn("secret installation path", str(error))


if __name__ == "__main__":
    unittest.main()
