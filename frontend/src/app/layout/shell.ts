import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { AuthService } from '../core/auth.service';

/** Estructura de la app autenticada: barra lateral de navegación + contenido. */
@Component({
  selector: 'app-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  styleUrl: './shell.scss',
  template: `
    <div class="shell">
      <nav class="nav" aria-label="Principal">
        <a class="nav__brand" routerLink="/chat">Knowledge Assistant</a>

        <a class="nav__link" routerLink="/chat" routerLinkActive="active">Chat</a>
        <a class="nav__link" routerLink="/documents" routerLinkActive="active">Mis documentos</a>

        @if (auth.isAdmin()) {
          <p class="nav__section">Administración</p>
          <a class="nav__link" routerLink="/admin/documents" routerLinkActive="active">Documentos</a>
          <a class="nav__link" routerLink="/admin/groups" routerLinkActive="active">Grupos</a>
          <a class="nav__link" routerLink="/admin/users" routerLinkActive="active">Usuarios</a>
          <a class="nav__link" routerLink="/admin/quality" routerLinkActive="active">Calidad</a>
        }

        <div class="spacer"></div>
        @if (auth.user(); as user) {
          <div class="nav__user">
            <strong>{{ user.full_name }}</strong>
            <span class="small muted">{{ user.email }}</span>
          </div>
        }
        <button class="btn btn--ghost btn--sm" type="button" (click)="auth.logout()">
          Cerrar sesión
        </button>
      </nav>

      <div class="content">
        <router-outlet />
      </div>
    </div>
  `,
})
export class Shell {
  protected readonly auth = inject(AuthService);
}
