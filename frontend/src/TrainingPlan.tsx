import {useState} from 'react';
import {useData, type Row} from './api';
import {formatLaneMetric} from './laneMetrics.mjs';
import {percent} from './utils.mjs';

const metrics:Record<string,string>={gd_15:'GD@15 minimum',xpd_15:'XPD@15 minimum',cs_min:'CS/min minimum',damage_min:'Dégâts champions/min minimum',solo_deaths_15:'Morts sans assist avant 15 min : maximum'};
const today=()=>new Date().toISOString().slice(0,10);
export default function TrainingPlan({player,revision}:{player:string;revision:number}) {
  const [refresh,setRefresh]=useState(0);
  const result=useData('/api/training',{player},revision+refresh,Boolean(player));
  const champions=useData('/api/champions',{},revision);
  const [title,setTitle]=useState('');const [metric,setMetric]=useState('gd_15');
  const [threshold,setThreshold]=useState('0');const [champion,setChampion]=useState('');const [role,setRole]=useState('');
  const [starts,setStarts]=useState(today);const [ends,setEnds]=useState(today);
  const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  async function mutate(data:Record<string,unknown>) {
    setBusy(true);setError('');
    try {
      const response=await fetch('/api/training',{method:'POST',headers:{'Content-Type':'application/json','X-MyLeague-Action':'roster'},body:JSON.stringify({...data,player})});
      const body=await response.json();if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'Enregistrement impossible');
      setRefresh(v=>v+1);return true;
    } catch(e){setError(e instanceof Error?e.message:'Service indisponible');return false;}
    finally {setBusy(false);}
  }
  return <section className="panel"><div className="panel-head"><div><h2>Plan de progression enregistré</h2><p>Objectifs et séances partagés par le staff pour ce joueur. Périodes UTC, tous patches confondus : le filtre global de patch ne limite pas le plan.</p></div></div>
    <form onSubmit={async e=>{e.preventDefault();if(await mutate({action:'create',title,metric,threshold:Number(threshold),champion,role,starts_on:starts,ends_on:ends}))setTitle('');}}>
      <div className="filters"><label className="field">Objectif<input required maxLength={160} value={title} onChange={e=>setTitle(e.target.value)} placeholder="Ex. Stabiliser mon début de lane"/></label>
      <label className="field">Indicateur<select value={metric} onChange={e=>{setMetric(e.target.value);setThreshold('0');}}>{Object.entries(metrics).map(([key,label])=><option value={key} key={key}>{label}</option>)}</select></label>
      <label className="field">Seuil<input type="number" required step="any" min={metric==='gd_15'||metric==='xpd_15'?-100000:0} max={100000} value={threshold} onChange={e=>setThreshold(e.target.value)}/></label>
      <label className="field">Champion<select value={champion} onChange={e=>setChampion(e.target.value)}><option value="">Tous</option>{champions.rows.map(c=><option key={String(c.champion_key)}>{String(c.name)}</option>)}</select></label>
      <label className="field">Rôle<select value={role} onChange={e=>setRole(e.target.value)}><option value="">Tous</option>{['TOP','JUNGLE','MIDDLE','BOTTOM','UTILITY'].map(r=><option key={r}>{r}</option>)}</select></label>
      <label className="field">Début (UTC)<input required type="date" value={starts} onChange={e=>setStarts(e.target.value)}/></label><label className="field">Fin incluse (UTC)<input required type="date" min={starts} value={ends} onChange={e=>setEnds(e.target.value)}/></label>
      <button disabled={busy||!player} type="submit">Enregistrer l’objectif</button></div>
    </form>
    {(error||result.error)&&<p role="alert" className="error-banner">{error||result.error}</p>}
    {result.loading?<p role="status">Chargement du plan…</p>:!result.error&&!result.rows.length?<p>Aucun objectif enregistré. Choisis un axe de travail ci-dessus.</p>:null}
    {result.rows.map(goal=><Goal key={String(goal.id)} goal={goal} busy={busy} mutate={mutate}/>)}
    <p className="note">Progression recalculée sur les parties collectées de la période après le build Gold. Les valeurs absentes sont exclues, pas remplacées par zéro. « Terminé » est une décision du coach, pas une validation automatique du niveau du joueur.</p>
  </section>;
}

function Goal({goal,busy,mutate}:{goal:Row;busy:boolean;mutate:(data:Record<string,unknown>)=>Promise<boolean>}) {
  const [notes,setNotes]=useState('');const [date,setDate]=useState(String(goal.starts_on));
  const evaluated=Number(goal.evaluated);const sessions=goal.sessions as unknown as {id:number;played_on:string;notes:string}[];
  return <article className="pro-game"><div className="panel-head"><h3>{String(goal.title)}</h3><span className="badge">{goal.status==='active'?'En cours':goal.status==='completed'?'Terminé':'Archivé'}</span></div>
    <p>{metrics[String(goal.metric)]} : {formatLaneMetric(String(goal.metric),goal.threshold,2)} · {String(goal.champion||'Tous champions')} · {String(goal.role||'Tous rôles')} · {String(goal.starts_on)} → {String(goal.ends_on)}</p>
    <p>Moyenne observée : <strong>{formatLaneMetric(String(goal.metric),goal.mean,2)}</strong> · Seuil atteint : <strong>{percent(evaluated?Number(goal.success)/evaluated:null)}</strong> ({String(goal.success)}/{evaluated} parties évaluables ; {Number(goal.games)-evaluated} sans mesure).</p>
    {evaluated<5&&<p>Moins de cinq parties évaluables : données insuffisantes pour conclure.</p>}
    <div className="filters">{[['active','Reprendre'],['completed','Marquer terminé'],['archived','Archiver']].filter(([s])=>s!==goal.status).map(([status,label])=><button className="quiet" disabled={busy} key={status} onClick={()=>mutate({action:'status',id:Number(goal.id),status})}>{label}</button>)}</div>
    {goal.status==='active'&&<form onSubmit={async e=>{e.preventDefault();if(await mutate({action:'session',id:Number(goal.id),played_on:date,notes}))setNotes('');}}><div className="filters"><label className="field">Date de séance (UTC)<input required type="date" min={String(goal.starts_on)} max={String(goal.ends_on)} value={date} onChange={e=>setDate(e.target.value)}/></label><label className="field">Bilan de séance<textarea required maxLength={2000} value={notes} onChange={e=>setNotes(e.target.value)} placeholder="Exercice réalisé, VOD revue, observations…"/></label><button disabled={busy} type="submit">Enregistrer la séance</button></div></form>}
    {sessions?.map(s=><p key={s.id}><strong>{s.played_on}</strong> — {s.notes}</p>)}
  </article>;
}
