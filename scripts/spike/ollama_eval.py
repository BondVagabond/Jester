"""Spike harness: measure a local Ollama model against Jester's real prompts.

Not production code. Lives outside the packaged trees on purpose - pyproject's
packages.find includes only jester*, pipeline* and training*.

Run from the repo root with the module form, so `scripts` resolves as a package:

    python -m scripts.spike.ollama_eval [--model MODEL] [--think] [--repetitions N]

`python scripts/spike/ollama_eval.py` raises ModuleNotFoundError - sys.path[0] is
then `scripts/spike`, not the repo root, so `scripts.spike.prompt_suite` cannot resolve.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from jester.ai import ModelRole
from jester.ai.providers import _system_message_for_role

GEN_TOK_S_FLOOR = 10.0


@dataclass(frozen=True)
class MeasuredCall:
    content: str
    thinking: str
    latency_s: float
    load_duration_s: float
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
    role: ModelRole,
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
        'messages': [
            {'role': 'system', 'content': _system_message_for_role(role)},
            {'role': 'user', 'content': prompt},
        ],
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
    load_ns = int(body.get('load_duration') or 0)

    return MeasuredCall(
        content=str(message.get('content') or ''),
        thinking=str(message.get('thinking') or ''),
        latency_s=latency_s,
        load_duration_s=load_ns / 1e9,
        prompt_tokens=prompt_tokens,
        eval_tokens=eval_tokens,
        prompt_tok_s=prompt_tokens / (prompt_ns / 1e9) if prompt_ns else 0.0,
        gen_tok_s=eval_tokens / (eval_ns / 1e9) if eval_ns else 0.0,
        done_reason=str(body.get('done_reason') or ''),
    )


def is_generation_degraded(call: MeasuredCall) -> bool:
    """Generation throughput far below what the GPU can sustain, from paging or CPU fallback.

    Measured 2026-08-10 on an RTX 3060 Ti: healthy decode runs 37-90 tok/s, and
    CPU-only fallback runs ~8.5 tok/s, while a model paging to system RAM measured
    3.0 tok/s. A floor between those regimes separates them from healthy generation,
    but not from each other - check the placement percentage in the environment
    block to tell which regime a degraded run is in.

    An earlier version compared generation against prompt-eval rate. That could not
    work: prompt_tok_s is dominated by prompt length (measured 388-12,495 tok/s on
    the same healthy run), so the paging case's ratio fell inside the healthy band.
    """
    if call.gen_tok_s <= 0:
        return False
    return call.gen_tok_s < GEN_TOK_S_FLOOR


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
    from scripts.spike.prompt_suite import SUITE, check_call, render_prompt, role_label

    args = build_parser().parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    env_before = capture_environment()
    client = httpx.Client(base_url=args.base_url, timeout=args.timeout)
    results: list[RoleResult] = []
    samples: list[str] = []
    calls_export: list[dict[str, object]] = []
    degraded = False

    for case in SUITE:
        label = role_label(case.role)
        prompt, output_contract = render_prompt(case)
        result = RoleResult(role=label, prompt_name=case.prompt_name)
        for repetition in range(args.repetitions):
            call = call_ollama(
                client,
                model=args.model,
                role=case.role,
                prompt=prompt,
                num_ctx=args.num_ctx,
                think=args.think,
                num_predict=case.num_predict,
                temperature=case.temperature,
                json_format=case.expects_json,
            )
            passed = check_call(case, call.content, output_contract)
            result.calls.append(call)
            result.passes.append(passed)
            degraded = degraded or is_generation_degraded(call)
            calls_export.append(
                {
                    'role': label,
                    'prompt_name': case.prompt_name,
                    'repetition': repetition,
                    'passed': passed,
                    'content': call.content,
                    'thinking': call.thinking,
                    'latency_s': call.latency_s,
                    'load_duration_s': call.load_duration_s,
                    'prompt_tokens': call.prompt_tokens,
                    'eval_tokens': call.eval_tokens,
                    'prompt_tok_s': call.prompt_tok_s,
                    'gen_tok_s': call.gen_tok_s,
                    'done_reason': call.done_reason,
                }
            )
        results.append(result)
        if not case.expects_json and result.calls:
            samples.append(f'## {case.prompt_name}\n\n{result.calls[0].content}\n')
        print(f'{label:9} {case.prompt_name:28} {sum(result.passes)}/{len(result.passes)}')

    env_after = capture_environment()
    report = _render_report(args, env_before, env_after, results, degraded)
    (out_dir / 'report.md').write_text(report, encoding='utf-8')
    (out_dir / 'samples.md').write_text('\n'.join(samples), encoding='utf-8')
    (out_dir / 'calls.json').write_text(json.dumps(calls_export, indent=2), encoding='utf-8')
    print(f'\nWrote {out_dir / "report.md"}, {out_dir / "samples.md"} and {out_dir / "calls.json"}')
    return 0


def _length_truncated_calls(results: list[RoleResult]) -> list[str]:
    """Calls whose done_reason is 'length' - the response was cut off before finishing.

    For a thinking model this is the diagnostic that the whole token budget went to
    reasoning and no answer was produced (see OllamaChatClient._extract_ollama_content).
    """
    notes = []
    for result in results:
        for index, call in enumerate(result.calls):
            if call.done_reason == 'length':
                notes.append(f'{result.role} / {result.prompt_name} (repetition {index + 1})')
    return notes


def _context_overflow_calls(results: list[RoleResult], num_ctx: int) -> list[str]:
    """Calls whose prompt reached num_ctx - Ollama may have silently truncated the prompt."""
    notes = []
    for result in results:
        for index, call in enumerate(result.calls):
            if call.prompt_tokens and call.prompt_tokens >= num_ctx:
                notes.append(
                    f'{result.role} / {result.prompt_name} (repetition {index + 1}): '
                    f'{call.prompt_tokens} prompt tokens >= num_ctx {num_ctx}'
                )
    return notes


def _cold_load_calls(results: list[RoleResult], threshold_s: float = 1.0) -> list[str]:
    """Calls whose load_duration materially inflated their own latency figure."""
    notes = []
    for result in results:
        for index, call in enumerate(result.calls):
            if call.load_duration_s >= threshold_s:
                notes.append(
                    f'{result.role} / {result.prompt_name} (repetition {index + 1}): '
                    f'{call.load_duration_s:.1f}s of model load included in a '
                    f'{call.latency_s:.1f}s latency figure'
                )
    return notes


def _render_report(
    args: argparse.Namespace,
    env_before: dict[str, str],
    env_after: dict[str, str],
    results: list[RoleResult],
    degraded: bool,
) -> str:
    lines = [
        f'# Ollama spike report - {args.model}',
        '',
        f'num_ctx {args.num_ctx} | think {args.think} | repetitions {args.repetitions}',
        '',
    ]
    if degraded:
        lines += [
            f'> **SLOW GENERATION DETECTED.** Generation fell below {GEN_TOK_S_FLOOR:.1f} tok/s on at '
            'least one call.',
            '> The model is either paging to system RAM (VRAM oversubscription) or running on CPU.',
            '> Check the placement percentage in the environment block below to tell which.',
            '> Latency figures below are not representative. Free VRAM, lower num_ctx, or use a smaller model.',
            '',
        ]

    length_truncations = _length_truncated_calls(results)
    if length_truncations:
        lines += ['> **RESPONSE CUT OFF (done_reason=length)** on:'] + [
            f'> - {note}' for note in length_truncations
        ]
        lines.append('')

    context_overflows = _context_overflow_calls(results, args.num_ctx)
    if context_overflows:
        lines += ['> **PROMPT AT OR OVER num_ctx** - Ollama may have silently truncated the prompt:'] + [
            f'> - {note}' for note in context_overflows
        ]
        lines.append('')

    cold_loads = _cold_load_calls(results)
    if cold_loads:
        lines += ['> **MODEL LOAD INSIDE LATENCY FIGURE** (no warm-up call precedes measurement):'] + [
            f'> - {note}' for note in cold_loads
        ]
        lines.append('')

    lines += ['| role | prompt | pass | gen tok/s | latency s | done reasons |', '|---|---|---|---|---|---|']
    for result in results:
        rate = summarize([call.gen_tok_s for call in result.calls])
        latency = summarize([call.latency_s for call in result.calls])
        done_reasons = ', '.join(sorted({call.done_reason for call in result.calls if call.done_reason})) or 'n/a'
        lines.append(
            f'| {result.role} | {result.prompt_name} | '
            f'{sum(result.passes)}/{len(result.passes)} | {rate} | {latency} | {done_reasons} |'
        )
    lines += [
        '',
        'Full per-call records (content, thinking, done_reason, load_duration, etc.) are in calls.json '
        'next to this report.',
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
