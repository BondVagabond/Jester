from __future__ import annotations

from pathlib import Path

import httpx

from jester.ai import ModelRequest, ModelRole, ModelSelectionPolicy, build_model_registry
from jester.ai.providers import OpenAIChatCompletionsClient
from jester.api.deps import build_container
from jester.app.contracts import PrepArtifactType, PrepRequest, TeachingRequest
from jester.config.settings import OpenAIProviderSettings, load_settings
from jester.corpus import CorpusProfile, build_corpus_registry, normalize_corpus_payload


def test_openai_client_parses_chat_completion_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith('/chat/completions')
        payload = request.read().decode('utf-8')
        assert 'demo-model' in payload
        return httpx.Response(
            200,
            json={
                'choices': [
                    {
                        'message': {
                            'content': 'A concise generated answer.'
                        }
                    }
                ],
                'usage': {
                    'prompt_tokens': 12,
                    'completion_tokens': 4,
                    'total_tokens': 16,
                },
            },
        )

    client = OpenAIChatCompletionsClient(
        role=ModelRole.PRIMARY_GENERATION,
        model_name='demo-model',
        settings=OpenAIProviderSettings(api_key='test-key'),
        http_client=httpx.Client(
            base_url='https://example.test/v1',
            transport=httpx.MockTransport(handler),
        ),
    )

    response = client.generate(
        ModelRequest(
            role=ModelRole.PRIMARY_GENERATION,
            prompt='Summarize the scene.',
            temperature=0.1,
            max_tokens=64,
        )
    )

    assert response.provider_name == 'openai'
    assert response.model_name == 'demo-model'
    assert response.content == 'A concise generated answer.'
    assert response.token_usage == {
        'prompt_tokens': 12,
        'completion_tokens': 4,
        'total_tokens': 16,
    }


def test_build_model_registry_registers_real_clients_when_openai_is_configured() -> None:
    settings = load_settings(
        {
            'JESTER_ENVIRONMENT': 'dev',
            'JESTER_PRIMARY_PROVIDER': 'openai',
            'JESTER_REASONING_PROVIDER': 'openai',
            'JESTER_SMALL_FAST_PROVIDER': 'openai',
            'JESTER_OPENAI_API_KEY': 'test-key',
        }
    )

    registry = build_model_registry(
        settings,
        openai_client_factory=lambda provider_settings: httpx.Client(
            base_url=str(provider_settings.base_url),
            transport=httpx.MockTransport(lambda request: httpx.Response(500, json={'error': {'message': 'unused'}})),
        ),
    )
    selector = ModelSelectionPolicy(registry)

    assert isinstance(registry.client_for(ModelRole.PRIMARY_GENERATION), OpenAIChatCompletionsClient)
    assert selector.resolve(ModelRole.PRIMARY_GENERATION).available is True
    assert selector.resolve(ModelRole.REASONING).provider_name == 'openai'


def test_normalize_corpus_payload_derives_ids_and_source_defaults() -> None:
    chunk = normalize_corpus_payload(
        {
            'name': 'Initiative Basics',
            'rule_text': 'Initiative establishes turn order in combat.',
            'metadata': {'chapter': 'Combat'},
            'tags': ['initiative', 'combat'],
        },
        corpus_name='rules',
        profile=CorpusProfile.ARBITER,
        default_source_prefix='rules',
    )

    assert chunk.corpus_name == 'rules'
    assert chunk.doc_id == 'initiative-basics'
    assert chunk.chunk_id == 'initiative-basics:1'
    assert chunk.source == 'rules/initiative-basics.md'
    assert chunk.metadata['chapter'] == 'Combat'
    assert 'arbiter' in chunk.tags


def test_startup_corpus_registry_loads_default_corpora() -> None:
    settings = load_settings({'JESTER_ENVIRONMENT': 'test'})
    registry = build_corpus_registry(settings.corpora, ingestion_policy=settings.ingestion)

    allowed = registry.list_allowed()
    assert {registered.definition.corpus_id for registered in allowed} == {'world', 'rules'}
    assert all(registered.documents for registered in allowed)


def test_build_container_uses_non_empty_startup_corpora(tmp_path: Path) -> None:
    settings = load_settings(
        {
            'JESTER_ENVIRONMENT': 'test',
            'JESTER_STATE_DB_PATH': str(tmp_path / 'runtime.sqlite3'),
        }
    )
    container = build_container(settings=settings)

    assert {registered.definition.corpus_id for registered in container.corpus_registry.list_allowed()} == {
        'world',
        'rules',
    }


def test_prep_service_uses_world_corpus_debug_and_provenance(tmp_path: Path) -> None:
    settings = load_settings(
        {
            'JESTER_ENVIRONMENT': 'test',
            'JESTER_STATE_DB_PATH': str(tmp_path / 'prep.sqlite3'),
        }
    )
    container = build_container(settings=settings)

    result = container.prep_application_service.execute(
        PrepRequest(
            request_id='prep-world-1',
            artifact_type=PrepArtifactType.NPC_BRIEF,
            topic='Goblin Lookout',
            goal='Create a table-ready NPC',
            include_flavor_prose=False,
        ),
        tenant_id='default',
    )

    assert result.response.npc_brief is not None
    assert result.response.npc_brief.provenance
    assert result.debug.retrieved
    assert result.debug.retrieved[0].route.corpus_id == 'world'
    assert any(hit.corpus_id == 'world' for hit in result.debug.retrieved[0].hits)


def test_teaching_service_is_retrieval_first_with_startup_rules_corpus(tmp_path: Path) -> None:
    settings = load_settings(
        {
            'JESTER_ENVIRONMENT': 'test',
            'JESTER_STATE_DB_PATH': str(tmp_path / 'teaching.sqlite3'),
        }
    )
    container = build_container(settings=settings)

    result = container.teaching_application_service.execute(
        TeachingRequest(
            request_id='teach-rules-1',
            question='Explain how attack rolls work.',
            include_practice=False,
        )
    )

    assert result.response.provenance
    assert result.debug.retrieved
    assert result.debug.retrieved[0].route.corpus_id == 'rules'
    assert any(hit.corpus_id == 'rules' for hit in result.debug.retrieved[0].hits)
    assert 'hit or miss' in result.response.explanation.summary.lower()
