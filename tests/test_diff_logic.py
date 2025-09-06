import os
import tempfile
import time
import unittest

from src.core import db as dbm


class TestDiffLogic(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, 'urls.db')
        self.conn = dbm.ensure_db(self.db_path)

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()

    def test_new_this_run(self):
        now = int(time.time())
        dbm.upsert_source(self.conn, 's1', 'rss', None, '{}')
        dbm.upsert_url(self.conn, 'https://a', canonical=None, discovered_via='rss', http_status=200, lastmod=None, etag=None)
        dbm.touch_url_by_source(self.conn, 's1', 'https://a')
        # Force first_seen to now-10
        self.conn.execute("UPDATE url_by_source SET first_seen=? WHERE source_id='s1' AND url='https://a'", (now-10,))
        self.conn.commit()
        rows = list(dbm.query_new_urls(self.conn, start_ts=now-20, end_ts=now-5))
        self.assertTrue(any(r[1] == 'https://a' for r in rows))


if __name__ == '__main__':
    unittest.main()

