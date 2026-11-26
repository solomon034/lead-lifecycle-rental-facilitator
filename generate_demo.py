"""Regenerate the fictional rental demo CSVs with no external inputs."""

import csv
from datetime import date, timedelta
from pathlib import Path
import random


DEMO = Path(__file__).resolve().parent / 'demo'
FIRST_DAY = date(2030, 5, 1)
LAST_DAY = date(2030, 5, 31)
PEOPLE_COUNT = 120
REPEAT_COUNT = 24
SEED = 203005

LISTINGS = (
    ('HOME-01', 'Demo Larkglass Studio', 1075, 0, '2030-05-08', 'laundry'),
    ('HOME-02', 'Demo Bramblewake Flat', 1325, 1, '2030-05-14', 'laundry|outdoor_space'),
    ('HOME-03', 'Demo Alderfold Corner Flat', 1500, 2, '2030-05-12', 'bike_storage|laundry'),
    ('HOME-04', 'Demo Fernweft Terrace', 1450, 2, '', 'outdoor_space'),
    ('HOME-05', 'Demo Cloudmere Courtyard', 1600, 2, '2030-05-15', 'outdoor_space|laundry'),
    ('HOME-06', 'Demo Cloverglass Loft', 1790, 2, '2030-05-23', 'bike_storage|laundry'),
    ('HOME-07', 'Demo Juniperfold Cottage', 1925, 3, '2030-06-05', 'outdoor_space|laundry'),
    ('HOME-08', 'Demo Siltwing Flat', 1230, 1, '2030-05-09', 'bike_storage'),
    ('HOME-09', 'Demo Reedweave Duplex', 2125, 3, '2030-06-01', 'bike_storage|outdoor_space|laundry'),
    ('HOME-10', 'Demo Rainbell Studio', 990, 0, '', ''),
    ('HOME-11', 'Demo Pebbleloom Flat', 1390, 1, '2030-05-26', 'laundry'),
    ('HOME-12', 'Demo Copperfern Walk-Up', 1550, 2, '2030-06-12', 'bike_storage'),
    ('HOME-13', 'Demo Mossweft Bungalow', 1690, 2, '', 'outdoor_space|bike_storage'),
)
CHANNELS = ('web', 'phone', 'referral')
CHANNEL_WEIGHTS = (65, 25, 10)


def write_csv(folder, table, columns, rows):
    with (folder / f'{table}.csv').open('w', encoding='utf-8', newline='') as output:
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(columns)
        writer.writerows(rows)


def generate_demo(folder=DEMO):
    rng = random.Random(SEED)
    people = [(f'PERSON-{number:03d}', f'Demo Person {number:03d}')
              for number in range(1, PEOPLE_COUNT + 1)]

    # Each marketed listing gets an inquiry. Popularity then varies by listing.
    active_listing_ids = [row[0] for row in LISTINGS[:-1]]
    listing_weights = (14, 12, 12, 10, 11, 7, 4, 9, 4, 7, 6, 4)
    primary_listings = active_listing_ids + rng.choices(
        active_listing_ids, weights=listing_weights, k=PEOPLE_COUNT - len(active_listing_ids)
    )
    rng.shuffle(primary_listings)

    # Include both report boundaries and leave time for the May repeat inquiries.
    inquiry_dates = (
        [FIRST_DAY]
        + [FIRST_DAY + timedelta(days=rng.randint(0, 25)) for _ in range(PEOPLE_COUNT - 2)]
        + [LAST_DAY]
    )
    primary_inquiries = [
        (received_on, person_id, listing_id)
        for received_on, (person_id, _), listing_id in zip(inquiry_dates, people, primary_listings)
    ]
    inquiries = primary_inquiries.copy()

    # Four people also inquire outside May, on a different listing.
    outside_dates = (
        FIRST_DAY - timedelta(days=4), FIRST_DAY - timedelta(days=1),
        LAST_DAY + timedelta(days=1), LAST_DAY + timedelta(days=3),
    )
    outside_inquiries = [
        (outside_date, person_id, listing_id)
        for outside_date, (_, person_id, listing_id) in zip(outside_dates, primary_inquiries[-4:])
    ]
    repeat_inquiries = [
        (received_on + timedelta(days=rng.randint(1, 5)), person_id, listing_id)
        for received_on, person_id, listing_id in rng.sample(primary_inquiries[:-4], REPEAT_COUNT)
    ]
    for received_on, person_id, previous_listing in outside_inquiries + repeat_inquiries:
        alternatives = [listing_id for listing_id in active_listing_ids if listing_id != previous_listing]
        inquiries.append((received_on, person_id, rng.choice(alternatives)))

    leads, events = [], []
    for number, (received_on, person_id, listing_id) in enumerate(sorted(inquiries), start=1):
        lead_id = f'LEAD-{number:03d}'
        channel = rng.choices(CHANNELS, weights=CHANNEL_WEIGHTS)[0]
        leads.append((lead_id, person_id, listing_id, received_on, channel))
        if rng.random() < 0.14:
            continue

        reply_on = received_on + timedelta(days=rng.choice((0, 0, 1, 1, 2, 3)))
        events.append((reply_on, lead_id, 'reply'))
        if rng.random() < 0.18:
            events.append((reply_on + timedelta(days=rng.randint(1, 4)), lead_id, 'reply'))
        if rng.random() < 0.56:
            viewing_on = reply_on + timedelta(days=rng.randint(1, 9))
            events.append((viewing_on, lead_id, 'viewing'))
            if rng.random() < 0.14:
                events.append((viewing_on + timedelta(days=rng.randint(2, 6)), lead_id, 'viewing'))

    event_rows = [
        (f'EVENT-{number:03d}', lead_id, event_type, event_on)
        for number, (event_on, lead_id, event_type) in enumerate(sorted(events), start=1)
    ]
    folder.mkdir(parents=True, exist_ok=True)
    write_csv(folder, 'people', ('person_id', 'display_label'), people)
    write_csv(folder, 'listings',
              ('listing_id', 'title', 'monthly_rent', 'bedrooms', 'available_on', 'features'), LISTINGS)
    write_csv(folder, 'leads', ('lead_id', 'person_id', 'listing_id', 'received_on', 'channel'), leads)
    write_csv(folder, 'events', ('event_id', 'lead_id', 'event_type', 'event_on'), event_rows)


if __name__ == '__main__':
    generate_demo()
