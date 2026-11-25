"""Desktop-pet behaviour (pure logic, no Qt): needs, gestures and a small state machine.

Inspired by classic desktop pets (eSheep, Shimeji, oneko, Desktop Goose): walks along the
taskbar, falls with gravity when dropped, chases the cursor, poops, eats, sleeps, likes being
petted and gets dizzy and then angry when shaken.
"""

import math
import random
from dataclasses import dataclass, field

GRAVITY = 2200.0        # px/s²
WALK_SPEED = 55.0       # px/s
CHASE_SPEED = 125.0
HARD_LANDING = 900.0    # vertical speed that hurts


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


@dataclass
class Needs:
    hunger: float = 20.0       # 0 = full, 100 = starving
    happiness: float = 70.0
    energy: float = 80.0

    def tick(self, dt: float, sleeping: bool) -> None:
        self.hunger = _clamp(self.hunger + dt / 120)          # +1 every 2 min
        self.happiness = _clamp(self.happiness - dt / 300)    # -1 every 5 min
        self.energy = _clamp(self.energy + dt / 4 if sleeping else self.energy - dt / 150)

    def advance_offline(self, seconds: float) -> None:
        """Time passed while the app was closed (capped at 12 h): hungrier, a bit sadder, rested."""
        s = max(0.0, min(seconds, 12 * 3600))
        self.hunger = _clamp(self.hunger + s / 240)
        self.happiness = _clamp(self.happiness - s / 900)
        self.energy = _clamp(self.energy + s / 60)

    @property
    def unhappy(self) -> bool:
        return self.hunger > 75 or self.happiness < 25

    def summary(self) -> str:
        return (f"Hambre {self.hunger:.0f}%  ·  Felicidad {self.happiness:.0f}%  ·  "
                f"Energía {self.energy:.0f}%")


class ReversalDetector:
    """Detects back-and-forth motion: `reversals` direction changes of at least `min_travel`
    pixels within `window` seconds. Used for petting (rubbing) and shaking (while dragging)."""

    def __init__(self, min_travel: float, reversals: int, window: float) -> None:
        self.min_travel, self.reversals, self.window = min_travel, reversals, window
        self._anchor: float | None = None
        self._direction = 0
        self._times: list[float] = []

    def reset(self) -> None:
        self._anchor, self._direction, self._times = None, 0, []

    def feed(self, x: float, t: float) -> bool:
        if self._anchor is None:
            self._anchor = x
            return False
        travel = x - self._anchor
        if abs(travel) < self.min_travel:
            return False
        direction = 1 if travel > 0 else -1
        if self._direction and direction != self._direction:
            self._times = [s for s in self._times if t - s <= self.window] + [t]
        self._direction, self._anchor = direction, x
        if len(self._times) >= self.reversals:
            self._times = []
            return True
        return False


@dataclass
class World:
    """What the pet can see this tick (screen coordinates of the pet window's top-left)."""
    floor_y: float
    min_x: float
    max_x: float
    cursor_x: float | None = None
    paused: bool = False          # panel open or Claude busy: stay put


# Brain state -> sprite state
_SPRITES = {
    "walk": "walk", "chase": "walk", "sleep": "asleep", "fall": "fall", "land": "land",
    "poop": "poop", "eat": "eat", "pet": "pet", "dizzy": "dizzy", "angry": "angry",
    "yawn": "yawn", "held": "dragged",
}
# How long timed states last (s), matching their animations
_DURATIONS = {"poop": 2.3, "eat": 2.0, "pet": 2.6, "land": 0.45, "dizzy": 1.6, "angry": 5.0, "yawn": 1.8}


@dataclass
class PetBrain:
    x: float
    y: float
    needs: Needs = field(default_factory=Needs)
    rng: random.Random = field(default_factory=random.Random)
    facing: int = 1               # 1 = right, -1 = left
    state: str = "idle"
    vy: float = 0.0
    events: list[tuple] = field(default_factory=list)   # ("poop", x, y) | ("say", text)

    def __post_init__(self) -> None:
        self._timer = self.rng.uniform(2, 4)
        self._target_x = self.x
        self._poop_in = self.rng.uniform(240, 480)
        self._angry_pending = False
        self._then_sleep = False
        self._complained = 0.0

    # --- outputs ------------------------------------------------------------
    @property
    def sprite_state(self) -> str:
        if self.state == "idle":
            return "sad" if self.needs.unhappy else "idle"
        return _SPRITES.get(self.state, "idle")

    def _say(self, text: str) -> None:
        self.events.append(("say", text))

    def _set(self, state: str, seconds: float | None = None) -> None:
        self.state = state
        self._timer = seconds if seconds is not None else _DURATIONS.get(state, 3.0)

    def _walk_to(self, x: float) -> None:
        self._target_x = x
        self._set("walk", 20)

    # --- simulation ---------------------------------------------------------
    def tick(self, dt: float, world: World) -> None:
        dt = min(dt, 0.25)
        self.needs.tick(dt, sleeping=self.state == "sleep")
        self._poop_in -= dt
        self._complained = max(0.0, self._complained - dt)
        if self.state == "held":
            return

        if self.state != "fall" and self.y < world.floor_y - 0.5:
            self.vy = 0.0
            self._set("fall", 99)
        if self.state == "fall":
            self.vy += GRAVITY * dt
            self.y += self.vy * dt
            if self.y >= world.floor_y:
                self.y, impact, self.vy = world.floor_y, self.vy, 0.0
                if impact > HARD_LANDING:
                    self._say("¡Ay!")
                    self.needs.happiness = _clamp(self.needs.happiness - 3)
                self._set("land")
            return

        self.y = world.floor_y                       # floor may move (taskbar, resolution)
        self.x = _clamp(self.x, world.min_x, world.max_x)
        self._timer -= dt

        if self.state in ("walk", "chase"):
            if world.paused:
                self._set("idle", 2)
                return
            if self.state == "chase":
                if world.cursor_x is None:
                    self._set("idle", 2)
                    return
                self._target_x = _clamp(world.cursor_x, world.min_x, world.max_x)
            dx = self._target_x - self.x
            if abs(dx) < 3 or self._timer <= 0:
                if self.state == "chase" and abs(dx) < 3:
                    self._say("¡Te pillé!")
                self._set("idle", self.rng.uniform(2, 6))
                return
            speed = CHASE_SPEED if self.state == "chase" else WALK_SPEED
            self.x += math.copysign(min(abs(dx), speed * dt), dx)
            self.facing = 1 if dx > 0 else -1
            return

        if self.state == "sleep":
            if self._timer <= 0:
                if self.needs.energy >= 95:
                    self._set("yawn")
                else:
                    self._timer = 5
            return

        if self._timer > 0:
            return
        self._finish(world)

    def _finish(self, world: World) -> None:
        """A timed state ended: apply its effect and pick what to do next."""
        done = self.state
        if done == "poop":
            behind = self.x + (-self.facing) * 30
            self.events.append(("poop", behind, self.y))
            self._poop_in = self.rng.uniform(300, 600)
            self._walk_to(_clamp(self.x + self.facing * self.rng.uniform(80, 160), world.min_x, world.max_x))
            return
        if done == "eat":
            self.needs.hunger = _clamp(self.needs.hunger - 45)
            self.needs.happiness = _clamp(self.needs.happiness + 8)
            self._poop_in = min(self._poop_in, self.rng.uniform(45, 90))   # what goes in…
        if done == "land" and self._angry_pending:
            self._angry_pending = False
            self._set("dizzy")
            return
        if done == "dizzy":
            self._say("¡Grrr!")
            self._set("angry")
            return
        if done == "yawn" and self._then_sleep:
            self._then_sleep = False
            self._set("sleep", 5)
            return
        self._choose_next(world)

    def _choose_next(self, world: World) -> None:
        n, r = self.needs, self.rng.random()
        if world.paused:
            self._set("idle", 2)
        elif self._poop_in <= 0:
            self._set("poop")
        elif n.energy < 15:
            self._then_sleep = True
            self._set("yawn")
        elif n.unhappy and self._complained <= 0 and r < 0.3:
            self._complained = 600
            self._say("Tengo hambre…" if n.hunger > 75 else "Me aburro…")
            self._set("idle", 4)
        elif r < 0.45:
            span = world.max_x - world.min_x
            target = world.min_x + self.rng.random() * span
            if abs(target - self.x) < 60:
                target = _clamp(self.x + self.rng.choice((-1, 1)) * 120, world.min_x, world.max_x)
            self._walk_to(target)
        elif r < 0.55 and world.cursor_x is not None:
            self._set("chase", 6)
        elif r < 0.62:
            self._set("yawn")
        else:
            self._set("idle", self.rng.uniform(3, 7))

    # --- interactions -------------------------------------------------------
    def grab(self) -> None:
        self.vy = 0.0
        self._set("held", 99)

    def drag_to(self, x: float, y: float) -> None:
        if x != self.x:
            self.facing = 1 if x > self.x else -1
        self.x, self.y = x, y

    def shaken(self) -> None:
        if not self._angry_pending:
            self._say("¡Para, que me mareo!")
        self._angry_pending = True
        self.needs.happiness = _clamp(self.needs.happiness - 12)

    def release(self, x: float, y: float, world: World) -> None:
        self.x, self.y = x, y
        if y < world.floor_y - 0.5:
            self._set("fall", 99)          # gravity takes over in tick()
        elif self._angry_pending:
            self._angry_pending = False
            self._set("dizzy")
        else:
            self._set("idle", 2)

    def petted(self) -> bool:
        if self.state in ("held", "fall"):
            return False
        if self.state in ("angry", "dizzy"):
            self._say("¡Déjame!")
            return False
        if self.state == "sleep":
            self._set("yawn")
            return False
        self.needs.happiness = _clamp(self.needs.happiness + 6)
        self._say("♥")
        self._set("pet")
        return True

    def feed(self) -> bool:
        if self.state in ("held", "fall", "sleep"):
            return False
        if self.needs.hunger < 10:
            self._say("No tengo hambre")
            return False
        self._say("¡Ñam!")
        self._set("eat")
        return True

    def chase(self) -> None:
        if self.state not in ("held", "fall"):
            self._set("chase", 6)

    def poop_cleaned(self) -> None:
        self.needs.happiness = _clamp(self.needs.happiness + 2)
