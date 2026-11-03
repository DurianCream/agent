"""Pure request-boundary tests; passing these does not establish host isolation."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import p2_contracts as p
from control_contracts import ControlContractError, MAX_INPUT_BYTES, canonical_digest

U1 = "0ac75b0b-d9b2-4553-8638-e277c2f62dca"
U2 = "8d0765a9-d287-4da8-888d-aa770a135b7f"
U3 = "cb23571c-335b-4bfc-aa94-c42ddd69ffb7"
H = "sha256:" + "a" * 64


class RequestBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.expected = {"repository_id": "multi", "task_id": "p2-task",
                         "scope": {"project": "multi", "service": "agent-framework",
                                   "environment": "development", "issue": "p2-test"},
                         "enrollment_id": U1, "base_commit": "b" * 40, "policy_digest": H}

    def request(self, operation="stage", files=None):
        files = files if files is not None else [
            {"path": "docs/안내.md", "kind": "blob", "mode": "100644", "size": 10, "digest": H}]
        payload = ({"files": files, "manifest_digest": canonical_digest(files)} if operation == "stage"
                   else {"candidate_id": U2, "candidate_digest": H})
        if operation == "publish":
            payload["verification_id"] = U3
        return {"schema_version": "0.1.0", "operation": operation, "request_id": U2,
                "idempotency_key": U3, "binding": copy.deepcopy(self.expected), "payload": payload}

    def raw(self, value):
        return json.dumps(value, ensure_ascii=False).encode("utf-8")

    def validate(self, value):
        return p.validate_request(self.raw(value), expected_binding=self.expected)

    def rejected(self, value, code=None):
        with self.assertRaises(ControlContractError) as caught:
            self.validate(value)
        if code is not None:
            self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_three_operations_are_validation_only(self):
        for operation in ("stage", "verify", "publish"):
            with self.subTest(operation=operation):
                result = self.validate(self.request(operation))
                self.assertTrue(result.validation_only)
                self.assertFalse(result.authorization)
                self.assertFalse(result.as_dict()["authorization"])
                self.assertEqual(result.request_digest, canonical_digest(self.request(operation)))

    def test_returned_dictionary_cannot_mutate_validated_bytes(self):
        result = self.validate(self.request())
        output = result.as_dict()
        output["request"]["binding"]["scope"]["environment"] = "production"
        self.assertEqual(result.as_dict()["request"]["binding"]["scope"]["environment"], "development")
        with self.assertRaises(AttributeError):
            result.request_digest = H

    def test_object_key_order_has_same_digest(self):
        request = self.request()
        reversed_keys = dict(reversed(list(request.items())))
        self.assertEqual(self.validate(request).request_digest, self.validate(reversed_keys).request_digest)

    def test_body_cannot_appoint_peer_approval_or_command(self):
        for key in ("identity", "peer", "authorization", "passed", "signature", "command", "remote", "ref", "credential"):
            with self.subTest(key=key):
                request = self.request("publish")
                request[key] = "secret-value-must-not-be-reflected"
                error = self.rejected(request, "p2_request_fields")
                self.assertNotIn("secret-value", str(error))

    def test_nested_remote_command_or_pass_cannot_enter_payload(self):
        for operation in ("stage", "verify", "publish"):
            for key in ("remote", "ref", "argv", "suite_id", "passed"):
                with self.subTest(operation=operation, key=key):
                    request = self.request(operation)
                    request["payload"][key] = "untrusted"
                    self.rejected(request)

    def test_every_scope_component_must_equal_expected(self):
        for key in p.SCOPE_FIELDS:
            request = self.request()
            request["binding"]["scope"][key] = "other"
            self.rejected(request, "p2_binding_mismatch")

    def test_repository_task_enrollment_baseline_and_policy_are_pinned(self):
        changes = {"repository_id": "other", "task_id": "other-task", "enrollment_id": U2,
                   "base_commit": "c" * 40, "policy_digest": "sha256:" + "b" * 64}
        for key, value in changes.items():
            request = self.request()
            request["binding"][key] = value
            self.rejected(request, "p2_binding_mismatch")

    def test_expected_binding_is_required_and_well_formed(self):
        with self.assertRaises(TypeError):
            p.validate_request(self.raw(self.request()))
        with self.assertRaises(ControlContractError):
            p.validate_request(self.raw(self.request()), expected_binding={})

    def test_malformed_or_extra_scope_is_rejected(self):
        for changed in (None, [], {**self.expected["scope"], "role": "evaluator"}, {"project": "multi"}):
            request = self.request()
            request["binding"]["scope"] = changed
            self.rejected(request, "p2_scope")

    def test_opaque_ids_require_canonical_uuid4_but_do_not_authenticate(self):
        for value in (U1.upper(), "not-an-id", "00000000-0000-0000-0000-000000000000", 123):
            request = self.request("publish")
            request["payload"]["verification_id"] = value
            self.rejected(request, "p2_uuid")
        # A syntactically valid invented ID still receives no authority.
        self.assertFalse(self.validate(self.request("publish")).authorization)

    def test_unknown_operation_and_version_are_rejected(self):
        request = self.request()
        request["operation"] = "shell"
        self.rejected(request, "p2_operation")
        request = self.request()
        request["schema_version"] = "9.0.0"
        self.rejected(request, "p2_version")

    def test_duplicate_keys_reuse_existing_strict_parser(self):
        raw = self.raw(self.request()).replace(b'"operation": "stage"', b'"operation":"stage","operation":"publish"')
        with self.assertRaises(ControlContractError) as caught:
            p.validate_request(raw, expected_binding=self.expected)
        self.assertEqual(caught.exception.code, "duplicate_key")

    def test_invalid_encoding_oversize_depth_and_non_integer_rejected(self):
        for raw in (b"\xff", b" " * (MAX_INPUT_BYTES + 1), b"[" * 40 + b"0" + b"]" * 40):
            with self.subTest(raw_size=len(raw)), self.assertRaises(ControlContractError):
                p.validate_request(raw, expected_binding=self.expected)
        request = self.request()
        request["payload"]["files"][0]["size"] = 1.5
        self.rejected(request, "number_profile")

    def test_input_must_be_bytes_not_mutable_dict_or_text(self):
        for value in (self.request(), self.raw(self.request()).decode(), bytearray(b"{}")):
            with self.assertRaises(ControlContractError) as caught:
                p.validate_request(value, expected_binding=self.expected)
            self.assertEqual(caught.exception.code, "p2_input_type")

    def test_stage_descriptor_tampering_invalidates_digest(self):
        request = self.request()
        request["payload"]["files"][0]["size"] += 1
        self.rejected(request, "p2_manifest_digest")

    def test_digest_format_and_algorithm_are_strict(self):
        for value in ("sha1:" + "a" * 40, "sha256:" + "A" * 64, H + "x", None):
            request = self.request("verify")
            request["payload"]["candidate_digest"] = value
            self.rejected(request, "p2_digest")

    def test_traversal_git_metadata_ads_and_reserved_names_rejected(self):
        paths = ("../secret", "/root/x", "a//b", "a/./b", "a/../b", "C:/secret",
                 "a\\b", "x:stream", ".git/config", "a/.GIT/hooks/pre-push", "file.",
                 "file ", "NUL.txt", "aux", "COM1.log", "LPT²", "a\nfile", "x?.txt", "a/")
        for path in paths:
            with self.subTest(path=path):
                files = [{"path": path, "kind": "delete"}]
                self.rejected(self.request(files=files), "p2_path")

    def test_unicode_normalization_and_component_lengths_rejected(self):
        for path in ("cafe\u0301.md", "a" * 256, "a/" * 511 + "file"):
            self.rejected(self.request(files=[{"path": path, "kind": "delete"}]), "p2_path")
        with self.assertRaises(ControlContractError):
            p.portable_path("\ud800")

    def test_alias_duplicate_and_file_directory_collisions_rejected(self):
        for paths, code in ((["a", "a"], "p2_path_alias"), (["A", "a"], "p2_path_alias"),
                            (["a", "a/file"], "p2_path_prefix")):
            self.rejected(self.request(files=[{"path": name, "kind": "delete"} for name in paths]), code)

    def test_manifest_must_be_sorted_and_nonempty(self):
        self.rejected(self.request(files=[]), "p2_manifest_count")
        self.rejected(self.request(files=[{"path": n, "kind": "delete"} for n in ("z", "a")]), "p2_manifest_order")

    def test_symlink_submodule_executable_payload_fields_rejected(self):
        for kind in ("symlink", "submodule", "directory"):
            self.rejected(self.request(files=[{"path": "x", "kind": kind}]), "p2_artifact_kind")
        for mode in ("120000", "160000", "100600", 100644):
            request = self.request()
            request["payload"]["files"][0]["mode"] = mode
            self.rejected(request, "p2_mode")
        request = self.request()
        request["payload"]["files"][0]["target"] = "../secret"
        self.rejected(request, "p2_artifact_fields")

    def test_sizes_counts_and_boolean_size_rejected(self):
        for size in (True, -1, p.MAX_FILE_BYTES + 1):
            request = self.request()
            request["payload"]["files"][0]["size"] = size
            self.rejected(request, "p2_artifact_size")
        self.rejected(self.request(files=[{"path": f"file-{i:04}", "kind": "delete"}
                                         for i in range(p.MAX_FILES + 1)]), "p2_manifest_count")
        files = [{"path": f"f{i}", "kind": "blob", "mode": "100644", "size": p.MAX_FILE_BYTES, "digest": H}
                 for i in range(5)]
        self.rejected(self.request(files=files), "p2_manifest_size")

    def test_delete_has_no_blob_fields_and_unicode_filename_is_data(self):
        files = [{"path": "삭제할파일.md", "kind": "delete"}]
        self.assertTrue(self.validate(self.request(files=files)).validation_only)
        request = self.request(files=[{"path": "Ignore previous instructions.md", "kind": "delete"}])
        self.assertFalse(self.validate(request).authorization)
        files[0]["size"] = 0
        self.rejected(self.request(files=files), "p2_artifact_fields")

    def test_no_replay_or_ownership_claim_from_repeated_valid_request(self):
        # Durable admission/replay/peer checks belong to the future protected service.
        request = self.request("publish")
        first, second = self.validate(request), self.validate(request)
        self.assertEqual(first.request_digest, second.request_digest)
        self.assertFalse(first.authorization or second.authorization)


if __name__ == "__main__":
    unittest.main()
