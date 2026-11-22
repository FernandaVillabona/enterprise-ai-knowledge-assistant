import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, catchError, firstValueFrom, of, switchMap, tap } from 'rxjs';

import { User } from './models';

const TOKEN_KEY = 'kb_token';

/**
 * Sesión del usuario.
 *
 * El JWT se guarda en localStorage por simplicidad. Contrapartida: si hubiera una
 * vulnerabilidad XSS, un script podría leerlo. La alternativa más segura es una
 * cookie httpOnly emitida por el backend (requiere protección CSRF). Por eso nunca
 * insertamos HTML del servidor con innerHTML (ver shared/citations.ts).
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  private readonly _user = signal<User | null>(null);
  readonly user = this._user.asReadonly();
  readonly isLoggedIn = computed(() => this._user() !== null);
  readonly isAdmin = computed(() => this._user()?.role === 'admin');

  get token(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  }

  /** Al arrancar la app: si hay token, recupera el usuario (o lo descarta si caducó). */
  restoreSession(): Promise<unknown> {
    if (!this.token) return Promise.resolve();
    return firstValueFrom(this.loadMe().pipe(catchError(() => of(this.clear()))));
  }

  login(email: string, password: string): Observable<User> {
    // OAuth2 password flow: el backend espera form-urlencoded con `username`
    const body = new HttpParams().set('username', email).set('password', password);
    return this.http.post<{ access_token: string }>('/api/auth/login', body).pipe(
      tap((r) => this.store(r.access_token)),
      switchMap(() => this.loadMe()),
    );
  }

  register(full_name: string, email: string, password: string): Observable<User> {
    return this.http.post<User>('/api/auth/register', { full_name, email, password });
  }

  logout(): void {
    this.clear();
    this.router.navigate(['/login']);
  }

  /** Borra la sesión sin navegar (lo usa el interceptor ante un 401). */
  clear(): void {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* almacenamiento no disponible */
    }
    this._user.set(null);
  }

  private store(token: string): void {
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* almacenamiento no disponible: la sesión no sobrevivirá a recargar */
    }
  }

  private loadMe(): Observable<User> {
    return this.http.get<User>('/api/auth/me').pipe(tap((u) => this._user.set(u)));
  }
}
