"""Archive retained Workers log counts once daily; standard library only."""
import argparse
import csv
import io
import json
import os
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import date, datetime, time as day_time, timedelta, timezone
from pathlib import Path

TZ = timezone(timedelta(hours=8))
FIRST_DAY = date(2026, 10, 4)
PAGE_SIZE = 2000
FIELDS = ['date', 'category', 'agent', 'path', 'visits']
BOT_CATEGORIES = {'ai_bot', 'search_bot', 'other_bot'}


def day_bounds(day):
    start = datetime.combine(day, day_time.min, TZ)
    return int(start.timestamp() * 1000), int((start + timedelta(days=1)).timestamp() * 1000)


def query_body(start, end, cursor=None):
    filters = [
        {'key': '$workers.scriptName', 'operation': 'eq', 'type': 'string', 'value': 'dgolubenko'},
        {'key': 'event', 'operation': 'eq', 'type': 'string', 'value': 'site_visit'},
        {'key': 'method', 'operation': 'eq', 'type': 'string', 'value': 'GET'},
        {'key': 'status', 'operation': 'eq', 'type': 'number', 'value': 200},
        {'key': 'content_type', 'operation': 'eq', 'type': 'string', 'value': 'text/html'},
        {'key': 'category', 'operation': 'in', 'type': 'string', 'value': 'ai_bot,search_bot,other_bot'},
    ]
    body = {'queryId': 'daily-bot-archive', 'view': 'events', 'dry': True,
            'timeframe': {'from': start, 'to': end}, 'limit': PAGE_SIZE,
            'parameters': {'datasets': [], 'filterCombination': 'and', 'filters': filters}}
    if cursor:
        body.update(offset=cursor, offsetDirection='next')
    return body


def request_page(account, token, body):
    url = f'https://api.cloudflare.com/client/v4/accounts/{account}/workers/observability/telemetry/query'
    for attempt in range(4):
        request = urllib.request.Request(url, data=json.dumps(body).encode(),
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.load(response)
            if result.get('success') is not True:
                raise RuntimeError('Cloudflare query failed; existing archive was preserved')
            return result['result']
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise RuntimeError(f'Cloudflare query HTTP {error.code}; no archive changes') from None
        except (urllib.error.URLError, TimeoutError):
            if attempt == 3:
                raise RuntimeError('Cloudflare query unavailable; no archive changes') from None
        time.sleep(2 ** attempt)


def payload(event):
    source = event.get('source', {})
    if isinstance(source, str):
        try:
            source = json.loads(source)
        except json.JSONDecodeError:
            raise RuntimeError('Unexpected log payload; refusing an incomplete archive') from None
    if not isinstance(source, dict):
        raise RuntimeError('Unexpected log payload type')
    return source


def fetch_day(day, now, query):
    start, end = day_bounds(day)
    end = min(end, int(now.timestamp() * 1000))
    cursor = None
    cursors = set()
    seen = set()
    counts = Counter()
    expected_count = None
    for _ in range(200):
        response = query(query_body(start, end, cursor))
        block = response.get('events')
        if not isinstance(block, dict) or not isinstance(block.get('events'), list):
            raise RuntimeError('Cloudflare returned no event list; existing archive was preserved')
        events = block['events']
        if expected_count is None:
            expected_count = block.get('count')
        for event in events:
            identity = event.get('$metadata', {}).get('id')
            if not identity:
                raise RuntimeError('Event without ID; refusing to risk duplicate counts')
            if identity in seen:
                continue
            seen.add(identity)
            record = payload(event)
            timestamp = event.get('timestamp')
            if not isinstance(timestamp, (int, float)):
                raise RuntimeError('Event without timestamp')
            # Explicit half-open boundaries avoid midnight duplicates.
            if not start <= timestamp < end:
                continue
            if record.get('event') != 'site_visit' or record.get('method') != 'GET' or record.get('status') != 200 or record.get('content_type') != 'text/html':
                continue
            if record.get('category') not in BOT_CATEGORIES:
                continue
            path = record.get('path')
            agent = record.get('agent')
            if not isinstance(path, str) or not path.startswith('/') or not isinstance(agent, str):
                raise RuntimeError('Invalid page or agent in log record')
            # Group both legacy .html and clean URLs under the same page.
            if path == '/index.html':
                path = '/'
            elif path.endswith('.html'):
                path = path[:-5]
            counts[(record['category'], agent, path)] += 1
        if len(events) < PAGE_SIZE:
            if isinstance(expected_count, (int, float)) and len(seen) < expected_count:
                raise RuntimeError('Incomplete or sampled event result; archive was preserved')
            return counts
        next_cursor = events[-1].get('$metadata', {}).get('id')
        if not next_cursor or next_cursor in cursors:
            raise RuntimeError('Pagination stopped advancing; archive was preserved')
        cursors.add(next_cursor)
        cursor = next_cursor
    raise RuntimeError('Pagination safety limit reached; archive was preserved')


def csv_text(rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(FIELDS)
    writer.writerows(rows)
    return stream.getvalue()


def write_day(root, day, counts, partial):
    rows = [[day.isoformat(), *key, value] for key, value in sorted(counts.items())]
    (root / 'daily').mkdir(parents=True, exist_ok=True)
    (root / 'coverage').mkdir(parents=True, exist_ok=True)
    target = root / 'daily' / f'{day}.csv'
    target.write_text(csv_text(rows), encoding='utf-8')
    coverage = {'date': day.isoformat(), 'timezone': 'Asia/Shanghai',
                'status': 'partial' if partial else 'closed_day',
                'source': 'retained_workers_logs', 'logged_page_visits': sum(counts.values()),
                'note': 'Observed log records; not unique visitors or independently verified bot identities.'}
    (root / 'coverage' / f'{day}.json').write_text(json.dumps(coverage, indent=2) + '\n', encoding='utf-8')


def rebuild_summary(root):
    rows = []
    for file in sorted((root / 'daily').glob('*.csv')):
        with file.open(encoding='utf-8', newline='') as stream:
            rows.extend(list(csv.reader(stream))[1:])
    (root / 'all-days.csv').write_text(csv_text(rows), encoding='utf-8')
    totals = Counter()
    for row in rows:
        totals[(row[1], row[2])] += int(row[4])
    table = '| Category | Agent | Logged page visits |\n|---|---|---:|\n'
    for (category, agent), total in sorted(totals.items()):
        table += f'| {category} | {agent.replace(chr(124), " ")} | {total} |\n'
    report = '# Bot visits archive\n\nPrivate daily totals, timezone **Asia/Shanghai**.\n\n'
    report += '[Download all daily rows](all-days.csv) · [Daily CSV files](daily) · [Coverage notes](coverage)\n\n' + table
    report += '\nCounts represent successful GET requests for HTML pages, not unique users. Bot names are self-reported User-Agent hints. The first day includes setup/testing traffic. Cloudflare log sampling or dropped logs can reduce observed counts. A bot request does not prove indexing or citation.\n'
    (root / 'README.md').write_text(report, encoding='utf-8')


def archive(root, now, query, include_today=False):
    today = now.astimezone(TZ).date()
    days = [today - timedelta(days=2), today - timedelta(days=1)]
    if include_today:
        days.append(today)
    days = [day for day in days if day >= FIRST_DAY]
    # Query all days first. Failed/partial exports never erase prior files.
    fetched = [(day, fetch_day(day, now, query), day == today) for day in days]
    root.mkdir(parents=True, exist_ok=True)
    for day, counts, partial in fetched:
        write_day(root, day, counts, partial)
    rebuild_summary(root)
    return len(fetched)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--include-today', action='store_true')
    args = parser.parse_args()
    token = os.environ.get('CLOUDFLARE_LOGS_TOKEN', '')
    account = os.environ.get('CLOUDFLARE_ACCOUNT_ID', '')
    if not token or not account:
        raise SystemExit('Missing Cloudflare archive credentials')
    count = archive(Path('analytics'), datetime.now(timezone.utc),
                    lambda body: request_page(account, token, body), args.include_today)
    print(f'Archived {count} day(s); older CSV files retained.')


if __name__ == '__main__':
    main()
