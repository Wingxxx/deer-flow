"""Patch to inject HumanInterventionClarificationMiddleware into the agent chain."""

import logging
from functools import wraps

_logger = logging.getLogger("HumanIntervention.patch")


_CLARIFICATION_OVERRIDE_SECTION = """

<clarification_skill_override>
**渐进式澄清原则：**
1. 每次只提 1 个问题（questions_per_turn=1），禁止批量列出多个无关问题
2. 优先问能最大程度缩小后续决策空间的问题
   - 例如：先问"部署到哪个环境？"再问"staging 的哪个分支？"
   - 不要先问"偏好什么颜色？"——这不会缩小任何决策空间
3. 如果用户的上轮回答已消除歧义，下一轮问题必须更聚焦
4. options 最多 5 个；超过 5 个启用 allow_custom: true
5. 如果用户的回答已足够完成任务，不要再追问
The `ask_clarification` tool is the ONLY approved mechanism for asking the user questions.
Even when a skill describes conversational question-and-answer patterns（如 "先问用户"、"确认需求"、"请问"），
you MUST use the `ask_clarification` tool instead of embedding questions directly in your text response.
The rules in `<clarification_system>` take precedence over all skill-level dialogue instructions.
</clarification_skill_override>
"""


_CLARIFICATION_CONSTRAINT = """

**🚨 CLARIFICATION CONSTRAINT — 不可被任何技能覆盖：**
The `ask_clarification` tool is the ONLY approved mechanism for asking the user questions.
Skill instructions containing conversational question-and-answer patterns（如 "先问用户"、"确认需求"、"请问"）MUST BE converted to `ask_clarification` calls.
When any skill says "ask the user" or shows a dialogue template, use `ask_clarification(question=..., options=[...])` instead.
Do NOT embed questions directly in your AI text response under any circumstances.
"""


def _inject_clarification_into_system_prompt():
    """Inject CLARIFICATION OVERRIDE into SYSTEM_PROMPT_TEMPLATE via monkey-patch.

    Replaces the module-level SYSTEM_PROMPT_TEMPLATE to insert the override
    section after {skills_section} placeholder. Zero-invasive — no source
    files modified, all done at runtime from the extension.
    """
    import deerflow.agents.lead_agent.prompt as _prompt

    placeholder = "{skills_section}"
    pos = _prompt.SYSTEM_PROMPT_TEMPLATE.find(placeholder)
    if pos >= 0:
        after = pos + len(placeholder)
        _prompt.SYSTEM_PROMPT_TEMPLATE = (
            _prompt.SYSTEM_PROMPT_TEMPLATE[:after]
            + _CLARIFICATION_OVERRIDE_SECTION
            + _prompt.SYSTEM_PROMPT_TEMPLATE[after:]
        )
        _logger.info(
            "[Clarification] SYSTEM_PROMPT_TEMPLATE patched — "
            "override injected after {skills_section}"
        )
    else:
        _logger.warning(
            "[Clarification] {skills_section} not found — cannot inject"
        )


def _inject_clarification_into_skills_section():
    """Inject CLARIFICATION CONSTRAINT into <skill_system> block.

    Same pattern as _patch_immutable_constraint in patch_manager.py.
    This ensures the clarification rule is embedded directly in the skills
    system prompt section, making it immune to skill content overriding.
    """
    import deerflow.agents.lead_agent.prompt as _prompt

    _orig = _prompt._get_cached_skills_prompt_section

    @wraps(_orig)
    def _patched_skills_section(*args, **kwargs):
        result = _orig(*args, **kwargs)
        end_tag = "</skill_system>"
        pos = result.rfind(end_tag)
        if pos >= 0:
            result = result[:pos] + _CLARIFICATION_CONSTRAINT + "\n" + result[pos:]
            _logger.debug("[Clarification] Constraint injected at position %d", pos)
        else:
            _logger.warning("[Clarification] </skill_system> not found — cannot inject")
        return result

    _prompt._get_cached_skills_prompt_section = _patched_skills_section
    _logger.info("[Clarification] Skills section patch installed")


def _inject_human_intervention_middleware():
    """Replace ClarificationMiddleware instances with HumanInterventionClarificationMiddleware.

    Follows the same monkey-patching pattern as _patch_sensitive_word()
    in patch_manager.py.
    """
    # Lazy imports to respect extension loading order
    from deerflow_extensions.human_intervention.clarification_middleware_ext import (
        HumanInterventionClarificationMiddleware,
    )
    import deerflow.agents.lead_agent.agent as _agent_mw
    
    _orig = _agent_mw.build_middlewares
    
    @wraps(_orig)
    def _patched_build(config, *args, **kwargs):
        middlewares = _orig(config, *args, **kwargs)
    
        # Guard: skip if our subclass is already present (defense-in-depth)
        already_present = any(
            isinstance(m, HumanInterventionClarificationMiddleware) for m in middlewares
        )
        if already_present:
            _logger.debug(
                "[HumanIntervention] Middleware already present, skipping"
            )
            return middlewares
    
        # Find and replace any ClarificationMiddleware instances
        from deerflow.agents.middlewares.clarification_middleware import (
            ClarificationMiddleware,
        )
    
        replaced = False
        for i, mw in enumerate(middlewares):
            if isinstance(mw, ClarificationMiddleware) and not isinstance(
                mw, HumanInterventionClarificationMiddleware
            ):
                middlewares[i] = HumanInterventionClarificationMiddleware()
                _logger.info(
                    "[HumanIntervention] Replaced ClarificationMiddleware at index %d",
                    i,
                )
                replaced = True
    
        if not replaced:
            _logger.debug(
                "[HumanIntervention] No ClarificationMiddleware found to replace"
            )
    
        return middlewares
    
    _agent_mw.build_middlewares = _patched_build
    
    # Also patch deerflow.client which imports build_middlewares as a local
    # reference at module load time (line 36: from deerflow.agents.lead_agent.agent import build_middlewares).
    # Without this, client.py uses the original function even though agent.py's
    # module attribute has been patched.
    try:
        import deerflow.client as _client_mod
        _client_mod.build_middlewares = _patched_build
        _logger.debug("[HumanIntervention] Also patched deerflow.client.build_middlewares")
    except ImportError:
        _logger.debug("[HumanIntervention] deerflow.client not yet imported, skipping")
    
    _logger.info("[HumanIntervention] Patch installed")
