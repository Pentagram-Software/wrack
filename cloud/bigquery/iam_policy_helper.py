#!/usr/bin/env python3
"""
BigQuery dataset-level IAM policy helper.

Reads a JSON IAM policy from stdin, adds (or verifies) a member/role binding,
and writes the updated policy to stdout.  Designed to be called from setup-iam.sh
so that the JSON manipulation stays testable and shell-agnostic.

Usage:
    bq get-iam-policy PROJECT:DATASET | python3 iam_policy_helper.py MEMBER ROLE | \
        bq set-iam-policy PROJECT:DATASET /dev/stdin

    MEMBER  — IAM principal, e.g. serviceAccount:foo@project.iam.gserviceaccount.com
    ROLE    — IAM role URI, e.g. roles/bigquery.dataEditor
"""

import json
import sys


def add_binding(policy: dict, role: str, member: str) -> tuple[dict, bool]:
    """Add *member* to *role* binding in *policy*.

    Returns (updated_policy, was_changed).  Idempotent — returns was_changed=False
    if the binding already contains the member.
    """
    bindings: list[dict] = policy.setdefault("bindings", [])

    for binding in bindings:
        if binding.get("role") == role:
            members: list[str] = binding.setdefault("members", [])
            if member in members:
                return policy, False
            members.append(member)
            return policy, True

    bindings.append({"role": role, "members": [member]})
    return policy, True


def remove_binding(policy: dict, role: str, member: str) -> tuple[dict, bool]:
    """Remove *member* from *role* binding.  Returns (updated_policy, was_changed)."""
    bindings: list[dict] = policy.get("bindings", [])

    for binding in bindings:
        if binding.get("role") == role:
            members: list[str] = binding.get("members", [])
            if member in members:
                members.remove(member)
                return policy, True

    return policy, False


def has_binding(policy: dict, role: str, member: str) -> bool:
    """Return True if *member* already holds *role* in *policy*."""
    for binding in policy.get("bindings", []):
        if binding.get("role") == role and member in binding.get("members", []):
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    if len(args) < 2:
        print(
            f"Usage: {sys.argv[0]} <member> <role>",
            file=sys.stderr,
        )
        print(
            "  Reads JSON IAM policy from stdin, writes updated policy to stdout.",
            file=sys.stderr,
        )
        return 1

    member = args[0]
    role = args[1]

    try:
        policy = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"ERROR: could not parse JSON from stdin: {exc}", file=sys.stderr)
        return 2

    updated, changed = add_binding(policy, role, member)

    if not changed:
        print(
            f"INFO: {member} already has {role} — no change needed.",
            file=sys.stderr,
        )

    print(json.dumps(updated, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
