"""Tests for the stable mobile authentication response contract."""

from __future__ import annotations

import unittest

from auth_contract import refreshed_session_payload, sign_in_session_payload


class AuthenticationContractTests(unittest.TestCase):
    def test_sign_in_keeps_legacy_fields_and_adds_refresh_metadata(self):
        result = sign_in_session_payload(
            {
                "idToken": "id-1",
                "localId": "user-1",
                "refreshToken": "refresh-1",
                "expiresIn": "3600",
            }
        )

        self.assertEqual(result["idToken"], "id-1")
        self.assertEqual(result["user_id"], "user-1")
        self.assertEqual(result["refreshToken"], "refresh-1")
        self.assertEqual(result["expiresIn"], "3600")

    def test_refresh_adapts_snake_case_and_preserves_rotated_token(self):
        result = refreshed_session_payload(
            {
                "id_token": "id-2",
                "user_id": "user-1",
                "refresh_token": "refresh-2",
                "expires_in": "3600",
            },
            "refresh-1",
        )

        self.assertEqual(
            result,
            {
                "idToken": "id-2",
                "user_id": "user-1",
                "refreshToken": "refresh-2",
                "expiresIn": "3600",
            },
        )

    def test_refresh_falls_back_when_firebase_does_not_rotate_token(self):
        result = refreshed_session_payload(
            {"id_token": "id-2", "user_id": "user-1", "expires_in": "3600"},
            "refresh-1",
        )

        self.assertEqual(result["refreshToken"], "refresh-1")

    def test_missing_identity_fields_never_produce_a_success_payload(self):
        with self.assertRaises(ValueError):
            sign_in_session_payload({"idToken": "id-1"})


if __name__ == "__main__":
    unittest.main()
