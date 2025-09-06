import os
import tempfile
import unittest

from src.core import db as dbm


class TestDB(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, 'urls.db')
        self.conn = dbm.ensure_db(self.db_path)

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()

    def test_upsert_and_query(self):
        dbm.upsert_source(self.conn, 's1', 'rss', 'https://x', '{}')
        is_new, first = dbm.upsert_url(self.conn, 'https://x/test', canonical=None, discovered_via='rss', http_status=200, lastmod=None, etag=None)
        self.assertTrue(is_new)
        is_new_pair, first_pair = dbm.touch_url_by_source(self.conn, 's1', 'https://x/test')
        self.assertTrue(is_new_pair)
        rows = list(dbm.query_new_urls(self.conn, start_ts=first-1, end_ts=first+1))
        self.assertEqual(len(rows), 1)


if __name__ == '__main__':
    unittest.main()

