from __future__ import annotations

from jester.retrieval.contracts import ProvenanceEntry, RetrievalHit
from jester.retrieval.corpus_registry import CorpusRegistry, CorpusRegistryError


def attach_hit_provenance(
    hit: RetrievalHit,
    *,
    backend_name: str,
    corpus_registry: CorpusRegistry,
) -> RetrievalHit:
    corpus_id = hit.corpus_id
    if corpus_id is None:
        return hit
    try:
        registered = corpus_registry.get(corpus_id)
    except CorpusRegistryError:
        return hit
    entry = ProvenanceEntry(
        backend_name=backend_name,
        corpus_id=registered.definition.corpus_id,
        corpus_version=registered.definition.version,
        source=hit.source,
    )
    provenance = merge_provenance(hit.provenance, [entry])
    return hit.model_copy(update={'provenance': provenance})


def merge_provenance(
    current: list[ProvenanceEntry],
    incoming: list[ProvenanceEntry],
) -> list[ProvenanceEntry]:
    combined: dict[tuple[str, str, str, str], ProvenanceEntry] = {}
    for entry in [*current, *incoming]:
        key = (entry.backend_name, entry.corpus_id, entry.corpus_version, entry.source)
        combined[key] = entry
    return list(combined.values())
