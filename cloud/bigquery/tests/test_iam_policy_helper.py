"""
Unit tests for cloud/bigquery/iam_policy_helper.py

Run from workspace root:
    python -m pytest cloud/bigquery/tests/test_iam_policy_helper.py -v
"""
import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

# Load the module under test without it needing to be in a Python package
_MODULE_PATH = Path(__file__).parent.parent / "iam_policy_helper.py"
_spec = importlib.util.spec_from_file_location("iam_policy_helper", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

add_binding = _mod.add_binding
remove_binding = _mod.remove_binding
has_binding = _mod.has_binding
main = _mod.main

# ── Fixtures ─────────────────────────────────────────────────────────────────

MEMBER = "serviceAccount:telemetry-writer@wrack-control.iam.gserviceaccount.com"
ROLE = "roles/bigquery.dataEditor"


def empty_policy() -> dict:
    return {}


def policy_with_other_role() -> dict:
    return {
        "bindings": [
            {"role": "roles/bigquery.dataViewer", "members": ["serviceAccount:other@project.iam.gserviceaccount.com"]}
        ]
    }


def policy_with_same_role_other_member() -> dict:
    return {
        "bindings": [
            {"role": ROLE, "members": ["serviceAccount:other@project.iam.gserviceaccount.com"]}
        ]
    }


def policy_already_has_member() -> dict:
    return {
        "bindings": [
            {"role": ROLE, "members": [MEMBER]}
        ]
    }


# ── add_binding ───────────────────────────────────────────────────────────────

class TestAddBinding:
    def test_adds_binding_to_empty_policy(self):
        policy, changed = add_binding(empty_policy(), ROLE, MEMBER)
        assert changed is True
        assert has_binding(policy, ROLE, MEMBER)

    def test_adds_member_to_existing_role_binding(self):
        policy, changed = add_binding(policy_with_same_role_other_member(), ROLE, MEMBER)
        assert changed is True
        assert has_binding(policy, ROLE, MEMBER)
        # Original member must still be present
        assert has_binding(policy, ROLE, "serviceAccount:other@project.iam.gserviceaccount.com")

    def test_creates_new_role_binding_when_role_absent(self):
        policy, changed = add_binding(policy_with_other_role(), ROLE, MEMBER)
        assert changed is True
        assert has_binding(policy, ROLE, MEMBER)
        # Other role should be untouched
        assert has_binding(policy, "roles/bigquery.dataViewer", "serviceAccount:other@project.iam.gserviceaccount.com")

    def test_idempotent_when_binding_already_exists(self):
        policy, changed = add_binding(policy_already_has_member(), ROLE, MEMBER)
        assert changed is False
        # Binding still present
        assert has_binding(policy, ROLE, MEMBER)
        # No duplicate members
        for b in policy["bindings"]:
            if b["role"] == ROLE:
                assert policy["bindings"][0]["members"].count(MEMBER) == 1

    def test_does_not_mutate_input_policy_bindings_list(self):
        """add_binding must not silently share mutable state between calls."""
        original = empty_policy()
        policy_a, _ = add_binding(original, ROLE, MEMBER)
        # Calling again should not affect the binding count
        policy_b, changed = add_binding(policy_a, ROLE, MEMBER)
        assert changed is False

    def test_handles_policy_without_bindings_key(self):
        policy = {"version": 1}
        updated, changed = add_binding(policy, ROLE, MEMBER)
        assert changed is True
        assert "bindings" in updated
        assert has_binding(updated, ROLE, MEMBER)


# ── remove_binding ────────────────────────────────────────────────────────────

class TestRemoveBinding:
    def test_removes_existing_member(self):
        policy, changed = remove_binding(policy_already_has_member(), ROLE, MEMBER)
        assert changed is True
        assert not has_binding(policy, ROLE, MEMBER)

    def test_noop_when_member_absent(self):
        policy, changed = remove_binding(empty_policy(), ROLE, MEMBER)
        assert changed is False

    def test_noop_when_role_absent(self):
        policy, changed = remove_binding(policy_with_other_role(), ROLE, MEMBER)
        assert changed is False


# ── has_binding ───────────────────────────────────────────────────────────────

class TestHasBinding:
    def test_true_when_present(self):
        assert has_binding(policy_already_has_member(), ROLE, MEMBER)

    def test_false_when_absent(self):
        assert not has_binding(empty_policy(), ROLE, MEMBER)

    def test_false_for_wrong_role(self):
        assert not has_binding(policy_already_has_member(), "roles/bigquery.dataViewer", MEMBER)

    def test_false_for_wrong_member(self):
        assert not has_binding(policy_already_has_member(), ROLE, "serviceAccount:wrong@x.iam.gserviceaccount.com")


# ── main() CLI ────────────────────────────────────────────────────────────────

class TestMain:
    def _run_main(self, stdin_json: dict, argv: list[str]) -> tuple[int, str]:
        """Run main() with mocked stdin and captured stdout; returns (exit_code, stdout)."""
        input_str = json.dumps(stdin_json)
        captured = io.StringIO()
        original_stdin = sys.stdin
        original_stdout = sys.stdout

        sys.stdin = io.StringIO(input_str)
        sys.stdout = captured
        try:
            rc = main(argv)
        except SystemExit as exc:
            rc = int(exc.code)
        finally:
            sys.stdin = original_stdin
            sys.stdout = original_stdout

        return rc, captured.getvalue()

    def test_returns_updated_policy_as_json(self):
        rc, output = self._run_main(empty_policy(), [MEMBER, ROLE])
        assert rc == 0
        parsed = json.loads(output)
        assert has_binding(parsed, ROLE, MEMBER)

    def test_exits_1_on_missing_args(self):
        rc, _ = self._run_main(empty_policy(), [MEMBER])
        assert rc == 1

    def test_exits_2_on_invalid_json_stdin(self):
        original_stdin = sys.stdin
        sys.stdin = io.StringIO("NOT JSON {{{")
        try:
            rc = main([MEMBER, ROLE])
        except SystemExit as exc:
            rc = int(exc.code)
        finally:
            sys.stdin = original_stdin
        assert rc == 2

    def test_idempotent_run_returns_0(self):
        rc, output = self._run_main(policy_already_has_member(), [MEMBER, ROLE])
        assert rc == 0
        parsed = json.loads(output)
        assert has_binding(parsed, ROLE, MEMBER)
