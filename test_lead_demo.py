from contextlib import closing
import csv
from datetime import date
from pathlib import Path
import shutil
import tempfile
import unittest

from generate_demo import generate_demo
from lead_demo import DEMO, find_homes, lead_report, open_demo
from serve import render


class LeadDemoTests(unittest.TestCase):
    def setUp(self):
        self.db = self.enterContext(closing(open_demo()))

    def test_generator_recreates_checked_in_fixtures(self):
        with tempfile.TemporaryDirectory() as directory:
            regenerated = Path(directory)
            generate_demo(regenerated)
            for table in ('people', 'listings', 'leads', 'events'):
                filename = f'{table}.csv'
                with self.subTest(table=table):
                    self.assertEqual((regenerated / filename).read_text(encoding='utf-8'),
                                     (DEMO / filename).read_text(encoding='utf-8'))

    def test_report_matches_independent_csv_calculation(self):
        def fixture(name):
            with (DEMO / f'{name}.csv').open(newline='', encoding='utf-8') as source:
                return list(csv.DictReader(source))

        start, end = date(2030, 5, 1), date(2030, 5, 31)
        people = {person['person_id'] for person in fixture('people')}
        cohort = {lead['lead_id']: lead for lead in fixture('leads')
                  if start <= date.fromisoformat(lead['received_on']) <= end}
        events = fixture('events')

        def expected(inquiry_ids):
            seen = {role: set() for role in ('reply', 'viewing')}
            for event in events:
                if event['lead_id'] in inquiry_ids and date.fromisoformat(event['event_on']) <= end:
                    seen[event['event_type']].add(event['lead_id'])
            return {
                'people': len({cohort[key]['person_id'] for key in inquiry_ids}),
                'inquiries': len(inquiry_ids),
                'with_reply': len(seen['reply']),
                'with_viewing': len(seen['viewing']),
            }

        report = lead_report(self.db, start.isoformat(), end.isoformat())
        self.assertEqual(report['totals'], expected(set(cohort)))
        self.assertEqual(report['totals']['people'], len(people))
        self.assertGreaterEqual(len(people), 100)
        self.assertGreater(report['totals']['inquiries'], len(people))
        self.assertGreater(sum(row['people'] for row in report['listings']), len(people))
        self.assertTrue(any(row['inquiries'] == 0 for row in report['listings']))
        self.assertEqual({row['listing_id'] for row in report['listings']},
                         {row['listing_id'] for row in fixture('listings')})
        for row in report['listings']:
            count = expected({key for key, lead in cohort.items() if lead['listing_id'] == row['listing_id']})
            self.assertEqual({key: row[key] for key in count}, count)

    def test_single_day_includes_lead_at_both_boundaries(self):
        self.db.execute("INSERT INTO people VALUES ('TEST-PERSON', 'Test person')")
        self.db.execute("INSERT INTO listings VALUES ('TEST-HOME', 'Test home', 1000, 2, NULL, '')")
        self.db.execute("INSERT INTO leads VALUES ('TEST-LEAD', 'TEST-PERSON', 'TEST-HOME', '2031-03-01', 'web')")
        self.db.execute("INSERT INTO events VALUES ('TEST-REPLY-1', 'TEST-LEAD', 'reply', '2031-03-01')")
        self.db.execute("INSERT INTO events VALUES ('TEST-REPLY-2', 'TEST-LEAD', 'reply', '2031-03-01')")
        self.db.execute("INSERT INTO events VALUES ('TEST-VIEW', 'TEST-LEAD', 'viewing', '2031-03-02')")
        report = lead_report(self.db, '2031-03-01', '2031-03-01')
        self.assertEqual(report['totals'], {'people': 1, 'inquiries': 1, 'with_reply': 1, 'with_viewing': 0})

    def add_search_fixture(self):
        self.db.executemany('INSERT INTO listings VALUES (?, ?, ?, ?, ?, ?)', [
            ('TEST-UNKNOWN', 'Test unknown date', 1, 90, None, 'outdoor_space'),
            ('TEST-EXACT', 'Test exact match', 2, 90, '2030-05-14', 'outdoor_space'),
            ('TEST-LATER', 'Test later date', 2, 90, '2030-05-15', 'bike_storage'),
        ])

    def test_report_rejects_invalid_or_reversed_dates(self):
        for start, end in [('2030-05-33', '2030-05-12'), ('2030-05-13', '2030-05-12')]:
            with self.subTest(start=start), self.assertRaises(ValueError):
                lead_report(self.db, start, end)

    def test_search_includes_exact_boundaries_and_explains_unknown_date(self):
        self.add_search_fixture()
        result = find_homes(self.db, max_rent=2, min_bedrooms=90, available_by='2030-05-14')
        self.assertEqual([r['listing_id'] for r in result['matches']], ['TEST-EXACT'])
        self.assertEqual(result['date_not_confirmed'], 1)
        self.assertIn('The catalog lists 2030-05-14', result['sample_reply'])

    def test_feature_filter_and_no_date_requirement(self):
        self.add_search_fixture()
        result = find_homes(self.db, max_rent=2, min_bedrooms=90, feature='outdoor_space')
        self.assertEqual([r['listing_id'] for r in result['matches']], ['TEST-UNKNOWN', 'TEST-EXACT'])
        self.assertIn('availability date is not listed', result['sample_reply'])

    def test_no_match_does_not_invent_a_reply(self):
        result = find_homes(self.db, max_rent=500, min_bedrooms=2)
        self.assertEqual(result['matches'], [])
        self.assertEqual(result['sample_reply'], '')

    def test_data_contract_rejects_duplicate_orphan_and_impossible_events(self):
        event = self.db.execute('SELECT * FROM events LIMIT 1').fetchone()
        for table, row, message in [
            ('events', ','.join(event), 'duplicate'),
            ('events', 'TEST-ORPHAN,NO-SUCH-LEAD,reply,2030-05-06', 'unmatched'),
            ('events', f'TEST-EARLY,{event["lead_id"]},reply,2029-01-01', 'predates'),
            ('leads', 'TEST-LEAD,NO-SUCH-PERSON,HOME-01,2030-05-06,web', 'unmatched'),
        ]:
            with self.subTest(row=row), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                for source in DEMO.glob('*.csv'):
                    shutil.copyfile(source, folder / source.name)
                with (folder / f'{table}.csv').open('a', encoding='utf-8') as source:
                    source.write(row + '\n')
                with self.assertRaisesRegex(ValueError, message):
                    open_demo(folder)

    def test_browser_forms_show_validation_and_escape_invalid_input(self):
        html = render('start=%3Cscript%3E&max_rent=invalid')
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('Enter a valid date', html)
        self.assertIn('Enter whole numbers', html)


if __name__ == '__main__':
    unittest.main()
