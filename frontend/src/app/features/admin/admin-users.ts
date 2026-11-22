import { Component, inject, signal } from '@angular/core';

import { AdminService } from '../../core/admin.service';
import { AuthService } from '../../core/auth.service';
import { Group, UserAdmin, UserRole, apiErrorMessage } from '../../core/models';
import { toggleId } from '../../shared/format';

@Component({
  selector: 'app-admin-users',
  template: `
    <div class="page stack">
      <header class="page-header">
        <h1>Usuarios</h1>
      </header>

      @if (error()) {
        <p class="alert" role="alert">{{ error() }}</p>
      }

      <section class="card table-wrap">
        <table>
          <thead>
            <tr>
              <th>Usuario</th>
              <th>Rol</th>
              <th>Estado</th>
              <th>Grupos</th>
            </tr>
          </thead>
          <tbody>
            @for (u of users(); track u.id) {
              @let isMe = u.id === auth.user()?.id;
              <tr>
                <td>
                  <strong>{{ u.full_name }}</strong>
                  @if (isMe) {
                    <span class="badge badge--primary">Tú</span>
                  }
                  <div class="small muted">{{ u.email }}</div>
                </td>
                <td>
                  <select [value]="u.role" [disabled]="isMe" aria-label="Rol"
                    (change)="update(u, { role: $any($event.target).value })">
                    <option value="user">Usuario</option>
                    <option value="admin">Administrador</option>
                  </select>
                </td>
                <td>
                  <label class="checkbox small">
                    <input type="checkbox" [checked]="u.is_active" [disabled]="isMe"
                      (change)="update(u, { is_active: $any($event.target).checked })" />
                    {{ u.is_active ? 'Activo' : 'Desactivado' }}
                  </label>
                </td>
                <td>
                  @if (u.role === 'admin') {
                    <span class="small muted">Ve todos los documentos</span>
                  } @else {
                    <div class="row">
                      @for (g of groups(); track g.id) {
                        <label class="checkbox small">
                          <input type="checkbox" [checked]="hasGroup(u, g.id)"
                            (change)="setGroup(u, g.id, $any($event.target).checked)" />
                          {{ g.name }}
                        </label>
                      } @empty {
                        <span class="small muted">No hay grupos.</span>
                      }
                    </div>
                  }
                </td>
              </tr>
            }
          </tbody>
        </table>
      </section>
    </div>
  `,
})
export class AdminUsers {
  private readonly admin = inject(AdminService);
  protected readonly auth = inject(AuthService);

  protected readonly users = signal<UserAdmin[]>([]);
  protected readonly groups = signal<Group[]>([]);
  protected readonly error = signal<string | null>(null);

  constructor() {
    this.admin.users().subscribe((u) => this.users.set(u));
    this.admin.groups().subscribe((g) => this.groups.set(g));
  }

  protected hasGroup(u: UserAdmin, groupId: number): boolean {
    return u.groups.some((g) => g.id === groupId);
  }

  protected setGroup(u: UserAdmin, groupId: number, checked: boolean): void {
    const ids = toggleId(u.groups.map((g) => g.id), groupId, checked);
    this.update(u, { group_ids: ids });
  }

  protected update(
    u: UserAdmin,
    changes: { role?: UserRole; is_active?: boolean; group_ids?: number[] },
  ): void {
    this.error.set(null);
    this.admin.updateUser(u.id, changes).subscribe({
      next: (updated) => this.users.update((us) => us.map((x) => (x.id === updated.id ? updated : x))),
      error: (err) => {
        this.error.set(apiErrorMessage(err));
        this.users.update((us) => [...us]); // repinta con el valor anterior
      },
    });
  }
}
