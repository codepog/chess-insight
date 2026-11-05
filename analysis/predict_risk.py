"""Reproduce a saved personal model prediction for a completed-game position."""
from pathlib import Path
import argparse,json,sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'deps'))
from analyze_history import get_rows
import numpy as np

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--data-dir',type=Path,required=True)
    p.add_argument('--game-id',required=True)
    p.add_argument('--ply',type=int,required=True)
    args=p.parse_args()
    import csv
    model=json.loads((args.data_dir/'risk_model.json').read_text())
    game=next((json.loads(l) for l in (args.data_dir/'games.ndjson').read_text().splitlines() if json.loads(l)['id']==args.game_id),None)
    if game is None:raise SystemExit('Game ID not present in this archive')
    # Reconstruct board features from the row's pre-move FEN and game metadata.
    with (args.data_dir/'move_labels.csv').open() as f:
        row=next((r for r in csv.DictReader(f) if r['game_id']==args.game_id and int(r['ply'])==args.ply),None)
    if row is None:raise SystemExit('Player move not present in the labeled archive')
    from analyze_history import features,sigmoid
    import chess
    board=chess.Board(row['fen']);own=board.turn
    me=game['players']['white' if own else 'black'];opp=game['players']['black' if own else 'white']
    x=np.array(features(board,own,float(row['clock_before']),game['clock']['initial'],game['clock']['increment'],me.get('rating',0)-opp.get('rating',0),float(row['pre_cp'])))
    z=(x-np.array(model['means']))/np.array(model['scales'])
    risk=float(sigmoid(model['intercept']+z@np.array(model['coefficients'])))
    print(json.dumps({'game_id':args.game_id,'ply':args.ply,'scope':model['scope'],'predicted_engine_error_risk':risk,'note':'An uncalibrated fitted prediction, not a causal diagnosis or a prediction of game outcome.'},indent=2))

if __name__=='__main__':main()
