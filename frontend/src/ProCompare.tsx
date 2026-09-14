import {useState} from 'react';
import {useData, type Row, type Result} from './api';
import {num, percent} from './utils.mjs';
import Champion from './Champion';

const missing='Non disponible';
function ErrorState({result}:{result:Result}) {
  return result.error?<p role="alert" className="error-banner">{result.error} Vérifie le dernier build du DAG leaguepedia_ingestion.</p>:result.loading?<p role="status">Lecture des données de compétition…</p>:null;
}

function Comparison({year,revision}:{year:number;revision:number}) {
  const [a,setA]=useState(''); const [b,setB]=useState('');
  const [search,setSearch]=useState('');
  const [filters,setFilters]=useState({region:'',tournament:'',role:'',champion:'',patch:''});
  const options=useData('/api/pro/options',{year},revision);
  const players=useData('/api/pro/players',{year},revision);
  const valid=Boolean(a&&b&&a!==b);
  const params={year,...filters,player_a:a,player_b:b};
  const comparison=useData('/api/pro/compare',params,revision,valid);
  const history=useData('/api/pro/history',params,revision,valid);
  const labels=[a,b].map(p=>String(players.rows.find(r=>r.player_page===p)?.player_name||p));
  const selected=[a,b].map(p=>comparison.rows.find(r=>r.player_page===p));
  const fields:[keyof typeof filters,string,string][]=[['region','Région de compétition','competition_region'],['tournament','Tournoi','tournament_page'],['role','Rôle','role'],['champion','Champion','champion'],['patch','Patch pro (source)','source_patch']];
  const metrics:[string,string,string?,boolean?][]=[['Parties','games'],['Winrate','winrate','games_with_result',true],['KDA (ratio de totaux)','kda','games_with_kda'],['Kills moyens','avg_kills','games_with_kills'],['Morts moyennes','avg_deaths','games_with_deaths'],['Assists moyennes','avg_assists','games_with_assists'],['CS finaux moyens','avg_cs','games_with_cs'],['CS / minute','cs_min','games_with_cs_min'],['Or final moyen','avg_gold','games_with_gold'],['Or / minute','gold_min','games_with_gold_min'],['Dégâts champions moyens','avg_damage','games_with_damage'],['Vision moyenne','avg_vision','games_with_vision'],['Champions différents','champion_pool']];
  function choose(which:'a'|'b',value:string) {if(which==='a')setA(value);else setB(value);}
  return <>
    <aside className="note"><div><strong>Comparer à périmètre constant</strong><p>Les filtres s’appliquent aux deux joueurs. La région est celle du tournoi, pas la nationalité du joueur ni son serveur soloQ. Couverture Leaguepedia observée, possiblement partielle ; anciens alias non consolidés.</p></div></aside>
    <section className="panel"><div className="panel-head"><h2>Choisir deux joueurs actifs en {year}</h2><span className="badge">{players.rows.length} joueurs observés</span></div>
      <ErrorState result={players}/>
      <div className="filters"><label className="field">Rechercher un pseudo<input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Nom du joueur"/></label>
        {(['a','b'] as const).map((which,i)=><label className="field" key={which}>Joueur {i+1}<select value={which==='a'?a:b} onChange={e=>choose(which,e.target.value)} disabled={players.loading||Boolean(players.error)}><option value="">Choisir un joueur</option>{players.rows.filter(p=>[a,b].includes(String(p.player_page))||String(p.player_name).toLowerCase().includes(search.toLowerCase())).map(p=><option key={String(p.player_page)} value={String(p.player_page)} disabled={p.player_page===(which==='a'?b:a)}>{String(p.player_name)} · {String(p.games)} matchs</option>)}</select></label>)}
      </div>
      <ErrorState result={options}/>
      <div className="filters">{fields.map(([key,label,column])=>{
        const values=[...new Set(options.rows.map(r=>String(r[column]||'')).filter(Boolean))].sort();
        return <label className="field" key={key}>{label}<select value={filters[key]} onChange={e=>setFilters({...filters,[key]:e.target.value})}><option value="">Tous</option>{values.map(v=><option key={v} value={v}>{key==='tournament'?String(options.rows.find(r=>r.tournament_page===v)?.tournament||v):v}</option>)}</select></label>;
      })}<button className="quiet" onClick={()=>setFilters({region:'',tournament:'',role:'',champion:'',patch:''})}>Réinitialiser les filtres</button></div>
    </section>
    {!valid?<p className="empty">Choisis deux joueurs distincts pour afficher la comparaison.</p>:<>
      <ErrorState result={comparison}/>
      {!comparison.loading&&!comparison.error&&<section className="panel pro-comparison"><div className="panel-head"><h2>Comparaison individuelle</h2><span className="badge">{year} · Compétition</span></div>
        {selected.some(r=>!r||Number(r.games)<5)&&<p className="note">Au moins un joueur a moins de cinq parties sur ces filtres. Les écarts ne suffisent pas à conclure sur son niveau.</p>}
        <div className="table-scroll"><table><thead><tr><th>Indicateur</th>{labels.map((label,i)=><th key={i}>{label}</th>)}</tr></thead><tbody>{metrics.map(([label,key,coverage,ratio])=><tr key={key}><th scope="row">{label}</th>{selected.map((r,i)=><td key={i}>{r?.[key]==null?'—':ratio?percent(r[key]):num(r[key],key==='games'||key==='champion_pool'?0:2)}{coverage&&<small className="metric-coverage">{r?String(r[coverage]??0):0} parties renseignées</small>}</td>)}</tr>)}<tr><th scope="row">Gold@15 / différence d’or à 15 min</th><td>{missing}</td><td>{missing}</td></tr></tbody></table></div>
        <p className="panel-foot">Aucun Gold@15 collecté par cette source : l’or final n’est pas un substitut. Pas de vainqueur automatique de la comparaison.</p>
      </section>}
      <ErrorState result={history}/>
      {!history.loading&&!history.error&&<div className="split">{[a,b].map((player,i)=><PlayerHistory key={player} name={labels[i]} rows={history.rows.filter(r=>r.player_page===player)}/>)}</div>}
    </>}
  </>;
}

function PlayerHistory({name,rows}:{name:string;rows:Row[]}) {
  return <section className="panel"><div className="panel-head"><div><h2>{name}</h2><p>20 dernières participations correspondant aux filtres.</p></div></div>
    {!rows.length?<p className="empty">Aucune partie collectée pour ce périmètre.</p>:rows.map((r,i)=><article className="pro-game" key={i}><div className="panel-head"><Champion name={String(r.champion||'')}/><span className="badge">{r.win==null?'Résultat inconnu':r.win?'Victoire':'Défaite'}</span></div><p>{new Date(String(r.game_date)).toLocaleDateString('fr-FR')} · {String(r.tournament||'Tournoi inconnu')} · {String(r.team||'Équipe inconnue')} · {String(r.role||'Rôle inconnu')} · patch {String(r.source_patch||'inconnu')}</p><p>K / D / A : {String(r.kills??'—')} / {String(r.deaths??'—')} / {String(r.assists??'—')}</p><details><summary>Objets et runes de cette partie</summary><p>Objets finaux : {r.items?String(r.items).replaceAll(';',' · '):missing}</p><p>Trinket : {String(r.trinket||missing)}</p><p>Rune fondamentale : {String(r.keystone_rune||missing)}</p><p>Arbres : {String(r.primary_tree||'—')} / {String(r.secondary_tree||'—')}</p><p className="rune-source">Runes (texte source) : {String(r.runes||missing)}</p></details></article>)}
  </section>;
}

export default function ProCompare({revision}:{revision:number}) {
  const years=useData('/api/pro/years',{},revision);
  const [chosen,setChosen]=useState(0);
  const year=years.rows.some(r=>Number(r.year)===chosen)?chosen:Number(years.rows[0]?.year||0);
  return <><ErrorState result={years}/>{!years.loading&&!years.error&&!year?<div className="empty"><h2>Aucune partie pro disponible</h2><p>Lance leaguepedia_ingestion et attends la construction des tables Gold.</p></div>:year>0&&<><div className="filters"><label className="field">Année de compétition<select value={year} onChange={e=>setChosen(Number(e.target.value))}>{years.rows.map(r=><option key={String(r.year)} value={Number(r.year)}>{String(r.year)}</option>)}</select></label></div><Comparison key={year} year={year} revision={revision}/></>}</>;
}
