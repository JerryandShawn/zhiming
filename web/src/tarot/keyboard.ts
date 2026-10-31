/** Keep the physical deck grid intact when saved choices leave disabled holes. */
export function nextBackIndex(index: number, key: string, columns: number, locked: boolean[]): number {
  const offset = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: columns, ArrowUp: -columns }[key];
  if (key === 'Home') return locked.findIndex((value) => !value);
  if (key === 'End') {
    for (let target = locked.length - 1; target >= 0; target--) if (!locked[target]) return target;
    return -1;
  }
  if (offset === undefined) return index;
  for (let target = index + offset; target >= 0 && target < locked.length; target += offset) {
    if (!locked[target]) return target;
  }
  return index;
}
