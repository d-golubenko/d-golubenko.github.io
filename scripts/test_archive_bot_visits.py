import csv
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import archive_bot_visits as archive


def event(identity, day, path='/acid-recovery.html', agent='oai-searchbot', category='ai_bot', **changes):
    record = dict(event='site_visit', method='GET', status=200, content_type='text/html', category=category, agent=agent, path=path)
    record.update(changes)
    return {'$metadata': {'id': identity}, 'timestamp': archive.day_bounds(day)[0] + 1000, 'source': record}


class ArchiveTests(unittest.TestCase):
    now = datetime(2026, 10, 6, 2, tzinfo=timezone.utc)
    day = archive.date(2026, 10, 5)

    def test_day_bounds_use_shanghai_midnight(self):
        start, end = archive.day_bounds(self.day)
        self.assertEqual(datetime.fromtimestamp(start / 1000, timezone.utc).isoformat(), '2026-10-04T16:00:00+00:00')
        self.assertEqual(end - start, 86400000)

    def test_only_successful_bot_html_and_canonical_paths(self):
        records = [event('a', self.day), event('a', self.day),
                   event('b', self.day, path='/acid-recovery'),
                   event('c', self.day, path='/styles.css', content_type='text/css'),
                   event('d', self.day, status=301),
                   event('e', self.day, category='browser_or_unknown')]
        query = lambda body: {'events': {'events': records}}
        self.assertEqual(archive.fetch_day(self.day, self.now, query), {('ai_bot', 'oai-searchbot', '/acid-recovery'): 2})

    def test_pagination_and_id_deduplication(self):
        pages = [[event('a', self.day), event('b', self.day)], [event('b', self.day), event('c', self.day)], []]
        bodies = []
        def query(body):
            bodies.append(body)
            return {'events': {'events': pages.pop(0), 'count': 3}}
        with patch.object(archive, 'PAGE_SIZE', 2):
            result = archive.fetch_day(self.day, self.now, query)
        self.assertEqual(sum(result.values()), 3)
        self.assertEqual(bodies[1]['offset'], 'b')
        self.assertEqual(bodies[2]['offset'], 'c')

    def test_repeated_cursor_fails(self):
        with patch.object(archive, 'PAGE_SIZE', 1):
            with self.assertRaisesRegex(RuntimeError, 'advancing'):
                archive.fetch_day(self.day, self.now, lambda body: {'events': {'events': [event('a', self.day)]}})

    def test_incomplete_result_fails(self):
        with self.assertRaisesRegex(RuntimeError, 'Incomplete'):
            archive.fetch_day(self.day, self.now, lambda body: {'events': {'count': 2, 'events': [event('a', self.day)]}})

    def test_reruns_replace_totals_and_keep_older_days(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive.write_day(root, archive.date(2026, 10, 4), {}, False)
            def query(body):
                day = datetime.fromtimestamp(body['timeframe']['from'] / 1000, archive.TZ).date()
                return {'events': {'count': 1, 'events': [event(day.isoformat(), day)]}}
            archive.archive(root, self.now, query)
            original = (root / 'all-days.csv').read_bytes()
            archive.archive(root, self.now, query)
            self.assertEqual((root / 'all-days.csv').read_bytes(), original)
            self.assertTrue((root / 'daily' / '2026-10-04.csv').exists())
            with (root / 'all-days.csv').open() as stream:
                self.assertEqual(sum(int(row['visits']) for row in csv.DictReader(stream)), 2)

    def test_api_failure_keeps_all_existing_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive.write_day(root, self.day, {('ai_bot', 'gptbot', '/'): 5}, False)
            before = {p.name: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            with self.assertRaises(RuntimeError):
                archive.archive(root, self.now, lambda body: (_ for _ in ()).throw(RuntimeError('unavailable')))
            after = {p.name: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            self.assertEqual(before, after)

    def test_first_day_and_partial_backfill(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            now = datetime(2026, 10, 4, 8, tzinfo=timezone.utc)
            self.assertEqual(archive.archive(root, now, lambda body: {'events': {'count': 0, 'events': []}}, True), 1)
            coverage = json.loads((root / 'coverage' / '2026-10-04.json').read_text())
            self.assertEqual(coverage['status'], 'partial')
            self.assertFalse((root / 'daily' / '2026-10-03.csv').exists())


if __name__ == '__main__':
    unittest.main()
