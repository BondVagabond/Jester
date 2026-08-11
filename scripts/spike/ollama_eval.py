"""Spike harness: measure a local Ollama model against Jester's real prompts.

Not production code. Lives outside the packaged trees on purpose - pyproject's
packages.find includes only jester*, pipeline* and training*.
"""

from __future__ import annotations

import argparse
import statistics
import subprocess
import time
from dataclasses import dataclass, field

import httpx

OVERSUBSCRIPTION_RATIO = 0.05


@dataclass(frozen=True)
class MeasuredCall:
    content: str
    thinking: str
    latency_s: float
    prompt_tokens: int
    eval_tokens: int
    prompt_tok_s: float
    gen_tok_s: float
    done_reason: str


@dataclass
class RoleResult:
    role: str
    prompt_name: str
    calls: list[MeasuredCall] = field(default_factory=list)
    passes: list[bool] = field(default_factory=list)


def _run(command: list[str]) -> str:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return 'unavailable'
    return completed.stdout.strip() or 'unavailable'


def capture_environment() -> dict[str, str]:
    return {
        'ollama_ps': _run(['ollama', 'ps']),
        'gpu': _run(
            [
                'nvidia-smi',
                '--query-gpu=memory.used,memory.free,utilization.gpu',
                '--format=csv,noheader',
            ]
        ),
    }


def call_ollama(
    client: httpx.Client,
    *,
    model: str,
    prompt: str,
    num_ctx: int,
    think: bool,
    num_predict: int,
    temperature: float,
    json_format: bool,
) -> MeasuredCall:
    payload: dict[str, object] = {
        'model': model,
        'stream': False,
        'think': think,
        'messages': [{'role': 'user', 'content': prompt}],
        'options': {
            'temperature': temperature,
            'num_ctx': num_ctx,
            'num_predict': num_predict,
        },
    }
    if json_format:
        payload['format'] = 'json'

    started = time.perf_counter()
    response = client.post('/api/chat', json=payload)
    latency_s = time.perf_counter() - started
    response.raise_for_status()
    body = response.json()

    message = body.get('message') or {}
    prompt_tokens = int(body.get('prompt_eval_count') or 0)
    eval_tokens = int(body.get('eval_count') or 0)
    prompt_ns = int(body.get('prompt_eval_duration') or 0)
    eval_ns = int(body.get('eval_duration') or 0)

    return MeasuredCall(
        content=str(message.get('content') or ''),
        thinking=str(message.get('thinking') or ''),
        latency_s=latency_s,
        prompt_tokens=prompt_tokens,
        eval_tokens=eval_tokens,
        prompt_tok_s=prompt_tokens / (prompt_ns / 1e9) if prompt_ns else 0.0,
        gen_tok_s=eval_tokens / (eval_ns / 1e9) if eval_ns else 0.0,
        done_reason=str(body.get('done_reason') or ''),
    )


def is_oversubscribed(call: MeasuredCall) -> bool:
    """Generation far slower than prompt eval means VRAM is paging to system RAM.

    Measured 2026-08-10: 709 tok/s prompt against 3.0 tok/s generation while
    `ollama ps` reported 100% GPU. Placement alone called that run healthy.
    """
    if call.prompt_tok_s <= 0 or call.gen_tok_s <= 0:
        return False
    return (call.gen_tok_s / call.prompt_tok_s) < OVERSUBSCRIPTION_RATIO


def summarize(values: list[float]) -> str:
    if not values:
        return 'n/a'
    ordered = sorted(values)
    p50 = statistics.median(ordered)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    return f'p50 {p50:.1f} / p95 {p95:.1f}'


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Measure a local Ollama model against Jester prompts.')
    parser.add_argument('--model', default='qwen3.5:4b')
    parser.add_argument('--base-url', default='http://127.0.0.1:11434')
    parser.add_argument('--num-ctx', type=int, default=4096)
    parser.add_argument('--think', action='store_true')
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--timeout', type=float, default=600.0)
    parser.add_argument('--out-dir', default='scripts/spike/out')
    return parser
