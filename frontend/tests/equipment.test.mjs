import {test} from 'node:test';
import assert from 'node:assert/strict';
import {itemIcon,runeIcon,normalizeEquipment,splitEquipment} from '../src/equipmentAssets.mjs';

test('item assets use validated identifiers on official CDN',()=>{
  assert.equal(itemIcon('16.18.1',1001),'https://ddragon.leagueoflegends.com/cdn/16.18.1/img/item/1001.png');
  for(const id of [0,null,'../x','https://example.com'])assert.equal(itemIcon('16.18.1',id),'');
  assert.equal(itemIcon('../bad',1001),'');
});
test('rune assets use their declared path, not an invented numeric filename',()=>{
  assert.equal(runeIcon('perk-images/Styles/Precision/Conqueror/Conqueror.png'),'https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles/Precision/Conqueror/Conqueror.png');
  for(const path of ['../x.png','https://example.com/x.png','perk-images/../x.png',null])assert.equal(runeIcon(path),'');
});
test('names are normalized and unknown source text remains intact',()=>{
  assert.equal(normalizeEquipment('Électrocution'),'electrocution');
  assert.deepEqual(splitEquipment('Infinity Edge;Unknown item|Boots'),['Infinity Edge','Unknown item','Boots']);
  assert.deepEqual(splitEquipment(''),[]);
});
