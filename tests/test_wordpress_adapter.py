import unittest

from src.adapters.wordpress import WordPressAdapter


class TestWordPressAdapter(unittest.TestCase):
    def test_parse_posts(self):
        data = [
            {"link": "https://example.com/p1", "modified": "2024-01-01T00:00:00"},
            {"link": "https://example.com/p2", "modified": "2024-01-02T00:00:00"},
        ]
        items = list(WordPressAdapter.parse_posts(data))
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].url, 'https://example.com/p1')


if __name__ == '__main__':
    unittest.main()

