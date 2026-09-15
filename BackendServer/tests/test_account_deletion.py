"""Tests for complete, retry-safe account deletion."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from account_deletion import FIRESTORE_BATCH_SIZE, delete_account_data


class AccountDeletionTests(unittest.TestCase):
    def test_deletes_analysis_in_bounded_batches_storage_prefix_and_auth(self):
        firestore_client = MagicMock()
        user_reference = firestore_client.collection.return_value.document.return_value
        documents = [MagicMock() for _ in range(FIRESTORE_BATCH_SIZE + 1)]
        user_reference.collection.return_value.stream.return_value = iter(documents)
        first_batch = MagicMock()
        second_batch = MagicMock()
        firestore_client.batch.side_effect = [first_batch, second_batch]

        first_blob = MagicMock()
        second_blob = MagicMock()
        storage_bucket = MagicMock()
        storage_bucket.list_blobs.return_value = [first_blob, second_blob]
        auth_client = MagicMock()

        result = delete_account_data(
            "user-1",
            firestore_client=firestore_client,
            storage_bucket=storage_bucket,
            auth_client=auth_client,
        )

        self.assertEqual(
            result,
            {
                "analysis_documents": FIRESTORE_BATCH_SIZE + 1,
                "storage_objects": 2,
            },
        )
        self.assertEqual(first_batch.delete.call_count, FIRESTORE_BATCH_SIZE)
        second_batch.delete.assert_called_once_with(documents[-1].reference)
        first_batch.commit.assert_called_once_with()
        second_batch.commit.assert_called_once_with()
        user_reference.delete.assert_called_once_with()
        storage_bucket.list_blobs.assert_called_once_with(prefix="user-1/")
        first_blob.delete.assert_called_once_with()
        second_blob.delete.assert_called_once_with()
        auth_client.delete_user.assert_called_once_with("user-1")

    def test_authentication_is_not_deleted_when_data_cleanup_fails(self):
        firestore_client = MagicMock()
        user_reference = firestore_client.collection.return_value.document.return_value
        document = MagicMock()
        user_reference.collection.return_value.stream.return_value = iter([document])
        firestore_client.batch.return_value.commit.side_effect = RuntimeError("write failed")
        auth_client = MagicMock()

        with self.assertRaisesRegex(RuntimeError, "write failed"):
            delete_account_data(
                "user-1",
                firestore_client=firestore_client,
                storage_bucket=MagicMock(),
                auth_client=auth_client,
            )

        auth_client.delete_user.assert_not_called()

    def test_rejects_an_empty_user_id_before_touching_services(self):
        firestore_client = MagicMock()

        with self.assertRaises(ValueError):
            delete_account_data(
                " ",
                firestore_client=firestore_client,
                storage_bucket=MagicMock(),
                auth_client=MagicMock(),
            )

        firestore_client.collection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
