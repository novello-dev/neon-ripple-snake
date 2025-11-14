"""Ripple enemy behaviors for Neon Snake."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Iterable, List, Sequence, Tuple

import pygame

from .config import BLOCK, GRID_CELLS
from .effects import GridRipple


@dataclass(slots=True)
class RippleEnemy:
    x: float
    y: float
    speed: float
    size: int
    color: pygame.Color
    age: float = 0.0
    warmup: float = 0.45


NEON_RED = pygame.Color(255, 70, 90)


def _enemy_color() -> pygame.Color:
    jitter = random.uniform(0.9, 1.05)
    return pygame.Color(
        min(255, int(NEON_RED.r * jitter)),
        int(NEON_RED.g * 0.4 * jitter),
        min(255, int(NEON_RED.b * jitter)),
    )


def _find_spawn_point(
    avoid_positions: Sequence[Tuple[float, float]],
    enemies: Sequence[RippleEnemy],
    min_distance_from_avoid: float,
    min_spacing: float,
) -> Tuple[float, float] | None:
    """Pick a grid cell center away from fruits and other enemies."""

    attempts = 60
    jitter = BLOCK * 0.35
    for _ in range(attempts):
        gx = random.randint(1, max(1, GRID_CELLS - 2))
        gy = random.randint(1, max(1, GRID_CELLS - 2))
        x = gx * BLOCK + BLOCK / 2 + random.uniform(-jitter, jitter)
        y = gy * BLOCK + BLOCK / 2 + random.uniform(-jitter, jitter)

        if avoid_positions and min_distance_from_avoid > 0:
            too_close = False
            for ax, ay in avoid_positions:
                if math.hypot(x - ax, y - ay) < min_distance_from_avoid:
                    too_close = True
                    break
            if too_close:
                continue

        if min_spacing > 0:
            crowded = False
            for enemy in enemies:
                if math.hypot(x - enemy.x, y - enemy.y) < min_spacing:
                    crowded = True
                    break
            if crowded:
                continue

        return x, y

    return None


def spawn_enemy_random(
    enemies: List[RippleEnemy],
    *,
    avoid_positions: Sequence[Tuple[float, float]] = (),
    min_distance_from_avoid: float = 0.0,
    min_spacing: float = 0.0,
    speed_range: tuple[float, float] = (55.0, 105.0),
    color: pygame.Color | None = None,
    warmup: float = 0.45,
    on_spawn: Callable[[Tuple[float, float], pygame.Color], None] | None = None,
    add_to_list: bool = True,
) -> RippleEnemy | None:
    position = _find_spawn_point(
        avoid_positions,
        enemies,
        min_distance_from_avoid,
        min_spacing,
    )
    if position is None:
        return None

    speed_min, speed_max = speed_range
    if speed_max < speed_min:
        speed_max = speed_min
    speed = (
        random.uniform(speed_min, speed_max)
        if speed_max > speed_min
        else float(speed_min)
    )
    size = random.randint(10, 16)
    enemy_color = pygame.Color(color) if color else _enemy_color()
    enemy = RippleEnemy(
        x=position[0],
        y=position[1],
        speed=speed,
        size=size,
        color=enemy_color,
        age=0.0,
        warmup=warmup,
    )
    if add_to_list:
        enemies.append(enemy)
    if on_spawn:
        on_spawn(position, pygame.Color(enemy_color))
    return enemy


def update_enemies(
    enemies: List[RippleEnemy], target_pos: Tuple[float, float], dt: float
) -> List[RippleEnemy]:
    if dt <= 0:
        return enemies
    target_x, target_y = target_pos
    for enemy in enemies:
        dir_x = target_x - enemy.x
        dir_y = target_y - enemy.y
        length = math.hypot(dir_x, dir_y)
        if length <= 0.001:
            continue
        enemy.age = min(enemy.warmup, enemy.age + dt)
        warmup_ratio = enemy.age / enemy.warmup if enemy.warmup > 0 else 1.0
        speed_scale = 0.2 + 0.65 * warmup_ratio
        effective_speed = enemy.speed * speed_scale
        step = effective_speed * dt / length
        enemy.x += dir_x * step
        enemy.y += dir_y * step
    return enemies


def enemies_hit_snake(
    enemies: Iterable[RippleEnemy], snake_blocks: Sequence[Sequence[int]]
) -> bool:
    if not enemies:
        return False
    block_rect = pygame.Rect(0, 0, BLOCK, BLOCK)
    for block in snake_blocks:
        block_rect.topleft = (block[0], block[1])
        for enemy in enemies:
            enemy_rect = pygame.Rect(0, 0, enemy.size, enemy.size)
            enemy_rect.center = (int(enemy.x), int(enemy.y))
            if enemy_rect.colliderect(block_rect):
                return True
    return False


def cull_enemies_hit_by_ripples(
    enemies: List[RippleEnemy], ripples: Sequence[GridRipple]
) -> tuple[List[RippleEnemy], List[RippleEnemy]]:
    if not enemies or not ripples:
        return enemies, []
    survivors: List[RippleEnemy] = []
    destroyed: List[RippleEnemy] = []
    for enemy in enemies:
        enemy_destroyed = False
        for ripple in ripples:
            if ripple.duration <= 0:
                continue
            progress = 1.0 - (ripple.timer / ripple.duration)
            if progress <= 0:
                continue
            radius_cells = ripple.max_radius * progress
            dist_cells = math.hypot(enemy.x - ripple.x, enemy.y - ripple.y) / BLOCK
            if abs(dist_cells - radius_cells) <= ripple.band_width:
                enemy_destroyed = True
                destroyed.append(enemy)
                break
        if not enemy_destroyed:
            survivors.append(enemy)
    return survivors, destroyed


def draw_enemies(surface: pygame.Surface, enemies: Iterable[RippleEnemy]) -> None:
    for enemy in enemies:
        glow_size = enemy.size + 10
        glow = pygame.Surface((glow_size, glow_size), pygame.SRCALPHA)
        glow_color = pygame.Color(enemy.color)
        glow_color.a = 90
        pygame.draw.circle(
            glow, glow_color, (glow_size // 2, glow_size // 2), glow_size // 2
        )

        body_rect = pygame.Rect(0, 0, enemy.size, enemy.size)
        body_rect.center = (glow_size // 2, glow_size // 2)
        pygame.draw.rect(
            glow, enemy.color, body_rect, border_radius=max(2, enemy.size // 3)
        )

        surface.blit(glow, glow.get_rect(center=(enemy.x, enemy.y)))
