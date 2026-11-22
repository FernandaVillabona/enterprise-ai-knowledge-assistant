/** Tipos que reflejan los esquemas de la API (backend/app/schemas). */

export type UserRole = 'admin' | 'user';
export type Visibility = 'public' | 'restricted';
export type DocumentStatus = 'pending' | 'processing' | 'ready' | 'failed';
export type FileType = 'pdf' | 'docx' | 'txt';
export type Verdict =
  | 'supported'
  | 'partially_supported'
  | 'unsupported'
  | 'no_answer'
  | 'error'
  | 'pending'
  | 'not_evaluated';

export interface GroupBrief {
  id: number;
  name: string;
}

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface UserAdmin extends User {
  groups: GroupBrief[];
}

export interface Group {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  users: { id: number; email: string; full_name: string }[];
}

export interface DocumentAdmin {
  id: number;
  title: string;
  original_filename: string;
  file_type: FileType;
  size_bytes: number;
  status: DocumentStatus;
  error: string | null;
  num_pages: number | null;
  num_chunks: number | null;
  uploaded_by_id: number | null;
  created_at: string;
  processed_at: string | null;
  visibility: Visibility;
  groups: GroupBrief[];
}

export interface DocumentSummary {
  id: number;
  title: string;
  file_type: FileType;
  num_pages: number | null;
  processed_at: string | null;
}

export interface Chunk {
  id: number;
  chunk_index: number;
  page_number: number;
  token_count: number;
  content: string;
}

export interface Source {
  n: number;
  chunk_id: number;
  document_id: number;
  document_title: string;
  page_number: number;
  content: string;
  score: number;
  similarity: number | null;
  cited: boolean;
}

export interface Claim {
  claim: string;
  supported: boolean;
  sources: number[];
}

export interface Evaluation {
  verdict: Verdict;
  faithfulness: number | null;
  claims: Claim[];
  invalid_citations: number[];
  uncited: boolean;
  judge_model: string | null;
  error: string | null;
}

export interface Message {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  search_query: string | null;
  sources: Source[] | null;
  model: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  latency_ms: number | null;
  evaluation: Evaluation | null;
  faithfulness_score: number | null;
  flagged: boolean;
  feedback_rating: 1 | -1 | null;
  feedback_comment: string | null;
  created_at: string;
}

export interface Conversation {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

export interface ChatTurn {
  conversation_id: number;
  user_message: Message;
  assistant_message: Message;
}

export interface QualityMetrics {
  since: string;
  answers: number;
  no_info_answers: number;
  no_info_rate: number | null;
  evaluated: number;
  avg_faithfulness: number | null;
  hallucination_rate: number | null;
  flagged: number;
  feedback_positive: number;
  feedback_negative: number;
  avg_latency_ms: number | null;
  prompt_tokens: number;
  completion_tokens: number;
}

export interface FlaggedMessage {
  message_id: number;
  conversation_id: number;
  user_email: string;
  question: string | null;
  answer: string;
  evaluation: Evaluation | null;
  faithfulness_score: number | null;
  feedback_rating: number | null;
  feedback_comment: string | null;
  created_at: string;
}

/** Error de FastAPI: `detail` es un texto o una lista de errores de validación. */
export function apiErrorMessage(err: unknown, fallback = 'Ha ocurrido un error'): string {
  const detail = (err as { error?: { detail?: unknown } })?.error?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d: { msg?: string }) => d.msg ?? '').join('. ');
  }
  if ((err as { status?: number })?.status === 0) return 'No se pudo conectar con el servidor';
  return fallback;
}
