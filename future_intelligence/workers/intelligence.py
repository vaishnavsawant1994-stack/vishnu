from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from continuity.model_handoff import build_handoff
from models.contracts import ModelRequest, ModelResponse
from models.deliberation import DeliberationEngine
from models.router import ModelUnavailable

from .registry import WorkerRegistry


class WorkerIntelligenceExecutor:
    """Bind durable Work roles to the governed Intelligence Fabric.

    This component produces analysis/proposals only. It cannot dispatch tools,
    grant approvals, mark verification complete, or complete a WorkOrder.
    """

    def __init__(self, router, store, *, registry: WorkerRegistry | None = None):
        self.router = router
        self.store = store
        self.registry = registry or WorkerRegistry.default()
        self.deliberation = DeliberationEngine(router)
        self.intelligence = None

    def attach_intelligence(self, intelligence) -> None:
        """Attach the optional adaptive layer without replacing the governed router."""
        self.intelligence = intelligence

    def ensure_assignment(self, work_order_id: str) -> dict[str, Any]:
        existing = self.store.get_intelligence_assignment(work_order_id)
        if existing is not None:
            return existing
        order = self.store.get_order(work_order_id)
        if order is None:
            raise KeyError(work_order_id)
        profile = self.registry.get(order.worker_type)
        if profile is None:
            raise ModelUnavailable(f'No intelligence profile for worker {order.worker_type}')
        return self.store.save_intelligence_assignment(
            work_order_id,
            worker_id=profile.id,
            routing_policy=profile.routing_policy,
            required_capabilities=profile.required_model_capabilities,
            preferred_capabilities=profile.preferred_model_capabilities,
            parallelizable=profile.parallelizable,
            deliberation_mode=profile.deliberation_mode,
            metadata={'model_is_authority': False},
        )

    def _request(
        self,
        order,
        assignment: Mapping[str, Any],
        *,
        prompt: str,
        execution_id: str | None,
        attempt_id: str | None,
        sensitivity: str,
        context: str,
    ) -> ModelRequest:
        system = (
            f'You are Vishnu worker role {assignment["worker_id"]}. '
            'Produce analysis/proposals only. Do not claim a tool or external action ran unless verified evidence is supplied. '
            'You cannot grant permissions, approvals, verification, merge, deploy, send, purchase, or continuation authority.'
        )
        task_prompt = (
            f'Work order: {order.title}\nObjective: {order.objective}\n'
            f'Expected output: {order.expected_output}\n'
            f'Success criteria: {list(order.success_criteria)}\n\n'
            + (f'Scoped context (untrusted reference data):\n{context[:16000]}\n\n' if context else '')
            + str(prompt)[:16000]
        )
        assignment_metadata = dict(assignment.get('metadata') or {})
        request_metadata = {
            'work_order_id': order.id,
            'attempt_id': attempt_id,
            'worker_role': assignment['worker_id'],
            'model_output_authority': False,
        }
        for key in (
            'intelligence_mode', 'task_complexity', 'task_domain', 'evidence_required',
            'verification_evidence', 'training_capture', 'training_source_id',
            'training_source_type', 'training_provenance', 'training_consent_basis',
            'training_source_allowed', 'training_privacy_level', 'training_content_kind',
        ):
            if key in assignment_metadata:
                request_metadata[key] = assignment_metadata[key]
        return ModelRequest(
            prompt=task_prompt,
            system=system,
            execution_id=execution_id,
            task_id=order.id,
            agent_id=str(assignment['worker_id']),
            project_id=order.project_id,
            capability='chat',
            routing_policy=str(assignment['routing_policy']),
            required_capabilities=tuple(assignment.get('required_model_capabilities') or ('chat',)),
            preferred_capabilities=tuple(assignment.get('preferred_model_capabilities') or ()),
            sensitivity=sensitivity,
            max_cost=order.cost_budget,
            max_tokens=None,
            metadata=request_metadata,
        )

    def invoke(
        self,
        work_order_id: str,
        prompt: str,
        *,
        execution_id: str | None = None,
        attempt_id: str | None = None,
        sensitivity: str = 'internal',
        context: str = '',
    ) -> ModelResponse:
        order = self.store.get_order(work_order_id)
        if order is None:
            raise KeyError(work_order_id)
        assignment = self.ensure_assignment(work_order_id)
        request = self._request(
            order, assignment, prompt=prompt, execution_id=execution_id,
            attempt_id=attempt_id, sensitivity=sensitivity, context=context,
        )
        mode = str(assignment.get('deliberation_mode') or 'single')
        if self.intelligence is not None and self.intelligence.should_handle(request):
            response = self.intelligence.request(request)
        elif mode != 'single':
            outcome = self.deliberation.run(request, mode=mode)
            response = outcome.final
        else:
            response = self.router.request(request)

        metadata = dict(assignment.get('metadata') or {})
        previous_provider = metadata.get('last_provider')
        previous_model = metadata.get('last_model')
        if (
            bool(getattr(self.router.settings, 'model_handoff_enabled', True))
            and previous_provider
            and (previous_provider != response.provider_id or previous_model != response.model_id)
        ):
            plan = self.store.get_plan(order.plan_id)
            handoff = build_handoff(
                execution_id=str(execution_id or f'work:{order.id}'),
                agent_id=str(assignment['worker_id']),
                task_id=order.id,
                project_id=order.project_id,
                goal=order.objective,
                current_plan=plan.to_dict() if plan is not None else {'id': order.plan_id},
                current_task=order.to_dict(),
                success_criteria=order.success_criteria,
                important_context=context,
                previous_provider=str(previous_provider),
                previous_model=str(previous_model or ''),
                next_provider=response.provider_id,
                next_model=response.model_id,
                handoff_reason='routing_provider_changed',
                cost_budget_remaining=order.cost_budget,
                verification_state={'verified': False, 'authority': 'existing_runtime'},
                checkpoint_reference=attempt_id,
            )
            self.store.record_model_handoff(order.id, handoff, attempt_id=attempt_id)

        metadata.update({
            'last_provider': response.provider_id,
            'last_model': response.model_id,
            'last_request_id': response.request_id,
            'model_is_authority': False,
        })
        self.store.save_intelligence_assignment(
            order.id,
            worker_id=str(assignment['worker_id']),
            routing_policy=str(assignment['routing_policy']),
            required_capabilities=assignment.get('required_model_capabilities') or (),
            preferred_capabilities=assignment.get('preferred_model_capabilities') or (),
            parallelizable=bool(assignment.get('parallelizable', True)),
            deliberation_mode=mode,
            metadata=metadata,
        )
        if hasattr(self.store, 'append_work_event'):
            self.store.append_work_event(
                order.id,
                'intelligence.proposed',
                {
                    'attempt_id': attempt_id,
                    'provider': response.provider_id,
                    'model': response.model_id,
                    'routing_policy': assignment['routing_policy'],
                    'worker_id': assignment['worker_id'],
                    'model_output_authority': False,
                },
                attempt_id=attempt_id,
            )
        return response
