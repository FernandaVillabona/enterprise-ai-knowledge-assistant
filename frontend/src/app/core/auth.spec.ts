import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { authInterceptor } from './auth.interceptor';
import { AuthService } from './auth.service';

describe('AuthService + authInterceptor', () => {
  let auth: AuthService;
  let client: HttpClient;
  let http: HttpTestingController;
  let router: Router;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideRouter([{ path: 'login', children: [] }]),
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    auth = TestBed.inject(AuthService);
    client = TestBed.inject(HttpClient);
    http = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
  });

  afterEach(() => http.verify());

  function login(role: 'admin' | 'user' = 'user') {
    auth.login('ana@x.com', 'secreto-123').subscribe();
    const req = http.expectOne('/api/auth/login');
    // OAuth2 password flow: form-urlencoded con `username` (no JSON)
    expect(req.request.body.get('username')).toBe('ana@x.com');
    expect(req.request.body.get('password')).toBe('secreto-123');
    expect(req.request.headers.has('Authorization')).toBe(false);
    req.flush({ access_token: 'tok-123', token_type: 'bearer' });

    const me = http.expectOne('/api/auth/me');
    expect(me.request.headers.get('Authorization')).toBe('Bearer tok-123');
    me.flush({ id: 1, email: 'ana@x.com', full_name: 'Ana', role, is_active: true, created_at: '' });
  }

  it('inicia sesión, guarda el token y carga el usuario', () => {
    login();
    expect(auth.token).toBe('tok-123');
    expect(auth.isLoggedIn()).toBe(true);
    expect(auth.isAdmin()).toBe(false);
  });

  it('distingue administradores', () => {
    login('admin');
    expect(auth.isAdmin()).toBe(true);
  });

  it('ante un 401 cierra la sesión y vuelve al login', () => {
    login();
    const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    client.get('/api/conversations').subscribe({ error: () => undefined });
    http.expectOne('/api/conversations').flush(null, { status: 401, statusText: 'Unauthorized' });

    expect(auth.isLoggedIn()).toBe(false);
    expect(auth.token).toBeNull();
    expect(navigate).toHaveBeenCalledWith(['/login'], { queryParams: { expired: 1 } });
  });

  it('un 401 en el propio login no redirige (credenciales incorrectas)', () => {
    const navigate = vi.spyOn(router, 'navigate');
    auth.login('ana@x.com', 'mala').subscribe({ error: () => undefined });
    http
      .expectOne('/api/auth/login')
      .flush({ detail: 'x' }, { status: 401, statusText: 'Unauthorized' });
    expect(navigate).not.toHaveBeenCalled();
  });

  it('no envía el token a otros dominios', () => {
    login();
    client.get('https://example.com/data').subscribe();
    const req = http.expectOne('https://example.com/data');
    expect(req.request.headers.has('Authorization')).toBe(false);
    req.flush({});
  });

  it('restoreSession descarta un token caducado', async () => {
    localStorage.setItem('kb_token', 'caducado');
    const done = auth.restoreSession();
    http.expectOne('/api/auth/me').flush(null, { status: 401, statusText: 'Unauthorized' });
    await done;
    expect(auth.token).toBeNull();
    expect(auth.isLoggedIn()).toBe(false);
  });
});
