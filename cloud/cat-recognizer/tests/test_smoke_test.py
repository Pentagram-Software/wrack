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
    reload_side_effect=None,
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
    if reload_side_effect is not None:
        blob.reload.side_effect = reload_side_effect

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

    def test_success_with_prefix(self):
        client, _, _ = _mock_client()
        c = st._Counter()
        result = st.check_write_object(client, "my-bucket", c, prefix="ryfka/")
        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("ryfka/_smoke-test/"))
        self.assertEqual(c.passed, 1)

    def test_success_with_train_prefix(self):
        client, _, _ = _mock_client()
        c = st._Counter()
        result = st.check_write_object(client, "my-bucket", c, prefix="train/")
        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("train/_smoke-test/"))
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
# check_keep_objects
# ---------------------------------------------------------------------------

class TestCheckKeepObjects(unittest.TestCase):
    def test_all_keep_files_present(self):
        """reload() succeeds for all prefixes → all pass."""
        client, _, blob = _mock_client()
        blob.reload.return_value = None
        c = st._Counter()
        st.check_keep_objects(client, "my-bucket", ["ryfka/", "chaja/", "lea/"], c)
        self.assertEqual(c.passed, 3)
        self.assertEqual(c.failed, 0)

    def test_missing_keep_file(self):
        """reload() raises NotFound → fails."""
        client, _, blob = _mock_client(reload_side_effect=NotFound("not found"))
        c = st._Counter()
        st.check_keep_objects(client, "my-bucket", ["ryfka/"], c)
        self.assertEqual(c.failed, 1)
        self.assertEqual(c.passed, 0)

    def test_forbidden_on_keep_file(self):
        """reload() raises Forbidden → fails."""
        client, _, blob = _mock_client(reload_side_effect=Forbidden("denied"))
        c = st._Counter()
        st.check_keep_objects(client, "my-bucket", ["ryfka/"], c)
        self.assertEqual(c.failed, 1)

    def test_unexpected_exception_on_keep_file(self):
        """reload() raises unexpected exception → fails."""
        client, _, blob = _mock_client(reload_side_effect=RuntimeError("timeout"))
        c = st._Counter()
        st.check_keep_objects(client, "my-bucket", ["ryfka/"], c)
        self.assertEqual(c.failed, 1)

    def test_partial_keep_files_missing(self):
        """Some prefixes present, one missing → partial failures."""
        client, bucket, _ = _mock_client()

        call_count = {"n": 0}

        def reload_side_effect():
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise NotFound("second .keep missing")

        blob1 = MagicMock()
        blob1.reload.side_effect = reload_side_effect
        bucket.blob.return_value = blob1

        c = st._Counter()
        st.check_keep_objects(client, "my-bucket", ["ryfka/", "chaja/", "lea/"], c)
        self.assertEqual(c.passed, 2)
        self.assertEqual(c.failed, 1)

    def test_blob_name_construction(self):
        """Verifies that blob names are built as prefix + '.keep'."""
        client, bucket, blob = _mock_client()
        blob.reload.return_value = None
        c = st._Counter()
        st.check_keep_objects(client, "my-bucket", ["train/"], c)
        bucket.blob.assert_called_with("train/.keep")

    def test_processed_split_prefixes(self):
        """Verifies train/val/test prefixes for processed bucket."""
        client, _, blob = _mock_client()
        blob.reload.return_value = None
        c = st._Counter()
        st.check_keep_objects(client, "processed-bucket", ["train/", "val/", "test/"], c)
        self.assertEqual(c.passed, 3)
        self.assertEqual(c.failed, 0)

    def test_empty_prefixes_list(self):
        """No prefixes → no checks performed, counter unchanged."""
        client, _, _ = _mock_client()
        c = st._Counter()
        st.check_keep_objects(client, "my-bucket", [], c)
        self.assertEqual(c.passed, 0)
        self.assertEqual(c.failed, 0)


# ---------------------------------------------------------------------------
# _derive_bucket_names
# ---------------------------------------------------------------------------

class TestDeriveBucketNames(unittest.TestCase):
    def _args(self, mode="data", bucket_raw=None, bucket_processed=None,
              bucket_models=None, project="wrack-control"):
        ns = unittest.mock.MagicMock()
        ns.mode = mode
        ns.bucket_raw = bucket_raw
        ns.bucket_processed = bucket_processed
        ns.bucket_models = bucket_models
        ns.project = project
        return ns

    def test_default_names(self):
        raw, processed, models = st._derive_bucket_names(self._args())
        self.assertEqual(raw, "wrack-control-cat-recognizer-raw-data")
        self.assertEqual(processed, "wrack-control-cat-recognizer-processed-data")
        self.assertEqual(models, "wrack-control-cat-recognizer-models")

    def test_custom_raw_bucket(self):
        raw, processed, models = st._derive_bucket_names(
            self._args(bucket_raw="my-raw-bucket")
        )
        self.assertEqual(raw, "my-raw-bucket")
        self.assertEqual(processed, "wrack-control-cat-recognizer-processed-data")
        self.assertEqual(models, "wrack-control-cat-recognizer-models")

    def test_custom_processed_bucket(self):
        raw, processed, models = st._derive_bucket_names(
            self._args(bucket_processed="my-processed-bucket")
        )
        self.assertEqual(raw, "wrack-control-cat-recognizer-raw-data")
        self.assertEqual(processed, "my-processed-bucket")

    def test_custom_models_bucket(self):
        raw, processed, models = st._derive_bucket_names(
            self._args(bucket_models="my-models-bucket")
        )
        self.assertEqual(models, "my-models-bucket")

    def test_all_custom_buckets(self):
        raw, processed, models = st._derive_bucket_names(
            self._args(
                bucket_raw="raw-bucket",
                bucket_processed="processed-bucket",
                bucket_models="models-bucket",
            )
        )
        self.assertEqual(raw, "raw-bucket")
        self.assertEqual(processed, "processed-bucket")
        self.assertEqual(models, "models-bucket")

    def test_custom_project_prefix(self):
        raw, processed, models = st._derive_bucket_names(
            self._args(project="my-project")
        )
        self.assertTrue(raw.startswith("my-project-"))
        self.assertTrue(processed.startswith("my-project-"))
        self.assertTrue(models.startswith("my-project-"))

    def test_returns_three_values(self):
        result = st._derive_bucket_names(self._args())
        self.assertEqual(len(result), 3)

    def test_raw_bucket_name_contains_raw_data(self):
        raw, _, _ = st._derive_bucket_names(self._args())
        self.assertIn("raw-data", raw)

    def test_processed_bucket_name_contains_processed_data(self):
        _, processed, _ = st._derive_bucket_names(self._args())
        self.assertIn("processed-data", processed)


# ---------------------------------------------------------------------------
# Integration-style: run_data_mode / run_trainer_mode with mocked client
# ---------------------------------------------------------------------------

def _make_bucket_mock(allow_write=True):
    """Return a (bucket, blob) pair where upload behaviour is controlled by allow_write."""
    blob = MagicMock()
    blob.download_as_bytes.return_value = b"cat-recognizer smoke test"
    blob.reload.return_value = None
    if not allow_write:
        blob.upload_from_string.side_effect = Forbidden("permission denied")
    bucket = MagicMock()
    bucket.blob.return_value = blob
    return bucket, blob


def _mock_client_per_bucket(bucket_permissions):
    """
    Build a mock storage.Client whose bucket() method returns different mocks
    based on bucket name.  bucket_permissions maps bucket_name → allow_write bool.
    """
    bucket_mocks = {
        name: _make_bucket_mock(allow_write=allow)
        for name, allow in bucket_permissions.items()
    }

    client = MagicMock()
    client.list_blobs.return_value = iter([])
    client.bucket.side_effect = lambda name: bucket_mocks[name][0] if name in bucket_mocks else _make_bucket_mock()[0]
    return client


class TestRunDataMode(unittest.TestCase):
    @patch("smoke_test._gcs_client")
    def test_all_pass(self, mock_factory):
        # data SA: objectAdmin on raw (write allowed), objectViewer on processed (write denied)
        client = _mock_client_per_bucket({
            "raw-bucket": True,
            "processed-bucket": False,
        })
        mock_factory.return_value = client
        counter = st.run_data_mode("raw-bucket", "processed-bucket")
        self.assertTrue(counter.all_passed)
        # list(raw) + write(raw/ryfka) + read(raw) + keep×3 + list(proc) + denied_write(proc) + keep×3
        self.assertGreaterEqual(counter.passed, 10)

    @patch("smoke_test._gcs_client")
    def test_list_raw_fails_counts_as_failed(self, mock_factory):
        client, _, blob = _mock_client(list_blobs_side_effect=Forbidden("no"))
        blob.reload.return_value = None
        mock_factory.return_value = client
        counter = st.run_data_mode("raw-bucket", "processed-bucket")
        self.assertFalse(counter.all_passed)

    @patch("smoke_test._gcs_client")
    def test_write_to_ryfka_prefix(self, mock_factory):
        """data mode writes to ryfka/ prefix in raw bucket."""
        client = _mock_client_per_bucket({
            "raw-bucket": True,
            "processed-bucket": False,
        })
        mock_factory.return_value = client
        raw_bucket_mock = client.bucket("raw-bucket")
        st.run_data_mode("raw-bucket", "processed-bucket")
        written_names = [
            call_args[0][0]
            for call_args in raw_bucket_mock.blob.call_args_list
            if call_args[0][0].startswith("ryfka/_smoke-test/")
        ]
        self.assertGreater(len(written_names), 0)

    @patch("smoke_test._gcs_client")
    def test_write_denied_on_processed(self, mock_factory):
        """data mode should have write denied on processed bucket."""
        client = _mock_client_per_bucket({
            "raw-bucket": True,
            "processed-bucket": False,
        })
        mock_factory.return_value = client
        counter = st.run_data_mode("raw-bucket", "processed-bucket")
        # Denied write on processed bucket should count as passed
        self.assertGreater(counter.passed, 0)

    @patch("smoke_test._gcs_client")
    def test_raw_keep_placeholders_checked(self, mock_factory):
        """data mode verifies ryfka/, chaja/, lea/ .keep objects in raw bucket."""
        client = _mock_client_per_bucket({
            "raw-bucket": True,
            "processed-bucket": False,
        })
        mock_factory.return_value = client
        raw_bucket_mock = client.bucket("raw-bucket")
        st.run_data_mode("raw-bucket", "processed-bucket")
        checked_keeps = [
            call_args[0][0]
            for call_args in raw_bucket_mock.blob.call_args_list
            if call_args[0][0].endswith("/.keep")
        ]
        self.assertIn("ryfka/.keep", checked_keeps)
        self.assertIn("chaja/.keep", checked_keeps)
        self.assertIn("lea/.keep", checked_keeps)

    @patch("smoke_test._gcs_client")
    def test_processed_keep_placeholders_checked(self, mock_factory):
        """data mode verifies train/, val/, test/ .keep objects in processed bucket."""
        client = _mock_client_per_bucket({
            "raw-bucket": True,
            "processed-bucket": False,
        })
        mock_factory.return_value = client
        processed_bucket_mock = client.bucket("processed-bucket")
        st.run_data_mode("raw-bucket", "processed-bucket")
        checked_keeps = [
            call_args[0][0]
            for call_args in processed_bucket_mock.blob.call_args_list
            if call_args[0][0].endswith("/.keep")
        ]
        self.assertIn("train/.keep", checked_keeps)
        self.assertIn("val/.keep", checked_keeps)
        self.assertIn("test/.keep", checked_keeps)


class TestRunTrainerMode(unittest.TestCase):
    @patch("smoke_test._gcs_client")
    def test_all_pass(self, mock_factory):
        # trainer SA: objectViewer on raw (write denied), objectAdmin on processed and models
        client = _mock_client_per_bucket({
            "raw-bucket": False,
            "processed-bucket": True,
            "models-bucket": True,
        })
        mock_factory.return_value = client
        counter = st.run_trainer_mode("raw-bucket", "processed-bucket", "models-bucket")
        self.assertTrue(counter.all_passed)
        # list(raw) + denied_write(raw) + keep×3 + list(proc) + write(proc/train) + read(proc) + keep×3 + list(models) + write(models) + read(models)
        self.assertGreaterEqual(counter.passed, 13)

    @patch("smoke_test._gcs_client")
    def test_trainer_denied_write_on_raw(self, mock_factory):
        """Trainer should be denied writes to raw-data but allowed on processed and models."""
        client = _mock_client_per_bucket({
            "raw-bucket": False,
            "processed-bucket": True,
            "models-bucket": True,
        })
        mock_factory.return_value = client
        counter = st.run_trainer_mode("raw-bucket", "processed-bucket", "models-bucket")
        # The "denied write" on raw-data should count as passed
        self.assertGreater(counter.passed, 0)

    @patch("smoke_test._gcs_client")
    def test_write_to_train_prefix_in_processed(self, mock_factory):
        """trainer mode writes to train/ prefix in processed bucket."""
        client = _mock_client_per_bucket({
            "raw-bucket": False,
            "processed-bucket": True,
            "models-bucket": True,
        })
        mock_factory.return_value = client
        processed_bucket_mock = client.bucket("processed-bucket")
        st.run_trainer_mode("raw-bucket", "processed-bucket", "models-bucket")
        written_names = [
            call_args[0][0]
            for call_args in processed_bucket_mock.blob.call_args_list
            if call_args[0][0].startswith("train/_smoke-test/")
        ]
        self.assertGreater(len(written_names), 0)

    @patch("smoke_test._gcs_client")
    def test_raw_keep_placeholders_checked(self, mock_factory):
        """trainer mode verifies ryfka/, chaja/, lea/ .keep objects in raw bucket."""
        client = _mock_client_per_bucket({
            "raw-bucket": False,
            "processed-bucket": True,
            "models-bucket": True,
        })
        mock_factory.return_value = client
        raw_bucket_mock = client.bucket("raw-bucket")
        st.run_trainer_mode("raw-bucket", "processed-bucket", "models-bucket")
        checked_keeps = [
            call_args[0][0]
            for call_args in raw_bucket_mock.blob.call_args_list
            if call_args[0][0].endswith("/.keep")
        ]
        self.assertIn("ryfka/.keep", checked_keeps)
        self.assertIn("chaja/.keep", checked_keeps)
        self.assertIn("lea/.keep", checked_keeps)

    @patch("smoke_test._gcs_client")
    def test_processed_keep_placeholders_checked(self, mock_factory):
        """trainer mode verifies train/, val/, test/ .keep objects in processed bucket."""
        client = _mock_client_per_bucket({
            "raw-bucket": False,
            "processed-bucket": True,
            "models-bucket": True,
        })
        mock_factory.return_value = client
        processed_bucket_mock = client.bucket("processed-bucket")
        st.run_trainer_mode("raw-bucket", "processed-bucket", "models-bucket")
        checked_keeps = [
            call_args[0][0]
            for call_args in processed_bucket_mock.blob.call_args_list
            if call_args[0][0].endswith("/.keep")
        ]
        self.assertIn("train/.keep", checked_keeps)
        self.assertIn("val/.keep", checked_keeps)
        self.assertIn("test/.keep", checked_keeps)


if __name__ == "__main__":
    unittest.main()
