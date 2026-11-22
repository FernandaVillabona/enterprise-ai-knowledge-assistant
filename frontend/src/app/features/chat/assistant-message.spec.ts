import { TestBed } from '@angular/core/testing';

import { Message, Source } from '../../core/models';
import { AssistantMessage } from './assistant-message';

const SOURCE: Source = {
  n: 1,
  chunk_id: 10,
  document_id: 1,
  document_title: 'Política de vacaciones',
  page_number: 3,
  content: 'Son 23 días hábiles.',
  score: 0.03,
  similarity: 0.82,
  cited: true,
};

function message(overrides: Partial<Message> = {}): Message {
  return {
    id: 2,
    role: 'assistant',
    content: 'Tienes 23 días [1]. <b>Ojo</b> [9]',
    search_query: '¿vacaciones?',
    sources: [SOURCE, { ...SOURCE, n: 2, chunk_id: 11, cited: false }],
    model: 'gpt',
    prompt_tokens: 100,
    completion_tokens: 20,
    latency_ms: 900,
    evaluation: {
      verdict: 'partially_supported',
      faithfulness: 0.5,
      claims: [{ claim: 'Ojo', supported: false, sources: [] }],
      invalid_citations: [],
      uncited: false,
      judge_model: 'gpt',
      error: null,
    },
    faithfulness_score: 0.5,
    flagged: true,
    feedback_rating: null,
    feedback_comment: null,
    created_at: '',
    ...overrides,
  };
}

async function render(m: Message) {
  const fixture = TestBed.createComponent(AssistantMessage);
  fixture.componentRef.setInput('message', m);
  await fixture.whenStable();
  return fixture;
}

describe('AssistantMessage', () => {
  it('pinta las citas como botones y escapa el HTML de la respuesta', async () => {
    const el: HTMLElement = (await render(message())).nativeElement;
    const text = el.querySelector('.msg__text')!;

    expect(text.querySelector('b')).toBeNull(); // no se interpreta como HTML
    expect(text.textContent).toContain('<b>Ojo</b>');
    const cite = text.querySelector('button.cite')!;
    expect(cite.textContent?.trim()).toBe('1');
    expect(cite.getAttribute('aria-label')).toBe('Fuente 1: Política de vacaciones, página 3');
    // [9] no corresponde a ninguna fuente enviada
    expect(text.querySelector('.cite--invalid')?.textContent?.trim()).toBe('9');
  });

  it('lista solo las fuentes citadas y emite la fuente al pulsar una cita', async () => {
    const fixture = await render(message());
    const el: HTMLElement = fixture.nativeElement;
    expect(el.querySelectorAll('.source-chip').length).toBe(1);

    const emitted: Source[] = [];
    fixture.componentInstance.citeClick.subscribe((s) => emitted.push(s));
    (el.querySelector('.msg__text button.cite') as HTMLButtonElement).click();
    expect(emitted[0].chunk_id).toBe(10);
  });

  it('muestra el veredicto, el aviso de revisión y las afirmaciones no respaldadas', async () => {
    const fixture = await render(message());
    const el: HTMLElement = fixture.nativeElement;
    expect(el.textContent).toContain('Parcialmente respaldada · 50 %');
    expect(el.textContent).toContain('En revisión');

    (Array.from(el.querySelectorAll('button')).find((b) => b.textContent?.includes('Detalles')) as HTMLButtonElement).click();
    await fixture.whenStable();
    expect(el.textContent).toContain('Afirmaciones no respaldadas por las fuentes');
    expect(el.textContent).toContain('120 tokens');
  });

  it('no ofrece valoración si no hubo fuentes («no hay información»)', async () => {
    const el: HTMLElement = (await render(message({ sources: [], content: 'No he encontrado…' })))
      .nativeElement;
    expect(el.textContent).not.toContain('👍');
  });
});
