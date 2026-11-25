# Claude Buddy

[English](README.md) · **Español**

**Una mascota de escritorio que reúne todas tus sesiones locales de Claude Code y te deja retomarlas desde un panel flotante.**

Claude Buddy vive en la bandeja del sistema y como un pequeño personaje pixel-art sobre tu escritorio.
Haz clic en él y verás todas tus conversaciones de Claude Code (CLI, extensión de VS Code y app de
escritorio) agrupadas por proyecto: puedes buscarlas, leer su historial, seguir chateando con ellas
o abrirlas en una terminal. Mientras tanto, el buddy refleja lo que está haciendo Claude… y, si lo
dejas, también tiene vida propia.

<p align="center">
  <img src="docs/img/panel-sesiones.png" width="360" alt="Panel con las sesiones agrupadas por proyecto">
  &nbsp;
  <img src="docs/img/panel-historial.png" width="360" alt="Historial de una sesión con la caja de chat">
</p>

<p align="center">
  <img src="docs/img/buddy-estados.png" width="720" alt="Animaciones del buddy">
</p>

> Proyecto **no oficial** de la comunidad, sin relación con Anthropic. «Claude» y «Claude Code»
> son marcas de Anthropic. El personaje es un diseño propio de este proyecto.

## Características

- **Todas tus sesiones en un sitio**: lee `~/.claude/projects` y muestra título (tu primer mensaje),
  proyecto, última actividad, número de mensajes y origen (CLI, VS Code, Desktop).
- **Búsqueda** por título, proyecto, ruta o ID, sin distinguir mayúsculas ni acentos.
- **Historial** con formato (Markdown, tablas, código), herramientas usadas y errores; se
  actualiza solo si la sesión sigue activa en otro sitio.
- **Chat** para continuar cualquier sesión con [`claude-agent-sdk`](https://pypi.org/project/claude-agent-sdk/):
  respuesta en streaming, mismo directorio del proyecto y avisos de permiso (*Permitir / Denegar*)
  como en la terminal.
- **Abrir en terminal**: ejecuta `claude --resume <id>` en la carpeta del proyecto
  (Windows Terminal / PowerShell, Terminal.app, gnome-terminal, konsole, xterm…).
- **Un buddy que reacciona**: piensa, lee, busca, ejecuta comandos, escribe, te pide permiso,
  celebra cuando termina, se duerme si no hay actividad. 6 colores y 5 accesorios.
- **Modo mascota** (opcional): camina por la barra de tareas, cae con gravedad si lo sueltas,
  persigue el ratón, come, hace caca, duerme, le gustan los mimos y se enfada si lo agitas.
- **100 % local**: sin servidores propios, sin telemetría, sin guardar credenciales (usa la sesión
  que ya tiene Claude Code).

## Modo mascota

<p align="center">
  <img src="docs/img/modo-mascota.png" width="720" alt="El buddy caminando, una caca, mimos, mareado, comiendo y durmiendo">
</p>

Actívalo con clic derecho en el buddy → **Modo mascota**. Inspirado en clásicos como eSheep,
Shimeji, oneko o Desktop Goose.

| Qué haces | Qué pasa |
|---|---|
| Nada | Pasea por la barra de tareas, mira a los lados, bosteza, a veces persigue el ratón |
| Lo arrastras y lo sueltas en el aire | Cae con gravedad; si la caída es fuerte, «¡Ay!» |
| Mueves el ratón de lado a lado encima | **Mimos**: corazones y sube su felicidad |
| Lo agitas mientras lo arrastras | Se **marea** y después se **enfada** un rato (no quiere mimos) |
| Menú → *Mascota → Dar de comer* | Come una galleta… y al rato **hace caca** |
| Clic en una caca | La limpias (le gusta que su sitio esté limpio) |
| Lo dejas mucho rato | Se cansa y **duerme**; si tiene hambre o se aburre, se pone **triste** |

Tiene **hambre, felicidad y energía**, que se guardan al cerrar (y avanzan, con límite, mientras
la app está cerrada). Pasa el ratón por encima para verlas. Si chateas con Claude desde el panel,
la mascota se queda quieta y muestra lo que está haciendo Claude.

## Instalación

### Windows (instalador)

Descarga `ClaudeBuddy-Setup-<versión>.exe` de [Releases](../../releases) y ejecútalo. No necesita
permisos de administrador: se instala para tu usuario, con acceso en el menú Inicio y opción de
**iniciar con Windows**. Se desinstala desde *Configuración → Aplicaciones*.

### Desde el código (Windows, Linux, macOS)

Requisitos: Python 3.12+ y [uv](https://docs.astral.sh/uv/).

```bash
git clone <url-del-repositorio>
cd claude-buddy
uv sync
uv run claude-buddy              # app de bandeja
uv run python -m claude_buddy    # igual, con consola para ver errores
uv run claude-buddy-list         # listado de sesiones en la terminal
```

### Requisitos para chatear

[Claude Code](https://code.claude.com/docs) instalado y con la sesión iniciada
(comando `claude`). Sin él, Claude Buddy lista las sesiones y muestra su historial, pero no puede
continuar conversaciones.

## Uso

- **Clic** en el buddy o en el icono de la bandeja: abre o cierra el panel. **Clic derecho**: menú
  (color, accesorio, tamaño, ocultar mascota, modo mascota, salir).
- **Doble clic** (o `Intro`) en una sesión: historial. `Esc` o `←` vuelve a la lista.
- **Chat**: escribe abajo; `Intro` envía, `Mayús+Intro` salto de línea, `■` detiene.
  El selector inferior elige el modo de permisos: *Preguntar*, *Aceptar ediciones* o *Solo planificar*.
- **Abrir en terminal**: botón `>_` del historial o clic derecho en una sesión.
- Atajos: `Ctrl+F` buscar, `↓` pasar a la lista, `F5` actualizar.
- 📌 mantiene el panel abierto; se arrastra por la cabecera y se redimensiona desde la esquina.

> **Una sesión, un sitio a la vez.** Si la misma sesión está abierta en VS Code o en una terminal,
> no escribas también desde el panel: las respuestas se mezclarían. El panel avisa si la sesión
> ha tenido actividad reciente.

### Diagnóstico

`ClaudeBuddy.exe --diagnose` (o `uv run python -m claude_buddy --diagnose`) comprueba Claude Code,
las sesiones y la conexión del SDK **sin enviar ningún mensaje**. El registro está en
`%LOCALAPPDATA%\ClaudeBuddy\ClaudeBuddy\logs\buddy.log` (Windows) o en la carpeta de datos de la
aplicación de tu sistema.

## Privacidad

- La app **solo lee** `~/.claude` (o `CLAUDE_CONFIG_DIR`). Cuando chateas, es Claude Code quien
  añade los mensajes a la sesión, igual que en la terminal.
- No hay servidores propios ni telemetría. Las únicas conexiones de red son las que hace Claude
  Code para hablar con Claude.
- No guarda credenciales. Las preferencias (color, posición, necesidades de la mascota) se guardan
  con `QSettings` en tu usuario.

## Cómo funciona

```
src/claude_buddy/
├── parser.py, scanner.py   lectura tolerante de ~/.claude/projects/*/*.jsonl (con caché)
├── transcript.py           historial: cadena principal de la conversación, herramientas, errores
├── chat.py                 claude-agent-sdk en un hilo con asyncio (resume, streaming, permisos)
├── terminal.py             `claude --resume` en el terminal de cada sistema
├── pet.py                  lógica del modo mascota (necesidades, física, gestos), sin Qt
├── app.py                  bandeja, mascota de escritorio, panel y estados del buddy
└── ui/                     PySide6: panel, lista, historial, chat, sprites, iconos
```

El formato de los archivos de sesión no es público; está documentado a partir de sesiones reales en
[docs/formato-jsonl.md](docs/formato-jsonl.md). Los sprites son matrices de 16×16 en
[`ui/sprites.py`](src/claude_buddy/ui/sprites.py): añadir un estado o accesorio es editar texto.

## Desarrollo

```bash
uv sync
uv run pytest                      # tests (datos sintéticos; nunca leen tus sesiones)
uv run python docs/screenshots.py  # regenera las imágenes del README con datos inventados
```

### Generar el instalador de Windows

Requiere [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup --scope user`).

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

Pasa los tests, genera el icono, empaqueta con PyInstaller y crea
`dist\ClaudeBuddy-Setup-<versión>.exe`. No incluye el `claude.exe` (~390 MB) que trae
`claude-agent-sdk`: usa el Claude Code instalado por el usuario.

## Limitaciones conocidas

- El formato de `~/.claude` puede cambiar con nuevas versiones de Claude Code; el lector ignora lo
  que no conoce y avisa de líneas dañadas.
- Si Claude hace una pregunta con opciones durante el chat, desde el panel solo se puede permitir o
  denegar, no elegir la opción.
- El coste que se muestra al terminar es el estimado que informa Claude Code (equivalente en la API).
- Probado sobre todo en Windows 11; en Linux sin bandeja del sistema el panel se abre como ventana.

## Licencia

[MIT](LICENSE). El personaje y sus sprites son originales de este proyecto y se distribuyen bajo la
misma licencia. «Claude» y «Claude Code» son marcas de Anthropic y no están cubiertas por ella.
