from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from jester.api import create_app
from jester.api.deps import ServiceContainer, build_container
from jester.config.settings import AppSettings, load_settings
from jester.corpus.models import CorpusDocument
from jester.retrieval import CorpusDefinition, CorpusRegistry
from jester.state import SQLiteSessionRepository


def build_test_container(
    tmp_path: Path,
    *,
    require_api_key: bool = False,
) -> tuple[ServiceContainer, AppSettings]:
    settings = load_settings(
        {
            'JESTER_ENVIRONMENT': 'test',
            'JESTER_STATE_DB_PATH': str(tmp_path / 'api-state.sqlite3'),
            'JESTER_API_REQUIRE_KEY': 'true' if require_api_key else 'false',
            'JESTER_API_KEYS': 'secret-key' if require_api_key else '',
        }
    )
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
                doc_id='world-npc-1',
                chunk_id='world-npc-1:1',
                title='Goblin Lookout',
                text='The lookout knows where the hidden lever sits and bargains if cornered.',
                source='world:npc:goblin-lookout',
                corpus='world',
                tags=['npc'],
            ),
            CorpusDocument(
                doc_id='world-location-1',
                chunk_id='world-location-1:1',
                title='Copper Vault Entrance',
                text='Torchlight spills across damp stone and rusted iron gates.',
                source='world:location:copper-vault-entrance',
                corpus='world',
                tags=['location'],
            ),
        ],
    )
    registry.register(
        CorpusDefinition(
            corpus_id='rules',
            version='v1',
            source_type='jsonl',
            index_metadata={'kind': 'fixture'},
            allowed=True,
        ),
        [
            CorpusDocument(
                doc_id='rules-attack-1',
                chunk_id='rules-attack-1:1',
                title='Attack Roll Sequence',
                text='Attack rolls determine hit or miss before damage is rolled.',
                source='rules:attack',
                corpus='rules',
                tags=['attack'],
            ),
            CorpusDocument(
                doc_id='rules-initiative-1',
                chunk_id='rules-initiative-1:1',
                title='Initiative Basics',
                text='Initiative establishes turn order in combat and remains stable across rounds.',
                source='rules:initiative',
                corpus='rules',
                tags=['initiative'],
            ),
        ],
    )
    repository = SQLiteSessionRepository(tmp_path / 'api-state.sqlite3')
    container = build_container(
        settings=settings,
        corpus_registry=registry,
        session_repository=repository,
    )
    return container, settings


def build_test_client(
    tmp_path: Path,
    *,
    require_api_key: bool = False,
) -> tuple[FastAPI, ServiceContainer, AppSettings]:
    container, settings = build_test_container(tmp_path, require_api_key=require_api_key)
    app = create_app(settings=settings, container=container)
    return app, container, settings
