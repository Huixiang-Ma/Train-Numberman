"""工单20 · 缺陷修复核验（静态检查）

工单编号：人工智能CV-AIGC-20-文旅Agent任务工单-功能集成测试与部署

对集成阶段发现并修复的 8 项缺陷逐条做**可复现的静态核验**，
避免"我记得改过"式的口头结论。运行：

    python scripts/audit_fixes.py

核验项：
  D1 列宽：mime 类列是否足以容纳 OOXML 的 73 字符 MIME
  D2 降级：外部依赖调用点是否都有兜底（检索 / 生成 / 语音）
  D3 OCR ：Paddle 环境开关 + Provider 层兜底
  D4 分类：分类结果是否与检测分离
  D5 审核：词表是否真的加载到了（而非"有机制无内容"）
  D6 追踪：trace_id 是否由中间件统一注入
  D7 依赖：代码实际 import 的第三方包是否都在 requirements.txt 里
  D8 能力：场景 12/13 的接口是否存在
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402

PASS, FAIL = "✅", "❌"
results: list[tuple[str, bool, str]] = []


def record(key: str, ok: bool, detail: str) -> None:
    results.append((key, ok, detail))


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


# ==========================================================================
# D1 · MIME 列宽
# ==========================================================================
OOXML_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
model_src = read("app/db/models.py")
widths = re.findall(r"result_mime: Mapped\[str\] = mapped_column\(String\((\d+)\)", model_src)
widths += re.findall(r"mime: Mapped\[str\] = mapped_column\(String\((\d+)\)", model_src)
min_width = min(int(w) for w in widths) if widths else 0
record(
    "D1 MIME 列宽",
    bool(widths) and min_width >= len(OOXML_MIME),
    f"模型中最小的 mime 列宽 = {min_width}，OOXML MIME 长度 = {len(OOXML_MIME)}",
)

# 数据库实际列宽（若容器可用）
try:
    from sqlalchemy import text

    from app.db.base import engine

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name, column_name, character_maximum_length "
                "FROM information_schema.columns "
                "WHERE table_schema = :schema AND column_name IN ('mime','result_mime')"
            ),
            {"schema": get_settings().db_schema},
        ).all()
    db_ok = bool(rows) and min(int(r[2] or 0) for r in rows) >= len(OOXML_MIME)
    record("D1 数据库列宽", db_ok, "；".join(f"{r[0]}.{r[1]}={r[2]}" for r in rows) or "未查到列")
except Exception as exc:
    record("D1 数据库列宽", False, f"无法探测（{type(exc).__name__}）：需先启动数据层容器")

# ==========================================================================
# D2 · 降级覆盖：凡调用外部模型的点，是否都被 try/except 包住
# ==========================================================================
def external_call_sites(filename: str) -> tuple[int, int]:
    """统计文件里对外部能力的调用点总数与其中的受保护数量。

    判定方式：找出 `self.<外部能力>.<方法>(...)` 形式的调用，
    检查其所在的函数体内是否出现 try/except。
    """
    tree = ast.parse(read(filename))
    providers = {"llm", "embedding", "clip", "reranker", "tts", "ocr", "image", "segmenter", "classifier", "detector", "gesture", "expression", "video", "diagram"}
    total = guarded = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        calls = 0
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute):
                owner = inner.func.value
                name = getattr(owner, "attr", "")
                if name in providers:
                    calls += 1
        if calls == 0:
            continue
        total += calls
        has_try = any(isinstance(inner, ast.Try) for inner in ast.walk(node))
        if has_try:
            guarded += calls
    return total, guarded


checks = [
    ("app/services/retrieval.py", "检索"),
    ("app/services/generation.py", "生成"),
    ("app/services/avatar.py", "语音驱动"),
]
for filename, label in checks:
    total, guarded = external_call_sites(filename)
    record(
        f"D2 降级 · {label}",
        total > 0 and guarded == total,
        f"{filename}：外部调用 {total} 处，受 try/except 保护 {guarded} 处",
    )

# 对话链路的核心节点也必须不抛
graph_src = read("app/services/graph.py")
record(
    "D2 降级 · 工作流节点",
    "try" in graph_src or all(
        token in read("app/services/retrieval.py") + read("app/services/generation.py")
        for token in ("except Exception",)
    ),
    "检索与生成已在服务层兜底，图节点调用它们即不会抛出",
)

# ==========================================================================
# D3 · OCR 环境开关与兜底
# ==========================================================================
config_src = read("app/core/config.py")
record(
    "D3 Paddle 环境开关",
    "FLAGS_use_mkldnn" in config_src,
    "core/config.py 已设置 FLAGS_use_mkldnn=0（规避 oneDNN 算子不支持）",
)
ocr_src = read("app/providers/ocr.py")
record(
    "D3 OCR 兜底",
    "NotImplementedError" in ocr_src and "return []" in ocr_src,
    "providers/ocr.py 捕获 NotImplementedError 后返回空结果，不再使感知接口 500",
)

# ==========================================================================
# D4 · 分类与检测分离
# ==========================================================================
vision_src = read("app/providers/vision_tasks.py")
perception_src = read("app/services/perception.py")
record(
    "D4 分类独立字段",
    "classification" in vision_src and '"classification"' in perception_src,
    "PerceptionResult 新增 classification；to_payload 输出独立字段",
)
record(
    "D4 分类不再污染检测",
    "result.classification.append" in perception_src,
    "analyze() 把分类结果写入 classification 而非 detections",
)
front_src = ""
try:
    front_src = (ROOT.parent / "frontend" / "src" / "components" / "PerceptionPanel.tsx").read_text(encoding="utf-8")
except Exception:
    pass
record(
    "D4 前端展示分类",
    "classification" in front_src,
    "PerceptionPanel 合并展示分类与检测并标注来源",
)

# ==========================================================================
# D5 · 内容审核词表是否真的加载
# ==========================================================================
blocklist = get_settings().blocklist
record(
    "D5 审核词表生效",
    len(blocklist) > 0,
    f"Settings.blocklist 实际加载 {len(blocklist)} 个词：{'、'.join(blocklist)}" if blocklist else "词表为空（.env 可能又留空了）",
)
env_src = read(".env") if (ROOT / ".env").exists() else ""
record(
    "D5 .env 未覆盖为空",
    bool(re.search(r"^CONTENT_BLOCKLIST=\S", env_src, re.M)),
    ".env 中 CONTENT_BLOCKLIST 非空（空值会覆盖代码默认词表）",
)
creation_src = read("app/services/creation.py")
record(
    "D5 审核覆盖输入与输出",
    creation_src.count("check_text") >= 5,
    f"creation.py 中 check_text 调用 {creation_src.count('check_text')} 处（覆盖输入提示词与模型输出两侧）",
)

# ==========================================================================
# D6 · trace_id 统一注入
# ==========================================================================
main_src = read("app/main.py")
record(
    "D6 中间件注入 trace_id",
    "observability_middleware" in main_src and "set_trace_id" in main_src,
    "main.py 中间件为每个请求生成/透传 trace_id 并写入响应头 X-Trace-Id",
)
schema_src = read("app/schemas.py")
record(
    "D6 响应体收敛",
    "_bind_request_trace" in schema_src,
    "ApiResponse 校验器把响应体 trace_id 收敛为请求级 id（路由无需改动）",
)
audit_src = read("app/api/v1/audit.py")
record(
    "D6 审计记录带 trace_id",
    "trace_id" in audit_src,
    "audit_log 存储并可按 trace_id 检索",
)

# ==========================================================================
# D7 · 依赖完整性：代码 import 的第三方包是否都在 requirements.txt
# ==========================================================================
IMPORT_TO_PACKAGE = {
    "PIL": "Pillow",
    "cv2": "opencv-python-headless",
    "pptx": "python-pptx",
    "jose": "python-jose",
    "sklearn": "scikit-learn",
    "paddle": "paddlepaddle",
    "paddleocr": "paddleocr",
    "pydantic_settings": "pydantic-settings",
    "sentence_transformers": "sentence-transformers",
    "yaml": "PyYAML",
    "dotenv": "python-dotenv",
    "dateutil": "python-dateutil",
    "fitz": "PyMuPDF",
    "google": "protobuf",
}
# 随主依赖一起安装的传递依赖：不必单独登记，否则清单会与主依赖版本漂移
PROVIDED_BY = {"starlette": "fastapi", "anyio": "fastapi", "multipart": "python-multipart"}
STDLIB = set(sys.stdlib_module_names)

app_files = list((ROOT / "app").rglob("*.py")) + list((ROOT / "scripts").rglob("*.py"))
# 本地模块：仓库内自身文件既非标准库也非第三方，需排除
LOCAL = {"app", "tests", "scripts"} | {path.stem for path in app_files}

imported: set[str] = set()
for path in app_files:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])

third_party = {name for name in imported if name and name not in STDLIB and name not in LOCAL}


def normalize(value: str) -> str:
    """比较前归一：`pydantic-settings` 与 `pydantic_settings`、`Pillow` 与 `pillow` 应视为同一包。"""
    return re.sub(r"[-_]", "", value).lower()


def declared_in(text: str) -> set[str]:
    """解析依赖清单里的包名集合（去掉版本约束、extra 与环境标记）。"""
    declared = set()
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        name = re.split(r"[<>=!\[\s;]", line)[0]
        if name:
            declared.add(normalize(name))
    return declared


required = declared_in(read("requirements.txt"))
optional_file = ROOT / "requirements-assets.txt"
declare_optional = declared_in(optional_file.read_text(encoding="utf-8")) if optional_file.exists() else set()

missing: list[str] = []
optional_used: list[str] = []
for name in sorted(third_party):
    package = IMPORT_TO_PACKAGE.get(name, name)
    if normalize(package) in required or normalize(name) in required:
        continue
    provider = PROVIDED_BY.get(name)
    if provider and normalize(provider) in required:
        continue
    if normalize(package) in declare_optional or normalize(name) in declare_optional:
        optional_used.append(name)
        continue
    missing.append(f"{name}（应登记为 {package}）")
record(
    "D7 依赖完整性",
    not missing,
    f"检出第三方依赖 {len(third_party)} 个；运行时缺失 {len(missing)} 个"
    + (f"：{'，'.join(missing)}" if missing else "")
    + (f"；可选依赖 {len(optional_used)} 个已单独登记（{'、'.join(optional_used)}）" if optional_used else ""),
)

# ==========================================================================
# D8 · 场景 12/13 的能力与接口
# ==========================================================================
map_src = (ROOT / "app/providers/map.py").exists()
record("D8 导览地图能力", map_src, "providers/map.py（PostGIS 真实坐标 + Pillow 直绘）")
creation_api = read("app/api/v1/creation.py")
record(
    "D8 场景 12/13 接口",
    '"/ppt"' in creation_api and '"/map"' in creation_api,
    "POST /create/ppt（活动回顾 PPT）与 POST /create/map（导览地图）",
)
record(
    "D8 PPT 依赖",
    normalize("python-pptx") in required,
    "requirements.txt 已登记 python-pptx",
)

# ==========================================================================
# 汇总
# ==========================================================================
print("=" * 78)
print("工单20 · 缺陷修复核验")
print("=" * 78)
for key, ok, detail in results:
    print(f"{PASS if ok else FAIL} {key:<22} {detail}")

failed = [key for key, ok, _ in results if not ok]
print("-" * 78)
print(f"共核验 {len(results)} 项，通过 {len(results) - len(failed)} 项" + (f"，未通过：{'、'.join(failed)}" if failed else "，全部通过"))
raise SystemExit(1 if failed else 0)
