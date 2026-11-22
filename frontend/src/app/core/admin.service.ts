import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { FlaggedMessage, Group, QualityMetrics, UserAdmin, UserRole } from './models';

@Injectable({ providedIn: 'root' })
export class AdminService {
  private readonly http = inject(HttpClient);

  groups(): Observable<Group[]> {
    return this.http.get<Group[]>('/api/groups');
  }

  createGroup(name: string, description: string | null): Observable<Group> {
    return this.http.post<Group>('/api/groups', { name, description });
  }

  deleteGroup(id: number): Observable<void> {
    return this.http.delete<void>(`/api/groups/${id}`);
  }

  setMembers(groupId: number, userIds: number[]): Observable<Group> {
    return this.http.put<Group>(`/api/groups/${groupId}/members`, { user_ids: userIds });
  }

  users(): Observable<UserAdmin[]> {
    return this.http.get<UserAdmin[]>('/api/users');
  }

  updateUser(
    id: number,
    changes: { role?: UserRole; is_active?: boolean; group_ids?: number[] },
  ): Observable<UserAdmin> {
    return this.http.patch<UserAdmin>(`/api/users/${id}`, changes);
  }

  metrics(days: number): Observable<QualityMetrics> {
    return this.http.get<QualityMetrics>('/api/admin/metrics', { params: { days } });
  }

  flagged(): Observable<FlaggedMessage[]> {
    return this.http.get<FlaggedMessage[]>('/api/admin/flagged');
  }

  resolve(messageId: number): Observable<void> {
    return this.http.post<void>(`/api/admin/flagged/${messageId}/resolve`, {});
  }
}
