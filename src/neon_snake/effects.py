"""Shared visual effect helpers for Neon Snake."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterable, Sequence

import pygame

from .config import (
    BLOCK,
    GRID_CELLS,
    PARTICLE_DIRECTIONS,
    PARTICLE_LIFE,
    SNAKE_WASH_SPEED,
    SNAKE_WASH_WIDTH,
)

Particle = dict[str, float | pygame.Color | str]


@dataclass(slots=True)
class GridRipple:
    x: float
    y: float
    duration: float
    timer: float
    max_radius: float
    band_width: float
    intensity: float
    color: tuple[int, int, int]


@dataclass(slots=True)
class SnakeWash:
    color: tuple[int, int, int]
    progress: float
    speed: float
    width: float


def spawn_particles(
    particles: list[Particle],
    origin: tuple[int, int],
    color_choices: Sequence[pygame.Color],
    count: int = 22,
) -> None:
    """Emit a burst of chunky neon particles from the given origin."""

    cx = origin[0] + BLOCK / 2
    cy = origin[1] + BLOCK / 2

    for _ in range(count):
        dir_x, dir_y = random.choice(PARTICLE_DIRECTIONS)
        speed = random.uniform(80, 210)
        size = random.uniform(3.0, 7.0)
        color = pygame.Color(random.choice(color_choices))
        particles.append(
            {
                "x": cx,
                "y": cy,
                "vx": dir_x * speed,
                "vy": dir_y * speed,
                "life": PARTICLE_LIFE,
                "size": size,
                "color": color,
            }
        )


def spawn_head_sparks(
    particles: list[Particle],
    head_pos: tuple[int, int],
    direction: tuple[int, int],
    color: pygame.Color,
    *,
    count: int = 3,
) -> None:
    """Emit small sparks pointing along the snake head direction."""

    cx = head_pos[0] + BLOCK / 2
    cy = head_pos[1] + BLOCK / 2
    dir_x, dir_y = direction

    for _ in range(count):
        jitter_x = dir_x + random.uniform(-0.4, 0.4)
        jitter_y = dir_y + random.uniform(-0.4, 0.4)
        length = math.hypot(jitter_x, jitter_y) or 1.0
        speed = random.uniform(90, 170)
        vx = (jitter_x / length) * speed
        vy = (jitter_y / length) * speed

        spark_color = pygame.Color(color)
        spark_color.r = min(255, spark_color.r + 40)
        spark_color.g = min(255, spark_color.g + 40)
        spark_color.b = min(255, spark_color.b + 40)

        particles.append(
            {
                "x": cx,
                "y": cy,
                "vx": vx,
                "vy": vy,
                "life": random.uniform(0.12, 0.2),
                "size": random.uniform(2.0, 3.0),
                "color": spark_color,
                "type": "head",
            }
        )


def spawn_ripple(
    ripples: list[GridRipple],
    origin: tuple[int, int],
    color: pygame.Color,
    *,
    duration: float,
    radius_cells: float,
    band_width: float,
    intensity: float,
) -> None:
    """Push a ripple that marches across the grid from origin."""

    cx = float(origin[0] + BLOCK / 2)
    cy = float(origin[1] + BLOCK / 2)
    ripples.append(
        GridRipple(
            x=cx,
            y=cy,
            duration=duration,
            timer=duration,
            max_radius=radius_cells,
            band_width=band_width,
            intensity=intensity,
            color=(color.r, color.g, color.b),
        )
    )


def start_snake_wash(
    washes: list[SnakeWash],
    color: pygame.Color,
    *,
    speed: float = SNAKE_WASH_SPEED,
    width: float = SNAKE_WASH_WIDTH,
) -> None:
    """Start a color wash that flows along the snake body."""

    washes.append(
        SnakeWash(
            color=(color.r, color.g, color.b),
            progress=-width,
            speed=speed,
            width=width,
        )
    )


def update_particles(particles: list[Particle], dt: float) -> list[Particle]:
    """Advance particle positions and trim dead ones."""

    if dt <= 0:
        return particles

    for particle in particles:
        particle["x"] += particle["vx"] * dt  # type: ignore[index]
        particle["y"] += particle["vy"] * dt  # type: ignore[index]
        particle["life"] = max(0.0, particle["life"] - dt)  # type: ignore[index]
    return [p for p in particles if p["life"] > 0]  # type: ignore[index]


def update_ripples(ripples: list[GridRipple], dt: float) -> list[GridRipple]:
    """Reduce ripple timers and discard elapsed ones."""

    if dt <= 0:
        return ripples
    for ripple in ripples:
        ripple.timer = max(0.0, ripple.timer - dt)
    return [rip for rip in ripples if rip.timer > 0]


def update_snake_washes(
    washes: list[SnakeWash], dt: float, max_index: int
) -> list[SnakeWash]:
    """Move neon washes along the snake indexes."""

    if dt <= 0:
        return washes
    for wash in washes:
        wash.progress += wash.speed * dt
    return [wash for wash in washes if (wash.progress - wash.width) <= max_index]


def draw_particles(surface: pygame.Surface, particles: Iterable[Particle]) -> None:
    """Draw rounded neon particles onto the target surface."""

    for particle in particles:
        life = float(particle.get("life", PARTICLE_LIFE))
        alpha = int(255 * (life / PARTICLE_LIFE))
        if alpha <= 0:
            continue

        size = int(particle.get("size", 4))
        base_color = particle.get("color", pygame.Color(255, 255, 255))
        if not isinstance(base_color, pygame.Color):
            if isinstance(base_color, (tuple, list)):
                base_color = pygame.Color(*base_color)
            elif isinstance(base_color, str):
                base_color = pygame.Color(base_color)
            elif isinstance(base_color, (int, float)):
                base_color = pygame.Color(int(base_color))
            else:
                base_color = pygame.Color(255, 255, 255)

        color = pygame.Color(base_color.r, base_color.g, base_color.b, alpha)
        side = max(1, size)
        surf = pygame.Surface((side, side), pygame.SRCALPHA)
        rect = pygame.Rect(0, 0, side, side)
        pygame.draw.rect(surf, color, rect, border_radius=max(2, side // 3))

        x = int(particle["x"]) - side // 2  # type: ignore[index]
        y = int(particle["y"]) - side // 2  # type: ignore[index]
        surface.blit(surf, (x, y))


def draw_ripples(surface: pygame.Surface, ripples: Iterable[GridRipple]) -> None:
    """Tint grid cells inside ripple bands using an overlay surface."""

    ripples_list = list(ripples)
    if not ripples_list:
        return

    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    for ripple in ripples_list:
        if ripple.duration <= 0:
            continue
        progress = 1.0 - (ripple.timer / ripple.duration)
        fade = ripple.timer / ripple.duration if ripple.duration else 0.0
        radius = max(0.0, ripple.max_radius * progress)
        if fade <= 0 or radius <= 0:
            continue

        center_cx = ripple.x / BLOCK
        center_cy = ripple.y / BLOCK
        max_dist = radius + ripple.band_width + 1.0
        min_gx = max(0, int(center_cx - max_dist))
        max_gx = min(GRID_CELLS - 1, int(center_cx + max_dist))
        min_gy = max(0, int(center_cy - max_dist))
        max_gy = min(GRID_CELLS - 1, int(center_cy + max_dist))

        for gx in range(min_gx, max_gx + 1):
            for gy in range(min_gy, max_gy + 1):
                cell_center_x = gx * BLOCK + BLOCK / 2
                cell_center_y = gy * BLOCK + BLOCK / 2
                dist_cells = (
                    math.hypot(cell_center_x - ripple.x, cell_center_y - ripple.y)
                    / BLOCK
                )
                band_distance = abs(dist_cells - radius)
                if band_distance > ripple.band_width:
                    continue
                strength = (
                    (1.0 - band_distance / ripple.band_width) * ripple.intensity * fade
                )
                if strength <= 0:
                    continue
                tint = pygame.Color(*ripple.color)
                tint.a = int(200 * strength)
                cell_rect = pygame.Rect(gx * BLOCK, gy * BLOCK, BLOCK, BLOCK)
                overlay.fill(tint, cell_rect)

    surface.blit(overlay, (0, 0))
