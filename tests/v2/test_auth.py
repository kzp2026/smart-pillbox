from __future__ import annotations

import unittest

from v2.auth import LoginGuard, SessionClock, hash_password, verify_password


class PasswordHashTests(unittest.TestCase):
    def test_password_hash_round_trip_and_wrong_password_rejected(self) -> None:
        encoded = hash_password("correct horse", salt=b"0123456789abcdef")

        self.assertTrue(verify_password("correct horse", encoded))
        self.assertFalse(verify_password("wrong", encoded))
        self.assertNotIn("correct horse", encoded)

    def test_malformed_password_hash_is_rejected_without_error(self) -> None:
        self.assertFalse(verify_password("anything", "not-a-valid-hash"))


class LoginGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        encoded = hash_password("secret", salt=b"0123456789abcdef")
        self.guard = LoginGuard(
            username="owner",
            password_hash=encoded,
            max_failures=5,
            cooldown_seconds=900,
        )

    def test_five_failures_lock_login_for_fifteen_minutes(self) -> None:
        for _ in range(5):
            self.guard.authenticate("owner", "wrong", now=1_000.0)

        decision = self.guard.authenticate("owner", "secret", now=1_001.0)

        self.assertEqual(decision.status, "locked")
        self.assertGreaterEqual(decision.retry_after_seconds, 899)

    def test_success_resets_previous_failures(self) -> None:
        self.guard.authenticate("owner", "wrong", now=1_000.0)

        decision = self.guard.authenticate("owner", "secret", now=1_001.0)

        self.assertEqual(decision.status, "authenticated")
        self.assertEqual(self.guard.failure_count, 0)

    def test_locked_login_recovers_after_cooldown(self) -> None:
        for _ in range(5):
            self.guard.authenticate("owner", "wrong", now=1_000.0)

        decision = self.guard.authenticate("owner", "secret", now=1_901.0)

        self.assertEqual(decision.status, "authenticated")


class SessionClockTests(unittest.TestCase):
    def test_session_expires_after_eight_hours_inactivity(self) -> None:
        clock = SessionClock(max_idle_seconds=8 * 60 * 60)

        self.assertFalse(clock.is_expired(last_activity=0.0, now=28_800.0))
        self.assertTrue(clock.is_expired(last_activity=0.0, now=28_801.0))


if __name__ == "__main__":
    unittest.main()
