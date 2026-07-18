from __future__ import annotations

import unittest

from v2.ui.errors import public_error_message


class PublicErrorMessageTests(unittest.TestCase):
    def test_database_exception_details_are_not_exposed(self) -> None:
        exception = RuntimeError(
            'connection to aws-1-ap-southeast-1.pooler.supabase.com '
            'at 54.179.210.0 failed for postgresql://postgres:secret@example'
        )

        message = public_error_message("私有服务初始化失败", exception)

        self.assertEqual(
            message,
            "私有服务初始化失败。请检查管理应用中的服务配置后重试。",
        )
        self.assertNotIn("pooler.supabase.com", message)
        self.assertNotIn("54.179.210.0", message)
        self.assertNotIn("secret", message)


if __name__ == "__main__":
    unittest.main()
