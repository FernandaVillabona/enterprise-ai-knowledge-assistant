import { parseCitations } from './citations';

describe('parseCitations', () => {
  it('separa texto y citas en orden', () => {
    expect(parseCitations('Son 23 días [1][2].')).toEqual([
      { kind: 'text', text: 'Son 23 días ' },
      { kind: 'cite', n: 1 },
      { kind: 'cite', n: 2 },
      { kind: 'text', text: '.' },
    ]);
  });

  it('admite citas agrupadas con comas', () => {
    expect(parseCitations('[1, 3]')).toEqual([
      { kind: 'cite', n: 1 },
      { kind: 'cite', n: 3 },
    ]);
  });

  it('deja intacto el texto sin citas, incluido HTML (se mostrará escapado)', () => {
    const text = 'Sin fuentes <script>alert(1)</script> [no es cita]';
    expect(parseCitations(text)).toEqual([{ kind: 'text', text }]);
  });
});
