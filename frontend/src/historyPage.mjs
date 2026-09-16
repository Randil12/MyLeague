export function historyPage(rows) {
  return {rows:rows.slice(0,20),hasNext:rows.length>20};
}
