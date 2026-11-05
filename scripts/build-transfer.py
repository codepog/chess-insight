from pathlib import Path
import sys,json,math,argparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'analysis'))
ap=argparse.ArgumentParser()
ap.add_argument('--engine',type=Path,required=True)
args=ap.parse_args()
from analyze_history import win_proxy
import chess,chess.engine
BASE=ROOT/'analysis/data'
TARGET=ROOT/'dist/data.json'
d=json.loads(TARGET.read_text());rows=json.loads((BASE/'refined/endgame_decisions.json').read_text())
games={g['id']:g for g in map(json.loads,(BASE/'games.ndjson').read_text().splitlines())}
selection=[('tp1Oo8NB',79),('w7DdconG',103),('zUZDdOAg',78),('ZbdaIzSk',97),('LGcTyMNB',84),('VQU6WPIy',99)]
notes=[
 ('Keep the rook against the passer','Rc2 puts the rook on the second rank, against the advanced g-pawn. Rc5+ lets Black bring the king to g4 and continue with …g2 in the checked line.','Check which square your rook must control to stop the pawn.'),
 ('Keep the rook active','Rd7 threatens the a7-pawn and keeps the rook active. Ra1 lets Black consolidate with …Rc7 in the checked line.','Compare an active rook move with a retreat before choosing defense.'),
 ('Use the forcing resource','…Re3+ makes White respond to a check. The historical …Ke7 lets White take the d4-pawn with Rxd4.','Look for a useful check before allowing the opponent to take a pawn.'),
 ('Reposition before the pawns advance','Kh3 is the checked king move before Black pushes …d4. The historical h4 commits a pawn while leaving the king on g4. Compare the checked continuations before pushing.','Consider a king move alongside a pawn push.'),
 ('Check before the pawn advances','…Rb8+ forces the white king to respond. After the historical …Kd6, White can push b5 and gain the initiative.','Compare a forcing rook check before allowing a passed-pawn advance.'),
 ('Give the rook a target','Rh4 targets the d4-pawn; the checked line continues …Rf2, Rxd4. Ra3 instead lets Black play …Ra5 and pressure the a4-pawn.','Choose the rook’s job before choosing its square.'),
]
def line(board,ucis):
 b=board.copy();s=[{'fen':b.fen(),'san':'Position','uci':None}]
 for u in ucis[:10]:
  m=chess.Move.from_uci(u)
  if m not in b.legal_moves:break
  san=b.san(m);b.push(m);s.append({'fen':b.fen(),'san':san,'uci':u})
 return s
engine=chess.engine.SimpleEngine.popen_uci(str(args.engine))
engine.configure({'Threads':1,'Hash':64})
out=[]
for (gid,ply),note in zip(selection,notes):
 r=next(r for r in rows if r['game_id']==gid and int(r['ply'])==ply);b=chess.Board(r['fen']);g=games[gid]
 candidates=[]
 for m in b.legal_moves:
  info=engine.analyse(b,chess.engine.Limit(nodes=100000),root_moves=[m]);sc=info['score'].pov(b.turn)
  candidates.append({'uci':m.uci(),'san':b.san(m),'cp':sc.score(mate_score=100000),'mate':sc.mate(),'line':line(b,[x.uci() for x in info.get('pv',[m])])})
 maximum=max(c['cp'] for c in candidates);mate=any(c['mate']==1 for c in candidates)
 for c in candidates:
  c['drop']=round(max(0,win_proxy(maximum)-win_proxy(c['cp'])),2);c['sound']=c['mate']==1 if mate else c['drop']<=3
 best=max(candidates,key=lambda c:c['cp']);actual=next(c for c in candidates if c['uci']==r['played_uci'])
 own=b.turn;me=g['players']['white' if own else 'black'];opp=g['players']['black' if own else 'white']
 out.append({'id':f'{gid}-{ply}','gameId':gid,'ply':ply,'fen':b.fen(),'color':r['color'],'title':note[0],'explanation':note[1],'takeaway':note[2],
 'theme':'Endgame decision in single rook versus single rook','category':'Endgames','speed':r['speed'],'clock':r['clock_before'],'played':r['played_san'],'playedUci':r['played_uci'],
 'bestSan':best['san'],'best':best['line'],'actual':actual['line'],'preCp':best['cp'],'postCp':actual['cp'],'preMate':best['mate'],'postMate':actual['mate'],
 'candidates':candidates,'opponent':opp.get('user',{}).get('name','Anonymous'),'rating':me.get('rating'),'opponentRating':opp.get('rating'),
 'date':g['createdAt'],'timeControl':f"{g['clock']['initial']//60}+{g['clock']['increment']}",'result':r['result']})
 print(gid,'best',best['san'],'historical',actual['san'],'sound alternatives',[c['san'] for c in candidates if c['sound']],flush=True)
engine.quit()
assert not {p['gameId'] for p in out}&{p['gameId'] for p in d['positions']}
d['transfer']=out;d['meta']['transferPositions']=len(out)
TARGET.write_text(json.dumps(d,separators=(',',':')))
