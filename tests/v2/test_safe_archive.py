from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from v2.application.artifacts import ArchiveLimits, UnsafeArchive, extract_archive, inspect_archive


def make_zip(files: dict[str, bytes]) -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return payload.getvalue()


class SafeArchiveTests(unittest.TestCase):
    def test_archive_rejects_parent_traversal(self) -> None:
        with self.assertRaises(UnsafeArchive):
            inspect_archive(make_zip({"../evil.txt": b"bad"}), ArchiveLimits.default())

    def test_archive_rejects_extreme_compression_ratio(self) -> None:
        limits = ArchiveLimits(
            max_archive_bytes=2_000_000,
            max_entries=10,
            max_total_uncompressed=2_000_000,
            max_single_file=2_000_000,
            max_compression_ratio=5,
        )

        with self.assertRaises(UnsafeArchive):
            inspect_archive(make_zip({"huge.txt": b"0" * 500_000}), limits)

    def test_valid_archive_extracts_only_manifest_entries(self) -> None:
        archive_bytes = make_zip(
            {
                "cleaned_comments.xlsx": b"xlsx",
                "design_images/产品效果图.png": b"png",
            }
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            manifest = extract_archive(archive_bytes, Path(temp_dir), ArchiveLimits.default())

            self.assertEqual(len(manifest.entries), 2)
            self.assertEqual((Path(temp_dir) / "cleaned_comments.xlsx").read_bytes(), b"xlsx")
            self.assertEqual((Path(temp_dir) / "design_images" / "产品效果图.png").read_bytes(), b"png")


if __name__ == "__main__":
    unittest.main()
