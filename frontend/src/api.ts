import {useEffect, useState} from 'react';
export type Row = Record<string, string | number | boolean | null>;
export type Params = Record<string, string | number | string[]>;
export type Result = { rows: Row[]; loading: boolean; error: string; disabled: boolean };
export function useData(path: string, params: Params = {}, revision = 0, enabled = true): Result {
  const encoded = new URLSearchParams();
  for (const [key,value] of Object.entries(params)) {
    if(Array.isArray(value)) value.forEach(v=>encoded.append(key,v));
    else encoded.set(key,String(value));
  }
  const url = `${path}?${encoded}`;
  const [state,setState] = useState<{key:string;rows:Row[];loading:boolean;error:string}>({key:'',rows:[],loading:true,error:''});
  const key = `${url}|${revision}|${enabled}`;
  useEffect(()=>{
    if(!enabled) return;
    const controller = new AbortController();
    setState({key,rows:[],loading:true,error:''});
    fetch(url,{signal:controller.signal}).then(async response=>{
      const body = await response.json();
      if(!response.ok) throw new Error(typeof body.detail==='string'?body.detail:'Paramètres invalides ou service indisponible.');
      if(!Array.isArray(body)) throw new Error('Réponse inattendue du serveur.');
      if(!controller.signal.aborted) setState({key,rows:body,loading:false,error:''});
    }).catch(error=>{if(!controller.signal.aborted)setState({key,rows:[],loading:false,error:error.message});});
    return ()=>controller.abort();
  },[url,key,enabled]);
  if(!enabled) return {rows:[],loading:false,error:'',disabled:true};
  if(state.key!==key) return {rows:[],loading:true,error:'',disabled:false};
  return {...state,disabled:false};
}
