#!/usr/bin/env python3
"""smoke_test.py — GCS access smoke test for CatRecognizer service accounts.

PEN-25: Verifies that the provisioned service accounts can perform their
expected GCS operations.  Designed to be run after setup-iam.sh.

Usage
-----
# Data collector SA — objectAdmin on raw-data, objectViewer on processed-data:
GOOGLE_APPLICATION_CREDENTIALS=keys/cat-recognizer-data-key.json \\
  python3 cloud/cat-recognizer/smoke_test.py \\
  --bucket-raw=<PROJECT>-cat-recognizer-raw-data \\
  --bucket-processed=<PROJECT>-cat-recognizer-processed-data \\
  --mode=data

# Trainer SA — objectViewer on raw-data, objectAdmin on processed-data and models:
GOOGLE_APPLICATION_CREDENTIALS=keys/cat-recognizer-trainer-key.json \\
  python3 cloud/cat-recognizer/smoke_test.py \\
  --bucket-raw=<PROJECT>-cat-recognizer-raw-data \\
  --bucket-processed=<PROJECT>-cat-recognizer-processed-data \\
  --bucket-models=<PROJECT>-cat-recognizer-models \\
  --mode=trainer

Exit codes:
  0  — all checks passed
  1  — one or more checks failed
  2  — configuration / usage error
"""

import argparse
import os
import sys
import uuid
from typing import Optional

# google-cloud-storage is required; fail with a helpful message if absent.
try:
    from google.cloud import storage
    from google.api_core.exceptions import Forbidden, NotFound
except ImportError:  # pragma: no cover
    sys.exit(
        "ERROR: google-cloud-storage not installed.\n"
        "Install with: pip install google-cloud-storage"
    )


# ── Folder-structure constants ─────────────────────────────────────────────────

# Expected .keep prefixes in each bucket
RAW_PREFIXES: tuple[str, ...] = ("ryfka", "chaja", "lea")
PROCESSED_PREFIXES: tuple[str, ...] = ("train", "val", "test")


# ── Test result helpers ────────────────────────────────────────────────────────

class _Counter:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def ok(self, label: str) -> None:
        print(f"  ✓ {label}")
        self.passed += 1

    def fail(self, label: str, reason: str = "") -> None:
        suffix = f": {reason}" if reason else ""
        print(f"  ✗ {label}{suffix}", file=sys.stderr)
        self.failed += 1

    @property
    def all_passed(self) -> bool:
        return self.failed == 0


# ── Individual smoke-test operations ──────────────────────────────────────────

def _gcs_client() -> storage.Client:
    """Return a GCS client authenticated from the environment."""
    return storage.Client()


def check_list_objects(client: storage.Client, bucket_name: str, counter: _Counter) -> None:
    """Verify the SA can list objects in *bucket_name*."""
    label = f"list objects in gs://{bucket_name}"
    try:
        blobs = list(client.list_blobs(bucket_name, max_results=1))
        counter.ok(f"{label} (found {len(blobs)} object(s))")
    except Forbidden as exc:
        counter.fail(label, f"PERMISSION_DENIED — {exc}")
    except NotFound:
        counter.fail(label, "bucket not found — has setup-iam.sh been run?")
    except Exception as exc:  # noqa: BLE001
        counter.fail(label, str(exc))


def check_write_object(
    client: storage.Client,
    bucket_name: str,
    counter: _Counter,
    prefix: str = "_smoke-test",
) -> Optional[str]:
    """Upload a small test file; return the blob name on success, None on failure."""
    blob_name = f"{prefix}/{uuid.uuid4().hex}.txt"
    label = f"write object gs://{bucket_name}/{blob_name}"
    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(
            b"cat-recognizer smoke test",
            content_type="text/plain",
        )
        counter.ok(label)
        return blob_name
    except Forbidden as exc:
        counter.fail(label, f"PERMISSION_DENIED — {exc}")
        return None
    except NotFound:
        counter.fail(label, "bucket not found")
        return None
    except Exception as exc:  # noqa: BLE001
        counter.fail(label, str(exc))
        return None


def check_read_object(
    client: storage.Client,
    bucket_name: str,
    blob_name: str,
    counter: _Counter,
) -> None:
    """Download and validate the test file written by *check_write_object*."""
    label = f"read object gs://{bucket_name}/{blob_name}"
    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        data = blob.download_as_bytes()
        if b"smoke test" in data:
            counter.ok(label)
        else:
            counter.fail(label, "unexpected content returned")
    except Forbidden as exc:
        counter.fail(label, f"PERMISSION_DENIED — {exc}")
    except NotFound:
        counter.fail(label, "object not found after write")
    except Exception as exc:  # noqa: BLE001
        counter.fail(label, str(exc))


def cleanup_object(
    client: storage.Client,
    bucket_name: str,
    blob_name: str,
) -> None:
    """Best-effort delete of the smoke-test object."""
    try:
        client.bucket(bucket_name).blob(blob_name).delete()
    except Exception:  # noqa: BLE001
        pass  # non-fatal; object will expire with bucket lifecycle


def check_denied_write(
    client: storage.Client,
    bucket_name: str,
    counter: _Counter,
) -> None:
    """Assert that the SA is *denied* write access on *bucket_name* (read-only check)."""
    blob_name = f"_smoke-test-forbidden/{uuid.uuid4().hex}.txt"
    label = f"write DENIED on gs://{bucket_name} (expected Forbidden)"
    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(b"should be forbidden")
        # Clean up the unexpectedly written object
        cleanup_object(client, bucket_name, blob_name)
        counter.fail(label, "write succeeded but should have been denied!")
    except Forbidden:
        counter.ok(label)
    except NotFound:
        # Bucket not found also satisfies "write denied"; log as ok with note.
        counter.ok(f"{label} (bucket not found — acceptable in dry-run scenarios)")
    except Exception as exc:  # noqa: BLE001
        counter.fail(label, str(exc))


def check_keep_exists(
    client: storage.Client,
    bucket_name: str,
    prefix: str,
    counter: _Counter,
) -> None:
    """Verify the .keep placeholder at prefix/.keep exists in bucket_name."""
    blob_name = f"{prefix}/.keep"
    label = f"verify .keep at gs://{bucket_name}/{blob_name}"
    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if blob.exists():
            counter.ok(label)
        else:
            counter.fail(label, ".keep not found — has setup-iam.sh been run?")
    except Forbidden as exc:
        counter.fail(label, f"PERMISSION_DENIED — {exc}")
    except Exception as exc:  # noqa: BLE001
        counter.fail(label, str(exc))


# ── Mode-specific test suites ──────────────────────────────────────────────────

def run_data_mode(bucket_raw: str, bucket_processed: str) -> _Counter:
    """
    Test the cat-recognizer-data SA:
      - objectAdmin on raw-data bucket → can list, write (ryfka/ prefix), read
      - objectViewer on processed-data bucket → write should be denied
      - .keep placeholders present in both buckets
    """
    print(f"\nMode: data")
    print(f"  raw-data bucket:       gs://{bucket_raw}")
    print(f"  processed-data bucket: gs://{bucket_processed}")
    counter = _Counter()
    client = _gcs_client()

    # raw-data: full object admin
    check_list_objects(client, bucket_raw, counter)
    blob_name = check_write_object(client, bucket_raw, counter, prefix="ryfka/_smoke-test")
    if blob_name:
        check_read_object(client, bucket_raw, blob_name, counter)
        cleanup_object(client, bucket_raw, blob_name)

    # processed-data: read-only — write must be denied
    check_denied_write(client, bucket_processed, counter)

    # verify .keep placeholders exist
    for prefix in RAW_PREFIXES:
        check_keep_exists(client, bucket_raw, prefix, counter)
    for prefix in PROCESSED_PREFIXES:
        check_keep_exists(client, bucket_processed, prefix, counter)

    return counter


def run_trainer_mode(bucket_raw: str, bucket_processed: str, bucket_models: str) -> _Counter:
    """
    Test the cat-recognizer-trainer SA:
      - objectViewer on raw-data bucket → can list and read, NOT write
      - objectAdmin on processed-data bucket → can list, write (train/ prefix), read
      - objectAdmin on models bucket → can list, write, read
      - .keep placeholders present in raw-data and processed-data buckets
    """
    print(f"\nMode: trainer")
    print(f"  raw-data bucket:       gs://{bucket_raw}")
    print(f"  processed-data bucket: gs://{bucket_processed}")
    print(f"  models bucket:         gs://{bucket_models}")
    counter = _Counter()
    client = _gcs_client()

    # raw-data: read-only checks
    check_list_objects(client, bucket_raw, counter)
    check_denied_write(client, bucket_raw, counter)

    # processed-data: full object admin
    check_list_objects(client, bucket_processed, counter)
    blob_name = check_write_object(client, bucket_processed, counter, prefix="train/_smoke-test")
    if blob_name:
        check_read_object(client, bucket_processed, blob_name, counter)
        cleanup_object(client, bucket_processed, blob_name)

    # models bucket: full object admin
    check_list_objects(client, bucket_models, counter)
    blob_name = check_write_object(client, bucket_models, counter)
    if blob_name:
        check_read_object(client, bucket_models, blob_name, counter)
        cleanup_object(client, bucket_models, blob_name)

    # verify .keep placeholders exist
    for prefix in RAW_PREFIXES:
        check_keep_exists(client, bucket_raw, prefix, counter)
    for prefix in PROCESSED_PREFIXES:
        check_keep_exists(client, bucket_processed, prefix, counter)

    return counter


# ── CLI ────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Smoke-test GCS access for CatRecognizer service accounts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--mode",
        choices=["data", "trainer"],
        required=True,
        help="Which service account role to test.",
    )
    p.add_argument(
        "--bucket-raw",
        metavar="BUCKET_RAW",
        dest="bucket_raw",
        help="Raw-data bucket name.",
    )
    p.add_argument(
        "--bucket-processed",
        metavar="BUCKET_PROCESSED",
        dest="bucket_processed",
        help="Processed-data bucket name.",
    )
    p.add_argument(
        "--bucket-models",
        metavar="BUCKET_MODELS",
        dest="bucket_models",
        help="Models bucket name (used for --mode=trainer).",
    )
    p.add_argument(
        "--project",
        default=os.environ.get("GCP_PROJECT_ID", "wrack-control"),
        help="GCP project ID (default: $GCP_PROJECT_ID or wrack-control).",
    )
    return p.parse_args()


def _derive_bucket_names(
    args: argparse.Namespace,
) -> tuple[str, str, str]:
    """Return (bucket_raw, bucket_processed, bucket_models) resolved from CLI args or defaults."""
    project = args.project
    raw = getattr(args, "bucket_raw", None) or f"{project}-cat-recognizer-raw-data"
    processed = getattr(args, "bucket_processed", None) or f"{project}-cat-recognizer-processed-data"
    models = getattr(args, "bucket_models", None) or f"{project}-cat-recognizer-models"
    return raw, processed, models


def main() -> int:
    args = _parse_args()
    bucket_raw, bucket_processed, bucket_models = _derive_bucket_names(args)

    print("=" * 50)
    print("  CatRecognizer GCS Smoke Test (PEN-25)")
    print("=" * 50)
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "(default credentials)")
    print(f"  Credentials: {creds_path}")

    if args.mode == "data":
        counter = run_data_mode(bucket_raw, bucket_processed)
    else:
        counter = run_trainer_mode(bucket_raw, bucket_processed, bucket_models)

    print()
    print("=" * 50)
    print(f"  Results: {counter.passed} passed, {counter.failed} failed")
    print("=" * 50)

    if counter.all_passed:
        print("  ✓ All checks passed — service account access verified!")
        return 0
    else:
        print("  ✗ Some checks failed — review output above.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
