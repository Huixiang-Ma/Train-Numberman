"""工单17 · 知识内容生成服务（主选 Qwen）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
链路：检索（含重排）结果 → 组装上下文 → Qwen 生成 → 内容安全校验。
"""
from __future__ import annotations

import logging
from typing import Sequence

from ..core.config import get_settings
from ..providers.base import Hit, KbChunkData
from ..providers.registry import get_llm

logger = logging.getLogger("wenlv.generation")

SYSTEM_PROMPT = (
    "你是《文旅创新智脑》的数字人讲解助手，面向景区游客。"
    "只依据给定资料作答，不得编造；资料不足时明确说明。"
    "输出使用简体中文，语气亲和、条理清晰，控制在 200 字以内。"
)

MULTILINGUAL_SYSTEM = (
    "你是专业的中文-多语言翻译，面向景区游客讲解场景。"
    "只输出译文，不要解释，不要添加任何前后缀。"
)


class GenerationService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.llm = get_llm()

    # ---------------- 上下文组装 ----------------
    @staticmethod
    def build_prompt(query: str, hits: Sequence[Hit], lang: str = "zh") -> str:
        lines = []
        for index, hit in enumerate(hits, start=1):
            chunk: KbChunkData = hit.chunk
            content = chunk.content.strip().replace("\n", " ")
            lines.append(f"[{index}] 《{chunk.title}》（来源：{chunk.source or '景区知识库'}）{content}")
        context = "\n".join(lines) or "（无检索结果）"
        return (
            f"【用户问题】{query}\n"
            f"【目标语言】{lang}\n"
            f"【参考资料】\n{context}\n\n"
            "请基于以上资料给出面向游客的讲解，并在结尾用「资料来源：」列出引用的资料编号。"
        )

    # ---------------- 生成 ----------------
    def generate_with_status(self, query: str, hits: Sequence[Hit], lang: str = "zh") -> tuple[str, bool]:
        """返回生成文本及是否降级，供需要区分事实讲解与提示语的调用方使用。"""
        if not hits:
            return "暂未在景区知识库中检索到相关资料，建议补充更具体的关键词，或上传照片后再试一次。", True
        try:
            answer = self.llm.generate(self.build_prompt(query, hits, lang), system=SYSTEM_PROMPT)
        except Exception as exc:
            logger.warning("生成模型不可用，返回降级提示：%s: %s", type(exc).__name__, exc)
            # 检索已命中资料，故把资料要点直接给游客，避免"什么都答不出来"
            digest = "；".join(hit.chunk.title for hit in list(hits)[:3])
            text = f"讲解服务暂时繁忙，先为你列出相关资料：{digest}。请稍后再试一次获取完整讲解。"
            return text, True
        return self._sanitize(answer), False

    def generate(self, query: str, hits: Sequence[Hit], lang: str = "zh") -> str:
        """生成讲解文本；保留原有字符串返回契约供现有对话链路使用。"""
        text, _ = self.generate_with_status(query, hits, lang)
        return text

    def translate(self, text: str, target_lang: str) -> str:
        prompt = f"请将下面的讲解词翻译为 {target_lang}：\n{text}"
        try:
            return self._sanitize(self.llm.generate(prompt, system=MULTILINGUAL_SYSTEM))
        except Exception as exc:
            logger.warning("翻译模型不可用：%s: %s", type(exc).__name__, exc)
            return text  # 翻译失败时回退为原文，不阻断字幕链路

    # ---------------- 内容安全（docs/03 第五章）----------------
    def _sanitize(self, text: str) -> str:
        for banned in self.settings.blocklist:
            if banned and banned in text:
                return "该内容未通过安全审核，已拦截。请更换问题后重试。"
        return text
