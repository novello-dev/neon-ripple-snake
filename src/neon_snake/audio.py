"""Lightweight audio utilities for Neon Snake — reactive chiptune edition."""

from __future__ import annotations

import math
import random
from array import array
from dataclasses import dataclass
from typing import Dict, List, Tuple

import pygame

# ===========================
#  Synth Configuration
# ===========================


@dataclass(frozen=True)
class SynthPatch:
    freq: float
    duration_ms: int
    harmonics: Tuple[Tuple[float, float], ...] = ((1.0, 1.0),)
    sweep: float = 0.0
    noise: float = 0.0
    attack: float = 0.02
    decay: float = 0.15
    release: float = 0.2
    sustain_level: float = 0.6
    vibrato_rate: float = 0.0
    vibrato_depth: float = 0.0
    volume: float = 0.5
    waveform: str = "square"  # "sine", "square", "triangle"
    bitcrush_levels: int = 0
    fade_ms: int = 18
    mix_volume: float = 0.4
    pulse_width: float = 0.5


# ===========================
#   Audio Engine
# ===========================


class AudioEngine:
    """Encapsulates mixer init plus procedural chiptune-style tone playback."""

    def __init__(self) -> None:
        self.enabled = False
        self.sounds: Dict[str, pygame.mixer.Sound] = {}
        self.sample_rate: int = 32000
        self.sound_fades: Dict[str, int] = {}
        self.mix_levels: Dict[str, float] = {}
        self.channel_count: int = 24
        self._channels: List[pygame.mixer.Channel] = []
        self._reserved_channels: Dict[str, pygame.mixer.Channel] = {}

        self.master_sfx_volume: float = 0.45
        self.music_volume: float = 0.24
        self.music: pygame.mixer.Sound | None = None
        self._music_channel: pygame.mixer.Channel | None = None
        self._last_play: Dict[str, int] = {}
        self._sound_gate_ms: int = 60
        self._mix_events: List[Tuple[int, float]] = []
        self._limiter_window_ms: int = 220
        self._limiter_ceiling: float = 1.32

        self._init_audio()

    def _init_audio(self) -> None:
        """Initialise pygame.mixer and synthesise the tones we need."""

        try:
            pygame.mixer.init(frequency=self.sample_rate, size=-16, channels=1)
        except pygame.error:
            self.enabled = False
            self.sounds.clear()
            return

        pygame.mixer.set_num_channels(self.channel_count)
        self.enabled = True
        mixer_info = pygame.mixer.get_init()
        if mixer_info:
            self.sample_rate = mixer_info[0]
        self._channels = [pygame.mixer.Channel(i) for i in range(self.channel_count)]
        self._reserved_channels = {}
        if self._channels:
            # Keep the last channel exclusive to the ripple effect
            self._reserved_channels["ripple"] = self._channels[-1]

        # ---------------------------
        #  Game Boy inspired patches
        # ---------------------------
        patches: Dict[str, SynthPatch] = {
            "turn": SynthPatch(
                freq=340,
                duration_ms=90,
                harmonics=((1.0, 1.0), (2.0, 0.2)),
                sweep=-180,
                attack=0.001,
                decay=0.05,
                release=0.05,
                sustain_level=0.16,
                vibrato_rate=5.5,
                vibrato_depth=3.0,
                noise=0.04,
                volume=0.75,
                waveform="square",
                bitcrush_levels=5,
                fade_ms=6,
                mix_volume=0.28,
                pulse_width=0.24,
            ),
            "fruit": SynthPatch(
                freq=380,
                duration_ms=140,
                harmonics=((1.0, 1.0), (2.0, 0.3), (3.0, 0.15)),
                sweep=120,
                attack=0.001,
                decay=0.09,
                release=0.09,
                sustain_level=0.25,
                vibrato_rate=3.5,
                vibrato_depth=2.0,
                noise=0.06,
                volume=0.82,
                waveform="square",
                bitcrush_levels=4,
                fade_ms=9,
                mix_volume=0.34,
                pulse_width=0.35,
            ),
            "bonus": SynthPatch(
                freq=300,
                duration_ms=420,
                harmonics=((0.5, 0.4), (1.0, 1.0), (1.5, 0.45)),
                sweep=140,
                attack=0.003,
                decay=0.2,
                release=0.4,
                sustain_level=0.48,
                vibrato_rate=3.0,
                vibrato_depth=4.5,
                noise=0.15,
                volume=0.92,
                waveform="square",
                bitcrush_levels=4,
                fade_ms=18,
                mix_volume=0.31,
                pulse_width=0.4,
            ),
            "spawn_warning": SynthPatch(
                freq=260,
                duration_ms=160,
                harmonics=((1.0, 1.0),),
                sweep=-40,
                attack=0.001,
                decay=0.08,
                release=0.08,
                sustain_level=0.2,
                vibrato_rate=2.2,
                vibrato_depth=2.5,
                noise=0.15,
                volume=0.7,
                waveform="square",
                bitcrush_levels=4,
                fade_ms=6,
                mix_volume=0.3,
                pulse_width=0.28,
            ),
            "enemy_spawn": SynthPatch(
                freq=210,
                duration_ms=190,
                harmonics=((0.5, 0.7), (1.0, 1.0)),
                sweep=90,
                attack=0.001,
                decay=0.12,
                release=0.15,
                sustain_level=0.22,
                vibrato_rate=2.0,
                vibrato_depth=2.0,
                noise=0.3,
                volume=0.85,
                waveform="square",
                bitcrush_levels=3,
                fade_ms=10,
                mix_volume=0.32,
                pulse_width=0.3,
            ),
            "over": SynthPatch(
                freq=150,
                duration_ms=520,
                harmonics=((0.5, 1.0), (1.0, 0.6)),
                sweep=-320,
                noise=0.45,
                attack=0.004,
                decay=0.28,
                release=0.55,
                sustain_level=0.42,
                vibrato_rate=2.2,
                vibrato_depth=3.5,
                volume=0.7,
                waveform="square",
                bitcrush_levels=4,
                fade_ms=32,
                mix_volume=0.32,
            ),
            "ripple": SynthPatch(
                freq=190,
                duration_ms=360,
                harmonics=((0.5, 0.7), (1.0, 1.0)),
                sweep=-80,
                attack=0.006,
                decay=0.2,
                release=0.35,
                sustain_level=0.48,
                vibrato_rate=2.4,
                vibrato_depth=3.5,
                noise=0.15,
                volume=0.8,
                waveform="square",
                bitcrush_levels=5,
                fade_ms=22,
                mix_volume=0.3,
                pulse_width=0.46,
            ),
            "enemy_destroy": SynthPatch(
                freq=170,
                duration_ms=200,
                harmonics=((0.5, 0.9), (1.0, 0.7)),
                sweep=110,
                noise=0.6,
                attack=0.0,
                decay=0.12,
                release=0.2,
                sustain_level=0.32,
                volume=0.8,
                waveform="square",
                bitcrush_levels=3,
                fade_ms=12,
                mix_volume=0.29,
            ),
        }

        self.sounds = {}
        for name, patch in patches.items():
            self.sounds[name] = self._render_patch(patch)
            self.sound_fades[name] = patch.fade_ms
            self.mix_levels[name] = patch.mix_volume

    # ===========================
    #   Synthesizer Core
    # ===========================

    def _render_patch(self, patch: SynthPatch) -> pygame.mixer.Sound:
        """Generate a chiptune-like tone with ADSR envelope and coarse bitcrush."""

        sample_rate = self.sample_rate
        sample_count = max(1, int(sample_rate * patch.duration_ms / 1000))
        attack = int(sample_count * patch.attack)
        decay = int(sample_count * patch.decay)
        release = int(sample_count * patch.release)
        sustain_start = min(sample_count, attack + decay)
        sustain_end = max(sustain_start, sample_count - release)

        two_pi = 2.0 * math.pi
        samples = [0.0] * sample_count

        for idx in range(sample_count):
            t = idx / sample_rate
            progress = idx / sample_count if sample_count else 0.0
            freq = patch.freq + patch.sweep * progress

            # vibrato
            if patch.vibrato_rate > 0.0 and patch.vibrato_depth != 0.0:
                freq += math.sin(two_pi * patch.vibrato_rate * t) * patch.vibrato_depth

            sample_val = 0.0

            # Build the composite waveform from configured partials
            for mult, weight in patch.harmonics:
                voice_freq = freq * mult
                cycle_pos = (voice_freq * t) % 1.0
                if patch.waveform == "square":
                    pulse = max(0.05, min(0.95, patch.pulse_width))
                    wave = 1.0 if cycle_pos < pulse else -1.0
                elif patch.waveform == "triangle":
                    wave = 4.0 * abs(cycle_pos - 0.5) - 1.0
                else:
                    wave = math.sin(two_pi * voice_freq * t)

                sample_val += weight * wave

            if patch.noise > 0.0:
                sample_val += patch.noise * (random.random() * 2.0 - 1.0)

            # ADSR
            if attack and idx < attack:
                env = idx / attack
            elif decay and idx < sustain_start:
                env = 1.0 - (1.0 - patch.sustain_level) * ((idx - attack) / decay)
            elif idx < sustain_end:
                env = patch.sustain_level
            elif release > 0:
                env = patch.sustain_level * (
                    1.0 - (idx - sustain_end) / max(1, release)
                )
            else:
                env = 0.0

            val = sample_val * max(0.0, env)

            # Coarse bitcrush to mimic 8-bit hardware
            if patch.bitcrush_levels > 0:
                levels = float(patch.bitcrush_levels)
                val = round(val * levels) / levels

            samples[idx] = val

        # Normalise the rendered samples
        peak = max((abs(val) for val in samples), default=1.0)
        if peak <= 0.0:
            peak = 1.0
        # Apply patch volume scaled by master SFX volume
        scale = 32767 * (patch.volume * self.master_sfx_volume) / peak

        waveform = array(
            "h",
            (int(max(-32767, min(32767, val * scale))) for val in samples),
        )
        return pygame.mixer.Sound(buffer=waveform)

    def _find_channel(self) -> pygame.mixer.Channel | None:
        if not self._channels:
            return None
        reserved = set(self._reserved_channels.values())
        for channel in self._channels:
            if channel in reserved:
                continue
            if not channel.get_busy():
                return channel
        # Steal the first non-reserved channel if all are busy.
        for channel in self._channels:
            if channel in reserved:
                continue
            channel.stop()
            return channel
        return None

    def _dynamic_volume(self, base: float) -> float:
        if not self._channels:
            return max(0.0, min(1.0, base))
        busy = sum(1 for channel in self._channels if channel.get_busy())
        ratio = busy / len(self._channels)
        scale = 1.0 - 0.45 * ratio
        scaled = base * scale
        return max(0.12, min(1.0, scaled))

    def _limit_volume(self, base: float, now: int) -> float:
        window = self._limiter_window_ms
        self._mix_events = [
            (ts, level) for ts, level in self._mix_events if now - ts < window
        ]
        projected = sum(level for _, level in self._mix_events) + base
        if projected <= self._limiter_ceiling:
            self._mix_events.append((now, base))
            return base
        scale = max(0.2, self._limiter_ceiling / max(projected, 1e-5))
        adjusted = base * scale
        self._mix_events.append((now, adjusted))
        return adjusted

    # ===========================
    #   Public API
    # ===========================

    def play(self, name: str) -> None:
        """Play the requested chiptune-style tone."""
        if not self.enabled:
            return
        sound = self.sounds.get(name)
        if not sound:
            return
        fade = max(0, self.sound_fades.get(name, 18))
        base_volume = self.mix_levels.get(name, 0.4)
        now = pygame.time.get_ticks()
        last_tick = self._last_play.get(name, 0)
        if now - last_tick < self._sound_gate_ms:
            return
        self._last_play[name] = now

        try:
            channel = self._reserved_channels.get(name)
            if channel is not None:
                if name == "ripple" and channel.get_busy():
                    channel.fadeout(max(120, fade))
                channel.set_volume(
                    self._dynamic_volume(self._limit_volume(base_volume, now))
                )
                channel.play(sound, fade_ms=fade)
                return

            channel = self._find_channel()
            if channel is None:
                return
            channel.set_volume(
                self._dynamic_volume(self._limit_volume(base_volume, now))
            )
            channel.play(sound, fade_ms=fade)
        except pygame.error:
            self.enabled = False
