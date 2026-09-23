"""工单18 · 数字人形象资产预处理

工单编号：人工智能CV-AIGC-18-文旅Agent任务工单-智能导览与互动体验

职责：
  1) 形象去背景：主选 SAM 2（models/sam2.1_t.pt）多点提示分割出完整人物；
     备选 keying（纯白影棚底的连通域抠图）、rembg（分割模型）；
  2) 关键点定位并输出归一化坐标 JSON，供前端 2.5D 驱动：
       - face：MediaPipe FaceLandmarker → 嘴部、眼睛（眨眼用）、头部
       - hands：MediaPipe HandLandmarker → 双手位置（肢体动作骨骼用）
       - shoulders / neck：由面部几何推算的骨骼枢轴

用法：
  python scripts/prepare_avatar.py --id qingci                 # 默认 SAM 2
  python scripts/prepare_avatar.py --id qingci --method keying # 纯白底素材
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image, ImageFilter  # noqa: E402

AVATAR_DIR = ROOT.parent / "frontend" / "public" / "avatar"
MODEL_DIR = ROOT.parent / "models"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

# --- MediaPipe FaceMesh 关键点索引 ---
LM_FOREHEAD = 10
LM_CHIN = 152
LM_CHEEK_LEFT = 234
LM_CHEEK_RIGHT = 454
LM_UPPER_LIP = 13
LM_LOWER_LIP = 14
LM_MOUTH_LEFT = 61
LM_MOUTH_RIGHT = 291
# 眼睛轮廓：外角 / 内角 / 上睑 / 下睑
EYE_LEFT = (33, 133, 159, 145)
EYE_RIGHT = (362, 263, 386, 374)

# SAM 2 多点提示（归一化坐标，1=人物，0=背景）
SAM_POSITIVE = [
    (0.500, 0.130),
    (0.500, 0.488),
    (0.480, 0.700),
    (0.470, 0.900),
    (0.293, 0.586),
    (0.713, 0.586),
    (0.200, 0.720),
    (0.800, 0.720),
]
SAM_NEGATIVE = [(0.040, 0.030), (0.960, 0.030), (0.040, 0.970), (0.960, 0.970), (0.020, 0.300), (0.980, 0.300)]


def newest_source() -> Path:
    candidates = [p for p in AVATAR_DIR.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES and "-cutout" not in p.stem]
    if not candidates:
        raise SystemExit(f"未在 {AVATAR_DIR} 找到形象原图，请先执行 generate_avatar.py")
    return max(candidates, key=lambda p: p.stat().st_mtime)


# ==========================================================================
# 去背景
# ==========================================================================
def _sam_prompt(source: Path, width: int, height: int) -> tuple[list[list[int]], list[int]]:
    """生成 SAM 提示点：优先按人物框自适应，检不出人物时退回固定构图。

    固定提示点是按**半身像**构图写的（头顶在画面上部、躯干占满中部）。全身立绘里
    人物明显更小、更居中，同一组点会大量落到背景上，SAM 于是返回空掩码
    （"未返回掩码，请检查提示点或更换素材"）。这里直接用项目已有的 YOLO 检测器
    取人物框，再在框内按躯干比例放正点。
    """
    from app.providers.registry import get_detector

    points: list[tuple[float, float]] = list(SAM_POSITIVE)
    labels: list[int] = [1] * len(SAM_POSITIVE)
    try:
        detections = get_detector().detect(source.read_bytes(), track=False)
    except Exception as exc:  # 检测器不可用不应阻断抠图，退回固定提示点
        print(f"[cutout] YOLO 提示点生成失败（{type(exc).__name__}），改用固定提示点")
        detections = []

    people = [item for item in detections if item.label in {"person", "游客"}]
    if people:
        best = max(people, key=lambda item: item.score * item.box[2] * item.box[3])
        x, y, w, h = best.box
        points = [
            (x + w * 0.5, y + h * 0.16),  # 头/颈
            (x + w * 0.5, y + h * 0.45),  # 胸腹
            (x + w * 0.5, y + h * 0.78),  # 裙摆
            (x + w * 0.18, y + h * 0.40),  # 左袖
            (x + w * 0.82, y + h * 0.40),  # 右袖
        ]
        labels = [1] * len(points)
        print(f"[cutout] 按人物框生成提示点（置信度 {best.score:.2f}，框 {w:.2f}×{h:.2f}）")
    else:
        print("[cutout] 未检出人物，沿用固定提示点")

    points += list(SAM_NEGATIVE)
    labels += [0] * len(SAM_NEGATIVE)
    return [[round(px * width), round(py * height)] for px, py in points], labels


def cutout_by_sam(source: Path, target: Path) -> None:
    """SAM 2 多提示分割：正点落在人物躯干/头/裙摆，负点落在四角与两侧背景。"""
    import numpy as np
    from scipy import ndimage
    from ultralytics import SAM

    weight = MODEL_DIR / "sam2.1_t.pt"
    if not weight.exists():
        raise SystemExit(f"未找到 SAM 2 权重 {weight}")

    with Image.open(source) as handle:
        width, height = handle.size
        # ultralytics 走文件路径时对中文目录不友好，统一用内存数组送入
        frame = np.asarray(handle.convert("RGB"))

    points, labels = _sam_prompt(source, width, height)

    model = SAM(str(weight))
    result = model(frame, points=[points], labels=[labels], verbose=False)
    masks = result[0].masks
    if masks is None or len(masks.data) == 0:
        raise SystemExit("SAM 2 未返回掩码，请检查提示点或更换素材")

    probability = masks.data[0].cpu().numpy().astype("float32")

    # 后处理：浅色衣料与浅色背景对比度低，SAM 掩码易在衣物内部出现孔洞，
    # 需做「闭运算 → 填洞 → 取最大连通域 → 再填洞」清理，避免透明底出现斑点。
    binary = probability > 0.5
    binary = ndimage.binary_closing(binary, structure=np.ones((9, 9)))
    binary = ndimage.binary_fill_holes(binary)
    components, count = ndimage.label(binary)
    if count > 1:
        sizes = ndimage.sum(binary, components, range(1, count + 1))
        binary = components == (int(np.argmax(sizes)) + 1)
    binary = ndimage.binary_fill_holes(binary)

    # 以清理后的二值掩码约束原始概率图，保留 SAM 的软边缘，再羽化
    cleaned = probability * binary
    alpha = np.clip((cleaned - 0.35) / 0.3, 0.0, 1.0)
    alpha_image = Image.fromarray((alpha * 255).astype("uint8"), mode="L").filter(ImageFilter.GaussianBlur(0.9))

    with Image.open(source) as handle:
        output = handle.convert("RGBA")
    output.putalpha(alpha_image)
    output.save(target)
    print(f"[cutout] SAM 2 分割完成 {source.name} -> {target.name}（人物占比 {float(alpha.mean()):.3f}）")


def cutout_by_keying(source: Path, target: Path) -> None:
    """浅色影棚底连通域抠图：只去除与画面边缘相连的浅色区域。

    阈值不写死：AIGC 出图未必是纯白（近期一次出图背景为浅灰，四角 219~239），
    固定阈值会把大片背景留在画面里。改为从边框像素自适应推算「浅色」的门槛。
    """
    import numpy as np
    from scipy import ndimage

    image = Image.open(source).convert("RGB")
    array = np.asarray(image).astype(np.int16)
    height, width, _ = array.shape

    ring = max(4, min(height, width) // 64)
    # 采样区域只用四角与上沿：半身像的下沿常被人物本身（衣料）裁切占据，
    # 若把下沿算进统计，深色衣料会把阈值一路放宽到几乎不过滤。
    patch = max(8, min(height, width) // 16)
    samples = [
        array[:ring, :, :],                                              # 上沿
        array[:patch, :patch, :],                                        # 左上角
        array[:patch, -patch:, :],                                       # 右上角
        array[-patch:, :patch, :],                                       # 左下角
        array[-patch:, -patch:, :],                                      # 右下角
    ]
    border = np.concatenate([item.reshape(-1, 3) for item in samples])
    border_min = border.min(axis=1)
    border_spread = border.max(axis=1) - border_min
    # 取采样区里偏暗的一侧作为门槛（10% 分位），再留 8 级余量，兼容渐变与暗角
    white_min = int(max(180, np.percentile(border_min, 10) - 8))
    max_spread = int(max(8, np.percentile(border_spread, 95) + 4))

    minimum = array.min(axis=2)
    maximum = array.max(axis=2)
    near_white = (minimum >= white_min) & ((maximum - minimum) <= max_spread)

    labels, count = ndimage.label(near_white)
    if count == 0:
        raise SystemExit("未识别到浅色背景区域，请改用 --method sam")

    border_labels = set(labels[0, :].tolist()) | set(labels[-1, :].tolist())
    border_labels |= set(labels[:, 0].tolist()) | set(labels[:, -1].tolist())
    border_labels.discard(0)
    if not border_labels:
        raise SystemExit("浅色区域未与画面边缘相连，请改用 --method sam")

    background = np.isin(labels, sorted(border_labels))
    alpha = np.where(background, 0, 255).astype(np.uint8)

    # 自检：只看上沿与两侧上半。半身像的下沿被人物占据是正常的，
    # 把它算进残留会把正常结果误报成"没抠干净"。
    border_alpha = np.concatenate(
        [
            alpha[:ring, :].ravel(),
            alpha[ring : height // 2, :ring].ravel(),
            alpha[ring : height // 2, -ring:].ravel(),
        ]
    )
    residue = float(border_alpha.mean()) / 255.0
    alpha_image = Image.fromarray(alpha, mode="L").filter(ImageFilter.GaussianBlur(0.8))

    output = image.convert("RGBA")
    output.putalpha(alpha_image)
    output.save(target)
    print(
        f"[cutout] 浅底抠图完成 {source.name} -> {target.name}"
        f"（阈值 min>={white_min} 通道差<={max_spread}，人物占比 {1 - background.mean():.3f}，边框残留 {residue:.3f}）"
    )
    if residue > 0.08:
        print(f"[cutout] 警告：画面边框仍有 {residue:.1%} 未被扣除，背景可能没抠干净")


def cutout_by_rembg(source: Path, target: Path) -> None:
    """分割模型抠图（首次需下载 u2net 权重）。"""
    from rembg import remove

    target.write_bytes(remove(source.read_bytes()))
    print(f"[cutout] rembg 抠图完成 {source.name} -> {target.name}")


def cutout(source: Path, target: Path, method: str = "keying") -> None:
    {"sam": cutout_by_sam, "keying": cutout_by_keying, "rembg": cutout_by_rembg}[method](source, target)


# ==========================================================================
# 关键点定位
# ==========================================================================
def _face_landmarks(image_path: Path):
    """返回 (全图归一化关键点列表, 原图尺寸)。

    单张全身立绘里人脸只占画面高的一小部分：MediaPipe 会把任何输入缩放到固定尺寸，
    因此"把整图放大再检测"没有任何帮助（脸的有效像素数不变），必须**裁剪头部区域**后
    再检测，并把裁剪图内的相对坐标映射回全图。半身像走原图一次即可命中，行为不变。
    """
    import numpy as np
    import mediapipe
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    model_path = MODEL_DIR / "mediapipe" / "face_landmarker.task"
    if not model_path.exists():
        raise SystemExit(f"未找到 {model_path}")

    # MediaPipe 的 C++ 层无法打开含非 ASCII 字符的路径，改为内存缓冲加载
    options = vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_buffer=model_path.read_bytes()),
        num_faces=1,
        running_mode=vision.RunningMode.IMAGE,
        min_face_detection_confidence=0.3,
    )
    landmarker = vision.FaceLandmarker.create_from_options(options)

    image = Image.open(image_path).convert("RGB")
    width, height = image.size

    # 裁剪候选：全图 → 上 45%（含头肩）→ 上 30% 中间 70% 宽 → 上 22% 中间 45% 宽
    crops = [
        (0.0, 0.0, 1.0, 1.0),
        (0.0, 0.0, 1.0, 0.45),
        (0.15, 0.0, 0.70, 0.30),
        (0.275, 0.0, 0.45, 0.22),
    ]
    for left, top, crop_w, crop_h in crops:
        box_px = (
            int(left * width),
            int(top * height),
            int((left + crop_w) * width),
            int((top + crop_h) * height),
        )
        patch = image.crop(box_px)
        if patch.width < 64 or patch.height < 64:
            continue
        mp_image = mediapipe.Image(image_format=mediapipe.ImageFormat.SRGB, data=np.array(patch))
        result = landmarker.detect(mp_image)
        if not result.face_landmarks:
            continue
        origin_x, origin_y = box_px[0] / width, box_px[1] / height
        span_x, span_y = (box_px[2] - box_px[0]) / width, (box_px[3] - box_px[1]) / height
        return (
            [(origin_x + float(item.x) * span_x, origin_y + float(item.y) * span_y) for item in result.face_landmarks[0]],
            (width, height),
        )
    raise SystemExit("未在人像中检测到人脸，请换一张正脸清晰的形象图")


def _hand_landmarks(image_path: Path):
    import numpy as np
    import mediapipe
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    model_path = MODEL_DIR / "mediapipe" / "hand_landmarker.task"
    if not model_path.exists():
        print("[hands] 未找到 hand_landmarker.task，跳过手部关键点")
        return []

    options = vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_buffer=model_path.read_bytes()),
        num_hands=2,
        running_mode=vision.RunningMode.IMAGE,
        min_hand_detection_confidence=0.2,
    )
    landmarker = vision.HandLandmarker.create_from_options(options)

    image = Image.open(image_path).convert("RGB")
    # 与面部同理：全身立绘里的手只有几十像素，原尺寸常常检不出，放大后重试。
    # 归一化坐标与输入尺寸无关，放大不影响结果口径。
    result = None
    for scale in (1, 2, 3):
        candidate = image if scale == 1 else image.resize((image.width * scale, image.height * scale), Image.LANCZOS)
        mp_image = mediapipe.Image(image_format=mediapipe.ImageFormat.SRGB, data=np.array(candidate))
        result = landmarker.detect(mp_image)
        if result.hand_landmarks:
            break
    if result is None:
        return []

    hands = []
    for index, points in enumerate(result.hand_landmarks):
        xs = [p.x for p in points]
        ys = [p.y for p in points]
        hands.append(
            {
                "side": "left" if (sum(xs) / len(xs)) < 0.5 else "right",
                "index": index,
                "x": round(min(xs), 5),
                "y": round(min(ys), 5),
                "w": round(max(xs) - min(xs), 5),
                "h": round(max(ys) - min(ys), 5),
                "wrist": {"x": round(points[0].x, 5), "y": round(points[0].y, 5)},
                "center": {"x": round(sum(xs) / len(xs), 5), "y": round(sum(ys) / len(ys), 5)},
            }
        )
    return hands


def detect_regions(image_path: Path) -> dict:
    """输出嘴部 / 眼睛 / 头部 / 双手 / 肩颈枢轴（全部为归一化坐标）。"""
    points, (width, height) = _face_landmarks(image_path)

    def at(index: int) -> tuple[float, float]:
        item = points[index]
        return float(item[0]), float(item[1])

    def box(indices: tuple[int, ...]) -> dict:
        xs = [at(i)[0] for i in indices]
        ys = [at(i)[1] for i in indices]
        return {"x": round(min(xs), 5), "y": round(min(ys), 5), "w": round(max(xs) - min(xs), 5), "h": round(max(ys) - min(ys), 5)}

    # --- 嘴部：叠加层以唇线为中心，高度按嘴宽比例预留张开空间 ---
    mouth_left, mouth_right = at(LM_MOUTH_LEFT), at(LM_MOUTH_RIGHT)
    upper, lower = at(LM_UPPER_LIP), at(LM_LOWER_LIP)
    mouth_w = abs(mouth_right[0] - mouth_left[0])
    mouth_h = max(0.022, mouth_w * 0.45)
    mouth_x = min(mouth_left[0], mouth_right[0]) - mouth_w * 0.12
    mouth_y = (upper[1] + lower[1]) / 2 - mouth_h / 2

    # --- 眼睛：眨眼时用上睑肤色条覆盖眼球 ---
    eye_left = box(EYE_LEFT)
    eye_right = box(EYE_RIGHT)

    # --- 头部与肩颈枢轴 ---
    forehead, chin = at(LM_FOREHEAD), at(LM_CHIN)
    cheek_left, cheek_right = at(LM_CHEEK_LEFT), at(LM_CHEEK_RIGHT)
    face_height = abs(chin[1] - forehead[1])
    face_center_x = (cheek_left[0] + cheek_right[0]) / 2
    face_width = abs(cheek_right[0] - cheek_left[0])

    # 颈与肩枢轴：由颌-额距离推算，肩线约在下颌下方半个脸高处
    neck_y = chin[1] + face_height * 0.20
    shoulder_y = chin[1] + face_height * 0.52
    shoulder_dx = face_width * 0.62

    hands = _hand_landmarks(image_path)
    left_hand = next((h for h in hands if h["side"] == "left"), None)
    right_hand = next((h for h in hands if h["side"] == "right"), None)

    return {
        "image": image_path.name,
        "width": width,
        "height": height,
        "mouth": {"x": round(mouth_x, 5), "y": round(mouth_y, 5), "w": round(mouth_w * 1.24, 5), "h": round(mouth_h, 5)},
        "eyes": {"left": eye_left, "right": eye_right},
        # head 箱必须与脸部对称轴对齐。原先取 min(cheek_left, cheek_right) 作左边界、
        # 宽度却是 face_width*1.28，等于只向一侧扩了 0.28 倍脸宽，箱子中心偏离对称轴
        # 0.0328（33.5px）。而头部/眉/下脸三块骨都以 head 箱中心为对称轴，于是整套面部
        # 形变偏心，左右两侧位移不一致 —— 这是"脸部整体不协调"的根源之一。
        "head": {
            "x": round(face_center_x - face_width * 0.64, 5),
            "y": round(forehead[1], 5),
            "w": round(face_width * 1.28, 5),
            "h": round(face_height * 1.25, 5),
        },
        "neck": {"x": round(face_center_x, 5), "y": round(neck_y, 5)},
        "shoulders": {
            "left": {"x": round(face_center_x - shoulder_dx, 5), "y": round(shoulder_y, 5)},
            "right": {"x": round(face_center_x + shoulder_dx, 5), "y": round(shoulder_y, 5)},
        },
        "hands": {"left": left_hand, "right": right_hand},
        "source": "mediapipe:face-landmarker+hand-landmarker / sam2.1_t",
    }


# ==========================================================================
# 闭眼贴图
# ==========================================================================
MASK_SIDE = 0.14  # 遮罩相对眼裂的横向外扩比例
MASK_TOP = 0.30  # 上额外扩
MASK_BOTTOM = 0.45  # 下额外扩


def make_blink(closed_source: Path, cutout_path: Path, meta: dict, target: Path, search: int = 26) -> Path:
    """由「闭眼渲染图」产出眨眼贴图：RGB 为闭眼画面，alpha 为只覆盖眼裂的窄遮罩。

    这份素材此前有两个硬伤，是「闭眼幅度太大」的直接来源：
      1. 遮罩带高是眼裂的 6.1 倍（眉心到鼻梁整片被替换），一眨眼糊上一块亮色；
      2. 闭眼渲染与抠图是两次独立生成，存在数像素错位，交叉淡入时出现重影。
    所以这里做两件事：先用头部区域（排除眼裂本身，因为睁/闭内容本就不同）估计平移
    并纠正错位，再把遮罩收紧到眼裂附近。
    """
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter

    closed = Image.open(closed_source).convert("RGB")
    cutout_image = Image.open(cutout_path).convert("RGBA")
    if closed.size != cutout_image.size:
        closed = closed.resize(cutout_image.size, Image.LANCZOS)

    wide, high = cutout_image.size
    closed_rgb = np.asarray(closed).astype(np.float32)
    cutout_rgba = np.asarray(cutout_image).astype(np.float32)
    cutout_rgb = cutout_rgba[..., :3]

    def box_px(box: dict) -> tuple[int, int, int, int]:
        return (
            int(box["x"] * wide),
            int(box["y"] * high),
            int((box["x"] + box["w"]) * wide),
            int((box["y"] + box["h"]) * high),
        )

    # ---- 1) 配准：用头部区域、排除眼裂，估计使两图最接近的平移 ----
    head_x0, head_y0, head_x1, head_y1 = box_px(meta["head"])
    crop_x0, crop_y0 = max(0, head_x0 - search), max(0, head_y0 - search)
    crop_x1, crop_y1 = min(wide, head_x1 + search), min(high, head_y1 + search)

    eyes = np.zeros((high, wide), bool)
    for key in ("left", "right"):
        x0, y0, x1, y1 = box_px(meta["eyes"][key])
        margin = int((y1 - y0) * 0.9)
        eyes[max(0, y0 - margin) : y1 + margin, max(0, x0 - 6) : x1 + 6] = True

    region = np.zeros((high, wide), bool)
    region[head_y0:head_y1, head_x0:head_x1] = True
    region &= cutout_rgba[..., 3] > 200
    region &= ~eyes

    # 只在头部外扩区域内搜索；region 位于其中，故平移不会引入区域外像素
    region_crop = region[crop_y0:crop_y1, crop_x0:crop_x1]
    closed_crop = closed_rgb[crop_y0:crop_y1, crop_x0:crop_x1]
    cutout_crop = cutout_rgb[crop_y0:crop_y1, crop_x0:crop_x1]

    best_diff, best_dx, best_dy = None, 0, 0
    for dy in range(-search, search + 1):
        for dx in range(-search, search + 1):
            shifted = np.roll(np.roll(closed_crop, dy, axis=0), dx, axis=1)
            diff = float(np.abs(shifted - cutout_crop).mean(axis=2)[region_crop].mean())
            if best_diff is None or diff < best_diff:
                best_diff, best_dx, best_dy = diff, dx, dy

    aligned = np.roll(np.roll(closed_rgb, best_dy, axis=0), best_dx, axis=1)
    print(f"[blink] 配准偏移 dx={best_dx} dy={best_dy}（残差 {best_diff:.2f}/255）")

    # ---- 2) 窄遮罩：椭圆外形贴合眼睑，尺寸只比眼裂略大 ----
    mask_image = Image.new("L", (wide, high), 0)
    painter = ImageDraw.Draw(mask_image)
    for key in ("left", "right"):
        box = meta["eyes"][key]
        x0 = (box["x"] - box["w"] * MASK_SIDE) * wide
        x1 = (box["x"] + box["w"] * (1 + MASK_SIDE)) * wide
        y0 = (box["y"] - box["h"] * MASK_TOP) * high
        y1 = (box["y"] + box["h"] * (1 + MASK_BOTTOM)) * high
        painter.ellipse([x0, y0, x1, y1], fill=255)
    mask_image = mask_image.filter(ImageFilter.GaussianBlur(max(2.0, high * 0.0022)))

    alpha = np.asarray(mask_image).astype(np.float32) / 255.0
    alpha *= np.clip(cutout_rgba[..., 3] / 255.0, 0.0, 1.0)  # 不越出人物轮廓
    # 压掉羽化产生的大面积极淡值，避免整片区域被轻微改动
    alpha = np.clip((alpha - 0.08) / 0.84, 0.0, 1.0)

    output = np.zeros((high, wide, 4), dtype=np.uint8)
    output[..., :3] = np.clip(aligned, 0, 255).astype(np.uint8)
    output[..., 3] = (alpha * 255).astype(np.uint8)
    Image.fromarray(output, "RGBA").save(target)

    solid = np.asarray(mask_image) > 200
    rows = np.where(solid.any(axis=1))[0]
    band = int(rows.max() - rows.min() + 1) if len(rows) else 0
    eye_h = box_px(meta["eyes"]["left"])[3] - box_px(meta["eyes"]["left"])[1]
    print(f"[blink] 遮罩带高 {band}px / 眼裂高 {eye_h}px → {band / max(eye_h, 1):.2f} 倍（改造前 6.1 倍）")
    print(f"[blink] 闭眼贴图 -> {target}")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="数字人形象资产预处理（工单18）")
    parser.add_argument("source", nargs="?", help="AIGC 生成的形象原图路径")
    parser.add_argument("--id", default="qingci", help="数字人标识，用于输出文件名")
    parser.add_argument("--method", default="keying", choices=["keying", "sam", "rembg"], help="去背景方式")
    parser.add_argument("--skip-cutout", action="store_true", help="只重算关键点")
    parser.add_argument("--closed", help="闭眼渲染图路径，用于生成眨眼贴图")
    args = parser.parse_args()

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    source = Path(args.source) if args.source else newest_source()
    if not source.is_absolute():
        source = (Path.cwd() / source).resolve()

    cutout_path = AVATAR_DIR / f"{args.id}-cutout.png"
    if not args.skip_cutout:
        cutout(source, cutout_path, method=args.method)

    meta = detect_regions(source)
    meta["image"] = f"/avatar/{cutout_path.name}"

    if args.closed:
        closed_source = Path(args.closed)
        if not closed_source.is_absolute():
            closed_source = (Path.cwd() / closed_source).resolve()
        blink_path = AVATAR_DIR / f"{args.id}-blink.png"
        make_blink(closed_source, cutout_path, meta, blink_path)
        meta["blink_image"] = f"/avatar/{blink_path.name}"

    meta_path = AVATAR_DIR / f"{args.id}.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[meta] 关键点 -> {meta_path}")
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == "__main__":
    main()
