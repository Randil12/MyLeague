// An explicit patch belongs only to the current player and analysis screen.
export function resolvePlayerPatch(selection, scope) {
  return selection.scope === scope && selection.patch !== '__all__' ? selection.patch : '';
}
