// Competition region describes observed games, not a team's headquarters.
export function regionOptions(rows, column, region) {
  const scoped = ['team', 'tournament_page'].includes(column) && region
    ? rows.filter(row => row.competition_region === region) : rows;
  return [...new Set(scoped.map(row => String(row[column] || '')).filter(Boolean))].sort();
}

export function updateProFilters(filters, key, value) {
  return {...filters, ...(key === 'region' ? {team: '', tournament: ''} : {}), [key]: value};
}
