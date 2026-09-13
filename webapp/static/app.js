const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = (value, digits = 0) => value == null ? '—' : Number(value).toLocaleString('fr-FR', {maximumFractionDigits: typeof digits === 'number' ? digits : 0});
const pct = value => value == null ? '—' : `${number(value * 100, 1)} %`;
const date = value => value ? new Date(value).toLocaleString('fr-FR', {dateStyle:'short',timeStyle:'short'}) : '—';
const roles = {TOP:'Top', JUNGLE:'Jungle', MIDDLE:'Mid', BOTTOM:'ADC', UTILITY:'Support', UNKNOWN:'Non défini'};
const pages = {
  meta:['La méta, en perspective.', 'Les tendances de ton échantillon pour préparer la prochaine victoire.'],
  draft:['Une draft se prépare.', 'Prioriser les champions disponibles, sans oublier la taille de l’échantillon.'],
  training:['Le prochain cap.', 'Croiser le pool de ton joueur avec les priorités du patch.'],
  builds:['Chaque choix compte.', 'Objets et runes observés dans les matchs collectés, champion par champion.'],
  evolution:['Le patch change. Toi aussi.', 'Comparer les résultats avec le patch précédent disponible dans l’entrepôt.'],
  tiers:['À chaque niveau, sa méta.', 'Le niveau correspond au joueur source de la collecte, pas à tous les participants.'],
  supervision:['La confiance se vérifie.', 'Observer les collectes et les alertes avant d’interpréter les résultats.'],
};
let page = 'meta', patch = '', rows = [], meta = [], players = [], generation = 0;
let aborter = new AbortController();
const excluded = new Set();
let exportRows = [];

async function api(resource, params = {}, signal = aborter.signal) {
  const response = await fetch(`/api/${resource}?${new URLSearchParams(params)}`, {signal});
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : 'Impossible de charger les données. Réessaie dans un instant.');
  }
  return response.json();
}
const data = (name, extra = {}) => api(`data/${name}`, {patch, ...extra});
function empty(title, description) {return `<div class="empty"><span class="eyebrow">PAS DE DONNÉES À INVENTER</span><h2>${esc(title)}</h2><p>${esc(description)}</p></div>`;}
function insight(title, description) {return `<aside class="insight"><span class="insight-mark" aria-hidden="true">↗</span><div><strong>${esc(title)}</strong><p>${esc(description)}</p></div></aside>`;}
function badge(value) {const warn = ['faible','à acquérir','failed','critical','partial_success'].includes(value);return `<span class="badge ${warn?'warn':''}">${esc(value)}</span>`;}
function champion(name) {return `<span class="champion"><span class="avatar" aria-hidden="true">${esc((name || '?').slice(0,2).toUpperCase())}</span>${esc(name)}</span>`;}
function winrate(value) {return `<span class="${value == null?'':value>=.5?'positive':'negative'}">${pct(value)}</span>`;}
function delta(value) {return value == null ? '—' : `<span class="${value>=0?'positive':'negative'}">${value>0?'+':''}${number(value*100,2)} pts</span>`;}
function score(value) {return `<span class="meter"><meter min="0" max="100" value="${Number(value)||0}" aria-label="Score sur 100"></meter>${number(value,1)}</span>`;}
function table(title, description, columns, items) {
  if (!items.length) return empty('Aucun résultat pour cette sélection.', 'Essaie un autre patch ou élargis les filtres. Si la source est vide, il faut d’abord exécuter ses collectes puis dbt_transform.');
  return `<section class="panel"><div class="panel-head"><div><h2>${esc(title)}</h2><p>${esc(description)}</p></div><span class="count">${number(items.length)} RÉSULTATS</span></div><div class="table-wrap"><table><thead><tr>${columns.map(c=>`<th scope="col">${esc(c[0])}</th>`).join('')}</tr></thead><tbody>${items.map(r=>`<tr>${columns.map(c=>`<td>${c[2]?c[2](r[c[1]],r):esc(r[c[1]])}</td>`).join('')}</tr>`).join('')}</tbody></table></div></section>`;
}
const option = (value,label=value) => `<option value="${esc(value)}">${esc(label)}</option>`;
function control(label,id,html) {return `<label class="control" for="${id}">${esc(label)}${html}</label>`;}
function commonControls(includeRole = true) {
  return control('Rechercher un champion','search','<input id="search" type="search" placeholder="Nom du champion…">')+
    (includeRole ? control('Rôle','role',`<select id="role">${option('','Tous les rôles')}${Object.entries(roles).map(([v,l])=>option(v,l)).join('')}</select>`) : '')+
    control('Picks minimum','minimum','<input id="minimum" type="number" min="0" max="1000000" value="10">');
}
function filtered(items) {
  const search = ($('#search')?.value || '').toLocaleLowerCase('fr');
  const role = $('#role')?.value || '';
  const min = Math.max(0,Number($('#minimum')?.value)||0);
  return items.filter(r => (r.champion_name || '').toLocaleLowerCase('fr').includes(search) && (!role || r.role === role) && (r.picks ?? 0)>=min);
}
function filters(html) {return `<div class="toolbar">${html}<button class="action secondary" id="export">Exporter CSV ↓</button></div><div id="results"></div>`;}
function bindFilters(render) {
  $('#workspace').querySelectorAll('input:not([type=checkbox]),select').forEach(e=>e.addEventListener('input',render));
  $('#export')?.addEventListener('click',download);
  render();
}
function download() {
  if (!exportRows.length) return;
  const keys = Object.keys(exportRows[0]);
  const cell = value => {
    let s = String(value ?? '');
    if (/^[=+@\-\t\r]/.test(s)) s = "'" + s;
    return `"${s.replace(/"/g,'""')}"`;
  };
  const csv = [keys.map(cell).join(';'),...exportRows.map(row=>keys.map(k=>cell(row[k])).join(';'))].join('\r\n');
  const url = URL.createObjectURL(new Blob(['\uFEFF'+csv], {type:'text/csv;charset=utf-8'}));
  const link = document.createElement('a');link.href=url;link.download=`myleague-${page}-${patch.replace(/[^\w.-]/g,'')}.csv`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function renderMeta() {
  $('#workspace').innerHTML = filters(commonControls()+control('Trier par','sort',`<select id="sort">${option('presence','Présence pick + ban')}${option('winrate','Taux de victoire')}${option('picks','Nombre de picks')}</select>`));
  bindFilters(()=>{
    exportRows = filtered(rows).sort((a,b)=>(b[$('#sort').value]??-1)-(a[$('#sort').value]??-1));
    $('#results').innerHTML = table('Les champions du patch','Clique sur un champion pour explorer ses objets et ses runes.',[
      ['Champion','champion_name',(v)=>`<button class="text-button" data-champion="${esc(v)}">${champion(v)}</button>`],['Rôle','role',v=>esc(roles[v]||v)],['Picks','picks',number],['Winrate','winrate',winrate],['Pickrate','pickrate',pct],['Banrate','banrate',pct],['Présence','presence',pct]],exportRows)+
      insight('Lire le volume avant le pourcentage.', 'Un winrate élevé sur quelques matchs n’est pas une preuve de supériorité. Cet échantillon EUW ne représente pas tous les joueurs de League of Legends.');
    $('#results').querySelectorAll('[data-champion]').forEach(b=>b.onclick=()=>{sessionStorage.setItem('myleague-champion',b.dataset.champion);location.hash='builds';});
  });
}
function renderDraft() {
  $('#workspace').innerHTML = insight('Une shortlist, pas un pilote automatique.', 'Score dbt : présence ladder, performance, présence pro et volume. Les synergies et les matchups de ta composition ne sont pas modélisés.')+
    filters(commonControls()+control('Confiance minimale','confidence',`<select id="confidence">${option('0','Toutes')}${option('1','Moyenne')}${option('2','Élevée')}</select>`)+ '<button class="action secondary" id="reset">Réinitialiser la draft</button>');
  const rank = {'faible':0,'moyenne':1,'élevée':2};
  const render=()=>{
    const candidates=filtered(rows).filter(r=>(rank[r.confidence_level]??0)>=Number($('#confidence').value));
    exportRows=candidates.filter(r=>!excluded.has(r.champion_name));
    $('#results').innerHTML=`<p class="selection-note">${excluded.size} champion(s) marqué(s) indisponible(s). La sélection reste dans cet onglet et n’est pas enregistrée en base.</p>`+
      (exportRows[0]?insight(`À examiner : ${exportRows[0].champion_name}`,`${exportRows[0].recommendation} · ${exportRows[0].picks} picks · confiance ${exportRows[0].confidence_level}.`):'')+
      table('Préparation de draft','Coche les champions déjà choisis ou bannis pour les retirer de la shortlist.',[
        ['Indisponible','champion_name',v=>`<input class="exclude" type="checkbox" data-exclude="${esc(v)}" aria-label="${esc(v)} indisponible" ${excluded.has(v)?'checked':''}>`],
        ['Champion','champion_name',champion],['Rôle','role',v=>esc(roles[v]||v)],['Score','priority_score',score],['Picks','picks',number],['Winrate','winrate',winrate],['Confiance','confidence_level',badge],['Recommandation','recommendation']],candidates);
    $('#results').querySelectorAll('[data-exclude]').forEach(e=>e.onchange=()=>{e.checked?excluded.add(e.dataset.exclude):excluded.delete(e.dataset.exclude);render();});
  };
  $('#reset').onclick=()=>{excluded.clear();render();};bindFilters(render);
}
async function renderTraining(token) {
  players=await data('players');if(token!==generation)return;
  if(!players.length){$('#workspace').innerHTML=empty('Aucun pool exploitable pour ce patch.', 'Ce modèle utilise uniquement le dernier patch et les champions avec au moins 100 picks. Vérifie le patch, le volume collecté et les joueurs enregistrés, puis lance riot_academy_tracking et dbt_transform.');return;}
  $('#workspace').innerHTML=filters(control('Joueur suivi','player',`<select id="player">${players.map(p=>option(p.puuid,p.player_name)).join('')}</select>`));
  let selection=0;
  const load=async()=>{
    const n=++selection;
    $('#results').innerHTML=empty('Chargement du pool…','Lecture des priorités d’entraînement.');
    try{
      const result=await data('training',{player:$('#player').value});
      if(token!==generation||n!==selection)return;
      exportRows=result;
      $('#results').innerHTML=table('Le pool face à la méta','Les priorités suivent les règles du modèle dbt, pas une évaluation humaine du joueur.',[
        ['Champion','champion_name',champion],['Rôle','role',v=>esc(roles[v]||v)],['Priorité entraînement','training_priority',v=>number(v,1)],['État','readiness',badge],['Maîtrise','mastery_level',number],['Points','mastery_points',number],['Dernière partie','last_played_at',date]],result)+insight('Préparer la prochaine séance.', 'La maîtrise mesure l’expérience accumulée sur un champion, pas la performance actuelle. Confronte ces priorités aux VOD et aux objectifs du joueur.');
    }catch(e){if(token===generation&&n===selection)showError(e,'#results');}
  };
  $('#player').onchange=load;$('#export').onclick=download;await load();
}
async function renderBuilds(token) {
  meta=await data('meta');if(token!==generation)return;
  if(!meta.length){$('#workspace').innerHTML=empty('Pas encore de champions à explorer.','Collecte des matchs et exécute dbt_transform.');return;}
  const names=[...new Set(meta.map(r=>r.champion_name))].sort();
  $('#workspace').innerHTML=filters(control('Champion','champion',`<select id="champion">${names.map(n=>option(n)).join('')}</select>`));
  const remembered=sessionStorage.getItem('myleague-champion');if(names.includes(remembered))$('#champion').value=remembered;
  let selection=0;
  const load=async()=>{
    const n=++selection,c=$('#champion').value;sessionStorage.setItem('myleague-champion',c);
    $('#results').innerHTML=empty('Chargement du champion…','Lecture des objets et des runes.');
    try{
      const [items,runes]=await Promise.all([data('items',{champion:c}),data('runes',{champion:c})]);
      if(token!==generation||n!==selection)return;
      const stats=meta.find(r=>r.champion_name===c);
      exportRows=[...items.map(r=>({type:'objet',nom:r.item_name,echantillon:r.times_built,winrate:r.winrate})),...runes.map(r=>({type:'rune',nom:r.keystone_name,echantillon:r.picks,winrate:r.winrate}))];
      $('#results').innerHTML=insight(c,`${number(stats.picks)} picks · ${pct(stats.winrate)} de victoires · KDA ${number(stats.kda,2)} · ${number(stats.avg_cs_per_min,1)} CS/min.`)+
        `<div class="split">${table('Objets observés','Au moins 3 occurrences, triées par fréquence.',[['Objet','item_name'],['Builds','times_built',number],['Winrate','winrate',winrate]],items)}${table('Runes fondamentales','Triées par nombre de picks.',[['Rune','keystone_name'],['Branche','style_name'],['Picks','picks',number],['Winrate','winrate',winrate]],runes)}</div>`+
        insight('Fréquent ne veut pas dire optimal.', 'Ces objets sont observés dans les inventaires de fin de partie. Ils ne décrivent ni un ordre d’achat ni un effet causal sur la victoire.');
    }catch(e){if(token===generation&&n===selection)showError(e,'#results');}
  };
  $('#champion').onchange=load;$('#export').onclick=download;await load();
}
function renderEvolution() {
  $('#workspace').innerHTML=filters(commonControls(false));
  bindFilters(()=>{exportRows=filtered(rows);$('#results').innerHTML=table('Ce qui bouge entre deux patchs','Les écarts de winrate sont exprimés en points de pourcentage.',[
    ['Champion','champion_name',champion],['Patch précédent','previous_patch'],['Picks actuels','picks',number],['Picks précédents','previous_picks',number],['Winrate','winrate',winrate],['Δ winrate','winrate_delta',delta],['Tendance','trend'],['Note officielle','official_change']],exportRows)+insight('Une évolution, pas une causalité.', 'Une hausse peut venir du patch, des joueurs ou de la composition de l’échantillon. Une comparaison nécessite deux patchs alimentés.');});
}
function renderTiers() {
  $('#workspace').innerHTML=filters(commonControls(false)+control('Niveau source','tier',`<select id="tier">${option('','Tous')}${[...new Set(rows.map(r=>r.tier))].sort().map(t=>option(t)).join('')}</select>`));
  bindFilters(()=>{exportRows=filtered(rows).filter(r=>!$('#tier').value||r.tier===$('#tier').value);$('#results').innerHTML=table('Méta par niveau source','Élargir RIOT_EUW_EXTRA_TIERS est nécessaire pour comparer d’autres niveaux.',[['Champion','champion_name',champion],['Niveau','tier'],['Picks','picks',number],['Winrate','winrate',winrate],['Pickrate','pickrate',pct],['KDA','kda',v=>number(v,2)]],exportRows);});
}
async function renderSupervision(token) {
  const results=await Promise.allSettled([data('runs'),data('alerts')]);if(token!==generation)return;
  $('#workspace').innerHTML=results.map((r,i)=>r.status==='rejected'?empty(i?'Alertes indisponibles':'Historique indisponible',r.reason.message):i?
    (r.value.length?table('Alertes actives','Alertes connues du système de monitoring.',[['Pipeline','pipeline_name'],['Type','alert_type'],['Sévérité','severity',badge],['Dernière détection','last_detected_at',date]],r.value):insight('Aucune alerte active enregistrée.', 'Cela ne garantit pas le succès de tous les DAGs : vérifie également Airflow.')):
    table('Dernières collectes','Les tables d’audit ne couvrent pas encore tous les pipelines.',[['Pipeline','pipeline_name'],['Statut','status',badge],['Début','started_at',date],['Fin','ended_at',date],['Lignes écrites','records_written',number],['Erreurs','error_count',number]],r.value)).join('<br>');
}
function showError(error,target='#workspace') {
  if(error.name==='AbortError')return;
  $(target).innerHTML=empty('Les données ne sont pas accessibles.',error.message);
}
async function navigate() {
  aborter.abort();aborter=new AbortController();const token=++generation;
  page=location.hash.slice(1) in pages ? location.hash.slice(1) : 'meta';
  document.title=`MyLeague — ${pages[page][0]}`;
  $('#page-title').textContent=pages[page][0];$('#page-description').textContent=pages[page][1];
  document.querySelectorAll('[data-page]').forEach(a=>{a.classList.toggle('active',a.dataset.page===page);if(a.dataset.page===page)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
  $('#workspace').setAttribute('aria-busy','true');$('#workspace').innerHTML=empty('Chargement de l’analyse…','Lecture des données Gold.');exportRows=[];
  try{
    if(page==='supervision'){await renderSupervision(token);return;}
    if(!patch){$('#workspace').innerHTML=empty('Aucun patch disponible.','Vérifie la connexion à PostgreSQL et lance les collectes puis dbt_transform. Clique ensuite sur Actualiser.');return;}
    if(page==='training'){await renderTraining(token);return;}
    if(page==='builds'){await renderBuilds(token);return;}
    const result=await data(page);if(token!==generation)return;rows=result;
    ({meta:renderMeta,draft:renderDraft,evolution:renderEvolution,tiers:renderTiers})[page]();
  }catch(e){if(token===generation)showError(e);}finally{if(token===generation)$('#workspace').setAttribute('aria-busy','false');}
}
let summaryVersion=0;
async function summary() {
  const version=++summaryVersion,selected=patch;
  $('#metrics').innerHTML='';if(!selected)return;
  try{
    // Independent signal: navigation may change while the patch summary is loading.
    const result=await api('data/summary',{patch:selected},new AbortController().signal);
    if(version!==summaryVersion||patch!==selected)return;
    const s=result[0];if(!s)return;
    const values=[['Matchs analysés',number(s.total_matches),'Classé solo · matchs retenus par dbt'],['Durée moyenne',`${number(s.avg_duration_min,1)} min`,'Sur les matchs de ce patch'],['Patch étudié',selected,'Échantillon de ton entrepôt'],['Dernier match',date(s.last_game_at),'Heure de début · pas l’heure du build']];
    $('#metrics').innerHTML=values.map(([l,v,n])=>`<article class="metric"><span class="metric-label">${esc(l)}</span><strong class="metric-value">${esc(v)}</strong><span class="metric-note">${esc(n)}</span></article>`).join('');
  }catch(e){if(version===summaryVersion)$('#status').innerHTML=`<div class="notice">Résumé du patch indisponible. ${esc(e.message)}</div>`;}
}
async function initialize() {
  $('#refresh').disabled=true;$('#status').innerHTML='';
  try{
    const available=await api('patches',{},new AbortController().signal);
    if(!available.some(r=>r.patch===patch))patch=available[0]?.patch||'';
    $('#patch').innerHTML=available.length?available.map(r=>option(r.patch)).join(''):option('','Aucun patch');
    $('#patch').value=patch;$('#patch').disabled=!available.length;
    $('#updated').textContent=`Consulté à ${new Date().toLocaleTimeString('fr-FR')} · entrepôt Gold`;
  }catch(e){patch='';$('#patch').innerHTML=option('','Indisponible');$('#patch').disabled=true;$('#status').innerHTML=`<div class="notice">${esc(e.message)} Aucune donnée de démonstration n’est affichée.</div>`;}
  finally{$('#refresh').disabled=false;}
  await Promise.all([summary(),navigate()]);
}
$('#patch').onchange=()=>{patch=$('#patch').value;excluded.clear();$('#status').innerHTML='';summary();navigate();};
$('#refresh').onclick=initialize;
window.addEventListener('hashchange',navigate);
initialize();
