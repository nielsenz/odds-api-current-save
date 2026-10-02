"""Collect bounded, resumable research odds without modifying production feeds.

Credentials come from ODDS_API_KEY or --key-file, never manifests/logs.
Historical responses retain requested/effective times and raw outcome identities.
"""
import argparse
import csv
import gzip
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = 'https://api.the-odds-api.com/v4/'


def instant(value):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('Odds timestamps must include an offset')
    return stamp


class Capture:
    def __init__(self, root, key, budget):
        self.root, self.key, self.budget = root, key, budget
        root.mkdir(parents=True, exist_ok=True)
        self.journal = root / 'requests.jsonl'
        self.records = [json.loads(x) for x in self.journal.read_text().splitlines()] if self.journal.exists() else []
        self.spent = sum(int(x.get('cost', 0)) for x in self.records)
        quotas = [int(r['remaining']) for r in self.records if r.get('remaining') is not None]
        self.remaining = quotas[-1] if quotas else None

    def get(self, path, params, label, estimate):
        identity = json.dumps([path, params], sort_keys=True)
        token = hashlib.sha256(identity.encode()).hexdigest()[:20]
        target = self.root / 'raw' / (token + '.json.gz')
        if target.exists():
            if any(r['id'] == token and r['status'] == 'invalid_effective_snapshot' for r in self.records):
                raise ValueError('Cached historical response is later than requested cutoff')
            with gzip.open(target, 'rt') as f:
                return json.load(f)
        if self.spent + estimate > self.budget or (self.remaining is not None and self.remaining < estimate + 1000):
            return None
        target.parent.mkdir(exist_ok=True)
        receipt = dict(id=token, path=path, parameters=params, label=label,
                       requested_at_utc=datetime.now(timezone.utc).isoformat())
        query = urllib.parse.urlencode(dict(params, apiKey=self.key))
        try:
            with urllib.request.urlopen(BASE + path + '?' + query, timeout=45) as r:
                payload = json.load(r)
                receipt.update(status=r.status, cost=int(r.headers.get('x-requests-last', estimate)),
                               remaining=r.headers.get('x-requests-remaining'),
                               account_used=r.headers.get('x-requests-used'), response_date=r.headers.get('Date'))
        except urllib.error.HTTPError as e:
            receipt.update(status=e.code, cost=int(e.headers.get('x-requests-last', 0)),
                           remaining=e.headers.get('x-requests-remaining'))
            payload = None
        except Exception as e:
            receipt.update(status='transport_error', error_type=type(e).__name__, cost=0)
            payload = None
        receipt['received_at_utc'] = datetime.now(timezone.utc).isoformat()
        self.spent += receipt['cost']
        if receipt.get('remaining') is not None:
            self.remaining = int(receipt['remaining'])
        invalid_snapshot = False
        if payload is not None:
            if isinstance(payload, dict) and payload.get('timestamp') and params.get('date'):
                if instant(payload['timestamp']) > instant(params['date']):
                    invalid_snapshot = True
                    receipt['status'] = 'invalid_effective_snapshot'
            with gzip.open(target, 'wt') as f:
                json.dump(payload, f)
            receipt['raw_file'] = str(target.relative_to(self.root))
            receipt['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
        with self.journal.open('a') as f:
            f.write(json.dumps(receipt) + '\n')
        self.records.append(receipt)
        if len(self.records) % 25 == 0 or receipt['status'] != 200:
            print(json.dumps(dict(requests=len(self.records), spent=self.spent,
                                  remaining=self.remaining, label=label, status=receipt['status'])), flush=True)
        if receipt['status'] in (401, 403, 429):
            raise RuntimeError('Collector stopped on HTTP ' + str(receipt['status']))
        if invalid_snapshot:
            raise ValueError('Historical response is later than requested cutoff')
        time.sleep(.1)
        return payload

    def odds(self, sport, when, markets, label):
        historical = when is not None
        params = dict(regions='us', markets=markets, oddsFormat='american')
        if historical:
            params['date'] = when
        prefix = 'historical/' if historical else ''
        return self.get(prefix + 'sports/' + sport + '/odds', params, label,
                        len(markets.split(',')) * (10 if historical else 1))

    def event(self, sport, event_id, when, markets, label):
        return self.get('historical/sports/' + sport + '/events/' + event_id + '/odds',
                        dict(regions='us', markets=markets, oddsFormat='american', date=when),
                        label, 10 * len(markets.split(',')))

    def export(self):
        fields = ['capture_id', 'label', 'sport', 'event_id', 'commence_time', 'home_team', 'away_team',
                  'requested_snapshot', 'effective_snapshot', 'retrieved_at', 'book', 'book_update',
                  'market', 'market_update', 'outcome', 'description', 'point', 'price', 'pre_start',
                  'requested_cutoff_safe', 'vendor_snapshot_consistent']
        count = 0
        with (self.root / 'outcomes.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader()
            for receipt in self.records:
                if not receipt.get('raw_file') or receipt['status'] != 200:
                    continue
                with gzip.open(self.root / receipt['raw_file'], 'rt') as raw:
                    payload = json.load(raw)
                effective = payload.get('timestamp', receipt['received_at_utc']) if isinstance(payload, dict) else receipt['received_at_utc']
                data = payload.get('data', payload) if isinstance(payload, dict) else payload
                events = data if isinstance(data, list) else [data]
                for event in events:
                    if not isinstance(event, dict) or 'bookmakers' not in event:
                        continue
                    for book in event['bookmakers']:
                        for market in book['markets']:
                            cutoff = receipt['parameters'].get('date', receipt['received_at_utc'])
                            updated = market.get('last_update') or book.get('last_update')
                            pre_start = bool(event.get('commence_time') and instant(effective) < instant(event['commence_time']))
                            safe = bool(pre_start and updated and instant(updated) <= instant(cutoff)
                                        and instant(updated) < instant(event['commence_time']))
                            consistent = bool(updated and instant(updated) <= instant(effective))
                            for outcome in market['outcomes']:
                                writer.writerow(dict(capture_id=receipt['id'], label=receipt['label'],
                                    sport=event.get('sport_key'), event_id=event['id'], commence_time=event.get('commence_time'),
                                    home_team=event.get('home_team'), away_team=event.get('away_team'),
                                    requested_snapshot=receipt['parameters'].get('date'), effective_snapshot=effective,
                                    retrieved_at=receipt['received_at_utc'], book=book['key'], book_update=book.get('last_update'),
                                    market=market['key'], market_update=market.get('last_update'), outcome=outcome['name'],
                                    description=outcome.get('description'), point=outcome.get('point'), price=outcome['price'],
                                    pre_start=pre_start, requested_cutoff_safe=safe, vendor_snapshot_consistent=consistent))
                                count += 1
        summary = dict(requests=len(self.records), credits_spent=self.spent, budget=self.budget,
                       account_remaining_last_observed=self.remaining, outcome_rows=count,
                       errors=[{k:r.get(k) for k in ('id','label','status','error_type')} for r in self.records if r['status'] != 200],
                       production_feeds_modified=False, status='research_only')
        (self.root / 'summary.json').write_text(json.dumps(summary, indent=2))
        print(json.dumps(summary), flush=True)


def dates(start, end, step=1):
    d, stop = datetime.fromisoformat(start), datetime.fromisoformat(end)
    while d <= stop:
        yield d.strftime('%Y-%m-%d')
        d += timedelta(days=step)


def iso(d):
    return d.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--key-file', type=Path)
    ap.add_argument('--budget', type=int, default=12000)
    ap.add_argument('--plan', action='store_true')
    args = ap.parse_args()
    plan = {'live_reference': 'NFL/CFB/NHL/WNBA main markets and NFL/NHL supported outright boards',
            'nfl_2025': '18 weekly main boards, 44 outcome-independent game samples with 24h/30m prop pairs',
            'cbb': '2025 November–December daily 12:00 UTC spreads',
            'wnba': '2026 every-third-day 15:00 UTC spread/total boards and 24 sampled 30m closes',
            'wnba_props': 'Three-event points/rebounds/assists pilot at 24h and 30m, if budget permits',
            'nhl_props': '16 sampled 2025–26 games, 24h/30m shots-on-goal pairs',
            'nba': '2025 every-ninth-day Jan–Jun spread/total pilot',
            'nhl_missing_season': '2023–24 daily 05:00/15:00 UTC all-US moneylines; 2024–26 already archived',
            'budget': args.budget, 'quota_reserve': 1000}
    if args.plan:
        print(json.dumps(plan, indent=2)); return
    key = os.environ.get('ODDS_API_KEY') or (args.key_file.read_text().strip() if args.key_file else '')
    if not key:
        ap.error('Provide ODDS_API_KEY or --key-file')
    cap = Capture(args.out, key, args.budget)
    (args.out / 'plan.json').write_text(json.dumps(plan, indent=2))
    try:
        for sport in ['americanfootball_nfl', 'americanfootball_ncaaf', 'icehockey_nhl', 'basketball_wnba']:
            cap.odds(sport, None, 'h2h,spreads,totals', 'live_reference')
        for sport in ['americanfootball_nfl_super_bowl_winner', 'icehockey_nhl_championship_winner']:
            cap.odds(sport, None, 'outrights', 'live_futures')
        nfl_events = {}
        for day in dates('2025-09-07', '2026-01-04', 7):
            payload = cap.odds('americanfootball_nfl', day+'T12:00:00Z', 'spreads,totals', 'nfl_2025_weekly_reference')
            if not payload: continue
            events = sorted(payload.get('data', []), key=lambda e:(e['commence_time'],e['id']))
            eligible = [e for e in events if day <= e['commence_time'][:10] <= day]
            for event in eligible[:3]: nfl_events[event['id']] = event
        for event in list(nfl_events.values())[:44]:
            kick = datetime.fromisoformat(event['commence_time'].replace('Z','+00:00'))
            for hours, label in [(24, 'nfl_props_24h'), (.5, 'nfl_props_30m')]:
                cap.event('americanfootball_nfl',event['id'],iso(kick-timedelta(hours=hours)),
                          'player_pass_yds,player_rush_yds,player_reception_yds,player_receptions',label)
        for day in dates('2025-11-01','2025-12-31'):
            cap.odds('basketball_ncaab',day+'T12:00:00Z','spreads','cbb_noon_2025')
        wnba_events = {}
        for day in dates('2026-05-15','2026-09-30',3):
            payload=cap.odds('basketball_wnba',day+'T15:00:00Z','spreads,totals','wnba_decision_2026')
            if payload:
                for event in payload.get('data',[]):
                    if day == event['commence_time'][:10]: wnba_events[event['id']]=event
        for event in list(wnba_events.values())[:24]:
            kick=datetime.fromisoformat(event['commence_time'].replace('Z','+00:00'))
            cap.event('basketball_wnba',event['id'],iso(kick-timedelta(minutes=30)),
                      'spreads,totals','wnba_30m_2026')
        nhl_events = {}
        for day in dates('2025-10-15','2026-03-31',21):
            payload=cap.odds('icehockey_nhl',day+'T15:00:00Z','h2h','nhl_sog_event_discovery')
            if payload:
                for event in payload.get('data',[])[:2]: nhl_events[event['id']]=event
        for event in list(nhl_events.values())[:16]:
            kick=datetime.fromisoformat(event['commence_time'].replace('Z','+00:00'))
            for hours,label in [(24,'nhl_sog_24h'),(.5,'nhl_sog_30m')]:
                cap.event('icehockey_nhl',event['id'],iso(kick-timedelta(hours=hours)),'player_shots_on_goal',label)
        for day in dates('2025-01-02','2025-06-15',9):
            cap.odds('basketball_nba',day+'T15:00:00Z','spreads,totals','nba_priced_pilot')
        for day in dates('2023-10-10','2024-06-25'):
            for hour,label in [(5,'nhl_2023_24_open'),(15,'nhl_2023_24_morning')]:
                cap.odds('icehockey_nhl',f'{day}T{hour:02}:00:00Z','h2h',label)
        for event in list(wnba_events.values())[:3]:
            kick=datetime.fromisoformat(event['commence_time'].replace('Z','+00:00'))
            for hours,label in [(24,'wnba_props_24h'),(.5,'wnba_props_30m')]:
                cap.event('basketball_wnba',event['id'],iso(kick-timedelta(hours=hours)),
                          'player_points,player_rebounds,player_assists',label)
    finally:
        cap.export()


if __name__ == '__main__':
    main()
