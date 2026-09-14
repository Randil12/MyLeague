import {useState} from 'react';
import {useData} from './api';
import Champion from './Champion';
import {num,percent} from './utils.mjs';
import {laneMean,goalResult} from './laneMetrics.mjs';

const metrics=[['damage_min','Dégâts champions / min'],['cs_min','CS / min'],['gold_15','Gold@15'],['gd_15','GD@15'],['csd_15','CSD@15'],['xpd_15','XPD@15'],['solo_kills','Solo kills / partie (Riot)'],['solo_kills_15','Kills sans assist avant 15 min'],['solo_deaths_15','Morts sans assist avant 15 min']];
const objectives=[['damage_min','Dégâts champions / min : minimum','min'],['cs_min','CS / min : minimum','min'],['gd_15','Or : atteindre une différence minimale','min'],['csd_15','Farm : atteindre une différence minimale','min'],['solo_kills_15','Kills sans assist : atteindre un minimum','min'],['solo_deaths_15','Morts sans assist : ne pas dépasser un maximum','max']];

export default function LaneAnalysis({player,patch,revision}:{player:string;patch:string;revision:number}){
  const result=useData('/api/lane',{player,patch},revision,Boolean(player&&patch));
  const [role,setRole]=useState('');const [champion,setChampion]=useState('');
  const [objective,setObjective]=useState('gd_15');const [threshold,setThreshold]=useState(0);
  const [since,setSince]=useState('');
  const rows=result.rows.filter(r=>(!role||r.role===role)&&(!champion||r.champion_name===champion)&&(!since||String(r.game_started_at).slice(0,10)>=since));
  const goal=goalResult(rows,objective,threshold,objectives.find(o=>o[0]===objective)![2]);
  const evaluable=rows.filter(r=>r.gd_15!=null);const ahead=evaluable.filter(r=>Number(r.gd_15)>0);
  if(result.disabled)return null;
  return <section className="panel"><div className="panel-head"><div><h2>Lane à 15 minutes et objectifs de séance</h2><p>SoloQ · patch {patch} · jusqu’aux 200 dernières parties collectées de ce patch.</p></div></div>
    {result.loading?<p role="status">Lecture des timelines…</p>:result.error?<p role="alert">{result.error} Vérifie le build du modèle gold_player_lane dans dbt_transform.</p>:<>
      <div className="filters"><label className="field">Rôle<select value={role} onChange={e=>setRole(e.target.value)}><option value="">Tous</option>{[...new Set(result.rows.map(r=>String(r.role||'')).filter(Boolean))].sort().map(r=><option key={r}>{r}</option>)}</select></label><label className="field">Champion<select value={champion} onChange={e=>setChampion(e.target.value)}><option value="">Tous</option>{[...new Set(result.rows.map(r=>String(r.champion_name)))].sort().map(c=><option key={c}>{c}</option>)}</select></label><label className="field">Depuis le (UTC)<input type="date" value={since} onChange={e=>setSince(e.target.value)}/></label></div>
      {!rows.length?<p className="empty">Aucune partie pour ce périmètre. Attends la collecte puis le build Gold, ou change les filtres.</p>:<>
        <div className="stats">{metrics.map(([key,label])=>{const m=laneMean(rows,key);return <article className="stat" key={key}><span>{label}</span><strong>{num(m.mean,2)}</strong><small>{m.count} / {rows.length} parties renseignées</small></article>;})}<article className="stat"><span>Fréquence d’avance à 15 min</span><strong>{percent(evaluable.length?ahead.length/evaluable.length:null)}</strong><small>{ahead.length} / {evaluable.length} parties évaluables</small></article><article className="stat"><span>Victoires avec une avance à 15 min</span><strong>{percent(ahead.length?ahead.filter(r=>r.win===true).length/ahead.length:null)}</strong><small>{ahead.length} parties · association, pas causalité</small></article></div>
        <div className="filters"><label className="field">Objectif de séance<select value={objective} onChange={e=>{setObjective(e.target.value);setThreshold(0);}}>{objectives.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label><label className="field">Seuil<input type="number" step="any" min={-10000} max={10000} value={threshold} onChange={e=>setThreshold(Math.max(-10000,Math.min(10000,Number(e.target.value)||0)))}/></label></div>
        <p><strong>Objectif atteint : {percent(goal.rate)}</strong> · {goal.success} / {goal.evaluated} parties évaluables ; {rows.length-goal.evaluated} exclues faute de données.</p><p>Réglage de cette séance, non enregistré. Les filtres ci-dessus définissent les parties évaluées. Un résultat sur moins de cinq parties ne permet pas de conclure.</p>
        <div className="table-scroll"><table><thead><tr><th>Partie (UTC)</th><th>Champion</th><th>Adversaire au rôle</th><th>Dégâts champions / min</th><th>CS / min</th><th>Gold@15</th><th>GD@15</th><th>CSD@15</th><th>XPD@15</th><th>Kills sans assist &lt;15</th><th>Morts sans assist &lt;15</th><th>Observation réelle</th></tr></thead><tbody>{rows.map(r=><tr key={String(r.match_id)}><td>{String(r.game_started_at).slice(0,10)}<small className="metric-coverage">{String(r.match_id)}</small></td><td><Champion name={String(r.champion_name)}/></td><td>{r.opponent?<Champion name={String(r.opponent)}/>:'—'}</td>{['damage_min','cs_min','gold_15','gd_15','csd_15','xpd_15','solo_kills_15','solo_deaths_15'].map(k=><td key={k}>{num(r[k],k==='damage_min'||k==='cs_min'?2:0)}</td>)}<td>{r.observed_at_ms==null?'—':`${num(Number(r.observed_at_ms)/1000,3)} s`}</td></tr>)}</tbody></table></div>
      </>}
      <p className="note">Dégâts/min et CS/min : moyennes par partie sur la durée totale, indépendantes des timelines. CS = sbires + monstres. Gold = or total acquis ; Δ = joueur moins adversaire au même rôle déclaré (les lane swaps restent une limite). Observation la plus proche de 15:00, tolérance ±5 s. Pas d’estimation pour les parties trop courtes. Kills sans assist = événements sans assistance enregistrée, pas une preuve de duel isolé ; les exécutions sans tueur joueur sont exclues. Une timeline incomplète reste indisponible.</p>
    </>}
  </section>;
}
