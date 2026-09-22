"""工单20 · 个性化导览地图渲染（Pillow 直绘）

工单编号：人工智能CV-AIGC-20-文旅Agent任务工单-功能集成测试与部署
对应工单20 典型场景 13「帮我生成一份导览地图，支持下载和打印」。

技术取向：工单原文技术要点为「路径规划、地图生成、内容定制」。
本项目已有 **PostgreSQL + PostGIS** 存景点真实坐标（阶段四 seed_places.py 灌入），
因此这里直接用真实坐标绘制示意地图，而不是引入第三方底图 SDK：

  1. 无需外部地图服务与密钥，离线可复现，适合景区内网与自助终端；
  2. 坐标取自库内真实数据，路线与顺序由行程策划结果驱动，是"内容定制"而非贴图；
  3. 输出为高分辨率 PNG，可直接打印或下载分享。

坐标系说明：景区尺度（数百米）下经纬度可视为局部平面，按线性映射到画布；
距离用 Haversine 公式按米计算，用于行程单上的步行里程。
"""
from __future__ import annotations

import io
import math
from typing import Any, Sequence

from PIL import Image, ImageDraw

from .video import load_font

# 与前端 Tailwind 令牌一致的暖色体系
PAPER = (251, 243, 231)
SURFACE = (255, 252, 246)
AMBER = (200, 138, 62)
AMBER_DEEP = (150, 96, 36)
AMBER_SOFT = (247, 226, 197)
CLAY = (176, 102, 74)
INK = (58, 44, 36)
INK_SOFT = (140, 118, 96)
SAND = (228, 210, 186)

WIDTH, HEIGHT = 1400, 1000
PAD_X, PAD_Y = 120, 170  # 留出标题带与图例空间


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """两点球面距离（米）。"""
    lon1, lat1 = a
    lon2, lat2 = b
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


class SiteMapRenderer:
    """把行程分站绘制成可打印的导览地图。"""

    name = "pillow-sitemap"

    def render(
        self,
        title: str,
        stops: Sequence[dict[str, Any]],
        all_points: Sequence[dict[str, Any]] | None = None,
        subtitle: str = "",
    ) -> bytes:
        """stops: [{name, lon, lat, index}]；all_points: 全部景点（作为淡色底图参照）。"""
        stops = [s for s in stops if s.get("lon") is not None and s.get("lat") is not None]
        if not stops:
            raise ValueError("没有可用于绘图的景点坐标")

        points = list(stops) + [p for p in (all_points or []) if p.get("lon") is not None and p.get("lat") is not None]
        lons = [float(p["lon"]) for p in points]
        lats = [float(p["lat"]) for p in points]
        min_lon, max_lon = min(lons), max(lons)
        min_lat, max_lat = min(lats), max(lats)
        # 单点或少点聚集时给一个最小跨度，避免所有标记叠在一处
        span_lon = max(max_lon - min_lon, 0.0008)
        span_lat = max(max_lat - min_lat, 0.0008)

        def project(lon: float, lat: float) -> tuple[float, float]:
            x = PAD_X + (lon - min_lon) / span_lon * (WIDTH - PAD_X * 2)
            # 纬度越大越靠北，画布 y 向下，故取反
            y = HEIGHT - PAD_Y - (lat - min_lat) / span_lat * (HEIGHT - PAD_Y * 2)
            return x, y

        canvas = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
        draw = ImageDraw.Draw(canvas)

        # ---- 底纹：细网格，读起来像一张导览图而非纯色块 ----
        for x in range(0, WIDTH, 50):
            draw.line([(x, 0), (x, HEIGHT)], fill=(246, 237, 224), width=1)
        for y in range(0, HEIGHT, 50):
            draw.line([(0, y), (WIDTH, y)], fill=(246, 237, 224), width=1)

        title_font = load_font(46)
        sub_font = load_font(24)
        label_font = load_font(26)
        tiny_font = load_font(20)
        num_font = load_font(24)

        # ---- 其他景点：淡色小点，提供方位参照 ----
        for point in all_points or []:
            if point.get("lon") is None or point.get("lat") is None:
                continue
            x, y = project(float(point["lon"]), float(point["lat"]))
            draw.ellipse([x - 7, y - 7, x + 7, y + 7], fill=AMBER_SOFT, outline=SAND, width=2)
            draw.text((x + 13, y - 11), str(point.get("name") or ""), font=tiny_font, fill=INK_SOFT)

        # ---- 路线：按行程顺序连线，带箭头 ----
        coords = [project(float(s["lon"]), float(s["lat"])) for s in stops]
        if len(coords) > 1:
            draw.line(coords, fill=CLAY, width=7, joint="curve")
            for index in range(len(coords) - 1):
                self._arrow(draw, coords[index], coords[index + 1])

        # ---- 分站标记：编号圆 ----
        for index, (stop, (x, y)) in enumerate(zip(stops, coords)):
            radius = 26
            draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=AMBER, outline=SURFACE, width=4)
            label = str(stop.get("index") or index + 1)
            width = draw.textlength(label, font=num_font)
            draw.text((x - width / 2, y - num_font.size / 2 - 3), label, font=num_font, fill=(255, 248, 236))
            name = str(stop.get("name") or "")
            width = draw.textlength(name, font=label_font)
            # 标签避让：上半部分向下标，下半部分向上标
            label_y = y + radius + 8 if y < HEIGHT * 0.6 else y - radius - label_font.size - 8
            draw.text((x - width / 2, label_y), name, font=label_font, fill=INK)

        # ---- 标题带 ----
        draw.rectangle([0, 0, WIDTH, 108], fill=AMBER_SOFT)
        draw.text((PAD_X // 2, 26), title, font=title_font, fill=INK)
        draw.line([(0, 108), (WIDTH, 108)], fill=SAND, width=2)

        # ---- 图例与里程 ----
        total = sum(haversine_m(
            (float(stops[i]["lon"]), float(stops[i]["lat"])),
            (float(stops[i + 1]["lon"]), float(stops[i + 1]["lat"])),
        ) for i in range(len(stops) - 1))

        legend_y = HEIGHT - PAD_Y // 2 - 6
        draw.line([(PAD_X // 2, legend_y - 34), (WIDTH - PAD_X // 2, legend_y - 34)], fill=SAND, width=2)
        if subtitle:
            draw.text((PAD_X // 2, legend_y - 26), subtitle, font=sub_font, fill=INK_SOFT)

        legend = [
            f"共 {len(stops)} 站",
            f"步行约 {total:.0f} 米",
            f"预计 {max(1, round(total / 60))} 分钟",
        ]
        x = PAD_X // 2
        for text in legend:
            width = draw.textlength(text, font=sub_font)
            draw.rounded_rectangle([x, legend_y + 6, x + width + 36, legend_y + 50], radius=14, fill=SURFACE, outline=SAND, width=2)
            draw.text((x + 18, legend_y + 16), text, font=sub_font, fill=AMBER_DEEP)
            x += width + 56

        note = "示意地图（按景点真实坐标绘制），实际路径以景区现场指示为准"
        draw.text((WIDTH - PAD_X // 2 - draw.textlength(note, font=tiny_font), legend_y + 20), note, font=tiny_font, fill=INK_SOFT)

        buffer = io.BytesIO()
        canvas.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()

    @staticmethod
    def _arrow(draw: ImageDraw.ImageDraw, start: tuple[float, float], end: tuple[float, float]) -> None:
        """在线段中点画一个方向箭头。"""
        mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
        angle = math.atan2(end[1] - start[1], end[0] - start[0])
        size = 17
        left = (mx - size * math.cos(angle - 0.42), my - size * math.sin(angle - 0.42))
        right = (mx - size * math.cos(angle + 0.42), my - size * math.sin(angle + 0.42))
        tip = (mx + size * 0.7 * math.cos(angle), my + size * 0.7 * math.sin(angle))
        draw.polygon([tip, left, right], fill=CLAY)
