"""Export actual analysis into a small, browser-local case study. No synthetic results."""
from pathlib import Path
import sys,json,csv,math,io,shutil,argparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'analysis'))
p=argparse.ArgumentParser()
p.add_argument('--engine',type=Path,required=True)
p.add_argument('--data-dir',type=Path,default=ROOT/'analysis/data')
p.add_argument('--refined-cache',type=Path,default=ROOT/'analysis/refined_cache')
args=p.parse_args()
from analyze_history import features,win_proxy
import chess,chess.pgn,chess.svg,chess.engine
DATA=args.data_dir
OUT=ROOT/'dist'
OUT.mkdir(parents=True,exist_ok=True)
games={g['id']:g for g in map(json.loads,(DATA/'games.ndjson').read_text().splitlines())}
rows=list(csv.DictReader((DATA/'move_labels.csv').open()))
byfen={r['fen']:r for r in rows}
summary=json.loads((DATA/'refined/classification_summary.json').read_text())
model=json.loads((DATA/'risk_model.json').read_text())
evaluation=json.loads((DATA/'model_evaluation.json').read_text())
events=json.loads((DATA/'refined/classified_events.json').read_text())
endgames=json.loads((DATA/'refined/endgame_decisions.json').read_text())
details={(r['game_id'],int(r['ply'])):r for r in events+endgames}

def line_data(board,ucis):
    b=board.copy(); seq=[{'fen':b.fen(),'san':'Position','uci':None}]
    for u in ucis[:10]:
        try:
            m=chess.Move.from_uci(u)
            if m not in b.legal_moves:break
            san=b.san(m);b.push(m);seq.append({'fen':b.fen(),'san':san,'uci':u})
        except ValueError:break
    return seq

notes={
 'lfuBOxok':('Look for the finish','The rook move Rf6 is checkmate. Capturing a pawn with Rxg6 misses an immediate finish. You had 20 seconds, so the position is useful for a deliberate checks-first drill.','Before taking material, scan every forcing check.'),
 'uDioHwT0':('Keep the king out of the net','After Kg4, the checked line begins …h5+, followed by …g4+ and …g3+. Kh3 avoids that mating net. This is a king-safety decision, even with so little material left.','Name the opponent’s strongest pawn check before moving your king.'),
 'qlnvDLnu':('A trade changes the whole ending','Rxe2+ allows Kxe2 and enters a pawn ending the engine evaluates as losing for Black. Keeping the rooks with Rc3 maintains roughly equal chances.','Calculate the pawn ending before offering a rook trade.'),
 'TzZCoUIw':('The pawn can wait','Rxd6 releases the black king with …Ke7. Ra7 keeps the rook active on the seventh rank and restricts the king. Compare the lines before deciding that an extra pawn is worth the activity.','Ask what your rook is preventing before moving it to take a pawn.'),
 'RfTYCHaz':('Find the forcing fork','Nf1+ attacks the king and the rook on d2. The check gives Black time to take the rook in the checked continuation.','Look for knight checks that also attack a heavier piece.'),
 'EI1GVeLt':('Check the opponent’s jump','The historical move g6 allowed a knight fork. Practice checking the opponent’s forcing replies before committing to a pawn move.','Before your move, scan the opponent’s knight checks.'),
 'gKKAlMSL':('Take the hanging queen','The queen on c3 can be captured with Qxc3. Ke2 instead lets Black check with …b4+ and take the rook on a1 in the checked line.','Scan the whole board for undefended pieces before moving your king.'),
 'fCGYrT2D':('Calculate the recapture','After …Nxd4, Nxd4 is met by …Qxd5. Work through the full exchange rather than rejecting a capture just because the piece can be taken back.','Count material after the complete capture sequence.'),
 'EPz68xy3':('Use the pin before taking the rook','The pawn on d3 appears to defend the knight on c4, but it is pinned to the king on d2 by the rook on d5. …Qxc4 exploits that alignment. …Qxa1 instead allows Rxa1 and loses the queen.','Check which apparent defenders are pinned to their king.'),
 'bcO54BEV':('Find the mate in two','Qxf7+ leaves Black only Kh8, followed by Qxg7#. The bishop on b3 protects f7; the bishop on d4 protects g7. Rfd1 misses this sequence.','Calculate forcing checks even when the queen moves next to the king.'),
 'jvjzb0Wr':('The queen can fork with check','…Qd4+ checks the king and attacks the bishop on f4. After Kf1, …Qxf4 collects it. The historical …g5 lets White generate counterplay with Rc8+.','A queen check can also be a double attack.'),
 'Oq8J1n0I':('Do not check on autopilot','…Qxg2 is immediate mate. The historical …Nxf3+ lets Qxf3 take the knight. This position carries more than one useful label: missed mate and an allowed free-piece capture.','Compare all forcing checks rather than playing the first one you see.'),
 'NcTrrCAv':('Check what the knight can take','After …Bb7, White has Nxd6, winning the queen even though the knight can be recaptured. …Nxe4 is one checked alternative; several queen retreats also preserve the position.','Check the opponent’s captures on your most valuable pieces.'),
 'C7PVAIhZ':('Stop the mate before taking material','The historical …axb5 opens the a-file and permits Qa8#. …Qe8 addresses the mating threat. A pawn capture is irrelevant when the king has no escape.','Before opening a file, trace the opponent’s queen route to your king.'),
 'PpuOGqz5':('Step off the fork diagonal','Qxf5 leaves the king on e1 and rook on a1 exposed to …Qxc3+, a queen fork. Castling first is one sound alternative, moving the king away from the diagonal.','Before taking material, check whether your king and rook can be forked.'),
 'CdDIylyB':('A pawn grab permits a mating net','After Nxb7, Black has …Rh8+ and the checked line ends Rh4 …Rxh4#. Nf5+ creates a forcing interruption; Rxf7+ is another sound first move.','Check the opponent’s rook checks before sending a defender away.'),
 'co69A7ox':('Respect the pin on the e-file','Qb5 allows …Qxb5 because the bishop on e2 is pinned to the king on e1 by the rook on e4. The bishop cannot recapture the queen. Rd2 avoids this tactic.','A geometrical defender is not a legal defender when its king is pinned.'),
 '4ik6lbk1':('Meet the threat with the rook','…Kg8 permits Rag7+ and a sequence of checks that dominates the seventh rank. …Rf7 is the checked defensive resource. Compare the exchange after Raxf7+ before walking the king into the net.','Look for an active defensive rook move before retreating the king.'),
 'eLt51sSg':('Create counterplay with a pawn break','…Kf7 allows Kg4 and gives up the favorable evaluation. The checked pawn moves …a4 and …b5 preserve more of Black’s chances. This is a small-sample teaching example, not proof of a general pawn-ending weakness.','Calculate pawn breaks alongside king moves in a pawn ending.'),
 'AYZVXDYq':('Remove the obstacle to promotion','…Kxa4 removes the a4 pawn and clears a route for the b-pawn. The checked continuation reaches …b1=Q. …Kc3 instead lets the knight reorganize and the evaluation falls to a draw.','Identify which pawn blocks your passer, then calculate the promotion race.'),
}

engine=chess.engine.SimpleEngine.popen_uci(str(args.engine))
engine.configure({'Threads':1,'Hash':64})
cachepath=ROOT/'analysis/candidate_cache.json'
candidate_cache=json.loads(cachepath.read_text()) if cachepath.exists() else {}
positions=[]
f=(DATA/'refined/targeted_practice.pgn').open()
while (pgn:=chess.pgn.read_game(f)) is not None:
    b=pgn.board();r=byfen[b.fen()];g=games[r['game_id']];own=r['color']=='white'
    refined=details.get((r['game_id'],int(r['ply'])),{})
    cached=json.loads((args.refined_cache/f"{g['id']}_100000.json").read_text()).get(str(r['ply']),{})
    best=cached.get('best',{});actual=cached.get('actual',{})
    line=best.get('pv') or [m.uci() for m in pgn.mainline_moves()]
    actual_line=actual.get('pv') or [r['played_uci']]
    pid=f"{g['id']}-{r['ply']}"
    if pid not in candidate_cache:
        candidates=[]
        for m in list(b.legal_moves):
            test=b.copy();test.push(m)
            if test.is_game_over():
                outcome=test.outcome();cp=0 if outcome.winner is None else (100000 if outcome.winner==b.turn else -100000)
                mate=1 if outcome and outcome.winner==b.turn else None
                pv=[m]
            else:
                info=engine.analyse(b,chess.engine.Limit(nodes=100000),root_moves=[m])
                sc=info['score'].pov(b.turn);cp=sc.score(mate_score=100000);mate=sc.mate();pv=info.get('pv',[m])
            candidates.append({'uci':m.uci(),'san':b.san(m),'cp':cp,'mate':mate,'line':line_data(b,[x.uci() for x in pv[:7]])})
        candidate_cache[pid]=candidates
        cachepath.write_text(json.dumps(candidate_cache))
    candidates=candidate_cache[pid]
    maxcp=max(x['cp'] for x in candidates)
    exact_mate=any(x['mate']==1 for x in candidates)
    for c in candidates:
        c['drop']=round(max(0,win_proxy(maxcp)-win_proxy(c['cp'])),2)
        c['sound']=(c['mate']==1) if exact_mate else c['drop']<=3
    title,explanation,takeaway=notes.get(g['id'],(pgn.headers['Event'].replace('Missed ','').replace('Allowed ','Preventing '),
        'Compare the move played with the engine continuation. Work through the opponent’s strongest reply before reducing this position to a general rule.',
        'List the opponent’s checks, captures and threats after your intended move.'))
    initial=g['clock']['initial'];inc=g['clock']['increment']
    me=g['players']['white' if own else 'black'];opp=g['players']['black' if own else 'white']
    x=features(b,own,float(r['clock_before']),initial,inc,me.get('rating',0)-opp.get('rating',0),float(r['pre_cp']))
    risk=1/(1+math.exp(-(model['intercept']+sum((a-mu)/s*w for a,mu,s,w in zip(x,model['means'],model['scales'],model['coefficients'])))))
    cat='Endgames' if pgn.headers['Event'].startswith('Endgame') else ('Defense' if pgn.headers['Event'].startswith('Allowed') else 'Tactics')
    positions.append({'id':pid,'gameId':g['id'],'ply':int(r['ply']),'fen':b.fen(),'inCheck':b.is_check(),'title':title,'category':cat,
      'theme':pgn.headers['Event'],'explanation':explanation,'takeaway':takeaway,'color':r['color'],'speed':r['speed'],
      'clock':round(float(r['clock_before']),2),'thinking':round(float(r['thinking_seconds']),2),
      'played':r['played_san'],'playedUci':r['played_uci'],'bestSan':b.san(chess.Move.from_uci(line[0])),
      'best':line_data(b,line),'actual':line_data(b,actual_line),'candidates':candidates,
      'preCp':best.get('cp',int(float(r['pre_cp']))),'postCp':actual.get('cp',int(float(r['post_cp']))),
      'preMate':best.get('mate'),'postMate':actual.get('mate'),
      'opponent':opp.get('user',{}).get('name','Anonymous'),'rating':me.get('rating'),'opponentRating':opp.get('rating'),
      'date':g['createdAt'],'timeControl':f"{initial//60}+{inc}",'opening':r['opening'],'result':float(r['result']),
      'risk':risk,'features':x,'initialClock':initial})
    print('Prepared',pid,flush=True)
engine.quit()

# Held-out examples reproduce the saved model exactly. Use stratified risk bands,
# not a selection of only impressive predictions.
held=[]
testids=set(model['test_game_ids'])
for r in rows:
    if r['game_id'] not in testids:continue
    b=chess.Board(r['fen']);g=games[r['game_id']];own=b.turn
    me=g['players']['white' if own else 'black'];opp=g['players']['black' if own else 'white']
    x=features(b,own,float(r['clock_before']),g['clock']['initial'],g['clock']['increment'],me.get('rating',0)-opp.get('rating',0),float(r['pre_cp']))
    risk=1/(1+math.exp(-(model['intercept']+sum((a-mu)/s*w for a,mu,s,w in zip(x,model['means'],model['scales'],model['coefficients'])))))
    held.append({'id':r['game_id']+'-'+r['ply'],'gameId':r['game_id'],'ply':int(r['ply']),'fen':r['fen'],
      'color':r['color'],'clock':float(r['clock_before']),'features':x,'risk':risk,'actual':int(r['error']),
      'played':r['played_san'],'date':int(r['created_at']),'initialClock':g['clock']['initial']})
ordered=sorted(held,key=lambda r:r['risk']);bins=[]
for k in range(10):
    group=ordered[k*len(ordered)//10:(k+1)*len(ordered)//10]
    bins.append({'n':len(group),'risk':sum(x['risk'] for x in group)/len(group),'errorRate':sum(x['actual'] for x in group)/len(group)})
sample=[ordered[round(i*(len(ordered)-1)/49)] for i in range(50)]
# All 20,537 rows are aggregated, never represented as a live engine in-browser.
rating=[]
for g in games.values():
    if g['variant']!='standard' or g['speed']!='bullet':continue
    me=next(v for v in g['players'].values() if v.get('user',{}).get('id')=='chickenboi2')
    rating.append({'date':g['createdAt'],'rating':me['rating']})
meta={'user':'chickenboi2','window':'Nov 2025 – Nov 2026','downloadedGames':619,'standardGames':618,'moves':20537,'practicePositions':len(positions),
 'bulletGames':589,'blitzGames':29,'refinedPositions':8724,'engine':'Stockfish 19','trainingNodes':12000,'refinedNodes':100000}
(OUT/'data.json').write_text(json.dumps({'meta':meta,'summary':summary,'evaluation':evaluation,'model':model,'positions':positions,'heldout':sample,'riskBins':bins,'rating':rating},separators=(',',':')))
assets=OUT/'assets';assets.mkdir(exist_ok=True)
for symbol in 'PNBRQKpnbrqk':
    piece=chess.Piece.from_symbol(symbol)
    (assets/f"{'w' if piece.color else 'b'}{piece.symbol().lower()}.svg").write_text(chess.svg.piece(piece))
shutil.copy(DATA/'refined/targeted_practice.pgn',OUT/'assets/targeted-practice.pgn')
shutil.copy(DATA/'risk_model.json',OUT/'assets/risk-model.json')
shutil.copy(DATA/'model_evaluation.json',OUT/'assets/model-evaluation.json')
print('Wrote',OUT/'data.json',(OUT/'data.json').stat().st_size,'bytes')
