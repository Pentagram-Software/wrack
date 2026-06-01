#!/usr/bin/env python3
"""smoke_test.py — GCS access smoke test for CatRecognizer service accounts.

PEN-24: Verifies that the provisioned service accounts can perform their
expected GCS operations.  Designed to be run after setup-iam.sh.

Usage
-----
# Data collector SA — should have objectAdmin on training-data bucket:
GOOGLE_APPLICATION_CREDENTIALS=keys/cat-recognizer-data-key.json \\
  python3 cloud/cat-recognizer/smoke_test.py \\
  --bucket=<PROJECT>-cat-recognizer-training-data --mode=data

# Trainer SA — should have objectViewer on training-data, objectAdmin on models:
GOOGLE_APPLICATION_CREDENTIALS=keys/cat-recognizer-trainer-key.json \\
  python3 cloud/cat-recognizer/smoke_test.py \\
  --bucket-data=<PROJECT>-cat-recognizer-training-data \\
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
import tempfile
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
) -> Optional[str]:
    """Upload a small test file; return the blob name on success, None on failure."""
    blob_name = f"_smoke-test/{uuid.uuid4().hex}.txt"
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


# ── Mode-specific test suites ──────────────────────────────────────────────────

def run_data_mode(bucket_training: str) -> _Counter:
    """
    Test the cat-recognizer-data SA:
      - objectAdmin on training-data bucket → can list, write, read
    """
    print(f"\nMode: data  (bucket: gs://{bucket_training})")
    counter = _Counter()
    client = _gcs_client()

    check_list_objects(client, bucket_training, counter)
    blob_name = check_write_object(client, bucket_training, counter)
    if blob_name:
        check_read_object(client, bucket_training, blob_name, counter)
        cleanup_object(client, bucket_training, blob_name)

    return counter


def run_trainer_mode(bucket_training: str, bucket_models: str) -> _Counter:
    """
    Test the cat-recognizer-trainer SA:
      - objectViewer on training-data bucket → can list and read, but NOT write
      - objectAdmin on models bucket         → can list, write, read
    """
    print(f"\nMode: trainer")
    print(f"  training-data bucket: gs://{bucket_training}")
    print(f"  models bucket:        gs://{bucket_models}")
    counter = _Counter()
    client = _gcs_client()

    # Training-data: read-only checks
    check_list_objects(client, bucket_training, counter)
    check_denied_write(client, bucket_training, counter)

    # Models bucket: full write checks
    check_list_objects(client, bucket_models, counter)
    blob_name = check_write_object(client, bucket_models, counter)
    if blob_name:
        check_read_object(client, bucket_models, blob_name, counter)
        cleanup_object(client, bucket_models, blob_name)

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
        "--bucket",
        metavar="BUCKET",
        help="Bucket name to test (used for --mode=data as the training-data bucket).",
    )
    p.add_argument(
        "--bucket-data",
        metavar="BUCKET_DATA",
        dest="bucket_data",
        help="Training-data bucket name (used for --mode=trainer).",
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
) -> tuple[str, str]:
    """Return (bucket_training, bucket_models) resolved from CLI args or defaults."""
    project = args.project
    default_training = f"{project}-cat-recognizer-training-data"
    default_models = f"{project}-cat-recognizer-models"

    if args.mode == "data":
        training = args.bucket or default_training
        models = default_models
    else:  # trainer
        training = args.bucket_data or default_training
        models = args.bucket_models or default_models

    return training, models


def main() -> int:
    args = _parse_args()
    bucket_training, bucket_models = _derive_bucket_names(args)

    print("=" * 50)
    print("  CatRecognizer GCS Smoke Test (PEN-24)")
    print("=" * 50)
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "(default credentials)")
    print(f"  Credentials: {creds_path}")

    if args.mode == "data":
        counter = run_data_mode(bucket_training)
    else:
        counter = run_trainer_mode(bucket_training, bucket_models)

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
