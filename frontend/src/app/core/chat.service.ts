import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ChatTurn, Conversation, ConversationDetail, Message } from './models';

@Injectable({ providedIn: 'root' })
export class ChatService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/conversations';

  list(): Observable<Conversation[]> {
    return this.http.get<Conversation[]>(this.base);
  }

  get(id: number): Observable<ConversationDetail> {
    return this.http.get<ConversationDetail>(`${this.base}/${id}`);
  }

  create(): Observable<Conversation> {
    return this.http.post<Conversation>(this.base, {});
  }

  delete(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}`);
  }

  send(conversationId: number, content: string): Observable<ChatTurn> {
    return this.http.post<ChatTurn>(`${this.base}/${conversationId}/messages`, { content });
  }

  feedback(
    conversationId: number,
    messageId: number,
    rating: 1 | -1,
    comment?: string,
  ): Observable<Message> {
    return this.http.post<Message>(
      `${this.base}/${conversationId}/messages/${messageId}/feedback`,
      { rating, comment: comment || null },
    );
  }
}
