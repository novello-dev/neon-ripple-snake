"""Neon Snake with a fixed-step loop, neon flair, and compact logic."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame

from .audio import AudioEngine
from .config import (
    BLOCK,
    BONUS_CHANCE,
    BONUS_DURATION,
    BONUS_POINTS,
    DIRECTIONS,
    FONT_NAME,
    FONT_SIZE,
    FPS,
    FRUIT_COLORS,
    GRID_CELLS,
    HIGHSCORE_FILE,
    KEY_TO_DIRECTION,
    MAX_MOVES_PER_SECOND,
    MOVES_PER_SECOND,
    OPPOSITE,
    PALETTE,
    SNAKE_WASH_SPEED,
    SNAKE_WASH_WIDTH,
    SPEED_STEP,
    TRAIL_LIFE,
    WINDOW_SIZE,
)
from .effects import (
    GridRipple,
    SnakeWash,
    draw_particles,
    draw_ripples,
    spawn_head_sparks,
    spawn_particles,
    spawn_ripple,
    start_snake_wash,
    update_particles,
    update_ripples,
    update_snake_washes,
)
from .enemies import (
    RippleEnemy,
    cull_enemies_hit_by_ripples,
    draw_enemies,
    enemies_hit_snake,
    spawn_enemy_random,
)
from .enemies import update_enemies as update_enemy_positions


@dataclass(slots=True)
class BonusFruit:
    """Lightweight record describing the temporary yellow fruit."""

    pos: tuple[int, int]
    timer: float


@dataclass(slots=True)
class SpawnIndicator:
    x: float
    y: float
    time: float
    duration: float
    color: tuple[int, int, int]
    payload: RippleEnemy | None = None


SPAWN_INDICATOR_COLOR = (255, 70, 90)
SPAWN_INDICATOR_DURATION = (0.9, 1.2)


class NeonSnake:
    """Encapsulates game state, logic (step), and rendering (draw)."""

    def __init__(self) -> None:
        pygame.init()
        # OS window (final target) – double buffer + scaled for smoother edges
        self._base_window_flags = pygame.DOUBLEBUF | pygame.SCALED
        self.fullscreen = False
        self.window = pygame.display.set_mode(
            (WINDOW_SIZE, WINDOW_SIZE), self._base_window_flags
        )
        pygame.display.set_caption("Neon Snake")
        # Offscreen scene (for shake + postFX)
        self.scene = pygame.Surface((WINDOW_SIZE, WINDOW_SIZE)).convert_alpha()
        # Scanline overlay
        self.scanlines = self._build_scanlines()
        self.scanlines_enabled: bool = True

        # VFX feature toggles
        self.shake_enabled: bool = True
        self.particles_enabled: bool = True
        self.trail_enabled: bool = True
        self.ripples_enabled: bool = True
        self.performance_mode: bool = False

        self.background = self._build_background()
        self.font = pygame.font.SysFont(FONT_NAME, FONT_SIZE)
        self.audio = AudioEngine()

        # Screen shake state
        self.shake_timer: float = 0.0
        self.shake_intensity: float = 0.0
        self.shake_duration: float = 0.0

        # High score + speed info
        self.high_score: int = 0
        self._load_high_score()
        self.current_speed: float = float(MOVES_PER_SECOND)

        self.enemy_spawns_active: bool = False
        self.enemy_spawn_timer: float = 0.0
        self.fruits_eaten: int = 0
        self.spawn_indicators: list[SpawnIndicator] = []

        self._reset_game_state()

    # --- High score persistence ----------------------------------------

    def _load_high_score(self) -> None:
        try:
            HIGHSCORE_FILE.parent.mkdir(parents=True, exist_ok=True)
            text = HIGHSCORE_FILE.read_text(encoding="utf-8")
            self.high_score = int(text.strip() or "0")
        except (OSError, ValueError):
            self.high_score = 0

    def _save_high_score(self) -> None:
        try:
            HIGHSCORE_FILE.parent.mkdir(parents=True, exist_ok=True)
            HIGHSCORE_FILE.write_text(str(self.high_score), encoding="utf-8")
        except OSError:
            pass

    def _reset_game_state(self) -> None:
        """Reset snake, fruit, timers, and fx so we can restart quickly."""
        self.score = 0
        start_x = BLOCK * 10
        start_y = BLOCK * 5
        self.head = [start_x, start_y]
        self.snake_blocks = [
            [start_x, start_y],
            [start_x - BLOCK, start_y],
            [start_x - BLOCK * 2, start_y],
        ]
        self.direction = "RIGHT"
        self.pending_direction = "RIGHT"
        self.state = "running"

        self.fruits_eaten = 0
        self.trail = []
        self.particles = []
        self.grid_ripples: list[GridRipple] = []
        self.snake_washes: list[SnakeWash] = []
        self.enemies: list[RippleEnemy] = []
        self.spawn_indicators = []
        self.enemy_spawns_active = False
        self.enemy_spawn_timer = 0.0
        self.bonus: BonusFruit | None = None

        self.current_speed = float(MOVES_PER_SECOND)
        self.move_interval = 1.0 / self.current_speed
        self._move_accumulator = 0.0

        self.spawn_fruit()
        self._update_speed()
        self._enemy_idle_phase = 0.0

    def _toggle_pause(self) -> None:
        """Toggle between paused and running states (ignore game over)."""
        if self.state == "game_over":
            return
        if self.state == "paused":
            self.state = "running"
            self._move_accumulator = 0.0
        else:
            self.state = "paused"

    def _update_speed(self) -> None:
        """Update snake speed and movement interval based on score."""
        if SPEED_STEP <= 0:
            target_speed = float(MOVES_PER_SECOND)
        else:
            bonus = self.score / SPEED_STEP
            target_speed = float(MOVES_PER_SECOND) + bonus
        target_speed = min(float(MAX_MOVES_PER_SECOND), max(1.0, target_speed))
        self.current_speed = target_speed
        self.move_interval = 1.0 / self.current_speed

    def _apply_display_mode(self) -> None:
        """Recreate the main window honoring the fullscreen toggle."""
        flags = self._base_window_flags
        if self.fullscreen:
            flags |= pygame.FULLSCREEN
        self.window = pygame.display.set_mode((WINDOW_SIZE, WINDOW_SIZE), flags)
        title = "Neon Snake" + (" [Fullscreen]" if self.fullscreen else "")
        pygame.display.set_caption(title)

    def _pulse_offset(self, phase_shift: int = 0) -> int:
        """Return a small oscillating value used by fruit glow animations."""
        frame = ((pygame.time.get_ticks() // 70) + phase_shift) % 6
        step = frame if frame < 3 else 5 - frame
        return step  # 0..2

    def _draw_fruit_sprite(
        self, pos: tuple[int, int], color: pygame.Color, phase_shift: int = 0
    ) -> pygame.Rect:
        """Draw a rounded neon fruit and return the occupied rect."""
        pulse = self._pulse_offset(phase_shift)
        halo = 10 + pulse * 2
        sprite_size = BLOCK + halo
        sprite = pygame.Surface((sprite_size, sprite_size), pygame.SRCALPHA)
        center = sprite_size // 2

        glow_color = pygame.Color(color)
        glow_color.a = 85
        pygame.draw.circle(sprite, glow_color, (center, center), BLOCK // 2 + pulse + 5)

        fruit_radius = BLOCK // 2 + pulse
        body_rect = pygame.Rect(0, 0, fruit_radius * 2, fruit_radius * 2)
        body_rect.center = (center, center)

        body_surface = pygame.Surface(body_rect.size, pygame.SRCALPHA)
        base_color = pygame.Color(color)
        pygame.draw.ellipse(body_surface, base_color, body_surface.get_rect())

        # Soft rim for depth
        rim_color = pygame.Color(
            max(0, color.r - 30),
            max(0, color.g - 30),
            max(0, color.b - 30),
            220,
        )
        pygame.draw.ellipse(
            body_surface,
            rim_color,
            body_surface.get_rect().inflate(0, -4),
            width=3,
        )

        # Gentle vertical gradient so fruits look juicy instead of flat
        gradient = pygame.Surface(body_rect.size, pygame.SRCALPHA)
        for y in range(body_rect.height):
            t = y / max(1, body_rect.height - 1)
            shade = pygame.Color(
                min(255, int(base_color.r * (0.75 + 0.25 * (1 - t)))),
                min(255, int(base_color.g * (0.8 + 0.2 * (1 - t)))),
                min(255, int(base_color.b * (0.85 + 0.15 * (1 - t)))),
                int(120 * (1 - t)),
            )
            pygame.draw.line(gradient, shade, (0, y), (body_rect.width, y))
        body_surface.blit(gradient, (0, 0), special_flags=pygame.BLEND_PREMULTIPLIED)

        sprite.blit(body_surface, body_rect.topleft)

        # Stem + leaf for extra silhouette cues
        stem_color = pygame.Color(50, 30, 15)
        pygame.draw.rect(
            sprite,
            stem_color,
            pygame.Rect(center - 2, body_rect.top - 6, 4, 8),
            border_radius=2,
        )
        leaf = pygame.Surface((BLOCK // 2, BLOCK // 3), pygame.SRCALPHA)
        pygame.draw.ellipse(leaf, pygame.Color(60, 220, 120, 210), leaf.get_rect())
        leaf = pygame.transform.rotate(leaf, -25)
        sprite.blit(leaf, (center, body_rect.top - leaf.get_height() // 2))

        # Specular highlights: two streaks + a small dot
        highlight_surface = pygame.Surface(body_rect.size, pygame.SRCALPHA)
        gloss_height = max(2, int(fruit_radius / 1.5))
        pygame.draw.ellipse(
            highlight_surface,
            pygame.Color(255, 255, 255, 120),
            pygame.Rect(2, 4, fruit_radius, gloss_height),
        )
        pygame.draw.ellipse(
            highlight_surface,
            pygame.Color(255, 255, 255, 50),
            pygame.Rect(
                6,
                body_rect.height // 2,
                fruit_radius,
                max(2, fruit_radius // 2),
            ),
        )
        pygame.draw.circle(
            highlight_surface,
            pygame.Color(255, 255, 255, 150),
            (fruit_radius + 2, 6),
            3,
        )
        sprite.blit(
            highlight_surface,
            body_rect.topleft,
            special_flags=pygame.BLEND_PREMULTIPLIED,
        )

        top_left = (pos[0] - halo // 2, pos[1] - halo // 2)
        self.scene.blit(sprite, top_left)
        return pygame.Rect(top_left, (sprite_size, sprite_size))

    def _leave_trail(self, pos: tuple[int, int]) -> None:
        if not self.trail_enabled:
            return
        self.trail.append({"x": float(pos[0]), "y": float(pos[1]), "life": TRAIL_LIFE})
        if len(self.trail) > 80:
            self.trail.pop(0)

    # --- Screen shake helpers -----------------------------------------

    def _start_shake(self, intensity: float, duration: float) -> None:
        """Start a short camera shake effect."""
        if not self.shake_enabled:
            return
        self.shake_intensity = max(self.shake_intensity, intensity)
        self.shake_duration = max(self.shake_duration, duration)
        self.shake_timer = self.shake_duration

    def _current_shake_offset(self) -> tuple[int, int]:
        if self.shake_timer <= 0.0 or self.shake_duration <= 0.0:
            return 0, 0
        t = self.shake_timer / self.shake_duration
        strength = self.shake_intensity * t
        ox = int(random.uniform(-strength, strength))
        oy = int(random.uniform(-strength, strength))
        return ox, oy

    # --- Ripple helpers ----------------------------------------------

    def _emit_ripple(
        self,
        origin: tuple[int, int],
        color: pygame.Color,
        *,
        duration: float,
        radius_cells: float,
        band_width: float,
        intensity: float,
    ) -> None:
        spawn_ripple(
            self.grid_ripples,
            origin,
            color,
            duration=duration,
            radius_cells=radius_cells,
            band_width=band_width,
            intensity=intensity,
        )
        self.audio.play("ripple")

    def _register_spawn_indicator(
        self,
        pos: tuple[float, float],
        color: pygame.Color,
        *,
        payload: RippleEnemy | None = None,
        duration: float | None = None,
    ) -> None:
        countdown = duration or random.uniform(*SPAWN_INDICATOR_DURATION)
        marker = SpawnIndicator(
            x=float(pos[0]),
            y=float(pos[1]),
            time=countdown,
            duration=countdown,
            color=(int(color.r), int(color.g), int(color.b)),
            payload=payload,
        )
        self.spawn_indicators.append(marker)
        self.audio.play("spawn_warning")

    def _update_spawn_indicators(self, dt: float) -> None:
        if dt <= 0:
            return
        survivors: list[SpawnIndicator] = []
        for marker in self.spawn_indicators:
            marker.time = max(0.0, marker.time - dt)
            if marker.time <= 0.0:
                if marker.payload is not None:
                    marker.payload.age = 0.0
                    marker.payload.warmup = max(0.35, marker.payload.warmup)
                    self.enemies.append(marker.payload)
                    spawn_particles(
                        self.particles,
                        (
                            int(marker.x - BLOCK / 2),
                            int(marker.y - BLOCK / 2),
                        ),
                        [pygame.Color(*marker.color)],
                        count=10,
                    )
                    self.audio.play("enemy_spawn")
                continue
            survivors.append(marker)
        self.spawn_indicators = survivors

    def _start_enemy_spawns(self) -> None:
        if self.enemy_spawns_active:
            return
        self.enemy_spawns_active = True
        self._schedule_enemy_spawn()

    def _desired_enemy_count(self) -> int:
        """Gradually raise the concurrent enemy cap as the match progresses."""
        wave_bonus = self.fruits_eaten // 2
        score_bonus = int(self.score // 80)
        desired = 1 + wave_bonus + score_bonus
        return max(1, min(5, desired))

    def _pending_spawn_count(self) -> int:
        return sum(1 for marker in self.spawn_indicators if marker.payload is not None)

    def _schedule_enemy_spawn(self) -> None:
        speed_factor = max(1.0, self.current_speed / MOVES_PER_SECOND)
        score_factor = min(3.0, self.score / 60.0)
        fruit_factor = min(1.0, self.fruits_eaten / 6)
        difficulty = (
            1.0 + 0.45 * (speed_factor - 1.0) + 0.3 * score_factor + 0.25 * fruit_factor
        )
        base_delay = random.uniform(1.8, 2.6)
        active_total = len(self.enemies) + self._pending_spawn_count()
        deficit = max(0, self._desired_enemy_count() - active_total)
        urgency = 1.0 + 0.4 * deficit if deficit else 0.8
        delay = max(0.45, base_delay / max(0.6, difficulty / urgency))
        self.enemy_spawn_timer = delay

    def _tick_enemy_spawn_timer(self, dt: float) -> None:
        if not self.enemy_spawns_active or dt <= 0:
            return
        self.enemy_spawn_timer = max(0.0, self.enemy_spawn_timer - dt)
        if self.enemy_spawn_timer > 0.0:
            return
        desired = self._desired_enemy_count()
        pending = self._pending_spawn_count()
        active_total = len(self.enemies) + pending
        deficit = desired - active_total
        if deficit <= 0:
            self._schedule_enemy_spawn()
            return
        spawn_budget = max(1, min(3, deficit))
        spawned_any = False
        attempts = 0
        while attempts < spawn_budget:
            spawned = self._spawn_enemy()
            spawned_any = spawned_any or spawned
            attempts += 1
            if not spawned:
                break
        if spawned_any:
            self._schedule_enemy_spawn()
        else:
            self.enemy_spawn_timer = 0.4

    def _spawn_enemy(self) -> bool:
        snake_speed_px = self.current_speed * BLOCK
        speed_min = max(28.0, snake_speed_px * 0.4)
        speed_max = max(speed_min + 4.0, snake_speed_px * 0.6)
        avoid_positions: list[tuple[float, float]] = [
            (self.fruit_pos[0] + BLOCK / 2, self.fruit_pos[1] + BLOCK / 2)
        ]
        if self.bonus:
            avoid_positions.append(
                (self.bonus.pos[0] + BLOCK / 2, self.bonus.pos[1] + BLOCK / 2)
            )
        occupied = list(self.enemies)
        occupied.extend(
            marker.payload for marker in self.spawn_indicators if marker.payload
        )
        enemy = spawn_enemy_random(
            occupied,
            avoid_positions=avoid_positions,
            min_distance_from_avoid=BLOCK * 5,
            min_spacing=BLOCK * 3.5,
            speed_range=(speed_min, speed_max),
            color=pygame.Color(*SPAWN_INDICATOR_COLOR),
            warmup=0.55,
            on_spawn=None,
            add_to_list=False,
        )
        if not enemy:
            return False
        self._register_spawn_indicator(
            (enemy.x, enemy.y),
            enemy.color,
            payload=enemy,
        )
        return True

    def _spawn_enemy_explosions(self, destroyed: list[RippleEnemy]) -> None:
        if not destroyed:
            return
        for enemy in destroyed:
            origin = (
                int(enemy.x) - BLOCK // 2,
                int(enemy.y) - BLOCK // 2,
            )
            spawn_particles(self.particles, origin, [enemy.color], count=18)
        self.audio.play("enemy_destroy")

    # --- Bonus fruit helpers ------------------------------------------

    def _handle_bonus_pickup(self) -> None:
        if not self.bonus:
            return
        bonus_pos = self.bonus.pos
        self.bonus = None

        self.score += BONUS_POINTS
        self._update_speed()
        self.audio.play("bonus")
        spawn_particles(
            self.particles,
            bonus_pos,
            [
                self.fruit_color,
                PALETTE["bonus"],
                PALETTE["snake"][0],
                PALETTE["snake"][2],
            ],
        )

        bonus_color = pygame.Color(PALETTE["bonus"])
        self._emit_ripple(
            bonus_pos,
            bonus_color,
            duration=1.6,
            radius_cells=GRID_CELLS * 0.9,
            band_width=1.4,
            intensity=0.9,
        )
        self._emit_ripple(
            bonus_pos,
            pygame.Color(240, 250, 255),
            duration=1.0,
            radius_cells=GRID_CELLS * 0.6,
            band_width=0.9,
            intensity=0.5,
        )
        start_snake_wash(self.snake_washes, bonus_color, speed=9.5, width=8.0)
        self._start_shake(intensity=6.0, duration=0.35)
        self._maybe_spawn_bonus(chance=0.35)

    def _reachable_bonus_spots(self) -> list[tuple[int, int]]:
        """Enumerate grid cells that the snake can reach before the timer ends."""
        max_steps = max(1, int(BONUS_DURATION / self.move_interval) - 1)
        head_x, head_y = self.head
        spots: list[tuple[int, int]] = []
        for x in range(0, WINDOW_SIZE, BLOCK):
            for y in range(0, WINDOW_SIZE, BLOCK):
                if [x, y] in self.snake_blocks or (x, y) == self.fruit_pos:
                    continue
                dist = (abs(x - head_x) + abs(y - head_y)) // BLOCK
                if dist <= max_steps:
                    spots.append((x, y))
        return spots

    def _maybe_spawn_bonus(self, chance: float = BONUS_CHANCE) -> None:
        """Occasionally drop a bonus fruit within reach of the head."""
        if self.bonus or random.random() > chance:
            return
        options = self._reachable_bonus_spots()
        if not options:
            return
        self.bonus = BonusFruit(pos=random.choice(options), timer=BONUS_DURATION)

    def _tick_bonus(self, dt: float) -> None:
        """Fade bonus timer while the game is running."""
        if not self.bonus or dt <= 0:
            return
        self.bonus.timer -= dt
        if self.bonus.timer <= 0:
            self.bonus = None

    # --- Effects update ------------------------------------------------

    def _update_effects(self, dt: float) -> None:
        """Advance simple VFX timers; accepts zero dt while paused."""
        if dt > 0:
            if self.shake_timer > 0.0:
                self.shake_timer = max(0.0, self.shake_timer - dt)
                if self.shake_timer <= 0.0:
                    self.shake_intensity = 0.0
                    self.shake_duration = 0.0
            if self.spawn_indicators:
                self._update_spawn_indicators(dt)

        if dt <= 0:
            return

        for blob in self.trail:
            blob["life"] = max(0.0, blob["life"] - dt)
        self.trail = [blob for blob in self.trail if blob["life"] > 0]

        for particle in self.particles:
            particle["x"] += particle["vx"] * dt
            particle["y"] += particle["vy"] * dt
            particle["life"] = max(0.0, particle["life"] - dt)
        self.particles = [p for p in self.particles if p["life"] > 0]

        for ripple in self.grid_ripples:
            ripple.timer = max(0.0, ripple.timer - dt)
        self.grid_ripples = [rip for rip in self.grid_ripples if rip.timer > 0]

        head_center = self._enemy_chase_target(dt)
        self.enemies = update_enemy_positions(self.enemies, head_center, dt)
        self.enemies, destroyed_enemies = cull_enemies_hit_by_ripples(
            self.enemies, self.grid_ripples
        )
        if destroyed_enemies:
            self._spawn_enemy_explosions(destroyed_enemies)
        if self.state == "running" and enemies_hit_snake(
            self.enemies, self.snake_blocks
        ):
            self.game_over()
            return
        self._tick_enemy_spawn_timer(dt)

        max_index = len(self.snake_blocks)
        for wash in self.snake_washes:
            wash.progress += wash.speed * dt
        self.snake_washes = [
            wash
            for wash in self.snake_washes
            if (wash.progress - wash.width) <= max_index
        ]
        self._tick_bonus(dt)

    def _enemy_chase_target(self, dt: float) -> tuple[float, float]:
        if self.state == "running":
            return (self.head[0] + BLOCK / 2, self.head[1] + BLOCK / 2)
        center = WINDOW_SIZE / 2
        radius = WINDOW_SIZE * 0.32
        phase_speed = 0.55
        self._enemy_idle_phase = (self._enemy_idle_phase + dt * phase_speed) % math.tau
        wobble = math.sin(self._enemy_idle_phase * 1.7) * (WINDOW_SIZE * 0.08)
        target_x = center + math.cos(self._enemy_idle_phase) * radius
        target_y = center + math.sin(self._enemy_idle_phase * 0.85) * radius + wobble
        return target_x, target_y

    def _draw_spawn_indicators(self) -> None:
        if not self.spawn_indicators:
            return
        for marker in self.spawn_indicators:
            duration = marker.duration or 0.001
            ratio = marker.time / duration if duration else 0.0
            ratio = max(0.0, min(1.0, ratio))
            progress = 1.0 - ratio
            eased = progress**0.8
            center = (int(marker.x), int(marker.y))
            base_color = pygame.Color(*marker.color)

            # Soft neon halo hugging the grid square
            halo_size = int(BLOCK * 2.4 + eased * 8)
            halo = pygame.Surface((halo_size, halo_size), pygame.SRCALPHA)
            halo_color = pygame.Color(
                base_color.r,
                base_color.g,
                base_color.b,
                int(45 + 140 * eased),
            )
            pygame.draw.rect(
                halo,
                halo_color,
                halo.get_rect(),
                border_radius=max(6, halo_size // 3),
            )
            self.scene.blit(halo, halo.get_rect(center=center))

            tile_size = BLOCK + int(6 + eased * 5)
            tile_rect = pygame.Rect(0, 0, tile_size, tile_size)
            tile_rect.center = center
            body_color = pygame.Color(
                min(255, int(base_color.r * 1.08 + 12)),
                min(255, int(base_color.g * 0.9 + 15)),
                min(255, int(base_color.b * 1.02 + 10)),
            )
            pygame.draw.rect(self.scene, body_color, tile_rect, border_radius=6)

            inset_rect = tile_rect.inflate(-6, -6)
            if inset_rect.width > 0 and inset_rect.height > 0:
                inset_color = pygame.Color(
                    max(0, base_color.r - 35),
                    max(0, base_color.g - 15),
                    max(0, base_color.b - 15),
                )
                pygame.draw.rect(self.scene, inset_color, inset_rect, border_radius=4)

                charge_rect = inset_rect.inflate(-6, -6)
                if charge_rect.width > 0 and charge_rect.height > 0:
                    fill_height = max(3, int(charge_rect.height * eased))
                    fill_rect = pygame.Rect(
                        charge_rect.left,
                        charge_rect.bottom - fill_height,
                        charge_rect.width,
                        fill_height,
                    )
                    fill_color = pygame.Color(255, 255, 255, int(110 + 100 * eased))
                    pygame.draw.rect(self.scene, fill_color, fill_rect, border_radius=3)

                highlight_height = max(2, int(inset_rect.height * 0.25))
                highlight_rect = pygame.Rect(
                    inset_rect.left + 2,
                    inset_rect.top + 2,
                    inset_rect.width - 4,
                    highlight_height,
                )
                pygame.draw.rect(
                    self.scene,
                    pygame.Color(255, 255, 255, 60),
                    highlight_rect,
                    border_radius=3,
                )

            # A dotted perimeter made of tiny neon squares so the timer feels "pixel" based
            pip_segments = 12
            ring_radius = tile_rect.width // 2 + BLOCK // 2
            pip_size = max(4, BLOCK // 3)
            pip_progress = eased * pip_segments
            for idx in range(pip_segments):
                portion = min(1.0, max(0.0, pip_progress - idx))
                if portion <= 0.0:
                    continue
                angle = math.tau * (idx / pip_segments)
                px = int(center[0] + math.cos(angle) * ring_radius)
                py = int(center[1] + math.sin(angle) * ring_radius)
                pip_rect = pygame.Rect(0, 0, pip_size, pip_size)
                pip_rect.center = (px, py)
                pip_color = pygame.Color(
                    base_color.r,
                    base_color.g,
                    base_color.b,
                    int(70 + 160 * portion),
                )
                pygame.draw.rect(self.scene, pip_color, pip_rect, border_radius=2)
                inner_rect = pip_rect.inflate(-2, -2)
                if inner_rect.width > 0 and inner_rect.height > 0:
                    pygame.draw.rect(
                        self.scene,
                        pygame.Color(255, 255, 255, int(90 * portion)),
                        inner_rect,
                        border_radius=2,
                    )

            pulse_size = max(4, int(6 + 6 * (1.0 - eased)))
            pulse_rect = pygame.Rect(0, 0, pulse_size, pulse_size)
            pulse_rect.center = center
            pulse_color = pygame.Color(255, 255, 255, int(80 + 100 * (1.0 - eased)))
            pygame.draw.rect(self.scene, pulse_color, pulse_rect, border_radius=2)

    def _draw_trail(self) -> None:
        glow = pygame.Surface((BLOCK * 2, BLOCK * 2), pygame.SRCALPHA)
        for blob in self.trail:
            alpha = int(140 * (blob["life"] / TRAIL_LIFE))
            if alpha <= 0:
                continue
            glow.fill((0, 0, 0, 0))
            size = BLOCK + int((1 - blob["life"] / TRAIL_LIFE) * 8)
            rect = pygame.Rect(0, 0, size, size)
            rect.center = (BLOCK, BLOCK)
            color = (0, 255, 255, alpha)
            pygame.draw.rect(glow, color, rect, border_radius=6)
            pos = (blob["x"] - BLOCK / 2, blob["y"] - BLOCK / 2)
            self.scene.blit(glow, pos)

    def _segment_color(self, idx: int, base_color: pygame.Color) -> pygame.Color:
        if not self.snake_washes:
            return base_color
        r, g, b = float(base_color.r), float(base_color.g), float(base_color.b)
        for wash in self.snake_washes:
            distance = idx - wash.progress
            if abs(distance) > wash.width:
                continue
            weight = 1.0 - abs(distance) / wash.width
            r += (wash.color[0] - r) * weight
            g += (wash.color[1] - g) * weight
            b += (wash.color[2] - b) * weight
        return pygame.Color(int(r), int(g), int(b))

    def _apply_glow(self, color: pygame.Color, strength: float) -> pygame.Color:
        """Blend the given color toward white based on strength (0..1)."""
        clamped = max(0.0, min(1.0, strength))
        return pygame.Color(
            min(255, int(color.r + (255 - color.r) * clamped)),
            min(255, int(color.g + (255 - color.g) * clamped)),
            min(255, int(color.b + (255 - color.b) * clamped)),
        )

    def _draw_bonus_aura(self, core_rect: pygame.Rect, ratio: float) -> None:
        """Colore quadrados ao redor do bônus, encolhendo conforme o tempo acaba."""
        if ratio <= 0.0:
            return

        center_cell_x = core_rect.centerx // BLOCK
        center_cell_y = core_rect.centery // BLOCK

        max_radius_cells = 5.0
        radius = max_radius_cells * ratio

        min_gx = max(0, int(center_cell_x - radius - 1))
        max_gx = min(GRID_CELLS - 1, int(center_cell_x + radius + 1))
        min_gy = max(0, int(center_cell_y - radius - 1))
        max_gy = min(GRID_CELLS - 1, int(center_cell_y + radius + 1))

        overlay = pygame.Surface((WINDOW_SIZE, WINDOW_SIZE), pygame.SRCALPHA)

        gold = PALETTE["bonus"]
        fruit_col = getattr(self, "fruit_color", PALETTE["fruit"])

        for gx in range(min_gx, max_gx + 1):
            for gy in range(min_gy, max_gy + 1):
                dx = gx - center_cell_x
                dy = gy - center_cell_y
                dist = (dx * dx + dy * dy) ** 0.5
                if dist > radius:
                    continue

                t = 0.0 if radius <= 0 else dist / radius
                t = max(0.0, min(1.0, t))

                r = int(gold.r * (1.0 - t) + fruit_col.r * t)
                g = int(gold.g * (1.0 - t) + fruit_col.g * t)
                b = int(gold.b * (1.0 - t) + fruit_col.b * t)

                alpha = int(130 * (1.0 - t) * ratio)
                if alpha <= 0:
                    continue

                tint = (r, g, b, alpha)
                cell_rect = pygame.Rect(gx * BLOCK, gy * BLOCK, BLOCK, BLOCK)
                overlay.fill(tint, cell_rect)

        self.scene.blit(overlay, (0, 0))

    def _draw_bonus(self) -> None:
        """Renderiza bônus dourado com barra, anel e aura."""
        if not self.bonus:
            return

        core_rect = self._draw_fruit_sprite(
            self.bonus.pos,
            PALETTE["bonus"],
            phase_shift=2,
        )
        ratio = max(0.0, min(1.0, self.bonus.timer / BONUS_DURATION))

        squares = 6
        square_size = max(3, BLOCK // 3)
        gap = 2
        stack_height = squares * square_size + (squares - 1) * gap
        top = core_rect.centery - stack_height // 2
        timer_x = core_rect.right + 4
        if timer_x + square_size > WINDOW_SIZE:
            timer_x = core_rect.left - 4 - square_size

        active = min(squares, max(0, int(ratio * squares + 0.999)))
        threshold = squares - active
        active_color = pygame.Color(PALETTE["bonus"])
        inactive_color = pygame.Color(35, 35, 40)

        for idx in range(squares):
            square_rect = pygame.Rect(
                timer_x,
                top + idx * (square_size + gap),
                square_size,
                square_size,
            )
            color = active_color if idx >= threshold else inactive_color
            pygame.draw.rect(self.scene, color, square_rect, border_radius=1)

        cx, cy = core_rect.center
        max_radius = core_rect.width // 2 + 10
        ring_radius = int(max(0, max_radius * ratio))
        if ring_radius > 0:
            ring_color = pygame.Color(PALETTE["bonus"])
            ring_color.a = 200
            pygame.draw.circle(self.scene, ring_color, (cx, cy), ring_radius, width=2)

        self._draw_bonus_aura(core_rect, ratio)

    def _draw_head_highlight(self, rect: pygame.Rect, color: pygame.Color) -> None:
        """Add a subtle beam oriented toward the current movement direction."""
        direction = DIRECTIONS.get(self.direction)
        if not direction:
            return

        beam = pygame.Color(color)
        beam.r = min(255, beam.r + 70)
        beam.g = min(255, beam.g + 70)
        beam.b = min(255, beam.b + 70)
        beam.a = 255

        thickness = max(2, BLOCK // 5)
        highlight = rect.copy()

        if direction[0] == 1:
            highlight.width = thickness
            highlight.left = rect.right - thickness
        elif direction[0] == -1:
            highlight.width = thickness
            highlight.left = rect.left
        elif direction[1] == 1:
            highlight.height = thickness
            highlight.top = rect.bottom - thickness
        elif direction[1] == -1:
            highlight.height = thickness
            highlight.top = rect.top
        else:
            return

        pygame.draw.rect(self.scene, beam, highlight, border_radius=2)

    def _draw_overlay(self, lines: list[str]) -> None:
        overlay = pygame.Surface((WINDOW_SIZE, WINDOW_SIZE), pygame.SRCALPHA)
        overlay.fill((5, 5, 15, 140))
        for idx, text in enumerate(lines):
            surf = self.font.render(text, True, PALETTE["text"])
            rect = surf.get_rect()
            rect.center = (WINDOW_SIZE // 2, WINDOW_SIZE // 2 + idx * (FONT_SIZE + 8))
            overlay.blit(surf, rect)
        self.scene.blit(overlay, (0, 0))

    # --- HUD: score ----------------------------------------------------

    def show_score(self) -> None:
        """Renderize apenas o placar atual no HUD."""
        score_text = self.font.render(f"SCORE {self.score:04}", True, PALETTE["text"])

        width = score_text.get_width()
        height = score_text.get_height() + 8

        hud_rect = pygame.Rect(10, 10, width + 16, height + 10)
        hud = pygame.Surface(hud_rect.size, pygame.SRCALPHA)
        hud.fill(PALETTE["hud"])

        fruit_rect = pygame.Rect(self.fruit_pos[0], self.fruit_pos[1], BLOCK, BLOCK)
        head_rect = pygame.Rect(self.head[0], self.head[1], BLOCK, BLOCK)
        overlap = hud_rect.colliderect(fruit_rect) or hud_rect.colliderect(head_rect)

        if overlap:
            hud.set_alpha(70)
        else:
            hud.set_alpha(255)

        hud.blit(score_text, (8, 5))

        self.scene.blit(hud, hud_rect.topleft)

    # --- Fruit spawn ---------------------------------------------------

    def spawn_fruit(self) -> None:
        """Place a fruit at a random non-snake grid position with a random color."""
        self.fruit_pos = self._random_fruit_pos()
        self.fruit_color = random.choice(FRUIT_COLORS)

    def _random_fruit_pos(self) -> tuple[int, int]:
        """Return a random fruit position that does not collide with the snake."""
        max_cells = WINDOW_SIZE // BLOCK
        corner_cells = {
            (0, 0),
            (0, WINDOW_SIZE - BLOCK),
            (WINDOW_SIZE - BLOCK, 0),
            (WINDOW_SIZE - BLOCK, WINDOW_SIZE - BLOCK),
        }
        while True:
            pos = (
                random.randrange(0, max_cells) * BLOCK,
                random.randrange(0, max_cells) * BLOCK,
            )
            if pos in corner_cells:
                continue
            if list(pos) not in self.snake_blocks:
                return pos

    # --- Input / eventos -----------------------------------------------

    def handle_events(self) -> bool:
        """Handle window/keyboard events and translate them into intents."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE and self.state != "game_over":
                    self._toggle_pause()
                    continue

                if event.key in (pygame.K_f, pygame.K_F11):
                    self.fullscreen = not self.fullscreen
                    self._apply_display_mode()
                    continue

                if self.state == "game_over":
                    if event.key == pygame.K_r:
                        self._reset_game_state()
                    elif event.key == pygame.K_q:
                        return False
                    continue

                # Toggles
                if event.key == pygame.K_c:
                    self.scanlines_enabled = not self.scanlines_enabled
                    continue

                if event.key == pygame.K_v:
                    self.shake_enabled = not self.shake_enabled
                    if not self.shake_enabled:
                        self.shake_timer = 0.0
                        self.shake_intensity = 0.0
                        self.shake_duration = 0.0
                    continue

                if event.key == pygame.K_p:
                    self.performance_mode = not self.performance_mode
                    if self.performance_mode:
                        self.scanlines_enabled = False
                        self.particles_enabled = False
                        self.trail_enabled = False
                        self.ripples_enabled = False
                        self.shake_enabled = False
                        self.shake_timer = 0.0
                        self.shake_intensity = 0.0
                        self.shake_duration = 0.0
                    else:
                        self.scanlines_enabled = True
                        self.particles_enabled = True
                        self.trail_enabled = True
                        self.ripples_enabled = True
                        self.shake_enabled = True
                    continue

                if self.state == "paused":
                    continue

                new_dir = KEY_TO_DIRECTION.get(event.key)
                if new_dir and new_dir != OPPOSITE[self.direction]:
                    if new_dir != self.direction:
                        self.audio.play("turn")
                    self.pending_direction = new_dir
        return True

    # --- Logic step ----------------------------------------------------

    def step(self) -> None:
        """Advance the game state by exactly one grid cell."""
        self.direction = self.pending_direction

        dx, dy = DIRECTIONS[self.direction]
        new_head = [
            (self.head[0] + dx * BLOCK) % WINDOW_SIZE,
            (self.head[1] + dy * BLOCK) % WINDOW_SIZE,
        ]

        if new_head in self.snake_blocks:
            self.game_over()
            return
        self.head = new_head
        self.snake_blocks.insert(0, self.head.copy())
        self._leave_trail((self.head[0], self.head[1]))
        head_color = self._segment_color(0, PALETTE["snake"][0])
        spawn_head_sparks(
            self.particles,
            (self.head[0], self.head[1]),
            DIRECTIONS[self.direction],
            head_color,
        )

        if tuple(self.head) == self.fruit_pos:
            self.score += 10
            self._update_speed()
            self.audio.play("fruit")
            spawn_particles(
                self.particles,
                self.fruit_pos,
                [
                    self.fruit_color,
                    PALETTE["bonus"],
                    PALETTE["snake"][0],
                    PALETTE["snake"][2],
                ],
            )
            fruit_color = pygame.Color(self.fruit_color)
            self._emit_ripple(
                self.fruit_pos,
                fruit_color,
                duration=1.2,
                radius_cells=GRID_CELLS * 0.55,
                band_width=0.8,
                intensity=0.55,
            )
            start_snake_wash(self.snake_washes, fruit_color, speed=12.5, width=5.0)
            self._start_shake(intensity=4.0, duration=0.25)
            self.spawn_fruit()
            self._maybe_spawn_bonus()
            self.fruits_eaten += 1
            if self.fruits_eaten == 1:
                self._start_enemy_spawns()
        elif self.bonus and tuple(self.head) == self.bonus.pos:
            self._handle_bonus_pickup()
        if self.snake_blocks:
            self.snake_blocks.pop()

    # --- Background & post FX -----------------------------------------

    def _build_background(self) -> pygame.Surface:
        """Create a gradient grid background once to keep draw() light."""
        surface = pygame.Surface((WINDOW_SIZE, WINDOW_SIZE))
        for y in range(WINDOW_SIZE):
            t = y / WINDOW_SIZE
            r = int(
                PALETTE["bg_top"].r + (PALETTE["bg_bottom"].r - PALETTE["bg_top"].r) * t
            )
            g = int(
                PALETTE["bg_top"].g + (PALETTE["bg_bottom"].g - PALETTE["bg_top"].g) * t
            )
            b = int(
                PALETTE["bg_top"].b + (PALETTE["bg_bottom"].b - PALETTE["bg_top"].b) * t
            )
            pygame.draw.line(surface, (r, g, b), (0, y), (WINDOW_SIZE, y))
        for i in range(0, WINDOW_SIZE, BLOCK):
            pygame.draw.line(surface, PALETTE["grid"], (i, 0), (i, WINDOW_SIZE), 1)
            pygame.draw.line(surface, PALETTE["grid"], (0, i), (WINDOW_SIZE, i), 1)
        return surface

    def _build_scanlines(self) -> pygame.Surface:
        """Build a subtle CRT-style scanline overlay."""
        overlay = pygame.Surface((WINDOW_SIZE, WINDOW_SIZE), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 0))
        for y in range(0, WINDOW_SIZE, 2):
            pygame.draw.line(overlay, (0, 0, 0, 60), (0, y), (WINDOW_SIZE, y))
        return overlay

    # --- Draw ----------------------------------------------------------

    def draw(self) -> None:
        """Render the current frame (background, fruit, snake, score, HUD)."""
        self.scene.blit(self.background, (0, 0))

        if self.ripples_enabled:
            draw_ripples(self.scene, self.grid_ripples)
        self._draw_fruit_sprite(self.fruit_pos, self.fruit_color)
        self._draw_bonus()
        self._draw_spawn_indicators()
        self._draw_trail()
        if self.enemies:
            draw_enemies(self.scene, self.enemies)
        if self.particles_enabled:
            draw_particles(self.scene, self.particles)

        wave_time = pygame.time.get_ticks() * 0.002
        head_pulse = (math.sin(wave_time * 1.6) + 1.0) * 0.5

        for idx, pos in enumerate(self.snake_blocks):
            base_color = PALETTE["snake"][idx % len(PALETTE["snake"])]
            color = self._segment_color(idx, base_color)
            glow_strength = 0.08 * (0.5 + 0.5 * math.sin(wave_time + idx * 0.45))
            color = self._apply_glow(color, glow_strength)

            rect = pygame.Rect(pos[0], pos[1], BLOCK, BLOCK)
            if idx == 0:
                size_offset = int(round(head_pulse * 2))
                if size_offset:
                    rect = rect.inflate(size_offset, size_offset)

            pygame.draw.rect(
                self.scene,
                color,
                rect,
                border_radius=4,
            )

        self.show_score()

        if self.state == "paused":
            self._draw_overlay(["Paused", "Press SPACE to resume"])
        elif self.state == "game_over":
            self._draw_overlay(
                [
                    "Game Over",
                    f"Score: {self.score}",
                    f"Best:  {self.high_score}",
                    "R to restart / Q to quit",
                ]
            )

        if self.scanlines_enabled:
            self.scene.blit(self.scanlines, (0, 0))

        ox, oy = self._current_shake_offset()
        self.window.fill((0, 0, 0))
        self.window.blit(self.scene, (ox, oy))

    # --- Game over & main loop ----------------------------------------

    def game_over(self) -> None:
        """Freeze play, show overlay, and register highscore."""
        if self.state == "game_over":
            return
        self.state = "game_over"
        if self.score > self.high_score:
            self.high_score = self.score
            self._save_high_score()
        self.audio.play("over")
        self._start_shake(intensity=8.0, duration=0.6)

    def start(self) -> None:
        """Run the main loop: handle events, step at a fixed rate, then render."""
        pygame.display.set_caption("Neon Snake")
        clock = pygame.time.Clock()
        running = True

        while running:
            dt = clock.tick(FPS) / 1000.0

            running = self.handle_events()

            effect_dt = dt
            if self.state == "running":
                self._move_accumulator += dt
                while self._move_accumulator >= self.move_interval:
                    self.step()
                    self._move_accumulator -= self.move_interval
            elif self.state == "paused":
                effect_dt = 0.0

            self._update_effects(effect_dt)

            self.draw()
            pygame.display.update()

        pygame.quit()


if __name__ == "__main__":
    game = NeonSnake()
    game.start()
