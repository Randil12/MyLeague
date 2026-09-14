import test from 'node:test';
import assert from 'node:assert/strict';
import {laneMean,goalResult} from '../src/laneMetrics.mjs';
test('lane coverage excludes missing observations but preserves zero',()=>{
  assert.deepEqual(laneMean([{v:null},{v:0},{v:100},{v:'bad'},{}],'v'),{count:2,mean:50});
  assert.deepEqual(laneMean([{v:null}],'v'),{count:0,mean:null});
});
test('goals include equality and do not treat missing as success',()=>{
  const rows=[{v:null},{v:0},{v:1},{v:2}];
  assert.deepEqual(goalResult(rows,'v',1,'max'),{evaluated:3,success:2,rate:2/3});
  assert.deepEqual(goalResult(rows,'v',1,'min'),{evaluated:3,success:2,rate:2/3});
  assert.equal(goalResult([{v:null}],'v',0,'max').rate,null);
});
