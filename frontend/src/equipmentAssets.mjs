const cdn='https://ddragon.leagueoflegends.com/cdn';
export function itemIcon(version,id) {
  return /^\d+\.\d+\.\d+$/.test(String(version))&&/^[1-9]\d*$/.test(String(id))?`${cdn}/${version}/img/item/${id}.png`:'';
}
export function runeIcon(path) {
  return typeof path==='string'&&/^perk-images\/[A-Za-z0-9_/-]+\.png$/.test(path)&&!path.includes('..')?`${cdn}/img/${path}`:'';
}
export function normalizeEquipment(value) {
  return String(value??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]/g,'');
}
export function splitEquipment(value) {
  return String(value??'').split(/[;\n|]/).map(v=>v.trim()).filter(Boolean);
}
