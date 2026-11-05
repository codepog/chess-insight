"""Engine-label a game archive and fit an interpretable personal error-risk model.

No external coaching service is called. Labels are explicitly defined engine proxies.
"""
from pathlib import Path
import argparse, collections, concurrent.futures, csv, hashlib, io, json, math, sys, time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'deps'))
import numpy as np
import chess
import chess.pgn
import chess.engine

VALUES={chess.PAWN:1,chess.KNIGHT:3,chess.BISHOP:3,chess.ROOK:5,chess.QUEEN:9,chess.KING:0}
FEATURES=['move_number','own_material','opponent_material','material_balance','pieces_on_board',
          'own_pawns','opponent_pawns','log_legal_moves','in_check','endgame','opening',
          'queens_on_board','rooks_on_board','king_distance','log_clock_before','clock_fraction',
          'under_10_seconds','increment_seconds','rating_difference','as_white','pre_eval_proxy']

def win_proxy(cp):
    return 100/(1+math.exp(-.00368208*max(-10000,min(10000,cp))))

def material(board,color):
    return sum(len(board.pieces(pt,color))*v for pt,v in VALUES.items())

def phase(board):
    np_material=sum(len(board.pieces(pt,c))*VALUES[pt] for c in [True,False] for pt in [2,3,4,5])
    queens=len(board.pieces(chess.QUEEN,True))+len(board.pieces(chess.QUEEN,False))
    if np_material<=20 or (queens==0 and np_material<=26):
        return 'endgame'
    return 'opening' if board.fullmove_number<=10 else 'middlegame'

def ending_type(board):
    if any(board.pieces(chess.QUEEN,c) for c in [True,False]): return 'queen'
    if any(board.pieces(chess.ROOK,c) for c in [True,False]):
        return 'rook_and_minor' if any(board.pieces(p,c) for c in [True,False] for p in [2,3]) else 'rook'
    if any(board.pieces(p,c) for c in [True,False] for p in [2,3]): return 'minor_piece'
    return 'pawn'

def features(board,own,clock_before,initial,increment,rating_diff,cp):
    om,em=material(board,own),material(board,not own)
    ph=phase(board)
    return [board.fullmove_number,om,em,om-em,len(board.piece_map()),
            len(board.pieces(chess.PAWN,own)),len(board.pieces(chess.PAWN,not own)),
            math.log1p(board.legal_moves.count()),int(board.is_check()),int(ph=='endgame'),int(ph=='opening'),
            sum(len(board.pieces(chess.QUEEN,c)) for c in [True,False]),
            sum(len(board.pieces(chess.ROOK,c)) for c in [True,False]),
            chess.square_distance(board.king(own),board.king(not own)),math.log1p(max(0,clock_before)),
            max(0,clock_before)/max(1,initial),int(clock_before<10),increment,rating_diff,int(own),win_proxy(cp)/100]

def evaluate(engine,board,nodes):
    outcome=board.outcome(claim_draw=False)
    if outcome:
        cp=0 if outcome.winner is None else (100000 if outcome.winner else -100000)
        return dict(cp=cp,mate=None,best=None,pv=[],depth=0,terminal=True)
    info=engine.analyse(board,chess.engine.Limit(nodes=nodes))
    score=info['score'].white()
    pv=info.get('pv',[])
    return dict(cp=score.score(mate_score=100000),mate=score.mate(),best=pv[0].uci() if pv else None,
                pv=[m.uci() for m in pv[:8]],depth=info.get('depth',0),terminal=False)

def game_analysis(game,engine_path,nodes):
    if game.get('variant')!='standard': return dict(id=game['id'],excluded='nonstandard_variant')
    try:
        board=chess.Board()
        moves=[]
        for san in game.get('moves','').split():
            move=board.parse_san(san); moves.append(move); board.push(move)
        if not moves: return dict(id=game['id'],excluded='no_moves')
        engine=chess.engine.SimpleEngine.popen_uci(engine_path)
        engine.configure({'Threads':1,'Hash':64})
        board=chess.Board()
        infos=[evaluate(engine,board,nodes)]
        for move in moves:
            board.push(move); infos.append(evaluate(engine,board,nodes))
        engine.quit()
        return dict(id=game['id'],engine=infos)
    except Exception as exc:
        return dict(id=game['id'],error=str(exc))

def get_rows(game,infos,user):
    own=game['players']['white'].get('user',{}).get('id','').lower()==user.lower()
    me=game['players']['white' if own else 'black']
    opp=game['players']['black' if own else 'white']
    clock=game.get('clock',{})
    initial=clock.get('initial',0); inc=clock.get('increment',0)
    clocks=game.get('clocks',[])
    board=chess.Board(); rows=[]
    for j,san in enumerate(game['moves'].split()):
        move=board.parse_san(san)
        if board.turn==own:
            before,after=infos[j],infos[j+1]
            cp0=before['cp']*(1 if own else -1)
            cp1=after['cp']*(1 if own else -1)
            loss=max(0,cp0-cp1)
            proxy_drop=max(0,win_proxy(cp0)-win_proxy(cp1))
            if before['best']==move.uci():
                loss=0; proxy_drop=0
            cb=clocks[j-2]/100 if j>=2 and len(clocks)>j-2 else initial
            ca=clocks[j]/100 if len(clocks)>j else None
            think=max(0,cb+inc-ca) if ca is not None else None
            ph=phase(board)
            result=1 if game.get('winner')==('white' if own else 'black') else (.5 if 'winner' not in game else 0)
            tags=[ph]
            mate_in_one_available=False
            if before['best']:
                test_board=board.copy(); test_board.push_uci(before['best'])
                mate_in_one_available=test_board.is_checkmate()
                actual_board=board.copy();actual_board.push(move)
                if mate_in_one_available and not actual_board.is_checkmate():
                    tags.append('missed_mate_in_one')
            if cb<10: tags.append('under_10_seconds')
            if ph=='endgame': tags.append(ending_type(board)+'_ending')
            if cp0>=200 and cp1<=50: tags.append('large_advantage_lost')
            if abs(cp0)<=50 and cp1<=-200: tags.append('balanced_to_losing_eval')
            severity='large' if proxy_drop>=10 else ('moderate' if proxy_drop>=5 else 'small_or_none')
            rows.append(dict(game_id=game['id'],created_at=game['createdAt'],speed=game['speed'],rated=game.get('rated'),
                             color='white' if own else 'black',result=result,game_status=game['status'],
                             ply=j+1,move_number=board.fullmove_number,played_san=san,played_uci=move.uci(),
                             fen=board.fen(),phase=ph,endgame_type=ending_type(board) if ph=='endgame' else '',
                             clock_before=cb,clock_after=ca,thinking_seconds=think,
                             pre_cp=cp0,post_cp=cp1,cp_loss=loss,eval_proxy_drop=proxy_drop,
                             engine_depth=min(before['depth'],after['depth']),best_uci=before['best'],
                             best_pv=before['pv'],severity=severity,error=int(proxy_drop>=10),tags=tags,
                             mate_in_one_available=mate_in_one_available,
                             opening=game.get('opening',{}).get('name','Unknown'),
                             features=features(board,own,cb,initial,inc,me.get('rating',0)-opp.get('rating',0),cp0)))
        board.push(move)
    return rows

def sigmoid(z): return 1/(1+np.exp(-np.clip(z,-35,35)))

def fit(X,y,l2):
    # Penalized Newton method; the intercept is not penalized.
    beta=np.zeros(X.shape[1]); beta[0]=math.log((y.sum()+.5)/(len(y)-y.sum()+.5))
    penalty=np.eye(X.shape[1])*l2; penalty[0,0]=0
    for _ in range(60):
        p=sigmoid(X@beta); w=np.maximum(p*(1-p),1e-6)
        grad=X.T@(p-y)/len(y)+penalty@beta
        h=(X.T*w)@X/len(y)+penalty+np.eye(X.shape[1])*1e-8
        step=np.linalg.solve(h,grad)
        beta-=step
        if np.max(np.abs(step))<1e-6: break
    return beta

def metrics(y,p):
    p=np.clip(p,1e-8,1-1e-8)
    auc=None
    if 0<y.sum()<len(y):
        order=np.argsort(p); ranks=np.zeros(len(p)); k=0
        while k<len(p):
            end=k+1
            while end<len(p) and p[order[end]]==p[order[k]]:end+=1
            ranks[order[k:end]]=(k+1+end)/2; k=end
        n1=y.sum(); n0=len(y)-n1; auc=float((ranks[y==1].sum()-n1*(n1+1)/2)/(n1*n0))
    return dict(n=len(y),errors=int(y.sum()),error_rate=float(y.mean()),
                log_loss=float(-np.mean(y*np.log(p)+(1-y)*np.log(1-p))),
                brier=float(np.mean((p-y)**2)),auc=auc)

def train(rows,out):
    # Predict only bullet play. Few blitz games cannot support a separate model.
    eligible=[r for r in rows if r['speed']=='bullet']
    gameids=sorted({r['game_id'] for r in eligible},key=lambda g:next(r['created_at'] for r in eligible if r['game_id']==g))
    n=len(gameids); a=int(.6*n); b=int(.8*n)
    partitions=[set(gameids[:a]),set(gameids[a:b]),set(gameids[b:])]
    sets=[[r for r in eligible if r['game_id'] in ids] for ids in partitions]
    if min(map(len,sets))<100 or min(sum(r['error'] for r in s) for s in sets)<10:
        card={'status':'insufficient_data','split_games':[len(s) for s in partitions]}
        (out/'model_evaluation.json').write_text(json.dumps(card,indent=2)); return card
    Xs=[np.array([r['features'] for r in s],float) for s in sets]
    ys=[np.array([r['error'] for r in s],float) for s in sets]
    mean=Xs[0].mean(0); scale=Xs[0].std(0); scale[scale<1e-6]=1
    Zs=[np.column_stack([np.ones(len(x)),(x-mean)/scale]) for x in Xs]
    choices=[]
    for l2 in [.001,.01,.1,1.0]:
        beta=fit(Zs[0],ys[0],l2)
        choices.append((metrics(ys[1],sigmoid(Zs[1]@beta))['log_loss'],l2,beta))
    _,l2,beta=min(choices,key=lambda x:x[0])
    base=(ys[0].sum()+.5)/(len(ys[0])+1)
    predicted=sigmoid(Zs[2]@beta)
    test=metrics(ys[2],predicted); baseline=metrics(ys[2],np.full(len(ys[2]),base))
    clock_groups=collections.defaultdict(list)
    for r in sets[0]:clock_groups['low' if r['clock_before']<10 else 'normal'].append(r['error'])
    clockrates={k:(sum(v)+1)/(len(v)+2) for k,v in clock_groups.items()}
    clockbaseline=metrics(ys[2],np.array([clockrates.get('low' if r['clock_before']<10 else 'normal',base) for r in sets[2]]))
    card=dict(status='trained',model='L2 logistic regression implemented with NumPy',target='Engine-proxy deterioration of at least 10 percentage points',
              features=FEATURES,split='Chronological 60 percent train / 20 percent validation / 20 percent test, grouped by whole games',
              split_games=[len(p) for p in partitions],train=metrics(ys[0],sigmoid(Zs[0]@beta)),
              validation=metrics(ys[1],sigmoid(Zs[1]@beta)),test=test,constant_baseline=baseline,clock_baseline=clockbaseline,
              selected_l2=l2,beats_constant_log_loss=test['log_loss']<baseline['log_loss'],beats_clock_log_loss=test['log_loss']<clockbaseline['log_loss'],
              scope='Personal bullet play only. Predicts engine-labeled risk, not motives, teaching quality or improvement.',
              label_limitations='Finite-search engine labels are noisy. Evaluation-proxy drops are not calibrated personal win probabilities. Position rows within a game are correlated.')
    model=dict(feature_names=FEATURES,means=mean.tolist(),scales=scale.tolist(),intercept=float(beta[0]),coefficients=beta[1:].tolist(),
               selected_l2=l2,scope=card['scope'],training_game_ids=gameids[:a],validation_game_ids=gameids[a:b],test_game_ids=gameids[b:])
    (out/'risk_model.json').write_text(json.dumps(model,indent=2))
    (out/'model_evaluation.json').write_text(json.dumps(card,indent=2))
    with (out/'heldout_predictions.csv').open('w') as f:
        writer=csv.writer(f);writer.writerow(['game_id','ply','actual_engine_error','predicted_risk'])
        for r,p in zip(sets[2],predicted):writer.writerow([r['game_id'],r['ply'],r['error'],round(float(p),6)])
    return card

def summarize(rows,games):
    def group(key):
        d=collections.defaultdict(list)
        for r in rows:d[key(r)].append(r)
        return {k:dict(moves=len(rs),errors=sum(r['error'] for r in rs),error_rate=sum(r['error'] for r in rs)/len(rs),games=len({r['game_id'] for r in rs})) for k,rs in sorted(d.items())}
    bygame=collections.defaultdict(list)
    for r in rows:bygame[r['game_id']].append(r)
    eg=[]
    for gid,rs in bygame.items():
        qualifying=[r for r in rs if r['phase']=='endgame' and r['pre_cp']>=200]
        if qualifying:
            eg.append(dict(game_id=gid,speed=rs[0]['speed'],first_ply=qualifying[0]['ply'],result=rs[0]['result'],
                           large_advantage_losses=sum('large_advantage_lost' in r['tags'] for r in rs if r['phase']=='endgame')))
    return dict(standard_games=len(bygame),player_moves=len(rows),large_errors=sum(r['error'] for r in rows),
                mate_in_one_opportunities=sum(r['mate_in_one_available'] for r in rows),
                missed_mate_in_one=sum('missed_mate_in_one' in r['tags'] for r in rows),
                phase=group(lambda r:r['phase']),speed=group(lambda r:r['speed']),
                clock=group(lambda r:'under_10_seconds' if r['clock_before']<10 else 'at_least_10_seconds'),
                bullet_clock=group(lambda r:r['speed']+('_under_10_seconds' if r['clock_before']<10 else '_at_least_10_seconds')),
                endgame_types=group(lambda r:r['endgame_type'] or 'not_endgame'),
                promising_endgames=dict(definition='At least one own turn in an endgame with engine score at least +200cp. Screening heuristic, not a theoretical or practical guaranteed win.',
                    games=len(eg),wins=sum(x['result']==1 for x in eg),draws=sum(x['result']==.5 for x in eg),losses=sum(x['result']==0 for x in eg)),
                promising_endgame_records=eg)

def drills(rows,engine_path,out):
    # Re-evaluate review candidates more deeply. These are examples, not a random sample.
    engine=chess.engine.SimpleEngine.popen_uci(engine_path)
    engine.configure({'Threads':1,'Hash':128})
    candidates=sorted([r for r in rows if r['phase']=='endgame' and r['error']],key=lambda r:(r['pre_cp']>=150,r['eval_proxy_drop']),reverse=True)
    chosen=[]; used=set()
    for r in candidates:
        if r['game_id'] in used: continue
        board=chess.Board(r['fen']); own=board.turn
        before=evaluate(engine,board,150000)
        played=chess.Move.from_uci(r['played_uci']); afterboard=board.copy();afterboard.push(played)
        after=evaluate(engine,afterboard,150000)
        cp0=before['cp']*(1 if own else -1);cp1=after['cp']*(1 if own else -1)
        drop=max(0,win_proxy(cp0)-win_proxy(cp1))
        if drop<10 or before['best']==played.uci():continue
        item={k:v for k,v in r.items() if k!='features'}
        item.update(refined_pre_cp=cp0,refined_post_cp=cp1,refined_proxy_drop=drop,
                    refined_pre_mate=before['mate']*(1 if own else -1) if before['mate'] is not None else None,
                    refined_post_mate=after['mate']*(1 if own else -1) if after['mate'] is not None else None,
                    refined_best=before['best'],refined_pv=before['pv'],refined_nodes=150000,
                    refined_depth_before=before['depth'],refined_depth_after=after['depth'])
        chosen.append(item);used.add(r['game_id'])
        if len(chosen)>=8:break
    engine.quit()
    (out/'endgame_review_positions.json').write_text(json.dumps(chosen,indent=2))
    with (out/'endgame_practice.pgn').open('w') as f:
        for i,r in enumerate(chosen,1):
            game=chess.pgn.Game();board=chess.Board(r['fen']);game.setup(board)
            game.headers.update(Event=f'Endgame practice {i}',Site=f'https://lichess.org/{r["game_id"]}',Result='*')
            game.comment=f'Position from your game. You played {r["played_san"]} with {r["clock_before"]:.1f}s at the start of your turn. Find a better plan before viewing the line. Engine example, not proof of a unique best move.'
            node=game
            for uci in r['refined_pv']:
                move=chess.Move.from_uci(uci)
                if move not in board.legal_moves:break
                node=node.add_variation(move);board.push(move)
            f.write(str(game)+'\n\n')
    return chosen

def write_feedback(out,summary,card,examples,manifest):
    s=summary
    lines=['# Personal chess study for chickenboi2','',f'Window: {manifest["since"]} through {manifest["until"]}.',
           '',f'Downloaded {manifest["completed_games"]} completed games. Analyzed {s["standard_games"]} standard games and {s["player_moves"]:,} of your moves. The nonstandard game is preserved in the archive but excluded from analysis.',
           '', '## What the analysis measures','',
           'Stockfish 19 searched 12,000 nodes per position with one thread. A "large error" means a drop of at least 10 percentage points in a fixed evaluation proxy, using the published Lichess centipawn-to-Win% curve. This is an operational label, not an estimate of your personal chance of winning. It is not an official Lichess mistake classification. Finite search can miss tactics; selected review positions were checked again at 150,000 nodes.',
           '', '## Patterns in your games','', '| Context | Your moves | Large errors | Error rate | Games |','|---|---:|---:|---:|---:|']
    for key,v in s['phase'].items():lines.append(f'| {key} | {v["moves"]:,} | {v["errors"]} | {v["error_rate"]:.1%} | {v["games"]} |')
    lines+=['','The phase labels are material-based heuristics. Move rates are descriptive, correlated within games and affected by position difficulty. They do not establish that one phase causes your mistakes.',
            '', '### Bullet and the clock','', '| Clock at start of your turn | Moves | Large errors | Rate |','|---|---:|---:|---:|']
    for k,v in s['bullet_clock'].items():
        if k.startswith('bullet_'):lines.append(f'| {k.removeprefix("bullet_").replace("_"," ")} | {v["moves"]:,} | {v["errors"]} | {v["error_rate"]:.1%} |')
    eg=s['promising_endgames']
    lines+=['','Clock time is measured before the move, using the previous clock reading and increment rules. A correlation with time pressure cannot separate technique, position complexity and earlier clock management.',
            '', '### Endgame conversion','',f'{eg["games"]} games reached an endgame where you had at least one engine evaluation of +2 pawns or more: {eg["wins"]} wins, {eg["draws"]} draws and {eg["losses"]} losses. This is a screening statistic. A shallow engine advantage at one moment is not proof that an endgame was readily winnable. The examples below are a better starting point for review.',
            '', '## Training priorities','',
            '1. Start with the eight reviewed endgame positions in `endgame_practice.pgn`. Solve them without a clock and write the plan before opening the suggested line.',
            '2. Check the same idea in unfamiliar positions. If you struggle untimed, study the technique. If you solve it untimed, practice similar positions with a realistic clock.',
            '3. Separate bullet practice from rapid improvement. This archive has bullet and blitz games, so it does not validate a claim about your current rapid or over-the-board skill.',
            '4. Track later, unseen positions and comparable opportunities in new games. Memorizing these examples does not establish transferable improvement.',
            '', '## Reviewed examples','']
    lines += [f'The engine found mate-in-one opportunities on {s["mate_in_one_opportunities"]} of your turns; {s["missed_mate_in_one"]} were missed. These tags are verified by legal-move checkmate detection. This illustrates why "endgame" is a position category, not a diagnosis: some late-game errors are immediate tactics rather than missing endgame theory.', '']
    for i,r in enumerate(examples,1):
        b=chess.Board(r['fen']);best=b.san(chess.Move.from_uci(r['refined_best']))
        def score(cp,mate):
            if mate is not None:return ('mate available in '+str(mate)) if mate>0 else ('getting mated in '+str(abs(mate)))
            return f'{cp/100:+.2f} pawns'
        lines+=[f'{i}. [{r["game_id"]}, ply {r["ply"]}](https://lichess.org/{r["game_id"]}#{r["ply"]-1}): {r["endgame_type"].replace("_"," ")}; played **{r["played_san"]}**, suggested **{best}**; clock before move {r["clock_before"]:.1f}s. Deeper search evaluation: {score(r["refined_pre_cp"],r["refined_pre_mate"])} to {score(r["refined_post_cp"],r["refined_post_mate"])} from your side.']
    lines+=['','## Trained model','']
    if card['status']=='trained':
        lines += [f'A regularized logistic regression was trained on your bullet positions. Entire games were split chronologically into {card["split_games"][0]} training, {card["split_games"][1]} validation and {card["split_games"][2]} test games. Scaling was learned on training data only; regularization was selected on validation data.',
                  '', '| Held-out measure | Personal model | Constant-rate baseline | Clock-only baseline |','|---|---:|---:|---:|',
                  f'| Log loss (lower is better) | {card["test"]["log_loss"]:.4f} | {card["constant_baseline"]["log_loss"]:.4f} | {card["clock_baseline"]["log_loss"]:.4f} |',
                  f'| Brier score (lower is better) | {card["test"]["brier"]:.4f} | {card["constant_baseline"]["brier"]:.4f} | {card["clock_baseline"]["brier"]:.4f} |',
                  '', f'Test AUC: {card["test"]["auc"]:.3f}. Test labels: {card["test"]["errors"]} large errors among {card["test"]["n"]:,} moves.',
                  '', ('The model beats both simple baselines on held-out log loss. This is preliminary predictive evidence, not proof of stable generalization or coaching effectiveness.' if card['beats_constant_log_loss'] and card['beats_clock_log_loss'] else 'The model does not beat both simple baselines on held-out log loss. Use the engine examples and descriptive patterns; do not treat the fitted model as a validated personal coach.'),
                  '', 'The model estimates engine-labeled risk before a move from board, clock and rating context. It does not classify why you erred. Its probabilities have not been separately calibrated. The main archive was analyzed at a modest search budget, so label quality limits model quality. No language model or chess engine was trained from scratch.']
    else:lines.append('There was not enough labeled data for a reliable three-way training split.')
    lines+=['','## Files and reproducibility','',
            '- `games.pgn` and `games.ndjson`: full completed-game export, with clocks and any existing evaluations.',
            '- `move_labels.csv`: your moves with engine labels and context; `analysis_summary.json`: aggregate counts.',
            '- `risk_model.json`: fitted coefficients and feature scaling; `model_evaluation.json`: scope and validation results.',
            '- `heldout_predictions.csv`: predictions on the games not used for training or model selection.',
            '- `endgame_practice.pgn` and `endgame_review_positions.json`: positions with deeper checks and source links.',
            '', '## Primary references','',
            '- [Lichess export API](https://lichess.org/api#tag/Games/operation/apiGamesUser)',
            '- [Lichess evaluation proxy and accuracy caveats](https://lichess.org/page/accuracy)',
            '- [Stockfish](https://stockfishchess.org/)',
            '- [python-chess engine interface](https://python-chess.readthedocs.io/en/latest/engine.html)',
            '', 'All analysis concerns completed games and runs locally after the export. No private credentials were needed.']
    (out/'feedback.md').write_text('\n'.join(lines)+'\n')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--engine',type=Path,required=True)
    parser.add_argument('--cache-dir',type=Path,default=HERE/'cache')
    parser.add_argument('--nodes',type=int,default=12000)
    args=parser.parse_args()
    args.cache_dir.mkdir(parents=True,exist_ok=True)
    games=[json.loads(l) for l in (args.data_dir/'games.ndjson').read_text().splitlines() if l.strip()]
    manifest=json.loads((args.data_dir/'download_manifest.json').read_text())
    jobs=[];results={}
    for g in games:
        f=args.cache_dir/f'{g["id"]}_{args.nodes}.json'
        if f.exists():results[g['id']]=json.loads(f.read_text())
        else:jobs.append(g)
    print(f'Analyze {len(jobs)} games; {len(results)} cached',flush=True)
    start=time.monotonic()
    with concurrent.futures.ProcessPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(game_analysis,g,str(args.engine.resolve()),args.nodes):g for g in jobs}
        for i,future in enumerate(concurrent.futures.as_completed(futures),1):
            g=futures[future];result=future.result();results[g['id']]=result
            (args.cache_dir/f'{g["id"]}_{args.nodes}.json').write_text(json.dumps(result))
            if i%50==0:print(f'Engine analysis {i}/{len(jobs)} games, {time.monotonic()-start:.1f}s',flush=True)
    rows=[];excluded=[]
    for g in games:
        result=results[g['id']]
        if 'engine' not in result:excluded.append(result);continue
        rows.extend(get_rows(g,result['engine'],'chickenboi2'))
    if any('error' in x for x in excluded):raise RuntimeError(f'Analysis failures: {excluded}')
    print(f'Built {len(rows)} labeled player moves',flush=True)
    with (args.data_dir/'move_labels.csv').open('w') as f:
        fields=[k for k in rows[0] if k!='features']
        writer=csv.DictWriter(f,fields);writer.writeheader()
        for r in rows:writer.writerow({k:json.dumps(r[k]) if isinstance(r[k],list) else r[k] for k in fields})
    summary=summarize(rows,games)
    summary['excluded']=excluded
    (args.data_dir/'analysis_summary.json').write_text(json.dumps(summary,indent=2))
    card=train(rows,args.data_dir)
    print('Model validation:',json.dumps(card,indent=2),flush=True)
    examples=drills(rows,str(args.engine.resolve()),args.data_dir)
    write_feedback(args.data_dir,summary,card,examples,manifest)
    print('Summary:',json.dumps({k:v for k,v in summary.items() if k!='promising_endgame_records'},indent=2),flush=True)
    print('Reviewed examples:',len(examples),flush=True)

if __name__=='__main__':main()
