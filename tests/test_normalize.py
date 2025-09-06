import unittest

from src.core.normalize import normalize_url


class TestNormalize(unittest.TestCase):
    def test_tracking_and_sort(self):
        url = 'https://Example.com/Path/?b=2&utm_source=x&a=1&gclid=zzz'
        self.assertEqual(
            normalize_url(url),
            'https://example.com/Path/?a=1&b=2'
        )

    def test_fragment_and_index(self):
        url = 'https://example.com/a/index.html#frag'
        self.assertEqual(normalize_url(url), 'https://example.com/a/')


if __name__ == '__main__':
    unittest.main()

