import {useState} from 'react';
import Champion from './Champion';
import {topChampions,filterLeaderboard} from './leaderboardChampions.mjs';
import {useData,type Row} from './api';
import {percent, num} from './utils.mjs';

export default function Leaderboard({revision}:{revision:number}) {
  const result=useData('/api/leaderboard',{},revision);
  const [search,setSearch]=useState('');
  const [page,setPage]=useState(0);
  const [champion,setChampion]=useState('');const [sort,setSort]=useState('lp');
  const champions=[...new Set(result.rows.flatMap(r=>topChampions(r).map(c=>c.name)))].sort();
  const rows:Row[]=filterLeaderboard(result.rows,search,champion,sort);
  const pages=Math.max(1,Math.ceil(rows.length/50));
  const currentPage=Math.min(page,pages-1);
  const stamp=result.rows[0]?.collected_at;
  return <section className="panel"><div className="panel-head"><div><span className="eyebrow">CLASSÉ SOLO • EUW</span><h2>Top 1 000 EUW</h2><p>Classement du dernier snapshot Riot, pas un classement instantané.</p></div><span className="badge">{result.rows.length} / 1000 collectés</span></div>
    <div className="filters"><label className="field">Rechercher un Riot ID<input value={search} onChange={e=>{setSearch(e.target.value);setPage(0);}} placeholder="Pseudo#TAG"/></label><label className="field">Champion dans le top 5<select value={champion} onChange={e=>{setChampion(e.target.value);setPage(0);}}><option value="">Tous les champions</option>{champions.map(c=><option key={c}>{c}</option>)}</select></label><label className="field">Trier par<select value={sort} onChange={e=>{setSort(e.target.value);setPage(0);}}><option value="lp">Classement LP</option><option value="champion" disabled={!champion}>Parties sur le champion sélectionné</option></select></label><span>Snapshot : {stamp?new Date(String(stamp)).toLocaleString('fr-FR'):'indisponible'}</span></div>
    {result.loading?<p role="status">Lecture du classement…</p>:result.error?<p role="alert">{result.error}</p>:<>
      {result.rows.length<1000&&<p className="note">Classement partiel : {result.rows.length} comptes disponibles. Le DAG riot_euw_ingestion doit terminer son snapshot.</p>}
      <div className="table-scroll"><table><thead><tr><th>Position</th><th>Riot ID</th><th>Rang</th><th>LP</th><th>Victoires</th><th>Défaites</th><th>Winrate</th><th>5 champions les plus joués · {String(result.rows[0]?.champion_year??new Date().getFullYear())}</th></tr></thead><tbody>{rows.slice(currentPage*50,(currentPage+1)*50).map(r=><tr key={String(r.position)}><td>{String(r.position)}</td><td>{String(r.player_name)}</td><td>{String(r.tier)}</td><td>{num(r.league_points)}</td><td>{num(r.wins)}</td><td>{num(r.losses)}</td><td>{percent(r.winrate)}</td><td>{topChampions(r).length?<div className="composition-icons">{topChampions(r).map(c=><span key={c.name}><Champion name={c.name}/><small>{num(c.games)} matchs</small></span>)}</div>:<span>Historique non collecté</span>}<small className="metric-coverage">{num(r.champion_sample_games)} parties collectées cette année</small></td></tr>)}</tbody></table></div>
      {!rows.length&&<p>Aucun joueur correspondant.</p>}
      <div className="filters"><button className="quiet" disabled={currentPage===0} onClick={()=>setPage(currentPage-1)}>Précédent</button><span>Page {currentPage+1} / {pages}</span><button className="quiet" disabled={currentPage+1>=pages} onClick={()=>setPage(currentPage+1)}>Suivant</button></div>
      <p className="panel-foot">Top 5 calculé uniquement sur les parties soloQ collectées de l’année UTC, tous patches confondus : historique potentiellement partiel, pas des points de maîtrise. Les égalités de volume sont départagées par nom de champion. Le filtre cherche uniquement dans le top 5 ; la position LP originale est conservée. Pseudos manquants : résolution progressive par ACCOUNT-V1. À égalité de LP, tri par victoires puis identifiant interne.</p>
    </>}
  </section>;
}
