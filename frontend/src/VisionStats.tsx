import {useData, type Row} from './api';
import {numericValues} from './laneMetrics.mjs';
import {num} from './utils.mjs';

const metrics = [
  ['wards_placed', 'Wards posées'],
  ['control_wards_placed', 'Balises de contrôle posées'],
  ['control_wards_bought', 'Balises de contrôle achetées'],
];

export function VisionStats({rows}:{rows:Row[]}) {
  return <section aria-label="Vision et balises"><h3>Vision et balises</h3>
    <div className="stats">{metrics.map(([key,label])=>{
      const values=numericValues(rows,key);
      const total=values.reduce((sum:number,value:number)=>sum+value,0);
      return <article className="stat" key={key}><span>{label}</span>
        <strong>{values.length?num(total/values.length,2):'—'}<small> / partie</small></strong>
        <small>{values.length?`${num(total)} au total · `:''}{values.length} / {rows.length} parties renseignées</small>
      </article>;
    })}</div>
    <p className="note">Moyennes par partie renseignée. Achats et poses distincts ; compteurs non cumulables.</p>
  </section>;
}

export default function PlayerVision({player,patch,revision}:{player:string;patch:string;revision:number}) {
  const result=useData('/api/lane',{player,patch},revision,Boolean(player));
  if(result.disabled)return null;
  if(result.loading)return <p role="status">Chargement des métriques de vision…</p>;
  if(result.error)return <p role="alert">{result.error} Vérifie le build dbt gold_player_lane.</p>;
  if(!result.rows.length)return <p>Aucune partie disponible pour les métriques de vision.</p>;
  return <VisionStats rows={result.rows}/>;
}
