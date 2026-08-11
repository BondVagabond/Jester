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
from pathlib import Path

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


def main() -> int:
    from scripts.spike.prompt_suite import SUITE, check_call, render_prompt

    args = build_parser().parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    env_before = capture_environment()
    client = httpx.Client(base_url=args.base_url, timeout=args.timeout)
    results: list[RoleResult] = []
    samples: list[str] = []
    oversubscribed = False

    for case in SUITE:
        prompt, output_contract = render_prompt(case.prompt_name, case.version)
        result = RoleResult(role=case.role, prompt_name=case.prompt_name)
        for _ in range(args.repetitions):
            call = call_ollama(
                client,
                model=args.model,
                prompt=prompt,
                num_ctx=args.num_ctx,
                think=args.think,
                num_predict=case.num_predict,
                temperature=case.temperature,
                json_format=case.expects_json,
            )
            result.calls.append(call)
            result.passes.append(check_call(case, call.content, output_contract))
            oversubscribed = oversubscribed or is_oversubscribed(call)
        results.append(result)
        if not case.expects_json and result.calls:
            samples.append(f'## {case.prompt_name}\n\n{result.calls[0].content}\n')
        print(f'{case.role:9} {case.prompt_name:28} {sum(result.passes)}/{len(result.passes)}')

    env_after = capture_environment()
    report = _render_report(args, env_before, env_after, results, oversubscribed)
    (out_dir / 'report.md').write_text(report, encoding='utf-8')
    (out_dir / 'samples.md').write_text('\n'.join(samples), encoding='utf-8')
    print(f'\nWrote {out_dir / "report.md"} and {out_dir / "samples.md"}')
    return 0


def _render_report(
    args: argparse.Namespace,
    env_before: dict[str, str],
    env_after: dict[str, str],
    results: list[RoleResult],
    oversubscribed: bool,
) -> str:
    lines = [
        f'# Ollama spike report - {args.model}',
        '',
        f'num_ctx {args.num_ctx} | think {args.think} | repetitions {args.repetitions}',
        '',
    ]
    if oversubscribed:
        lines += [
            '> **VRAM OVERSUBSCRIPTION DETECTED.** Generation ran at under 5% of prompt-eval rate.',
            '> The model does not fit in available VRAM and the driver is paging to system RAM.',
            '> Latency figures below are not representative. Free VRAM or use a smaller model.',
            '',
        ]
    lines += ['| role | prompt | pass | gen tok/s | latency s |', '|---|---|---|---|---|']
    for result in results:
        rate = summarize([call.gen_tok_s for call in result.calls])
        latency = summarize([call.latency_s for call in result.calls])
        lines.append(
            f'| {result.role} | {result.prompt_name} | '
            f'{sum(result.passes)}/{len(result.passes)} | {rate} | {latency} |'
        )
    lines += [
        '',
        '## Environment before',
        '```',
        env_before['ollama_ps'],
        env_before['gpu'],
        '```',
        '',
        '## Environment after',
        '```',
        env_after['ollama_ps'],
        env_after['gpu'],
        '```',
    ]
    return '\n'.join(lines)


if __name__ == '__main__':
    raise SystemExit(main())
