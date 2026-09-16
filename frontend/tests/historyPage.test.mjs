import test from 'node:test';
import assert from 'node:assert/strict';
import {historyPage} from '../src/historyPage.mjs';

test('history shows 20 games and uses the extra row only for next-page detection',()=>{
  const rows=Array.from({length:21},(_,match_id)=>({match_id}));
  assert.deepEqual(historyPage(rows),{rows:rows.slice(0,20),hasNext:true});
  assert.equal(historyPage(rows.slice(0,20)).hasNext,false);
  assert.equal(historyPage(rows.slice(0,8)).rows.length,8);
  assert.deepEqual(historyPage([]),{rows:[],hasNext:false});
});
