import unittest

from src.adapters.rss import RSSAdapter


class TestRSSAdapter(unittest.TestCase):
    def test_parse_feed(self):
        xml = """
        <rss version="2.0">
          <channel>
            <title>Example</title>
            <item>
              <title>One</title>
              <link>https://example.com/one</link>
              <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
            </item>
            <item>
              <title>Two</title>
              <guid>https://example.com/two</guid>
              <pubDate>Tue, 02 Jan 2024 00:00:00 GMT</pubDate>
            </item>
          </channel>
        </rss>
        """
        items = list(RSSAdapter.parse_feed(xml))
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].url, 'https://example.com/one')
        self.assertEqual(items[1].url, 'https://example.com/two')


if __name__ == '__main__':
    unittest.main()

