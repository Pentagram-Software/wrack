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
    exists_return_value=True,
    exists_side_effect=None,
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
    if exists_side_effect is not None:
        blob.exists.side_effect = exists_side_effect
    else:
        blob.exists.return_value = exists_return_value

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

    def test_custom_prefix(self):
        client, _, _ = _mock_client()
        c = st._Counter()
        result = st.check_write_object(client, "my-bucket", c, prefix="ryfka/_smoke-test")
        self.assertIsNotNone(result)
        self.assertTrue(result.startswith("ryfka/_smoke-test/"))
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
# check_keep_exists
# ---------------------------------------------------------------------------

class TestCheckKeepExists(unittest.TestCase):
    def test_keep_exists_passes(self):
        client, _, _ = _mock_client(exists_return_value=True)
        c = st._Counter()
        st.check_keep_exists(client, "my-bucket", "ryfka", c)
        self.assertEqual(c.passed, 1)
        self.assertEqual(c.failed, 0)

    def test_keep_missing_fails(self):
        client, _, _ = _mock_client(exists_return_value=False)
        c = st._Counter()
        st.check_keep_exists(client, "my-bucket", "ryfka", c)
        self.assertEqual(c.failed, 1)
        self.assertEqual(c.passed, 0)

    def test_forbidden_fails(self):
        client, _, _ = _mock_client(exists_side_effect=Forbidden("denied"))
        c = st._Counter()
        st.check_keep_exists(client, "my-bucket", "ryfka", c)
        self.assertEqual(c.failed, 1)

    def test_unexpected_exception_fails(self):
        client, _, _ = _mock_client(exists_side_effect=RuntimeError("timeout"))
        c = st._Counter()
        st.check_keep_exists(client, "my-bucket", "train", c)
        self.assertEqual(c.failed, 1)

    def test_blob_name_format(self):
        """Verify check_keep_exists looks up prefix/.keep."""
        client, bucket, blob = _mock_client(exists_return_value=True)
        c = st._Counter()
        st.check_keep_exists(client, "my-bucket", "chaja", c)
        bucket.blob.assert_called_with("chaja/.keep")
        self.assertEqual(c.passed, 1)


# ---------------------------------------------------------------------------
# _derive_bucket_names
# ---------------------------------------------------------------------------

class TestDeriveBucketNames(unittest.TestCase):
    def _args(self, mode, bucket_raw=None, bucket_processed=None,
              bucket_models=None, project="wrack-control"):
        ns = unittest.mock.MagicMock()
        ns.mode = mode
        ns.bucket_raw = bucket_raw
        ns.bucket_processed = bucket_processed
        ns.bucket_models = bucket_models
        ns.project = project
        return ns

    def test_data_mode_default_names(self):
        raw, processed, models = st._derive_bucket_names(self._args("data"))
        self.assertEqual(raw, "wrack-control-cat-recognizer-raw-data")
        self.assertEqual(processed, "wrack-control-cat-recognizer-processed-data")
        self.assertEqual(models, "wrack-control-cat-recognizer-models")

    def test_data_mode_custom_raw_bucket(self):
        raw, processed, models = st._derive_bucket_names(
            self._args("data", bucket_raw="my-raw-bucket")
        )
        self.assertEqual(raw, "my-raw-bucket")
        self.assertEqual(processed, "wrack-control-cat-recognizer-processed-data")
        self.assertEqual(models, "wrack-control-cat-recognizer-models")

    def test_trainer_mode_default_names(self):
        raw, processed, models = st._derive_bucket_names(self._args("trainer"))
        self.assertEqual(raw, "wrack-control-cat-recognizer-raw-data")
        self.assertEqual(processed, "wrack-control-cat-recognizer-processed-data")
        self.assertEqual(models, "wrack-control-cat-recognizer-models")

    def test_trainer_mode_custom_buckets(self):
        raw, processed, models = st._derive_bucket_names(
            self._args(
                "trainer",
                bucket_raw="raw-bucket",
                bucket_processed="proc-bucket",
                bucket_models="models-bucket",
            )
        )
        self.assertEqual(raw, "raw-bucket")
        self.assertEqual(processed, "proc-bucket")
        self.assertEqual(models, "models-bucket")

    def test_custom_project_prefix(self):
        raw, processed, models = st._derive_bucket_names(
            self._args("data", project="my-project")
        )
        self.assertTrue(raw.startswith("my-project-"))
        self.assertTrue(processed.startswith("my-project-"))
        self.assertTrue(models.startswith("my-project-"))

    def test_bucket_names_contain_expected_suffixes(self):
        raw, processed, models = st._derive_bucket_names(self._args("data"))
        self.assertIn("raw-data", raw)
        self.assertIn("processed-data", processed)
        self.assertIn("models", models)


# ---------------------------------------------------------------------------
# Integration-style: run_data_mode / run_trainer_mode with mocked client
# ---------------------------------------------------------------------------

class TestRunDataMode(unittest.TestCase):
    @patch("smoke_test._gcs_client")
    def test_all_pass(self, mock_factory):
        """data SA: write raw, denied on processed, all .keep present → all pass."""
        calls = {"count": 0}

        def upload_side_effect(data, content_type=None):
            calls["count"] += 1
            if calls["count"] == 2:
                # Second upload is the check_denied_write call on processed bucket
                raise Forbidden("denied on processed-data")

        client, _, blob = _mock_client(
            upload_side_effect=upload_side_effect,
            exists_return_value=True,
        )
        mock_factory.return_value = client
        counter = st.run_data_mode("raw-bucket", "processed-bucket")
        self.assertTrue(counter.all_passed)
        # list(1) + write(1) + read(1) + denied(1) + keep×3(raw) + keep×3(processed) = 10
        self.assertEqual(counter.passed, 10)
        self.assertEqual(counter.failed, 0)

    @patch("smoke_test._gcs_client")
    def test_list_fails_counts_as_failed(self, mock_factory):
        client, _, _ = _mock_client(list_blobs_side_effect=Forbidden("no"))
        mock_factory.return_value = client
        counter = st.run_data_mode("raw-bucket", "processed-bucket")
        self.assertFalse(counter.all_passed)

    @patch("smoke_test._gcs_client")
    def test_keep_missing_counts_as_failed(self, mock_factory):
        """If .keep placeholders are absent the mode should report failures."""
        calls = {"count": 0}

        def upload_side_effect(data, content_type=None):
            calls["count"] += 1
            if calls["count"] == 2:
                raise Forbidden("denied on processed-data")

        client, _, _ = _mock_client(
            upload_side_effect=upload_side_effect,
            exists_return_value=False,  # all .keep checks return False → fail
        )
        mock_factory.return_value = client
        counter = st.run_data_mode("raw-bucket", "processed-bucket")
        self.assertFalse(counter.all_passed)
        # 6 .keep checks all fail
        self.assertEqual(counter.failed, 6)

    @patch("smoke_test._gcs_client")
    def test_write_prefix_uses_ryfka(self, mock_factory):
        """Verify that data mode writes under the ryfka/ prefix."""
        calls = {"count": 0}

        def upload_side_effect(data, content_type=None):
            calls["count"] += 1
            if calls["count"] == 2:
                raise Forbidden("denied on processed-data")

        client, bucket, blob = _mock_client(
            upload_side_effect=upload_side_effect,
            exists_return_value=True,
        )
        mock_factory.return_value = client
        st.run_data_mode("raw-bucket", "processed-bucket")
        # The first blob creation should use a ryfka/_smoke-test/ prefix
        first_blob_name = bucket.blob.call_args_list[0][0][0]
        self.assertTrue(first_blob_name.startswith("ryfka/_smoke-test/"))


class TestRunTrainerMode(unittest.TestCase):
    @patch("smoke_test._gcs_client")
    def test_all_pass(self, mock_factory):
        """trainer SA: denied on raw, write processed+models, all .keep present → all pass."""
        calls = {"count": 0}

        def upload_side_effect(data, content_type=None):
            calls["count"] += 1
            if calls["count"] == 1:
                # First upload is the check_denied_write call on raw bucket
                raise Forbidden("denied on raw-data")
            # Subsequent uploads (processed + models) succeed

        client, _, blob = _mock_client(
            upload_side_effect=upload_side_effect,
            exists_return_value=True,
        )
        mock_factory.return_value = client
        counter = st.run_trainer_mode("raw-bucket", "processed-bucket", "models-bucket")
        self.assertTrue(counter.all_passed)
        # list(raw)(1) + denied(1) + list(proc)(1) + write(proc)(1) + read(proc)(1)
        # + list(models)(1) + write(models)(1) + read(models)(1)
        # + keep×3(raw) + keep×3(processed) = 14
        self.assertEqual(counter.passed, 14)
        self.assertEqual(counter.failed, 0)

    @patch("smoke_test._gcs_client")
    def test_trainer_denied_write_on_raw_data(self, mock_factory):
        """Trainer should be denied writes on raw-data but allowed on processed + models."""
        calls = {"count": 0}

        def upload_side_effect(data, content_type=None):
            calls["count"] += 1
            if calls["count"] == 1:
                raise Forbidden("denied on raw-data")

        client, _, blob = _mock_client(upload_side_effect=upload_side_effect)
        mock_factory.return_value = client
        counter = st.run_trainer_mode("raw-bucket", "processed-bucket", "models-bucket")
        # The "denied write" on raw-data should count as passed
        self.assertGreater(counter.passed, 0)

    @patch("smoke_test._gcs_client")
    def test_keep_missing_counts_as_failed(self, mock_factory):
        """If .keep placeholders are absent the mode should report failures."""
        calls = {"count": 0}

        def upload_side_effect(data, content_type=None):
            calls["count"] += 1
            if calls["count"] == 1:
                raise Forbidden("denied on raw-data")

        client, _, _ = _mock_client(
            upload_side_effect=upload_side_effect,
            exists_return_value=False,
        )
        mock_factory.return_value = client
        counter = st.run_trainer_mode("raw-bucket", "processed-bucket", "models-bucket")
        self.assertFalse(counter.all_passed)
        self.assertEqual(counter.failed, 6)

    @patch("smoke_test._gcs_client")
    def test_write_prefix_uses_train(self, mock_factory):
        """Verify that trainer mode writes to processed bucket under train/ prefix."""
        calls = {"count": 0}

        def upload_side_effect(data, content_type=None):
            calls["count"] += 1
            if calls["count"] == 1:
                raise Forbidden("denied on raw-data")

        client, bucket, blob = _mock_client(
            upload_side_effect=upload_side_effect,
            exists_return_value=True,
        )
        mock_factory.return_value = client
        st.run_trainer_mode("raw-bucket", "processed-bucket", "models-bucket")
        # Second blob creation (after denied_write) goes to processed with train/ prefix
        blob_names = [c[0][0] for c in bucket.blob.call_args_list]
        train_blobs = [n for n in blob_names if n.startswith("train/_smoke-test/")]
        self.assertGreater(len(train_blobs), 0)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants(unittest.TestCase):
    def test_raw_prefixes(self):
        self.assertEqual(set(st.RAW_PREFIXES), {"ryfka", "chaja", "lea"})

    def test_processed_prefixes(self):
        self.assertEqual(set(st.PROCESSED_PREFIXES), {"train", "val", "test"})


if __name__ == "__main__":
    unittest.main()
