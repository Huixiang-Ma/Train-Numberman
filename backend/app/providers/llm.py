"""工单17 · 生成模型（主选 Qwen，国产合规）

工单编号：人工智能CV-AIGC-17-文旅Agent任务工单-多模态文旅知识检索与生成
技术栈：Qwen（docs/01）。两种私有化/调用方式：
  serving=local → 本地 transformers 加载 Qwen 权重（Windows / CPU 场景）
  serving=vllm  → vLLM / OpenAI 兼容端点（Linux + GPU 生产环境）
"""
from __future__ import annotations

import threading
from pathlib import Path

import httpx

from .base import LLMProvider


class QwenLLM(LLMProvider):
    name = "qwen"

    def __init__(
        self,
        serving: str = "local",
        model_path: Path | None = None,
        base_url: str = "",
        api_key: str = "",
        model: str = "qwen-plus",
        max_new_tokens: int = 512,
    ) -> None:
        self.serving = serving
        self.model_path = Path(model_path) if model_path else None
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_new_tokens = max_new_tokens
        self._lock = threading.Lock()
        self._tokenizer = None
        self._model_obj = None

    # ---------- 本地私有化 ----------
    def _ensure_local(self) -> None:
        if self._model_obj is not None:
            return
        with self._lock:
            if self._model_obj is not None:
                return
            if not self.model_path or not self.model_path.exists():
                raise RuntimeError(
                    f"未找到 Qwen 权重目录：{self.model_path}（请先执行 download_models.py qwen）"
                )
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(str(self.model_path), trust_remote_code=True)
            self._model_obj = AutoModelForCausalLM.from_pretrained(
                str(self.model_path), torch_dtype=torch.float32, trust_remote_code=True
            )
            self._model_obj.eval()

    def _generate_local(self, prompt: str, system: str | None, max_new_tokens: int) -> str:
        import torch

        self._ensure_local()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        text = self._tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self._tokenizer([text], return_tensors="pt")
        with torch.no_grad():
            generated = self._model_obj.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                repetition_penalty=1.05,
            )
        output = generated[0][inputs["input_ids"].shape[1] :]
        return self._tokenizer.decode(output, skip_special_tokens=True).strip()

    # ---------- vLLM / OpenAI 兼容 ----------
    def _generate_remote(self, prompt: str, system: str | None, max_new_tokens: int) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={"model": self.model, "messages": messages, "max_tokens": max_new_tokens, "temperature": 0.3},
            )
            resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    # ---------- 对外 ----------
    def generate(self, prompt: str, system: str | None = None, max_new_tokens: int | None = None) -> str:
        tokens = max_new_tokens or self.max_new_tokens
        if self.serving == "vllm":
            return self._generate_remote(prompt, system, tokens)
        return self._generate_local(prompt, system, tokens)
