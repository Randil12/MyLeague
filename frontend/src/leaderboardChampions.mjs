export function topChampions(row){
  return [1,2,3,4,5].flatMap(i=>row[`champion_${i}`]?[{name:String(row[`champion_${i}`]),games:Number(row[`champion_${i}_games`]??0)}]:[]);
}
export function filterLeaderboard(rows,search,champion,sort){
  const filtered=rows.filter(r=>String(r.player_name).toLowerCase().includes(search.toLowerCase())&&(!champion||topChampions(r).some(c=>c.name===champion)));
  return filtered.sort((a,b)=>{
    const games=r=>topChampions(r).find(c=>c.name===champion)?.games??0;
    return (sort==='champion'&&champion?games(b)-games(a):0)||Number(a.position)-Number(b.position);
  });
}
