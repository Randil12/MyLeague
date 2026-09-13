import {useState} from 'react';
import {useData} from './api';
import {percent, num} from './utils.mjs';

export default function Leaderboard({revision}:{revision:number}) {
  const result=useData('/api/leaderboard',{},revision);
  const [search,setSearch]=useState('');
  const rows=result.rows.filter(r=>String(r.player_name).toLowerCase().includes(search.toLowerCase()));
  const stamp=result.rows[0]?.collected_at;
  return <section className="panel"><div className="panel-head"><div><span className="eyebrow">CLASSÉ SOLO • EUW</span><h2>Top 300 Challenger</h2><p>Classement du dernier snapshot Riot, pas un classement instantané.</p></div><span className="badge">{result.rows.length} / 300 collectés</span></div>
    <div className="filters"><label className="field">Rechercher un Riot ID<input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Pseudo#TAG"/></label><span>Snapshot : {stamp?new Date(String(stamp)).toLocaleString('fr-FR'):'indisponible'}</span></div>
    {result.loading?<p role="status">Lecture du classement…</p>:result.error?<p role="alert">{result.error}</p>:<>
      {result.rows.length<300&&<p className="note">Classement partiel : {result.rows.length} comptes disponibles. Le DAG riot_euw_ingestion doit terminer son snapshot. Aucun joueur n’est inventé pour compléter la liste.</p>}
      <div className="table-scroll"><table><thead><tr><th>Position</th><th>Riot ID</th><th>LP</th><th>Victoires</th><th>Défaites</th><th>Winrate</th></tr></thead><tbody>{rows.map(r=><tr key={String(r.position)}><td>{String(r.position)}</td><td>{String(r.player_name)}</td><td>{num(r.league_points)}</td><td>{num(r.wins)}</td><td>{num(r.losses)}</td><td>{percent(r.winrate)}</td></tr>)}</tbody></table></div>
      {!rows.length&&<p>Aucun joueur correspondant.</p>}
      <p className="panel-foot">Pseudos manquants : résolution progressive par ACCOUNT-V1. À égalité de LP, tri par victoires puis identifiant interne.</p>
    </>}
  </section>;
}
