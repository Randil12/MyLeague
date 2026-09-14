import {useState} from 'react';
import {useData} from './api';
import {num, percent} from './utils.mjs';

function PlayerCard({year,revision}:{year:number;revision:number}) {
  const [source,setSource]=useState('soloq');
  const [player,setPlayer]=useState('');
  const [search,setSearch]=useState('');
  const directory=useData(source==='pro'?'/api/pro/players':'/api/my-players',source==='pro'?{year}:{},revision);
  const players=directory.rows;
  const id=source==='pro'?'player_page':'puuid';
  const valid=players.some(r=>r[id]===player);
  const result=useData('/api/pro/coaching',{source,player,year},revision,valid);
  const accounts=useData('/api/pro/accounts',{player,year},revision,valid&&source==='pro');
  const row=result.rows[0];
  const fields=[['Parties','games',''],['Winrate','winrate','games_with_result'],['KDA (ratio de totaux)','kda','games_with_kda'],['CS / minute','cs_min','games_with_cs_min'],['Dégâts champions / minute','damage_min','games_with_damage_min'],['Or / minute','gold_min','games_with_gold_min'],['Champions différents','champion_pool','']];
  return <section className="panel coaching-player"><div className="filters">
    <label className="field">Population<select value={source} onChange={e=>{setSource(e.target.value);setPlayer('');setSearch('');}}><option value="soloq">Mes joueurs · soloQ EUW</option><option value="pro">Joueurs pro · compétition</option></select></label>
    <label className="field">Rechercher<input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Pseudo du joueur"/></label>
    <label className="field">Joueur<select value={valid?player:''} onChange={e=>setPlayer(e.target.value)}><option value="">Choisir un joueur</option>{players.filter(r=>r[id]===player||String(r.player_name).toLowerCase().includes(search.toLowerCase())).map(r=><option key={String(r[id])} value={String(r[id])}>{String(r.player_name)}</option>)}</select></label>
  </div><p className="badge">{source==='pro'?'Compétition · Leaguepedia':'SoloQ EUW · Riot'} · {year}</p>
    {directory.error&&<p role="alert" className="error-banner">{directory.error}</p>}
    {directory.loading?<p role="status">Chargement des joueurs…</p>:!players.length&&!directory.error?<p className="empty">{source==='pro'?'Aucun joueur pro collecté cette année.':'Ajoute tes joueurs dans le roster ci-dessus.'}</p>:null}
    {result.error&&<p role="alert" className="error-banner">{result.error}</p>}
    {valid&&(result.loading?<p role="status">Calcul des statistiques…</p>:!result.error&&<><p className="note">{Number(row?.games||0)<5?'Moins de cinq parties : échantillon insuffisant pour conclure.':'Statistiques sur les parties collectées de l’année, tous patches et rôles confondus.'}</p><table><tbody>{fields.map(([label,key,coverage])=><tr key={key}><th scope="row">{label}</th><td>{row?.[key]==null?'—':key==='winrate'?percent(row[key]):num(row[key],key==='games'||key==='champion_pool'?0:2)}{coverage&&<small className="metric-coverage">{String(row?.[coverage]??0)} parties renseignées</small>}</td></tr>)}</tbody></table></>)}
    {source==='pro'&&valid&&<aside className="note"><div><strong>Comptes soloQ déclarés sur Leaguepedia</strong>{accounts.loading?<p>Lecture du profil…</p>:accounts.error?<p role="alert">{accounts.error}</p>:<p className="rune-source">{String(accounts.rows[0]?.reported_accounts||'Aucun compte renseigné dans Cargo.')}</p>}<p>Texte source non vérifié, potentiellement ancien ou incomplet. Pour suivre un compte EUW, vérifie son Riot ID actuel puis ajoute-le au roster. Ces comptes ne sont pas automatiquement attribués ni importés.</p></div></aside>}
  </section>;
}

export default function CoachingCompare({revision}:{revision:number}) {
  const [year,setYear]=useState(new Date().getFullYear());
  return <><div className="filters"><label className="field">Année (UTC)<input type="number" min={2000} max={2100} value={year} onChange={e=>{const n=Number(e.target.value);if(n>=2000&&n<=2100)setYear(n);}}/></label></div><p className="note">Choisis deux joueurs de ton équipe, deux pros ou un de chaque. La compétition organisée et la soloQ ont des contextes différents : cette comparaison descriptive ne mesure pas un écart de niveau. Gold@15 non disponible. Les données manquantes restent vides.</p><div className="split"><PlayerCard key={`a-${year}`} year={year} revision={revision}/><PlayerCard key={`b-${year}`} year={year} revision={revision}/></div></>;
}
