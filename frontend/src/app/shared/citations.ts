/**
 * Convierte la respuesta del asistente en segmentos de texto y de cita.
 *
 *   "Son 23 días [1][2]." → [text "Son 23 días ", cite 1, cite 2, text "."]
 *
 * La plantilla pinta los segmentos con interpolación ({{ }}), nunca con innerHTML:
 * Angular escapa el texto, así que aunque un documento o el modelo devolvieran
 * "<script>", se mostraría como texto y no se ejecutaría (protección XSS).
 */
export type Segment = { kind: 'text'; text: string } | { kind: 'cite'; n: number };

const CITATION = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

export function parseCitations(text: string): Segment[] {
  const segments: Segment[] = [];
  let last = 0;
  for (const match of text.matchAll(CITATION)) {
    const index = match.index ?? 0;
    if (index > last) segments.push({ kind: 'text', text: text.slice(last, index) });
    for (const n of match[1].split(',')) segments.push({ kind: 'cite', n: Number(n.trim()) });
    last = index + match[0].length;
  }
  if (last < text.length) segments.push({ kind: 'text', text: text.slice(last) });
  return segments;
}
