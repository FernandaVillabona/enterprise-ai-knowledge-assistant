import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { AdminService } from '../../core/admin.service';
import { FlaggedMessage, QualityMetrics, apiErrorMessage } from '../../core/models';
import { percent } from '../../shared/format';
import { VerdictBadge } from '../../shared/verdict-badge';

/** Calidad del asistente (fase 6): métricas y cola de respuestas a revisar. */
@Component({
  selector: 'app-admin-quality',
  imports: [FormsModule, DatePipe, DecimalPipe, VerdictBadge],
  template: `
    <div class="page stack">
      <header class="page-header">
        <div>
          <h1>Calidad de las respuestas</h1>
          <p class="muted">Fidelidad medida por un LLM juez, checks de citas y valoraciones de usuarios.</p>
        </div>
        <label class="row" style="flex-direction: row; align-items: center">
          Periodo
          <select [(ngModel)]="days" (ngModelChange)="loadMetrics()" style="width: auto">
            <option [ngValue]="7">7 días</option>
            <option [ngValue]="30">30 días</option>
            <option [ngValue]="90">90 días</option>
          </select>
        </label>
      </header>

      @if (error()) {
        <p class="alert" role="alert">{{ error() }}</p>
      }

      @if (metrics(); as m) {
        <div class="grid">
          <div class="card">
            <p class="small muted">Respuestas</p>
            <p class="metric">{{ m.answers }}</p>
            <p class="small muted">{{ pct(m.no_info_rate) }} sin información</p>
          </div>
          <div class="card">
            <p class="small muted">Fidelidad media</p>
            <p class="metric">{{ pct(m.avg_faithfulness) }}</p>
            <p class="small muted">{{ m.evaluated }} evaluadas por el juez</p>
          </div>
          <div class="card">
            <p class="small muted">Tasa de alucinación</p>
            <p class="metric">{{ pct(m.hallucination_rate) }}</p>
            <p class="small muted">con alguna afirmación no respaldada</p>
          </div>
          <div class="card">
            <p class="small muted">Pendientes de revisión</p>
            <p class="metric">{{ m.flagged }}</p>
            <p class="small muted">👍 {{ m.feedback_positive }} · 👎 {{ m.feedback_negative }}</p>
          </div>
          <div class="card">
            <p class="small muted">Latencia media</p>
            <p class="metric">{{ m.avg_latency_ms === null ? '—' : (m.avg_latency_ms | number: '1.0-0') + ' ms' }}</p>
            <p class="small muted">{{ m.prompt_tokens + m.completion_tokens | number }} tokens</p>
          </div>
        </div>
      }

      <section class="stack">
        <h2>Respuestas marcadas para revisión</h2>
        @for (f of flagged(); track f.message_id) {
          <article class="card stack" style="gap: 0.5rem">
            <div class="row">
              <app-verdict-badge [evaluation]="f.evaluation" />
              @if (f.feedback_rating === -1) {
                <span class="badge badge--bad">👎 del usuario</span>
              }
              <span class="small muted">{{ f.user_email }} · {{ f.created_at | date: 'dd/MM/yyyy HH:mm' }}</span>
              <span class="spacer"></span>
              <button class="btn btn--sm" type="button" (click)="resolve(f)">Marcar como revisada</button>
            </div>
            <p style="margin: 0"><strong>Pregunta:</strong> {{ f.question }}</p>
            <p style="margin: 0; white-space: pre-wrap"><strong>Respuesta:</strong> {{ f.answer }}</p>
            @if (unsupported(f).length) {
              <div class="alert small">
                <strong>No respaldado por las fuentes:</strong>
                <ul style="margin: 0.25rem 0 0; padding-left: 1.1rem">
                  @for (c of unsupported(f); track $index) {
                    <li>{{ c }}</li>
                  }
                </ul>
              </div>
            }
            @if (f.evaluation?.uncited) {
              <p class="small muted" style="margin: 0">La respuesta no cita ninguna fuente.</p>
            }
            @if (f.feedback_comment) {
              <p class="small" style="margin: 0"><strong>Comentario:</strong> {{ f.feedback_comment }}</p>
            }
          </article>
        } @empty {
          <p class="card empty">No hay respuestas pendientes de revisión. 🎉</p>
        }
      </section>
    </div>
  `,
  styles: `
    .metric {
      font-size: 1.6rem;
      font-weight: 700;
      margin: 0.1rem 0;
    }
    .card p {
      margin: 0;
    }
  `,
})
export class AdminQuality {
  private readonly admin = inject(AdminService);
  protected readonly pct = percent;

  protected readonly metrics = signal<QualityMetrics | null>(null);
  protected readonly flagged = signal<FlaggedMessage[]>([]);
  protected readonly error = signal<string | null>(null);
  protected days = 30;

  constructor() {
    this.loadMetrics();
    this.loadFlagged();
  }

  protected loadMetrics(): void {
    this.admin.metrics(this.days).subscribe({
      next: (m) => this.metrics.set(m),
      error: (err) => this.error.set(apiErrorMessage(err)),
    });
  }

  protected unsupported(f: FlaggedMessage): string[] {
    return (f.evaluation?.claims ?? []).filter((c) => !c.supported).map((c) => c.claim);
  }

  protected resolve(f: FlaggedMessage): void {
    this.admin.resolve(f.message_id).subscribe({
      next: () => {
        this.flagged.update((fs) => fs.filter((x) => x.message_id !== f.message_id));
        this.loadMetrics();
      },
      error: (err) => this.error.set(apiErrorMessage(err)),
    });
  }

  private loadFlagged(): void {
    this.admin.flagged().subscribe({
      next: (f) => this.flagged.set(f),
      error: (err) => this.error.set(apiErrorMessage(err)),
    });
  }
}
