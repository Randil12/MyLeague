import {useState} from 'react';
import {useData} from './api';
import Champion from './Champion';
import {num,percent} from './utils.mjs';

export default function ProDraft({revision}:{revision:number}) {
  const patches=useData('/api/pro/draft/patches',{},revision);
  const [chosen,setChosen]=useState('');
  const [search,setSearch]=useState('');
  const patch=patches.rows.some(r=>r.patch===chosen)?chosen:String(patches.rows[0]?.patch||'');
  const result=useData('/api/pro/draft',{patch},revision,Boolean(patch));
  const rows=result.rows.filter(r=>String(r.champion_name).toLowerCase().includes(search.toLowerCase()));
  return <><div className="filters"><label className="field">Patch professionnel<select value={patch} onChange={e=>setChosen(e.target.value)}><option value="" disabled>Choisir un patch</option>{patches.rows.map(r=><option key={String(r.patch)}>{String(r.patch)}</option>)}</select></label><label className="field">Champion<input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Rechercher un champion"/></label></div><p className="note">Compétitions collectées sur Leaguepedia, toutes régions confondues. Picks et bans uniquement professionnels, sans score soloQ. Les patches sont normalisés dans l’entrepôt.</p>
    {(patches.error||result.error)&&<p role="alert" className="error-banner">{patches.error||result.error}</p>}
    {patches.loading||result.loading?<p role="status">Chargement de la méta pro…</p>:!patches.error&&!result.error&&<section className="panel"><div className="panel-head"><h2>Priorités pick / ban · Pro</h2><span className="badge">{num(result.rows[0]?.total_games||0)} parties collectées</span></div>{!rows.length?<p className="empty">Aucune donnée pour ce filtre. Vérifie les DAG Leaguepedia et dbt.</p>:<div className="table-scroll"><table><thead><tr><th>Champion</th><th>Picks</th><th>Bans</th><th>Présence</th><th>Winrate</th></tr></thead><tbody>{rows.map(r=><tr key={String(r.champion_name)}><td><Champion name={String(r.champion_name)}/></td><td>{num(r.picks)}</td><td>{num(r.bans)}</td><td>{percent(r.presence)}</td><td>{percent(r.winrate)}</td></tr>)}</tbody></table></div>}<p className="panel-foot">Tri par présence (pick ou ban). Un petit échantillon ne suffit pas à établir une priorité de draft.</p></section>}
  </>;
}
