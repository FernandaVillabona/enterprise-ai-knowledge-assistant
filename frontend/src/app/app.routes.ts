import { Routes } from '@angular/router';

import { adminGuard, authGuard, guestGuard } from './core/guards';
import { Shell } from './layout/shell';

/**
 * Las pantallas se cargan bajo demanda (loadComponent): el usuario normal nunca
 * descarga el código del panel de administración.
 */
export const routes: Routes = [
  {
    path: 'login',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/login').then((m) => m.Login),
  },
  {
    path: 'register',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/register').then((m) => m.Register),
  },
  {
    path: '',
    component: Shell,
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'chat' },
      {
        path: 'chat',
        loadComponent: () => import('./features/chat/chat-page').then((m) => m.ChatPage),
      },
      {
        path: 'chat/:id',
        loadComponent: () => import('./features/chat/chat-page').then((m) => m.ChatPage),
      },
      {
        path: 'documents',
        loadComponent: () =>
          import('./features/documents/my-documents').then((m) => m.MyDocuments),
      },
      {
        path: 'admin',
        canActivate: [adminGuard],
        children: [
          { path: '', pathMatch: 'full', redirectTo: 'documents' },
          {
            path: 'documents',
            loadComponent: () =>
              import('./features/admin/admin-documents').then((m) => m.AdminDocuments),
          },
          {
            path: 'groups',
            loadComponent: () => import('./features/admin/admin-groups').then((m) => m.AdminGroups),
          },
          {
            path: 'users',
            loadComponent: () => import('./features/admin/admin-users').then((m) => m.AdminUsers),
          },
          {
            path: 'quality',
            loadComponent: () =>
              import('./features/admin/admin-quality').then((m) => m.AdminQuality),
          },
        ],
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
