export function numericValues(rows,key){return rows.map(r=>r[key]).filter(v=>v!=null&&v!==''&&Number.isFinite(Number(v))).map(Number);}
export function formatLaneMetric(key,value,digits=0){
  if(value==null||value===''||!Number.isFinite(Number(value)))return '—';
  return Number(value).toLocaleString('fr-FR',{
    maximumFractionDigits:digits,
    signDisplay:['gd_15','xpd_15'].includes(key)?'exceptZero':'auto',
  });
}
export function laneMean(rows,key){const values=numericValues(rows,key);return {count:values.length,mean:values.length?values.reduce((a,b)=>a+b,0)/values.length:null};}
export function goalResult(rows,key,threshold,direction){
  const values=numericValues(rows,key);
  const success=values.filter(v=>direction==='min'?v>=threshold:v<=threshold).length;
  return {evaluated:values.length,success,rate:values.length?success/values.length:null};
}
