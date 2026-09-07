import json
import tempfile
import unittest
import zipfile
from pathlib import Path


class SourceSnapshotTests(unittest.TestCase):
    def test_includes_untracked_source_and_excludes_private_inputs(self):
        from experiment.source_snapshot import snapshot
        from experiment.pipeline.io import sha256
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'repo';root.mkdir()
            for name in ('new.py','README.md','deploy.ps1','.streamlit/config.toml','experiment/pipeline/new.py','.streamlit/secrets.toml','data/private.csv','output/history.json','.env','experiment/runs/a/private/input.csv'):
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('private' if 'secrets' in name else 'example',encoding='utf-8')
            dest=Path(temp)/'delivery';result=snapshot(root,dest)
            with zipfile.ZipFile(dest/'source.zip') as z:
                self.assertEqual(set(z.namelist()),{'new.py','README.md','deploy.ps1','.streamlit/config.toml','experiment/pipeline/new.py'})
            self.assertEqual(result['source_zip_sha256'],sha256(dest/'source.zip'))
            self.assertIn('experiment/pipeline/new.py',result['files'])
            with self.assertRaises(FileExistsError):snapshot(root,dest)

if __name__=='__main__':unittest.main()
