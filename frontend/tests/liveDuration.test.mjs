import {test} from 'node:test';
import assert from 'node:assert/strict';
import {liveDuration} from '../src/liveDuration.mjs';

test('duration uses observation time, including old observations, not browser time',()=>{
  assert.equal(liveDuration('2026-09-14T10:00:00Z','2026-09-14T10:23:42Z'),'23 min 42 s');
  assert.equal(liveDuration('2026-09-14T12:00:00+02:00','2026-09-14T10:00:00Z'),'0 min 00 s');
});
test('missing, invalid and reversed timestamps do not invent a duration',()=>{
  for(const start of [null,'','invalid','1970-01-01T00:00:00Z','2026-09-14T11:00:00Z']) {
    assert.equal(liveDuration(start,'2026-09-14T10:00:00Z'),'Indisponible');
  }
  assert.equal(liveDuration('2026-09-14T10:00:00Z',null),'Indisponible');
});
