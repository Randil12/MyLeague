import {createContext,useContext,useEffect,useState,type ReactNode} from 'react';
import {itemIcon,runeIcon,normalizeEquipment,splitEquipment} from './equipmentAssets.mjs';

type Entry={kind:'item'|'rune';id:string;name:string;url:string};
type Rune={id:number;name:string;key:string;icon:string;slots?:{runes:Rune[]}[]};
const Catalog=createContext<Entry[]>([]);

export function EquipmentProvider({children}:{children:ReactNode}) {
  const [entries,setEntries]=useState<Entry[]>([]);
  useEffect(()=>{
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),20000);
    async function json(url:string) {
      const response=await fetch(url,{signal:controller.signal});
      if(!response.ok)throw new Error('Catalogue indisponible');
      return response.json();
    }
    async function load() {
      const versions=await json('https://ddragon.leagueoflegends.com/api/versions.json');
      const version=versions[0];
      if(typeof version!=='string'||!/^\d+\.\d+\.\d+$/.test(version))return;
      await Promise.allSettled(['fr_FR','en_US'].flatMap(locale=>[
        (async()=>{
          const body=await json(`https://ddragon.leagueoflegends.com/cdn/${version}/data/${locale}/item.json`);
          const items=Object.entries(body.data as Record<string,{name:string}>).map(([id,item]):Entry=>({kind:'item',id,name:item.name,url:itemIcon(version,id)}));
          if(!controller.signal.aborted)setEntries(old=>[...old,...items]);
        })(),
        (async()=>{
          const styles:Rune[]=await json(`https://ddragon.leagueoflegends.com/cdn/${version}/data/${locale}/runesReforged.json`);
          const runes=styles.flatMap(style=>[style,...(style.slots??[]).flatMap(slot=>slot.runes)]).flatMap(r=>[r.name,r.key].map((name):Entry=>({kind:'rune',id:String(r.id),name,url:runeIcon(r.icon)})));
          if(!controller.signal.aborted)setEntries(old=>[...old,...runes]);
        })(),
      ]));
    }
    void load().catch(()=>{}).finally(()=>clearTimeout(timeout));
    return ()=>{controller.abort();clearTimeout(timeout);};
  },[]);
  return <Catalog.Provider value={entries}>{children}</Catalog.Provider>;
}

export function Equipment({kind,name,id}:{kind:'item'|'rune';name:string;id?:string|number|null}) {
  const entries=useContext(Catalog);
  const [failed,setFailed]=useState('');
  const key=normalizeEquipment(name);
  const row=entries.find(r=>r.kind===kind&&(id!=null?r.id===String(id):r.id===name||normalizeEquipment(r.name)===key));
  const label=name||row?.name||'Non disponible';
  return <span className="champion" title={label}>{row?.url&&failed!==row.url&&<img className="champion-icon" src={row.url} width={32} height={32} alt="" loading="lazy" onError={()=>setFailed(row.url)}/>}<span>{label}</span></span>;
}

export function EquipmentList({kind,value}:{kind:'item'|'rune';value:string}) {
  const values=splitEquipment(value);
  return <span className="composition-icons">{values.length?values.map((name,i)=><Equipment key={`${i}-${name}`} kind={kind} name={name}/>):'Non disponible'}</span>;
}
