import { Component, inject, signal } from '@angular/core';
import {
  AbstractControl,
  NonNullableFormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { AuthService } from '../../core/auth.service';
import { apiErrorMessage } from '../../core/models';

/** Mismo límite que el backend: bcrypt solo usa los primeros 72 bytes. */
function maxUtf8Bytes(max: number) {
  return (control: AbstractControl): ValidationErrors | null =>
    new TextEncoder().encode(control.value ?? '').length > max ? { maxBytes: max } : null;
}

@Component({
  selector: 'app-register',
  imports: [ReactiveFormsModule, RouterLink],
  styleUrl: './auth.scss',
  template: `
    <main class="auth">
      <form class="card stack auth__card" [formGroup]="form" (ngSubmit)="submit()">
        <h1>Crear cuenta</h1>

        @if (error()) {
          <p class="alert" role="alert">{{ error() }}</p>
        }

        <label>
          Nombre completo
          <input type="text" formControlName="full_name" autocomplete="name" />
        </label>
        <label>
          Email
          <input type="email" formControlName="email" autocomplete="email" />
          @if (form.controls.email.touched && form.controls.email.invalid) {
            <span class="field-error">Introduce un email válido</span>
          }
        </label>
        <label>
          Contraseña
          <input type="password" formControlName="password" autocomplete="new-password" />
          @if (form.controls.password.touched && form.controls.password.invalid) {
            <span class="field-error">Entre 8 caracteres y 72 bytes</span>
          }
        </label>

        <button class="btn btn--primary" type="submit" [disabled]="form.invalid || loading()">
          Registrarme
        </button>
        <p class="small muted">
          Las cuentas nuevas solo ven documentos públicos hasta que un administrador les asigne
          grupos.
        </p>
        <p class="small muted">¿Ya tienes cuenta? <a routerLink="/login">Inicia sesión</a></p>
      </form>
    </main>
  `,
})
export class Register {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  protected readonly form = inject(NonNullableFormBuilder).group({
    full_name: ['', [Validators.required, Validators.maxLength(255)]],
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(8), maxUtf8Bytes(72)]],
  });
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);

  submit(): void {
    if (this.form.invalid) return;
    const { full_name, email, password } = this.form.getRawValue();
    this.loading.set(true);
    this.error.set(null);
    this.auth.register(full_name, email, password).subscribe({
      next: () => this.router.navigate(['/login'], { queryParams: { registered: 1 } }),
      error: (err) => {
        this.error.set(apiErrorMessage(err, 'No se pudo crear la cuenta'));
        this.loading.set(false);
      },
    });
  }
}
