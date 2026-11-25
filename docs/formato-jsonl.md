# Formato de las sesiones de Claude Code (`~/.claude/projects`)

[English](jsonl-format.md) · **Español**

Documentado inspeccionando 39 sesiones reales (Claude Code 2.1.331, noviembre de 2026).
Formato **no oficial**: puede cambiar entre versiones, así que el parser debe tolerar
tipos y campos desconocidos.

## Estructura de carpetas

```
~/.claude/projects/
└── <cwd-codificado>/                 p. ej. c--dev-Buddy-chatui
    ├── <session-id>.jsonl            una sesión = un archivo (nombre = sessionId)
    ├── <session-id>/
    │   ├── subagents/agent-*.jsonl   transcripciones de subagentes (+ .meta.json)
    │   ├── tool-results/*.txt        salidas largas de herramientas
    │   └── custom-title.json         {"customTitle": "..."} (opcional)
    └── memory/*.md                   memoria del proyecto (no son sesiones)
```

- Sesiones = solo `*/<uuid>.jsonl` en el primer nivel. Ignorar `subagents/`, `tool-results/`, `memory/`.
- **El nombre de carpeta es una codificación con pérdida**: `:`, `\`, `/`, espacios y `.` pasan a `-`
  (`c:\dev\Buddy chatui` → `c--dev-Buddy-chatui`). No se puede decodificar: el `cwd` real
  hay que leerlo de dentro del `.jsonl`.
- La misma ruta puede aparecer dos veces con distinta mayúscula de unidad (`C--…` desde la CLI,
  `c--…` desde VS Code). Para agrupar por proyecto hay que normalizar mayúsculas en Windows.
- Puede respetarse la variable `CLAUDE_CONFIG_DIR` si apunta a otra carpeta de configuración.

## Registros

Cada línea es un objeto JSON con un campo `type`. La primera línea **no** es necesariamente
un mensaje (suele ser `queue-operation`, `session-owner` o `mode`). En la muestra: 0 líneas
corruptas y `sessionId` siempre igual al nombre del archivo.

| `type` | Uso para Claude Buddy |
|---|---|
| `user` | Mensaje del usuario **o** resultado de herramienta (ver abajo) |
| `assistant` | Respuesta del modelo; **un registro por bloque** de contenido |
| `ai-title` | `aiTitle`: título generado automáticamente (se reescribe varias veces) |
| `custom-title` | `customTitle`: título puesto por el usuario (prioritario) |
| `summary` | `summary`: título de versiones antiguas |
| `last-prompt` | `lastPrompt`: último prompt enviado |
| `system` | Eventos (`subtype`: `compact_boundary`, `api_error`, `turn_duration`…) |
| `attachment`, `api-request*`, `file-history-*`, `mode`, `permission-mode`, `queue-operation`, `session-owner`, `cost-state`, `tools-used`, `atis-latch`, `agent-name`, `teleported-from`, `artifact-*` | Internos: ignorar |

Campos comunes en `user`/`assistant`/`system`/`attachment`: `uuid`, `parentUuid` (árbol de
conversación), `sessionId`, `timestamp`, `cwd`, `gitBranch`, `version`, `entrypoint`, `isSidechain`.

- `timestamp`: ISO 8601 UTC con milisegundos (`2026-11-24T12:08:31.123Z`).
- `entrypoint`: `claude-vscode`, `cli`, `claude-desktop`, `sdk-ts` (y presumiblemente `sdk-py`).
- `cwd`: puede cambiar dentro de una sesión (siempre a un **subdirectorio** del inicial).
  El directorio original del proyecto es el `cwd` del **primer** registro que lo tenga.

### `message` en `user`

`message = {"role": "user", "content": str | [bloques]}`, bloques `text`, `image`,
`document`, `tool_result`.

Un registro `user` **no** es un prompt real si cumple alguna de:

- tiene `toolUseResult` (contenido `tool_result`; es la respuesta a una herramienta),
- `isMeta: true` (avisos inyectados), `isCompactSummary: true` (resumen tras compactar),
- `isSidechain: true` (subagente; no apareció en archivos de primer nivel).

Dentro de un prompt real, algunos bloques de texto son contexto inyectado, no texto del usuario:
`<ide_opened_file>`, `<ide_selection>` (VS Code los envía como bloque **separado** antes del texto),
`<system-reminder>`, `<task-notification>`, `<local-command-stdout>`.
Casos especiales:

- `<command-name>/xyz</command-name>…<command-args>…` → comando slash; mostrar como `/xyz args`.
- `<pasted_content …>…</pasted_content>` → texto pegado por el usuario; es contenido real.
- Prompts solo con imagen → sin texto.

### `message` en `assistant`

Formato de la API de Anthropic (`id`, `model`, `content`, `stop_reason`, `usage`…).
Una respuesta se reparte en **varios registros consecutivos con el mismo `message.id`**,
uno por bloque (`thinking`, `text`, `tool_use`). Para contar o mostrar respuestas hay que
agrupar por `message.id`.

## Orden y ramas de la conversación (fase 3)

`uuid` / `parentUuid` forman un árbol. En los datos reales hay unas 745 bifurcaciones, pero
casi todas (744) son **resultados de herramientas en paralelo**: cada `tool_result` cuelga de
su `tool_use`, y la conversación continúa solo desde el último. Las ramas reales (el usuario
deshace y edita un mensaje) son raras.

El historial se construye así:

1. Hoja = último registro `user`/`assistant` del archivo (no sidechain).
2. Cadena principal = ancestros de la hoja siguiendo `parentUuid`; si es `null`, se sigue
   `logicalParentUuid` (los `compact_boundary` cortan la cadena así).
3. Se recorren los registros **en orden de archivo** y se muestran los de la cadena principal.
   Los resultados de herramientas fuera de la cadena se aceptan (paralelos), y de ellos
   solo se muestran los errores (`is_error`).
4. Registros `assistant` consecutivos con el mismo `message.id` se funden en una respuesta.

## Definiciones propuestas para la fase 1

- **Título**: primer prompt real del usuario (aplicando las reglas anteriores), recortado a una línea.
  Si no hay ninguno, `customTitle` → `aiTitle` → `summary` → `(sin título)`.
- **Última actividad**: `timestamp` máximo del archivo; si no hay, `mtime` del archivo.
- **Nº de mensajes**: prompts reales del usuario + respuestas del asistente con texto visible
  (agrupadas por `message.id`). No cuenta llamadas ni resultados de herramientas.
- **Proyecto**: `cwd` inicial; si no existe, el nombre de la carpeta codificada.
