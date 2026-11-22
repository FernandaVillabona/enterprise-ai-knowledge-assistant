import { Component, computed, input } from '@angular/core';

import { Evaluation } from '../core/models';

interface BadgeInfo {
  label: string;
  tone: 'ok' | 'warn' | 'bad' | 'muted';
  hint: string;
}

/** Etiqueta con el veredicto del juez de fidelidad (fase 6). */
@Component({
  selector: 'app-verdict-badge',
  template: `
    @if (info(); as i) {
      <span class="badge" [class]="'badge--' + i.tone" [title]="i.hint">{{ i.label }}</span>
    }
  `,
})
export class VerdictBadge {
  readonly evaluation = input<Evaluation | null>(null);
  readonly flagged = input(false);

  protected readonly info = computed<BadgeInfo | null>(() => {
    const ev = this.evaluation();
    if (!ev) return null;
    const pct = ev.faithfulness !== null ? ` · ${Math.round(ev.faithfulness * 100)} %` : '';
    if (ev.invalid_citations.length) {
      return { label: 'Citas corregidas', tone: 'warn', hint: 'Se eliminaron citas a fuentes inexistentes' };
    }
    switch (ev.verdict) {
      case 'supported':
        return { label: `Respaldada${pct}`, tone: 'ok', hint: 'Todas las afirmaciones están en las fuentes' };
      case 'partially_supported':
        return { label: `Parcialmente respaldada${pct}`, tone: 'warn', hint: 'Algunas afirmaciones no están en las fuentes' };
      case 'unsupported':
        return { label: `No respaldada${pct}`, tone: 'bad', hint: 'La mayoría de afirmaciones no están en las fuentes' };
      case 'pending':
        return { label: 'Verificando…', tone: 'muted', hint: 'El juez de fidelidad está revisando la respuesta' };
      case 'error':
        return { label: 'Sin verificar', tone: 'muted', hint: 'El juez de fidelidad falló' };
      case 'not_evaluated':
        return ev.uncited
          ? { label: 'Sin citas', tone: 'warn', hint: 'La respuesta no cita ninguna fuente' }
          : null;
      default:
        return null;
    }
  });
}
