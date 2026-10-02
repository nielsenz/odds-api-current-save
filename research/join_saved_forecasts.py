"""Join the bounded odds archive to explicit saved forecast sources, offline.

No training, API calls, bet selection, or ledger writes. Native identities,
forecast provenance, missing matches and quote-clock exclusions are retained.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass, asdict
from datetime import datetime
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import unicodedata
from zoneinfo import ZoneInfo

NFL_NAMES = dict(zip(
    'ARI ATL BAL BUF CAR CHI CIN CLE DAL DET GB HOU IND JAX KC LA LAC LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS DEN'.split(),
    ['Arizona Cardinals','Atlanta Falcons','Baltimore Ravens','Buffalo Bills','Carolina Panthers','Chicago Bears','Cincinnati Bengals','Cleveland Browns','Dallas Cowboys','Detroit Lions','Green Bay Packers','Houston Texans','Indianapolis Colts','Jacksonville Jaguars','Kansas City Chiefs','Los Angeles Rams','Los Angeles Chargers','Las Vegas Raiders','Miami Dolphins','Minnesota Vikings','New England Patriots','New Orleans Saints','New York Giants','New York Jets','Philadelphia Eagles','Pittsburgh Steelers','Seattle Seahawks','San Francisco 49ers','Tampa Bay Buccaneers','Tennessee Titans','Washington Commanders','Denver Broncos']))
NHL_NAMES = dict(zip(
    'ANA ARI BOS BUF CAR CBJ CGY CHI COL DAL DET EDM FLA LAK MIN MTL NJD NSH NYI NYR OTT PHI PIT SEA SJS STL TBL TOR UTA VAN VGK WPG WSH'.split(),
    ['Anaheim Ducks','Arizona Coyotes','Boston Bruins','Buffalo Sabres','Carolina Hurricanes','Columbus Blue Jackets','Calgary Flames','Chicago Blackhawks','Colorado Avalanche','Dallas Stars','Detroit Red Wings','Edmonton Oilers','Florida Panthers','Los Angeles Kings','Minnesota Wild','Montreal Canadiens','New Jersey Devils','Nashville Predators','New York Islanders','New York Rangers','Ottawa Senators','Philadelphia Flyers','Pittsburgh Penguins','Seattle Kraken','San Jose Sharks','St Louis Blues','Tampa Bay Lightning','Toronto Maple Leafs','Utah Hockey Club','Vancouver Canucks','Vegas Golden Knights','Winnipeg Jets','Washington Capitals']))


def normalized(value):
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]', '', text)


def player_name(value):
    text = re.sub(r'\b(jr|sr|ii|iii|iv)\.?$', '', str(value or '').strip(), flags=re.I)
    return normalized(text)


def team_name(sport, value):
    mapping = NFL_NAMES if sport.startswith('americanfootball_nfl') else NHL_NAMES if sport == 'icehockey_nhl' else {}
    return normalized(mapping.get(str(value), value))


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def native_id(value):
    text = str(value)
    return text[:-2] if text.endswith('.0') else text


def rows(path):
    if path.suffix == '.parquet':
        import pandas as pd
        yield from pd.read_parquet(path).to_dict('records')
    else:
        opener = gzip.open if path.suffix == '.gz' else open
        with opener(path, 'rt', newline='') as f:
            yield from csv.DictReader(f)


def stamp(value):
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if t.tzinfo is None:
        raise ValueError('Timestamp lacks timezone')
    return t


@dataclass(frozen=True)
class Forecast:
    model: str
    sport: str
    game_id: str
    date: str
    home: str
    away: str
    market: str
    prediction: float
    actual: float | None
    subject: str = ''
    player_id: str = ''
    source: str = ''
    basis: str = 'historical_replay_no_capture_clock'
    captured_at: str = ''
    cutoff: str = ''
    commence_time: str = ''

    @property
    def identity(self):
        return (self.model, self.game_id, self.market, self.player_id)


class Join:
    def __init__(self, forecasts, aliases=None):
        self.forecasts = forecasts
        self.aliases = aliases or {}
        self.index = defaultdict(list)
        self.vendor = defaultdict(list)
        seen = {}
        for f in forecasts:
            if f.identity in seen:
                raise ValueError('Duplicate forecast identity: ' + str(f.identity))
            seen[f.identity] = f
            if f.basis.startswith('excluded_'):continue
            home, away = team_name(f.sport, f.home), team_name(f.sport, f.away)
            subject_names = {team_name(f.sport, f.subject)} if f.market == 'outrights' else self.aliases.get(f.player_id, {player_name(f.subject)}) if f.player_id else {''}
            for name in subject_names:
                self.index[(f.sport, f.date, home, away, f.market, name)].append(f)
            self.vendor[(f.sport, f.game_id, f.market)].append(f)

    def match(self, q):
        subject = team_name(q['sport'],q['outcome']) if q['market']=='outrights' else player_name(q.get('description')) if q['market'].startswith('player_') else ''
        day = stamp(q['commence_time']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
        key = (q['sport'], day, team_name(q['sport'],q['home_team']), team_name(q['sport'],q['away_team']),q['market'],subject)
        candidates = self.vendor.get((q['sport'],q['event_id'],q['market'])) or self.index.get(key, [])
        found = {}
        rejected = []
        for f in candidates:
            if team_name(f.sport,f.home) != key[2] or team_name(f.sport,f.away) != key[3]:
                rejected.append('home_away_mismatch'); continue
            if f.player_id and subject not in self.aliases.get(f.player_id,{player_name(f.subject)}):
                continue
            if f.commence_time and abs((stamp(f.commence_time)-stamp(q['commence_time'])).total_seconds()) > 3600:
                rejected.append('kickoff_mismatch'); continue
            found[f.identity] = f
        by_model = Counter(f.model for f in found.values())
        if any(n > 1 for n in by_model.values()):
            return [], 'ambiguous_player_or_game'
        return list(found.values()), 'matched' if found else rejected[0] if rejected else 'no_saved_forecast'


def compare(f, q):
    line = number(q.get('point'))
    if f.market not in ('h2h', 'outrights') and line is None:
        raise ValueError('Matched quote lacks a numeric line')
    if f.market in ('spreads', 'h2h') and team_name(q['sport'], q['outcome']) not in (team_name(q['sport'], q['home_team']), team_name(q['sport'], q['away_team'])):
        raise ValueError('Matched quote has an unknown team outcome')
    if f.market not in ('spreads', 'h2h', 'outrights') and q['outcome'] not in ('Over', 'Under'):
        raise ValueError('Matched quote has an unknown total/prop outcome')
    is_home = team_name(q['sport'],q['outcome']) == team_name(q['sport'],q['home_team'])
    if f.market == 'spreads':
        delta = (f.prediction if is_home else -f.prediction) + line
        observed = None if f.actual is None else (f.actual if is_home else -f.actual) + line
    elif f.market in ('h2h', 'outrights'):
        delta = None
        observed = None if f.actual is None else f.actual if is_home else 1-f.actual
    else:
        direction = 1 if q['outcome'] == 'Over' else -1
        delta = direction * (f.prediction-line)
        observed = None if f.actual is None else direction * (f.actual-line)
    result = '' if observed is None else ('win' if observed > 0 else 'push' if observed == 0 else 'loss')
    if f.market == 'h2h' and observed is not None:
        result = 'win' if observed == 1 else 'loss'
    probability = f.prediction if f.market=='outrights' else (f.prediction if is_home else 1-f.prediction) if f.market=='h2h' else None
    price=number(q['price'])
    implied=None if not price else (100/(price+100) if price>0 else -price/(-price+100))
    probability_difference=None if probability is None or implied is None else probability-implied
    quote_time = q['requested_snapshot'] or q['retrieved_at']
    prestart = stamp(quote_time) < stamp(q['commence_time'])
    capture_ok = bool(f.captured_at and stamp(f.captured_at) <= stamp(quote_time))
    return dict(model=f.model, native_game_id=f.game_id, native_player_id=f.player_id,
                forecast=f.prediction, model_probability=probability, price_implied_probability=implied, probability_difference=probability_difference, actual_stat=f.actual, model_difference=delta,
                statistic_result=result, forecast_basis=f.basis, forecast_captured_at=f.captured_at,
                forecast_training_cutoff=f.cutoff, forecast_source=f.source,
                forecast_precedes_quote=capture_ok,
                quote_prestart=prestart,
                strict_quote_timing=prestart and q['requested_cutoff_safe']=='True' and q['vendor_snapshot_consistent']=='True',
                settlement_status='statistic_only_action_unknown' if f.market.startswith('player_') else 'unresolved_future_event' if f.market=='outrights' else 'historical_statistic_comparison',
                wager_profit=None)


def load_forecasts(home):
    forecasts, sources, unavailable, aliases = [], {}, [], {}
    nfl = home/'nfl/team_model/python-team-model'

    def read(relative):
        p=home/relative
        if not p.exists():
            unavailable.append(str(relative));return []
        sources[str(relative)] = hashlib.sha256(p.read_bytes()).hexdigest()
        return list(rows(p))

    def add(model,sport,r,market,value,actual=None,**extra):
        value=number(value)
        if value is None: return
        forecasts.append(Forecast(model,sport,native_id(r['game_id']),str(r['date'])[:10],
                                  r['home_team'],r['away_team'],market,value,number(actual),**extra))

    schedule=read(Path('nfl/team_model/python-team-model/outputs/2026/week-4-refresh-20261002T050339Z/inputs/schedules.csv'))
    games={r['game_id']:r for r in schedule}
    nfl_players=read(Path('nfl/team_model/python-team-model/.cache/player-movement/players.csv'))
    for p in nfl_players:
        names={p.get('display_name'),p.get('football_name')}
        for first in ['first_name','common_first_name']:
            if p.get(first) and p.get('last_name'):names.add(str(p[first])+' '+str(p['last_name']))
        aliases[p['gsis_id']]={player_name(n) for n in names if n and str(n)!='nan'}

    def nfl_game(r):
        g=games[r['game_id']]
        return dict(r,date=g['gameday'],home_team=g['home_team'],away_team=g['away_team'])

    for p in sorted((nfl/'outputs/2025').glob('week-*/predictions_v4_optimized_week_*_2025.csv')):
        rel=p.relative_to(home)
        for r in read(rel):
            if r.get('model_version')!='phase4_corrected_v1':raise ValueError('Uncorrected Phase 4 source')
            if int(r['training_cutoff_week_exclusive'])>int(r['week']):raise ValueError('Future training cutoff')
            g=nfl_game(r);s=games[r['game_id']];actual=None if not s['home_score'] else float(s['home_score'])-float(s['away_score'])
            add('nfl_phase4_corrected','americanfootball_nfl',g,'spreads',r['spread'],actual,source=str(rel),cutoff=f"{r['season']}:week<{r['training_cutoff_week_exclusive']}")
    rel=Path('nfl/team_model/python-team-model/outputs/2025/summary/2025_totals_vs_actuals.csv')
    for r in read(rel):add('nfl_revamp_totals_saved','americanfootball_nfl',nfl_game(r),'totals',r['model_total'],r['actual_total'],source=str(rel),basis='saved_historical_totals_fit_clock_unverified')
    refresh=Path('nfl/team_model/python-team-model/outputs/2026/week-4-refresh-20261002T050339Z')
    manifest_relative=refresh/'run_manifest.json'
    manifest_path=home/manifest_relative
    sources[str(manifest_relative)]=hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    refresh_clock=json.loads(manifest_path.read_text())['generated_at_utc']
    for file,model,margin,total in [('phase4/2026/week-4/predictions_v4_optimized_week_4_2026.csv','nfl_phase4_corrected','spread',None),('totals.csv','nfl_revamp_totals_saved',None,'model_total'),('weekly-primary-qb-context/score_forecasts.csv','nfl_primary_epa','margin','total'),('independent.csv','nfl_independent','model_spread','model_total')]:
        rel=refresh/file
        for r in read(rel):
            g=nfl_game(r)
            for market,col in [('spreads',margin),('totals',total)]:
                if col:add(model,'americanfootball_nfl',g,market,r[col],source=str(rel),basis='dated_2026_research_manifest_clock_upper_bound',captured_at=r.get('generated_at_utc') or refresh_clock,cutoff='2026:week<4')

    rel=Path('nfl/team_model/python-team-model/outputs/experiments/advanced-volume-props-20260926-v3/predictions.parquet')
    for r in read(rel):
        if r['season']!=2025 or r['model']!='calibration' or r['target'] not in ('passing_yards','rushing_yards'):continue
        if r['training_max_season']>=r['season']:raise ValueError('Prop target-season fit')
        market='player_pass_yds' if r['target']=='passing_yards' else 'player_rush_yds'
        add('nfl_prior_volume_calibration','americanfootball_nfl',nfl_game(r),market,r['prediction'],r['actual'],subject=r['player_name'],player_id=r['player_id'],source=str(rel),cutoff=str(r['training_max_season']))
    panel_rel=Path('nfl/team_model/python-team-model/outputs/experiments/yard-new-seasons-20260927-v3/2025_panel.parquet')
    receptions={(r['game_id'],r['player_id']):r['actual_receptions'] for r in read(panel_rel)}
    rel=Path('nfl/team_model/python-team-model/outputs/experiments/yard-new-seasons-20260927-v3/2025_predictions.parquet')
    for r in read(rel):
        name=next(iter(sorted(aliases.get(r['player_id'],{''}))))
        g=nfl_game(r)
        add('nfl_injury_aware_yards_mean','americanfootball_nfl',g,'player_reception_yds',r['expected_yards'],r['actual_yards'],subject=name,player_id=r['player_id'],source=str(rel),cutoff='through2024; target-week prior history only')
        if number(r['probability']) is not None:
            add('nfl_injury_aware_reception_mean','americanfootball_nfl',g,'player_receptions',float(r['probability'])*float(r['conditional_receptions']),receptions.get((r['game_id'],r['player_id'])),source=str(rel),subject=name,player_id=r['player_id'],cutoff='through2024; target-week prior history only')

    futures_relative=refresh/'futures-asof-thursday-final/manifest.json'
    futures_manifest=home/futures_relative
    sources[str(futures_relative)]=hashlib.sha256(futures_manifest.read_bytes()).hexdigest()
    futures_clock=json.loads(futures_manifest.read_text())['generated_at']
    rel=refresh/'futures-asof-thursday-final/futures.csv'
    for r in read(rel):
        g=dict(game_id='2026_super_bowl_'+r['team'],date='2027-02-14',home_team='',away_team='')
        add('nfl_experimental_super_bowl','americanfootball_nfl_super_bowl_winner',g,'outrights',r['super_bowl'],subject=r['team'],source=str(rel),basis='experimental_unvalidated_simulation',captured_at=futures_clock,cutoff='49 fixed games; post PIT-CLE final')

    rel=Path('college-basketball/validation/results/legit_spread_roi/legit_spread_predictions.csv')
    cbb_unsafe=0
    for r in read(rel):
        if str(r['date'])[:4]!='2025':continue
        unsafe=str(r['training_cutoff'])[:10]>=str(r['date'])[:10]
        if unsafe:cbb_unsafe+=1
        add('cbb_canonical_ridge','basketball_ncaab',r,'spreads',r['predicted_home_margin'],r['actual_home_margin'],source=str(rel),cutoff=r['training_cutoff'],commence_time=r['commence_time'],basis='excluded_training_cutoff_unverified' if unsafe else 'historical_replay_no_capture_clock')
    if cbb_unsafe:unavailable.append(f'CBB: retained unmatched and excluded from joining {cbb_unsafe} 2025 forecasts with cutoff on/after target date; fit exclusivity unverified.')
    for file,model,margin,total,actual_margin,actual_total,date in [('analysis/joint_score_model/stage1_predictions_2026.csv','wnba_joint_score','pred_mean_margin','pred_mean_total','actual_margin','actual_total','local_game_date'),('analysis/cover/stage1/2026_feature_build/spread_advanced_predictions_2026.csv','wnba_saved_spread_baseline','predicted_spread','predicted_total','actual_spread','actual_total','game_date')]:
        rel=Path('wnba')/file
        for r in read(rel):
            r=dict(r,date=r[date])
            for market,col,ac in [('spreads',margin,actual_margin),('totals',total,actual_total)]:add(model,'basketball_wnba',r,market,r[col],r[ac],source=str(rel),basis='saved_walkforward_research_no_capture_clock')

    rel=Path('nhl/nhl-revamp/exports/historical/pregame_predictions_correctness.csv')
    for r in read(rel):add('nhl_saved_site_pregame','icehockey_nhl',r,'h2h',float(r['home_win_prob'])/100,r['actual_home_win'],source=str(rel),basis='site_history_not_frozen_funded_manifest')
    rel=Path('nhl/sog-model/outputs/opportunities/production_rolling_predictions.csv.gz')
    actuals={(native_id(r['game_id']),native_id(r['player_id'])):number(r['sog']) for r in read(rel)}
    rel=Path('nhl/sog-model/outputs/bottom_up_audit/per_player_predictions.csv.gz')
    for r in read(rel):
        g=dict(r,date=r['game_date'],home_team=r['team'] if str(r['is_home']) in ('1','1.0') else r['opponent'],away_team=r['opponent'] if str(r['is_home']) in ('1','1.0') else r['team'])
        add('nhl_prior_roster_sog_replay','icehockey_nhl',g,'player_shots_on_goal',r['predicted_mu'],actuals.get((native_id(r['game_id']),native_id(r['player_id']))),subject=r['player_name'],player_id=native_id(r['player_id']),source=str(rel),basis='monthly_refit_prior_game_roster_replay',cutoff=str(r['game_date'])[:7]+'-01',commence_time=r['commence_time'])
    rel=Path('nba/data/models/walkforward_predictions.csv')
    nba=read(rel)
    unavailable.append('NBA saved walk-forward predictions end 2024-01-21; collected NBA quotes are 2025. No overlapping forecast source.')
    unavailable.append('NHL saved pregame forecasts begin October 2024; the new 2023-24 moneyline archive has no overlapping registered forecast. NHL championship futures source not registered.')
    unavailable.append('No registered 2026 WNBA player-prop or current CFB forecast source found for this archive.')
    return forecasts, sources, unavailable, aliases


def quote_identity(q):
    return tuple(q.get(k,'') for k in ('capture_id','sport','event_id','book','market','outcome','description','point'))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--sports-home',type=Path,default=Path(os.environ.get('SPORTS_HOME',str(Path(__file__).resolve().parents[2]))))
    ap.add_argument('--odds',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();home=args.sports_home.resolve()
    forecasts,sources,unavailable,aliases=load_forecasts(home);join=Join(forecasts,aliases)
    args.out.mkdir(parents=True,exist_ok=False)
    quote_identities=Counter();quote_prices=defaultdict(set)
    for q in rows(args.odds):
        key=quote_identity(q);quote_identities[key]+=1;quote_prices[key].add(q['price'])
    fields=['archive_row_number','quote_identity_count','quote_price_conflict','comparison_quote_eligible','model','native_game_id','native_player_id','forecast','model_probability','price_implied_probability','probability_difference','actual_stat','model_difference','statistic_result','forecast_basis','forecast_captured_at','forecast_training_cutoff','forecast_source','forecast_precedes_quote','quote_prestart','strict_quote_timing','settlement_status','wager_profit','join_status']
    matched=set();quote_counts=Counter();model_counts=Counter();model_safe=Counter();statuses=Counter();total=0;joined=0
    model_games=defaultdict(set);model_safe_forecasts=defaultdict(set);model_clock_safe=Counter();model_actuals=defaultdict(set)
    with gzip.open(args.out/'joined_quotes.csv.gz','wt',newline='') as f:
        writer=None
        for q in rows(args.odds):
            total+=1
            key=quote_identity(q)
            q=dict(q,archive_row_number=total,quote_identity_count=quote_identities[key],quote_price_conflict=len(quote_prices[key])>1)
            quote_counts[q['sport']]+=1;candidates,status=join.match(q);statuses[(q['sport'],status)]+=1
            if writer is None:writer=csv.DictWriter(f,fieldnames=list(q)+[k for k in fields if k not in q]);writer.writeheader()
            if not candidates:writer.writerow(dict(q,join_status=status));continue
            joined+=1
            for forecast in candidates:
                result=compare(forecast,q);result['comparison_quote_eligible']=result['strict_quote_timing'] and quote_identities[key]==1;writer.writerow(dict(q,**result,join_status=status));matched.add(forecast.identity)
                model_counts[forecast.model]+=1;model_safe[forecast.model]+=result['strict_quote_timing']
                model_games[forecast.model].add(forecast.game_id)
                if forecast.actual is not None:model_actuals[forecast.model].add(forecast.identity)
                if result['strict_quote_timing']:model_safe_forecasts[forecast.model].add(forecast.identity)
                model_clock_safe[forecast.model]+=result['strict_quote_timing'] and result['forecast_precedes_quote']
    with gzip.open(args.out/'unmatched_forecasts.csv.gz','wt',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(asdict(forecasts[0])));writer.writeheader()
        for forecast in forecasts:
            if forecast.identity not in matched:writer.writerow(asdict(forecast))
    universe=Counter(f.model for f in forecasts);excluded=Counter(f.model for f in forecasts if f.basis.startswith('excluded_'));matched_by=Counter(i[0] for i in matched)
    summary=dict(odds_rows=total,matched_odds_rows=joined,unmatched_odds_rows=total-joined,
                 duplicate_quote_identities=sum(n>1 for n in quote_identities.values()),conflicting_price_quote_identities=sum(len(v)>1 for v in quote_prices.values()),
                 forecast_rows=len(forecasts),matched_forecasts=len(matched),
                 per_model={m:dict(forecasts=universe[m],excluded_forecasts=excluded[m],matched_forecasts=matched_by[m],joined_quote_rows=model_counts[m],strict_quote_rows=model_safe[m],matched_games_or_future_teams=len(model_games[m]),strict_matched_forecasts=len(model_safe_forecasts[m]),matched_forecasts_with_actuals=len(model_actuals[m]),clock_verified_quote_rows=model_clock_safe[m]) for m in universe},
                 quote_statuses=[dict(sport=s,status=t,rows=n) for (s,t),n in statuses.items()],
                 unavailable=unavailable,credits_used=0,ledger_writes=0,
                 odds_sha256=hashlib.sha256(args.odds.read_bytes()).hexdigest(),source_sha256=sources)
    (args.out/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps({k:v for k,v in summary.items() if k!='source_sha256'},indent=2))


if __name__=='__main__':
    main()
