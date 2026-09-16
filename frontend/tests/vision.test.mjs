import test from 'node:test';
import assert from 'node:assert/strict';
import {numericValues, laneMean} from '../src/laneMetrics.mjs';

test('vision averages exclude absent values but retain genuine zeroes',()=>{
  for(const key of ['wards_placed','control_wards_placed','control_wards_bought']) {
    const rows=[{[key]:12},{[key]:0},{[key]:null},{}];
    assert.deepEqual(numericValues(rows,key),[12,0]);
    assert.deepEqual(laneMean(rows,key),{count:2,mean:6});
    assert.deepEqual(laneMean([{}, {[key]:null}],key),{count:0,mean:null});
  }
});
