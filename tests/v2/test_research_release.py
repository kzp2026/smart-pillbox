"""The deployed research entry must identify its method without private access."""
from pathlib import Path
import unittest
from packaging.requirements import Requirement
from streamlit.testing.v1 import AppTest


class ResearchReleaseTests(unittest.TestCase):
    def test_login_identifies_method_without_initializing_private_repository(self):
        app = AppTest.from_string('''
import streamlit as st
from unittest.mock import patch
from v2.app import _render_login
with patch('v2.app._repository_for', side_effect=AssertionError('private access forbidden')):
    _render_login(st, None)
''').run()
        self.assertFalse(app.exception)
        self.assertTrue(any('研究方法：paper-repro-v2.1' in item.value for item in app.caption))

    def test_cloud_manifest_declares_direct_research_dependencies(self):
        root = Path(__file__).resolve().parents[2]
        requirements = {Requirement(line).name.lower() for line in (root/'requirements.txt').read_text(encoding='utf-8').splitlines() if line.strip() and not line.startswith('#')}
        self.assertFalse({'jsonschema', 'scipy', 'threadpoolctl'} - requirements)


if __name__ == '__main__':
    unittest.main()
