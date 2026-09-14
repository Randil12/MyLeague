import test from 'node:test';
import assert from 'node:assert/strict';
import {topChampions,filterLeaderboard} from '../src/leaderboardChampions.mjs';
test('top champions preserves slots, missing coverage and original ladder positions',()=>{
  const rows=[{player_name:'A',position:1,champion_1:'Azir',champion_1_games:3},
    {player_name:'B',position:2,champion_1:'Ahri',champion_1_games:10,champion_2:'Azir',champion_2_games:5},
    {player_name:'C',position:3}];
  assert.deepEqual(topChampions(rows[2]),[]);
  assert.equal(topChampions(rows[1])[1].name,'Azir');
  assert.deepEqual(filterLeaderboard(rows,'','Azir','champion').map(r=>r.position),[2,1]);
  assert.deepEqual(filterLeaderboard(rows,'','Azir','lp').map(r=>r.position),[1,2]);
  assert.equal(filterLeaderboard(rows,'b','Azir','lp').length,1);
  assert.equal(filterLeaderboard(rows,'','Garen','lp').length,0);
  assert.deepEqual(rows.map(r=>r.position),[1,2,3]);
});
