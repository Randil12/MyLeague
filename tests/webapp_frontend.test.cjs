// Pure rendering/formatting tests. No browser or database required.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = readFileSync(path.join(__dirname, '../webapp/static/app.js'), 'utf8');
const elements = {};
const context = vm.createContext({
  document: {querySelector: key => elements[key] ?? null},
  AbortController, URLSearchParams, console, setTimeout,
});
// Skip event registration and initial network requests, retain all production functions.
vm.runInContext(source.slice(0, source.indexOf("$('#patch').onchange=")), context);
const run = code => vm.runInContext(code, context);

test('escaping prevents stored HTML injection', () => {
  assert.equal(run(`esc('<img src=x onerror="alert(1)">')`), '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
});
test('null metrics are unknown, not zero', () => {
  assert.equal(run('pct(null)'), '—');
  assert.equal(run('number(null)'), '—');
  assert.equal(run('delta(null)'), '—');
});
test('number formatter accepts the row supplied by table renderer', () => {
  assert.equal(run('number(250, {picks:250})'), '250');
  assert.ok(run(`table('Meta','',[['Picks','picks',number]],[{picks:250}])`).includes('250'));
});
test('percentages and deltas have correct units', () => {
  assert.equal(run('pct(.52)'), '52 %');
  assert.ok(run('delta(.015)').includes('+1,5 pts'));
});
test('filters combine champion, role and sample threshold', () => {
  elements['#search'] = {value:'ah'};
  elements['#role'] = {value:'MIDDLE'};
  elements['#minimum'] = {value:'10'};
  assert.equal(run(`filtered([
    {champion_name:'Ahri',role:'MIDDLE',picks:50},
    {champion_name:'Ahri',role:'TOP',picks:50},
    {champion_name:'Ahri',role:'MIDDLE',picks:2},
    {champion_name:'Annie',role:'MIDDLE',picks:50}
  ]).length`), 1);
});
test('empty table explicitly communicates absence of data', () => {
  const html = run(`table('Meta','',[],[])`);
  assert.ok(html.includes('Aucun résultat'));
  assert.ok(!html.includes('<table>'));
});

test('meta, draft, evolution and tiers render real-shaped rows', () => {
  for (const key of ['#workspace','#results','#export','#reset']) {
    elements[key] = {innerHTML:'',querySelectorAll:()=>[],addEventListener:()=>{}};
  }
  elements['#search'] = {value:''};
  elements['#role'] = {value:''};
  elements['#minimum'] = {value:'0'};
  elements['#sort'] = {value:'presence'};
  elements['#confidence'] = {value:'0'};
  elements['#tier'] = {value:''};
  run(`rows=[{champion_name:'Ahri', role:'MIDDLE', picks:250, winrate:.52,
    presence:.3, priority_score:50, confidence_level:'élevée',
    recommendation:'Pick de rotation', previous_patch:'16.1',
    previous_picks:200, winrate_delta:.02, tier:'MASTER'}]`);
  for (const renderer of ['renderMeta','renderDraft','renderEvolution','renderTiers']) {
    run(`${renderer}()`);
    assert.ok(elements['#results'].innerHTML.includes('Ahri'), renderer);
    assert.ok(elements['#results'].innerHTML.includes('250'), renderer);
  }
});

test('draft exclusion removes a champion from exportable shortlist', () => {
  run(`excluded.add('Ahri');renderDraft()`);
  assert.equal(run('exportRows.length'), 0);
  run('excluded.clear()');
});
