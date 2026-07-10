import unittest

from app.services.notification_utils import unique_qq_numbers


class OnlineNotifierTests(unittest.TestCase):
    def test_unique_qq_numbers_dedupes_and_skips_empty_values(self) -> None:
        self.assertEqual(
            unique_qq_numbers(["10001", None, "", "10002", "10001", 10002]),
            ["10001", "10002"],
        )


if __name__ == "__main__":
    unittest.main()
