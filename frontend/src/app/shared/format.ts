import { DocumentStatus } from '../core/models';

export const STATUS_LABEL: Record<DocumentStatus, { label: string; tone: string }> = {
  pending: { label: 'En cola', tone: 'badge' },
  processing: { label: 'Procesando', tone: 'badge badge--primary' },
  ready: { label: 'Listo', tone: 'badge badge--ok' },
  failed: { label: 'Error', tone: 'badge badge--bad' },
};

export function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${(value * 100).toFixed(1)} %`;
}

export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** Alterna un id en una lista (para grupos de checkboxes). */
export function toggleId(ids: number[], id: number, checked: boolean): number[] {
  return checked ? [...new Set([...ids, id])] : ids.filter((x) => x !== id);
}
