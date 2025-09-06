import unittest

from src.adapters.sitemap import SitemapAdapter


class TestSitemapAdapter(unittest.TestCase):
    def test_parse_urlset(self):
        xml = """
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://example.com/a</loc><lastmod>2024-01-01</lastmod></url>
          <url><loc>https://example.com/b</loc></url>
        </urlset>
        """
        items = [x for x in SitemapAdapter._iter_sitemap_xml(xml) if x.meta.get('_type') != 'index']
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].url, 'https://example.com/a')
        self.assertEqual(items[0].lastmod, '2024-01-01')

    def test_parse_index(self):
        xml = """
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <sitemap><loc>https://example.com/s1.xml</loc></sitemap>
        </sitemapindex>
        """
        items = list(SitemapAdapter._iter_sitemap_xml(xml))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].meta.get('_type'), 'index')


if __name__ == '__main__':
    unittest.main()

