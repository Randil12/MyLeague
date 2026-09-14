import {useState} from 'react';
import {useData} from './api';
import Champion from './Champion';
import {num,percent} from './utils.mjs';

export default function ProDraft({revision}:{revision:number}) {
  const patches=useData('/api/pro/draft/patches',{},revision);
  const [chosen,setChosen]=useState('');
  const [search,setSearch]=useState('');
  const [region,setRegion]=useState('');const [role,setRole]=useState('');
  const patch=patches.rows.some(r=>r.patch===chosen)?chosen:String(patches.rows[0]?.patch||'');
  const options=useData('/api/pro/draft/options',{patch},revision,Boolean(patch));
  const result=useData('/api/pro/draft',{patch,region,role},revision,Boolean(patch));
  const rows=result.rows.filter(r=>String(r.champion_name).toLowerCase().includes(search.toLowerCase()));
  return <><div className="filters"><label className="field">Patch professionnel<select value={patch} onChange={e=>{setChosen(e.target.value);setRegion('');setRole('');}}><option value="" disabled>Choisir un patch</option>{patches.rows.map(r=><option key={String(r.patch)}>{String(r.patch)}</option>)}</select></label><label className="field">Région de compétition<select value={region} onChange={e=>{setRegion(e.target.value);setRole('');}}><option value="">Toutes</option>{[...new Set(options.rows.map(r=>String(r.competition_region)))].sort().map(v=><option key={v}>{v}</option>)}</select></label><label className="field">Rôle<select value={role} onChange={e=>setRole(e.target.value)}><option value="">Tous</option>{[...new Set(options.rows.filter(r=>!region||r.competition_region===region).map(r=>String(r.role||'')).filter(Boolean))].sort().map(v=><option key={v}>{v}</option>)}</select></label><label className="field">Champion<input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Rechercher un champion"/></label></div><p className="note">Compétitions collectées sur Leaguepedia. La région correspond au tournoi. Un rôle filtre les picks observés ; aucun rôle n’est attribué aux bans. Picks et bans uniquement professionnels, sans score soloQ. Les patches sont normalisés dans l’entrepôt.</p>
    {(patches.error||options.error||result.error)&&<p role="alert" className="error-banner">{patches.error||options.error||result.error}</p>}
    {patches.loading||options.loading||result.loading?<p role="status">Chargement de la méta pro…</p>:!patches.error&&!options.error&&!result.error&&<section className="panel"><div className="panel-head"><h2>Priorités pick / ban · Pro</h2><span className="badge">{num(result.rows[0]?.total_games||0)} parties collectées</span></div>{!rows.length?<p className="empty">Aucune donnée pour ce filtre. Vérifie les DAG Leaguepedia et dbt.</p>:<div className="table-scroll"><table><thead><tr><th>Champion</th><th>Picks</th>{!role&&<th>Bans</th>}<th>{role?'Fréquence de pick au rôle':'Présence'}</th><th>Winrate</th></tr></thead><tbody>{rows.map(r=><tr key={String(r.champion_name)}><td><Champion name={String(r.champion_name)}/></td><td>{num(r.picks)}</td>{!role&&<td>{num(r.bans)}</td>}<td>{percent(role?r.pickrate:r.presence)}</td><td>{percent(r.winrate)}</td></tr>)}</tbody></table></div>}<p className="panel-foot">{role?'Tri par picks au rôle. Fréquence : picks à ce rôle / parties collectées du patch et de la région.':'Tri par présence (pick ou ban).'} Un petit échantillon ne suffit pas à établir une priorité de draft.</p></section>}
  </>;
}
