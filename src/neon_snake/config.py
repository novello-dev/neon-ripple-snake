"""Centralized configuration and palette definitions for Neon Snake."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pygame

BASE_DIR = Path(__file__).resolve().parent


def _default_data_dir() -> Path:
    """Return a platform-appropriate user data directory for saves/logs."""

    if sys.platform.startswith("win"):
        base = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "neon-snake"


DATA_DIR = Path(os.getenv("NEON_SNAKE_DATA_DIR") or _default_data_dir())
HIGHSCORE_FILE = Path(
    os.getenv("NEON_SNAKE_HIGHSCORE_FILE") or DATA_DIR / "highscore.txt"
)

WINDOW_SIZE: int = 480  # 480 / 16 => 30 cells
BLOCK: int = 16  # larger snake segments for tighter grid
FONT_NAME: str = "consolas"
FONT_SIZE: int = 24

FPS: int = 180
MOVES_PER_SECOND: int = 10
SPEED_STEP: int = 60
MAX_MOVES_PER_SECOND: int = 16

TRAIL_LIFE: float = 0.35
PARTICLE_LIFE: float = 0.45
BONUS_DURATION: float = 3.5
BONUS_POINTS: int = 35
BONUS_CHANCE: float = 0.45
GRID_CELLS: int = WINDOW_SIZE // BLOCK
SNAKE_WASH_SPEED: float = 11.0
SNAKE_WASH_WIDTH: float = 6.0
SPAWNER_POSITIONS: tuple[tuple[int, int], ...] = (
    (BLOCK * 2, BLOCK * 2),
    (WINDOW_SIZE - BLOCK * 3, BLOCK * 2),
    (WINDOW_SIZE // 2 - BLOCK // 2, WINDOW_SIZE - BLOCK * 3),
)

PARTICLE_DIRECTIONS = [
    (1.0, 0.0),
    (-1.0, 0.0),
    (0.0, 1.0),
    (0.0, -1.0),
    (0.7, 0.7),
    (-0.7, 0.7),
    (0.7, -0.7),
    (-0.7, -0.7),
]

DIRECTIONS: dict[str, tuple[int, int]] = {
    "UP": (0, -1),
    "DOWN": (0, 1),
    "LEFT": (-1, 0),
    "RIGHT": (1, 0),
}
OPPOSITE: dict[str, str] = {
    "UP": "DOWN",
    "DOWN": "UP",
    "LEFT": "RIGHT",
    "RIGHT": "LEFT",
}
KEY_TO_DIRECTION = {
    pygame.K_UP: "UP",
    pygame.K_w: "UP",
    pygame.K_DOWN: "DOWN",
    pygame.K_s: "DOWN",
    pygame.K_LEFT: "LEFT",
    pygame.K_a: "LEFT",
    pygame.K_RIGHT: "RIGHT",
    pygame.K_d: "RIGHT",
}

PALETTE = {
    "bg_top": pygame.Color(7, 10, 18),
    "bg_bottom": pygame.Color(2, 24, 43),
    "grid": pygame.Color(10, 40, 60),
    "fruit": pygame.Color(255, 84, 138),
    "fruit_glow": pygame.Color(255, 84, 138, 90),
    "text": pygame.Color(216, 239, 255),
    "hud": pygame.Color(10, 10, 10, 150),
    "bonus": pygame.Color(255, 208, 0),
    "snake": [
        pygame.Color(57, 255, 233),
        pygame.Color(127, 255, 212),
        pygame.Color(0, 230, 255),
        pygame.Color(178, 255, 255),
    ],
}

FRUIT_COLORS = [
    pygame.Color(255, 84, 138),
    pygame.Color(0, 230, 255),
    pygame.Color(141, 255, 112),
    pygame.Color(178, 127, 255),
]
