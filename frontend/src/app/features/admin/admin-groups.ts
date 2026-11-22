import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { AdminService } from '../../core/admin.service';
import { Group, UserAdmin, apiErrorMessage } from '../../core/models';
import { toggleId } from '../../shared/format';

@Component({
  selector: 'app-admin-groups',
  imports: [FormsModule],
  template: `
    <div class="page stack">
      <header class="page-header">
        <div>
          <h1>Grupos</h1>
          <p class="muted">Los miembros de un grupo ven los documentos restringidos a ese grupo.</p>
        </div>
      </header>

      <form class="card row" style="align-items: flex-end" (ngSubmit)="create()">
        <label style="flex: 1; min-width: 180px">
          Nombre
          <input type="text" name="name" [(ngModel)]="name" maxlength="100" placeholder="p. ej. Recursos Humanos" />
        </label>
        <label style="flex: 2; min-width: 220px">
          Descripción (opcional)
          <input type="text" name="description" [(ngModel)]="description" maxlength="255" />
        </label>
        <button class="btn btn--primary" type="submit" [disabled]="!name.trim()">Crear grupo</button>
      </form>

      @if (error()) {
        <p class="alert" role="alert">{{ error() }}</p>
      }

      @for (g of groups(); track g.id) {
        <section class="card stack">
          <div class="row">
            <div>
              <h2>{{ g.name }}</h2>
              @if (g.description) {
                <p class="small muted" style="margin: 0">{{ g.description }}</p>
              }
            </div>
            <span class="spacer"></span>
            <span class="badge">{{ g.users.length }} miembros</span>
            @if (editing() === g.id) {
              <button class="btn btn--primary btn--sm" type="button" (click)="saveMembers(g)">Guardar miembros</button>
              <button class="btn btn--sm" type="button" (click)="editing.set(null)">Cancelar</button>
            } @else {
              <button class="btn btn--sm" type="button" (click)="startEdit(g)">Editar miembros</button>
            }
            <button class="btn btn--sm btn--danger" type="button" (click)="remove(g)">Borrar</button>
          </div>

          @if (editing() === g.id) {
            <div class="row">
              @for (u of users(); track u.id) {
                <label class="checkbox small">
                  <input type="checkbox" [checked]="memberIds.includes(u.id)"
                    (change)="memberIds = toggle(memberIds, u.id, $any($event.target).checked)" />
                  {{ u.full_name }} <span class="muted">({{ u.email }})</span>
                </label>
              }
            </div>
          } @else {
            <div class="row">
              @for (u of g.users; track u.id) {
                <span class="badge" [title]="u.email">{{ u.full_name }}</span>
              } @empty {
                <span class="small muted">Sin miembros.</span>
              }
            </div>
          }
        </section>
      } @empty {
        <p class="card empty">Aún no hay grupos.</p>
      }
    </div>
  `,
})
export class AdminGroups {
  private readonly admin = inject(AdminService);
  protected readonly toggle = toggleId;

  protected readonly groups = signal<Group[]>([]);
  protected readonly users = signal<UserAdmin[]>([]);
  protected readonly editing = signal<number | null>(null);
  protected readonly error = signal<string | null>(null);
  protected name = '';
  protected description = '';
  protected memberIds: number[] = [];

  constructor() {
    this.load();
    this.admin.users().subscribe((u) => this.users.set(u));
  }

  protected create(): void {
    this.admin.createGroup(this.name.trim(), this.description.trim() || null).subscribe({
      next: () => {
        this.name = '';
        this.description = '';
        this.load();
      },
      error: (err) => this.error.set(apiErrorMessage(err)),
    });
  }

  protected startEdit(g: Group): void {
    this.memberIds = g.users.map((u) => u.id);
    this.editing.set(g.id);
  }

  protected saveMembers(g: Group): void {
    this.admin.setMembers(g.id, this.memberIds).subscribe({
      next: () => {
        this.editing.set(null);
        this.load();
      },
      error: (err) => this.error.set(apiErrorMessage(err)),
    });
  }

  protected remove(g: Group): void {
    const msg = `¿Borrar el grupo «${g.name}»? Sus miembros perderán el acceso a los documentos restringidos a él.`;
    if (!confirm(msg)) return;
    this.admin.deleteGroup(g.id).subscribe({
      next: () => this.load(),
      error: (err) => this.error.set(apiErrorMessage(err)),
    });
  }

  private load(): void {
    this.error.set(null);
    this.admin.groups().subscribe((g) => this.groups.set(g));
  }
}
