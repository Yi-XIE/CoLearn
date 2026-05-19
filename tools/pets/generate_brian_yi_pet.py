#!/usr/bin/env python3
"""Generate a Brian-inspired Codex pet from a handcrafted vector-like model."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from PIL import ImageDraw

CELL_W = 192
CELL_H = 208
PET_ID = "brian"
DISPLAY_NAME = "Brian"
DESCRIPTION = "Brian from Family Guy as a Codex pet."

OUTLINE = (0, 0, 0, 255)
WHITE = (255, 255, 255, 255)
COLLAR = (220, 0, 52, 255)
TAG = (246, 168, 22, 255)
PINK = (241, 104, 149, 255)
TRANSPARENT = (0, 0, 0, 0)

ROW_COUNTS = {
    "idle": 6,
    "running-right": 8,
    "running-left": 8,
    "waving": 4,
    "jumping": 5,
    "failed": 8,
    "waiting": 6,
    "running": 6,
    "review": 6,
}


@dataclass(frozen=True)
class FrontPose:
    bob: float = 0.0
    blink: float = 0.0
    look_x: float = 0.0
    look_y: float = 0.0
    brow: float = 0.0
    expression: str = "flat"
    left_arm: tuple[float, float] = (68.0, 138.0)
    right_arm: tuple[float, float] = (124.0, 138.0)
    left_leg: tuple[float, float] = (78.0, 186.0)
    right_leg: tuple[float, float] = (114.0, 186.0)
    tag_dx: float = 0.0
    ear_left_drop: float = 0.0
    ear_right_drop: float = 0.0
    body_dx: float = 0.0
    mouth_dx: float = 0.0


def norm_box(box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    return (
        int(round(min(x0, x1))),
        int(round(min(y0, y1))),
        int(round(max(x0, x1))),
        int(round(max(y0, y1))),
    )


def ell(draw: ImageDraw.ImageDraw, box: tuple[float, float, float, float], fill, outline=OUTLINE, width: int = 3) -> None:
    draw.ellipse(norm_box(box), fill=fill, outline=outline, width=width)


def rr(
    draw: ImageDraw.ImageDraw,
    box: tuple[float, float, float, float],
    radius: int,
    fill,
    outline=OUTLINE,
    width: int = 3,
) -> None:
    draw.rounded_rectangle(norm_box(box), radius=radius, fill=fill, outline=outline, width=width)


def poly(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]], fill, outline=OUTLINE, width: int = 3) -> None:
    pts = [(int(round(x)), int(round(y))) for x, y in points]
    draw.polygon(pts, fill=fill, outline=outline)
    if width > 1:
        draw.line(pts + [pts[0]], fill=outline, width=width, joint="curve")


def bezier(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    steps: int = 14,
) -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    for index in range(steps + 1):
        t = index / steps
        x = (
            (1 - t) ** 3 * p0[0]
            + 3 * (1 - t) ** 2 * t * p1[0]
            + 3 * (1 - t) * t * t * p2[0]
            + t**3 * p3[0]
        )
        y = (
            (1 - t) ** 3 * p0[1]
            + 3 * (1 - t) ** 2 * t * p1[1]
            + 3 * (1 - t) * t * t * p2[1]
            + t**3 * p3[1]
        )
        points.append((int(round(x)), int(round(y))))
    return points


def thick_curve(
    draw: ImageDraw.ImageDraw,
    start: tuple[float, float],
    ctrl: tuple[float, float],
    end: tuple[float, float],
    fill=WHITE,
    outline=OUTLINE,
    width: int = 10,
    paw: int = 7,
) -> None:
    pts = bezier(start, ctrl, ctrl, end, steps=12)
    draw.line(pts, fill=outline, width=width + 4, joint="curve")
    draw.line(pts, fill=fill, width=width, joint="curve")
    ell(draw, (end[0] - paw, end[1] - paw + 1, end[0] + paw, end[1] + paw + 1), fill=fill, outline=outline, width=2)


def draw_eye_front(
    draw: ImageDraw.ImageDraw,
    center: tuple[float, float],
    blink: float,
    look_x: float,
    look_y: float,
    brow: float,
) -> None:
    cx, cy = center
    if blink >= 0.88:
        draw.line((int(cx - 11), int(cy), int(cx + 11), int(cy + 1)), fill=OUTLINE, width=3)
        return
    open_height = max(6, 18 - int(round(blink * 12)))
    ell(draw, (cx - 15, cy - open_height / 2, cx + 15, cy + open_height / 2), fill=WHITE, outline=OUTLINE, width=2)
    pupil_x = cx + look_x * 3
    pupil_y = cy + look_y * 2
    ell(draw, (pupil_x - 2.5, pupil_y - 2.5, pupil_x + 2.5, pupil_y + 2.5), fill=OUTLINE, outline=OUTLINE, width=1)
    draw.line(
        (
            int(cx - 15),
            int(cy - 6 + brow),
            int(cx + 15),
            int(cy - 7 + brow),
        ),
        fill=OUTLINE,
        width=2,
    )


def draw_eye_side(draw: ImageDraw.ImageDraw, center: tuple[float, float], blink: float, brow: float) -> None:
    cx, cy = center
    if blink >= 0.88:
        draw.line((int(cx - 9), int(cy), int(cx + 9), int(cy)), fill=OUTLINE, width=3)
        return
    ell(draw, (cx - 13, cy - 8, cx + 13, cy + 8), fill=WHITE, outline=OUTLINE, width=2)
    ell(draw, (cx + 1, cy - 1, cx + 5, cy + 3), fill=OUTLINE, outline=OUTLINE, width=1)
    draw.line((int(cx - 12), int(cy - 5 + brow), int(cx + 12), int(cy - 6 + brow)), fill=OUTLINE, width=2)


def draw_mouth_front(draw: ImageDraw.ImageDraw, x: float, y: float, expression: str) -> None:
    if expression == "open":
        draw.pieslice(norm_box((x - 13, y - 2, x + 13, y + 16)), 0, 180, fill=OUTLINE, outline=OUTLINE)
        draw.pieslice(norm_box((x - 5, y + 7, x + 8, y + 15)), 180, 360, fill=PINK, outline=PINK)
    elif expression == "smirk":
        pts = bezier((x - 12, y + 1), (x - 4, y + 2), (x + 4, y - 1), (x + 12, y - 2), steps=10)
        draw.line(pts, fill=OUTLINE, width=2)
    elif expression == "frown":
        pts = bezier((x - 12, y - 1), (x - 4, y - 5), (x + 4, y - 5), (x + 12, y - 1), steps=10)
        draw.line(pts, fill=OUTLINE, width=2)
    else:
        draw.line((int(x - 12), int(y), int(x + 12), int(y - 1)), fill=OUTLINE, width=2)


def draw_front_frame(pose: FrontPose) -> Image.Image:
    image = Image.new("RGBA", (CELL_W, CELL_H), TRANSPARENT)
    draw = ImageDraw.Draw(image)

    bob = pose.bob
    dx = pose.body_dx

    poly(draw, [(46 + dx, 136 + bob), (34 + dx, 142 + bob), (48 + dx, 150 + bob)], fill=WHITE)

    rr(draw, (52 + dx, 82 + bob, 140 + dx, 184 + bob), radius=36, fill=WHITE, outline=OUTLINE, width=3)
    ell(draw, (54 + dx, 155 + bob, 96 + dx, 198 + bob), fill=WHITE, outline=OUTLINE, width=3)
    ell(draw, (96 + dx, 155 + bob, 138 + dx, 198 + bob), fill=WHITE, outline=OUTLINE, width=3)

    thick_curve(draw, (70 + dx, 104 + bob), (60 + dx, 123 + bob), pose.left_arm, width=10)
    thick_curve(draw, (122 + dx, 104 + bob), (132 + dx, 123 + bob), pose.right_arm, width=10)
    thick_curve(draw, (82 + dx, 152 + bob), (80 + dx, 170 + bob), pose.left_leg, width=10, paw=9)
    thick_curve(draw, (110 + dx, 152 + bob), (112 + dx, 170 + bob), pose.right_leg, width=10, paw=9)

    draw.line((int(96 + dx), int(154 + bob), int(96 + dx), int(185 + bob)), fill=OUTLINE, width=2)
    for start_x in (66 + dx, 72 + dx, 120 + dx, 126 + dx):
        draw.line((int(start_x), int(186 + bob), int(start_x + 3), int(180 + bob)), fill=OUTLINE, width=2)

    ell(draw, (42 + dx, 16 + bob + pose.ear_left_drop, 68 + dx, 51 + bob + pose.ear_left_drop), fill=WHITE, outline=OUTLINE, width=3)
    ell(draw, (124 + dx, 16 + bob + pose.ear_right_drop, 150 + dx, 51 + bob + pose.ear_right_drop), fill=WHITE, outline=OUTLINE, width=3)
    rr(draw, (48 + dx, 8 + bob, 144 + dx, 82 + bob), radius=30, fill=WHITE, outline=OUTLINE, width=3)

    draw.line((int(61 + dx), int(61 + bob), int(62 + dx), int(89 + bob)), fill=OUTLINE, width=2)
    draw.line((int(131 + dx), int(61 + bob), int(130 + dx), int(89 + bob)), fill=OUTLINE, width=2)

    draw_eye_front(draw, (76 + dx, 26 + bob), pose.blink, pose.look_x, pose.look_y, pose.brow)
    draw_eye_front(draw, (116 + dx, 26 + bob), pose.blink, pose.look_x, pose.look_y, pose.brow)
    ell(draw, (74 + dx, 21 + bob, 118 + dx, 72 + bob), fill=OUTLINE, outline=OUTLINE, width=1)
    draw_mouth_front(draw, 97 + dx + pose.mouth_dx, 71 + bob, pose.expression)
    draw.arc(norm_box((80 + dx, 73 + bob, 114 + dx, 84 + bob)), 15, 165, fill=OUTLINE, width=2)

    rr(draw, (54 + dx, 76 + bob, 138 + dx, 93 + bob), radius=8, fill=COLLAR, outline=OUTLINE, width=2)
    ell(draw, (92 + dx + pose.tag_dx, 92 + bob, 104 + dx + pose.tag_dx, 106 + bob), fill=TAG, outline=OUTLINE, width=2)

    return image


def draw_side_frame(phase: int) -> Image.Image:
    image = Image.new("RGBA", (CELL_W, CELL_H), TRANSPARENT)
    draw = ImageDraw.Draw(image)

    t = phase / 8.0
    stride = math.sin(t * math.tau)
    lift = math.cos(t * math.tau)
    bob = abs(stride) * 2.2

    rear_leg_x = 84 - stride * 7
    rear_leg_y = 185 - max(0.0, stride) * 7 + bob
    front_leg_x = 120 + stride * 7
    front_leg_y = 185 - max(0.0, -stride) * 7 + bob
    rear_arm_y = 135 - stride * 3 + bob
    front_arm_y = 136 + stride * 3 + bob
    tag_dx = lift * 1.5

    poly(draw, [(65, 144 + bob), (48, 151 + bob), (63, 160 + bob)], fill=WHITE)

    rr(draw, (68, 86 + bob, 126, 188 + bob), radius=28, fill=WHITE, outline=OUTLINE, width=3)
    rr(draw, (64, 18 + bob, 152, 82 + bob), radius=28, fill=WHITE, outline=OUTLINE, width=3)
    ell(draw, (136, 29 + bob, 176, 70 + bob), fill=OUTLINE, outline=OUTLINE, width=1)
    ell(draw, (84, 21 + bob, 108, 54 + bob), fill=WHITE, outline=OUTLINE, width=3)
    draw_eye_side(draw, (103, 27 + bob), blink=0.05 if phase not in {3, 7} else 0.5, brow=0.5)

    rr(draw, (77, 77 + bob, 118, 93 + bob), radius=8, fill=COLLAR, outline=OUTLINE, width=2)
    ell(draw, (95 + tag_dx, 93 + bob, 107 + tag_dx, 107 + bob), fill=TAG, outline=OUTLINE, width=2)

    thick_curve(draw, (86, 152 + bob), (82, 169 + bob), (rear_leg_x, rear_leg_y), width=10, paw=8)
    thick_curve(draw, (111, 152 + bob), (116, 168 + bob), (front_leg_x, front_leg_y), width=10, paw=8)
    thick_curve(draw, (88, 108 + bob), (94, 124 + bob), (96, rear_arm_y), width=9, paw=6)
    thick_curve(draw, (115, 108 + bob), (123, 124 + bob), (126, front_arm_y), width=9, paw=6)

    draw.line((124, int(87 + bob), 137, int(86 + bob)), fill=OUTLINE, width=2)
    draw.line((119, int(93 + bob), 130, int(93 + bob)), fill=OUTLINE, width=2)

    return image


def idle_frames() -> list[Image.Image]:
    poses = [
        FrontPose(bob=0, blink=0.0, expression="flat", look_x=0.0, brow=0.0, tag_dx=-1),
        FrontPose(bob=1, blink=0.0, expression="flat", look_x=0.6, brow=0.2, tag_dx=0),
        FrontPose(bob=0, blink=0.25, expression="flat", look_x=0.4, brow=0.2, tag_dx=1),
        FrontPose(bob=-1, blink=0.95, expression="flat", look_x=0.0, brow=1.0, tag_dx=1),
        FrontPose(bob=0, blink=0.35, expression="flat", look_x=-0.3, brow=0.4, tag_dx=0),
        FrontPose(bob=1, blink=0.0, expression="smirk", look_x=0.0, brow=0.2, tag_dx=-1),
    ]
    return [draw_front_frame(pose) for pose in poses]


def waving_frames() -> list[Image.Image]:
    poses = [
        FrontPose(expression="smirk", right_arm=(124, 130), left_arm=(68, 139), look_x=0.8, brow=-0.3),
        FrontPose(expression="smirk", right_arm=(134, 108), left_arm=(68, 139), look_x=1.1, brow=-0.8, tag_dx=1),
        FrontPose(expression="open", right_arm=(138, 96), left_arm=(68, 139), look_x=1.3, brow=-1.0, tag_dx=1),
        FrontPose(expression="smirk", right_arm=(130, 118), left_arm=(68, 139), look_x=0.8, brow=-0.3),
    ]
    return [draw_front_frame(pose) for pose in poses]


def jumping_frames() -> list[Image.Image]:
    poses = [
        FrontPose(bob=2, expression="flat", left_arm=(70, 138), right_arm=(122, 138), left_leg=(79, 188), right_leg=(113, 188)),
        FrontPose(bob=-4, expression="smirk", left_arm=(66, 132), right_arm=(126, 132), left_leg=(78, 181), right_leg=(114, 181), tag_dx=-1),
        FrontPose(bob=-11, expression="open", left_arm=(63, 127), right_arm=(129, 127), left_leg=(78, 173), right_leg=(114, 173), brow=-0.8, tag_dx=1),
        FrontPose(bob=-5, expression="smirk", left_arm=(66, 131), right_arm=(126, 131), left_leg=(78, 179), right_leg=(114, 179), tag_dx=1),
        FrontPose(bob=1, expression="flat", left_arm=(69, 137), right_arm=(123, 137), left_leg=(79, 187), right_leg=(113, 187)),
    ]
    return [draw_front_frame(pose) for pose in poses]


def failed_frames() -> list[Image.Image]:
    poses = []
    for index in range(8):
        bob = 1 + abs(3.5 - index) * 0.5
        blink = 0.35 if index not in {2, 5} else 0.75
        poses.append(
            FrontPose(
                bob=bob,
                blink=blink,
                expression="frown",
                look_x=0.0,
                brow=1.6,
                ear_left_drop=7.0,
                ear_right_drop=8.0,
                left_arm=(68, 145),
                right_arm=(124, 145),
                left_leg=(80, 190),
                right_leg=(112, 190),
            )
        )
    return [draw_front_frame(pose) for pose in poses]


def waiting_frames() -> list[Image.Image]:
    poses = [
        FrontPose(expression="flat", look_x=0.5, look_y=-1.3, brow=-0.6, right_arm=(122, 132), left_arm=(69, 137), tag_dx=-1),
        FrontPose(expression="flat", look_x=0.9, look_y=-1.4, brow=-0.8, right_arm=(124, 130), left_arm=(69, 136), tag_dx=0),
        FrontPose(expression="smirk", look_x=1.2, look_y=-1.5, brow=-1.0, right_arm=(126, 128), left_arm=(69, 135), tag_dx=1),
        FrontPose(expression="smirk", look_x=1.0, look_y=-1.2, brow=-0.8, right_arm=(124, 129), left_arm=(69, 136), tag_dx=1),
        FrontPose(expression="flat", look_x=0.6, look_y=-0.8, brow=-0.6, right_arm=(123, 131), left_arm=(69, 137), tag_dx=0),
        FrontPose(expression="flat", look_x=0.4, look_y=-1.0, brow=-0.5, right_arm=(122, 132), left_arm=(69, 137), tag_dx=-1),
    ]
    return [draw_front_frame(pose) for pose in poses]


def running_frames() -> list[Image.Image]:
    poses = [
        FrontPose(expression="smirk", look_x=0.8, brow=0.6, left_arm=(70, 131), right_arm=(124, 138), tag_dx=-1),
        FrontPose(expression="smirk", look_x=1.0, brow=0.4, left_arm=(68, 138), right_arm=(126, 129), tag_dx=0),
        FrontPose(expression="smirk", look_x=0.9, brow=0.5, left_arm=(71, 130), right_arm=(124, 139), tag_dx=1),
        FrontPose(expression="smirk", look_x=0.6, brow=0.2, left_arm=(68, 139), right_arm=(126, 129), tag_dx=1),
        FrontPose(expression="smirk", look_x=0.8, brow=0.5, left_arm=(70, 131), right_arm=(124, 138), tag_dx=0),
        FrontPose(expression="smirk", look_x=0.7, brow=0.4, left_arm=(68, 138), right_arm=(126, 130), tag_dx=-1),
    ]
    return [draw_front_frame(pose) for pose in poses]


def review_frames() -> list[Image.Image]:
    poses = [
        FrontPose(expression="flat", look_x=1.3, brow=1.0, left_arm=(75, 136), right_arm=(118, 130), body_dx=1),
        FrontPose(expression="flat", look_x=1.5, brow=1.2, left_arm=(75, 136), right_arm=(116, 126), body_dx=1, tag_dx=1),
        FrontPose(expression="smirk", look_x=1.6, brow=1.4, left_arm=(75, 136), right_arm=(115, 123), body_dx=1, tag_dx=1),
        FrontPose(expression="flat", blink=0.85, look_x=1.4, brow=1.6, left_arm=(75, 136), right_arm=(116, 126), body_dx=1, tag_dx=1),
        FrontPose(expression="flat", look_x=1.1, brow=1.1, left_arm=(75, 136), right_arm=(118, 130), body_dx=1, tag_dx=0),
        FrontPose(expression="smirk", look_x=1.2, brow=1.0, left_arm=(75, 136), right_arm=(118, 130), body_dx=1, tag_dx=-1),
    ]
    return [draw_front_frame(pose) for pose in poses]


def running_side_frames(direction: int) -> list[Image.Image]:
    frames = [draw_side_frame(index) for index in range(8)]
    if direction < 0:
        return [frame.transpose(Image.Transpose.FLIP_LEFT_RIGHT) for frame in frames]
    return frames


def all_frames() -> dict[str, list[Image.Image]]:
    frames = {
        "idle": idle_frames(),
        "running-right": running_side_frames(1),
        "running-left": running_side_frames(-1),
        "waving": waving_frames(),
        "jumping": jumping_frames(),
        "failed": failed_frames(),
        "waiting": waiting_frames(),
        "running": running_frames(),
        "review": review_frames(),
    }
    for state, expected in ROW_COUNTS.items():
        got = len(frames[state])
        if got != expected:
            raise ValueError(f"{state} expected {expected} frames, got {got}")
    return frames


def save_frames(run_dir: Path) -> Path:
    frames_root = run_dir / "frames"
    for state, frames in all_frames().items():
        state_dir = frames_root / state
        state_dir.mkdir(parents=True, exist_ok=True)
        for index, frame in enumerate(frames):
            frame.save(state_dir / f"{index:02d}.png")
    return frames_root


def write_request(run_dir: Path) -> None:
    payload = {
        "pet_id": PET_ID,
        "display_name": DISPLAY_NAME,
        "description": DESCRIPTION,
        "style_preset": "flat-vector",
        "style_notes": "Family Guy Brian reference matched as closely as possible in a readable Codex pet atlas.",
        "pet_notes": (
            "Large rounded white dog head, half-lidded eyes, huge black oval nose, red collar, "
            "gold tag, simple black outline, Brian proportions."
        ),
        "output_format": {
            "cell_width": CELL_W,
            "cell_height": CELL_H,
            "columns": 8,
            "rows": 9,
        },
    }
    (run_dir / "pet_request.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    run_dir = Path("output/pets/brian-run").resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    save_frames(run_dir)
    write_request(run_dir)
    print(f"wrote handcrafted frames to {run_dir}")


if __name__ == "__main__":
    main()
