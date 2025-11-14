"""Entry point for the Neon Snake game."""

from __future__ import annotations

from neon_snake.game import NeonSnake


def main() -> None:
    game = NeonSnake()
    game.start()


if __name__ == "__main__":
    main()
