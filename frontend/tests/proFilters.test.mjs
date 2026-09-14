import test from 'node:test';
import assert from 'node:assert/strict';
import {regionOptions, updateProFilters} from '../src/proFilters.mjs';

const rows = [
  {competition_region:'EMEA', team:'A', tournament_page:'EU'},
  {competition_region:'EMEA', team:'A', tournament_page:'EU'},
  {competition_region:'Korea', team:'B', tournament_page:'KR'},
];
test('teams and tournaments follow competition region without duplicates', () => {
  assert.deepEqual(regionOptions(rows,'team','EMEA'), ['A']);
  assert.deepEqual(regionOptions(rows,'tournament_page','EMEA'), ['EU']);
  assert.deepEqual(regionOptions(rows,'team',''), ['A','B']);
  assert.deepEqual(regionOptions(rows,'team','Unknown'), []);
});
test('region change clears incompatible dependent selections', () => {
  assert.deepEqual(updateProFilters({region:'EMEA',team:'A',tournament:'EU',role:'Top'},'region','Korea'),
    {region:'Korea',team:'',tournament:'',role:'Top'});
});
