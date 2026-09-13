"""Immutable research NHL totals snapshots at a fixed 15:00 UTC vendor as-of."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone,timedelta
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request

UTC=timezone.utc
ENDPOINT='https://api.the-odds-api.com/v4/historical/sports/icehockey_nhl/odds'


def iso(value):return value.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
def stamp(value):
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:raise ValueError('Timestamp must include timezone')
    return parsed.astimezone(UTC)


def phase(now):
    now=now.astimezone(UTC);minute=now.hour*60+now.minute
    return 'early' if minute<905 else 'capture' if minute<920 else 'missed'


def normalize(payload,decision,retrieved):
    vendor=stamp(payload['timestamp'])
    if not decision-timedelta(minutes=10)<=vendor<=decision:raise ValueError('Vendor snapshot is outside the fixed as-of tolerance')
    rows=[];coverage=[]
    for game in payload['data']:
        start=stamp(game['commence_time']);books=[];accepted=0
        for book in game.get('bookmakers',[]):
            key={'williamhill_us':'caesars'}.get(book['key'],book['key']);books.append(key)
            for market in book.get('markets',[]):
                if market.get('key')!='totals':continue
                updated=stamp(market.get('last_update',book.get('last_update')))
                if updated>vendor:raise ValueError('Market update is newer than vendor as-of')
                groups={}
                for outcome in market.get('outcomes',[]):
                    line=outcome.get('point');side=outcome.get('name')
                    if isinstance(line,(int,float)) and side in ['Over','Under']:
                        pair=groups.setdefault(float(line),{})
                        if side in pair:raise ValueError('Duplicate side for a book/line')
                        pair[side]=outcome.get('price')
                for line,pair in groups.items():
                    valid=set(pair)=={'Over','Under'} and all(isinstance(p,(int,float)) and abs(p)>=100 for p in pair.values())
                    if not valid:continue
                    rows.append(dict(odds_game_id=game['id'],home_team=game['home_team'],away_team=game['away_team'],commence_time=iso(start),bookmaker=key,line=line,over_price=pair['Over'],under_price=pair['Under'],market_last_update=iso(updated),vendor_asof=iso(vendor),decision_asof=iso(decision),retrieved_at=iso(retrieved),prestart=start>decision));accepted+=1
        coverage.append(dict(odds_game_id=game['id'],commence_time=iso(start),home_team=game['home_team'],away_team=game['away_team'],bookmakers=sorted(set(books)),valid_book_lines=accepted,prestart=start>decision))
    return rows,coverage


def fetch(decision):
    key=os.environ.get('ODDS_API_KEY')
    if not key:raise RuntimeError('Missing ODDS_API_KEY')
    params=dict(apiKey=key,regions='us',markets='totals',oddsFormat='american',date=iso(decision))
    request=urllib.request.Request(ENDPOINT+'?'+urllib.parse.urlencode(params),headers={'User-Agent':'NHL-research-totals-collector/1'})
    try:
        with urllib.request.urlopen(request,timeout=45) as response:
            payload=json.load(response);quota={k:response.headers.get(k) for k in ['x-requests-remaining','x-requests-used','x-requests-last']}
    except Exception as error:
        code=getattr(error,'code',None);raise RuntimeError('Odds request failed: '+type(error).__name__+(f' HTTP {code}' if code else '')) from None
    return payload,quota


def exclusive(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')


def collect(root,mode,now=None,day=None):
    now=now or datetime.now(UTC);day=day or now.date().isoformat();decision=stamp(day+'T15:00:00Z')
    if mode=='probe' and decision>now and day==now.date().isoformat():decision-=timedelta(days=1);day=decision.date().isoformat()
    if mode=='capture' and day!=now.date().isoformat():raise ValueError('Scheduled capture must use today')
    if mode=='capture' and phase(now)=='early':return dict(status='before_window',decision_asof=iso(decision))
    directory=root/day if mode=='capture' else root/(mode+'s')/(day+'_'+now.strftime('%Y%m%dT%H%M%SZ'))
    status_file=directory/'status.json'
    if status_file.exists():return json.loads(status_file.read_text())
    status=dict(mode=mode,decision_asof=iso(decision),attempt_at=iso(now),prospective_capture=mode=='capture' and phase(now)=='capture',markets=['totals'],region='us',funded=False)
    if mode=='capture' and phase(now)=='missed':
        status.update(status='missed_window',reason='No automatic historical recovery outside 15:05–15:20 UTC');exclusive(status_file,status);return status
    if decision>now:raise ValueError('Cannot request a future as-of')
    try:
        payload,quota=fetch(decision);retrieved=datetime.now(UTC);rows,coverage=normalize(payload,decision,retrieved)
        # A request crossing the deadline cannot be silently labeled timely.
        if mode=='capture' and retrieved>=decision+timedelta(minutes=20):status['prospective_capture']=False
        exclusive(directory/'response.json',payload);exclusive(directory/'quotes.json',rows);exclusive(directory/'coverage.json',coverage)
        status.update(status='captured' if rows else 'no_totals_returned',retrieved_at=iso(retrieved),vendor_asof=payload['timestamp'],returned_events=len(coverage),valid_book_lines=len(rows),events_without_totals=sum(x['valid_book_lines']==0 for x in coverage),missing_execution_books=sorted({'betmgm','caesars'}-{x['bookmaker'] for x in rows}),quota=quota)
    except Exception as error:
        # Never emit request URLs, exception bodies or credential values.
        status.update(status='failed',prospective_capture=False,error_type=type(error).__name__)
    exclusive(status_file,status);return status


def health(root):
    files=sorted(root.glob('*/status.json'));rows=[json.loads(p.read_text()) for p in files]
    return dict(capture_days=len(rows),latest=rows[-1] if rows else None,probe_runs=len(list((root/'probes').glob('*/status.json'))),recovery_runs=len(list((root/'recovers').glob('*/status.json'))))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['capture','probe','recover','health']);parser.add_argument('--root',type=Path,default=Path('data/nhl_totals_15utc'));parser.add_argument('--date');args=parser.parse_args()
    result=health(args.root) if args.mode=='health' else collect(args.root,args.mode,day=args.date);print(json.dumps(result,indent=2))
    return 1 if result.get('status')=='failed' else 0

if __name__=='__main__':raise SystemExit(main())
