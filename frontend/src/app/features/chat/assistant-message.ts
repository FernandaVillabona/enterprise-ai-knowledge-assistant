import { Component, computed, input, output, signal } from '@angular/core';

import { Message, Source } from '../../core/models';
import { parseCitations } from '../../shared/citations';
import { VerdictBadge } from '../../shared/verdict-badge';

/**
 * Respuesta del asistente: texto con citas clicables, fuentes, veredicto de
 * fidelidad, valoración 👍/👎 y detalles técnicos (consulta usada, tokens, latencia).
 */
@Component({
  selector: 'app-assistant-message',
  imports: [VerdictBadge],
  styleUrl: './assistant-message.scss',
  template: `
    <article class="msg" [class.msg--flagged]="message().flagged">
      <p class="msg__text">
        @for (seg of segments(); track $index) {
          @if (seg.kind === 'text') {
            <!-- En un <span>: con white-space: pre-wrap, los saltos de línea de la
                 plantilla alrededor del texto se verían como espacios -->
            <span>{{ seg.text }}</span>
          } @else {
            @let source = sourceByN().get(seg.n);
            @if (source) {
              <button
                type="button"
                class="cite"
                [class.active]="activeChunk() === source.chunk_id"
                [attr.aria-label]="'Fuente ' + seg.n + ': ' + source.document_title + ', página ' + source.page_number"
                (click)="citeClick.emit(source)"
              >{{ seg.n }}</button>
            } @else {
              <span class="cite cite--invalid" title="Cita a una fuente inexistente">{{ seg.n }}</span>
            }
          }
        }
      </p>

      @if (cited().length) {
        <ul class="msg__sources">
          @for (s of cited(); track s.chunk_id) {
            <li>
              <button type="button" class="source-chip" (click)="citeClick.emit(s)">
                <span class="cite">{{ s.n }}</span>
                {{ s.document_title }} · pág. {{ s.page_number }}
              </button>
            </li>
          }
        </ul>
      }

      <footer class="row msg__footer">
        <app-verdict-badge [evaluation]="message().evaluation" />
        @if (message().flagged) {
          <span class="badge badge--warn" title="Un administrador revisará esta respuesta">En revisión</span>
        }
        <span class="spacer"></span>
        @if (message().sources?.length) {
          <button
            type="button"
            class="btn btn--ghost btn--sm"
            [attr.aria-pressed]="message().feedback_rating === 1"
            [class.selected]="message().feedback_rating === 1"
            (click)="rate.emit(1)"
            title="Respuesta útil"
          >👍</button>
          <button
            type="button"
            class="btn btn--ghost btn--sm"
            [attr.aria-pressed]="message().feedback_rating === -1"
            [class.selected]="message().feedback_rating === -1"
            (click)="rate.emit(-1)"
            title="Respuesta no útil o incorrecta"
          >👎</button>
        }
        <button type="button" class="btn btn--ghost btn--sm" (click)="showDetails.set(!showDetails())">
          {{ showDetails() ? 'Ocultar detalles' : 'Detalles' }}
        </button>
      </footer>

      @if (showDetails()) {
        <dl class="msg__details small">
          <dt>Consulta de búsqueda</dt>
          <dd>{{ message().search_query || '—' }}</dd>
          <dt>Fragmentos recuperados</dt>
          <dd>{{ message().sources?.length ?? 0 }} ({{ cited().length }} citados)</dd>
          <dt>Modelo · tokens · latencia</dt>
          <dd>
            {{ message().model || 'sin llamada al LLM' }} ·
            {{ (message().prompt_tokens ?? 0) + (message().completion_tokens ?? 0) }} tokens ·
            {{ message().latency_ms ?? 0 }} ms
          </dd>
          @if (unsupported().length) {
            <dt>Afirmaciones no respaldadas por las fuentes</dt>
            <dd>
              <ul>
                @for (c of unsupported(); track $index) {
                  <li>{{ c }}</li>
                }
              </ul>
            </dd>
          }
        </dl>
      }
    </article>
  `,
})
export class AssistantMessage {
  readonly message = input.required<Message>();
  readonly activeChunk = input<number | null>(null);
  readonly citeClick = output<Source>();
  readonly rate = output<1 | -1>();

  protected readonly showDetails = signal(false);
  protected readonly segments = computed(() => parseCitations(this.message().content));
  protected readonly sourceByN = computed(
    () => new Map((this.message().sources ?? []).map((s) => [s.n, s])),
  );
  protected readonly cited = computed(() => (this.message().sources ?? []).filter((s) => s.cited));
  protected readonly unsupported = computed(() =>
    (this.message().evaluation?.claims ?? []).filter((c) => !c.supported).map((c) => c.claim),
  );
}
