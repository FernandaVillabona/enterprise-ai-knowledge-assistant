import { DatePipe } from '@angular/common';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { Subscription, switchMap, timer } from 'rxjs';

import { AdminService } from '../../core/admin.service';
import { DocumentsService } from '../../core/documents.service';
import { Chunk, DocumentAdmin, Group, Visibility, apiErrorMessage } from '../../core/models';
import { STATUS_LABEL, fileSize, toggleId } from '../../shared/format';

@Component({
  selector: 'app-admin-documents',
  imports: [FormsModule, DatePipe],
  template: `
    <div class="page stack">
      <header class="page-header">
        <h1>Documentos</h1>
      </header>

      <!-- Subida -->
      <form class="card stack" (ngSubmit)="upload()">
        <h2>Subir documento</h2>
        <div class="row" style="align-items: flex-end">
          <label style="flex: 2; min-width: 220px">
            Archivo (PDF, DOCX o TXT, máx. 20 MB)
            <input type="file" accept=".pdf,.docx,.txt" (change)="onFile($event)" />
          </label>
          <label style="flex: 2; min-width: 200px">
            Título (opcional)
            <input type="text" name="title" [(ngModel)]="title" maxlength="255"
              placeholder="Por defecto, el nombre del archivo" />
          </label>
          <label style="flex: 1; min-width: 160px">
            Visibilidad
            <select name="visibility" [(ngModel)]="visibility">
              <option value="restricted">Restringido a grupos</option>
              <option value="public">Público (todos)</option>
            </select>
          </label>
        </div>
        @if (visibility === 'restricted') {
          <fieldset class="row" style="border: none; padding: 0; margin: 0">
            <legend class="small muted">Grupos con acceso (sin grupos: solo administradores)</legend>
            @for (g of groups(); track g.id) {
              <label class="checkbox">
                <input type="checkbox" [checked]="groupIds.includes(g.id)"
                  (change)="groupIds = toggle(groupIds, g.id, $any($event.target).checked)" />
                {{ g.name }}
              </label>
            } @empty {
              <span class="small muted">No hay grupos. Créalos en «Grupos».</span>
            }
          </fieldset>
        }
        @if (uploadError()) {
          <p class="alert" role="alert">{{ uploadError() }}</p>
        }
        <div>
          <button class="btn btn--primary" type="submit" [disabled]="!file || uploading()">
            @if (uploading()) {
              <span class="spinner"></span>
            }
            Subir y procesar
          </button>
        </div>
      </form>

      <!-- Listado -->
      <section class="card">
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Documento</th>
                <th>Estado</th>
                <th>Acceso</th>
                <th>Contenido</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (d of documents(); track d.id) {
                <tr>
                  <td>
                    <strong>{{ d.title }}</strong>
                    <div class="small muted">
                      {{ d.original_filename }} · {{ size(d.size_bytes) }} · {{ d.created_at | date: 'dd/MM/yyyy HH:mm' }}
                    </div>
                  </td>
                  <td>
                    <span [class]="status[d.status].tone">{{ status[d.status].label }}</span>
                    @if (d.error) {
                      <div class="small field-error">{{ d.error }}</div>
                    }
                  </td>
                  <td>
                    @if (editing()?.id === d.id) {
                      <div class="stack" style="gap: 0.4rem; min-width: 200px">
                        <select [(ngModel)]="editVisibility" name="editVisibility">
                          <option value="restricted">Restringido</option>
                          <option value="public">Público</option>
                        </select>
                        @if (editVisibility === 'restricted') {
                          @for (g of groups(); track g.id) {
                            <label class="checkbox small">
                              <input type="checkbox" [checked]="editGroupIds.includes(g.id)"
                                (change)="editGroupIds = toggle(editGroupIds, g.id, $any($event.target).checked)" />
                              {{ g.name }}
                            </label>
                          }
                        }
                        <div class="row">
                          <button class="btn btn--primary btn--sm" type="button" (click)="saveAccess(d)">Guardar</button>
                          <button class="btn btn--sm" type="button" (click)="editing.set(null)">Cancelar</button>
                        </div>
                      </div>
                    } @else {
                      @if (d.visibility === 'public') {
                        <span class="badge badge--ok">Público</span>
                      } @else if (d.groups.length) {
                        @for (g of d.groups; track g.id) {
                          <span class="badge badge--primary">{{ g.name }}</span>
                        }
                      } @else {
                        <span class="badge badge--warn" title="Solo lo ven los administradores">Solo admins</span>
                      }
                      <button class="btn btn--ghost btn--sm" type="button" (click)="startEdit(d)">Cambiar</button>
                    }
                  </td>
                  <td class="small">
                    @if (d.status === 'ready') {
                      {{ d.num_pages }} pág. · {{ d.num_chunks }} fragmentos
                      <button class="btn btn--ghost btn--sm" type="button" (click)="toggleChunks(d)">
                        {{ chunksFor() === d.id ? 'Ocultar' : 'Ver fragmentos' }}
                      </button>
                    } @else {
                      —
                    }
                  </td>
                  <td>
                    <div class="row" style="flex-wrap: nowrap">
                      <button class="btn btn--sm" type="button" (click)="reprocess(d)"
                        [disabled]="d.status === 'processing' || d.status === 'pending'">Reprocesar</button>
                      <button class="btn btn--sm btn--danger" type="button" (click)="remove(d)">Borrar</button>
                    </div>
                  </td>
                </tr>
                @if (chunksFor() === d.id) {
                  <tr>
                    <td colspan="5">
                      <div class="stack" style="max-height: 420px; overflow-y: auto">
                        @for (c of chunks(); track c.id) {
                          <div class="small" style="border-left: 3px solid var(--border); padding-left: 0.6rem">
                            <strong>#{{ c.chunk_index }}</strong>
                            <span class="muted"> · pág. {{ c.page_number }} · {{ c.token_count }} tokens</span>
                            <p style="margin: 0.2rem 0 0; white-space: pre-wrap">{{ c.content }}</p>
                          </div>
                        }
                      </div>
                    </td>
                  </tr>
                }
              } @empty {
                <tr><td colspan="5" class="empty">Aún no hay documentos.</td></tr>
              }
            </tbody>
          </table>
        </div>
        @if (listError()) {
          <p class="alert" role="alert">{{ listError() }}</p>
        }
      </section>
    </div>
  `,
})
export class AdminDocuments {
  private readonly docs = inject(DocumentsService);
  private readonly admin = inject(AdminService);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly status = STATUS_LABEL;
  protected readonly size = fileSize;
  protected readonly toggle = toggleId;

  protected readonly documents = signal<DocumentAdmin[]>([]);
  protected readonly groups = signal<Group[]>([]);
  protected readonly uploading = signal(false);
  protected readonly uploadError = signal<string | null>(null);
  protected readonly listError = signal<string | null>(null);
  protected readonly editing = signal<DocumentAdmin | null>(null);
  protected readonly chunksFor = signal<number | null>(null);
  protected readonly chunks = signal<Chunk[]>([]);
  private readonly inProgress = computed(() =>
    this.documents().some((d) => d.status === 'pending' || d.status === 'processing'),
  );

  protected file: File | null = null;
  protected title = '';
  protected visibility: Visibility = 'restricted';
  protected groupIds: number[] = [];
  protected editVisibility: Visibility = 'restricted';
  protected editGroupIds: number[] = [];
  private polling?: Subscription;

  constructor() {
    this.refresh();
    this.admin.groups().subscribe((g) => this.groups.set(g));
  }

  protected onFile(event: Event): void {
    this.file = (event.target as HTMLInputElement).files?.[0] ?? null;
  }

  protected upload(): void {
    if (!this.file) return;
    this.uploading.set(true);
    this.uploadError.set(null);
    this.docs
      .upload({ file: this.file, title: this.title, visibility: this.visibility, groupIds: this.groupIds })
      .subscribe({
        next: () => {
          this.uploading.set(false);
          this.title = '';
          this.refresh();
        },
        error: (err) => {
          this.uploading.set(false);
          this.uploadError.set(apiErrorMessage(err, 'No se pudo subir el documento'));
        },
      });
  }

  protected startEdit(d: DocumentAdmin): void {
    this.editVisibility = d.visibility;
    this.editGroupIds = d.groups.map((g) => g.id);
    this.editing.set(d);
  }

  protected saveAccess(d: DocumentAdmin): void {
    const groupIds = this.editVisibility === 'public' ? [] : this.editGroupIds;
    this.docs.updateAccess(d.id, this.editVisibility, groupIds).subscribe({
      next: (updated) => {
        this.documents.update((ds) => ds.map((x) => (x.id === updated.id ? updated : x)));
        this.editing.set(null);
      },
      error: (err) => this.listError.set(apiErrorMessage(err)),
    });
  }

  protected toggleChunks(d: DocumentAdmin): void {
    if (this.chunksFor() === d.id) {
      this.chunksFor.set(null);
      return;
    }
    this.chunksFor.set(d.id);
    this.chunks.set([]);
    this.docs.chunks(d.id).subscribe((c) => this.chunks.set(c));
  }

  protected reprocess(d: DocumentAdmin): void {
    this.docs.reprocess(d.id).subscribe({
      next: () => this.refresh(),
      error: (err) => this.listError.set(apiErrorMessage(err)),
    });
  }

  protected remove(d: DocumentAdmin): void {
    if (!confirm(`¿Borrar «${d.title}» y todos sus fragmentos? No se puede deshacer.`)) return;
    this.docs.delete(d.id).subscribe({
      next: () => this.refresh(),
      error: (err) => this.listError.set(apiErrorMessage(err)),
    });
  }

  /** Recarga la lista y, mientras haya documentos procesándose, la refresca cada 3 s. */
  private refresh(): void {
    this.docs.list().subscribe({
      next: (list) => {
        this.documents.set(list);
        this.listError.set(null);
        if (this.inProgress() && !this.polling) {
          this.polling = timer(3000, 3000)
            .pipe(
              switchMap(() => this.docs.list()),
              takeUntilDestroyed(this.destroyRef),
            )
            .subscribe((l) => {
              this.documents.set(l);
              if (!this.inProgress()) {
                this.polling?.unsubscribe();
                this.polling = undefined;
              }
            });
        }
      },
      error: (err) => this.listError.set(apiErrorMessage(err)),
    });
  }
}
