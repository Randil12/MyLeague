import test from 'node:test';
import assert from 'node:assert/strict';
import {resolvePlayerPatch} from '../src/playerScope.mjs';

test('player statistics default to all patches; explicit filter stays scoped',()=>{
  const scope='coaching:Individuel:Tacos';
  assert.equal(resolvePlayerPatch({scope:'',patch:'__all__'},scope),'');
  const selection={scope,patch:'16.18'};
  assert.equal(resolvePlayerPatch(selection,scope),'16.18');
  assert.equal(resolvePlayerPatch(selection,'coaching:Individuel:Other'), '');
  assert.equal(resolvePlayerPatch(selection,'training:Tacos'), '');
  assert.equal(resolvePlayerPatch({scope,patch:'__all__'},scope),'');
});
