import {useState} from 'react';
import {useData} from './api';
import Champion from './Champion';
import {num,percent} from './utils.mjs';
import {laneMean,formatLaneMetric} from './laneMetrics.mjs';

const metrics=[['damage_min','Dégâts champions / min'],['cs_min','CS / min'],['gold_15','Gold@15'],['gd_15','GD@15'],['csd_15','CSD@15'],['xpd_15','XPD@15'],['solo_kills','Solo kills / partie (Riot)'],['solo_kills_15','Kills sans assist avant 15 min'],['solo_deaths_15','Morts sans assist avant 15 min']];

export default function LaneAnalysis({player,patch,revision}:{player:string;patch:string;revision:number}){
  const result=useData('/api/lane',{player,patch},revision,Boolean(player));
  const [role,setRole]=useState('');const [champion,setChampion]=useState('');
  const [since,setSince]=useState('');const [page,setPage]=useState(0);
  const rows=result.rows.filter(r=>(!role||r.role===role)&&(!champion||r.champion_name===champion)&&(!since||String(r.game_started_at).slice(0,10)>=since));
  const pages=Math.max(1,Math.ceil(rows.length/50));const currentPage=Math.min(page,pages-1);
  const evaluable=rows.filter(r=>r.gd_15!=null);const ahead=evaluable.filter(r=>Number(r.gd_15)>0);
  if(result.disabled)return null;
  return <section className="panel"><div className="panel-head"><div><h2>Diagnostic individuel et lane à 15 minutes</h2><p>SoloQ · {patch?`patch ${patch}`:'tous les patches'} · {rows.length} parties analysées.</p></div></div>
    {result.loading?<p role="status">Lecture des timelines…</p>:result.error?<p role="alert">{result.error} Vérifie le build du modèle gold_player_lane dans dbt_transform.</p>:<>
      <div className="filters"><label className="field">Rôle<select value={role} onChange={e=>{setRole(e.target.value);setPage(0);}}><option value="">Tous</option>{[...new Set(result.rows.map(r=>String(r.role||'')).filter(Boolean))].sort().map(r=><option key={r}>{r}</option>)}</select></label><label className="field">Champion<select value={champion} onChange={e=>{setChampion(e.target.value);setPage(0);}}><option value="">Tous</option>{[...new Set(result.rows.map(r=>String(r.champion_name)))].sort().map(c=><option key={c}>{c}</option>)}</select></label><label className="field">Depuis le (UTC)<input type="date" value={since} onChange={e=>{setSince(e.target.value);setPage(0);}}/></label></div>
      {!rows.length?<p className="empty">Aucune partie pour ce périmètre. Attends la collecte puis le build Gold, ou change les filtres.</p>:<>
        <div className="stats">{metrics.map(([key,label])=>{const m=laneMean(rows,key);return <article className="stat" key={key}><span>{label}</span><strong>{formatLaneMetric(key,m.mean,2)}</strong><small>{m.count} / {rows.length} parties renseignées</small></article>;})}<article className="stat"><span>Fréquence d’avance à 15 min</span><strong>{percent(evaluable.length?ahead.length/evaluable.length:null)}</strong><small>{ahead.length} / {evaluable.length} parties évaluables</small></article><article className="stat"><span>Victoires avec une avance à 15 min</span><strong>{percent(ahead.length?ahead.filter(r=>r.win===true).length/ahead.length:null)}</strong><small>{ahead.length} parties · association, pas causalité</small></article></div>
        <div className="table-scroll"><table><thead><tr><th>Partie (UTC)</th><th>Champion</th><th>Adversaire au rôle</th><th>Dégâts champions / min</th><th>CS / min</th><th>Gold@15</th><th>GD@15</th><th>CSD@15</th><th>XPD@15</th><th>Kills sans assist &lt;15</th><th>Morts sans assist &lt;15</th><th>Observation réelle</th></tr></thead><tbody>{rows.slice(currentPage*50,(currentPage+1)*50).map(r=><tr key={String(r.match_id)}><td>{String(r.game_started_at).slice(0,10)}<small className="metric-coverage">{String(r.match_id)}</small></td><td><Champion name={String(r.champion_name)}/></td><td>{r.opponent?<Champion name={String(r.opponent)}/>:'—'}</td>{['damage_min','cs_min','gold_15','gd_15','csd_15','xpd_15','solo_kills_15','solo_deaths_15'].map(k=><td key={k}>{formatLaneMetric(k,r[k],k==='damage_min'||k==='cs_min'?2:0)}</td>)}<td>{r.observed_at_ms==null?'—':`${num(Number(r.observed_at_ms)/1000,3)} s`}</td></tr>)}</tbody></table></div><div className="filters"><button className="quiet" disabled={currentPage===0} onClick={()=>setPage(currentPage-1)}>Précédent</button><span>Page {currentPage+1} / {pages} · statistiques sur les {rows.length} parties</span><button className="quiet" disabled={currentPage+1>=pages} onClick={()=>setPage(currentPage+1)}>Suivant</button></div>
      </>}
      <p className="note">Moyennes sur les données renseignées. Δ = joueur moins adversaire au même rôle ; observation à 15 min ±5 s. Parties trop courtes ou timelines incomplètes : données indisponibles. Un kill sans assist ne prouve pas un duel isolé.</p>
    </>}
  </section>;
}
