"""Standalone analytics and listing search using original fictional fixtures."""

import argparse
from contextlib import closing
import csv
from datetime import date
import json
from pathlib import Path
import sqlite3


PROJECT = Path(__file__).resolve().parent
DEMO = PROJECT / 'demo'
DEFAULT_START = '2030-05-01'
DEFAULT_END = '2030-05-31'
FEATURES = frozenset({'laundry', 'outdoor_space', 'bike_storage'})
SCHEMAS = {
    'listings': ('listing_id', 'title', 'monthly_rent', 'bedrooms', 'available_on', 'features'),
    'people': ('person_id', 'display_label'),
    'leads': ('lead_id', 'person_id', 'listing_id', 'received_on', 'channel'),
    'events': ('event_id', 'lead_id', 'event_type', 'event_on'),
}


def iso_date(value):
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError('Enter a valid date as YYYY-MM-DD.') from exc
    if parsed.isoformat() != value:
        raise ValueError('Enter a valid date as YYYY-MM-DD.')
    return value


def read_rows(folder, table):
    words = SCHEMAS[table]
    with (folder / f'{table}.csv').open(newline='', encoding='utf-8-sig') as source:
        reader = csv.reader(source)
        if tuple(next(reader, ())) != words:
            raise ValueError(f'{table}.csv: unexpected column names or order.')
        for number, values in enumerate(reader, start=2):
            if len(values) != len(words):
                raise ValueError(f'{table}.csv row {number}: wrong number of fields.')
            fields = [value.strip() for value in values]
            try:
                if any(not field for key, field in zip(words, fields) if key not in {'available_on', 'features'}):
                    raise ValueError('Required fields are missing.')
                if table == 'listings':
                    fields[2], fields[3] = int(fields[2]), int(fields[3])
                    if not set(filter(None, fields[5].split('|'))) <= FEATURES:
                        raise ValueError('An unknown listing feature was supplied.')
                    fields[4] = iso_date(fields[4]) if fields[4] else None
                elif table in {'leads', 'events'}:
                    date_column = words.index('received_on' if table == 'leads' else 'event_on')
                    fields[date_column] = iso_date(fields[date_column])
            except ValueError as exc:
                raise ValueError(f'{table}.csv row {number}: {exc}') from exc
            yield tuple(fields)


def open_demo(folder=DEMO):
    connection = sqlite3.connect(':memory:')
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript((PROJECT / 'model.sql').read_text(encoding='utf-8'))
        with connection:
            for table, fields in SCHEMAS.items():
                placeholders = ', '.join('?' for _ in fields)
                try:
                    connection.executemany(f'INSERT INTO {table} VALUES ({placeholders})', read_rows(folder, table))
                except sqlite3.IntegrityError as exc:
                    raise ValueError(f'{table}.csv contains a duplicate, invalid, or unmatched record.') from exc
            if connection.execute('''
                SELECT 1 FROM events JOIN leads USING (lead_id)
                WHERE event_on < received_on LIMIT 1
            ''').fetchone():
                raise ValueError('An engagement event predates its lead.')
    except (OSError, ValueError, sqlite3.Error):
        connection.close()
        raise
    return connection


def lead_report(connection, start, end):
    """Leads received in the period, with milestones observed by its end."""
    if iso_date(start) > iso_date(end):
        raise ValueError('The reporting start must be on or before the end.')
    total, *listing_rows = connection.execute('''
        WITH cohort AS (
            SELECT * FROM lead_milestones WHERE received_on BETWEEN :start AND :end
        )
        SELECT listings.listing_id, listings.title,
               count(DISTINCT cohort.person_id) AS people,
               count(cohort.lead_id) AS inquiries,
               count(CASE WHEN first_reply <= :end THEN 1 END) AS with_reply,
               count(CASE WHEN first_viewing <= :end THEN 1 END) AS with_viewing
        FROM listings
        LEFT JOIN cohort USING (listing_id)
        GROUP BY listings.listing_id, listings.title
        UNION ALL
        SELECT NULL, 'Total', count(DISTINCT person_id), count(*),
               count(CASE WHEN first_reply <= :end THEN 1 END),
               count(CASE WHEN first_viewing <= :end THEN 1 END)
        FROM cohort
        ORDER BY listing_id NULLS FIRST
    ''', {'start': start, 'end': end})
    return {
        'start': start,
        'end': end,
        'totals': {key: total[key] for key in ('people', 'inquiries', 'with_reply', 'with_viewing')},
        'listings': [dict(row) for row in listing_rows],
    }


def find_homes(connection, *, max_rent, min_bedrooms=0, available_by='', feature=''):
    """Match listing attributes only, without evaluating a person or household."""
    if max_rent < 1 or min_bedrooms < 0:
        raise ValueError('Enter a positive budget and a bedroom count of zero or more.')
    if available_by:
        iso_date(available_by)
    if feature and feature not in FEATURES:
        raise ValueError('Choose a feature from the listing catalog.')

    matches = []
    date_not_confirmed = 0
    for listing in connection.execute('SELECT * FROM listings ORDER BY monthly_rent, listing_id'):
        features = set(listing['features'].split('|'))
        if listing['monthly_rent'] > max_rent or listing['bedrooms'] < min_bedrooms:
            continue
        if feature and feature not in features:
            continue
        known_date = listing['available_on']
        if available_by and not known_date:
            date_not_confirmed += 1
            continue
        if available_by and known_date > available_by:
            continue
        reasons = ['Within budget', 'Meets bedroom minimum']
        if available_by:
            reasons.append('Listed date meets the deadline')
        if feature:
            reasons.append(f'Lists {feature.replace("_", " ")}')
        matches.append({**dict(listing), 'reasons': reasons})
    return {
        'matches': matches,
        'date_not_confirmed': date_not_confirmed,
        'sample_reply': draft_reply(matches[0]) if matches else '',
    }


def draft_reply(listing):
    bedrooms = listing['bedrooms']
    layout = 'a studio layout' if not bedrooms else f'{bedrooms} bedroom' + ('s' if bedrooms != 1 else '')
    date_summary = (
        f" The catalog lists {listing['available_on']} as the availability date."
        if listing['available_on'] else ' The availability date is not listed.'
    )
    return (
        f"One option is {listing['title']}, listed at ${listing['monthly_rent']:,} per month "
        f"with {layout}.{date_summary} "
        'Would you like to review the listing details?'
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    report = commands.add_parser('report')
    report.add_argument('--start', default=DEFAULT_START)
    report.add_argument('--end', default=DEFAULT_END)
    search = commands.add_parser('find')
    search.add_argument('--max-rent', type=int, required=True)
    search.add_argument('--min-bedrooms', type=int, default=0)
    search.add_argument('--available-by', default='')
    search.add_argument('--feature', choices=sorted(FEATURES), default='')
    args = parser.parse_args()
    try:
        with closing(open_demo()) as connection:
            if args.command == 'report':
                output = lead_report(connection, args.start, args.end)
            else:
                output = find_homes(connection, max_rent=args.max_rent, min_bedrooms=args.min_bedrooms,
                                    available_by=args.available_by, feature=args.feature)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
