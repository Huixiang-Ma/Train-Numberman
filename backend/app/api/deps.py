"""工单17 · 接口依赖（RBAC）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
"""
from __future__ import annotations

from ..core.security import ROLE_EDITOR, ROLE_GUEST, require_role

# 游客可访问检索与问答；知识库写入需运营及以上
guest_only = require_role(ROLE_GUEST)
require_editor = require_role(ROLE_EDITOR)
