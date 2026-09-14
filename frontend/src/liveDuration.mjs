/** Wall-clock estimate at the observation, not the game's precise internal clock. */
export function liveDuration(startedAt, checkedAt) {
  if (!startedAt || !checkedAt) return 'Indisponible';
  const start = Date.parse(String(startedAt));
  const checked = Date.parse(String(checkedAt));
  if (!Number.isFinite(start) || !Number.isFinite(checked) || start <= 0 || checked < start) return 'Indisponible';
  const seconds = Math.floor((checked - start) / 1000);
  return `${Math.floor(seconds / 60)} min ${String(seconds % 60).padStart(2, '0')} s`;
}
