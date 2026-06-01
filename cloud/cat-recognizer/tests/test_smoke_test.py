"""Unit tests for cloud/cat-recognizer/smoke_test.py.

Tests use unittest.mock to patch google.cloud.storage so no real GCP
credentials or network access are required.
"""

import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# Provide a minimal stub for google.cloud.storage and google.api_core.exceptions
# so that smoke_test.py can be imported without the real SDK installed.
# ---------------------------------------------------------------------------

def _make_google_stubs() -> None:
    """Inject minimal google.* stubs into sys.modules if the real package is absent."""
    if "google.cloud.storage" in sys.modules:
        return  # real package available — no stub needed

    google = types.ModuleType("google")
    google_cloud = types.ModuleType("google.cloud")
    google_cloud_storage = types.ModuleType("google.cloud.storage")
    google_api_core = types.ModuleType("google.api_core")
    google_api_core_exceptions = types.ModuleType("google.api_core.exceptions")

    class Forbidden(Exception):
        pass

    class NotFound(Exception):
        pass

    google_api_core_exceptions.Forbidden = Forbidden
    google_api_core_exceptions.NotFound = NotFound

    # Minimal Client stub
    google_cloud_storage.Client = MagicMock

    google.cloud = google_cloud
    google_cloud.storage = google_cloud_storage
    google.api_core = google_api_core
    google_api_core.exceptions = google_api_core_exceptions

    sys.modules.update(
        {
            "google": google,
            "google.cloud": google_cloud,
            "google.cloud.storage": google_cloud_storage,
            "google.api_core": google_api_core,
            "google.api_core.exceptions": google_api_core_exceptions,
        }
    )


_make_google_stubs()

# Now import the module under test.
_MODULE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_MODULE_DIR))
import smoke_test as st  # noqa: E402

# Convenience aliases to the exception classes used inside smoke_test
Forbidden = sys.modules["google.api_core.exceptions"].Forbidden
NotFound = sys.modules["google.api_core.exceptions"].NotFound


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_client(
    list_blobs_side_effect=None,
    upload_side_effect=None,
    download_side_effect=None,
    delete_side_effect=None,
):
    """Build a mock storage.Client whose bucket().blob() chain is pre-wired."""
    blob = MagicMock()
    if upload_side_effect is not None:
        blob.upload_from_string.side_effect = upload_side_effect
    if download_side_effect is not None:
        blob.download_as_bytes.side_effect = download_side_effect
    if delete_side_effect is not None:
        blob.delete.side_effect = delete_side_effect
    else:
        blob.download_as_bytes.return_value = b"cat-recognizer smoke test"

    bucket = MagicMock()
    bucket.blob.return_value = blob

    client = MagicMock()
    client.bucket.return_value = bucket
    if list_blobs_side_effect is not None:
        client.list_blobs.side_effect = list_blobs_side_effect
    else:
        client.list_blobs.return_value = iter([])  # empty bucket is fine

    return client, bucket, blob


# ---------------------------------------------------------------------------
# _Counter
# ---------------------------------------------------------------------------

class TestCounter(unittest.TestCase):
    def test_initial_state(self):
        c = st._Counter()
        self.assertEqual(c.passed, 0)
        self.assertEqual(c.failed, 0)
        self.assertTrue(c.all_passed)

    def test_ok_increments_passed(self):
        c = st._Counter()
        c.ok("list objects")
        self.assertEqual(c.passed, 1)
        self.assertEqual(c.failed, 0)

    def test_fail_increments_failed(self):
        c = st._Counter()
        c.fail("write object", "PERMISSION_DENIED")
        self.assertEqual(c.passed, 0)
        self.assertEqual(c.failed, 1)
        self.assertFalse(c.all_passed)

    def test_all_passed_mixed(self):
        c = st._Counter()
        c.ok("a")
        c.ok("b")
        c.fail("c")
        self.assertFalse(c.all_passed)


# ---------------------------------------------------------------------------
# check_list_objects
# ---------------------------------------------------------------------------

class TestCheckListObjects(unittest.TestCase):
    def test_success(self):
        client, _, _ = _mock_client()
        c = st._Counter()
        st.check_list_objects(client, "my-bucket", c)
        self.assertEqual(c.passed, 1)
        self.assertEqual(c.failed, 0)

    def test_forbidden(self):
        client, _, _ = _mock_client(list_blobs_side_effect=Forbidden("denied"))
        c = st._Counter()
        st.check_list_objects(client, "my-bucket", c)
        self.assertEqual(c.failed, 1)

    def test_not_found(self):
        client, _, _ = _mock_client(list_blobs_side_effect=NotFound("no bucket"))
        c = st._Counter()
        st.check_list_objects(client, "my-bucket", c)
        self.assertEqual(c.failed, 1)

    def test_unexpected_exception(self):
        client, _, _ = _mock_client(list_blobs_side_effect=RuntimeError("network error"))
        c = st._Counter()
        st.check_list_objects(client, "my-bucket", c)
        self.assertEqual(c.failed, 1)


# ---------------------------------------------------------------------------
# check_write_object
# ---------------------------------------------------------------------------

class TestCheckWriteObject(unittest.TestCase):
    def test_success_returns_blob_name(self):
        client, _, _ = _mock_client()
        c = st._Counter()
        result = st.check_write_object(client, "my-bucket", c)
        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("_smoke-test/"))
        self.assertEqual(c.passed, 1)

    def test_forbidden_returns_none(self):
        client, _, _ = _mock_client(upload_side_effect=Forbidden("denied"))
        c = st._Counter()
        result = st.check_write_object(client, "my-bucket", c)
        self.assertIsNone(result)
        self.assertEqual(c.failed, 1)

    def test_not_found_returns_none(self):
        client, _, _ = _mock_client(upload_side_effect=NotFound("no bucket"))
        c = st._Counter()
        result = st.check_write_object(client, "my-bucket", c)
        self.assertIsNone(result)
        self.assertEqual(c.failed, 1)


# ---------------------------------------------------------------------------
# check_read_object
# ---------------------------------------------------------------------------

class TestCheckReadObject(unittest.TestCase):
    def test_success(self):
        client, _, blob = _mock_client()
        blob.download_as_bytes.return_value = b"cat-recognizer smoke test"
        c = st._Counter()
        st.check_read_object(client, "my-bucket", "_smoke-test/abc.txt", c)
        self.assertEqual(c.passed, 1)

    def test_unexpected_content(self):
        client, _, blob = _mock_client()
        blob.download_as_bytes.return_value = b"something else entirely"
        c = st._Counter()
        st.check_read_object(client, "my-bucket", "_smoke-test/abc.txt", c)
        self.assertEqual(c.failed, 1)

    def test_forbidden(self):
        client, _, blob = _mock_client()
        blob.download_as_bytes.side_effect = Forbidden("denied")
        c = st._Counter()
        st.check_read_object(client, "my-bucket", "_smoke-test/abc.txt", c)
        self.assertEqual(c.failed, 1)

    def test_not_found(self):
        client, _, blob = _mock_client()
        blob.download_as_bytes.side_effect = NotFound("gone")
        c = st._Counter()
        st.check_read_object(client, "my-bucket", "_smoke-test/abc.txt", c)
        self.assertEqual(c.failed, 1)


# ---------------------------------------------------------------------------
# check_denied_write
# ---------------------------------------------------------------------------

class TestCheckDeniedWrite(unittest.TestCase):
    def test_forbidden_is_ok(self):
        client, _, _ = _mock_client(upload_side_effect=Forbidden("denied"))
        c = st._Counter()
        st.check_denied_write(client, "my-bucket", c)
        self.assertEqual(c.passed, 1)
        self.assertEqual(c.failed, 0)

    def test_not_found_is_ok(self):
        client, _, _ = _mock_client(upload_side_effect=NotFound("no bucket"))
        c = st._Counter()
        st.check_denied_write(client, "my-bucket", c)
        self.assertEqual(c.passed, 1)

    def test_write_succeeds_is_fail(self):
        client, _, _ = _mock_client()
        c = st._Counter()
        st.check_denied_write(client, "my-bucket", c)
        self.assertEqual(c.failed, 1)

    def test_unexpected_exception_is_fail(self):
        client, _, _ = _mock_client(upload_side_effect=RuntimeError("timeout"))
        c = st._Counter()
        st.check_denied_write(client, "my-bucket", c)
        self.assertEqual(c.failed, 1)


# ---------------------------------------------------------------------------
# cleanup_object (best-effort — should not raise)
# ---------------------------------------------------------------------------

class TestCleanupObject(unittest.TestCase):
    def test_success_is_silent(self):
        client, _, blob = _mock_client()
        blob.delete.return_value = None
        # Should not raise
        st.cleanup_object(client, "my-bucket", "_smoke-test/abc.txt")

    def test_exception_is_swallowed(self):
        client, _, blob = _mock_client()
        blob.delete.side_effect = Exception("network error")
        # Should not raise
        st.cleanup_object(client, "my-bucket", "_smoke-test/abc.txt")


# ---------------------------------------------------------------------------
# _derive_bucket_names
# ---------------------------------------------------------------------------

class TestDeriveBucketNames(unittest.TestCase):
    def _args(self, mode, bucket=None, bucket_data=None, bucket_models=None,
              project="wrack-control"):
        ns = unittest.mock.MagicMock()
        ns.mode = mode
        ns.bucket = bucket
        ns.bucket_data = bucket_data
        ns.bucket_models = bucket_models
        ns.project = project
        return ns

    def test_data_mode_default_names(self):
        training, models = st._derive_bucket_names(self._args("data"))
        self.assertEqual(training, "wrack-control-cat-recognizer-training-data")
        self.assertEqual(models, "wrack-control-cat-recognizer-models")

    def test_data_mode_custom_bucket(self):
        training, models = st._derive_bucket_names(
            self._args("data", bucket="my-custom-bucket")
        )
        self.assertEqual(training, "my-custom-bucket")

    def test_trainer_mode_default_names(self):
        training, models = st._derive_bucket_names(self._args("trainer"))
        self.assertEqual(training, "wrack-control-cat-recognizer-training-data")
        self.assertEqual(models, "wrack-control-cat-recognizer-models")

    def test_trainer_mode_custom_buckets(self):
        training, models = st._derive_bucket_names(
            self._args("trainer", bucket_data="data-bucket", bucket_models="models-bucket")
        )
        self.assertEqual(training, "data-bucket")
        self.assertEqual(models, "models-bucket")

    def test_custom_project_prefix(self):
        training, _ = st._derive_bucket_names(self._args("data", project="my-project"))
        self.assertTrue(training.startswith("my-project-"))


# ---------------------------------------------------------------------------
# Integration-style: run_data_mode / run_trainer_mode with mocked client
# ---------------------------------------------------------------------------

class TestRunDataMode(unittest.TestCase):
    @patch("smoke_test._gcs_client")
    def test_all_pass(self, mock_factory):
        client, _, blob = _mock_client()
        mock_factory.return_value = client
        counter = st.run_data_mode("test-bucket")
        self.assertTrue(counter.all_passed)
        self.assertGreaterEqual(counter.passed, 2)  # list + write + read

    @patch("smoke_test._gcs_client")
    def test_list_fails_counts_as_failed(self, mock_factory):
        client, _, _ = _mock_client(list_blobs_side_effect=Forbidden("no"))
        mock_factory.return_value = client
        counter = st.run_data_mode("test-bucket")
        self.assertFalse(counter.all_passed)


class TestRunTrainerMode(unittest.TestCase):
    @patch("smoke_test._gcs_client")
    def test_trainer_denied_write_on_training_data(self, mock_factory):
        # Trainer should be denied writes to training-data but allowed on models
        calls = {"count": 0}

        def upload_side_effect(data, content_type=None):
            calls["count"] += 1
            if calls["count"] == 1:
                # First upload attempt is to training-data — must be Forbidden
                raise Forbidden("denied on training-data")
            # Subsequent uploads are to models bucket — succeed

        client, _, blob = _mock_client(upload_side_effect=upload_side_effect)
        mock_factory.return_value = client
        counter = st.run_trainer_mode("train-bucket", "models-bucket")
        # The "denied write" on training-data should count as passed
        self.assertGreater(counter.passed, 0)


if __name__ == "__main__":
    unittest.main()
