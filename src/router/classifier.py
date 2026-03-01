"""Keyword-based task classifier producing ClassificationResult."""

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING, Optional

from router.models import ClassificationResult, TaskType, estimate_tokens

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from router.config import EmbeddingConfig

# ---------------------------------------------------------------------------
# Keyword sets per task type (order matters: checked top-to-bottom)
# ---------------------------------------------------------------------------

_REASONING_KEYWORDS = [
    r"\bsolve\b", r"\bprove\b", r"\bproof\b", r"\blogic\b", r"\blogical\b",
    r"\bpuzzle\b", r"\bparadox\b", r"\bdeduce\b", r"\binfer\b", r"\breasoning\b",
    r"\bstep.by.step\b", r"\bwalk.through\b", r"\bdemonstrate\b", r"\bderive\b",
    r"\birrational\b", r"\bprime\b", r"\bmathematical\b", r"\bequation\b",
    r"\bhypothes[ie]s\b", r"\bsyllogism\b", r"\bif.then\b", r"\bcontradict\b",
    # Expanded: math operations and formal reasoning
    r"\bcalculate\b", r"\bcompute\b", r"\bdetermine whether\b", r"\bdetermine\b",
    r"\bgiven that\b", r"\bif and only if\b", r"\bwhat if\b", r"\bsuppose\b",
    r"\boptimize\b", r"\boptimal\b", r"\btheorem\b", r"\bcorollary\b",
    r"\bcounterexample\b", r"\bprobabilit", r"\bformula\b", r"\bsequence\b",
    r"\bvalid argument\b", r"\bdeductive\b", r"\binductive\b",
]

_KNOWLEDGE_KEYWORDS = [
    r"\banalyze\b", r"\banalysis\b", r"\bevaluate\b", r"\bassess\b",
    r"\bstrategy\b", r"\bstrategic\b", r"\breport\b", r"\bmarket\b",
    r"\bbusiness\b", r"\btrade.off\b", r"\bcompare\b", r"\bcontrast\b",
    r"\badvantage\b", r"\bdisadvantage\b", r"\bpros and cons\b", r"\brisk\b",
    r"\bopportunity\b", r"\bcompetitor\b", r"\bindustry\b", r"\btrend\b",
    r"\bforecast\b", r"\brecommend\b", r"\badvise\b", r"\bconsult\b",
    # Expanded: professional/enterprise language
    r"\bbest practice", r"\bexecutive summary\b", r"\broi\b", r"\bstakeholder\b",
    r"\bproposal\b", r"\bframework\b", r"\bplanning\b", r"\bimpact\b",
    r"\bdecision\b", r"\bresearch\b", r"\blandscape\b", r"\bwhite paper\b",
    r"\bkpi\b", r"\bkey performance\b", r"\bcompetitive\b",
]

_CODE_KEYWORDS = [
    r"\bcode\b", r"\bfunction\b", r"\bprogram\b", r"\bscript\b",
    r"\bdebug\b", r"\brefactor\b", r"\bimplementation\b", r"\bimplement\b",
    r"\bclass\b", r"\bmethod\b", r"\balgorithm\b", r"\bapi\b",
    r"\bsyntax\b", r"\bbug\b", r"\berror\b", r"\bexception\b",
    r"\bunit test\b", r"\bpython\b", r"\bjavascript\b", r"\btypescript\b",
    r"\brust\b", r"\bgolang\b", r"\bjava\b", r"\bc\+\+\b", r"\bsql\b",
    r"\bwrite a.*(function|class|script|test)\b",
    # Expanded: DevOps and tooling
    r"\bdocker\b", r"\bkubernetes\b", r"\bk8s\b", r"\bdeploy\b",
    r"\bgit\b", r"\bbash\b", r"\bshell script\b", r"\bterminal\b",
    r"\bcli\b", r"\blibrary\b", r"\bdependency\b", r"\bpackage\b",
    r"\brepository\b", r"\bpull request\b", r"\bci/cd\b", r"\bpipeline\b",
    r"\bcompiler\b", r"\btype error\b", r"\bruntime error\b",
]

_EXTRACTION_KEYWORDS = [
    r"\bsummariz", r"\bsummary\b", r"\btranslat", r"\bextract\b",
    r"\blist\s+all\b", r"\bpull out\b", r"\bidentify all\b",
    r"\bconvert\b", r"\bparaphrase\b", r"\bcondense\b", r"\bshorten\b",
    r"\bnotes\b", r"\bbullet points?\b", r"\bkey points?\b",
    r"\bwhat does.*(say|mean)\b", r"\bwhat (is|are) the main\b",
    # Expanded: retrieval and listing
    r"\bkey takeaway", r"\benumerate\b", r"\blist out\b", r"\bfind all\b",
    r"\bgather\b", r"\bitemize\b", r"\btop \d+\b", r"\btl;?dr\b",
    r"\bin brief\b", r"\bmain point", r"\bhighlight", r"\bwhat are the\b",
]

_CREATIVE_KEYWORDS = [
    r"\bwrite .{0,20}(poem|story|song|haiku|sonnet|essay|blog)\b",
    r"\bcreative\b", r"\bimagine\b", r"\bbrainstorm\b", r"\bfiction\b",
    r"\bcharacter\b", r"\bnarrative\b", r"\bplot\b", r"\bmetaphor\b",
    r"\binvent\b", r"\boriginal\b", r"\binspir\b",
    # Standalone genre nouns
    r"\bpoem\b", r"\bhaiku\b", r"\bsonnet\b",
    # Expanded: marketing and drafting creative content
    r"\btagline\b", r"\bslogan\b", r"\bpitch\b", r"\bdraft a\b",
    r"\bcompose\b", r"\bmarketing copy\b", r"\badvertisement\b",
    r"\bwrite me a\b", r"\bstorytelling\b", r"\bcatchy\b", r"\bcreate a (story|poem|narrative|slogan)\b",
]

_TOOLS_KEYWORDS = [
    r"\bjson\b", r"\bxml\b", r"\bcsv\b", r"\bstructured output\b",
    r"\bschedule\b", r"\bcalendar\b", r"\bcreate a plan\b", r"\bworkflow\b",
    r"\bform\b", r"\bfill in\b", r"\btemplate\b",
]

_FACTUALITY_KEYWORDS = [
    r"\bverify\b", r"\bfact.check\b", r"\baccurate\b", r"\bsource\b",
    r"\bcite\b", r"\breference\b", r"\bstatistic\b", r"\bdata\b",
    r"\bpeer.reviewed\b", r"\bscientific\b", r"\bproven\b", r"\bevidence\b",
]


def _matches(text: str, patterns: list[str]) -> int:
    """Return count of pattern matches in lowercased text."""
    low = text.lower()
    return sum(1 for p in patterns if re.search(p, low))


def _complexity_score(
    text: str,
    token_estimate: int,
    task_type: TaskType,
    keyword_hits: int,
) -> float:
    """
    Heuristic complexity score 0.0–1.0.
    Factors: token length, multi-step language, task type base,
             keyword density, question count, domain jargon.
    """
    score = 0.0
    low = text.lower()

    # Token length factor (longer → more complex)
    if token_estimate > 500:
        score += 0.3
    elif token_estimate > 200:
        score += 0.2
    elif token_estimate > 50:
        score += 0.1

    # Multi-step language (up to 0.2)
    multi_step = len(re.findall(
        r"\b(step|first|second|third|then|finally|next|after that|additionally|furthermore|moreover)\b",
        low
    ))
    score += min(0.2, multi_step * 0.05)

    # Multiple questions → multi-faceted request (up to 0.1)
    question_count = text.count("?")
    if question_count >= 3:
        score += 0.1
    elif question_count >= 2:
        score += 0.05

    # Domain-specific jargon density boosts complexity (up to 0.1)
    _JARGON = [
        r"\beigenvalue\b", r"\bgradient\b", r"\bderivative\b", r"\bintegral\b",
        r"\bregression\b", r"\bpolymorphism\b", r"\basync\b", r"\bconcurren",
        r"\bdistributed\b", r"\bmicroservice\b", r"\bencrypt", r"\boutput token\b",
        r"\blatency\b", r"\bthroughput\b", r"\bstakeholder\b", r"\bcompliance\b",
    ]
    jargon_hits = sum(1 for p in _JARGON if re.search(p, low))
    score += min(0.1, jargon_hits * 0.03)

    # Task type base complexity
    base = {
        TaskType.reasoning: 0.5,
        TaskType.knowledge_work: 0.4,
        TaskType.code: 0.4,
        TaskType.extraction: 0.1,
        TaskType.creative: 0.3,
        TaskType.general: 0.2,
    }
    score += base[task_type]

    return round(min(1.0, score), 2)


def _try_embedding_classify(
    text: str,
    cfg: "EmbeddingConfig",
) -> Optional[TaskType]:
    """
    Attempt embedding-based classification. Returns None immediately if:
      - corpus is not initialized
      - the embedding call fails for any reason
      - the k-NN vote does not reach unanimity above threshold
    """
    import router.embeddings as _emb
    if not _emb.is_corpus_initialized():
        return None
    try:
        client = _emb.EmbeddingClient(
            base_url=cfg.base_url,
            model=cfg.model,
        )
        query_vec = client.embed_text(text)
    except Exception as exc:
        logger.debug("Embedding classify failed: %s", exc)
        return None
    return _emb.classify_by_similarity(
        query_vec,
        k=cfg.top_k,
        threshold=cfg.similarity_threshold,
    )


def classify_request(
    messages: list[dict],
    embedding_config: Optional["EmbeddingConfig"] = None,
) -> ClassificationResult:
    """Classify a request by task type, complexity, and flags."""
    # Use the last user message as the primary signal
    text = " ".join(
        m.get("content", "")
        for m in messages
        if m.get("role") in ("user", "system")
    )

    token_estimate = estimate_tokens(text)
    requires_tools = bool(_matches(text, _TOOLS_KEYWORDS))
    factuality_risk = bool(_matches(text, _FACTUALITY_KEYWORDS))

    # Classify: try each type in priority order, pick highest-signal match
    candidates: list[tuple[int, TaskType]] = [
        (_matches(text, _REASONING_KEYWORDS), TaskType.reasoning),
        (_matches(text, _CODE_KEYWORDS), TaskType.code),
        (_matches(text, _EXTRACTION_KEYWORDS), TaskType.extraction),
        (_matches(text, _KNOWLEDGE_KEYWORDS), TaskType.knowledge_work),
        (_matches(text, _CREATIVE_KEYWORDS), TaskType.creative),
    ]

    # Pick the type with the most keyword hits (min 1 to qualify)
    best_hits, task_type = max(candidates, key=lambda x: x[0])
    if best_hits == 0:
        task_type = TaskType.general

    # Embedding refinement (optional, no-op if disabled or unavailable)
    if embedding_config is not None and embedding_config.enabled:
        override = _try_embedding_classify(text, embedding_config)
        if override is not None:
            task_type = override

    complexity = _complexity_score(text, token_estimate, task_type, best_hits)

    return ClassificationResult(
        task_type=task_type,
        complexity=complexity,
        token_estimate=token_estimate,
        requires_tools=requires_tools,
        factuality_risk=factuality_risk,
    )
