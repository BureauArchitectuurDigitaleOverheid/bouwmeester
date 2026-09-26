interface TreeUnit {
  id: string;
  parent_id?: string | null;
}

/** Every eenheid below `rootIds` (the roots themselves excluded). */
export function descendantIds(units: TreeUnit[], rootIds: Iterable<string>): Set<string> {
  const children = new Map<string, string[]>();
  for (const u of units) {
    if (!u.parent_id) continue;
    const siblings = children.get(u.parent_id);
    if (siblings) siblings.push(u.id);
    else children.set(u.parent_id, [u.id]);
  }
  const found = new Set<string>();
  const queue = [...rootIds];
  while (queue.length > 0) {
    for (const child of children.get(queue.pop()!) ?? []) {
      if (!found.has(child)) {
        found.add(child);
        queue.push(child);
      }
    }
  }
  return found;
}
