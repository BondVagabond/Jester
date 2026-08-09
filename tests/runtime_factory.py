from __future__ import annotations

from jester.domain import (
    NPC,
    Campaign,
    DiceExpression,
    Location,
    Party,
    PlayerCharacter,
    Position,
    Scene,
    Session,
)


def build_session(*, seed: int = 17, session_id: str = 'session-1') -> Session:
    campaign = Campaign(
        campaign_id='campaign-1',
        name='The Copper Vault',
        description='A tense dungeon crawl beneath an old trade city.',
        party_id='party-1',
        location_ids=['location-1'],
        scene_ids=['scene-1'],
        session_ids=[session_id],
    )
    party = Party(
        party_id='party-1',
        campaign_id='campaign-1',
        member_ids=['pc-1', 'pc-2'],
        shared_notes='The party is searching for a stolen key.',
    )
    location = Location(
        location_id='location-1',
        name='Copper Vault Entrance',
        description='Torchlight spills across damp stone and rusted iron gates.',
        dm_notes='A concealed lever opens the smugglers tunnel.',
    )
    scene = Scene(
        scene_id='scene-1',
        campaign_id='campaign-1',
        location_id='location-1',
        party_id='party-1',
        name='Vault Threshold',
        summary='The party faces a goblin lookout in a cramped stone corridor.',
        participant_ids=['pc-1', 'pc-2', 'npc-1'],
        dm_notes='The goblin is waiting for reinforcements.',
    )
    player_one = PlayerCharacter(
        entity_id='pc-1',
        name='Aria',
        armor_class=15,
        max_hp=24,
        current_hp=24,
        initiative_modifier=40,
        attack_bonus=6,
        attack_range=1,
        damage=DiceExpression(count=1, sides=8, modifier=2),
        speed=6,
        scene_position=Position(slot=0),
        controller_id='player-1',
        character_class='Fighter',
        level=3,
        private_notes='Aria secretly seeks the vault key for herself.',
    )
    player_two = PlayerCharacter(
        entity_id='pc-2',
        name='Bram',
        armor_class=13,
        max_hp=18,
        current_hp=18,
        initiative_modifier=20,
        attack_bonus=4,
        attack_range=1,
        damage=DiceExpression(count=1, sides=6, modifier=2),
        speed=6,
        scene_position=Position(slot=4),
        controller_id='player-2',
        character_class='Rogue',
        level=3,
        private_notes='Bram owes a debt to the city watch.',
    )
    goblin = NPC(
        entity_id='npc-1',
        name='Goblin Lookout',
        armor_class=12,
        max_hp=12,
        current_hp=12,
        initiative_modifier=0,
        attack_bonus=4,
        attack_range=1,
        damage=DiceExpression(count=1, sides=6, modifier=1),
        speed=6,
        scene_position=Position(slot=1),
        faction='goblins',
        dm_notes='The lookout knows where the hidden lever sits.',
    )
    return Session(
        session_id=session_id,
        campaign_id='campaign-1',
        name='Copper Vault Session',
        dm_id='dm-1',
        player_ids=['player-1', 'player-2'],
        campaign=campaign,
        party=party,
        current_scene_id='scene-1',
        scenes={'scene-1': scene},
        player_characters={'pc-1': player_one, 'pc-2': player_two},
        npcs={'npc-1': goblin},
        locations={'location-1': location},
        random_seed=seed,
        active=True,
    )