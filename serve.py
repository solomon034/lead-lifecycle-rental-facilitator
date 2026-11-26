"""Serve the fictional demo locally using only the Python standard library."""

from contextlib import closing
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

from lead_demo import DEFAULT_END, DEFAULT_START, FEATURES, find_homes, lead_report, open_demo


def render(query):
    values = {key: entries[0] for key, entries in parse_qs(query, keep_blank_values=True).items()}

    def field(name, default):
        return values.get(name, default)

    start, end = field('start', DEFAULT_START), field('end', DEFAULT_END)
    rent, beds = field('max_rent', '1600'), field('min_bedrooms', '2')
    deadline, feature = field('available_by', '2030-05-15'), field('feature', '')
    options = ''.join(
        f'<option value="{name}"{" selected" if name == feature else ""}>{name.replace("_", " ").title()}</option>'
        for name in sorted(FEATURES)
    )
    with closing(open_demo()) as db:
        try:
            report = report_markup(lead_report(db, start, end))
        except ValueError as exc:
            report = f'<p role="alert">{escape(str(exc))}</p>'
        try:
            budget, bedrooms = int(rent), int(beds)
        except ValueError:
            search = '<p role="alert">Enter whole numbers for rent and bedrooms.</p>'
        else:
            try:
                search = search_markup(find_homes(db, max_rent=budget, min_bedrooms=bedrooms,
                                                  available_by=deadline, feature=feature))
            except ValueError as exc:
                search = f'<p role="alert">{escape(str(exc))}</p>'

    return f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lead Lifecycle &amp; Rental Facilitator</title>
<style>
  * {{ box-sizing: border-box }}
  body {{ margin: 0 auto; max-width: 66rem; padding: clamp(1rem, 4vw, 3rem); background: #f8f6ef; color: #252c28; font: 1rem/1.55 system-ui, sans-serif }}
  h1, h2 {{ font-family: Georgia, serif; line-height: 1.15 }}
  h1 {{ font-size: clamp(2rem, 5vw, 3.5rem); margin-block: .3em }}
  h2 {{ font-size: 1.7rem; margin-top: 0 }}
  header {{ margin-bottom: 2rem }}
  .eyebrow {{ color: #315947; font-weight: 700 }}
  main {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; align-items: start }}
  section {{ min-width: 0; padding: 1.2rem; background: white; border: 1px solid #c7cec6; border-radius: 12px }}
  .fields {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .75rem }}
  label {{ display: flex; flex-direction: column; font-weight: 600; gap: .25rem }}
  input, select {{ min-width: 0; width: 100%; border: 1px solid #687b70; border-radius: 5px; background: white; padding: .55rem; font: inherit }}
  button {{ margin: 1rem 0; background: #234638; color: white; border: 0; border-radius: 5px; padding: .65rem 1rem; font: inherit; cursor: pointer }}
  :focus-visible {{ outline: 3px solid #436c54; outline-offset: 3px }}
  .table-wrap {{ overflow-x: auto }}
  table {{ border-collapse: collapse; width: 100%; font-size: .9rem }}
  th, td {{ text-align: left; padding: .45rem; border-bottom: 1px solid #dce2dc }}
  .matches {{ padding-inline-start: 1.25rem }}
  .matches li {{ margin-bottom: .7rem }}
  blockquote {{ margin: 0; padding: .75rem; background: #edf3ee }}
  @media (max-width: 50rem) {{ main {{ grid-template-columns: 1fr }} }}
  @media (max-width: 25rem) {{ .fields {{ grid-template-columns: 1fr }} }}
</style>
<header><div class="eyebrow">Fictional data demo</div><h1>Lead Lifecycle &amp; Rental Facilitator</h1>
<p>Track inquiry activity and compare stated search criteria with a sample rental catalog.</p></header>
<main>
<section aria-labelledby="report"><h2 id="report">Lead lifecycle</h2>
<p>Counts inquiries received in the selected period, with replies and viewings observed by its end. The total counts each person once across all listings.</p>
<form method="get" action="/#report">{hidden_fields(max_rent=rent, min_bedrooms=beds, available_by=deadline, feature=feature)}
<div class="fields">
<label>Start date <input type="date" name="start" value="{escape(start)}" required></label>
<label>End date <input type="date" name="end" value="{escape(end)}" required></label>
</div>
<button type="submit">Refresh report</button></form>{report}</section>
<section aria-labelledby="find"><h2 id="find">Find a Home</h2>
<p>Enter listing criteria. Every result explains the match. All prices and dates are invented.</p>
<form method="get" action="/#find">{hidden_fields(start=start, end=end)}
<div class="fields">
<label>Monthly rent limit ($) <input type="number" name="max_rent" min="1" step="1" value="{escape(rent)}" required></label>
<label>Minimum bedrooms <input type="number" name="min_bedrooms" min="0" step="1" value="{escape(beds)}" required></label>
<label>Available by (optional) <input type="date" name="available_by" value="{escape(deadline)}"></label>
<label>Feature (optional) <select name="feature"><option value="">Any</option>{options}</select></label>
</div>
<button type="submit">Find matches</button></form>{search}</section>
</main></html>'''


def hidden_fields(**fields):
    return ''.join(f'<input type="hidden" name="{name}" value="{escape(value)}">' for name, value in fields.items())


def report_markup(report):
    columns = ('people', 'inquiries', 'with_reply', 'with_viewing')

    def cells(row):
        return ''.join(f'<td>{row[column]}</td>' for column in columns)

    body = ''.join(
        f'<tr><th scope="row">{escape(row["title"])}</th>{cells(row)}</tr>'
        for row in report['listings']
    )
    footer = f'<tfoot><tr><th scope="row">Total</th>{cells(report["totals"])}</tr></tfoot>'
    return ('<div class="table-wrap" tabindex="0" aria-label="Lead report table"><table><thead><tr>'
            '<th scope="col">Listing</th><th scope="col">People</th><th scope="col">Inquiries</th><th scope="col">With reply</th>'
            '<th scope="col">With viewing</th></tr></thead><tbody>' + body + '</tbody>' + footer + '</table></div>')


def search_markup(result):
    rows = ''.join(
        f'<li><strong>{escape(listing["title"])}</strong> · ${listing["monthly_rent"]:,}/mo · '
        f'{listing["bedrooms"]} bedrooms · {escape(listing["available_on"] or "date unknown")}<br>'
        f'{escape(" · ".join(listing["reasons"]))}</li>' for listing in result['matches']
    )
    matches = f'<ul class="matches">{rows}</ul>' if rows else '<p>No listings meet the selected criteria.</p>'
    count = result['date_not_confirmed']
    excluded = f'<p>Excluded {count} otherwise matching listing(s) with no recorded date.</p>' if count else ''
    reply = result['sample_reply']
    draft = f'<h3>Sample reply for review</h3><blockquote>{escape(reply)}</blockquote>' if reply else ''
    return matches + excluded + draft


class DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        if url.path != '/':
            self.send_error(404)
            return
        body = render(url.query).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # The demo has no analytics or request logs.
        return


if __name__ == '__main__':
    with HTTPServer(('127.0.0.1', 4180), DemoHandler) as server:
        print('Demo: http://127.0.0.1:4180', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
