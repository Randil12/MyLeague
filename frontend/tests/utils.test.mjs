import {test} from 'node:test';
import assert from 'node:assert/strict';
import {csv, csvCell, num, percent, filterDraft} from '../src/utils.mjs';

test('unknown statistics remain unknown',()=>{
  assert.equal(num(null),'—');assert.equal(percent(null),'—');assert.equal(percent(.525),'52,5 %');
});
test('CSV neutralizes spreadsheet formulas and escapes quotes',()=>{
  assert.equal(csvCell('=1+1'),'"\'=1+1"');
  assert.equal(csvCell('  +1'),'"\'  +1"');
  assert.equal(csvCell('a"b'),'"a""b"');
  assert.equal(csv([]),'');
});
test('draft combines search, role, sample and exclusions',()=>{
  const rows=[{champion_name:'Ahri',role:'MIDDLE',picks:100},{champion_name:'Annie',role:'MIDDLE',picks:3},{champion_name:'Ahri',role:'TOP',picks:20}];
  assert.equal(filterDraft(rows,'ah','MIDDLE',10,[]).length,1);
  assert.equal(filterDraft(rows,'','MIDDLE',10,['Ahri']).length,0);
});
