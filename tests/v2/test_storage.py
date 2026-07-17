from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from uuid import UUID
from unittest.mock import patch

from v2.adapters.postgres import KnowledgeRepository
from v2.adapters.storage import LocalArtifactStore, RepositoryArtifactStore, SupabaseArtifactStore


class FakeResponse:
    def __init__(self, payload: bytes = b"") -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return self.payload


class LocalArtifactStoreTests(unittest.TestCase):
    def test_artifacts_with_same_name_are_scoped_by_run_uuid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = LocalArtifactStore(Path(temp_dir))

            first = store.put(UUID(int=1), "效果图.png", b"one", "image/png")
            second = store.put(UUID(int=2), "效果图.png", b"two", "image/png")

            self.assertNotEqual(first.path, second.path)
            self.assertEqual(store.read(first.path), b"one")
            self.assertEqual(store.read(second.path), b"two")

    def test_unsafe_file_name_is_reduced_to_safe_leaf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = LocalArtifactStore(Path(temp_dir))

            artifact = store.put(UUID(int=1), "../../outside.png", b"safe", "image/png")

            self.assertNotIn("..", artifact.path)
            self.assertTrue(artifact.path.endswith("outside.png"))
            self.assertFalse((Path(temp_dir).parent / "outside.png").exists())

    def test_delete_many_reports_each_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = LocalArtifactStore(Path(temp_dir))
            artifact = store.put(UUID(int=1), "效果图.png", b"one", "image/png")

            report = store.delete_many([artifact.path, "../unsafe.png"])

            self.assertEqual(report.deleted, (artifact.path,))
            self.assertEqual(report.failed, ("../unsafe.png",))


class SupabaseArtifactStoreTests(unittest.TestCase):
    def test_upload_uses_private_object_endpoint_and_server_key_header(self) -> None:
        requests = []

        def fake_urlopen(request, timeout=0):
            requests.append(request)
            return FakeResponse(b"{}")

        store = SupabaseArtifactStore(
            storage_url="https://project.supabase.co/storage/v1",
            bucket="agent-v2-private",
            service_key="service-secret",
        )
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            artifact = store.put(UUID(int=1), "效果图.png", b"png", "image/png")

        self.assertEqual(len(requests), 1)
        self.assertIn("/object/agent-v2-private/runs/", requests[0].full_url)
        self.assertEqual(requests[0].get_header("Authorization"), "Bearer service-secret")
        self.assertNotIn("service-secret", repr(artifact))


class RepositoryArtifactStoreTests(unittest.TestCase):
    def test_private_database_blob_store_persists_reads_and_deletes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = KnowledgeRepository(
                f"sqlite:///{Path(temp_dir) / 'private.sqlite3'}", "owner"
            )
            repository.initialize()
            store = RepositoryArtifactStore(repository)

            first = store.put(UUID(int=1), "效果图.png", b"one", "image/png")
            second = store.put(UUID(int=1), "效果图.png", b"two", "image/png")

            self.assertNotEqual(first.path, second.path)
            self.assertEqual(store.read(first.path), b"one")
            self.assertEqual(store.read(second.path), b"two")
            report = store.delete_many([first.path, "../unsafe.png"])
            self.assertEqual(report.deleted, (first.path,))
            self.assertEqual(report.failed, ("../unsafe.png",))


if __name__ == "__main__":
    unittest.main()
