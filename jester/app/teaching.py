# ruff: noqa: I001
from __future__ import annotations

from dataclasses import dataclass

from jester.ai import (
    ModelRegistry,
    ModelRole,
    ModelSelectionPolicy,
    ModelTraceRecord,
    ReasoningService,
    RolePromptModelClient,
    SmallFastClassifier,
    TeachingPlanArtifact,
)
from jester.app.contracts import (
    LessonResponse,
    MisconceptionHint,
    PracticeScenario,
    ProvenanceReference,
    QuizItem,
    RulesConceptExplanation,
    TeachingConcept,
    TeachingDepth,
    TeachingRequest,
)
from jester.app.orchestration import (
    GenerationRequest,
    RetrievalContextService,
    RetrievedContext,
    ServiceWarning,
    ServiceWarningCode,
    TeachingServiceResult,
    WorkspaceDebugInfo,
    WorkspaceName,
    WorkspacePromptAssembler,
    WorkspaceRoutingPolicy,
    WorkspaceTask,
)
from jester.app.orchestration.contracts import RetrievedContextItem
from jester.app.prompting import PromptModelClient
from jester.retrieval import QueryRetriever, RetrievalQuery, RetrievedDocument
from jester.validation import OutputValidationPolicy



class TeachingServiceError(ValueError):
    """Raised when a teaching request cannot be resolved safely."""


@dataclass(frozen=True, slots=True)
class _ConceptDefinition:
    title: str
    prerequisites: tuple[TeachingConcept, ...]
    beginner_summary: str
    intermediate_summary: str
    beginner_points: tuple[str, ...]
    intermediate_points: tuple[str, ...]
    worked_example: tuple[str, ...]
    misconceptions: tuple[tuple[str, str, str], ...]
    scenario_title: str
    scenario_setup: str
    scenario_prompt: str
    beginner_steps: tuple[str, ...]
    intermediate_steps: tuple[str, ...]
    sample_resolution: tuple[str, ...]
    quiz_question: str
    quiz_answer: str
    quiz_explanation: str


_CONCEPTS: dict[TeachingConcept, _ConceptDefinition] = {
    TeachingConcept.ABILITY_CHECKS: _ConceptDefinition(
        title='Ability Checks',
        prerequisites=(),
        beginner_summary='An ability check tests whether a character can succeed at an uncertain task.',
        intermediate_summary=(
            'An ability check uses a d20 plus a relevant ability modifier when '
            'failure and success would both matter.'
        ),
        beginner_points=(
            'Roll one d20 when the outcome is uncertain.',
            'Add the relevant ability modifier.',
            'Compare the total to the difficulty.',
        ),
        intermediate_points=(
            'Only call for a check when the result matters.',
            'Pick the ability that best fits the fictional approach.',
            'Checks resolve uncertainty without replacing roleplay.',
        ),
        worked_example=(
            'A rogue tries to force a gate before guards arrive.',
            'The table uses a Strength check because timing and failure matter.',
        ),
        misconceptions=(
            (
                'Every hard action needs a roll.',
                'Only uncertain actions with stakes need a check.',
                'That keeps play moving and avoids empty rolling.',
            ),
        ),
        scenario_title='Force the Gate',
        scenario_setup='A rusted gate blocks the corridor while footsteps approach.',
        scenario_prompt='Explain when and how to call for an ability check here.',
        beginner_steps=(
            'Describe the goal.',
            'Pick the relevant ability.',
            'Roll only if failure matters.',
        ),
        intermediate_steps=(
            'Clarify the approach first.',
            'Set a difficulty from the fiction.',
            'Roll only if both success and failure change the scene.',
        ),
        sample_resolution=(
            'The DM calls for Strength, the roll succeeds, and the gate opens in time.',
        ),
        quiz_question='When is an ability check appropriate?',
        quiz_answer='When the outcome is uncertain and failure would matter.',
        quiz_explanation='Checks are for meaningful uncertainty, not routine actions.',
    ),
    TeachingConcept.ATTACK_ROLLS: _ConceptDefinition(
        title='Attack Rolls',
        prerequisites=(TeachingConcept.BASIC_ACTIONS,),
        beginner_summary='An attack roll tells you whether an attack hits the target at all.',
        intermediate_summary=(
            'An attack roll is a d20 plus attack modifiers compared against Armor '
            'Class to determine hit or miss.'
        ),
        beginner_points=(
            'Roll a d20 for the attack.',
            'Add the attack bonus.',
            'If the total meets Armor Class, the attack hits.',
        ),
        intermediate_points=(
            'Hit chance and damage are separate steps.',
            'Armor Class measures how hard the target is to hit cleanly.',
            'A high-damage weapon still does nothing on a miss.',
        ),
        worked_example=(
            'A fighter attacks AC 12 and rolls 9 + 6 for a total of 15.',
            'The attack hits, so damage is rolled afterward.',
        ),
        misconceptions=(
            (
                'Damage and attack are the same roll.',
                'Attack resolves hit or miss before damage exists.',
                'Separating the steps keeps combat deterministic and readable.',
            ),
        ),
        scenario_title='Strike the Goblin',
        scenario_setup='A goblin stands one slot away from the fighter.',
        scenario_prompt='Walk through the hit check from declaration to result.',
        beginner_steps=(
            'Declare the target.',
            'Roll d20 + attack bonus.',
            'Compare to Armor Class.',
        ),
        intermediate_steps=(
            'Confirm the target is in range.',
            'Roll d20 + attack bonus.',
            'Only move to damage if the hit succeeds.',
        ),
        sample_resolution=(
            'The fighter rolls 15 total against AC 12, so the hit lands.',
        ),
        quiz_question='What decides whether a weapon attack hits?',
        quiz_answer='The attack total compared to Armor Class.',
        quiz_explanation='Attack rolls answer hit or miss before damage is applied.',
    ),
    TeachingConcept.DAMAGE: _ConceptDefinition(
        title='Damage',
        prerequisites=(TeachingConcept.ATTACK_ROLLS, TeachingConcept.HIT_POINTS),
        beginner_summary='Damage lowers current hit points after a hit or successful effect.',
        intermediate_summary=(
            'Damage is resolved after success and reduces current hit points '
            'without changing whether the attack hit.'
        ),
        beginner_points=(
            'Roll damage after the hit is confirmed.',
            'Subtract the result from current hit points.',
            'At zero hit points, the target leaves normal fighting state.',
        ),
        intermediate_points=(
            'Damage never turns a miss into a hit.',
            'Damage changes current hit points, not maximum hit points.',
            'Zero hit points trigger the next state change immediately.',
        ),
        worked_example=(
            'A fighter hits and rolls 1d8 + 2 damage for 6 total.',
            'The goblin loses 6 current hit points.',
        ),
        misconceptions=(
            (
                'A big damage roll can rescue a miss.',
                'Damage matters only after the hit already succeeded.',
                'This protects trust in mechanical outcomes.',
            ),
        ),
        scenario_title='Resolve the Hit',
        scenario_setup='A sword strike has already connected with the goblin.',
        scenario_prompt='Explain the damage step from roll to state update.',
        beginner_steps=(
            'Roll damage.',
            'Add the damage modifier.',
            'Subtract from current hit points.',
        ),
        intermediate_steps=(
            'Confirm the hit first.',
            'Roll the listed damage expression once.',
            'Apply the result and check for zero hit points.',
        ),
        sample_resolution=(
            'The goblin drops from 12 to 6 hit points after the damage roll.',
        ),
        quiz_question='When do you roll damage?',
        quiz_answer='After the hit or effect has already succeeded.',
        quiz_explanation='Damage is the consequence of success, not the test for success.',
    ),
    TeachingConcept.INITIATIVE: _ConceptDefinition(
        title='Initiative',
        prerequisites=(TeachingConcept.TURNS,),
        beginner_summary='Initiative sets turn order in combat.',
        intermediate_summary=(
            'Initiative establishes combat turn order at the start of a fight '
            'and then repeats that order each round.'
        ),
        beginner_points=(
            'Each combatant gets a place in the order.',
            'The highest initiative goes first.',
            'After the last turn, the order loops back to the top.',
        ),
        intermediate_points=(
            'Initiative is about order, not attack or damage.',
            'Once set, the order stays stable until a rule changes it.',
            'Current actor and round number belong to canonical combat state.',
        ),
        worked_example=(
            'Aria acts first, Bram acts second, and the goblin acts third.',
            'After the goblin turn, the round returns to Aria.',
        ),
        misconceptions=(
            (
                'Initiative is rerolled every turn.',
                'Initiative sets order once and that order repeats.',
                'Stable turn order makes combat easier to audit and explain.',
            ),
        ),
        scenario_title='Start Combat',
        scenario_setup='Three combatants enter a corridor fight.',
        scenario_prompt='Explain what initiative solves before anyone attacks.',
        beginner_steps=(
            'Set the turn order.',
            'Identify who acts first.',
            'Use that order until combat ends.',
        ),
        intermediate_steps=(
            'Establish order once at combat start.',
            'Use current combatant state to decide legal actions.',
            'Advance rounds only after the last combatant finishes.',
        ),
        sample_resolution=(
            'The fighter, rogue, and goblin keep the same repeating order for the fight.',
        ),
        quiz_question='What does initiative determine?',
        quiz_answer='The order of turns in combat.',
        quiz_explanation='It answers who acts now and who acts next.',
    ),
    TeachingConcept.TURNS: _ConceptDefinition(
        title='Turns',
        prerequisites=(),
        beginner_summary='A turn is the part of combat when one combatant acts.',
        intermediate_summary=(
            'A turn is the current combatant active window to move, attack, or '
            'end turn within initiative order.'
        ),
        beginner_points=(
            'Only one combatant acts at a time.',
            'When that combatant finishes, the next turn begins.',
            'Rounds are made of many turns in order.',
        ),
        intermediate_points=(
            'Turn legality depends on current combat state.',
            'Ending the turn passes control to the next combatant.',
            'Movement and actions must resolve inside the active turn window.',
        ),
        worked_example=(
            'It is Aria turn, so only Aria supported actions are legal right now.',
            'When Aria ends the turn, Bram becomes the current combatant.',
        ),
        misconceptions=(
            (
                'Anyone can act whenever they speak up.',
                'Only the current combatant can take supported actions.',
                'Turn enforcement is one of the main protections against state drift.',
            ),
        ),
        scenario_title='Pass the Turn',
        scenario_setup='Aria has finished moving and now wants to stop acting.',
        scenario_prompt='Explain what ending the turn changes in the combat state.',
        beginner_steps=(
            'Finish the current choices.',
            'Mark the turn as ended.',
            'Advance to the next combatant.',
        ),
        intermediate_steps=(
            'Confirm the acting combatant is current.',
            'Advance the turn marker.',
            'Reset the next combatant movement budget in the MVP engine.',
        ),
        sample_resolution=(
            'Aria ends the turn and Bram becomes current immediately.',
        ),
        quiz_question='What happens when a turn ends?',
        quiz_answer='Control passes to the next combatant in initiative order.',
        quiz_explanation='Turns move combat forward one actor at a time.',
    ),
    TeachingConcept.HIT_POINTS: _ConceptDefinition(
        title='Hit Points',
        prerequisites=(),
        beginner_summary='Hit points show how much harm a creature can still take.',
        intermediate_summary=(
            'Hit points are canonical state values that fall when damage is '
            'applied and determine whether a combatant stays active.'
        ),
        beginner_points=(
            'Current hit points go down when damage is applied.',
            'Maximum hit points are the ceiling.',
            'At zero hit points, the creature is no longer fighting normally.',
        ),
        intermediate_points=(
            'Current and maximum hit points are different values.',
            'Current hit points change during play; maximum usually does not.',
            'Combat state and entity state should always agree on the current number.',
        ),
        worked_example=(
            'A goblin starts at 12 hit points and takes 6 damage.',
            'The goblin now has 6 current hit points.',
        ),
        misconceptions=(
            (
                'Hit points only matter when combat ends.',
                'Hit points matter after every successful damage application.',
                'Immediate updates keep state and narration aligned.',
            ),
        ),
        scenario_title='Track the Goblin Health',
        scenario_setup='The goblin has already taken one hit.',
        scenario_prompt='Explain current versus maximum hit points.',
        beginner_steps=(
            'Read the current hit points.',
            'Apply new damage to the current value only.',
            'Check whether the result reaches zero.',
        ),
        intermediate_steps=(
            'Keep current and maximum hit points separate.',
            'Update current hit points after each resolved hit.',
            'Use zero hit points to trigger the next state change.',
        ),
        sample_resolution=(
            'The goblin reaches zero current hit points and leaves normal action state.',
        ),
        quiz_question='What is the difference between current and maximum hit points?',
        quiz_answer='Current hit points change during play; maximum hit points are the ceiling.',
        quiz_explanation='Damage changes the current value, not the maximum value.',
    ),
    TeachingConcept.BASIC_ACTIONS: _ConceptDefinition(
        title='Basic Actions in Combat',
        prerequisites=(TeachingConcept.TURNS,),
        beginner_summary='The MVP engine supports attack, move, and end turn as basic combat actions.',
        intermediate_summary=(
            'Basic combat actions in the MVP engine are the deterministic '
            'choices available on your turn: attack, move, and end turn.'
        ),
        beginner_points=(
            'You act on your turn, not whenever you want.',
            'Attack, move, and end turn are the supported combat actions.',
            'Each action changes combat state in a specific way.',
        ),
        intermediate_points=(
            'Supported actions are limited by the current capability policy.',
            'Movement is tracked separately from attack resolution.',
            'End turn advances initiative and refreshes the next actor movement budget.',
        ),
        worked_example=(
            'Aria can move, attack a nearby goblin, or end the turn.',
            'Each choice follows a deterministic validation and resolution path.',
        ),
        misconceptions=(
            (
                'If you can describe it, the engine already supports it.',
                'Only explicitly supported actions are resolved mechanically right now.',
                'Honest boundaries protect user trust when rules coverage is incomplete.',
            ),
        ),
        scenario_title='Choose an Action',
        scenario_setup='Aria is the current combatant in a corridor fight.',
        scenario_prompt='Explain which supported options Aria has right now.',
        beginner_steps=(
            'Check that it is Aria turn.',
            'Choose move, attack, or end turn.',
            'Resolve that choice before anything else changes.',
        ),
        intermediate_steps=(
            'Confirm the acting combatant and turn state.',
            'Choose among currently implemented mechanical actions only.',
            'Resolve in code first and narrate afterward.',
        ),
        sample_resolution=(
            'Aria moves one slot, attacks if in range, or ends the turn to pass control onward.',
        ),
        quiz_question='Which combat actions are supported by the MVP engine?',
        quiz_answer='Attack, move, and end turn.',
        quiz_explanation='Those are the deterministic mechanical actions currently implemented.',
    ),
}

_KEYWORD_TO_CONCEPT: dict[str, TeachingConcept] = {
    'ability check': TeachingConcept.ABILITY_CHECKS,
    'attack roll': TeachingConcept.ATTACK_ROLLS,
    'damage': TeachingConcept.DAMAGE,
    'initiative': TeachingConcept.INITIATIVE,
    'turn': TeachingConcept.TURNS,
    'hit points': TeachingConcept.HIT_POINTS,
    'basic actions': TeachingConcept.BASIC_ACTIONS,
    'combat action': TeachingConcept.BASIC_ACTIONS,
}


class TeachingService:
    def __init__(
        self,
        *,
        retriever: QueryRetriever | None = None,
        model_client: PromptModelClient | None = None,
        policy: OutputValidationPolicy | None = None,
        model_registry: ModelRegistry | None = None,
        selection_policy: ModelSelectionPolicy | None = None,
        reasoning_service: ReasoningService | None = None,
        classifier: SmallFastClassifier | None = None,
    ) -> None:
        self._retriever = retriever
        self._model_client = model_client
        self._policy = policy
        self._selector = selection_policy or (ModelSelectionPolicy(model_registry) if model_registry else None)
        self._reasoning_service = reasoning_service or ReasoningService(self._selector)
        self._classifier = classifier or (SmallFastClassifier(self._selector) if self._selector is not None else None)
        self._retrieval_context = RetrievalContextService(retriever)
        self._prompt_assembler = WorkspacePromptAssembler(
            selection_policy=self._selector,
            legacy_model_client=model_client,
            policy=self._policy,
        )

    def get_prerequisites(self, concept: TeachingConcept) -> list[TeachingConcept]:
        return list(_CONCEPTS[concept].prerequisites)

    def classify_follow_up_depth(self, question: str) -> TeachingDepth:
        return self._resolve_depth(question, explicit_depth=None, trace_sink=None)

    def build_lesson(self, request: TeachingRequest) -> LessonResponse:
        return self.execute(request).response

    def execute(self, request: TeachingRequest) -> TeachingServiceResult:
        traces: list[ModelTraceRecord] = []
        warnings: list[ServiceWarning] = []
        concept = request.concept or self._infer_concept(request.question)
        definition = _CONCEPTS[concept]
        depth = self._resolve_depth(request.question, explicit_depth=request.depth, trace_sink=traces)

        retrieval_route = WorkspaceRoutingPolicy.teaching_retrieval()
        retrieved_context = self._retrieval_context.fetch(
            retrieval_route,
            query_text=WorkspaceRoutingPolicy.teaching_query_text(request.question, concept),
            request_id=request.request_id,
        )
        warnings.extend(retrieved_context.warnings)
        if not retrieved_context.hits:
            warnings.append(
                ServiceWarning(
                    code=ServiceWarningCode.AUTHORED_FALLBACK_USED,
                    message=(
                        'Teaching used authored concept scaffolding because retrieval did not return '
                        'supporting rules text.'
                    ),
                    degraded=False,
                )
            )

        plan_route = WorkspaceRoutingPolicy.teaching_plan()
        teaching_plan = self._reasoning_service.build_teaching_plan(
            concept=concept.value,
            depth=depth.value,
            prerequisites=[item.value for item in definition.prerequisites],
            misconceptions=[item[0] for item in definition.misconceptions],
            trace_sink=traces,
        )

        summary, key_points = _explanation_from_retrieval(
            definition,
            retrieved_context,
            depth,
        )
        explanation = RulesConceptExplanation(
            concept=concept,
            title=definition.title,
            summary=summary,
            prerequisites=list(definition.prerequisites),
            key_points=key_points,
            worked_example=list(definition.worked_example),
        )
        misconceptions = _ordered_misconceptions(definition, teaching_plan)

        answer_route = WorkspaceRoutingPolicy.teaching_answer()
        prose_response = self._prompt_assembler.generate(
            GenerationRequest(
                route=answer_route,
                template_values={
                    'concept': concept.value,
                    'question': request.question,
                    'depth': depth.value,
                    'structured_summary': _structured_summary(summary, teaching_plan),
                    'retrieved_rules': _retrieved_context_text_from_context(retrieved_context),
                },
                fallback_text=summary,
            ),
            trace_sink=traces,
        )
        warnings.extend(prose_response.warnings)
        _append_generation_trace(
            traces,
            prompt_name=prose_response.block.prompt_name,
            prompt_version=prose_response.block.prompt_version,
            used_fallback=prose_response.block.used_fallback,
            validation_passed=prose_response.block.validation_passed,
            provider_name=self._provider_name_for_role(answer_route.model_role),
            model_name=self._model_name_for_role(answer_route.model_role),
            outcome='teaching_explanation_validated',
            role=answer_route.model_role or ModelRole.REASONING,
        )

        practice_scenario = None
        routes = [retrieval_route, plan_route, answer_route]
        if request.include_practice:
            practice_route = WorkspaceRoutingPolicy.teaching_practice()
            practice_prose = self._prompt_assembler.generate(
                GenerationRequest(
                    route=practice_route,
                    template_values={
                        'concept': concept.value,
                        'depth': depth.value,
                        'scenario_setup': definition.scenario_setup,
                        'scenario_goal': definition.scenario_prompt,
                    },
                    fallback_text=' '.join(definition.sample_resolution),
                ),
                trace_sink=traces,
            )
            warnings.extend(practice_prose.warnings)
            _append_generation_trace(
                traces,
                prompt_name=practice_prose.block.prompt_name,
                prompt_version=practice_prose.block.prompt_version,
                used_fallback=practice_prose.block.used_fallback,
                validation_passed=practice_prose.block.validation_passed,
                provider_name=self._provider_name_for_role(practice_route.model_role),
                model_name=self._model_name_for_role(practice_route.model_role),
                outcome='teaching_practice_validated',
                role=practice_route.model_role or ModelRole.REASONING,
            )
            steps = (
                definition.beginner_steps
                if depth == TeachingDepth.BEGINNER
                else definition.intermediate_steps
            )
            practice_scenario = PracticeScenario(
                title=definition.scenario_title,
                setup=definition.scenario_setup,
                prompt=definition.scenario_prompt,
                expected_steps=list(steps),
                sample_resolution=list(definition.sample_resolution),
                prose=practice_prose.block,
            )
            routes.append(practice_route)

        quiz_item = QuizItem(
            question=definition.quiz_question,
            answer=definition.quiz_answer,
            explanation=definition.quiz_explanation,
        )
        response = LessonResponse(
            question=request.question,
            concept=concept,
            depth=depth,
            explanation=explanation,
            misconceptions=misconceptions,
            practice_scenario=practice_scenario,
            quiz_items=[quiz_item],
            provenance=[_to_provenance_reference_from_context(item) for item in retrieved_context.hits],
            prose=prose_response.block,
            teaching_plan=teaching_plan,
            model_traces=traces,
        )
        warnings.extend(_warnings_from_model_traces(traces))
        deduped_warnings = _dedupe_warnings(warnings)
        return TeachingServiceResult(
            response=response,
            warnings=deduped_warnings,
            debug=WorkspaceDebugInfo(
                workspace=WorkspaceName.TEACHING,
                primary_task=WorkspaceTask.TEACHING_ANSWER,
                routes=routes,
                retrieved=[retrieved_context],
                warnings=deduped_warnings,
                notes=[
                    'Teaching is retrieval-first and falls back to authored scaffolding when '
                    'retrieval is empty or degraded.',
                ],
            ),
        )

    def _build_prompt_client(self, trace_sink: list[ModelTraceRecord]) -> PromptModelClient | None:
        if self._selector is not None:
            selected = self._selector.require(ModelRole.PRIMARY_GENERATION)
            return RolePromptModelClient(selected, trace_sink=trace_sink)
        return self._model_client

    def _provider_name_for_role(self, role: ModelRole | None) -> str | None:
        if role is None:
            return None
        if self._selector is not None:
            return self._selector.resolve(role).provider_name
        if self._model_client is not None:
            return 'legacy'
        return None

    def _model_name_for_role(self, role: ModelRole | None) -> str | None:
        if role is None:
            return None
        if self._selector is not None:
            return self._selector.resolve(role).model_name
        if self._model_client is not None:
            return type(self._model_client).__name__
        return None

    def _resolve_depth(
        self,
        question: str,
        *,
        explicit_depth: TeachingDepth | None,
        trace_sink: list[ModelTraceRecord] | None,
    ) -> TeachingDepth:
        if explicit_depth is not None:
            return explicit_depth
        fallback = _heuristic_depth(question)
        if self._classifier is None:
            return fallback
        artifact = self._classifier.classify_teaching_depth(
            question=question,
            fallback_depth=fallback.value,
            trace_sink=trace_sink,
        )
        if artifact is None:
            return fallback
        try:
            return TeachingDepth(artifact.depth)
        except ValueError:
            return fallback

    def _infer_concept(self, question: str) -> TeachingConcept:
        normalized = question.lower()
        for keyword, concept in _KEYWORD_TO_CONCEPT.items():
            if keyword in normalized:
                return concept
        raise TeachingServiceError(f'Unsupported teaching concept in question: {question!r}.')

    def _retrieve_documents(
        self,
        request: TeachingRequest,
        concept: TeachingConcept,
    ) -> list[RetrievedDocument]:
        if self._retriever is None:
            return []
        return self._retriever.search(RetrievalQuery(text=f'{request.question} {concept.value}', k=3))


def _append_generation_trace(
    trace_sink: list[ModelTraceRecord],
    *,
    prompt_name: str,
    prompt_version: str,
    used_fallback: bool,
    validation_passed: bool,
    provider_name: str | None,
    model_name: str | None,
    outcome: str,
    role: ModelRole = ModelRole.PRIMARY_GENERATION,
) -> None:
    trace_sink.append(
        ModelTraceRecord(
            role=role,
            provider_name=provider_name,
            model_name=model_name,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            validation_passed=validation_passed,
            fallback_triggered=used_fallback,
            degraded=False,
            outcome=outcome,
        )
    )


def _heuristic_depth(question: str) -> TeachingDepth:
    normalized = question.lower()
    if any(term in normalized for term in ('advanced', 'deeper', 'why', 'interaction', 'sequence')):
        return TeachingDepth.INTERMEDIATE
    return TeachingDepth.BEGINNER


def _structured_summary(summary: str, plan: TeachingPlanArtifact) -> str:
    objectives = ' | '.join(plan.learning_objectives)
    sections = ' | '.join(plan.explanation_sections)
    return f'{summary} Objectives: {objectives}. Sections: {sections}.'


def _ordered_misconceptions(
    definition: _ConceptDefinition,
    plan: TeachingPlanArtifact,
) -> list[MisconceptionHint]:
    available = [
        MisconceptionHint(
            misconception=misconception,
            correction=correction,
            why_it_matters=why_it_matters,
        )
        for misconception, correction, why_it_matters in definition.misconceptions
    ]
    ordered: list[MisconceptionHint] = []
    seen: set[str] = set()
    focus_terms = [str(item).lower() for item in plan.misconception_focus]
    for focus in focus_terms:
        for hint in available:
            key = hint.misconception.lower()
            if key in seen:
                continue
            if focus in key or key in focus:
                ordered.append(hint)
                seen.add(key)
    for hint in available:
        key = hint.misconception.lower()
        if key not in seen:
            ordered.append(hint)
    return ordered


def _to_provenance_reference(document: RetrievedDocument) -> ProvenanceReference:
    return ProvenanceReference(
        doc_id=document.doc_id,
        chunk_id=document.chunk_id,
        source=document.source,
        title=document.title,
        score=document.score,
        excerpt=document.text,
    )


def _retrieved_context_text(documents: list[RetrievedDocument]) -> str:
    if not documents:
        return 'No additional rules corpus matched the question.'
    return ' '.join(f'{document.title}: {document.text}' for document in documents)







def _to_provenance_reference_from_context(item: RetrievedContextItem) -> ProvenanceReference:
    return ProvenanceReference(
        doc_id=item.doc_id,
        chunk_id=item.chunk_id,
        source=item.source,
        title=item.title,
        score=item.score,
        excerpt=item.excerpt,
    )


def _retrieved_context_text_from_context(context: RetrievedContext) -> str:
    if not context.hits:
        return 'No additional rules corpus matched the question.'
    return ' '.join(f'{item.title}: {item.excerpt}' for item in context.hits)


def _explanation_from_retrieval(
    definition: _ConceptDefinition,
    context: RetrievedContext,
    depth: TeachingDepth,
) -> tuple[str, list[str]]:
    authored_summary = (
        definition.beginner_summary
        if depth == TeachingDepth.BEGINNER
        else definition.intermediate_summary
    )
    authored_points = list(
        definition.beginner_points
        if depth == TeachingDepth.BEGINNER
        else definition.intermediate_points
    )
    if not context.hits:
        return authored_summary, authored_points

    sentences: list[str] = []
    for item in context.hits:
        parts = [part.strip() for part in item.excerpt.replace('?', '.').split('.') if part.strip()]
        sentences.extend(parts)

    if not sentences:
        return authored_summary, authored_points

    summary = sentences[0]
    if depth == TeachingDepth.INTERMEDIATE and authored_summary not in summary:
        summary = f'{summary} {authored_summary}'

    key_points = sentences[: len(authored_points)]
    if depth == TeachingDepth.INTERMEDIATE and definition.intermediate_summary not in key_points:
        key_points.append(definition.intermediate_summary)
    if len(key_points) < len(authored_points):
        key_points.extend(authored_points[len(key_points) :])
    return summary, key_points[: max(len(authored_points), 1)]


def _dedupe_warnings(warnings: list[ServiceWarning]) -> list[ServiceWarning]:
    deduped: list[ServiceWarning] = []
    seen: set[tuple[str, str]] = set()
    for warning in warnings:
        key = (warning.code.value, warning.message)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(warning)
    return deduped













def _warnings_from_model_traces(traces: list[ModelTraceRecord]) -> list[ServiceWarning]:
    warnings: list[ServiceWarning] = []
    for trace in traces:
        if not trace.fallback_triggered and not trace.degraded:
            continue
        message = trace.notes[0] if trace.notes else trace.outcome.replace('_', ' ')
        code = ServiceWarningCode.MODEL_UNAVAILABLE if trace.degraded else ServiceWarningCode.GENERATION_FALLBACK_USED
        warnings.append(
            ServiceWarning(
                code=code,
                message=message,
                degraded=trace.degraded,
            )
        )
    return warnings
