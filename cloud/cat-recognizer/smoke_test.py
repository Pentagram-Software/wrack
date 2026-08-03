#!/usr/bin/env python3
"""Smoke test for CatRecognizer Phase 2 GCS infra (PEN-193, task 5.4).

Verifies each service account's expected read/write access per bucket,
per `setup-infra.sh`'s IAM matrix. Run this **after** `setup-infra.sh` and
after downloading a JSON key for each service account (this session did not
provision real infra, so this hasn't been run against real GCP — see
README.md's "not yet run" note).

Usage::

    python3 smoke_test.py --project wrack-control \\
        --data-key path/to/data-collector-key.json \\
        --trainer-key path/to/trainer-export-key.json

Expected outcome:

- data-collector: write succeeds on raw-data, write FAILS on processed-data
  (read-only there).
- trainer-export: write succeeds on processed-data and models, write FAILS
  on raw-data (read-only there).
"""

from __future__ import annotations

import argparse
import sys


def _bucket_names(project: str) -> dict:
    return {
        "raw": "{}-cat-recognizer-raw-data".format(project),
        "processed": "{}-cat-recognizer-processed-data".format(project),
        "models": "{}-cat-recognizer-models".format(project),
    }


def _client_for_key(key_path: str):
    from google.cloud import storage
    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_file(key_path)
    return storage.Client(credentials=credentials, project=credentials.project_id)


def _can_write(client, bucket_name: str) -> bool:
    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob("_smoke_test/probe.txt")
        blob.upload_from_string("smoke test probe")
        blob.delete()
        return True
    except Exception as exc:  # noqa: BLE001 - report any permission/API failure as "can't write"
        print("    (write attempt failed: {})".format(exc))
        return False


def check_data_collector(project: str, key_path: str) -> bool:
    print("Checking cat-recognizer-data-collector...")
    client = _client_for_key(key_path)
    buckets = _bucket_names(project)

    ok = True
    print("  raw-data (expect: can write)")
    if _can_write(client, buckets["raw"]):
        print("    OK")
    else:
        print("    FAIL — expected write access to raw-data")
        ok = False

    print("  processed-data (expect: read-only, write must fail)")
    if not _can_write(client, buckets["processed"]):
        print("    OK (write correctly denied)")
    else:
        print("    FAIL — data-collector should NOT be able to write to processed-data")
        ok = False

    return ok


def check_trainer_export(project: str, key_path: str) -> bool:
    print("Checking cat-recognizer-trainer-export...")
    client = _client_for_key(key_path)
    buckets = _bucket_names(project)

    ok = True
    print("  raw-data (expect: read-only, write must fail)")
    if not _can_write(client, buckets["raw"]):
        print("    OK (write correctly denied)")
    else:
        print("    FAIL — trainer-export should NOT be able to write to raw-data")
        ok = False

    for name in ("processed", "models"):
        print("  {}-data (expect: can write)".format(name))
        if _can_write(client, buckets[name]):
            print("    OK")
        else:
            print("    FAIL — expected write access to {}".format(name))
            ok = False

    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--data-key", help="Path to the data-collector service account JSON key")
    parser.add_argument("--trainer-key", help="Path to the trainer-export service account JSON key")
    args = parser.parse_args()

    if not args.data_key and not args.trainer_key:
        parser.error("pass at least one of --data-key / --trainer-key")

    all_ok = True
    if args.data_key:
        all_ok = check_data_collector(args.project, args.data_key) and all_ok
    if args.trainer_key:
        all_ok = check_trainer_export(args.project, args.trainer_key) and all_ok

    if not all_ok:
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
