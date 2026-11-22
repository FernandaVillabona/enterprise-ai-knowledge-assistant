import { Component, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { AuthService } from '../../core/auth.service';
import { apiErrorMessage } from '../../core/models';

@Component({
  selector: 'app-login',
  imports: [ReactiveFormsModule, RouterLink],
  styleUrl: './auth.scss',
  template: `
    <main class="auth">
      <form class="card stack auth__card" [formGroup]="form" (ngSubmit)="submit()">
        <div>
          <h1>Knowledge Assistant</h1>
          <p class="muted">Pregunta a los documentos de tu empresa.</p>
        </div>

        @if (expired) {
          <p class="alert alert--info">Tu sesión ha caducado. Vuelve a entrar.</p>
        }
        @if (registered) {
          <p class="alert alert--info">Cuenta creada. Ya puedes iniciar sesión.</p>
        }
        @if (error()) {
          <p class="alert" role="alert">{{ error() }}</p>
        }

        <label>
          Email
          <input type="email" formControlName="email" autocomplete="username" />
        </label>
        <label>
          Contraseña
          <input type="password" formControlName="password" autocomplete="current-password" />
        </label>

        <button class="btn btn--primary" type="submit" [disabled]="form.invalid || loading()">
          @if (loading()) {
            <span class="spinner"></span>
          }
          Entrar
        </button>
        <p class="small muted">¿No tienes cuenta? <a routerLink="/register">Regístrate</a></p>
      </form>
    </main>
  `,
})
export class Login {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  protected readonly form = inject(NonNullableFormBuilder).group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', Validators.required],
  });
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly expired = this.route.snapshot.queryParamMap.has('expired');
  protected readonly registered = this.route.snapshot.queryParamMap.has('registered');

  submit(): void {
    if (this.form.invalid) return;
    const { email, password } = this.form.getRawValue();
    this.loading.set(true);
    this.error.set(null);
    this.auth.login(email, password).subscribe({
      next: () => {
        const returnUrl = this.route.snapshot.queryParamMap.get('returnUrl');
        // Solo rutas internas: evita redirecciones abiertas a otros dominios
        this.router.navigateByUrl(returnUrl?.startsWith('/') ? returnUrl : '/chat');
      },
      error: (err) => {
        this.error.set(apiErrorMessage(err, 'No se pudo iniciar sesión'));
        this.loading.set(false);
      },
    });
  }
}
