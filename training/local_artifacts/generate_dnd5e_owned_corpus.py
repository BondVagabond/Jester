from __future__ import annotations

from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent / "dnd5e_owned"

DOCS = [
    {
        "slug": "action-economy-field-notes",
        "title": "Action Economy Field Notes",
        "focus": "how a referee should treat action, bonus action, movement, and reaction pressure in a fifth-edition combat round",
        "signal": "players understand the tradeoff between spending a resource now and preserving a reaction for the enemy turn",
        "risk": "tables often flatten the round into a pile of attacks and forget that posture, timing, and denied options are part of the encounter texture",
        "example": "A shield fighter can advance to block a door, strike once, and still hold a reaction for an opportunity attack. That pattern changes the whole room because the enemy now has to decide whether to rush the choke point, throw ranged pressure past the defender, or spend movement to circle around difficult ground.",
    },
    {
        "slug": "advantage-and-disadvantage-judgment",
        "title": "Advantage And Disadvantage Judgment",
        "focus": "when situational benefits should collapse into advantage, when they should stay descriptive, and when the table should move on without bonus stacking",
        "signal": "the referee rewards smart play quickly without turning every check into a negotiation about tiny modifiers",
        "risk": "overexplaining the math slows the scene and teaches players to ask for arithmetic instead of describing leverage",
        "example": "If a rogue creates darkness, distracts a sentry, and attacks from a hidden ledge, the ruling should usually be one clean source of advantage rather than three separate bonuses. The goal is speed and clarity, not bookkeeping theater.",
    },
    {
        "slug": "saving-throw-pressure",
        "title": "Saving Throw Pressure",
        "focus": "building encounters that test different saving throws without making failure feel arbitrary or repetitive",
        "signal": "players can infer the shape of danger from the fiction before the dice hit the table",
        "risk": "if every threat is a Constitution save against poison or a Wisdom save against fear, classes with weak scores can feel trapped in a narrow failure loop",
        "example": "A haunted archive can present Dexterity saves against falling shelves, Intelligence saves against maddening glyphs, and Wisdom saves against whispering spirits. The scene feels broader because danger comes from place, not just from one monster stat block.",
    },
    {
        "slug": "concentration-and-counterplay",
        "title": "Concentration And Counterplay",
        "focus": "how ongoing spell effects should invite pressure, interruption, and tactical response instead of functioning like permanent scene edits",
        "signal": "both sides look for lines of fire, cover, forced movement, and split pressure once a strong concentration spell lands",
        "risk": "when concentration is never threatened, a single spell can shut down an encounter more completely than the fiction supports",
        "example": "A druid who locks the battlefield with an area spell should feel powerful, but nearby archers, climbing creatures, and enemies using shove effects give the rest of the combat a reason to keep moving instead of standing still inside the first ruling.",
    },
    {
        "slug": "short-rest-and-long-rest-pacing",
        "title": "Short Rest And Long Rest Pacing",
        "focus": "matching adventure pacing to the refresh expectations of fifth-edition classes so martial, caster, and utility roles all matter across a day",
        "signal": "the table can sense a rhythm of push, regroup, and renewed pressure rather than one enormous fight followed by an automatic reset",
        "risk": "if every challenge is followed by full recovery, resource decisions become cosmetic and certain class features lose their intended pacing value",
        "example": "A fortress approach might include scouting, a breach, a tense courtyard skirmish, and a boss chamber. Giving the party one defensible lull between those beats changes how they spend hit dice, spell slots, and once-per-rest abilities.",
    },
    {
        "slug": "exploration-turns-and-travel",
        "title": "Exploration Turns And Travel",
        "focus": "running overland travel and dungeon movement as a sequence of meaningful choices rather than as empty narration between combat scenes",
        "signal": "distance, light, noise, supplies, and route selection all appear in the players' planning language",
        "risk": "when travel has no friction, maps stop mattering and every environment feels interchangeable",
        "example": "A canyon crossing becomes interesting when the party must choose between speed on the exposed ridge, safety in the winding lower wash, or a resource-draining climb to a hidden goat path. None of those options needs combat to matter.",
    },
    {
        "slug": "vision-light-and-ambushes",
        "title": "Vision Light And Ambushes",
        "focus": "treating darkness, bright light, shadow, and line of sight as scene-shaping facts instead of occasional flavor text",
        "signal": "players ask where torches are, what the ceiling looks like, and which enemies can actually see the back line",
        "risk": "if vision rules appear only when the referee wants to surprise the group, players read lighting as a trap rather than an explorable system",
        "example": "A ruined chapel lit by stained moonlight gives ranged combatants islands of visibility while creatures clinging to the rafters drift in and out of shadow. The encounter stays legible because the sight picture is described before initiative starts.",
    },
    {
        "slug": "hazards-traps-and-fair-warning",
        "title": "Hazards Traps And Fair Warning",
        "focus": "using traps and environmental hazards as readable problems with clues, pressure, and consequence rather than sudden punishment",
        "signal": "players can investigate, bypass, trigger intentionally, or weaponize the hazard against opponents",
        "risk": "a hazard that has no warning signs teaches the group that careful observation does not matter",
        "example": "A fungus cavern with unstable spore pillars can telegraph danger through coughing scouts, pale residue on old armor, and a sour smell that thickens near the floor. Once the party notices the pattern, the room becomes tactical instead of arbitrary.",
    },
    {
        "slug": "social-scenes-with-stakes",
        "title": "Social Scenes With Stakes",
        "focus": "framing persuasion, deception, and intimidation around leverage, timing, and risk instead of a single charisma roll detached from context",
        "signal": "players gather information, trade favors, and choose which facts to reveal before they ask for a ruling",
        "risk": "if every negotiation collapses to one die roll, NPCs feel thin and character choices outside charisma become irrelevant",
        "example": "Convincing a magistrate to delay an arrest should hinge on proof, urgency, reputation, and who else is present in the chamber. The roll matters, but it is the final hinge, not the entire door.",
    },
    {
        "slug": "downtime-with-campaign-impact",
        "title": "Downtime With Campaign Impact",
        "focus": "turning crafting, research, training, and faction work into durable campaign movement rather than offscreen bookkeeping",
        "signal": "players choose downtime because they expect new hooks, allies, or complications to emerge from it",
        "risk": "if downtime only exists as a receipt for gold spent, the campaign loses one of its best tools for long-term change",
        "example": "A wizard researching a ruined observatory might uncover star charts, attract a rival scholar, and open a new route to a hidden site. The action fills calendar space and also changes the map of future choices.",
    },
    {
        "slug": "encounter-openers-and-first-impressions",
        "title": "Encounter Openers And First Impressions",
        "focus": "how the first two rounds of a fight establish threat, mobility, and objective pressure before damage totals fully accumulate",
        "signal": "players immediately understand what will go wrong if they stand still and trade blows",
        "risk": "encounters that begin with flat lines of enemies in empty rooms rarely improve after initiative is rolled",
        "example": "A bridge fight opens well when one enemy works the winch, another pins the rear rank with missile fire, and a brute advances from the center. The players get a problem tree right away instead of a blank damage race.",
    },
    {
        "slug": "front-line-space-control",
        "title": "Front Line Space Control",
        "focus": "how reach, choke points, forced movement, and readied pressure let martial characters shape a battlefield without magic",
        "signal": "the group notices that occupying the right square can matter as much as landing another attack",
        "risk": "if monsters and heroes can pass through every formation without cost, the map becomes decorative",
        "example": "Holding a stairway against climbing undead feels different from fighting on a ballroom floor. Narrow space lets a defender trade personal offense for group safety, which is a real and satisfying choice.",
    },
    {
        "slug": "ranged-pressure-and-cover",
        "title": "Ranged Pressure And Cover",
        "focus": "making ranged combat dynamic through cover changes, angle denial, elevation, and movement rather than static full-attacks from the back line",
        "signal": "archers reposition often, melee characters break sight lines, and spellcasters look for lanes before they commit",
        "risk": "flat battlefields with no cover turn every ranged exchange into a repetitive probability contest",
        "example": "Ruined wagons, low walls, and hanging canvas let both sides lean, duck, and relocate. A ranger with a clean lane feels sharp, but that lane has to be earned and defended round by round.",
    },
    {
        "slug": "monster-goals-beyond-hit-points",
        "title": "Monster Goals Beyond Hit Points",
        "focus": "giving enemies objectives such as theft, delay, escape, alarm, or ritual completion so combat outcomes are not measured only in casualties",
        "signal": "players ask what the opponents are trying to accomplish instead of assuming every foe fights to the death",
        "risk": "when monsters behave like sacks of hit points, combat feels disconnected from the wider adventure",
        "example": "Cult guards buying time for a summoner create a sharper encounter than cult guards waiting to be defeated. The players suddenly care about movement, target priority, and whether they can reach the ritual circle in time.",
    },
    {
        "slug": "boss-fights-with-support-structure",
        "title": "Boss Fights With Support Structure",
        "focus": "building major encounters around layers of support, terrain, timing, and recoverable mistakes rather than a single oversized stat block",
        "signal": "the boss feels important because the whole scene reinforces its role",
        "risk": "a solo creature in an empty room often collapses under focused action economy before its narrative weight appears at the table",
        "example": "A necromancer defended by bone wards, unstable soul braziers, and two disciplined bodyguards produces a richer fight than the same necromancer standing alone. The party can solve the room in multiple sequences.",
    },
    {
        "slug": "failure-states-with-forward-motion",
        "title": "Failure States With Forward Motion",
        "focus": "preserving campaign momentum when the party fails a check, loses an objective, or retreats from a fight",
        "signal": "failure changes the board, but it does not erase the campaign's next meaningful decision",
        "risk": "binary pass-fail design encourages caution to the point of paralysis because players learn that a bad roll can simply delete progress",
        "example": "If the group fails to stop a smuggler ship from leaving the harbor, the result might be a river chase, a bribed witness, or a delayed confrontation upstream. The loss matters because it bends the story rather than ending it.",
    },
    {
        "slug": "faction-play-and-reputation",
        "title": "Faction Play And Reputation",
        "focus": "tracking how recurring organizations respond to the party's methods, loyalties, and public decisions across multiple adventures",
        "signal": "the world remembers not just success, but style, alliances, and collateral damage",
        "risk": "if every patron resets between sessions, long-term political play never gains weight",
        "example": "Two groups may both reward the party for recovering an artifact, but one values discretion while the other values spectacle. The same mission outcome can improve one relationship and strain another.",
    },
    {
        "slug": "treasure-that-changes-play",
        "title": "Treasure That Changes Play",
        "focus": "using rewards that open new options, shortcuts, and tactical identities instead of treating treasure as a pure gold-value spreadsheet",
        "signal": "players discuss what an item allows them to attempt, not just whether it is numerically efficient",
        "risk": "uninspired rewards flatten progression because they never change how the group approaches problems",
        "example": "A climbing harness enchanted for silence is memorable because it changes infiltration plans. It matters even in scenes where its resale price never comes up.",
    },
    {
        "slug": "mystery-structure-for-adventure-sites",
        "title": "Mystery Structure For Adventure Sites",
        "focus": "placing clues, witness accounts, physical traces, and contradictory testimony so an investigation can survive missed rolls and partial information",
        "signal": "players connect evidence across rooms and NPCs rather than waiting for a single reveal scene",
        "risk": "if one clue carries the full plot, the adventure becomes fragile and the referee is forced to rescue it from behind the screen",
        "example": "A murdered courier might leave ink on a saddle strap, a coded receipt in the boot lining, and a witness who remembers the wrong coat color but the right accent. The truth emerges from accumulation, not from one perfect check.",
    },
    {
        "slug": "urban-adventures-and-time-pressure",
        "title": "Urban Adventures And Time Pressure",
        "focus": "running city scenarios where distance, rumor speed, watch response, and district boundaries shape play as strongly as combat statistics",
        "signal": "the party chooses routes, disguises, and meeting places with the same care they use when selecting spells for a dungeon crawl",
        "risk": "without time pressure, city play can become an endless chain of risk-free errands",
        "example": "A chase across a market quarter, shrine district, and flood channel feels alive when each area changes how pursuit works. Crowds slow heavy armor, temple bells summon guards, and canals offer escape at the cost of visibility.",
    },
]


def render_document(spec: dict[str, str]) -> str:
    return f"""# {spec['title']}

## Operational Focus
This briefing covers {spec['focus']}. It is written as original training-safe material for a fifth-edition fantasy roleplaying campaign and is meant to be read as guidance rather than as a verbatim rulebook extract. The useful habit is to anchor every ruling in table-facing clarity: what the players can perceive, what they can attempt next, and what cost follows if they ignore the pressure that the scene is already signaling.

## Referee Signal
The clearest sign that the scene is working is that {spec['signal']}. When that happens, players stop fishing for permission and start planning around the environment, the turn structure, and the behavior of the opposition. Good fifth-edition adjudication is rarely about adding more subsystems. It is usually about making the active pressure obvious enough that the group can choose a response, test it, and accept the result without confusion.

## Common Failure Mode
The main failure mode in this area is simple: {spec['risk']}. Once that drift starts, the table tends to solve every problem the same way. Combat becomes a damage race, exploration becomes narration without choices, and social play becomes a thin layer wrapped around one charisma check. The correction is not to slow the game down. The correction is to restore the missing constraint and let the players react to it.

## Table Example
{spec['example']} A strong encounter note should also identify the follow-through. What happens on the next round if the players do nothing? Which resource is under pressure? Which enemy or hazard can be interrupted? Those questions turn a scene from a static description into something the group can actually play.

## Reusable Pattern
When preparing scenes like this, write one sentence for the visible pressure, one sentence for the likely player response, and one sentence for the consequence if the party hesitates. That tiny structure is enough to support improvisation at the table. It also creates compact training data because each document preserves intent, friction, and resolution language in a format the runtime can sectionize and chunk cleanly.
"""


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for spec in DOCS:
        path = OUTPUT_DIR / f"{spec['slug']}.md"
        path.write_text(render_document(spec), encoding="utf-8")


if __name__ == "__main__":
    main()
