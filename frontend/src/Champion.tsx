import {createContext, useContext, useEffect, useState, type ReactNode} from 'react';
import {useData, type Row} from './api';

const Champions = createContext<Row[]>([]);
export function ChampionProvider({children}:{children:ReactNode}) {
  const result=useData('/api/champions',{},0);
  const [catalog,setCatalog]=useState<Row[]>([]);
  useEffect(()=>{
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),15000);
    async function load() {
      const versions=await fetch('https://ddragon.leagueoflegends.com/api/versions.json',{signal:controller.signal});
      if(!versions.ok)throw new Error('Catalogue indisponible');
      const version=(await versions.json())[0];
      if(typeof version!=='string'||!/^\d+\.\d+\.\d+$/.test(version))return;
      const response=await fetch(`https://ddragon.leagueoflegends.com/cdn/${version}/data/en_US/champion.json`,{signal:controller.signal});
      if(!response.ok)throw new Error('Catalogue indisponible');
      const body=await response.json();
      setCatalog(Object.values(body.data as Record<string,{id:string;key:string;name:string}>).map(c=>({champion_id:c.id,champion_key:c.key,name:c.name,version})));
    }
    void load().catch(()=>{}).finally(()=>clearTimeout(timer));
    return ()=>{controller.abort();clearTimeout(timer);};
  },[]);
  return <Champions.Provider value={[...catalog,...result.rows]}>{children}</Champions.Provider>;
}

export default function Champion({name}:{name:string}) {
  const rows=useContext(Champions);
  const [failed,setFailed]=useState('');
  const normalize=(v:unknown)=>String(v??'').toLowerCase().replace(/[^a-z0-9]/g,'');
  const row=rows.find(r=>[r.name,r.champion_id,r.champion_key].some(v=>normalize(v)===normalize(name)));
  const safe=row&&/^[0-9.]+$/.test(String(row.version))&&/^[A-Za-z0-9]+$/.test(String(row.champion_id));
  const url=safe?`https://ddragon.leagueoflegends.com/cdn/${row.version}/img/champion/${row.champion_id}.png`:'';
  const label=String(row?.name||(/^#?\d+$/.test(name)?'Champion inconnu':name)||'Champion inconnu');
  return <span className="champion">{url&&failed!==url?<img className="champion-icon" src={url} alt="" width={32} height={32} loading="lazy" onError={()=>setFailed(url)}/>:<span className="avatar" aria-hidden="true">{label.slice(0,2).toUpperCase()}</span>}{label}</span>;
}

export function Composition({value}:{value:string}) {
  return <span className="composition-icons">{value.split(/[,·]/).map(v=>v.trim()).filter(Boolean).map((name,i)=><Champion name={name} key={`${name}-${i}`}/>)}</span>;
}
