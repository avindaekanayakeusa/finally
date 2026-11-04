export interface TreemapItem {
  id: string;
  weight: number;
}

export interface TreemapRect {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * Lay out items in a rectangle (percent units, 0-100) by recursively splitting
 * the weight-sorted list into two halves of roughly equal weight along the longer side.
 */
export function treemap(items: TreemapItem[], x = 0, y = 0, w = 100, h = 100): TreemapRect[] {
  const sorted = items.filter((i) => i.weight > 0).sort((a, b) => b.weight - a.weight);
  return split(sorted, x, y, w, h);
}

function split(items: TreemapItem[], x: number, y: number, w: number, h: number): TreemapRect[] {
  if (items.length === 0) return [];
  if (items.length === 1) return [{ id: items[0].id, x, y, w, h }];

  const total = items.reduce((s, i) => s + i.weight, 0);
  let acc = 0;
  let cut = 0;
  while (cut < items.length - 1 && acc + items[cut].weight <= total / 2) acc += items[cut++].weight;
  if (cut === 0) acc = items[cut++].weight;

  const ratio = acc / total;
  const [a, b] = [items.slice(0, cut), items.slice(cut)];
  if (w >= h) {
    return [...split(a, x, y, w * ratio, h), ...split(b, x + w * ratio, y, w * (1 - ratio), h)];
  }
  return [...split(a, x, y, w, h * ratio), ...split(b, x, y + h * ratio, w, h * (1 - ratio))];
}
