"""工单17 · RAG 工作流编排（主选 LangGraph）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
技术栈：LangGraph + LangChain（docs/01）。把「检索 → 重排 → 生成」固化为显式状态图，
便于后续阶段（工单18 Agent 调度）在同一图上扩展节点。
"""
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from .generation import GenerationService
from .retrieval import RetrievalService


class RagState(TypedDict, total=False):
    query: str
    image: bytes | None
    target: str  # text(以图搜文) | image(以图搜图)
    top_k: int
    rerank_top_n: int
    tags: list[str] | None
    hits: list[Any]
    ocr_text: str
    answer: str
    lang: str


# ---------------- 节点 ----------------
def retrieve_node(state: RagState) -> RagState:
    service = RetrievalService()
    top_k = state.get("top_k", 10)
    image = state.get("image")
    if image:
        result = service.image_search(image, top_k=top_k, target=state.get("target", "text"), tags=state.get("tags"))
        return {"hits": result["hits"], "ocr_text": result["ocr_text"]}
    return {"hits": service.text_to_text(state["query"], top_k=top_k, tags=state.get("tags"))}


def rerank_node(state: RagState) -> RagState:
    hits = state.get("hits") or []
    top_n = state.get("rerank_top_n", 3)
    query = state.get("query") or state.get("ocr_text") or "图片内容讲解"
    return {"hits": RetrievalService.rerank(query, hits, top_n)}


def generate_node(state: RagState) -> RagState:
    query = state.get("query") or state.get("ocr_text") or "请讲解图片内容"
    answer = GenerationService().generate(query, state.get("hits") or [], lang=state.get("lang", "zh"))
    return {"answer": answer}


def build_rag_graph():
    graph = StateGraph(RagState)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("rerank", rerank_node)
    graph.add_node("generate", generate_node)
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "rerank")
    graph.add_edge("rerank", "generate")
    graph.add_edge("generate", END)
    return graph.compile()


_GRAPH = None


def get_rag_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_rag_graph()
    return _GRAPH


def run_rag(
    query: str,
    image: bytes | None = None,
    target: str = "text",
    top_k: int = 10,
    rerank_top_n: int = 3,
    tags: list[str] | None = None,
    lang: str = "zh",
) -> RagState:
    """执行完整的 RAG 工作流，返回最终状态（含 answer / hits / ocr_text）。"""
    initial: RagState = {
        "query": query,
        "image": image,
        "target": target,
        "top_k": top_k,
        "rerank_top_n": rerank_top_n,
        "tags": tags,
        "lang": lang,
    }
    return get_rag_graph().invoke(initial)
