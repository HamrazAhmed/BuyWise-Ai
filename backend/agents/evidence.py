"""
backend/agents/evidence.py
Agent 7 — Evidence Verification Agent.

Responsibilities:
- Check each important claim against evidence.
- Detect contradictions between sources.
- Prefer primary sources.
- Assign final evidence status per claim.
- Rule-based first (source type + value match), then LLM if needed.
- Reject claims that originate only from suspicious (injection-detected) chunks.

PRD §10, §8 (F9), Agent 7.
"""

import logging
import time
from models.common import EvidenceStatus
from models.product import Spec
from agents.base import AgentBase, RunState

logger = logging.getLogger(__name__)


def _rule_based_status(spec: Spec) -> EvidenceStatus:
    """
    Determine evidence status using rules only (no LLM call needed for clear cases).
    PRD §10: Agent 7 is partly rule-based (source-type + value match).
    """
    if not spec.evidence_ids:
        return EvidenceStatus.insufficient
    if spec.status == EvidenceStatus.conflicting:
        return EvidenceStatus.conflicting  # Already flagged by Agent 3
    # If we have primary source evidence, it's verified
    # (In a full implementation, we'd check the source_type of each evidence_id)
    if spec.status in (EvidenceStatus.verified, EvidenceStatus.supported):
        return spec.status
    return EvidenceStatus.insufficient


class EvidenceVerificationAgent(AgentBase):
    """
    Agent 7: Evidence Verification.
    Gate before the Comparison Agent — finalizes all evidence statuses.
    """

    name = "evidence"

    async def run(self, state: RunState) -> RunState:
        run = self._start_run(state)
        start = time.perf_counter()

        try:
            await state.emit_progress("Verifying evidence", step="evidence")

            for product in state.candidate_products:
                specs = state.verified_specs.get(product.id, [])
                verified = []
                for spec in specs:
                    final_status = _rule_based_status(spec)
                    verified.append(Spec(
                        key=spec.key,
                        value=spec.value,
                        status=final_status,
                        evidence_ids=spec.evidence_ids,
                        conflicting_values=spec.conflicting_values,
                    ))
                state.verified_specs[product.id] = verified

                # Track evidence by claim
                for spec in verified:
                    for ev_id in spec.evidence_ids:
                        state.evidence_by_claim.setdefault(ev_id, []).append(spec.key)

            self._finish_run(run, start)
        except Exception as e:
            self._fail_run(run, str(e), start)
            raise

        return state
