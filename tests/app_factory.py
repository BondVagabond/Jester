from __future__ import annotations

from jester.corpus.models import CorpusDocument
from jester.retrieval import BM25RetrievalService, QueryRetriever


def build_world_retriever() -> QueryRetriever:
    return BM25RetrievalService(
        [
            CorpusDocument(
                doc_id='world-npc-1',
                chunk_id='world-npc-1:1',
                title='Goblin Lookout',
                text='The lookout knows where the hidden lever sits. It bargains if cornered.',
                source='world:npc:goblin-lookout',
                corpus='world',
                tags=['npc'],
            ),
            CorpusDocument(
                doc_id='world-town-1',
                chunk_id='world-town-1:1',
                title='Copper Vault Entrance',
                text='Torchlight spills across damp stone. Guards whisper about missing cargo.',
                source='world:location:copper-vault-entrance',
                corpus='world',
                tags=['location'],
            ),
            CorpusDocument(
                doc_id='world-hook-1',
                chunk_id='world-hook-1:1',
                title='Stolen Key Rumor',
                text='A stolen key could open a smugglers tunnel beneath the city. Rival crews are already moving.',
                source='world:hook:stolen-key-rumor',
                corpus='world',
                tags=['hook'],
            ),
        ]
    )


def build_rules_retriever() -> QueryRetriever:
    return BM25RetrievalService(
        [
            CorpusDocument(
                doc_id='rules-initiative-1',
                chunk_id='rules-initiative-1:1',
                title='Initiative Basics',
                text='Initiative establishes turn order in combat and remains stable across rounds.',
                source='rules:initiative',
                corpus='rules',
                tags=['initiative'],
            ),
            CorpusDocument(
                doc_id='rules-attack-1',
                chunk_id='rules-attack-1:1',
                title='Attack Roll Sequence',
                text='Attack rolls determine hit or miss before any damage roll happens.',
                source='rules:attack-rolls',
                corpus='rules',
                tags=['attack_rolls'],
            ),
            CorpusDocument(
                doc_id='rules-damage-1',
                chunk_id='rules-damage-1:1',
                title='Damage Step',
                text='Damage reduces current hit points only after a hit or successful effect.',
                source='rules:damage',
                corpus='rules',
                tags=['damage'],
            ),
        ]
    )