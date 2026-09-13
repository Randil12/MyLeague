import {useEffect, useState, type FormEvent} from 'react';

type Player = {id:number; riot_id:string};
type Roster = {players:Player[]; limit:number};

export default function LiveRoster({revision,onChange}:{revision:number;onChange:()=>void}) {
  const [roster,setRoster]=useState<Roster>({players:[],limit:5});
  const [value,setValue]=useState('');
  const [busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  useEffect(()=>{
    const controller=new AbortController();
    fetch('/api/live/roster',{signal:controller.signal}).then(async response=>{
      const body=await response.json();
      if(!response.ok) throw new Error(body.detail||'Liste indisponible.');
      if(!Array.isArray(body.players)) throw new Error('Liste invalide.');
      if(!controller.signal.aborted){setRoster(body);setError('');setLoading(false);}
    }).catch(e=>{if(!controller.signal.aborted){setError(e.message);setLoading(false);}});
    return()=>controller.abort();
  },[revision]);

  async function mutate(method:'POST'|'DELETE',id?:number){
    setBusy(true);setError('');setNotice('');
    try{
      const response=await fetch(`/api/live/roster${id?`/${id}`:''}`,{
        method,headers:{'Content-Type':'application/json','X-MyLeague-Action':'roster'},
        body:method==='POST'?JSON.stringify({riot_id:value.trim()}):undefined,
      });
      const body=await response.json();
      if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'Riot ID invalide.');
      if(method==='POST')setValue('');
      setNotice(method==='POST'?'Joueur enregistré. Première observation au prochain cycle, sauf pause Riot.':'Joueur retiré du suivi. Les données historiques sont conservées.');
      onChange();
    }catch(e){setError(e instanceof Error?e.message:'Service indisponible.');}
    finally{setBusy(false);}
  }
  function submit(event:FormEvent){event.preventDefault();void mutate('POST');}
  return <section className="panel live-roster" aria-labelledby="roster-title">
    <div className="panel-head"><div><span className="eyebrow">LISTE PARTAGÉE · STRUCTURE</span><h2 id="roster-title">Mes joueurs à suivre</h2></div><span className="badge">{roster.players.length} / {roster.limit}</span></div>
    <p>Ajoute le Riot ID complet de tes joueurs EUW. Seuls ces joueurs sont interrogés ; les nouvelles observations apparaissent au prochain cycle. Suivi des parties classées solo uniquement.</p>
    <form onSubmit={submit} className="roster-form">
      <label htmlFor="roster-riot-id">Riot ID (Pseudo#TAG)<input id="roster-riot-id" value={value} onChange={e=>setValue(e.target.value)} placeholder="Pseudo#EUW" maxLength={64} required disabled={busy} autoComplete="off"/></label>
      <button type="submit" disabled={busy||loading||roster.players.length>=roster.limit||!value.trim()}>{busy?'Traitement…':'Ajouter au suivi'}</button>
    </form>
    {error&&<p role="alert" className="negative">{error}</p>}
    {notice&&<p role="status">{notice}</p>}
    {loading?<p>Chargement de la liste…</p>:!roster.players.length?<p>Aucun joueur configuré. Ajoute ton premier joueur ci-dessus.</p>:<ul className="roster-list">{roster.players.map(p=><li key={p.id}><span>{p.riot_id}</span><button type="button" disabled={busy} onClick={()=>void mutate('DELETE',p.id)} aria-label={`Retirer ${p.riot_id} du suivi`}>Retirer</button></li>)}</ul>}
    <small>Liste commune à toutes les personnes ayant accès à cette application privée. Retirer un joueur ne supprime pas ses matchs.</small>
  </section>;
}
