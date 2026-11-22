# Frontend (Angular 22)

Interfaz del Enterprise AI Knowledge Assistant. Ver el [README principal](../README.md).

```bash
npm install
npm start          # http://localhost:4200 (redirige /api a http://127.0.0.1:8000, ver proxy.conf.json)
npx ng test        # tests unitarios con Vitest
npm run build      # build de producción en dist/frontend/browser
```

## Estructura

```
src/app/
├── core/        # Modelos de la API, servicios HTTP, sesión (AuthService), interceptor y guards
├── shared/      # Utilidades y componentes comunes (citas, veredicto, formatos)
├── layout/      # Estructura con barra de navegación
└── features/
    ├── auth/        # Login y registro
    ├── chat/        # Chat con citas, panel de fuentes, veredicto y feedback
    ├── documents/   # Documentos accesibles para el usuario
    └── admin/       # Documentos, grupos, usuarios y calidad (lazy, solo admins)
```

## Decisiones

- **Componentes standalone, signals y detección de cambios zoneless** (por defecto en Angular 22).
- **Rutas lazy** (`loadComponent`): el usuario normal no descarga el panel de administración.
- **Citas sin `innerHTML`**: la respuesta se divide en segmentos de texto y de cita (`shared/citations.ts`) y Angular escapa el texto. Un `<script>` en un documento se muestra como texto.
- **Guards = experiencia, no seguridad**: el backend valida token y rol en cada petición.
- **JWT en `localStorage`** por simplicidad. Alternativa más robusta frente a XSS: cookie `httpOnly` emitida por el backend.
- **Veredicto en segundo plano**: tras responder, el chat consulta la conversación cada 2 s mientras el juez de fidelidad esté `pending`.
