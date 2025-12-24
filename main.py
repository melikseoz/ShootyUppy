from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Callable, Dict, List, Tuple

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
PURPLE: Color = (162, 90, 255)
ORANGE: Color = (255, 158, 89)
CYAN: Color = (80, 226, 196)
BACKGROUND: Color = (15, 16, 24)
GREY: Color = (120, 120, 134)
LIGHTNING_COLOR: Color = (142, 212, 255)

DAMAGE_FLASH_DURATION = 0.25
BASIC_ENEMY_SHAPE = "rectangle"
ENEMY_SHAPES = [
    ("rectangle", YELLOW),
    ("triangle", ORANGE),
    ("circle", CYAN),
    ("diamond", PURPLE),
]
BOUNCY_BALL_SIZE = 36
BOUNCY_BALL_LIFETIME = 6.0
BOUNCY_BALL_COLLISIONS = 10
LIGHTNING_DURATION = 0.25


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


def format_health(value: float) -> str:
    return str(int(round(value)))


def build_enemy_surface(shape: str, color: Color) -> pygame.Surface:
    width, height = 50, 30
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    rect = surface.get_rect()
    if shape == "triangle":
        points = [(rect.centerx, rect.top), (rect.right, rect.bottom), (rect.left, rect.bottom)]
        pygame.draw.polygon(surface, color, points)
    elif shape == "circle":
        pygame.draw.ellipse(surface, color, rect)
    elif shape == "diamond":
        points = [(rect.centerx, rect.top), (rect.right, rect.centery), (rect.centerx, rect.bottom), (rect.left, rect.centery)]
        pygame.draw.polygon(surface, color, points)
    else:
        pygame.draw.rect(surface, color, rect)
    return surface


class Bullet(pygame.sprite.Sprite):
    def __init__(
        self,
        pos: Tuple[float, float],
        velocity: Tuple[float, float],
        color: Color,
        damage: float,
        owner: pygame.sprite.Sprite | None = None,
    ):
        super().__init__()
        self.image = pygame.Surface((6, 18))
        self.image.fill(color)
        self.rect = self.image.get_rect(center=pos)
        self.velocity = velocity
        self.damage = float(damage)
        self.owner = owner

    def update(self, dt: float) -> None:
        self.rect.x += self.velocity[0] * dt
        self.rect.y += self.velocity[1] * dt


class BouncyBall(pygame.sprite.Sprite):
    def __init__(self, pos: Tuple[float, float], velocity: pygame.Vector2, damage: float):
        super().__init__()
        self.image = pygame.Surface((BOUNCY_BALL_SIZE, BOUNCY_BALL_SIZE), pygame.SRCALPHA)
        pygame.draw.circle(self.image, CYAN, (BOUNCY_BALL_SIZE // 2, BOUNCY_BALL_SIZE // 2), BOUNCY_BALL_SIZE // 2)
        self.rect = self.image.get_rect(center=pos)
        self.velocity = velocity
        self.damage = float(damage)
        self.lifetime = BOUNCY_BALL_LIFETIME
        self.remaining_collisions = BOUNCY_BALL_COLLISIONS

    def update(self, dt: float, screen_rect: pygame.Rect) -> None:
        self.lifetime -= dt
        if self.lifetime <= 0:
            self.kill()
            return

        self.rect.x += self.velocity.x * dt
        self.rect.y += self.velocity.y * dt

        if self.rect.left <= screen_rect.left or self.rect.right >= screen_rect.right:
            self.velocity.x *= -1
            self.rect.clamp_ip(screen_rect)
        if self.rect.top <= screen_rect.top or self.rect.bottom >= screen_rect.bottom:
            self.velocity.y *= -1
            self.rect.clamp_ip(screen_rect)

    def on_collision(self) -> None:
        self.remaining_collisions -= 1
        if self.remaining_collisions <= 0:
            self.kill()


class Player(pygame.sprite.Sprite):
    def __init__(self, config: Dict[str, float], screen_rect: pygame.Rect):
        super().__init__()
        self.config = config
        self.image = pygame.Surface((60, 28))
        self.image.fill(GREEN)
        start_y = screen_rect.bottom - config["bottom_margin"]
        self.rect = self.image.get_rect(midbottom=(screen_rect.centerx, start_y))
        self.speed = float(config["speed"])
        self.shoot_cooldown = float(config["shoot_cooldown"])
        self.last_shot_time = 0.0
        self.bullet_speed = float(config["bullet_speed"])
        self.bullet_damage = float(config["bullet_damage"])
        self.bullet_count = int(config["bullet_count"])
        self.max_health = float(config["max_health"])
        self.health = float(self.max_health)
        self.has_split_shot = False
        self.has_thorns = False
        self.has_chain_lightning = False
        self.has_bouncy_ball = False

    def move(self, direction: float, dt: float, screen_rect: pygame.Rect) -> None:
        self.rect.x += direction * self.speed * dt
        self.rect.clamp_ip(screen_rect)

    def shoot(self, now: float) -> List[pygame.sprite.Sprite]:
        if now - self.last_shot_time < self.shoot_cooldown:
            return []
        self.last_shot_time = now
        projectiles: List[pygame.sprite.Sprite] = []
        spread = 16
        offsets = [
            (i - (self.bullet_count - 1) / 2) * spread for i in range(self.bullet_count)
        ]
        for offset in offsets:
            pos = (self.rect.centerx + offset, self.rect.top)
            bullet = Bullet(pos, (0, -self.bullet_speed), BLUE, self.bullet_damage)
            projectiles.append(bullet)
        if self.has_split_shot:
            diag_speed = self.bullet_speed * 0.75
            projectiles.append(Bullet(self.rect.midtop, (-diag_speed, -self.bullet_speed), BLUE, self.bullet_damage))
            projectiles.append(Bullet(self.rect.midtop, (diag_speed, -self.bullet_speed), BLUE, self.bullet_damage))
        return projectiles

    def upgrade_damage(self, amount: int = 1) -> None:
        self.bullet_damage += float(amount)

    def upgrade_attack_speed(self, factor: float = 0.85) -> None:
        self.shoot_cooldown = max(0.05, self.shoot_cooldown * factor)

    def upgrade_bullet_count(self, amount: int = 1, cap: int = 6) -> None:
        self.bullet_count = min(cap, self.bullet_count + amount)

    def upgrade_speed(self, amount: float = 40.0) -> None:
        self.speed += amount

    def heal_percentage(self, pct: float) -> None:
        self.health = min(self.max_health, self.health + self.max_health * pct)


class Enemy(pygame.sprite.Sprite):
    def __init__(
        self,
        pos: Tuple[float, float],
        config: Dict[str, float],
        speed_multiplier: float,
        health_multiplier: float,
        shape: str,
        color: Color,
    ):
        super().__init__()
        self.base_width = 50
        self.base_height = 30
        self.image = build_enemy_surface(shape, color)
        self.rect = self.image.get_rect(center=pos)
        self.direction = 1
        self.speed = float(config["horizontal_speed"]) * speed_multiplier
        base_health = float(config["base_health"])
        self.health = max(1.0, base_health * health_multiplier)
        self.shoot_cooldown = float(config["shoot_cooldown"]) / (0.8 + speed_multiplier * 0.2)
        self.last_shot_time = 0.0
        self.bullet_speed = float(config["bullet_speed"])
        self.bullet_damage = float(config["bullet_damage"])

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
            return Bullet(pos, (0, self.bullet_speed), RED, self.bullet_damage, owner=self)
        return None


Powerup = Tuple[str, str, Callable[[Player], None]]


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
        (
            "Heal",
            "Recover 40% of your max HP.",
            lambda player: player.heal_percentage(0.4),
        ),
        (
            "Split Shot",
            "Gain two diagonal bullets each attack.",
            lambda player: setattr(player, "has_split_shot", True),
        ),
        (
            "Thorns",
            "When hit, also destroy the attacking enemy.",
            lambda player: setattr(player, "has_thorns", True),
        ),
        (
            "Chain Lightning",
            "Shots chain between 4 enemies for half damage.",
            lambda player: setattr(player, "has_chain_lightning", True),
        ),
        (
            "Bouncy Ball",
            "A bouncing orb patrols the arena for half bullet damage.",
            lambda player: setattr(player, "has_bouncy_ball", True),
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
        if wave >= 3:
            shape, color = random.choice(ENEMY_SHAPES)
        else:
            shape, color = BASIC_ENEMY_SHAPE, YELLOW
        enemy = Enemy((x, y), enemy_cfg, speed_multiplier, health_multiplier, shape, color)
        enemies.add(enemy)
    return enemies


def build_lightning_polyline(start: pygame.Vector2, end: pygame.Vector2) -> List[pygame.Vector2]:
    direction = end - start
    length = direction.length()
    if length == 0:
        return [start, end]
    direction = direction.normalize()
    perpendicular = pygame.Vector2(-direction.y, direction.x)
    segments = max(2, int(length // 35))
    points = [start]
    for i in range(1, segments):
        t = i / segments
        offset = perpendicular * random.uniform(-10, 10)
        points.append(start + direction * length * t + offset)
    points.append(end)
    return points


def chain_lightning_strike(
    start_enemy: Enemy, enemies: pygame.sprite.Group, damage: float, max_bounces: int = 4
) -> List[Tuple[pygame.Vector2, pygame.Vector2]]:
    remaining_targets = [e for e in enemies if e is not start_enemy]
    current_pos = pygame.Vector2(start_enemy.rect.center)
    segments: List[Tuple[pygame.Vector2, pygame.Vector2]] = []
    for _ in range(max_bounces):
        if not remaining_targets:
            break
        target = min(remaining_targets, key=lambda e: pygame.Vector2(e.rect.center).distance_to(current_pos))
        target.health -= damage
        target_center = pygame.Vector2(target.rect.center)
        segments.append((current_pos, target_center))
        current_pos = target_center
        if target.health <= 0:
            enemies.remove(target)
            remaining_targets = [e for e in remaining_targets if e is not target]
        else:
            remaining_targets = [e for e in remaining_targets if e is not target]
    return segments


def create_lightning_effect(segments: List[Tuple[pygame.Vector2, pygame.Vector2]]) -> List[List[pygame.Vector2]]:
    return [build_lightning_polyline(start, end) for start, end in segments]


def ensure_bouncy_ball_active(
    player: Player, bouncy_balls: pygame.sprite.Group, screen_rect: pygame.Rect
) -> None:
    if not player.has_bouncy_ball or bouncy_balls:
        return
    velocity = pygame.Vector2(player.bullet_speed * random.choice([-0.7, 0.7]), -player.bullet_speed * 0.6)
    ball = BouncyBall(player.rect.midtop, velocity, player.bullet_damage * 0.5)
    # Keep the ball on screen if the player is near the edge.
    ball.rect.clamp_ip(screen_rect)
    bouncy_balls.add(ball)


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
    card_rects: List[pygame.Rect],
) -> None:
    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    surface.blit(overlay, (0, 0))
    draw_text(
        surface,
        "Choose a powerup (press 1-3 or click)",
        title_font,
        WHITE,
        (surface.get_width() // 2, 120),
        "center",
    )
    for idx, (card_rect, (name, desc, _)) in enumerate(zip(card_rects, choices)):
        pygame.draw.rect(surface, GREY, card_rect, border_radius=10)
        pygame.draw.rect(surface, WHITE, card_rect, width=2, border_radius=10)
        draw_text(surface, f"{idx + 1}. {name}", font, WHITE, (card_rect.centerx, card_rect.top + 16), "center")
        draw_text(surface, desc, font, WHITE, (card_rect.centerx, card_rect.centery), "center")
        draw_text(surface, "Press number or click", font, BLUE, (card_rect.centerx, card_rect.bottom - 32), "center")


def build_powerup_card_rects(surface: pygame.Surface, card_count: int) -> List[pygame.Rect]:
    card_width = 360
    spacing = 40
    total_width = card_width * card_count + spacing * (card_count - 1)
    start_x = (surface.get_width() - total_width) // 2
    top = 200
    return [pygame.Rect(start_x + idx * (card_width + spacing), top, card_width, 180) for idx in range(card_count)]


def reset_game(
    config: Dict[str, Dict[str, float]],
    screen_rect: pygame.Rect,
) -> Tuple[
    Player,
    pygame.sprite.Group,
    pygame.sprite.Group,
    pygame.sprite.Group,
    pygame.sprite.Group,
    int,
    str,
]:
    player = Player(config["player"], screen_rect)
    enemies = create_wave(1, config, screen_rect)
    player_bullets = pygame.sprite.Group()
    enemy_bullets = pygame.sprite.Group()
    bouncy_balls = pygame.sprite.Group()
    wave = 1
    state = "playing"
    return player, enemies, player_bullets, enemy_bullets, bouncy_balls, wave, state


def set_display_mode(fullscreen: bool, config: Dict[str, Dict[str, float]]) -> Tuple[pygame.Surface, pygame.Rect]:
    if fullscreen:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    else:
        screen = pygame.display.set_mode((int(config["window"]["width"]), int(config["window"]["height"])))
    return screen, screen.get_rect()


def main() -> None:
    config_path = Path("config.toml")
    config = load_config(config_path)
    pygame.init()
    fullscreen = False
    screen, screen_rect = set_display_mode(fullscreen, config)
    pygame.display.set_caption("ShootyUppy - Click to shoot")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("arial", 20)
    title_font = pygame.font.SysFont("arial", 30, bold=True)

    player, enemies, player_bullets, enemy_bullets, bouncy_balls, wave, state = reset_game(config, screen_rect)
    lightning_effects: List[Dict[str, object]] = []
    running = True
    # playing | choosing | game_over
    powerup_choices: List[Powerup] = []
    powerup_card_rects: List[pygame.Rect] = []
    powerups = build_powerups()
    pending_wave: int | None = None
    damage_flash_timer = 0.0

    while running:
        dt = clock.tick(config["window"]["fps"]) / 1000.0
        now = pygame.time.get_ticks() / 1000.0
        damage_flash_timer = max(0.0, damage_flash_timer - dt)
        for effect in list(lightning_effects):
            effect["timer"] = float(effect["timer"]) - dt
            if effect["timer"] <= 0:
                lightning_effects.remove(effect)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                fullscreen = not fullscreen
                screen, screen_rect = set_display_mode(fullscreen, config)
                pygame.display.set_caption("ShootyUppy - Click to shoot")
                player.rect.clamp_ip(screen_rect)
                for sprite in enemies:
                    sprite.rect.clamp_ip(screen_rect)
                for ball in bouncy_balls:
                    ball.rect.clamp_ip(screen_rect)
                if state == "choosing":
                    powerup_card_rects = build_powerup_card_rects(screen, len(powerup_choices))
            if state == "game_over" and event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                player, enemies, player_bullets, enemy_bullets, bouncy_balls, wave, state = reset_game(
                    config, screen_rect
                )
                pending_wave = None
                powerup_choices = []
                powerup_card_rects = []
                damage_flash_timer = 0.0
            if state == "playing" and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                new_bullets = player.shoot(now)
                for projectile in new_bullets:
                    if isinstance(projectile, BouncyBall):
                        bouncy_balls.add(projectile)
                    else:
                        player_bullets.add(projectile)
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
                    powerup_choices = []
                    powerup_card_rects = []
                    ensure_bouncy_ball_active(player, bouncy_balls, screen_rect)
            if state == "choosing" and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = pygame.Vector2(event.pos)
                for idx, rect in enumerate(powerup_card_rects):
                    if rect.collidepoint(pos):
                        _, _, apply_fn = powerup_choices[idx]
                        apply_fn(player)
                        state = "playing"
                        enemies = create_wave(pending_wave or wave, config, screen_rect)
                        pending_wave = None
                        powerup_choices = []
                        powerup_card_rects = []
                        ensure_bouncy_ball_active(player, bouncy_balls, screen_rect)
                        break

        keys = pygame.key.get_pressed()
        if state == "playing":
            direction = 0.0
            if keys[pygame.K_a] or keys[pygame.K_LEFT]:
                direction -= 1
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
                direction += 1
            player.move(direction, dt, screen_rect)

            ensure_bouncy_ball_active(player, bouncy_balls, screen_rect)
            player_bullets.update(dt)
            enemy_bullets.update(dt)
            bouncy_balls.update(dt, screen_rect)
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
                    start_enemy = next((hit for hit in hits if hit in enemies), None)
                    for hit in hits:
                        hit.health -= bullet.damage
                        if hit.health <= 0:
                            enemies.remove(hit)
                    if player.has_chain_lightning and start_enemy:
                        segments = chain_lightning_strike(start_enemy, enemies, bullet.damage * 0.5)
                        if segments:
                            lightning_effects.append(
                                {"timer": LIGHTNING_DURATION, "polylines": create_lightning_effect(segments)}
                            )
                    player_bullets.remove(bullet)

            # Collisions: bouncy balls vs enemies.
            for ball in list(bouncy_balls):
                hits = [e for e in enemies if e.rect.colliderect(ball.rect)]
                if hits:
                    start_enemy = next((hit for hit in hits if hit in enemies), None)
                    for hit in hits:
                        hit.health -= ball.damage
                        if hit.health <= 0:
                            enemies.remove(hit)
                    if player.has_chain_lightning and start_enemy:
                        segments = chain_lightning_strike(start_enemy, enemies, ball.damage * 0.5)
                        if segments:
                            lightning_effects.append(
                                {"timer": LIGHTNING_DURATION, "polylines": create_lightning_effect(segments)}
                            )
                    ball.on_collision()

            # Collisions: enemy bullets vs player.
            for bullet in list(enemy_bullets):
                if player.rect.colliderect(bullet.rect):
                    player.health = max(0.0, player.health - bullet.damage)
                    damage_flash_timer = DAMAGE_FLASH_DURATION
                    owner = getattr(bullet, "owner", None)
                    if player.has_thorns and owner in enemies:
                        enemies.remove(owner)
                    enemy_bullets.remove(bullet)
                    if player.health <= 0:
                        state = "game_over"

            # Wave cleared?
            if not enemies and state == "playing":
                wave += 1
                should_choose_powerup = wave > 1 and (wave - 1) % 2 == 0
                if should_choose_powerup:
                    powerup_choices = random.sample(powerups, 3)
                    powerup_card_rects = build_powerup_card_rects(screen, len(powerup_choices))
                    state = "choosing"
                    pending_wave = wave
                else:
                    enemies = create_wave(wave, config, screen_rect)

        # Rendering
        if damage_flash_timer > 0:
            intensity = damage_flash_timer / DAMAGE_FLASH_DURATION
            background_color = tuple(
                int(BACKGROUND[i] + (RED[i] - BACKGROUND[i]) * min(1.0, intensity)) for i in range(3)
            )
        else:
            background_color = BACKGROUND
        screen.fill(background_color)
        pygame.draw.rect(screen, GREY, (0, screen_rect.bottom - 12, screen_rect.width, 12))
        screen.blit(player.image, player.rect)
        enemies.draw(screen)
        for enemy in enemies:
            draw_text(screen, format_health(enemy.health), font, BACKGROUND, enemy.rect.center, "center")
        player_bullets.draw(screen)
        bouncy_balls.draw(screen)
        enemy_bullets.draw(screen)
        for effect in lightning_effects:
            intensity = max(0.0, min(1.0, float(effect["timer"]) / LIGHTNING_DURATION))
            core_color = tuple(
                int(LIGHTNING_COLOR[i] * intensity + WHITE[i] * (1.0 - intensity) * 0.5) for i in range(3)
            )
            glow_color = tuple(min(255, int(value * 1.15)) for value in core_color)
            line_width = max(1, int(4 * intensity))
            for polyline in effect["polylines"]:
                points = [(int(point.x), int(point.y)) for point in polyline]
                if len(points) >= 2:
                    pygame.draw.lines(screen, glow_color, False, points, line_width + 2)
                    pygame.draw.lines(screen, core_color, False, points, line_width)

        draw_text(screen, f"Wave: {wave}", font, WHITE, (16, 12))
        draw_text(screen, f"Health: {format_health(player.health)}/{format_health(player.max_health)}", font, WHITE, (16, 36))
        draw_text(screen, "Move: A/D or arrows | Click to shoot", font, GREY, (16, 60))
        draw_text(screen, "Press F11 to toggle fullscreen", font, GREY, (16, 84))
        draw_text(screen, "Powerup every 2 waves | Survive the barrage!", font, GREY, (16, 108))

        if state == "choosing":
            draw_powerup_overlay(screen, font, title_font, powerup_choices, powerup_card_rects)
        elif state == "game_over":
            overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 180))
            screen.blit(overlay, (0, 0))
            draw_text(screen, "Game Over", title_font, RED, screen_rect.center, "center")
            draw_text(
                screen,
                "Press R to restart or ESC to exit",
                font,
                WHITE,
                (screen_rect.centerx, screen_rect.centery + 40),
                "center",
            )

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
