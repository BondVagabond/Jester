from __future__ import annotations

from jester.corpus.models import CorpusDocument
from jester.retrieval import (
    CorpusDefinition,
    CorpusRegistry,
    InMemoryRetrievalCache,
    RetrievalBackend,
    RetrievalOrchestrator,
    RetrievalQuery,
    VectorIndexBackend,
    VectorRetrievalService,
)
from jester.retrieval.corpus_registry import RegisteredCorpus


def _build_registry() -> CorpusRegistry:
    registry = CorpusRegistry()
    registry.register(
        CorpusDefinition(
            corpus_id='world',
            version='v1',
            source_type='jsonl',
            index_metadata={'kind': 'fixture'},
            allowed=True,
        ),
        [
            CorpusDocument(
                doc_id='world-1',
                chunk_id='world-1:1',
                title='Goblin Lookout',
                text='The goblin lookout knows where the hidden lever sits.',
                source='world:goblin-lookout',
                corpus='world',
                tags=['npc'],
            ),
            CorpusDocument(
                doc_id='world-2',
                chunk_id='world-2:1',
                title='Copper Vault Entrance',
                text='Torchlight spills across damp stone and rusted iron gates.',
                source='world:copper-vault-entrance',
                corpus='world',
                tags=['location'],
            ),
        ],
    )
    return registry


def test_retrieval_orchestrator_merges_backends_and_attaches_provenance() -> None:
    orchestrator = RetrievalOrchestrator(_build_registry(), cache=InMemoryRetrievalCache())

    response = orchestrator.retrieve_with_diagnostics(
        RetrievalQuery(text='goblin lever', corpus='world', k=2, request_id='req-1')
    )

    assert response.hits[0].doc_id == 'world-1'
    assert response.hits[0].provenance
    assert 'bm25:world' in response.hits[0].score_breakdown.backend_scores
    assert 'vector:world' in response.hits[0].score_breakdown.backend_scores
    assert len(response.diagnostics.backend_diagnostics) == 2


def test_retrieval_orchestrator_marks_cache_hit_on_repeat() -> None:
    orchestrator = RetrievalOrchestrator(_build_registry(), cache=InMemoryRetrievalCache())
    query = RetrievalQuery(text='goblin lever', corpus='world', k=2, request_id='req-1')

    first = orchestrator.retrieve_with_diagnostics(query)
    second = orchestrator.retrieve_with_diagnostics(query)

    assert first.diagnostics.cache_hit is False
    assert second.diagnostics.cache_hit is True


def test_retrieval_orchestrator_surfaces_degraded_vector_backend() -> None:
    registry = _build_registry()

    def failing_vector_factory(registered: RegisteredCorpus) -> RetrievalBackend:
        return VectorRetrievalService(
            registered.documents,
            corpus_id=registered.definition.corpus_id,
            backend=VectorIndexBackend(
                backend_name=f'vector:{registered.definition.corpus_id}',
                available=False,
                detail='vector backend offline',
            ),
            index_version=registered.definition.version,
        )

    orchestrator = RetrievalOrchestrator(
        registry,
        cache=InMemoryRetrievalCache(),
        vector_factory=failing_vector_factory,
    )

    response = orchestrator.retrieve_with_diagnostics(
        RetrievalQuery(text='goblin lever', corpus='world', k=2, request_id='req-1')
    )

    assert response.hits[0].doc_id == 'world-1'
    assert response.diagnostics.degraded is True
    assert any('vector backend offline' in message for message in response.diagnostics.failure_messages)
