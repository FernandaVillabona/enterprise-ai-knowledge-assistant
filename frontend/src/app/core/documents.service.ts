import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Chunk, DocumentAdmin, DocumentSummary, Visibility } from './models';

export interface UploadOptions {
  file: File;
  title?: string;
  visibility: Visibility;
  groupIds: number[];
}

@Injectable({ providedIn: 'root' })
export class DocumentsService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/documents';

  accessible(): Observable<DocumentSummary[]> {
    return this.http.get<DocumentSummary[]>(`${this.base}/accessible`);
  }

  list(): Observable<DocumentAdmin[]> {
    return this.http.get<DocumentAdmin[]>(this.base);
  }

  upload({ file, title, visibility, groupIds }: UploadOptions): Observable<DocumentAdmin> {
    // multipart/form-data: el navegador pone el Content-Type con el boundary
    const form = new FormData();
    form.append('file', file);
    if (title?.trim()) form.append('title', title.trim());
    form.append('visibility', visibility);
    groupIds.forEach((id) => form.append('group_ids', String(id)));
    return this.http.post<DocumentAdmin>(this.base, form);
  }

  updateAccess(id: number, visibility: Visibility, groupIds: number[]): Observable<DocumentAdmin> {
    return this.http.put<DocumentAdmin>(`${this.base}/${id}/access`, {
      visibility,
      group_ids: groupIds,
    });
  }

  chunks(id: number): Observable<Chunk[]> {
    return this.http.get<Chunk[]>(`${this.base}/${id}/chunks`, { params: { limit: 200 } });
  }

  reprocess(id: number): Observable<DocumentAdmin> {
    return this.http.post<DocumentAdmin>(`${this.base}/${id}/reprocess`, {});
  }

  delete(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}`);
  }
}
