"""Pet mode logic: physics, needs, poops, petting, shaking."""

import random

from claude_buddy.pet import Needs, PetBrain, ReversalDetector, World
from claude_buddy.ui import sprites

FLOOR = 900.0


def world(**kw) -> World:
    return World(floor_y=FLOOR, min_x=0, max_x=1800, **kw)


def brain(x=500.0, y=FLOOR, seed=1, **kw) -> PetBrain:
    return PetBrain(x, y, rng=random.Random(seed), **kw)


def run(b: PetBrain, seconds: float, w: World | None = None, dt: float = 0.04) -> None:
    w = w or world()
    for _ in range(int(seconds / dt)):
        b.tick(dt, w)


def test_dropped_pet_falls_and_lands():
    b = brain(y=300)
    b.tick(0.04, world())
    assert b.state == "fall" and b.sprite_state == "fall"
    run(b, 1.5)
    assert b.y == FLOOR and b.state != "fall"
    assert ("say", "¡Ay!") in b.events                       # 600 px fall is a hard landing


def test_walks_towards_target_and_faces_it():
    b = brain(x=500)
    b._walk_to(300)
    run(b, 1.0)
    assert 300 <= b.x < 500 and b.facing == -1 and b.sprite_state == "walk"
    run(b, 5.0)
    assert b.x == 300 or b.state != "walk"


def test_paused_pet_does_not_wander():
    b = brain()
    run(b, 60, world(paused=True))
    assert b.x == 500 and b.state in ("idle", "yawn", "poop")


def test_poop_cycle_leaves_a_poop_and_walks_away():
    b = brain()
    b._poop_in = 0
    b._timer = 0
    run(b, 0.1)
    assert b.state == "poop" and b.sprite_state == "poop"
    run(b, 2.5)
    poops = [e for e in b.events if e[0] == "poop"]
    assert len(poops) == 1 and poops[0][2] == FLOOR
    assert b.state == "walk"


def test_feeding_reduces_hunger_and_speeds_up_poop():
    b = brain(needs=Needs(hunger=80))
    assert b.feed() and b.state == "eat"
    run(b, 2.1)
    assert b.needs.hunger < 40 and b._poop_in <= 90
    assert brain(needs=Needs(hunger=5)).feed() is False      # not hungry


def test_petting_makes_it_happy_but_not_when_angry():
    b = brain(needs=Needs(happiness=50))
    assert b.petted() and b.sprite_state == "pet" and b.needs.happiness == 56
    b._set("angry")
    assert not b.petted() and ("say", "¡Déjame!") in b.events


def test_shaking_makes_it_dizzy_then_angry():
    b = brain()
    b.grab()
    assert b.sprite_state == "dragged"
    b.drag_to(600, 500)
    b.shaken()
    b.release(600, FLOOR, world())                           # dropped on the floor
    assert b.state == "dizzy"
    run(b, 1.7)
    assert b.state == "angry" and b.sprite_state == "angry"


def test_shaken_in_the_air_gets_dizzy_after_landing():
    b = brain()
    b.grab()
    b.shaken()
    b.release(500, 400, world())
    run(b, 1.2)
    assert b.state in ("dizzy", "angry")


def test_unhappy_pet_looks_sad():
    assert brain(needs=Needs(hunger=90)).sprite_state == "sad"


def test_tired_pet_yawns_then_sleeps_and_recovers():
    b = brain(needs=Needs(energy=5))
    b._timer = 0
    run(b, 2.0)
    assert b.state == "sleep" and b.sprite_state == "asleep"
    run(b, 450, dt=0.25)                                     # tick() caps dt at 0.25 s
    assert b.needs.energy >= 90 and b.state != "sleep"


def test_needs_over_time_and_offline():
    n = Needs(hunger=0, happiness=100, energy=100)
    n.tick(120, sleeping=False)
    assert round(n.hunger) == 1 and n.energy < 100
    n.advance_offline(10 ** 9)                                # capped at 12 h
    assert n.hunger <= 100 and n.energy == 100


def test_reversal_detector_petting():
    d = ReversalDetector(min_travel=6, reversals=3, window=1.6)
    xs = [0, 10, 0, 10, 0, 10]
    hits = [d.feed(x, t * 0.2) for t, x in enumerate(xs)]
    assert hits[-1] or any(hits)
    slow = ReversalDetector(min_travel=6, reversals=3, window=1.6)
    assert not any(slow.feed(x, t * 2.0) for t, x in enumerate(xs))    # too slow
    tiny = ReversalDetector(min_travel=6, reversals=3, window=1.6)
    assert not any(tiny.feed(x, t * 0.1) for t, x in enumerate([0, 2, 0, 2, 0, 2]))


def test_pet_sprites_are_valid():
    allowed = set(sprites.palette("terracotta")) | {"."}
    for state in ("walk", "fall", "land", "pet", "dizzy", "angry", "eat", "poop", "yawn", "sad"):
        for i in range(sprites.STATES[state].frames):
            grid = sprites.frame(state, i)
            assert len(grid) == 16 and all(len(r) == 16 for r in grid) and set("".join(grid)) <= allowed
    assert set("".join(sprites.poop_frame(0))) <= allowed