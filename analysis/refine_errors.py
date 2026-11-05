"""Conservative tactical motifs and endgame profiles from completed games.

Labels describe checked continuations, not a player's mental cause. No LLM labels.
"""
from pathlib import Path
import sys,json,csv,math,collections,concurrent.futures,argparse,time
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'deps'))
import chess,chess.engine,chess.pgn
import numpy as np
from analyze_history import win_proxy,material

V={chess.PAWN:1,chess.KNIGHT:3,chess.BISHOP:3,chess.ROOK:5,chess.QUEEN:9,chess.KING:100}
NAMES={
 'mate_in_one':'Mate in one', 'short_forced_mate':'Short mating sequence',
 'free_piece_capture':'Free piece capture', 'winning_capture':'Profitable material capture',
 'knight_fork':'Knight fork', 'other_fork':'Fork with another piece',
 'king_skewer':'King skewer', 'absolute_pin':'Absolute pin tactic',
 'discovered_check':'Discovered check', 'double_check':'Double check',
 'promotion_sequence':'Promotion sequence', 'back_rank_mate':'Back-rank mate',
 'removing_defender':'Removing a defender', 'discovered_attack':'Discovered attack',
}

def see_recapture(board,square,depth=8):
    """Capture-only exchange tree on one square; side may decline an exchange."""
    if depth<=0:return 0
    best=0
    for move in list(board.generate_legal_captures()):
        if move.to_square!=square:continue
        p=board.piece_at(square)
        gain=V[p.piece_type] if p else 1
        if move.promotion:gain+=V[move.promotion]-1
        board.push(move)
        value=gain-see_recapture(board,square,depth-1)
        board.pop()
        best=max(best,value)
    return best

def exchange_gain(board,move):
    if not board.is_capture(move):return 0
    p=board.piece_at(move.to_square)
    gain=V[p.piece_type] if p else 1
    if move.promotion:gain+=V[move.promotion]-1
    b=board.copy();b.push(move)
    return gain-see_recapture(b,move.to_square)

def legal_line(board,pv,max_plies=7):
    b=board.copy();line=[]
    for u in pv[:max_plies]:
        m=chess.Move.from_uci(u)
        if m not in b.legal_moves:break
        line.append(m);b.push(m)
    return line

def mating_moves(board):
    b=board.copy();out=[]
    for m in list(b.legal_moves):
        b.push(m)
        if b.is_checkmate():out.append(m.uci())
        b.pop()
    return out

def motif_labels(board,pv,mate=None):
    """Motifs anchored to first action, plus verified short mating sequences."""
    line=legal_line(board,pv)
    if not line:return []
    own=board.turn;m=line[0];piece=board.piece_at(m.from_square)
    after=board.copy();after.push(m)
    labels=[]
    if after.is_checkmate():labels.append('mate_in_one')
    if mate is not None and 1<mate<=3:labels.append('short_forced_mate')
    checkers=list(after.checkers())
    if len(checkers)>1:labels.append('double_check')
    if checkers and m.to_square not in checkers:labels.append('discovered_check')
    captured=board.piece_at(m.to_square)
    gain=exchange_gain(board,m) if board.is_capture(m) else 0
    if captured and captured.piece_type in [2,3,4,5] and gain>=2:
        replies=[x for x in after.generate_legal_captures() if x.to_square==m.to_square]
        labels.append('free_piece_capture' if not replies else 'winning_capture')
        # A geometrical defender which cannot legally recapture because of its king.
        for sq in board.attackers(not own,m.to_square):
            if board.piece_type_at(sq)!=chess.KING and board.is_pinned(not own,sq):
                if not any(x.from_square==sq and x.to_square==m.to_square for x in replies):
                    labels.append('absolute_pin');break
    # Require a concrete material gain in the short line for a fork label.
    attacked=[]
    for sq in after.attacks(m.to_square):
        p=after.piece_at(sq)
        if p and p.color!=own and p.piece_type!=chess.PAWN:
            if p.piece_type==chess.KING or V[p.piece_type]>V[piece.piece_type] or not after.attackers(not own,sq):
                attacked.append(sq)
    material_start=material(board,own)-material(board,not own)
    b=board.copy();gains=[]
    for i,x in enumerate(line[:6]):
        b.push(x)
        # Measure after the opponent has had a reply, not at a temporary capture peak.
        if i in [3,5] or b.is_game_over():gains.append(material(b,own)-material(b,not own)-material_start)
    third_capture=False
    if len(line)>=3:
        after_reply=after.copy();after_reply.push(line[1])
        third_capture=after_reply.is_capture(line[2])
    next_capture=(len(line)>=3 and third_capture and line[2].from_square==m.to_square and line[2].to_square in attacked)
    can_take_attacker=any(x.to_square==m.to_square and exchange_gain(after,x)>=0 for x in after.generate_legal_captures())
    if len(attacked)>=2 and next_capture and max(gains or [0])>=2 and not can_take_attacker:
        labels.append('knight_fork' if piece.piece_type==chess.KNIGHT else 'other_fork')
    # Strict checking skewer: king moves and the same slider takes a piece behind it.
    if piece.piece_type in [3,4,5] and after.is_check() and len(line)>=3:
        king=after.king(not own);reply=line[1];take=line[2]
        victim=after.piece_at(take.to_square)
        if (reply.from_square==king and take.from_square==m.to_square and victim and victim.color!=own
            and victim.piece_type in [2,3,4,5] and king in chess.SquareSet.between(m.to_square,take.to_square)
            and max(gains or [0])>=2):labels.append('king_skewer')
    # Pin created by the first move and exploited on the next own move.
    if len(line)>=3:
        sq=line[2].to_square
        victim=after.piece_at(sq)
        if third_capture and victim and victim.color!=own and after.is_pinned(not own,sq) and after_reply.is_pinned(not own,sq) and max(gains or [0])>=2:
            labels.append('absolute_pin')
        original_target=board.piece_at(sq)
        if third_capture and captured and original_target and original_target.color!=own and original_target.piece_type in [2,3,4,5] and sq!=m.to_square:
            if sq in board.attacks(m.to_square) and max(gains or [0])>=2:
                labels.append('removing_defender')
        if (third_capture and original_target and original_target.color!=own and original_target.piece_type in [2,3,4,5]
            and sq!=m.to_square and line[2].from_square!=m.to_square and m.from_square in chess.SquareSet.between(line[2].from_square,sq)
            and max(gains or [0])>=2):
            labels.append('discovered_attack')
    if m.promotion or (piece.piece_type==chess.PAWN and any(x.promotion for x in line[::2][:3])):
        labels.append('promotion_sequence')
    # A back-rank label requires actual checkmate at the end of the checked line.
    if mate is not None and 0<mate<=3:
        b=board.copy()
        for x in line:b.push(x)
        if b.is_checkmate():
            king=b.king(not own);back=7 if own else 0
            if chess.square_rank(king)==back and any(chess.square_rank(sq)==back for sq in b.checkers()):
                front=[chess.square(f,back+(-1 if own else 1)) for f in range(max(0,chess.square_file(king)-1),min(7,chess.square_file(king)+1)+1)]
                if all(b.piece_at(sq) and b.color_at(sq)!=own for sq in front):labels.append('back_rank_mate')
    return sorted(set(labels))

def endgame_kind(board):
    sets={c:{p.piece_type for p in board.piece_map().values() if p.color==c}-{1,6} for c in [True,False]}
    alltypes=sets[True]|sets[False]
    if not alltypes:return 'King and pawn'
    if alltypes=={4}:
        if not (sets[True] and sets[False]):return 'Rook versus pawns or bare king'
        counts=[len(board.pieces(chess.ROOK,c)) for c in [True,False]]
        if counts==[1,1]:return 'Single rook versus single rook'
        if counts==[2,2]:return 'Double rook endings'
        return 'Unequal rook material'
    if alltypes=={3}:
        if sets[True] and sets[False]:
            bishops=[(sq,p) for sq,p in board.piece_map().items() if p.piece_type==3]
            colors=[(chess.square_rank(sq)+chess.square_file(sq))%2 for sq,p in bishops]
            if len(bishops)==2:return 'Bishops of same color' if colors[0]==colors[1] else 'Bishops of opposite colors'
        return 'Other bishop ending'
    if alltypes=={2}:return 'Knight versus knight' if sets[True] and sets[False] else 'Knight versus pawns or bare king'
    if alltypes<={2,3}:
        if (sets[True],sets[False]) in [({2},{3}),({3},{2})]:return 'Bishop versus knight'
        return 'Other minor piece ending'
    if alltypes=={5}:return 'Queen versus queen' if sets[True] and sets[False] else 'Queen versus pawns or bare king'
    if alltypes<={4,5}:return 'Queen and rook material'
    if 5 in alltypes:return 'Queen with minor piece material'
    if 4 in alltypes:
        if (sets[True]=={4} and sets[False]<={2,3}) or (sets[False]=={4} and sets[True]<={2,3}):return 'Rook versus minor piece'
        return 'Rook with minor piece material'
    return 'Other'

def analyze_root(engine,board,nodes,move=None):
    outcome=board.outcome(claim_draw=False)
    if outcome:
        cp=0 if outcome.winner is None else (100000 if outcome.winner==board.turn else -100000)
        return dict(cp=cp,mate=None,pv=[],depth=0)
    kwargs={'root_moves':[move]} if move else {}
    info=engine.analyse(board,chess.engine.Limit(nodes=nodes),**kwargs)
    score=info['score'].pov(board.turn)
    return dict(cp=score.score(mate_score=100000),mate=score.mate(),pv=[m.uci() for m in info.get('pv',[])[:9]],depth=info.get('depth',0))

def refine_group(gid,rows,engine_path,nodes,cache_file):
    p=Path(cache_file);cached=json.loads(p.read_text()) if p.exists() else {}
    todo=[r for r in rows if str(r['ply']) not in cached]
    if not todo:return gid,cached
    engine=chess.engine.SimpleEngine.popen_uci(engine_path);engine.configure({'Threads':1,'Hash':64})
    for r in todo:
        board=chess.Board(r['fen']);played=chess.Move.from_uci(r['played_uci'])
        best=analyze_root(engine,board,nodes)
        actual=best if best['pv'] and best['pv'][0]==r['played_uci'] else analyze_root(engine,board,nodes,played)
        cached[str(r['ply'])]=dict(best=best,actual=actual)
    engine.quit();p.write_text(json.dumps(cached))
    return gid,cached

def rate_ci(items):
    bygame=collections.defaultdict(lambda:[0,0])
    for gid,miss in items:
        bygame[gid][0]+=int(miss);bygame[gid][1]+=1
    if not bygame:return [None,None]
    a=np.array(list(bygame.values()));rng=np.random.default_rng(123)
    rates=[]
    for _ in range(400):
        sm=a[rng.integers(0,len(a),len(a))].sum(0);rates.append(sm[0]/sm[1])
    return [float(x) for x in np.quantile(rates,[.025,.975])]

def main():
    p=argparse.ArgumentParser();p.add_argument('--data-dir',type=Path,required=True);p.add_argument('--engine',type=Path,required=True)
    p.add_argument('--cache-dir',type=Path,default=HERE/'refined_cache');p.add_argument('--nodes',type=int,default=100000)
    args=p.parse_args();out=args.data_dir/'refined';out.mkdir(exist_ok=True);args.cache_dir.mkdir(exist_ok=True)
    games={g['id']:g for g in map(json.loads,(args.data_dir/'games.ndjson').read_text().splitlines())}
    with (args.data_dir/'move_labels.csv').open() as f:rows=list(csv.DictReader(f))
    for r in rows:
        for k in ['ply','created_at']:r[k]=int(r[k])
        for k in ['clock_before','thinking_seconds','pre_cp','post_cp','eval_proxy_drop','result']:r[k]=float(r[k])
        r['best_pv']=json.loads(r['best_pv']);r['tags']=json.loads(r['tags'])
    selected=collections.defaultdict(list);opportunities={};first_endgames={};mate_checks={}
    # Screen every decision; exact mate-in-one check is independent of engine choice.
    for i,r in enumerate(rows):
        b=chess.Board(r['fen']);mates=mating_moves(b)
        if mates:mate_checks[(r['game_id'],r['ply'])]=mates
        labels=motif_labels(b,r['best_pv'])
        if mates:labels=sorted(set(labels+['mate_in_one']))
        opportunities[(r['game_id'],r['ply'])]=labels
        if r['phase']=='endgame':
            r['ending_kind']=endgame_kind(b)
            key=(r['game_id'],r['ending_kind'])
            if key not in first_endgames:first_endgames[key]=r['ply']
        # Refine all material/mating screens and all substantial endgame errors.
        if labels or r['eval_proxy_drop']>=10 or r['phase']=='endgame':
            selected[r['game_id']].append(r)
        if (i+1)%5000==0:print(f'Screened {i+1}/{len(rows)} player decisions',flush=True)
    print(f'Refine {sum(map(len,selected.values()))} positions in {len(selected)} games at {args.nodes} nodes per root search',flush=True)
    refined={};start=time.monotonic()
    with concurrent.futures.ProcessPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(refine_group,gid,rs,str(args.engine.resolve()),args.nodes,str(args.cache_dir/f'{gid}_{args.nodes}.json')) for gid,rs in selected.items()]
        for i,f in enumerate(concurrent.futures.as_completed(futures),1):
            gid,results=f.result()
            for ply,v in results.items():refined[(gid,int(ply))]=v
            if i%50==0:print(f'Refined {i}/{len(futures)} games in {time.monotonic()-start:.1f}s',flush=True)
    by_motif=collections.defaultdict(list);events=[];unclassified=[];endings=collections.defaultdict(list)
    for r in rows:
        key=(r['game_id'],r['ply']);b=chess.Board(r['fen']);data=refined.get(key)
        if not data:continue
        best,actual=data['best'],data['actual']
        drop=max(0,win_proxy(best['cp'])-win_proxy(actual['cp']))
        if best['pv'] and best['pv'][0]==r['played_uci']:drop=0
        # Small false-positive motifs are filtered by deeper search and material checks.
        own_labels=motif_labels(b,best['pv'],best['mate'])
        mates=mate_checks.get(key,[])
        if mates:own_labels=sorted(set(own_labels+['mate_in_one']))
        after=b.copy();after.push_uci(r['played_uci'])
        opp_pv=actual['pv'][1:] if actual['pv'] and actual['pv'][0]==r['played_uci'] else []
        opp_mate=abs(actual['mate']) if actual['mate'] is not None and actual['mate']<0 else None
        allowed=motif_labels(after,opp_pv,opp_mate) if drop>=10 else []
        if drop>=10 and mating_moves(after):allowed=sorted(set(allowed+['mate_in_one']))
        # Success means preserved evaluation, even if another good move was chosen.
        for label in own_labels:
            miss=(r['played_uci'] not in mates) if label=='mate_in_one' and mates else drop>=10
            by_motif[label].append((r['game_id'],bool(miss)))
            if miss:
                event=dict(r,direction='missed',motif=label,refined_drop=drop,refined_pre_cp=best['cp'],refined_actual_cp=actual['cp'],solution=best['pv'],refined_pre_mate=best['mate'])
                events.append(event)
        for label in allowed:
            events.append(dict(r,direction='allowed',motif=label,refined_drop=drop,refined_pre_cp=best['cp'],refined_actual_cp=actual['cp'],solution=best['pv'],refutation=opp_pv,refined_pre_mate=best['mate']))
        if drop>=10 and not own_labels and not allowed:unclassified.append(dict(r,refined_drop=drop))
        if r['phase']=='endgame':
            action='Other move'
            if best['pv']:
                bm=chess.Move.from_uci(best['pv'][0]);pt=b.piece_type_at(bm.from_square)
                bb=b.copy();bb.push(bm)
                if bb.is_checkmate():action='Immediate checkmate'
                elif b.is_capture(bm) or bb.is_check() or bm.promotion:action='Forcing check capture or promotion'
                elif pt==chess.KING:action='Quiet king maneuver'
                elif pt==chess.ROOK:action='Quiet rook maneuver'
                elif pt==chess.PAWN:action='Pawn move'
                else:action='Quiet piece maneuver'
            ab=b.copy()
            actual_line=legal_line(ab,actual['pv'],2)
            if len(actual_line)==2:
                original_types={p.piece_type for p in b.piece_map().values()}-{1,6}
                for m in actual_line:ab.push(m)
                final_types={p.piece_type for p in ab.piece_map().values()}-{1,6}
                if original_types=={4} and not final_types and b.is_capture(chess.Move.from_uci(r['played_uci'])):
                    action='Rook trade into pawn ending'
            endings[r['ending_kind']].append(dict(r,refined_drop=drop,refined_pre_cp=best['cp'],refined_actual_cp=actual['cp'],refined_pre_mate=best['mate'],better_move_action=action,solution=best['pv'],refutation=opp_pv))
    tactics=[]
    for label,items in by_motif.items():
        misses=sum(m for _,m in items)
        allowed_events=[e for e in events if e['direction']=='allowed' and e['motif']==label]
        tactics.append(dict(motif=label,name=NAMES[label],opportunities=len(items),missed=misses,miss_rate=misses/len(items),
                            games=len({g for g,m in items}),miss_rate_game_bootstrap_95=rate_ci(items),
                            allowed=len(allowed_events),allowed_games=len({e['game_id'] for e in allowed_events})))
    # Include labels observed only in refutations.
    for label in {e['motif'] for e in events}-{t['motif'] for t in tactics}:
        ev=[e for e in events if e['motif']==label and e['direction']=='allowed']
        tactics.append(dict(motif=label,name=NAMES[label],opportunities=0,missed=0,miss_rate=None,games=0,miss_rate_game_bootstrap_95=[None,None],allowed=len(ev),allowed_games=len({e['game_id'] for e in ev})))
    tactics.sort(key=lambda t:(t['missed']+t['allowed']),reverse=True)
    endgame_stats=[]
    # Exposure counts use every original position, not just the refined subset.
    all_ending=collections.defaultdict(list)
    for r in rows:
        if r['phase']=='endgame':all_ending[r['ending_kind']].append(r)
    for kind,allrows in all_ending.items():
        refinedrows=endings[kind]
        comparable=[r for r in refinedrows if -200<=r['refined_pre_cp']<=400 and r['refined_pre_mate'] is None]
        errors=[r for r in comparable if r['refined_drop']>=10]
        # Denominator is screened decisions, explicitly not every endgame move.
        bygame=collections.defaultdict(list)
        for r in refinedrows:bygame[r['game_id']].append(r)
        chances=[]
        for gid,rs in bygame.items():
            rs.sort(key=lambda x:x['ply'])
            for a,z in zip(rs,rs[1:]):
                if z['ply']==a['ply']+2 and a['refined_pre_cp']>=150 and a['refined_actual_cp']>=100 and z['refined_pre_cp']>=150 and a['refined_pre_mate'] is None and z['refined_pre_mate'] is None:
                    chances.append(dict(game_id=gid,result=a['result'],first_ply=a['ply']));break
        losses=[r for r in refinedrows if r['refined_pre_cp']>=150 and r['refined_actual_cp']<=50 and r['refined_drop']>=10]
        endgame_stats.append(dict(kind=kind,games=len({r['game_id'] for r in allrows}),moves=len(allrows),
                                 checked_moves=len(refinedrows),checked_competitive_moves=len(comparable),
                                 checked_large_errors=len(errors),competitive_error_rate=len(errors)/len(comparable) if comparable else None,
                                 competitive_error_rate_game_bootstrap_95=rate_ci([(r['game_id'],r['refined_drop']>=10) for r in comparable]),
                                 error_actions=dict(collections.Counter(r['better_move_action'] for r in errors)),
                                 errors_under_10_seconds=sum(r['clock_before']<10 for r in errors),advantage_losses=len(losses),
                                 stable_advantage_games=len(chances),wins=sum(x['result']==1 for x in chances),
                                 draws=sum(x['result']==.5 for x in chances),losses=sum(x['result']==0 for x in chances),
                                 stable_advantage_records=chances))
    endgame_stats.sort(key=lambda x:x['games'],reverse=True)
    summary=dict(standard_games=618,player_moves=len(rows),refined_positions=len(refined),nodes=args.nodes,
                 tactics=tactics,endgames=endgame_stats,classified_error_events=len(events),
                 unique_classified_error_moves=len({(e['game_id'],e['ply']) for e in events}),
                 unclassified_large_errors=len(unclassified),
                 limitations=['Motif detectors are conservative and incomplete; categories overlap.',
                              'Opportunity counts are engine-selected screens, not an exhaustive census of all tactics.',
                              'Only mate-in-one opportunities are exhaustively checked with legal moves.',
                              'Allowed-tactic counts have no equivalent opportunity denominator and should not be compared as miss rates.',
                              'Deeper-search errors are checked at finite node budgets, not tablebase truth.',
                              'All endgame positions are refined; comparisons below restrict to competitive evaluations and exclude forced mates.',
                              'Stable-advantage outcomes can overlap across material categories within a game and are descriptive.',
                              'No diagnosis of psychological cause or OTB/rapid skill is made.'])
    (out/'classification_summary.json').write_text(json.dumps(summary,indent=2))
    (out/'classified_events.json').write_text(json.dumps(events,indent=2))
    (out/'endgame_decisions.json').write_text(json.dumps([r for rs in endings.values() for r in rs],indent=2))
    (out/'unclassified_errors.json').write_text(json.dumps(unclassified,indent=2))
    make_report(out,summary,events)
    print(json.dumps(summary,indent=2),flush=True)

def make_report(out,s,events):
    lines=['# Tactical and endgame profile for chickenboi2','',
           f'All {s["player_moves"]:,} decisions from 618 standard games were screened. {s["refined_positions"]:,} positions were rechecked at {s["nodes"]:,} nodes per root search with Stockfish 19. The actual move was evaluated from the same starting position as the best alternative.',
           '', '## Tactical patterns','',
           '| Pattern | Detected chances | Missed value | Miss rate | Games with chances | Allowed opponent tactic |',
           '|---|---:|---:|---:|---:|---:|']
    for t in s['tactics']:
        rate=f'{t["miss_rate"]:.0%}' if t['miss_rate'] is not None else '-'
        lines.append(f'| {t["name"]} | {t["opportunities"]} | {t["missed"]} | {rate} | {t["games"]} | {t["allowed"]} |')
    lines+=['','A missed-value event means the chosen move lost at least 10 percentage points in the fixed engine-evaluation proxy. Another sound move counts as preserving value even if it does not execute the detected motif. Mate in one is checked exactly and counted as missed whenever no mating move was played. Allowed tactics are counted only after substantial evaluation deterioration; they do not have a matched denominator.',
            '', 'These are overlapping, conservative detectors. Most motifs are identified from the first action and short continuation, with material-gain checks; they do not cover every valid tactic. Opportunities with very few examples are not reliable weakness estimates. The JSON includes uncertainty intervals resampled by game.',
            '', '## Endgame material types','',
            '| Type | Games reached | Competitive decisions | Large errors | Error rate | Losses of an advantage |',
            '|---|---:|---:|---:|---:|---:|']
    for e in s['endgames']:
        rate=f'{e["competitive_error_rate"]:.1%}' if e['competitive_error_rate'] is not None else '-'
        lines.append(f'| {e["kind"]} | {e["games"]} | {e["checked_competitive_moves"]} | {e["checked_large_errors"]} | {rate} | {e["advantage_losses"]} |')
    lines+=['','All endgame decisions received deeper analysis. The rates restrict to positions evaluated from -2 to +4 pawns, excluding forced mates, to avoid counting long stretches of already-decided play as successful decisions. Position difficulty and clocks still differ, so this is not a fair peer benchmark. Advantage losses go from at least +1.5 pawns to at most +0.5 with a substantial proxy drop. A position can be an endgame and still contain a simple tactical mistake.',
            '', '### What the stronger endgame move does','',
            '| Type | Action categories among the large errors | Errors with under 10 seconds |','|---|---|---:|']
    for e in s['endgames']:
        if e['checked_large_errors']:
            actions='; '.join(f'{k}: {v}' for k,v in sorted(e['error_actions'].items(),key=lambda kv:kv[1],reverse=True))
            lines.append(f'| {e["kind"]} | {actions} | {e["errors_under_10_seconds"]}/{e["checked_large_errors"]} |')
    lines+=['','Action labels identify what the checked better move does, not why it works. A quiet king maneuver can be tactical defense; it is not automatically evidence of an opposition knowledge gap. The rook-trade label identifies an actual exchange into a pawn-only ending.',
            '', '### Outcomes after a sustained advantage','',
            '| Type | Games with sustained advantage | Won | Drew | Lost |','|---|---:|---:|---:|---:|']
    for e in s['endgames']:
        if e['stable_advantage_games']:lines.append(f'| {e["kind"]} | {e["stable_advantage_games"]} | {e["wins"]} | {e["draws"]} | {e["losses"]} |')
    lines+=['','Sustained advantage means two consecutive own turns in the same material category each evaluated at +1.5 pawns or more, while the first chosen move preserves at least +1 pawn, without a forced-mate evaluation. This is a practical screen, not a theoretical win. Small samples, opponent strength, clock, and transitions between endgame types limit comparisons.',
            '', '## Positions to review','']
    chosen=[];used=set()
    # Give tactical diversity; at most one primary example per family/direction.
    for direction in ['missed','allowed']:
        added=0
        for t in sorted(s['tactics'],key=lambda t:t['missed'] if direction=='missed' else t['allowed'],reverse=True):
            ev=[e for e in events if e['motif']==t['motif'] and e['direction']==direction and (e['game_id'],e['ply']) not in used]
            ev.sort(key=lambda e:(e['clock_before']>=10,e['refined_drop']),reverse=True)
            if ev:
                chosen.append(ev[0]);used.add((ev[0]['game_id'],ev[0]['ply']));added+=1
            if added>=7:break
    endgame_rows=json.loads((out/'endgame_decisions.json').read_text())
    for kind in [e['kind'] for e in s['endgames'] if e['games']>=10 and e['checked_competitive_moves']>=30][:6]:
        candidates=[r for r in endgame_rows if r['ending_kind']==kind and r['refined_drop']>=10
                    and -200<=r['refined_pre_cp']<=400 and r['refined_pre_mate'] is None
                    and (r['game_id'],r['ply']) not in used]
        candidates.sort(key=lambda r:(r['clock_before']>=15,r['better_move_action'] in ['Quiet king maneuver','Quiet rook maneuver','Rook trade into pawn ending'],r['refined_drop']),reverse=True)
        if candidates:
            e=dict(candidates[0],direction='endgame',motif='endgame')
            chosen.append(e);used.add((e['game_id'],e['ply']))
    exchanges=[r for r in endgame_rows if r['better_move_action']=='Rook trade into pawn ending'
               and r['refined_drop']>=10 and -200<=r['refined_pre_cp']<=400
               and (r['game_id'],r['ply']) not in used]
    if exchanges:
        e=dict(max(exchanges,key=lambda r:r['refined_drop']),direction='endgame',motif='endgame')
        chosen.append(e);used.add((e['game_id'],e['ply']))
    with (out/'targeted_practice.pgn').open('w') as f:
        for i,e in enumerate(chosen,1):
            board=chess.Board(e['fen']);solution=e['solution'];best=board.san(chess.Move.from_uci(solution[0])) if solution else '?'
            title=('Endgame decision in '+e['ending_kind'].lower()) if e['direction']=='endgame' else ('Missed ' if e['direction']=='missed' else 'Allowed ')+NAMES[e['motif']].lower()
            lines.append(f'{i}. **{title}** — [{e["game_id"]}, move {e["move_number"]}](https://lichess.org/{e["game_id"]}#{e["ply"]-1}): played **{e["played_san"]}**, preferred **{best}**, {e["clock_before"]:.1f}s before the turn. Position and solution are in the practice PGN.')
            g=chess.pgn.Game();g.setup(board);g.headers.update(Event=title,Site=f'https://lichess.org/{e["game_id"]}',Result='*')
            g.comment=f'{title}. You played {e["played_san"]}. Find a better move before viewing the continuation.'
            node=g
            for m in legal_line(board,solution,9):node=node.add_variation(m)
            if e['direction'] in ['allowed','endgame'] and e.get('refutation'):
                actual=g.add_variation(chess.Move.from_uci(e['played_uci']));actual.comment='Actual move and checked opponent refutation.'
                ab=board.copy();ab.push_uci(e['played_uci']);anode=actual
                for m in legal_line(ab,e['refutation'],7):anode=anode.add_variation(m)
            f.write(str(g)+'\n\n')
    lines+=['','## Classification definitions and limits','',
            '- Free piece capture: the checked first move takes a non-pawn piece with a capture-only exchange gain of at least two pawns and no immediate legal recapture on that square.',
            '- Profitable capture: a non-pawn capture wins at least two pawns in the capture-only exchange tree, even though recapture is available.',
            '- Fork: the first move attacks at least two valuable targets, the checked continuation captures a forked target, and a short material gain is visible. The attacker must not be immediately capturable at no exchange cost.',
            '- King skewer: a checking slider forces the king off a line, then captures material behind it.',
            '- Absolute pin: the checked capture exploits a defender pinned to its king, or a newly pinned piece is captured next in the continuation.',
            '- Removing a defender: the first action captures a piece defending another non-pawn target that is then captured in a material-winning continuation.',
            '- Discovered attack: the first move clears a line so a different friendly slider captures a pre-existing target on the next turn; routine recaptures on the first move\'s destination are excluded.',
            '- Short mating sequence: the engine reports mate within three moves; the label concerns the searched line and can require more review.',
            '- Bishop colors and piece inventories are exact board features. Endgame phase remains a material heuristic.',
            f'- {s["unclassified_large_errors"]:,} checked large-error moves did not match these tactical detectors. They remain unclassified rather than receiving an invented strategic explanation.',
            '', 'Relevant theme definitions: [Lichess puzzle themes](https://lichess.org/training/themes). Analysis uses [Stockfish](https://stockfishchess.org/) and [python-chess](https://python-chess.readthedocs.io/en/latest/).']
    (out/'tactics_and_endgames.md').write_text('\n'.join(lines)+'\n')

if __name__=='__main__':main()
