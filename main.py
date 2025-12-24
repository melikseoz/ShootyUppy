from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Dict, List, Tuple

import pygame

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for older interpreters
    import tomli as tomllib


DEFAULT_CONFIG: Dict[str, Dict[str, float]] = {
    "window": {"width": 960, "height": 720, "fps": 60},
    "player": {
        "speed": 360.0,
        "shoot_cooldown": 0.25,
        "bullet_speed": 900.0,
        "bullet_damage": 1,
        "bullet_count": 1,
        "max_health": 5,
        "bottom_margin": 32,
    },
    "enemy": {
        "rows": 3,
        "cols": 6,
        "horizontal_speed": 120.0,
        "shoot_cooldown": 1.5,
        "bullet_speed": 360.0,
        "bullet_damage": 1,
        "spacing": 96,
        "start_y": 90,
        "padding": 60,
        "base_health": 2,
    },
    "wave": {"speed_scaling": 0.12, "health_scaling": 0.6, "count_scaling": 0.12},
}

Color = Tuple[int, int, int]
WHITE: Color = (245, 245, 245)
GREEN: Color = (44, 204, 112)
RED: Color = (229, 77, 66)
YELLOW: Color = (242, 201, 76)
BLUE: Color = (90, 178, 255)
BACKGROUND: Color = (15, 16, 24)
GREY: Color = (120, 120, 134)


def deep_update(base: Dict, override: Dict) -> Dict:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = deep_update(base[key], value)
        else:
            base[key] = value
    return base


def load_config(path: Path) -> Dict[str, Dict[str, float]]:
    config = {key: value.copy() for key, value in DEFAULT_CONFIG.items()}
    if path.exists():
        with path.open("rb") as fp:
            file_config = tomllib.load(fp)
        config = deep_update(config, file_config)
    return config


class Bullet(pygame.sprite.Sprite):
    def __init__(self, pos: Tuple[float, float], velocity: Tuple[float, float], color: Color, damage: int):
        super().__init__()
        self.image = pygame.Surface((6, 18))
        self.image.fill(color)
        self.rect = self.image.get_rect(center=pos)
        self.velocity = velocity
        self.damage = damage

    def update(self, dt: float) -> None:
        self.rect.x += self.velocity[0] * dt
        self.rect.y += self.velocity[1] * dt


class Player(pygame.sprite.Sprite):
    def __init__(self, config: Dict[str, float], screen_rect: pygame.Rect):
        super().__init__()
        self.config = config
        self.image = pygame.Surface((60, 28))
        self.image.fill(GREEN)
        start_y = screen_rect.bottom - config["bottom_margin"]
        self.rect = self.image.get_rect(midbottom=(screen_rect.centerx, start_y))
        self.speed = config["speed"]
        self.shoot_cooldown = config["shoot_cooldown"]
        self.last_shot_time = 0.0
        self.bullet_speed = config["bullet_speed"]
        self.bullet_damage = config["bullet_damage"]
        self.bullet_count = int(config["bullet_count"])
        self.max_health = int(config["max_health"])
        self.health = self.max_health

    def move(self, direction: float, dt: float, screen_rect: pygame.Rect) -> None:
        self.rect.x += direction * self.speed * dt
        self.rect.clamp_ip(screen_rect)

    def shoot(self, now: float) -> List[Bullet]:
        if now - self.last_shot_time < self.shoot_cooldown:
            return []
        self.last_shot_time = now
        bullets: List[Bullet] = []
        spread = 16
        offsets = [
            (i - (self.bullet_count - 1) / 2) * spread for i in range(self.bullet_count)
        ]
        for offset in offsets:
            pos = (self.rect.centerx + offset, self.rect.top)
            bullet = Bullet(pos, (0, -self.bullet_speed), BLUE, self.bullet_damage)
            bullets.append(bullet)
        return bullets

    def upgrade_damage(self, amount: int = 1) -> None:
        self.bullet_damage += amount

    def upgrade_attack_speed(self, factor: float = 0.85) -> None:
        self.shoot_cooldown = max(0.05, self.shoot_cooldown * factor)

    def upgrade_bullet_count(self, amount: int = 1, cap: int = 6) -> None:
        self.bullet_count = min(cap, self.bullet_count + amount)

    def upgrade_speed(self, amount: float = 40.0) -> None:
        self.speed += amount


class Enemy(pygame.sprite.Sprite):
    def __init__(
        self,
        pos: Tuple[float, float],
        config: Dict[str, float],
        speed_multiplier: float,
        health_multiplier: float,
    ):
        super().__init__()
        self.base_width = 50
        self.base_height = 30
        self.image = pygame.Surface((self.base_width, self.base_height))
        self.image.fill(YELLOW)
        self.rect = self.image.get_rect(center=pos)
        self.direction = 1
        self.speed = config["horizontal_speed"] * speed_multiplier
        base_health = config["base_health"]
        self.health = max(1, math.ceil(base_health * health_multiplier))
        self.shoot_cooldown = config["shoot_cooldown"] / (0.8 + speed_multiplier * 0.2)
        self.last_shot_time = 0.0
        self.bullet_speed = config["bullet_speed"]
        self.bullet_damage = config["bullet_damage"]

    def update(self, dt: float, screen_rect: pygame.Rect) -> None:
        self.rect.x += self.direction * self.speed * dt
        if self.rect.left <= screen_rect.left + 20 or self.rect.right >= screen_rect.right - 20:
            self.direction *= -1

    def try_shoot(self, now: float) -> Bullet | None:
        if now - self.last_shot_time < self.shoot_cooldown:
            return None
        # Slight randomness so not all enemies fire simultaneously.
        if random.random() < 0.25:
            self.last_shot_time = now
            pos = (self.rect.centerx, self.rect.bottom)
            return Bullet(pos, (0, self.bullet_speed), RED, self.bullet_damage)
        return None


Powerup = Tuple[str, str, callable]


def build_powerups() -> List[Powerup]:
    return [
        (
            "Increased Damage",
            "+1 bullet damage.",
            lambda player: player.upgrade_damage(1),
        ),
        (
            "Increased Attack Speed",
            "Fire faster by 15%.",
            lambda player: player.upgrade_attack_speed(0.85),
        ),
        (
            "Increased Number of Bullets",
            "Add one more projectile per shot.",
            lambda player: player.upgrade_bullet_count(1),
        ),
        (
            "Increased Movement Speed",
            "+40 units movement speed.",
            lambda player: player.upgrade_speed(40.0),
        ),
    ]


def create_wave(wave: int, config: Dict[str, Dict[str, float]], screen_rect: pygame.Rect) -> pygame.sprite.Group:
    enemies = pygame.sprite.Group()
    enemy_cfg = config["enemy"]
    row_count = enemy_cfg["rows"]
    col_count = enemy_cfg["cols"]
    base_total = row_count * col_count
    additional = math.ceil(base_total * config["wave"]["count_scaling"] * (wave - 1))
    total = base_total + additional
    speed_multiplier = 1 + (wave - 1) * config["wave"]["speed_scaling"]
    health_multiplier = 1 + (wave - 1) * config["wave"]["health_scaling"]
    spacing = enemy_cfg["spacing"]
    start_y = enemy_cfg["start_y"]
    padding = enemy_cfg["padding"]

    cols = max(1, int(min(col_count + wave // 2, (screen_rect.width - padding * 2) // spacing)))
    for idx in range(total):
        row = idx // cols
        col = idx % cols
        x = padding + col * spacing
        y = start_y + row * spacing
        x = min(max(padding, x), screen_rect.width - padding)
        enemy = Enemy((x, y), enemy_cfg, speed_multiplier, health_multiplier)
        enemies.add(enemy)
    return enemies


def draw_text(
    surface: pygame.Surface,
    text: str,
    font: pygame.font.Font,
    color: Color,
    pos: Tuple[int, int],
    align: str = "topleft",
) -> None:
    rendered = font.render(text, True, color)
    rect = rendered.get_rect(**{align: pos})
    surface.blit(rendered, rect)


def draw_powerup_overlay(
    surface: pygame.Surface,
    font: pygame.font.Font,
    title_font: pygame.font.Font,
    choices: List[Powerup],
) -> None:
    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    surface.blit(overlay, (0, 0))
    draw_text(surface, "Choose a powerup (press 1-3)", title_font, WHITE, (surface.get_width() // 2, 120), "center")
    card_width = 260
    spacing = 40
    total_width = card_width * len(choices) + spacing * (len(choices) - 1)
    start_x = (surface.get_width() - total_width) // 2
    top = 200
    for idx, (name, desc, _) in enumerate(choices):
        x = start_x + idx * (card_width + spacing)
        card_rect = pygame.Rect(x, top, card_width, 180)
        pygame.draw.rect(surface, GREY, card_rect, border_radius=10)
        pygame.draw.rect(surface, WHITE, card_rect, width=2, border_radius=10)
        draw_text(surface, f"{idx + 1}. {name}", font, WHITE, (card_rect.centerx, card_rect.top + 16), "center")
        draw_text(surface, desc, font, WHITE, (card_rect.centerx, card_rect.centery), "center")
        draw_text(surface, "Press number", font, BLUE, (card_rect.centerx, card_rect.bottom - 32), "center")


def main() -> None:
    config_path = Path("config.toml")
    config = load_config(config_path)
    pygame.init()
    screen = pygame.display.set_mode((int(config["window"]["width"]), int(config["window"]["height"])))
    pygame.display.set_caption("ShootyUppy - Click to shoot")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("arial", 20)
    title_font = pygame.font.SysFont("arial", 30, bold=True)
    screen_rect = screen.get_rect()

    player = Player(config["player"], screen_rect)
    enemies = create_wave(1, config, screen_rect)
    player_bullets = pygame.sprite.Group()
    enemy_bullets = pygame.sprite.Group()
    wave = 1
    running = True
    state = "playing"  # playing | choosing | game_over
    powerup_choices: List[Powerup] = []
    powerups = build_powerups()
    pending_wave: int | None = None

    while running:
        dt = clock.tick(config["window"]["fps"]) / 1000.0
        now = pygame.time.get_ticks() / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            if state == "playing" and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                new_bullets = player.shoot(now)
                player_bullets.add(new_bullets)
            if state == "choosing" and event.type == pygame.KEYDOWN:
                choice_index = None
                if event.unicode in ("1", "2", "3"):
                    choice_index = int(event.unicode) - 1
                if choice_index is not None and choice_index < len(powerup_choices):
                    _, _, apply_fn = powerup_choices[choice_index]
                    apply_fn(player)
                    state = "playing"
                    enemies = create_wave(pending_wave or wave, config, screen_rect)
                    pending_wave = None

        keys = pygame.key.get_pressed()
        if state == "playing":
            direction = 0.0
            if keys[pygame.K_a] or keys[pygame.K_LEFT]:
                direction -= 1
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
                direction += 1
            player.move(direction, dt, screen_rect)

            player_bullets.update(dt)
            enemy_bullets.update(dt)
            enemies.update(dt, screen_rect)

            # Remove bullets off-screen.
            for bullet in list(player_bullets):
                if bullet.rect.bottom < 0:
                    player_bullets.remove(bullet)
            for bullet in list(enemy_bullets):
                if bullet.rect.top > screen_rect.height:
                    enemy_bullets.remove(bullet)

            # Enemy shooting back.
            for enemy in enemies:
                shot = enemy.try_shoot(now)
                if shot:
                    enemy_bullets.add(shot)

            # Collisions: player bullets vs enemies.
            for bullet in list(player_bullets):
                hits = [e for e in enemies if e.rect.colliderect(bullet.rect)]
                if hits:
                    for hit in hits:
                        hit.health -= bullet.damage
                        if hit.health <= 0:
                            enemies.remove(hit)
                    player_bullets.remove(bullet)

            # Collisions: enemy bullets vs player.
            for bullet in list(enemy_bullets):
                if player.rect.colliderect(bullet.rect):
                    player.health -= bullet.damage
                    enemy_bullets.remove(bullet)
                    if player.health <= 0:
                        state = "game_over"

            # Wave cleared?
            if not enemies and state == "playing":
                wave += 1
                should_choose_powerup = wave > 1 and (wave - 1) % 2 == 0
                if should_choose_powerup:
                    powerup_choices = random.sample(powerups, 3)
                    state = "choosing"
                    pending_wave = wave
                else:
                    enemies = create_wave(wave, config, screen_rect)

        # Rendering
        screen.fill(BACKGROUND)
        pygame.draw.rect(screen, GREY, (0, screen_rect.bottom - 12, screen_rect.width, 12))
        screen.blit(player.image, player.rect)
        enemies.draw(screen)
        player_bullets.draw(screen)
        enemy_bullets.draw(screen)

        draw_text(screen, f"Wave: {wave}", font, WHITE, (16, 12))
        draw_text(screen, f"Health: {player.health}/{player.max_health}", font, WHITE, (16, 36))
        draw_text(screen, "Move: A/D or arrows | Click to shoot", font, GREY, (16, 60))
        draw_text(screen, "Powerup every 2 waves | Survive the barrage!", font, GREY, (16, 84))

        if state == "choosing":
            draw_powerup_overlay(screen, font, title_font, powerup_choices)
        elif state == "game_over":
            overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 180))
            screen.blit(overlay, (0, 0))
            draw_text(screen, "Game Over", title_font, RED, screen_rect.center, "center")
            draw_text(screen, "Press ESC to exit", font, WHITE, (screen_rect.centerx, screen_rect.centery + 40), "center")

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
