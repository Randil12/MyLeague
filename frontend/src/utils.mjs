export const roleNames = { TOP:'Top', JUNGLE:'Jungle', MIDDLE:'Mid', BOTTOM:'ADC', UTILITY:'Support' };
export const num = (value, digits = 0) => value == null ? '—' : Number(value).toLocaleString('fr-FR', {maximumFractionDigits:digits});
export const percent = value => value == null ? '—' : `${num(Number(value)*100,1)} %`;
export const csvCell = value => {
  let text = String(value ?? '');
  if (/^[\s]*[=+@-]/.test(text) || /^[\t\r\n]/.test(text)) text = "'" + text;
  return `"${text.replace(/"/g,'""')}"`;
};
export const csv = rows => {
  if (!rows.length) return '';
  const keys = Object.keys(rows[0]);
  return '\uFEFF' + [keys.map(csvCell).join(';'), ...rows.map(r=>keys.map(k=>csvCell(r[k])).join(';'))].join('\r\n');
};
export function filterDraft(rows, search, role, minimum, excluded) {
  return rows.filter(r=>String(r.champion_name).toLocaleLowerCase('fr').includes(search.toLocaleLowerCase('fr')) &&
    (!role || r.role===role) && Number(r.picks)>=minimum && !excluded.includes(String(r.champion_name)));
}
