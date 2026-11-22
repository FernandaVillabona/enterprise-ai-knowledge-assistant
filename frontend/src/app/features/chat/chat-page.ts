import { Component, DestroyRef, ElementRef, effect, inject, input, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed, toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';
import { EMPTY, Observable, catchError, filter, map, of, switchMap, take, takeWhile, timer } from 'rxjs';

import { ChatService } from '../../core/chat.service';
import { Conversation, Message, Source, apiErrorMessage } from '../../core/models';
import { AssistantMessage } from './assistant-message';

const EXAMPLES = [
  '¿Cuántos días de vacaciones me corresponden?',
  '¿Cuántos días puedo teletrabajar a la semana?',
  '¿Qué plazo tengo para presentar los gastos de un viaje?',
];

@Component({
  selector: 'app-chat-page',
  imports: [FormsModule, RouterLink, RouterLinkActive, AssistantMessage],
  styleUrl: './chat-page.scss',
  template: `
    <div class="chat" [class.chat--with-source]="activeSource()">
      <!-- Conversaciones -->
      <aside class="chat__list" aria-label="Conversaciones">
        <button class="btn btn--primary" type="button" (click)="newConversation()">
          + Nueva conversación
        </button>
        <ul>
          @for (c of conversations(); track c.id) {
            <li class="row">
              <a
                class="chat__item"
                [routerLink]="['/chat', c.id]"
                routerLinkActive="active"
                [title]="c.title"
              >{{ c.title }}</a>
              <button
                class="btn btn--ghost btn--sm"
                type="button"
                (click)="remove(c)"
                [attr.aria-label]="'Borrar ' + c.title"
              >✕</button>
            </li>
          } @empty {
            <li class="small muted">Aún no hay conversaciones.</li>
          }
        </ul>
      </aside>

      <!-- Hilo -->
      <section class="chat__main">
        <div class="chat__thread" #thread aria-live="polite">
          @if (!messages().length && !pendingQuestion()) {
            <div class="empty stack">
              <h2>¿En qué te ayudo?</h2>
              <p>Respondo solo con la información de los documentos a los que tienes acceso, y cito
                las fuentes.</p>
              <div class="row chat__examples">
                @for (q of examples; track q) {
                  <button class="btn btn--sm" type="button" (click)="ask(q)">{{ q }}</button>
                }
              </div>
            </div>
          }

          @for (m of messages(); track m.id) {
            @if (m.role === 'user') {
              <p class="bubble">{{ m.content }}</p>
            } @else {
              <app-assistant-message
                [message]="m"
                [activeChunk]="activeSource()?.chunk_id ?? null"
                (citeClick)="activeSource.set($event)"
                (rate)="rate(m, $event)"
              />
            }
          }

          @if (pendingQuestion(); as q) {
            <p class="bubble">{{ q }}</p>
            <p class="row muted"><span class="spinner"></span> Buscando en los documentos…</p>
          }
          @if (error()) {
            <p class="alert" role="alert">{{ error() }}</p>
          }
        </div>

        <form class="chat__composer" (ngSubmit)="ask(draft)">
          <textarea
            name="question"
            rows="2"
            placeholder="Escribe tu pregunta… (Enter para enviar, Mayús+Enter para nueva línea)"
            [(ngModel)]="draft"
            (keydown.enter)="onEnter($event)"
            [disabled]="!!pendingQuestion()"
            maxlength="4000"
            aria-label="Pregunta"
          ></textarea>
          <button class="btn btn--primary" type="submit" [disabled]="!draft.trim() || !!pendingQuestion()">
            Enviar
          </button>
        </form>
      </section>

      <!-- Fuente seleccionada -->
      @if (activeSource(); as s) {
        <aside class="chat__source card" aria-label="Fuente">
          <div class="row">
            <span class="cite">{{ s.n }}</span>
            <strong>{{ s.document_title }}</strong>
            <span class="spacer"></span>
            <button class="btn btn--ghost btn--sm" type="button" (click)="activeSource.set(null)"
              aria-label="Cerrar fuente">✕</button>
          </div>
          <p class="small muted">
            Página {{ s.page_number }}
            @if (s.similarity !== null) {
              · similitud {{ (s.similarity * 100).toFixed(0) }} %
            }
          </p>
          <blockquote class="chat__quote">{{ s.content }}</blockquote>
        </aside>
      }
    </div>
  `,
})
export class ChatPage {
  /** Parámetro :id de la ruta (withComponentInputBinding). */
  readonly id = input<string>();

  private readonly chat = inject(ChatService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private readonly thread = viewChild<ElementRef<HTMLElement>>('thread');

  protected readonly examples = EXAMPLES;
  protected readonly conversations = signal<Conversation[]>([]);
  protected readonly messages = signal<Message[]>([]);
  protected readonly pendingQuestion = signal<string | null>(null);
  protected readonly activeSource = signal<Source | null>(null);
  protected readonly error = signal<string | null>(null);
  protected draft = '';

  constructor() {
    this.loadConversations();

    // Cada vez que cambia el :id de la URL, cargamos esa conversación
    toObservable(this.id)
      .pipe(
        switchMap((id) => {
          this.activeSource.set(null);
          this.error.set(null);
          if (!id) return of([] as Message[]);
          return this.chat.get(Number(id)).pipe(
            map((c) => c.messages),
            catchError(() => {
              this.router.navigate(['/chat']);
              return of([] as Message[]);
            }),
          );
        }),
        takeUntilDestroyed(),
      )
      .subscribe((messages) => {
        this.messages.set(messages);
        this.pollPendingEvaluations();
      });

    // Baja al final del hilo cuando llegan mensajes nuevos
    effect(() => {
      this.messages();
      this.pendingQuestion();
      const el = this.thread()?.nativeElement;
      if (el) queueMicrotask(() => (el.scrollTop = el.scrollHeight));
    });
  }

  protected onEnter(event: Event): void {
    const e = event as KeyboardEvent;
    if (e.shiftKey || e.isComposing) return;
    e.preventDefault();
    this.ask(this.draft);
  }

  protected ask(question: string): void {
    const content = question.trim();
    if (!content || this.pendingQuestion()) return;
    this.draft = '';
    this.error.set(null);
    this.pendingQuestion.set(content);

    const currentId = this.id();
    const conversationId$: Observable<number> = currentId
      ? of(Number(currentId))
      : this.chat.create().pipe(map((c) => c.id));

    conversationId$
      .pipe(switchMap((cid) => this.chat.send(cid, content)))
      .subscribe({
        next: (turn) => {
          this.pendingQuestion.set(null);
          if (String(turn.conversation_id) !== currentId) {
            // Conversación nueva: actualizamos la URL; el cambio de :id recarga el hilo
            this.router.navigate(['/chat', turn.conversation_id]);
          } else {
            this.messages.update((ms) => [...ms, turn.user_message, turn.assistant_message]);
            this.pollPendingEvaluations();
          }
          this.loadConversations();
        },
        error: (err) => {
          this.pendingQuestion.set(null);
          this.draft = content; // no perder lo escrito
          this.error.set(apiErrorMessage(err, 'No se pudo obtener la respuesta'));
        },
      });
  }

  protected rate(message: Message, rating: 1 | -1): void {
    const id = this.id();
    if (!id) return;
    this.chat.feedback(Number(id), message.id, rating).subscribe({
      next: (updated) => this.replaceMessage(updated),
      error: (err) => this.error.set(apiErrorMessage(err)),
    });
  }

  protected newConversation(): void {
    this.router.navigate(['/chat']);
  }

  protected remove(c: Conversation): void {
    if (!confirm(`¿Borrar la conversación «${c.title}»? No se puede deshacer.`)) return;
    this.chat.delete(c.id).subscribe(() => {
      this.loadConversations();
      if (this.id() === String(c.id)) this.router.navigate(['/chat']);
    });
  }

  private loadConversations(): void {
    this.chat.list().subscribe((list) => this.conversations.set(list));
  }

  private replaceMessage(updated: Message): void {
    this.messages.update((ms) => ms.map((m) => (m.id === updated.id ? updated : m)));
  }

  /**
   * El juez de fidelidad corre en segundo plano en el backend: mientras haya
   * veredictos `pending`, releemos la conversación cada 2 s (máximo 6 veces).
   */
  private pollPendingEvaluations(): void {
    const id = this.id();
    const hasPending = () => this.messages().some((m) => m.evaluation?.verdict === 'pending');
    if (!id || !hasPending()) return;

    timer(2000, 2000)
      .pipe(
        take(6),
        switchMap(() => this.chat.get(Number(id)).pipe(catchError(() => EMPTY))),
        filter(() => this.id() === id), // el usuario puede haber cambiado de conversación
        takeWhile((c) => c.messages.some((m) => m.evaluation?.verdict === 'pending'), true),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((c) => {
        for (const m of c.messages) {
          if (m.role === 'assistant') this.replaceMessage(m);
        }
      });
  }
}
