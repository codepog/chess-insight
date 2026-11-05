'use strict';
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.join(__dirname,'..','dist');
const d=JSON.parse(fs.readFileSync(path.join(root,'data.json'),'utf8'));
assert.equal(d.positions.length,20);
assert.equal(d.transfer.length,6);
const transferGames=new Set(d.transfer.map(p=>p.gameId));
assert.equal(transferGames.size,6);
assert.equal(d.positions.some(p=>transferGames.has(p.gameId)),false);
const ids=['training_game_ids','validation_game_ids','test_game_ids'].map(k=>new Set(d.model[k]));
assert.deepEqual(ids.map(s=>s.size),[353,118,118]);
for(let i=0;i<ids.length;i++)for(let j=i+1;j<ids.length;j++)assert.equal([...ids[i]].some(x=>ids[j].has(x)),false);
let candidates=0;
for(const p of [...d.positions,...d.transfer]){
  assert(p.candidates.some(c=>c.sound));
  assert.equal(new Set(p.candidates.map(c=>c.uci)).size,p.candidates.length);
  assert(p.candidates.find(c=>c.san===p.bestSan).sound);
  assert.equal(p.candidates.find(c=>c.uci===p.playedUci).sound,false);
  for(const branch of [p.best,p.actual,...p.candidates.map(c=>c.line)])assert.equal(branch[0].fen,p.fen);
  candidates+=p.candidates.length;
}
assert.equal(candidates,701);
for(const p of d.heldout){
  assert(ids[2].has(p.gameId));
  assert.equal(p.features.length,d.model.coefficients.length);
  const z=d.model.intercept+p.features.reduce((sum,v,i)=>sum+(v-d.model.means[i])/d.model.scales[i]*d.model.coefficients[i],0);
  const score=1/(1+Math.exp(-z));
  assert(Math.abs(score-p.risk)<1e-12);
}
assert.equal(d.riskBins.reduce((n,b)=>n+b.n,0),d.evaluation.test.n);
assert(Math.abs(d.riskBins.reduce((n,b)=>n+b.errorRate*b.n,0)-d.evaluation.test.errors)<1e-8);
for(const piece of ['wp','wn','wb','wr','wq','wk','bp','bn','bb','br','bq','bk'])assert(fs.existsSync(path.join(root,'assets',piece+'.svg')));
for(const file of ['index.html','styles.css','app.js','assets/risk-model.json','assets/model-evaluation.json','assets/targeted-practice.pgn'])assert(fs.existsSync(path.join(root,file)));
console.log('PASS: 26 practice positions (20 original + 6 additional games), 701 candidate moves, grading, 50 fitted predictions, 353/118/118 disjoint split, full test aggregates and assets.');
