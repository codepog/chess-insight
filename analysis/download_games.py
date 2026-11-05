"""Download one user's completed public games, with a fixed reproducible time window."""
import json
import argparse
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

USER = 'chickenboi2'
END = datetime.fromisoformat('2026-11-05T05:28:19+00:00')
START = END.astimezone(ZoneInfo('America/Los_Angeles')).replace(year=2025)
HEADERS = {'User-Agent': 'PersonalChessStudy/1.0', 'Accept': 'application/x-ndjson'}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    OUT=args.output_dir
    OUT.mkdir(parents=True,exist_ok=True)
    profile_url = f'https://lichess.org/api/user/{USER}'
    with urllib.request.urlopen(urllib.request.Request(profile_url, headers=HEADERS), timeout=60) as r:
        profile = json.load(r)
    (OUT / 'profile.json').write_text(json.dumps(profile, indent=2))
    params = dict(since=int(START.timestamp()*1000), until=int(END.timestamp()*1000),
                  moves='true', pgnInJson='true', clocks='true', evals='true',
                  opening='true', accuracy='true', ongoing='false', finished='true', sort='dateAsc')
    url = f'https://lichess.org/api/games/user/{USER}?' + urllib.parse.urlencode(params)
    records, ids = [], set()
    partial = OUT / 'games.ndjson.partial'
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=120) as r, partial.open('w') as f:
        for line in r:
            if not line.strip():
                continue
            obj = json.loads(line)
            if 'id' not in obj:
                raise RuntimeError(f'Unexpected export record: {obj}')
            if obj['id'] in ids:
                raise RuntimeError('Duplicate game ID in export')
            ids.add(obj['id'])
            f.write(json.dumps(obj, separators=(',', ':'))+'\n')
            records.append(obj)
            if len(records)%100 == 0:
                print(f'Downloaded {len(records)} games', flush=True)
    partial.replace(OUT / 'games.ndjson')
    with (OUT / 'games.pgn').open('w') as f:
        for obj in records:
            if obj.get('pgn'):
                f.write(obj['pgn'].strip()+'\n\n')
    counts = {}
    for obj in records:
        k=obj.get('speed','unknown'); counts[k]=counts.get(k,0)+1
    manifest = dict(username=USER, since=START.isoformat(), until=END.astimezone(ZoneInfo('America/Los_Angeles')).isoformat(),
                    since_ms=params['since'], until_ms=params['until'], source=url,
                    completed_games=len(records), pgn_games=sum(bool(o.get('pgn')) for o in records),
                    speed_counts=counts, analyzed_games=sum(bool(o.get('analysis')) for o in records),
                    games_with_clocks=sum(bool(o.get('clocks')) for o in records),
                    variants=sorted({o.get('variant','unknown') for o in records}))
    (OUT/'download_manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2), flush=True)
    if records:
        first=records[0]
        print('First record keys:',sorted(first))
        print('First record lengths:',{k:len(first[k]) for k in ['moves','clocks','analysis','pgn'] if k in first})

if __name__=='__main__':
    main()
