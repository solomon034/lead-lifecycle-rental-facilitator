PRAGMA foreign_keys = ON;

CREATE TABLE listings (
    listing_id TEXT PRIMARY KEY NOT NULL,
    title TEXT NOT NULL CHECK (length(title) > 0),
    monthly_rent INTEGER NOT NULL CHECK (monthly_rent > 0),
    bedrooms INTEGER NOT NULL CHECK (bedrooms >= 0),
    available_on TEXT,
    features TEXT NOT NULL
);

CREATE TABLE people (
    person_id TEXT PRIMARY KEY NOT NULL,
    display_label TEXT NOT NULL UNIQUE
);

CREATE TABLE leads (
    lead_id TEXT PRIMARY KEY NOT NULL,
    person_id TEXT NOT NULL REFERENCES people(person_id),
    listing_id TEXT NOT NULL REFERENCES listings(listing_id),
    received_on TEXT NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('web', 'phone', 'referral'))
);

CREATE TABLE events (
    event_id TEXT PRIMARY KEY NOT NULL,
    lead_id TEXT NOT NULL REFERENCES leads(lead_id),
    event_type TEXT NOT NULL CHECK (event_type IN ('reply', 'viewing')),
    event_on TEXT NOT NULL
);

-- One row per lead. Multiple events of the same type retain the first date.
CREATE VIEW lead_milestones AS
SELECT leads.lead_id, leads.person_id, leads.listing_id, leads.received_on,
       min(CASE WHEN event_type = 'reply' THEN event_on END) AS first_reply,
       min(CASE WHEN event_type = 'viewing' THEN event_on END) AS first_viewing
FROM leads
LEFT JOIN events USING (lead_id)
GROUP BY leads.lead_id, leads.person_id, leads.listing_id, leads.received_on;
