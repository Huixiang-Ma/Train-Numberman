"""工单20 §一 · 17 个典型场景回归

工单编号：人工智能CV-AIGC-20-文旅Agent任务工单-功能集成测试与部署

这个脚本回答一个问题：**17 个场景，现在哪些真的能跑通。**

三条如实原则：
  1. **不伪造输入**。图像场景用程序生成的合成图（几何图形），不拿真实照片冒充；
     音频场景用生成的静音/正弦波 WAV，只验证"链路能通、不 500"，
     因此 ASR 结果为空的场景会被标成 `degraded` 而不是 `pass` ——
     合成音频不等于真人提问，把两者等同就是自欺。
  2. **区分 pass / degraded / fail**。模型未加载、云端额度不足导致的降级
     与真正的功能缺陷是两回事，混在一起会让回归结果失去意义。
  3. **记录耗时**。AIGC 图像/视频是秒级到十秒级操作，耗时本身就是验收指标之一。

用法：
    python scripts/scenario_regression.py            # 全部场景
    python scripts/scenario_regression.py 1 3 13     # 只跑指定编号
"""
from __future__ import annotations

import io
import json
import sys
import time
import wave
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = "http://127.0.0.1:8100/api/v1"
TOKEN = ""

# 结果标记
PASS = "pass"
DEGRADED = "degraded"   # 链路可用，但输入或能力不完整（合成媒体、异步未等待、已登记缺口）
BLOCKED = "blocked"     # 外部依赖不可用（额度/鉴权/限流/超时）—— 不是产品缺陷
FAIL = "fail"
SKIP = "skip"

RESET = "\033[0m"
COLOR = {PASS: "\033[32m", DEGRADED: "\033[33m", BLOCKED: "\033[36m", FAIL: "\033[31m", SKIP: "\033[90m"}

# 上游不可用时的可读关键词。后端按 _upstream_error 约定返回 503/504 + 这些措辞，
# 探针据此把"外部依赖挂了"与"功能真的坏了"区分开 —— 混为一谈会让人去改正确的代码。
BLOCKED_HINTS = ("额度不足", "鉴权失败", "请求过于频繁", "响应超时")


def synthetic_image(size: int = 384, kind: str = "arch") -> bytes:
    """生成合成图：几何色块 + 文字。

    刻意**不用**真实照片：合成图只用于验证"链路是否通畅、是否 500"，
    不能用它的识别结果去评价模型准确率。kind 只影响画面构图，便于区分场景。
    """
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (size, size), (240, 236, 226))
    draw = ImageDraw.Draw(image)
    if kind == "arch":
        # 近似"建筑"：屋顶三角 + 柱体 + 台基
        draw.polygon([(60, 150), (192, 60), (324, 150)], fill=(120, 90, 70))
        for x in (95, 160, 225, 290):
            draw.rectangle([x, 150, x + 22, 300], fill=(150, 118, 92))
        draw.rectangle([50, 300, 334, 322], fill=(96, 74, 58))
    elif kind == "stele":
        # 近似"碑刻"：竖石 + 横向刻痕
        draw.rectangle([130, 70, 254, 320], fill=(88, 86, 82))
        for y in range(100, 300, 26):
            draw.rectangle([150, y, 234, y + 10], fill=(196, 194, 188))
    elif kind == "portrait":
        # 近似"人像"：头部 + 肩部
        draw.ellipse([120, 70, 264, 214], fill=(196, 158, 128))
        draw.rectangle([80, 214, 304, 340], fill=(70, 92, 118))
    elif kind == "plants":
        draw.rectangle([0, 300, size, size], fill=(96, 122, 74))
        for cx, cy, r in ((140, 250, 52), (240, 220, 62), (190, 280, 40)):
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(74, 122, 66))
    elif kind == "mural":
        draw.rectangle([40, 60, 344, 320], fill=(186, 152, 106))
        for i, color in enumerate(((140, 70, 60), (70, 100, 130), (170, 130, 60))):
            draw.ellipse([70 + i * 90, 130, 130 + i * 90, 250], fill=color)
    else:
        draw.rectangle([80, 80, 304, 304], fill=(150, 150, 150))

    draw.text((12, 8), f"SYNTHETIC/{kind}", fill=(30, 30, 30))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88)
    return buffer.getvalue()


def synthetic_wav(seconds: float = 1.2, sample_rate: int = 16000) -> bytes:
    """生成一段正弦波 WAV。

    只用来验证多模态接口能吃下音频、不抛 500；ASR 转出空文本是**预期**结果，
    因为正弦波不是语音。凡依赖 ASR 内容的场景会因此标为 degraded。
    """
    import math
    import struct

    frames = bytearray()
    total = int(sample_rate * seconds)
    for index in range(total):
        # 220Hz 正弦 + 淡入淡出，避免首尾爆音干扰解码
        envelope = min(1.0, index / 400, (total - index) / 400)
        value = int(12000 * envelope * math.sin(2 * math.pi * 220 * index / sample_rate))
        frames += struct.pack("<h", value)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(bytes(frames))
    return buffer.getvalue()


def call(method: str, path: str, auth: bool = False, **kwargs):
    headers = dict(kwargs.pop("headers", {}))
    if auth:
        headers["Authorization"] = f"Bearer {TOKEN}"
    started = time.perf_counter()
    try:
        response = httpx.request(method, BASE + path, timeout=180, headers=headers, **kwargs)
        elapsed = int((time.perf_counter() - started) * 1000)
    except Exception as exc:
        return 0, None, f"{type(exc).__name__}: {exc}", int((time.perf_counter() - started) * 1000)
    try:
        body = response.json()
    except Exception:
        body = None
    detail = ""
    if response.status_code >= 400:
        detail = str((body or {}).get("detail") or (body or {}).get("message") or response.text[:160])
    return response.status_code, (body or {}).get("data"), detail, elapsed


def _first_park() -> str:
    _, data, _, _ = call("GET", "/park?limit=1")
    items = (data or {}).get("items") or []
    return items[0]["id"] if items else ""


def _first_attraction_name() -> str:
    park_id = _first_park()
    if not park_id:
        return ""
    _, data, _, _ = call("GET", f"/park/{park_id}")
    attractions = (data or {}).get("attractions") or []
    return attractions[0]["name"] if attractions else ""


def verdict(ok: bool, degraded: bool = False) -> str:
    if ok and degraded:
        return DEGRADED
    return PASS if ok else FAIL


def blocked(status: int, detail: str) -> bool:
    """响应是否为"外部依赖不可用"。"""
    return status in (503, 504) and any(hint in detail for hint in BLOCKED_HINTS)


# --------------------------------------------------------------------------
# 17 个场景。每个返回 (标记, 说明)
# --------------------------------------------------------------------------

def s01() -> tuple[str, str]:
    """拍古建筑 → 识别 + 讲历史与建筑风格（图像分类·目标检测·RAG·TTS）"""
    status, data, detail, ms = call(
        "POST",
        "/perception/analyze",
        # 字段名是 frame（不是 image）；分类与 OCR 需要显式开关，默认关闭
        files={"frame": ("arch.jpg", synthetic_image(kind="arch"), "image/jpeg")},
        data={"with_classify": "true"},
    )
    if status != 200:
        return FAIL, f"感知接口 {status} {detail}"
    detections = (data or {}).get("detections") or []
    classes = (data or {}).get("classification") or []
    _, answer, answer_detail, _ = call("POST", "/query", json={"query": f"介绍{_first_attraction_name() or '古建筑'}的历史与建筑风格"})
    return (
        verdict(bool(detections or classes) and not answer_detail),
        f"检测 {len(detections)} / 分类 {len(classes)} 目标，讲解 {len((answer or {}).get('answer_text') or '')} 字，{ms}ms",
    )


def s02() -> tuple[str, str]:
    """语音问"必打卡景点" → 语音答复 + 推荐路线（ASR·NLP·路径规划·TTS）"""
    status, data, detail, ms = call(
        "POST",
        "/dialog/multimodal",
        files={"audio": ("tone.wav", synthetic_wav(), "audio/wav")},
        data={"text": "有哪些必打卡的景点", "with_avatar": "true", "with_perception": "false"},
    )
    if status != 200:
        return FAIL, f"对话接口 {status} {detail}"
    asr = (data or {}).get("asr_text")
    has_avatar = bool((data or {}).get("avatar"))
    # 合成正弦波的 ASR 结果必然为空，因此标 degraded 而不是假装通过
    return (
        verdict(bool((data or {}).get("answer_text")) and has_avatar, degraded=not asr),
        f"ASR {'有文本' if asr else '空（合成音频，预期）'}，数字人驱动 {'有' if has_avatar else '无'}，{ms}ms",
    )


def s03() -> tuple[str, str]:
    """上传碑刻 → OCR 识碑文 + 讲文化内涵（OCR·RAG·TTS）"""
    status, data, detail, ms = call(
        "POST",
        "/perception/analyze",
        # OCR 默认关闭，必须显式打开，否则 ocr_text 恒为空 —— 这会让"OCR 不可用"
        # 与"没开开关"两种情况看起来一模一样
        files={"frame": ("stele.jpg", synthetic_image(kind="stele"), "image/jpeg")},
        data={"with_ocr": "true"},
    )
    if status != 200:
        return FAIL, f"感知接口 {status} {detail}"
    ocr = (data or {}).get("ocr_text")
    # 合成图上只有 "SYNTHETIC/stele" 这行拉丁文字，中文碑文识别无从验证
    return verdict(True, degraded=not ocr), f"OCR {'命中' if ocr else '未命中（合成图无声碑文，预期）'}，{ms}ms"


def s04() -> tuple[str, str]:
    """景区内挥手 → 数字人主动问候 + 推荐附近活动（目标检测·手势识别·活动推荐）"""
    status, data, detail, ms = call("POST", "/avatar/greet", json={"gesture": "wave"})
    if status != 200:
        return FAIL, f"问候接口 {status} {detail}"
    status2, data2, detail2, _ = call("POST", "/activity/recommend", json={"interests": ["亲子"], "limit": 3})
    if status2 != 200:
        return FAIL, f"活动推荐 {status2} {detail2}"
    items = (data2 or {}).get("items") or []
    return verdict(bool((data or {}).get("text")), degraded=not items), f"问候语 {len((data or {}).get('text') or '')} 字，推荐 {len(items)} 项，{ms}ms"


def s05() -> tuple[str, str]:
    """输入"喜欢自然风光和摄影" → 摄影线路 + 拍照点（NLP·路径规划·兴趣画像）"""
    status, data, detail, ms = call(
        "POST", "/itinerary/plan", json={"interests": ["自然风光", "摄影"], "theme": "摄影", "duration": "半天"}
    )
    if status != 200:
        return FAIL, f"行程接口 {status} {detail}"
    stops = (data or {}).get("stops") or []
    return verdict(bool(stops)), f"{len(stops)} 个站点，{ms}ms"


def s06() -> tuple[str, str]:
    """上传合影 → 风格化纪念照 + 明信片（图像分割·风格迁移·模板生成）"""
    status, data, detail, ms = call(
        "POST",
        "/create/image",
        # 字段名是 files（复数）；kind 决定艺术化/明信片/虚拟合影，默认 artistic
        files={"files": ("portrait.jpg", synthetic_image(kind="portrait"), "image/jpeg")},
        data={"kind": "artistic", "style": "ink", "title": "回归纪念照", "background": "false"},
    )
    if status != 200:
        # 上游额度/鉴权问题属外部依赖不可用，不是功能缺陷
        return (BLOCKED if blocked(status, detail) else FAIL), f"图像生成 {status} {detail}"
    # 异步时返回 task，不阻塞等待（AIGC 图像实测 30~40s，轮询会拖长回归时间）
    if (data or {}).get("task_id"):
        return DEGRADED, f"已受理异步任务 {(data or {}).get('task_id')}，{ms}ms（未等待完成）"
    return verdict(bool((data or {}).get("url"))), f"产物 {(data or {}).get('id')}，{ms}ms"


def s07() -> tuple[str, str]:
    """上传短视频 → 分析内容 + 生成配音讲解（视频帧抽取·目标检测·TTS·视频合成）"""
    return SKIP, "需真实短视频样本；且工单20 场景7 的「逐帧分析后自动配解说」是本项目已登记的缺口①"


def s08() -> tuple[str, str]:
    """语音问"这雕像是谁" + 照片 → 识别 + 讲人物故事（ASR·图像识别·RAG·TTS）"""
    status, data, detail, ms = call(
        "POST",
        "/dialog/multimodal",
        files={"image": ("portrait.jpg", synthetic_image(kind="portrait"), "image/jpeg")},
        data={"text": "这雕像是谁", "with_avatar": "true", "with_perception": "true"},
    )
    if status != 200:
        return FAIL, f"多模态对话 {status} {detail}"
    perception = (data or {}).get("perception") or {}
    return verdict(bool((data or {}).get("answer_text"))), f"检测 {len(perception.get('detections') or [])} 个目标，{ms}ms"


def s09() -> tuple[str, str]:
    """上传动植物照片 → 识别物种 + 讲生态知识（图像分类·RAG·TTS）"""
    status, data, detail, ms = call(
        "POST",
        "/perception/analyze",
        files={"frame": ("plants.jpg", synthetic_image(kind="plants"), "image/jpeg")},
        data={"with_classify": "true"},
    )
    if status != 200:
        return FAIL, f"感知接口 {status} {detail}"
    classes = (data or {}).get("classification") or []
    return verdict(True, degraded=not classes), f"分类 {len(classes)} 项，{ms}ms"


def s10() -> tuple[str, str]:
    """生成"我的旅行日记" → 相册/短片 + 解说词 + 音乐（多模态整合·视频合成·TTS）"""
    status, data, detail, ms = call(
        "POST", "/create/diary", json={"title": "苏州两日", "tone": "抒情", "place": "苏州", "highlights": ["拙政园", "平江路"]}
    )
    if status != 200:
        return FAIL, f"日记接口 {status} {detail}"
    text = (data or {}).get("text_content") or ""
    return verdict(bool(text)), f"解说词 {len(text)} 字，{ms}ms（配乐属已登记缺口③）"


def s11() -> tuple[str, str]:
    """语音问"附近特色美食" → 定位检索 + 美食攻略（ASR·地理定位·MCP·内容生成）"""
    status, data, detail, ms = call(
        "POST", "/activity/recommend", json={"keyword": "美食", "latitude": 31.32, "longitude": 120.62, "radius_m": 8000, "limit": 5}
    )
    if status != 200:
        return FAIL, f"活动推荐 {status} {detail}"
    items = (data or {}).get("items") or []
    return verdict(True, degraded=not items), f"命中 {len(items)} 项，geo={'有' if (data or {}).get('has_geo') else '无'}，{ms}ms"


def s12() -> tuple[str, str]:
    """上传活动照片 → 活动回顾 PPT + 流程图（图像分析·文档生成·流程图生成）"""
    files = [
        ("files", ("a1.jpg", synthetic_image(kind="arch"), "image/jpeg")),
        ("files", ("a2.jpg", synthetic_image(kind="mural"), "image/jpeg")),
    ]
    status, data, detail, ms = call("POST", "/create/ppt", files=files, data={"title": "活动回顾", "subtitle": "回归测试"})
    if status != 200:
        return (BLOCKED if blocked(status, detail) else FAIL), f"PPT 生成 {status} {detail}"
    mime = (data or {}).get("mime") or ""

    # 攻略生成必须走**文档化的流程**：先用活动推荐拿到真实活动，再用它的 id 生成攻略。
    # 第一版探针直接编了一个活动名，接口返回 404 是正确行为（它按名字查库），
    # 但那样测的是"不存在的活动"，等于没测到这个场景。
    _, rec, rec_detail, _ = call("POST", "/activity/recommend", json={"limit": 1})
    items = (rec or {}).get("items") or []
    if not items:
        return DEGRADED, f"PPT {mime} 已生成；活动库为空，攻略流程未覆盖"
    activity = items[0]
    status2, data2, detail2, _ = call(
        "POST", "/create/guide", json={"activity_id": activity["id"], "activity_name": activity["name"]}
    )
    if status2 != 200:
        return FAIL, f"流程图生成 {status2} {detail2}"
    steps = (data2 or {}).get("steps") or []
    return (
        verdict("presentation" in mime and bool(steps)),
        f"PPT {mime}，活动「{activity['name']}」流程 {len(steps)} 步，{ms}ms",
    )


def s13() -> tuple[str, str]:
    """生成"导览地图" → 个性化地图可下载打印（路径规划·地图生成）"""
    park_id = _first_park()
    _, detail_data, _, _ = call("GET", f"/park/{park_id}")
    names = [item["name"] for item in ((detail_data or {}).get("attractions") or [])][:4]
    if len(names) < 2:
        return SKIP, "景区景点不足 2 个，无法生成线路"
    status, data, detail, ms = call(
        "POST", "/create/map", json={"title": "回归线路", "subtitle": "自动生成", "stops": [{"name": n, "index": i + 1} for i, n in enumerate(names)]}
    )
    if status != 200:
        return FAIL, f"地图生成 {status} {detail}"
    return verdict(bool((data or {}).get("url"))), f"{len(names)} 站，产物 {(data or {}).get('id')}，{ms}ms"


def s14() -> tuple[str, str]:
    """语音问"壁画讲什么故事" + 图片 → 识别 + 讲解（ASR·图像识别·RAG·TTS）"""
    status, data, detail, ms = call(
        "POST",
        "/dialog/multimodal",
        files={
            "image": ("mural.jpg", synthetic_image(kind="mural"), "image/jpeg"),
            "audio": ("tone.wav", synthetic_wav(), "audio/wav"),
        },
        data={"with_avatar": "true", "with_perception": "false"},
    )
    if status != 200:
        return FAIL, f"多模态对话 {status} {detail}"
    asr = (data or {}).get("asr_text")
    return verdict(bool((data or {}).get("answer_text")), degraded=not asr), f"ASR {'有文本' if asr else '空（合成音频，预期）'}，{ms}ms"


def s15() -> tuple[str, str]:
    """表情识别判断情绪 → 调整讲解风格（表情识别·情感计算·TTS）"""
    status, data, detail, ms = call(
        "POST", "/perception/analyze", files={"frame": ("face.jpg", synthetic_image(kind="portrait"), "image/jpeg")}
    )
    if status != 200:
        return FAIL, f"感知接口 {status} {detail}"
    expression = (data or {}).get("expression")
    # 合成几何图形没有真实人脸，MediaPipe 必然识别不到表情
    return (
        verdict(True, degraded=expression is None),
        f"表情 {'命中 ' + str(expression.get('name')) if expression else '未命中（合成图无人脸，预期）'}；"
        f"风格切换属已登记缺口②，{ms}ms",
    )


def s16() -> tuple[str, str]:
    """上传多张照片 → 旅行主题短视频 + 配乐（图片处理·视频合成·音乐生成）"""
    files = [
        ("files", ("p1.jpg", synthetic_image(kind="arch"), "image/jpeg")),
        ("files", ("p2.jpg", synthetic_image(kind="plants"), "image/jpeg")),
        ("files", ("p3.jpg", synthetic_image(kind="mural"), "image/jpeg")),
    ]
    # /create/video 只接受 title / captions / seconds_per_image / watermark /
    # with_narration / background —— 多传的字段会被 FastAPI 静默忽略，
    # 因此在探针里也严格按真实签名传，避免"以为传了其实没生效"。
    status, data, detail, ms = call(
        "POST",
        "/create/video",
        files=files,
        data={"title": "旅行短片", "with_narration": "true", "background": "false"},
    )
    if status != 200:
        return (BLOCKED if blocked(status, detail) else FAIL), f"视频生成 {status} {detail}"
    if (data or {}).get("task_id"):
        return DEGRADED, f"已受理异步任务 {(data or {}).get('task_id')}，{ms}ms（配乐属已登记缺口③）"
    return verdict(bool((data or {}).get("url"))), f"产物 {(data or {}).get('id')}，{ms}ms"


def s17() -> tuple[str, str]:
    """语音问"适合老人的休闲路线" → 适老化方案（ASR·NLP·兴趣画像·路径规划）"""
    status, data, detail, ms = call(
        "POST",
        "/itinerary/plan",
        json={"interests": ["休闲", "少步行"], "theme": "适老化", "duration": "半天", "companions": "老人", "pace": "慢"},
    )
    if status != 200:
        return FAIL, f"行程接口 {status} {detail}"
    stops = (data or {}).get("stops") or []
    # 工单20 场景17 要求"适老化方案"，当前只做到把步速与同行人作为入参传给通用策划
    return verdict(bool(stops), degraded=True), f"{len(stops)} 个站点（适老化画像属已登记缺口④，{ms}ms）"


SCENARIOS = [
    ("1", "拍古建筑→识别+讲历史与建筑风格", s01),
    ("2", "语音问必打卡→语音答复+推荐路线", s02),
    ("3", "上传碑刻→OCR 识碑文+讲文化内涵", s03),
    ("4", "景区内挥手→数字人问候+推荐附近活动", s04),
    ("5", "兴趣→摄影线路+拍照点", s05),
    ("6", "上传合影→风格化纪念照+明信片", s06),
    ("7", "上传短视频→分析内容+配音讲解", s07),
    ("8", "语音问「这雕像是谁」+照片→识别+讲人物故事", s08),
    ("9", "上传动植物照片→识别物种+讲生态知识", s09),
    ("10", "生成旅行日记→相册/短片+解说词+音乐", s10),
    ("11", "语音问附近美食→定位检索+美食攻略", s11),
    ("12", "上传活动照片→活动回顾 PPT+流程图", s12),
    ("13", "生成导览地图→个性化地图可下载打印", s13),
    ("14", "语音问壁画讲什么故事+图片→识别+讲解", s14),
    ("15", "表情识别→调整讲解风格", s15),
    ("16", "多张照片→旅行主题短视频+配乐", s16),
    ("17", "语音问适合老人的休闲路线→适老化方案", s17),
]


def main() -> None:
    global TOKEN
    only = set(sys.argv[1:])

    response = httpx.post(
        f"{BASE}/auth/token",
        data={"username": "admin", "password": "wenlv_admin_pass", "grant_type": "password"},
        timeout=60,
    )
    TOKEN = (response.json().get("data") or {}).get("access_token", "")
    print(f"令牌：{'已获取' if TOKEN else '获取失败（受影响场景会返回 401）'}")
    print(f"景区：{_first_park() or '库中无景区'}")
    print("=" * 78)

    tally = {PASS: 0, DEGRADED: 0, BLOCKED: 0, FAIL: 0, SKIP: 0}
    results: list[dict] = []

    for number, title, probe in SCENARIOS:
        if only and number not in only:
            continue
        try:
            mark, note = probe()
        except Exception as exc:
            mark, note = FAIL, f"探针异常 {type(exc).__name__}: {exc}"
        tally[mark] = tally.get(mark, 0) + 1
        results.append({"scene": number, "title": title, "verdict": mark, "note": note})
        print(f"{COLOR[mark]}{mark.upper():<9}{RESET} 场景{number:>2}  {title}")
        print(f"          {note}")

    print("=" * 78)
    print(
        f"通过 {tally[PASS]} · 降级 {tally[DEGRADED]} · 外部不可用 {tally[BLOCKED]} · "
        f"失败 {tally[FAIL]} · 跳过 {tally[SKIP]}"
    )
    print()
    print("说明：")
    print("  · 降级 = 链路可用但输入或能力不完整（合成图/合成音频、异步未等待、已登记缺口）")
    print("  · 外部不可用 = 上游通道额度/鉴权/限流/超时，后端返回 503/504 与可读原因，**不是产品缺陷**")
    print("  · 跳过 = 缺少必要样本（如真实短视频），不是功能不可用")
    print("  · 本回归使用合成媒体，只验证链路完整性，**不能**用于评价模型准确率")

    out = Path(__file__).resolve().parents[1] / "scripts" / "scenario_regression_result.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果已写入 {out}")


if __name__ == "__main__":
    main()
