"""工单18 · 数字人驱动服务

工单编号：人工智能CV-AIGC-18-文旅Agent任务工单-智能导览与互动体验
职责（docs/04 §4.6）：
  1) 语音合成：CosyVoice（SiliconFlow API）；
  2) 唇形同步：输出视位（viseme）时间轴，供前端 Three.js / Live2D 驱动；
     如需像素级唇形视频，可切换 LIPSYNC_PROVIDER=musetalk 调用 GPU 服务；
  3) 表情与动作驱动：由感知到的情绪决定表情与动作参数。
"""
from __future__ import annotations

import logging
from typing import Any

from ..core.config import get_settings
from ..providers.registry import get_tts

logger = logging.getLogger("wenlv.avatar")

# 视位集合（与前端数字人口型映射一致）
# C = 通用辅音口型：中文声母多数只是舌位变化，下颌开口很小，
#     原先借用 I/E（开口 0.35/0.55）会让每个辅音都像在念元音。
VISEMES = ["sil", "A", "I", "U", "E", "O", "M", "F", "C"]
_PUNCT = set("，。！？、；：,.!?;: \n\t\r")
_VOWEL_MAP = {
    "a": "A", "o": "O", "e": "E", "i": "I", "u": "U", "v": "U",
    "b": "M", "p": "M", "m": "M", "f": "F",
}

# ---- 时长：声母短、韵母长、标点停顿 ----
CONSONANT_MS = 55
VOWEL_MS = 135
PAUSE_MS = 190

# 韵母 → 视位（按「下颌开口 + 唇形圆展」归类；长韵母需排在前面做最长匹配）
_FINAL_TO_VISEME: list[tuple[str, str]] = [
    ("iang", "A"), ("uang", "A"), ("uai", "A"), ("uan", "A"), ("iao", "A"), ("ian", "A"),
    ("iong", "O"), ("ong", "O"), ("ou", "O"), ("uo", "O"), ("o", "O"),
    ("ang", "A"), ("ai", "A"), ("ao", "A"), ("an", "A"), ("a", "A"),
    ("ia", "A"), ("ua", "A"),
    ("eng", "E"), ("ei", "E"), ("en", "E"), ("er", "E"), ("ie", "E"), ("ue", "E"), ("e", "E"),
    ("ing", "I"), ("in", "I"), ("iu", "I"), ("i", "I"),
    ("un", "U"), ("ui", "U"), ("u", "U"), ("vn", "U"), ("v", "U"), ("ü", "U"),
]

# 声母 → 视位：双唇音闭口，唇齿音下唇触齿，其余为通用辅音
_INITIAL_TO_VISEME = {
    "b": "M", "p": "M", "m": "M",
    "f": "F",
}

try:  # 声韵母切分依赖 pypinyin；缺失时退回字符哈希（旧行为）
    from pypinyin import Style as _PinyinStyle
    from pypinyin import pinyin as _pinyin
except Exception:  # pragma: no cover
    _pinyin = None
    _PinyinStyle = None


def _final_to_viseme(final: str) -> str:
    plain = (final or "").strip()
    for suffix, viseme in _FINAL_TO_VISEME:
        if plain.startswith(suffix):
            return viseme
    return "C"


def _char_to_visemes(char: str) -> list[tuple[str, int]]:
    """把一个字符拆成「声母视位 + 韵母视位」，让口型跟随真实发音而不是随机哈希。"""
    if _pinyin is not None and "\u4e00" <= char <= "\u9fff":
        initial = _pinyin(char, style=_PinyinStyle.INITIALS, strict=True)[0][0]
        final = _pinyin(char, style=_PinyinStyle.FINALS, strict=True)[0][0]
        sequence: list[tuple[str, int]] = []
        if initial:
            sequence.append((_INITIAL_TO_VISEME.get(initial, "C"), CONSONANT_MS))
        sequence.append((_final_to_viseme(final), VOWEL_MS))
        return sequence

    lowered = char.lower()
    if lowered in _VOWEL_MAP:
        viseme = _VOWEL_MAP[lowered]
        return [(viseme, CONSONANT_MS if viseme in {"M", "F"} else VOWEL_MS)]
    if char.strip():
        return [("C", VOWEL_MS)]
    return []

EXPRESSION_TO_EMOTION = {"happy": "cheerful", "curious": "curious", "tired": "gentle", "neutral": "calm"}

EMOTION_STYLE = {
    "calm": "沉稳讲解，语速适中",
    "cheerful": "活泼明快，语气上扬",
    "curious": "引导式提问，鼓励互动",
    "gentle": "温和舒缓，适当精简",
}

MOTIONS = {"idle", "wave", "nod", "point", "explain"}


class AvatarService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.tts = get_tts()

    # ---------------- 形象信息 ----------------
    def profile(self) -> dict[str, Any]:
        return {
            "avatar_id": self.settings.avatar_id,
            "name": self.settings.avatar_name,
            "type": "2d/3d",
            "engine": {"3d": "three.js", "2d": "live2d-cubism"},
            "voice": {"provider": self.tts.name, "speaking_rate": "normal"},
            "lipsync": {"provider": self.settings.lipsync_provider, "viseme_set": VISEMES},
            "emotions": list(EMOTION_STYLE.keys()),
            "motions": sorted(MOTIONS),
            "asset_note": "形象资源由 AIGC 生成，符合文旅场景（docs/04 §3.1）",
        }

    # ---------------- 唇形视位 ----------------
    @staticmethod
    def visemes(text: str) -> list[dict[str, Any]]:
        """按发音生成视位时间轴。

        中文用 pypinyin 切出声母与韵母：声母给一个很短的通用/闭口视位，
        韵母按「下颌开口 + 唇形圆展」映射到主要视位；标点插入静默停顿。

        旧实现按字符 md5 哈希随机取视位，等于让嘴毫无规律地张合（平均开口度 0.4、
        每秒数次），并不具备语言学含义；现在口型跟随真实发音。
        """
        timeline: list[dict[str, Any]] = []
        cursor = 0
        for char in text:
            if char in _PUNCT:
                timeline.append({"t": cursor, "viseme": "sil", "char": char})
                cursor += PAUSE_MS
                continue
            for viseme, duration in _char_to_visemes(char):
                timeline.append({"t": cursor, "viseme": viseme, "char": char})
                cursor += duration
        return timeline

    @staticmethod
    def viseme_duration_ms(timeline: list[dict[str, Any]]) -> int:
        if not timeline:
            return 0
        return int(timeline[-1]["t"]) + VOWEL_MS + 60

    # ---------------- 驱动 ----------------
    def drive(
        self,
        text: str,
        lang: str = "zh",
        emotion: str | None = None,
        motion: str | None = None,
    ) -> dict[str, Any]:
        """生成数字人驱动数据（语音 + 唇形视位 + 表情 + 动作）。

        语音合成不可用时**降级为无声驱动**而不是抛错：
          工单20 集成测试暴露的问题——TTS 走云端额度，额度/网络异常时异常会一路上冒，
          使 /dialog 的 respond 节点失败、整个对话返回 500。对话是核心功能，
          不能因为配音不可用就整体不可用。
          前端的 playDrive 在 audio 缺失时已退化为按视位时间轴计时播放
          （见 frontend/src/api/client.ts），因此口型与动作演示不受影响。
        """
        emotion = emotion or self.settings.avatar_emotion
        motion = motion if motion in MOTIONS else "explain"

        audio: dict[str, Any] | None = None
        degraded = ""
        try:
            payload = self.tts.synthesize(text, lang=lang)
            audio = {
                "format": payload.get("format"),
                "base64": payload.get("audio_base64"),
                "size_bytes": payload.get("size_bytes"),
                "provider": self.tts.name,
            }
        except Exception as exc:
            degraded = f"语音合成不可用（{type(exc).__name__}），本次为无声演示"
            logger.warning("语音合成失败，降级为无声驱动：%s: %s", type(exc).__name__, exc)

        timeline = self.visemes(text)
        return {
            "avatar_id": self.settings.avatar_id,
            "emotion": emotion,
            "style": EMOTION_STYLE.get(emotion, EMOTION_STYLE["calm"]),
            "motion": motion,
            "audio": audio,
            "visemes": timeline,
            "duration_ms": self.viseme_duration_ms(timeline),
            "lipsync": self.settings.lipsync_provider,
            "degraded": degraded,
        }

    # ---------------- 感知触发的主动问候 ----------------
    def greet(self, gesture: str | None = None, lang: str = "zh") -> dict[str, Any]:
        from ..providers.vision_tasks import GESTURE_ACTIONS

        plan = GESTURE_ACTIONS.get(gesture or "挥手", GESTURE_ACTIONS["挥手"])
        emotion = "cheerful" if plan["action"] == "greet" else "curious"
        return {
            "text": plan["text"],
            "gesture": gesture or "挥手",
            "drive": self.drive(plan["text"], lang=lang, emotion=emotion, motion=plan["motion"]),
        }
