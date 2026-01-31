"""
Explanation Service - Natural Language Explanation Generation

Generates human-readable explanations of decisions using LLM,
based on ground truth data from the decision graph.
"""
import logging
from typing import Dict, Any

from .gemini_service import gemini_service

logger = logging.getLogger(__name__)


async def generate_decision_explanation(decision: Dict[str, Any]) -> str:
    """
    Generate natural language explanation of decision.
    
    Takes raw decision data from Neo4j and formats it into
    a clear, readable explanation with full context.
    
    Args:
        decision: Decision data dictionary from graph
        
    Returns:
        Human-readable explanation string
    """
    if not gemini_service.is_available():
        logger.warning("Gemini not available, using template explanation")
        return _template_explanation(decision)
    
    prompt = f"""You are an expert at explaining business decisions clearly and concisely.

DECISION DATA:
{_format_decision_for_prompt(decision)}

TASK:
Generate a comprehensive explanation of this decision in natural language.

STRUCTURE YOUR EXPLANATION:

## Summary
1-2 sentences: What was decided, when, by whom

## Why It Was Approved/Rejected
1 paragraph: Business justification and reasoning

## Evidence at Decision Time
Bullet points: Key data points that informed the decision (with sources and timestamps)

## Policy Context
1 paragraph: Which policy was in effect, any exceptions made

## Precedent (if applicable)
Similar past decisions that influenced this one

TONE: Professional, clear, factual. Use past tense. Be specific with numbers and dates.

IMPORTANT:
- This is GROUND TRUTH, not speculation - only state facts from the data
- Include exact timestamps to show when data was captured
- Highlight any policy exceptions with clear justification
- If precedents exist, explain HOW they influenced the decision

Generate the explanation now:"""
    
    try:
        response = gemini_service._model.generate_content(prompt)
        explanation = response.text.strip()
        
        logger.info(f"Generated explanation for decision {decision.get('id', 'unknown')}")
        return explanation
    
    except Exception as e:
        logger.error(f"Failed to generate explanation: {e}")
        # Fallback to template-based explanation
        return _template_explanation(decision)


def _format_decision_for_prompt(decision: Dict[str, Any]) -> str:
    """Format decision data for LLM prompt."""
    
    formatted = f"""
DECISION ID: {decision.get('id')}
TIMESTAMP: {decision.get('timestamp')}
OUTCOME: {decision.get('outcome')}

REQUEST:
- Customer: {decision.get('customer_name')}
- Requested: {decision.get('requested_action')}
- Requestor: {decision.get('requestor_email')}
- Reason: {decision.get('request_reason')}

DECISION:
- Final Action: {decision.get('final_action')}
- Decision Maker: {decision.get('decision_maker_email')}
- Reasoning: {decision.get('decision_reasoning')}

EVIDENCE:
"""
    
    evidence_list = decision.get('evidence', [])
    if evidence_list:
        for evidence in evidence_list:
            field = evidence.get('field', 'unknown')
            value = evidence.get('value', 'N/A')
            source = evidence.get('source', 'unknown')
            captured_at = evidence.get('captured_at', 'unknown')
            formatted += f"- {field}: {value} (from {source} at {captured_at})\n"
    else:
        formatted += "- No evidence captured\n"
    
    policy = decision.get('policy')
    if policy:
        formatted += f"""
POLICY:
- Version: {policy.get('version')}
- Effective From: {policy.get('effective_from')}
- Standard Limit: {policy.get('standard_limit')}
- Manager Limit: {policy.get('manager_limit')}
"""
    
    precedents = decision.get('precedents', [])
    if precedents:
        formatted += "\nPRECEDENTS:\n"
        for prec in precedents:
            formatted += f"- {prec.get('customer', 'Unknown')}: {prec.get('final_action', 'Unknown')} on {prec.get('timestamp', 'Unknown')}\n"
    
    return formatted


def _template_explanation(decision: Dict[str, Any]) -> str:
    """Fallback template-based explanation if LLM fails."""
    
    outcome = decision.get('outcome', 'Unknown').title()
    final_action = decision.get('final_action', 'Unknown')
    customer = decision.get('customer_name', 'Unknown')
    timestamp = decision.get('timestamp', 'Unknown')
    decision_maker = decision.get('decision_maker_email', 'Unknown')
    reasoning = decision.get('decision_reasoning', 'No reasoning provided')
    
    explanation = f"""## Decision: {outcome}

**Summary:** {final_action} for {customer} on {timestamp}.

**Decision Maker:** {decision_maker}

**Reasoning:** {reasoning}

## Evidence at Decision Time
"""
    
    evidence_list = decision.get('evidence', [])
    if evidence_list:
        for evidence in evidence_list:
            field = evidence.get('field', 'unknown')
            value = evidence.get('value', 'N/A')
            source = evidence.get('source', 'unknown')
            captured_at = evidence.get('captured_at', 'unknown')
            explanation += f"- **{field}** ({source}): {value} - captured at {captured_at}\n"
    else:
        explanation += "- No evidence captured\n"
    
    policy = decision.get('policy')
    if policy:
        explanation += f"\n## Policy Context\nPolicy version {policy.get('version')} was in effect. "
        explanation += f"Standard limit: {policy.get('standard_limit', 'N/A')}, "
        explanation += f"Manager limit: {policy.get('manager_limit', 'N/A')}.\n"
    
    precedents = decision.get('precedents', [])
    if precedents:
        explanation += "\n## Precedents Considered\n"
        for prec in precedents:
            explanation += f"- {prec.get('customer', 'Unknown')}: {prec.get('outcome', 'Unknown')} on {prec.get('timestamp', 'Unknown')}\n"
    
    return explanation


async def generate_similarity_explanation(
    decision1: Dict[str, Any],
    decision2: Dict[str, Any],
    similarity_score: float
) -> str:
    """
    Generate explanation of why two decisions are similar.
    
    Args:
        decision1: First decision data
        decision2: Second decision data
        similarity_score: Calculated similarity score
        
    Returns:
        Human-readable similarity explanation
    """
    summary1 = _create_brief_summary(decision1)
    summary2 = _create_brief_summary(decision2)
    
    return await gemini_service.explain_decision_similarity(
        summary1,
        summary2,
        similarity_score
    )


def _create_brief_summary(decision: Dict[str, Any]) -> str:
    """Create brief text summary of a decision for similarity comparison."""
    
    customer = decision.get('customer_name', 'Unknown')
    outcome = decision.get('outcome', 'Unknown')
    final_action = decision.get('final_action', 'Unknown')
    industry = decision.get('customer_industry', 'Unknown')
    arr = decision.get('customer_arr', 'Unknown')
    reason = decision.get('request_reason', '')
    reasoning = decision.get('decision_reasoning', '')
    
    return f"""
Customer: {customer} ({industry}, ARR: {arr})
Outcome: {outcome} at {final_action}
Request reason: {reason}
Decision reasoning: {reasoning}
""".strip()
