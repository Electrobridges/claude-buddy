"""Original 16x16 pixel buddy: states, animation frames and accessories (pure data, no Qt).

A frame is a tuple of 16 strings of 16 chars; each char is a palette key ('.' = transparent).
"""

from dataclasses import dataclass

SIZE = 16

# Palette keys: B body, D body shade, F feet, R blush, E eyes, M mouth, K ink/outline,
# W paper, L text (body colour), P pencil, Q eraser, H/h hat, Y gold, X red, G glasses/screen,
# N nightcap, S sparkle, V sweat drop, C terminal green
BODY = (
    "................",
    "................",
    "................",
    ".....BBBBBB.....",
    "...BBBBBBBBBB...",
    "..BBBBBBBBBBBB..",
    "..BBBBBBBBBBBB..",
    ".BBBBBBBBBBBBBB.",
    ".BBBBBBBBBBBBBB.",
    ".BBBBBBBBBBBBBB.",
    ".BBBBBBBBBBBBBB.",
    ".BBBBBBBBBBBBBB.",
    "..BBBBBBBBBBBB..",
    "...DDDDDDDDDD...",
    "...FF......FF...",
    "................",
)

ACCESSORIES: dict[str, tuple[str, ...]] = {
    "none": (),
    "wizard": (
        "........H.......",
        ".......HH.......",
        "......HHHH......",
        ".....HHYYHH.....",
        "...hhhhhhhhhh...",
    ),
    "sunglasses": (
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "................",
        "..GGWGGGGGWGGG..",
        "...GGGG..GGGG...",
    ),
    "crown": (
        "................",
        "....Y..YY..Y....",
        "....YYYYYYYY....",
        "....YXYYYYXY....",
    ),
    "nightcap": (
        ".............W..",
        "...........NN...",
        ".......NNNNN....",
        ".....NNNNNNN....",
        "...WWWWWWWWWW...",
    ),
}

BOOK = (
    ("KKKKKKKKKK", "KLLWKKLLWK", "KWWWKKWWWK", "KLWWKKLLLK", "KKKKKKKKKK"),
    ("KKKKKKKKKK", "KWWWKKLWWK", "KLLLKKWWWK", "KWWWKKLLWK", "KKKKKKKKKK"),
)
PAPER = ("KKKKKKKKKK", "KWWWWWWWWK", "KWWWWWWWWK", "KWWWWWWWWK", "KKKKKKKKKK")
TERMINAL = ("KKKKKKKKKK", "KGGGGGGGGK", "KGGGGGGGGK", "KGGGGGGGGK", "KKKKKKKKKK")
MAGNIFIER = (".KK.", "KWWK", "KWWK", ".KK.")
ZZZ = ("KKKK", "..K.", ".K..", "KKKK")
SPARKLE = (".S.", "SSS", ".S.")
QUESTION = ("KKK", "..K", ".K.", "...", ".K.")


@dataclass(frozen=True)
class StateSpec:
    label: str
    frames: int
    interval_ms: int


STATES: dict[str, StateSpec] = {
    "idle": StateSpec("En reposo", 16, 320),
    "thinking": StateSpec("Pensando", 6, 450),
    "reading": StateSpec("Leyendo", 8, 450),
    "writing": StateSpec("Escribiendo", 10, 300),
    "searching": StateSpec("Buscando", 8, 260),
    "running": StateSpec("Ejecutando", 6, 300),
    "waiting": StateSpec("Esperándote", 4, 420),
    "greeting": StateSpec("Saludando", 6, 220),
    "dragged": StateSpec("¡Me mueves!", 2, 260),
    "hover": StateSpec("Contento", 4, 500),
    "asleep": StateSpec("Durmiendo", 4, 700),
    "done": StateSpec("Hecho", 4, 300),
    "error": StateSpec("Error", 4, 400),
    # --- pet mode ---
    "walk": StateSpec("Paseando", 4, 170),
    "fall": StateSpec("¡Me caigo!", 2, 150),
    "land": StateSpec("¡Pum!", 2, 220),
    "pet": StateSpec("Mimos", 6, 260),
    "dizzy": StateSpec("Mareado", 4, 180),
    "angry": StateSpec("Enfadado", 4, 280),
    "eat": StateSpec("Comiendo", 6, 320),
    "poop": StateSpec("Haciendo caca", 6, 380),
    "yawn": StateSpec("Bostezando", 4, 450),
    "sad": StateSpec("Triste", 4, 600),
}

HEART = ("X.X", "XXX", ".X.")
COOKIE = ("YYYY", "YOYY", "YYOY", "YYYY")
POOP = (
    "................",
    "................",
    "................",
    "................",
    "................",
    "................",
    ".......O........",
    "......OOo.......",
    ".....OOOOO......",
    "......oOOOO.....",
    "....OOOOOOOO....",
    "...OOoOOOOOOO...",
    "..OOOOOOOOoOOO..",
    "..OOOOOOOOOOOO..",
    "...OOOOOOOOOO...",
    "................",
)


def poop_frame(index: int) -> tuple[str, ...]:
    """Poop left on the desktop, with wavy stink lines."""
    canvas: Canvas = [list(row) for row in POOP]
    lines = [(1, 5), (2, 4), (3, 5), (1, 10), (2, 11), (3, 10)] if index % 2 == 0 else \
            [(1, 4), (2, 5), (3, 4), (1, 11), (2, 10), (3, 11)]
    _px(canvas, lines, "g")
    return tuple("".join(row) for row in canvas)

# Idle loop: o=open, l/r=look left/right, b=blink, h=hop
_IDLE = "oooooll" "orr" "obohoo"

Canvas = list[list[str]]


def _stamp(canvas: Canvas, rows: tuple[str, ...], top: int = 0, left: int = 0) -> None:
    for r, line in enumerate(rows):
        for c, ch in enumerate(line):
            y, x = top + r, left + c
            if ch != "." and 0 <= y < SIZE and 0 <= x < SIZE:
                canvas[y][x] = ch


def _px(canvas: Canvas, points: list[tuple[int, int]], ch: str) -> None:
    for y, x in points:
        if 0 <= y < SIZE and 0 <= x < SIZE:
            canvas[y][x] = ch


def _eyes(canvas: Canvas, kind: str = "open", dy: int = 0, dx: int = 0) -> None:
    for col in (4, 10):
        if kind == "open":
            _px(canvas, [(7 + dy, col + dx), (7 + dy, col + 1 + dx),
                         (8 + dy, col + dx), (8 + dy, col + 1 + dx)], "E")
        elif kind == "closed":
            _px(canvas, [(8, col), (8, col + 1)], "E")
        elif kind == "happy":                       # ^ ^
            _px(canvas, [(7, col), (7, col + 1), (8, col - 1), (8, col + 2)], "E")
        elif kind == "x":
            c = col - 1 if col == 4 else col
            _px(canvas, [(6, c), (6, c + 2), (7, c + 1), (8, c), (8, c + 2)], "E")


def _mouth(canvas: Canvas, kind: str = "smile") -> None:
    shapes = {
        "smile": [(10, 6), (11, 7), (11, 8), (10, 9)],
        "flat": [(10, 7), (10, 8)],
        "frown": [(11, 6), (10, 7), (10, 8), (11, 9)],
        "o": [(10, 7), (10, 8), (11, 7), (11, 8)],
    }
    _px(canvas, shapes[kind], "M")


def _blush(canvas: Canvas) -> None:
    _px(canvas, [(10, 2), (10, 3), (10, 12), (10, 13)], "R")


def frame(state: str, index: int, accessory: str = "none") -> tuple[str, ...]:
    """Compose one animation frame. Unknown state/accessory fall back to idle/none."""
    state = state if state in STATES else "idle"
    spec = STATES[state]
    i = index % spec.frames
    canvas: Canvas = [list(row) for row in BODY]
    props: list[tuple[tuple[str, ...], int, int]] = []   # drawn over the accessory
    hop = crouch = False

    if state == "idle":
        step = _IDLE[i]
        if step == "b":
            _eyes(canvas, "closed")
        else:
            _eyes(canvas, "open", dx={"l": -1, "r": 1}.get(step, 0))
        hop = step == "h"
        _blush(canvas)
        _mouth(canvas, "smile")
    elif state == "thinking":
        _eyes(canvas, "open", dy=-1, dx=1)
        _blush(canvas)
        _mouth(canvas, "flat")
        dots = [(1, 11), (1, 13), (1, 15)][: (0, 1, 2, 3, 3, 0)[i]]
        props += [(("K",), y, x) for y, x in dots]
    elif state == "reading":
        _eyes(canvas, "open", dx=(-1, 0, 1, 0)[i % 4])
        props.append((BOOK[i // 4 % 2], 9, 3))
    elif state == "writing":
        _eyes(canvas, "open", dx=1 if i >= 4 else 0)
        props.append((PAPER, 9, 2))
        row, n = (10, i + 1) if i < 6 else (12, i - 5)
        text = [(10, 3 + k) for k in range(n if row == 10 else 6)]
        if row == 12:
            text += [(12, 3 + k) for k in range(n)]
        props += [(("L",), y, x) for y, x in text]
        tip = 3 + n
        props += [(("K",), row, tip), (("P",), row - 1, tip + 1),
                  (("P",), row - 2, tip + 2), (("Q",), row - 3, tip + 3)]
    elif state == "searching":
        x = (2, 4, 6, 8, 10, 8, 6, 4)[i]
        _eyes(canvas, "open", dx=-1 if x < 6 else (1 if x > 6 else 0))
        _mouth(canvas, "flat")
        props += [(MAGNIFIER, 9, x), (("K",), 13, x + 4), (("K",), 14, x + 5)]
    elif state == "running":
        _eyes(canvas, "open", dy=1)
        props.append((TERMINAL, 9, 3))
        props.append((("C",), 10, 4))                                  # prompt
        props += [(("C",), 10, 6 + k) for k in range((0, 1, 2, 3, 4, 4)[i])]
        if i % 2 == 0:
            props.append((("C",), 12, 4))                              # blinking cursor
    elif state == "waiting":
        _eyes(canvas, "open", dy=-1, dx=1)
        _blush(canvas)
        _mouth(canvas, "flat")
        props.append((QUESTION, 0, 12))
        hop = i == 2
    elif state == "greeting":
        _eyes(canvas, "happy")
        _blush(canvas)
        _mouth(canvas, "smile")
        hand = [(4, 15), (5, 15), (5, 14)] if i % 2 == 0 else [(7, 15), (8, 15)]
        _px(canvas, hand, "B")
        hop = i == 0
    elif state == "dragged":
        _eyes(canvas, "open", dy=-1)
        _mouth(canvas, "o")
        canvas[14] = list("...F........F..." if i == 0 else "....F......F....")
        canvas[15] = list("...F........F..." if i == 0 else "....F......F....")
    elif state == "hover":
        _eyes(canvas, "happy")
        _blush(canvas)
        _mouth(canvas, "smile")
        hop = i == 1
    elif state == "asleep":
        _eyes(canvas, "closed")
        _blush(canvas)
        props.append((ZZZ, 0 if i in (1, 2) else 1, 11 if i in (0, 3) else 12))
    elif state == "done":
        _eyes(canvas, "happy")
        _blush(canvas)
        _mouth(canvas, "smile")
        props.append((SPARKLE, 0, 0) if i % 2 == 0 else (SPARKLE, 0, 13))
        hop = i % 2 == 1
    elif state == "error":
        _eyes(canvas, "x")
        _mouth(canvas, "frown")
        props += [(("V",), 3 + i % 3, 14), (("V",), 4 + i % 3, 14)]
    elif state == "walk":                     # drawn facing right; mirrored when walking left
        _eyes(canvas, "open", dx=1)
        _blush(canvas)
        _mouth(canvas, "smile")
        canvas[14] = list("...FF......FF..." if i % 2 == 0 else "....FF......FF..")
        hop = i % 2 == 1
    elif state == "fall":
        _eyes(canvas, "open", dy=-1)
        _mouth(canvas, "o")
        dangle = "...F........F..." if i == 0 else "....F......F...."
        canvas[14], canvas[15] = list(dangle), list(dangle)
    elif state == "land":
        _eyes(canvas, "closed" if i == 0 else "open")
        _mouth(canvas, "flat")
        crouch = i == 0
    elif state == "pet":
        _eyes(canvas, "happy")
        _px(canvas, [(9, 2), (9, 3), (9, 12), (9, 13)], "R")     # extra blush
        _blush(canvas)
        _mouth(canvas, "smile")
        props.append((HEART, 2 - i % 3, 12))
        if i % 2:
            props.append((HEART, 2 - (i + 1) % 3, 1))
    elif state == "dizzy":
        _eyes(canvas, "x")
        _px(canvas, [(10, 6), (11, 7), (10, 8), (11, 9)], "M")    # wavy mouth
        orbit = [(2, 3), (1, 7), (2, 12), (1, 8)]
        props += [(("S",), *orbit[i % 4]), (("S",), *orbit[(i + 2) % 4])]
    elif state == "angry":
        _eyes(canvas, "open")
        _px(canvas, [(5, 4), (6, 5), (6, 10), (5, 11)], "E")      # frowning brows
        _px(canvas, [(10, 2), (10, 3), (10, 12), (10, 13)], "X")  # red cheeks
        _mouth(canvas, "frown")
        puff = [(1, 2), (0, 1)] if i % 2 == 0 else [(1, 13), (0, 14)]
        props += [(("W",), y, x) for y, x in puff]
    elif state == "eat":
        _eyes(canvas, "happy")
        _blush(canvas)
        _mouth(canvas, "o" if i % 2 else "flat")
        bite = (4, 4, 3, 3, 2, 0)[i]
        if bite:
            props.append((tuple(row[:bite] for row in COOKIE), 11, 9))
        else:
            props += [(("Y",), 13, 9), (("Y",), 14, 11)]           # crumbs
    elif state == "poop":
        relieved = i >= 4
        _eyes(canvas, "happy" if relieved else "closed")
        _mouth(canvas, "smile" if relieved else "flat")
        crouch = 1 <= i <= 3
        if i in (2, 3):
            props += [(("V",), 5, 14), (("V",), 6, 14)]
    elif state == "yawn":
        _eyes(canvas, "closed")
        _blush(canvas)
        if i in (1, 2):
            _px(canvas, [(10, 7), (10, 8), (11, 7), (11, 8), (12, 7), (12, 8)], "M")
        else:
            _mouth(canvas, "o")
    elif state == "sad":
        _eyes(canvas, "open", dy=1)
        _mouth(canvas, "frown")
        props.append((("V",), 10 + i % 2, 4))                    # tear

    _stamp(canvas, ACCESSORIES.get(accessory, ()))
    if hop:                                   # jump: the buddy (and its hat) moves up, props stay
        canvas = canvas[1:] + [["."] * SIZE]
    elif crouch:                              # squat: one pixel down
        canvas = [["."] * SIZE] + canvas[:-1]
    for rows, top, left in props:
        _stamp(canvas, rows, top, left)
    return tuple("".join(row) for row in canvas)


# Colour skins: body, shade, blush. Fixed colours are shared by all skins.
SKINS: dict[str, tuple[str, str, str, str]] = {
    # key: (label, body, shade, blush)
    "terracotta": ("Terracota", "#D97757", "#B05A3C", "#F0A08C"),
    "mint": ("Menta", "#4FBF94", "#348F6C", "#F29CA3"),
    "lavender": ("Lavanda", "#9B8BE0", "#7262C2", "#F2A0C8"),
    "sky": ("Cielo", "#58A6E6", "#3A7FBE", "#F2A0B0"),
    "lemon": ("Limón", "#E5C042", "#B8962A", "#F0957A"),
    "graphite": ("Grafito", "#6E7684", "#4C5360", "#E89AA0"),
}

ACCESSORY_LABELS = {
    "none": "Ninguno", "wizard": "Sombrero de mago", "sunglasses": "Gafas de sol",
    "crown": "Corona", "nightcap": "Gorro de dormir",
}

_FIXED = {
    "E": "#1E1E1E", "M": "#1E1E1E", "K": "#2A2A2A", "W": "#FBF7EF", "P": "#F2C14E",
    "Q": "#E88AA0", "H": "#6C4AB6", "h": "#8A6BD1", "Y": "#F2C14E", "X": "#D64545",
    "G": "#141414", "N": "#3A5BA0", "S": "#F2C14E", "V": "#7CC4F0", "C": "#5BE37D",
    "O": "#7A4A24", "o": "#9C6535", "g": "#9DB36A",
}


def palette(skin: str) -> dict[str, str]:
    _, body, shade, blush = SKINS.get(skin) or SKINS["terracotta"]
    return {**_FIXED, "B": body, "D": shade, "F": shade, "R": blush, "L": body}
