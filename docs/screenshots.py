"""Regenerate the README images in docs/img/ from made-up demo sessions (never real data).

    uv run python docs/screenshots.py
"""

import json
import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

DEMO = Path(tempfile.mkdtemp(prefix="buddy-demo-"))
os.environ["CLAUDE_CONFIG_DIR"] = str(DEMO)          # the app reads sessions from here

from PySide6.QtCore import QPoint, QRect, QSettings, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu  # noqa: E402

from claude_buddy.scanner import scan_sessions  # noqa: E402
from claude_buddy.transcript import load_transcript  # noqa: E402
from claude_buddy.ui import sprites  # noqa: E402
from claude_buddy.ui.mascot import Mascot, render  # noqa: E402
from claude_buddy.ui.panel import Panel  # noqa: E402

OUT = Path(__file__).parent / "img"
NOW = datetime.now(UTC)


def _write_session(project: str, sid: str, minutes_ago: int, turns: list[tuple[str, str, list[str]]]) -> None:
    folder = DEMO / "projects" / ("C--proyectos-" + project)
    folder.mkdir(parents=True, exist_ok=True)
    cwd = f"C:\\proyectos\\{project}"
    records, parent, t = [], None, NOW - timedelta(minutes=minutes_ago + 2 * len(turns))
    for n, (prompt, answer, tools) in enumerate(turns):
        def rec(kind, content, **extra):
            nonlocal parent, t
            uid = f"{sid}-{len(records)}"
            t += timedelta(seconds=20)
            message = {"role": "user" if kind == "user" else "assistant", "content": content}
            if kind == "assistant":
                message["id"] = f"{sid}-m{n}-{len(records)}"
            records.append({"type": kind, "uuid": uid, "parentUuid": parent, "cwd": cwd, "sessionId": sid,
                            "entrypoint": "claude-vscode", "timestamp": t.isoformat().replace("+00:00", "Z"),
                            "message": message, **extra})
            parent = uid
        rec("user", prompt)
        for i, tool in enumerate(tools):
            name, arg = tool.split(" ", 1)
            key = {"Bash": "command", "Grep": "pattern"}.get(name, "file_path")
            rec("assistant", [{"type": "tool_use", "id": f"t{n}{i}", "name": name, "input": {key: arg}}])
            rec("user", [{"type": "tool_result", "tool_use_id": f"t{n}{i}", "content": "ok"}], toolUseResult={})
        rec("assistant", [{"type": "text", "text": answer}])
    (folder / f"{sid}.jsonl").write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")


def make_demo_data() -> None:
    _write_session("tienda-online", "d1", 3, [
        ("Revisa por qué falla el test de pagos con tarjeta",
         "El test falla porque el importe se redondea **antes** de aplicar el IVA.\n\n"
         "- `calcular_total()` redondeaba cada línea por separado.\n"
         "- Ahora se redondea solo el total, como exige la pasarela.\n\n"
         "He corregido `pagos/totales.py` y los 42 tests pasan.",
         ["Grep redondear", "Read src/pagos/totales.py", "Edit src/pagos/totales.py", "Bash pytest tests/test_pagos.py"]),
        ("¿Afecta también a las devoluciones?",
         "Sí: `devoluciones.py` usa la misma función, así que ya queda corregido. Añadí un test para cubrirlo.",
         ["Read src/pagos/devoluciones.py", "Edit tests/test_devoluciones.py"]),
    ])
    _write_session("tienda-online", "d2", 95, [("Añade paginación a la lista de productos", "Hecho: 20 productos por página.", [])])
    _write_session("tienda-online", "d3", 60 * 26, [("Mejora los textos de la página de envío", "He reescrito los textos.", [])])
    _write_session("api-pedidos", "d4", 40, [("Documenta los endpoints de pedidos en OpenAPI", "Documentados 7 endpoints.", [])])
    _write_session("api-pedidos", "d5", 60 * 50, [("Optimiza la consulta de pedidos por cliente", "Añadido un índice.", [])])
    _write_session("scripts-backup", "d6", 60 * 24 * 4, [("Crea un script que comprima los logs antiguos", "Listo: `comprimir_logs.ps1`.", [])])


def save(image: QImage, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    image.save(str(OUT / name))
    print("written", OUT / name)


def panel_shots(app: QApplication) -> None:
    result = scan_sessions()
    panel = Panel(Mascot(), QMenu())
    panel.resize(440, 620)
    panel.set_result(result)
    panel.show()
    tree = panel._tree
    tree.setCurrentIndex(panel._proxy.index(0, 0, panel._proxy.index(0, 0)))
    app.processEvents()
    save(panel.grab().toImage(), "panel-sesiones.png")

    session = next(s for s in result.sessions if s.session_id == "d1")
    panel.open_session(session)
    panel.set_transcript(session, load_transcript(session.file))
    panel._chat.set_banner(None)
    panel._chat.show_permission("demo", "Bash · git commit -m \"Corrige el redondeo del IVA\"")
    for _ in range(5):
        app.processEvents()
    save(panel.grab().toImage(), "panel-historial.png")
    panel.hide()


def states_sheet() -> None:
    states = ["idle", "thinking", "reading", "writing", "searching", "running", "waiting", "done",
              "walk", "pet", "eat", "poop", "dizzy", "angry", "asleep", "sad"]
    cols, cell, label_h = 8, 96, 26
    img = QImage(cols * cell, (len(states) // cols) * (cell + label_h), QImage.Format.Format_ARGB32)
    img.fill(QColor("#F6F3EE"))
    p = QPainter(img)
    p.setFont(QFont("Segoe UI", 9))
    for i, state in enumerate(states):
        x, y = (i % cols) * cell, (i // cols) * (cell + label_h)
        frame = sprites.STATES[state].frames // 2
        p.drawPixmap(x + 8, y + 4, render(sprites.frame(state, frame), "terracotta", 80))
        p.setPen(QColor("#5B5750"))
        p.drawText(QRect(x, y + cell - 6, cell, label_h), Qt.AlignmentFlag.AlignHCenter, sprites.STATES[state].label)
    p.end()
    save(img, "buddy-estados.png")


def pet_scene() -> None:
    """Mock desktop strip: the pet walking on the taskbar, a poop, a cuddle and skins."""
    w, h, bar = 900, 230, 44
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    sky = QLinearGradient(0, 0, 0, h)
    sky.setColorAt(0, QColor("#9CC7DD"))
    sky.setColorAt(1, QColor("#D7E8EF"))
    p.fillRect(0, 0, w, h, sky)
    p.fillRect(0, h - bar, w, bar, QColor("#1F2A33"))
    floor = h - bar
    size = 96
    def put(state, frame, x, skin="terracotta", accessory="none", flip=False, s=size):
        pm = render(sprites.frame(state, frame, accessory), skin, s)
        if flip:
            pm = pm.transformed(__import__("PySide6.QtGui", fromlist=["QTransform"]).QTransform().scale(-1, 1))
        p.drawPixmap(x, floor - 15 * s // 16, pm)
    put("walk", 0, 40)
    p.drawPixmap(170, floor - 15 * 48 // 16, render(sprites.poop_frame(0), "terracotta", 48))
    put("pet", 3, 260, skin="mint")
    put("dizzy", 1, 400, skin="lavender")
    put("eat", 2, 540, skin="sky", accessory="crown")
    put("asleep", 1, 680, skin="lemon", accessory="nightcap")
    p.setPen(QColor("#E8E2D8"))
    p.setFont(QFont("Segoe UI", 9))
    p.drawText(QRect(0, h - bar, w, bar), Qt.AlignmentFlag.AlignCenter, "camina · hace caca · mimos · mareado · come · duerme")
    p.end()
    save(img, "modo-mascota.png")


def logo() -> None:
    save(render(sprites.frame("idle", 0), "terracotta", 128).toImage(), "logo.png")


def _save_gif(frames: list[QImage], name: str, ms: int) -> None:
    """Qt has no GIF writer: hand the frames to Pillow (dev dependency)."""
    from PIL import Image
    pil = []
    for img in frames:
        img = img.convertToFormat(QImage.Format.Format_RGBA8888)
        raw = bytes(img.constBits())[: img.sizeInBytes()]
        rgba = Image.frombuffer("RGBA", (img.width(), img.height()), raw, "raw", "RGBA", img.bytesPerLine(), 1)
        pil.append(rgba.convert("RGB").quantize(colors=64, method=Image.Quantize.MEDIANCUT))
    OUT.mkdir(parents=True, exist_ok=True)
    pil[0].save(OUT / name, save_all=True, append_images=pil[1:], duration=ms, loop=0, optimize=True)
    print("written", OUT / name, f"({(OUT / name).stat().st_size // 1024} KB)")


def states_gif() -> None:
    """Six buddies animating different activities side by side."""
    states = ["thinking", "reading", "writing", "searching", "running", "done"]
    cell, label_h, step = 112, 28, 60
    frames = []
    for k in range(80):                                   # 80 frames x 60 ms ≈ 4.8 s loop
        img = QImage(cell * len(states), cell + label_h, QImage.Format.Format_ARGB32)
        img.fill(QColor("#F6F3EE"))
        p = QPainter(img)
        p.setFont(QFont("Segoe UI", 10))
        for i, state in enumerate(states):
            spec = sprites.STATES[state]
            index = (k * step) // spec.interval_ms
            p.drawPixmap(i * cell + 8, 4, render(sprites.frame(state, index), "terracotta", 96))
            p.setPen(QColor("#5B5750"))
            p.drawText(QRect(i * cell, cell - 6, cell, label_h), Qt.AlignmentFlag.AlignHCenter, spec.label)
        p.end()
        frames.append(img)
    _save_gif(frames, "buddy-estados.gif", step)


def pet_gif() -> None:
    """Scripted pet-mode scene on a mock taskbar: walk, poop, walk away, cuddle, eat, sleep."""
    from PySide6.QtGui import QTransform
    w, h, bar, size, step = 720, 210, 40, 96, 80
    floor = h - bar
    timeline = ([("walk", 1)] * 22 + [("poop", 0)] * 30 + [("walk", 1)] * 18 + [("pet", 0)] * 26
                + [("eat", 0)] * 26 + [("yawn", 0)] * 12 + [("asleep", 0)] * 24)
    x, poop_x, frames, since = 30.0, None, [], {}
    for k, (state, direction) in enumerate(timeline):
        since[state] = since.get(state, k) if timeline[k - 1][0] == state and k else k
        local = k - since[state]
        index = (local * step) // sprites.STATES[state].interval_ms
        if state == "walk":
            x += direction * 7
        if state == "poop" and local == 28:
            poop_x = x - 30                               # left behind the pet
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        p = QPainter(img)
        sky = QLinearGradient(0, 0, 0, h)
        sky.setColorAt(0, QColor("#9CC7DD"))
        sky.setColorAt(1, QColor("#D7E8EF"))
        p.fillRect(0, 0, w, h, sky)
        p.fillRect(0, floor, w, bar, QColor("#1F2A33"))
        if poop_x is not None:
            p.drawPixmap(round(poop_x), floor - 15 * 48 // 16, render(sprites.poop_frame(k // 6), "terracotta", 48))
        pm = render(sprites.frame(state, index), "terracotta", size)
        if direction < 0:
            pm = pm.transformed(QTransform().scale(-1, 1))
        p.drawPixmap(round(x), floor - 15 * size // 16, pm)
        p.setPen(QColor("#E8E2D8"))
        p.setFont(QFont("Segoe UI", 10))
        p.drawText(QRect(0, floor, w, bar), Qt.AlignmentFlag.AlignCenter, sprites.STATES[state].label)
        p.end()
        frames.append(img)
    _save_gif(frames, "modo-mascota.gif", step)


def main() -> None:
    QApplication.setOrganizationName("ClaudeBuddyScreens")
    QApplication.setApplicationName("ClaudeBuddyScreens")
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(DEMO / "settings"))
    app = QApplication(sys.argv)
    make_demo_data()
    panel_shots(app)
    states_sheet()
    pet_scene()
    logo()
    states_gif()
    pet_gif()


if __name__ == "__main__":
    main()
