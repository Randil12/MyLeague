import {useData} from './api';
import {num, percent} from './utils.mjs';

export default function TeamOverview({patch,roster,revision}:{patch:string;roster:string[];revision:number}) {
  const result=useData('/api/team/summary',{patch,roster},revision,roster.length===5);
  return <section className="panel"><div className="panel-head"><div><h2>Tableau de suivi des cinq joueurs</h2><p>Performances solo individuelles sur le patch : pas un résultat de scrim ni une mesure de synergie.</p></div></div>
    {result.loading?<p role="status">Lecture des performances…</p>:result.error?<p role="alert">{result.error}</p>:<div className="table-scroll"><table><thead><tr><th>Joueur</th><th>Matchs</th><th>Winrate</th><th>KDA</th><th>CS/min</th><th>Vision/min</th></tr></thead><tbody>{result.rows.map((r,i)=><tr key={i}><td>{String(r.player_name)}</td><td>{num(r.games)}</td><td>{percent(r.winrate)}</td><td>{num(r.kda,2)}</td><td>{num(r.cs_min,2)}</td><td>{num(r.vision_min,2)}</td></tr>)}</tbody></table></div>}
  </section>;
}
