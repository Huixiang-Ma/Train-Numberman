"""工单19 · 流程图渲染能力（Mermaid + 位图成品）

工单编号：人工智能CV-AIGC-19-文旅Agent任务工单-创意策划与内容生成
对应 docs/01 §4.7：流程图生成主选 **Mermaid / Graphviz**。

为什么同时给两种产物：
  - **Mermaid 源码**：纯文本、可版本管理、可在前端或文档里二次编辑渲染（工单19 §4.4
    「内容编辑与定制」要求游客能对生成内容做简单编辑）。
  - **位图成品**：游客要的是能直接保存、下载、分享到社交平台的东西，
    源码不满足该诉求，因此用 Pillow 直绘一张流程图 PNG。

不依赖 Graphviz：本机未安装 graphviz 二进制与 Python 包，且 Mermaid 已在选型表内，
选 Mermaid 源码 + 自绘位图可避免引入外部可执行依赖。
"""
from __future__ import annotations

from typing import Any, Sequence

from PIL import Image, ImageDraw

from .base import DiagramRenderer
from .video import load_font

# 暖色体系，与前端 Tailwind 令牌保持一致（paper/amber/clay/sand/ink）
PAPER = (251, 243, 231)
SURFACE = (255, 252, 246)
AMBER = (200, 138, 62)
AMBER_SOFT = (247, 226, 197)
CLAY = (176, 102, 74)
INK = (58, 44, 36)
SAND = (228, 210, 186)


class MermaidDiagramRenderer(DiagramRenderer):
    """活动参与流程 / 体验流程图。"""

    name = "mermaid"

    def __init__(self, width: int = 1000, margin: int = 64) -> None:
        self.width = width
        self.margin = margin

    # ---------------- Mermaid 源码 ----------------
    @staticmethod
    def to_mermaid(title: str, steps: Sequence[str], direction: str = "TD") -> str:
        lines = [f"---", f"title: {title}", f"---", f"flowchart {direction}"]
        for index, step in enumerate(steps):
            text = step.replace('"', "'").replace("\n", " ")
            lines.append(f'    S{index}["{index + 1}. {text}"]')
        for index in range(len(steps) - 1):
            lines.append(f"    S{index} --> S{index + 1}")
        return "\n".join(lines)

    # ---------------- 位图渲染 ----------------
    def _wrap(self, draw: ImageDraw.ImageDraw, text: str, font, limit: int) -> list[str]:
        lines: list[str] = []
        current = ""
        for char in text:
            probe = current + char
            if draw.textlength(probe, font=font) > limit and current:
                lines.append(current)
                current = char
            else:
                current = probe
        if current:
            lines.append(current)
        return lines or [""]

    def render(self, title: str, steps: Sequence[str], direction: str = "TD") -> dict[str, Any]:
        steps = [s.strip() for s in steps if s and s.strip()]
        if not steps:
            raise ValueError("流程图至少需要一个步骤")

        title_font = load_font(38)
        step_font = load_font(26)
        index_font = load_font(22)

        box_w = self.width - self.margin * 2
        inner_limit = box_w - 150
        probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))

        # 先量算每步折行后的高度，得到整体画布尺寸
        blocks: list[list[str]] = []
        for step in steps:
            blocks.append(self._wrap(probe, step, step_font, inner_limit))
        line_h = 38
        padding = 26
        heights = [len(b) * line_h + padding * 2 for b in blocks]
        gap = 54  # 箭头区高度

        header = 120
        total_h = header + sum(heights) + gap * (len(steps) - 1) + self.margin

        image = Image.new("RGB", (self.width, total_h), PAPER)
        draw = ImageDraw.Draw(image)

        # 顶部标题带
        draw.rectangle([0, 0, self.width, 88], fill=AMBER_SOFT)
        draw.text((self.margin, 26), title, font=title_font, fill=INK)
        draw.line([(0, 88), (self.width, 88)], fill=SAND, width=2)

        y = header
        for index, lines in enumerate(blocks):
            height = heights[index]
            box = [self.margin, y, self.margin + box_w, y + height]
            draw.rounded_rectangle(box, radius=18, fill=SURFACE, outline=SAND, width=2)
            # 左侧序号圆
            radius = 22
            cx, cy = self.margin + 46, y + height / 2
            draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=AMBER)
            label = str(index + 1)
            label_w = draw.textlength(label, font=index_font)
            draw.text((cx - label_w / 2, cy - index_font.size / 2 - 2), label, font=index_font, fill=(255, 248, 236))

            text_y = y + padding
            for line in lines:
                draw.text((self.margin + 92, text_y), line, font=step_font, fill=INK)
                text_y += line_h

            # 连接箭头
            if index < len(steps) - 1:
                arrow_x = self.width / 2
                start = y + height + 10
                end = y + height + gap - 12
                draw.line([(arrow_x, start), (arrow_x, end)], fill=CLAY, width=3)
                draw.polygon(
                    [(arrow_x - 9, end - 2), (arrow_x + 9, end - 2), (arrow_x, end + 13)],
                    fill=CLAY,
                )
            y += height + gap

        output = Image.new("RGB", image.size, PAPER)
        output.paste(image, (0, 0))
        from io import BytesIO

        buffer = BytesIO()
        output.save(buffer, format="PNG", optimize=True)

        return {
            "title": title,
            "steps": list(steps),
            "mermaid": self.to_mermaid(title, steps, direction),
            "png": buffer.getvalue(),
            "width": output.width,
            "height": output.height,
        }
