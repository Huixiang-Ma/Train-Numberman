"""工单18 · 会话接口

工单编号：人工智能CV-AIGC-18-文旅Agent任务工单-智能导览与互动体验
  POST   /api/v1/session       创建会话
  GET    /api/v1/session/{id}  获取会话与上下文
  DELETE /api/v1/session/{id}  结束会话
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from ...schemas import ApiResponse, SessionCreateRequest
from ...services.session import SessionService

router = APIRouter(prefix="/session", tags=["session"])


def _to_out(session) -> dict:
    return {
        "id": session.id,
        "lang": session.lang,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "turns": [{"role": t.role, "content": t.content, "ts": t.ts, "meta": t.meta} for t in session.turns],
    }


@router.post("", response_model=ApiResponse)
def create_session(payload: SessionCreateRequest) -> ApiResponse:
    service = SessionService()
    session = service.create(lang=payload.lang)
    return ApiResponse(data={"store": service.provider, **_to_out(session)}, trace_id=uuid.uuid4().hex)


@router.get("/{session_id}", response_model=ApiResponse)
def get_session(session_id: str) -> ApiResponse:
    session = SessionService().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    return ApiResponse(data=_to_out(session), trace_id=uuid.uuid4().hex)


@router.delete("/{session_id}", response_model=ApiResponse)
def drop_session(session_id: str) -> ApiResponse:
    if not SessionService().drop(session_id):
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    return ApiResponse(data={"closed": session_id}, trace_id=uuid.uuid4().hex)
