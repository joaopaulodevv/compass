"""Knowledge retrieval, exposed as a tool.

Unlike the financial tools, this one reads nothing belonging to a user: the corpus is the
same for everyone. It therefore takes no `user_id`, which is also why the agent's toolbox
injects the identity only into tools whose schema asks for it.

What comes back always carries its provenance and its age. A model that cites a source can
be checked; a model that recalls a product's conditions from training cannot, and that is
the failure this tool exists to prevent.
"""

from __future__ import annotations

from typing import Any

from compass_api.knowledge.base import (
    DEFAULT_TOP_K,
    MAX_TOP_K,
    ensure_ingested,
    get_knowledge_base,
)

STALE_NOTE = "This passage may be out of date. Say so if you use it."


async def search_financial_knowledge(query: str, top_k: int = DEFAULT_TOP_K) -> dict[str, Any]:
    """Search Compass's curated financial knowledge.

    Use this for anything about how financial products or concepts work - liquidity, risk,
    emergency funds, fixed income, planning - instead of answering from memory. Cite the
    source of any passage you use, and say when a passage is marked as possibly outdated.

    Returns passages with their source, the date they were retrieved and their age in days.
    """
    base = await ensure_ingested(get_knowledge_base())
    found = await base.search(query, min(top_k, MAX_TOP_K))

    return {
        "query": query,
        "results": [
            {
                "title": item.chunk.title,
                "text": item.chunk.text,
                "score": item.score,
                "source": item.chunk.provenance.source,
                "url": item.chunk.provenance.url,
                "category": item.chunk.provenance.category,
                "retrieved_at": item.chunk.provenance.retrieved_at.isoformat(),
                "valid_from": (
                    item.chunk.provenance.valid_from.isoformat()
                    if item.chunk.provenance.valid_from
                    else None
                ),
                "age_days": item.age_days,
                "is_stale": item.is_stale,
                **({"note": STALE_NOTE} if item.is_stale else {}),
            }
            for item in found
        ],
    }


#: Tools that read shared knowledge rather than a user's own data.
KNOWLEDGE_TOOLS = (search_financial_knowledge,)
