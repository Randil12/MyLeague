import {useState} from 'react';
import {useData, type Row, type Result} from './api';
import {num, percent} from './utils.mjs';
import Champion from './Champion';
import {Equipment,EquipmentList} from './Equipment';

const missing='Non disponible';
function ErrorState({result}:{result:Result}) {
  return result.error?<p role="alert" className="error-banner">{result.error} Vérifie le dernier build du DAG leaguepedia_ingestion.</p>:result.loading?<p role="status">Lecture des données de compétition…</p>:null;
}

function Comparison({year,revision}:{year:number;revision:number}) {
  const [ids,setIds]=useState<string[]>([]);
  const [page,setPage]=useState(0);
  const [search,setSearch]=useState('');
  const [filters,setFilters]=useState({region:'',tournament:'',role:'',champion:'',patch:''});
  const options=useData('/api/pro/options',{year},revision);
  const players=useData('/api/pro/players',{year,...filters},revision);
  const valid=ids.length>=2&&ids.length<=5;
  const visible=players.rows.filter(p=>String(p.player_name).toLowerCase().includes(search.toLowerCase()));
  const pages=Math.max(1,Math.ceil(visible.length/20));
  const currentPage=Math.min(page,pages-1);
  const params={year,...filters,selected_players:ids};
  const comparison=useData('/api/pro/compare',params,revision,valid);
  const history=useData('/api/pro/history',params,revision,valid);
  const labels=ids.map(p=>String(players.rows.find(r=>r.player_page===p)?.player_name||p));
  const selected=ids.map(p=>comparison.rows.find(r=>r.player_page===p));
  const fields:[keyof typeof filters,string,string][]=[['region','Région de compétition','competition_region'],['tournament','Tournoi','tournament_page'],['role','Rôle','role'],['champion','Champion','champion'],['patch','Patch pro (source)','source_patch']];
  const metrics:[string,string,string?,boolean?][]=[['Parties','games'],['Winrate','winrate','games_with_result',true],['KDA (ratio de totaux)','kda','games_with_kda'],['Kills moyens','avg_kills','games_with_kills'],['Morts moyennes','avg_deaths','games_with_deaths'],['Assists moyennes','avg_assists','games_with_assists'],['CS finaux moyens','avg_cs','games_with_cs'],['CS / minute','cs_min','games_with_cs_min'],['Or final moyen','avg_gold','games_with_gold'],['Or / minute','gold_min','games_with_gold_min'],['Dégâts champions moyens','avg_damage','games_with_damage'],['Vision moyenne','avg_vision','games_with_vision'],['Champions différents','champion_pool']];
  function changeFilters(next:typeof filters) {setFilters(next);setIds([]);setPage(0);}
  function toggle(id:string) {setIds(current=>current.includes(id)?current.filter(p=>p!==id):current.length<5?[...current,id]:current);}
  return <>
    <aside className="note"><div><strong>Comparer à périmètre constant</strong><p>Les filtres s’appliquent aux joueurs sélectionnés. La région est celle du tournoi, pas la nationalité du joueur ni son serveur soloQ. Couverture Leaguepedia observée, possiblement partielle ; anciens alias non consolidés.</p></div></aside>
    <section className="panel"><div className="panel-head"><h2>Joueurs ayant joué en {year}</h2><span className="badge">{players.rows.length} joueurs observés · {ids.length}/5 sélectionnés</span></div>
      <ErrorState result={players}/>
      <div className="filters"><label className="field">Rechercher un pseudo<input value={search} onChange={e=>{setSearch(e.target.value);setPage(0);}} placeholder="Nom du joueur"/></label></div>
      <ErrorState result={options}/>
      <div className="filters">{fields.map(([key,label,column])=>{
        const values=[...new Set(options.rows.map(r=>String(r[column]||'')).filter(Boolean))].sort();
        return <label className="field" key={key}>{label}<select value={filters[key]} onChange={e=>changeFilters({...filters,[key]:e.target.value})}><option value="">Tous</option>{values.map(v=><option key={v} value={v}>{key==='tournament'?String(options.rows.find(r=>r.tournament_page===v)?.tournament||v):v}</option>)}</select></label>;
      })}<button className="quiet" onClick={()=>changeFilters({region:'',tournament:'',role:'',champion:'',patch:''})}>Réinitialiser les filtres</button></div>
      <p>Les filtres s’appliquent à la liste et aux statistiques. Les modifier efface la sélection.</p>
      <div className="filters">{ids.map((id,i)=><button className="quiet" key={id} onClick={()=>toggle(id)}>Retirer {labels[i]} ×</button>)}</div>
      {!players.loading&&!players.error&&<><div className="table-scroll"><table><thead><tr><th>Joueur</th><th>Parties dans le périmètre</th><th>Sélection</th></tr></thead><tbody>{visible.slice(currentPage*20,(currentPage+1)*20).map(p=><tr key={String(p.player_page)}><td>{String(p.player_name)}</td><td>{num(p.games)}</td><td><button className="quiet" aria-pressed={ids.includes(String(p.player_page))} disabled={!ids.includes(String(p.player_page))&&ids.length>=5} onClick={()=>toggle(String(p.player_page))}>{ids.includes(String(p.player_page))?'Retirer':'Comparer'}</button></td></tr>)}</tbody></table></div>
      {!visible.length&&<p className="empty">Aucun joueur collecté pour ces filtres.</p>}
      <div className="filters"><button className="quiet" disabled={currentPage===0} onClick={()=>setPage(currentPage-1)}>Précédent</button><span>Page {currentPage+1} / {pages} · {visible.length} résultats</span><button className="quiet" disabled={currentPage+1>=pages} onClick={()=>setPage(currentPage+1)}>Suivant</button></div></>}
    </section>
    {!valid?<p className="empty">Choisis de deux à cinq joueurs distincts pour afficher la comparaison.</p>:<>
      <ErrorState result={comparison}/>
      {!comparison.loading&&!comparison.error&&<section className="panel pro-comparison"><div className="panel-head"><h2>Comparaison individuelle</h2><span className="badge">{year} · Compétition</span></div>
        {selected.some(r=>!r||Number(r.games)<5)&&<p className="note">Au moins un joueur a moins de cinq parties sur ces filtres. Les écarts ne suffisent pas à conclure sur son niveau.</p>}
        <div className="table-scroll"><table><thead><tr><th>Indicateur</th>{labels.map((label,i)=><th key={i}>{label}</th>)}</tr></thead><tbody>{metrics.map(([label,key,coverage,ratio])=><tr key={key}><th scope="row">{label}</th>{selected.map((r,i)=><td key={i}>{r?.[key]==null?'—':ratio?percent(r[key]):num(r[key],key==='games'||key==='champion_pool'?0:2)}{coverage&&<small className="metric-coverage">{r?String(r[coverage]??0):0} parties renseignées</small>}</td>)}</tr>)}<tr><th scope="row">Gold@15 / différence d’or à 15 min</th>{ids.map(id=><td key={id}>{missing}</td>)}</tr></tbody></table></div>
        <p className="panel-foot">Aucun Gold@15 collecté par cette source : l’or final n’est pas un substitut. Pas de vainqueur automatique de la comparaison.</p>
      </section>}
      <ErrorState result={history}/>
      {!history.loading&&!history.error&&<div className="split">{ids.map((player,i)=><PlayerHistory key={player} name={labels[i]} rows={history.rows.filter(r=>r.player_page===player)}/>)}</div>}
    </>}
  </>;
}

function PlayerHistory({name,rows}:{name:string;rows:Row[]}) {
  return <section className="panel"><div className="panel-head"><div><h2>{name}</h2><p>20 dernières participations correspondant aux filtres.</p></div></div>
    {!rows.length?<p className="empty">Aucune partie collectée pour ce périmètre.</p>:rows.map((r,i)=><article className="pro-game" key={i}><div className="panel-head"><Champion name={String(r.champion||'')}/><span className="badge">{r.win==null?'Résultat inconnu':r.win?'Victoire':'Défaite'}</span></div><p>{new Date(String(r.game_date)).toLocaleDateString('fr-FR')} · {String(r.tournament||'Tournoi inconnu')} · {String(r.team||'Équipe inconnue')} · {String(r.role||'Rôle inconnu')} · patch {String(r.source_patch||'inconnu')}</p><p>K / D / A : {String(r.kills??'—')} / {String(r.deaths??'—')} / {String(r.assists??'—')}</p><details><summary>Objets et runes de cette partie</summary>{r.equipment_fields_collected===false?<p className="note">Ancienne collecte incomplète : les champs objets et runes n’ont pas tous été enregistrés. Le DAG Leaguepedia doit relire cette journée puis reconstruire Gold.</p>:<p className="note">Les champs non renseignés dans la source restent indisponibles. Les objets affichés sont ceux de fin de partie, pas un ordre d’achat.</p>}<p>Objets finaux : <EquipmentList kind="item" value={String(r.items||'')}/></p><p>Trinket : <Equipment kind="item" name={String(r.trinket||missing)}/></p><p>Rune fondamentale : <Equipment kind="rune" name={String(r.keystone_rune||missing)}/></p><p>Arbres : <Equipment kind="rune" name={String(r.primary_tree||'—')}/> / <Equipment kind="rune" name={String(r.secondary_tree||'—')}/></p><p className="rune-source">Runes : <EquipmentList kind="rune" value={String(r.runes||'')}/></p></details></article>)}
  </section>;
}

export default function ProCompare({revision}:{revision:number}) {
  const years=useData('/api/pro/years',{},revision);
  const [year,setChosen]=useState(new Date().getFullYear());
  const available=[...new Set([new Date().getFullYear(),...years.rows.map(r=>Number(r.year))])].sort((a,b)=>b-a);
  return <><ErrorState result={years}/><div className="filters"><label className="field">Année de compétition<select value={year} onChange={e=>setChosen(Number(e.target.value))}>{available.map(y=><option key={y} value={y}>{y}</option>)}</select></label></div><Comparison key={year} year={year} revision={revision}/></>;
}
