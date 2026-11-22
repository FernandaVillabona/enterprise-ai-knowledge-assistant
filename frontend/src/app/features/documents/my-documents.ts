import { DatePipe } from '@angular/common';
import { Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';

import { DocumentsService } from '../../core/documents.service';

/** Documentos que el usuario puede consultar en el chat (según sus grupos). */
@Component({
  selector: 'app-my-documents',
  imports: [DatePipe, RouterLink],
  template: `
    <div class="page">
      <header class="page-header">
        <div>
          <h1>Mis documentos</h1>
          <p class="muted">El asistente solo usa estos documentos para responderte.</p>
        </div>
        <a class="btn btn--primary" routerLink="/chat">Ir al chat</a>
      </header>

      @if (documents(); as docs) {
        @if (docs.length) {
          <div class="grid">
            @for (d of docs; track d.id) {
              <article class="card stack" style="gap: 0.25rem">
                <span class="badge" style="align-self: flex-start">{{ d.file_type.toUpperCase() }}</span>
                <h3>{{ d.title }}</h3>
                <p class="small muted">
                  {{ d.num_pages }} pág. · actualizado {{ d.processed_at | date: 'dd/MM/yyyy' }}
                </p>
              </article>
            }
          </div>
        } @else {
          <p class="card empty">
            Todavía no tienes acceso a ningún documento. Pide a un administrador que te añada a un
            grupo.
          </p>
        }
      } @else {
        <p class="row muted"><span class="spinner"></span> Cargando…</p>
      }
    </div>
  `,
})
export class MyDocuments {
  protected readonly documents = toSignal(inject(DocumentsService).accessible());
}
