#!/usr/bin/env python3
"""
Shared utilities for AI4SS content curation scripts.
Provides URL normalization, dedup registry, taxonomy loading, and relevance scoring.
"""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path
from typing import Dict, List, Optional, Set


# ============================================
# URL Normalization & Dedup
# ============================================

def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication.
    Strips tracking params, trailing slashes, www prefix, fragments.
    """
    url = url.strip().lower()
    if not url:
        return ""

    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return url

    # Remove www. prefix
    host = parsed.hostname or ""
    if host.startswith("www."):
        host = host[4:]

    # Remove tracking parameters
    tracking_params = {
        "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
        "ref", "source", "fbclid", "gclid", "mc_cid", "mc_eid",
    }
    if parsed.query:
        params = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)
        filtered = {k: v for k, v in params.items() if k.lower() not in tracking_params}
        query = urllib.parse.urlencode(filtered, doseq=True)
    else:
        query = ""

    # Rebuild without fragment, with cleaned query
    path = parsed.path.rstrip("/")
    if query:
        return f"{parsed.scheme}://{host}{path}?{query}"
    return f"{parsed.scheme}://{host}{path}"


def build_dedup_registry(repo_root: str | Path) -> Set[str]:
    """Scan existing _skills/, _papers/, _resources/ for URLs already in the site."""
    repo_root = Path(repo_root).resolve()
    existing_urls: Set[str] = set()

    collection_dirs = ["_skills", "_papers", "_resources"]
    for coll_dir in collection_dirs:
        coll_path = repo_root / coll_dir
        if not coll_path.exists():
            continue
        for md_file in coll_path.rglob("*.md"):
            if md_file.name == "index.md":
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
            except Exception:
                continue
            # Extract link from frontmatter
            link = _extract_frontmatter_field(text, "link")
            if link:
                existing_urls.add(normalize_url(link))
    return existing_urls


def _extract_frontmatter_field(text: str, field: str) -> Optional[str]:
    """Extract a single field value from YAML frontmatter."""
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        if key.strip() == field:
            return val.strip().strip('"').strip("'")
    return None


# ============================================
# Taxonomy & Keywords
# ============================================

# Social science domain keywords for relevance scoring
SOCIAL_SCIENCE_KEYWORDS = [
    # Disciplines
    "social science", "political science", "economics", "sociology",
    "psychology", "public policy", "communication", "anthropology",
    "education", "linguistics",
    # Methods
    "causal inference", "survey", "experiment", "regression",
    "natural language processing", "nlp", "text analysis",
    "network analysis", "machine learning", "deep learning",
    "mixed methods", "qualitative", "quantitative",
    # Workflow
    "literature review", "research design", "data collection",
    "data analysis", "academic writing", "visualization",
    "reproducibility", "open science", "replication",
    # Tools
    "stata", "spss", "r language", "python", "jupyter",
    "tableau", "gephi", "atlas.ti", "nvivo",
    # AI specific
    "llm", "large language model", "gpt", "claude", "ai agent",
    "prompt engineering", "rag", "fine-tuning",
    # Chinese keywords
    "社会科学", "政治学", "经济学", "社会学", "心理学",
    "因果推断", "文本分析", "数据分析", "论文", "研究",
]


def load_taxonomy_keywords(repo_root: str | Path) -> List[str]:
    """Load additional keywords from _data/taxonomy.yml if available."""
    taxonomy_path = Path(repo_root).resolve() / "_data" / "taxonomy.yml"
    if not taxonomy_path.exists():
        return SOCIAL_SCIENCE_KEYWORDS

    keywords = list(SOCIAL_SCIENCE_KEYWORDS)
    try:
        text = taxonomy_path.read_text(encoding="utf-8")
        # Simple extraction of en: values from taxonomy
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("en:"):
                val = line.split(":", 1)[1].strip()
                if val and val not in keywords:
                    keywords.append(val.lower())
            elif line.startswith("zh:"):
                val = line.split(":", 1)[1].strip()
                if val and val not in keywords:
                    keywords.append(val)
    except Exception:
        pass
    return keywords


# ============================================
# Relevance Scoring
# ============================================

# Source trust tiers
SOURCE_TRUST = {
    "semantic-scholar": 3,
    "semanticscholar": 3,
    "arxiv": 3,
    "github": 2,
    "huggingface": 2,
    "paperswithcode": 2,
    "reddit": 1,
    "hackernews": 1,
}


def score_relevance(
    title: str,
    description: str,
    source: str,
    *,
    stars: int = 0,
    upvotes: int = 0,
    citations: int = 0,
    keywords: Optional[List[str]] = None,
) -> float:
    """Score a result's relevance to AI4SS (0-10 scale).

    Score = keyword_match (0-5) + source_trust (0-3) + popularity (0-2)
    """
    if keywords is None:
        keywords = SOCIAL_SCIENCE_KEYWORDS

    text = f"{title} {description}".lower()

    # Keyword match score (0-5)
    hits = sum(1 for kw in keywords if kw.lower() in text)
    keyword_score = min(hits, 5)

    # Source trust score (0-3)
    trust_score = SOURCE_TRUST.get(source.lower(), 1)

    # Popularity score (0-2)
    popularity = max(stars, upvotes, citations)
    if popularity >= 1000:
        pop_score = 2.0
    elif popularity >= 100:
        pop_score = 1.5
    elif popularity >= 20:
        pop_score = 1.0
    elif popularity >= 5:
        pop_score = 0.5
    else:
        pop_score = 0.0

    return keyword_score + trust_score + pop_score


# ============================================
# Jekyll File Generation Helpers
# ============================================

def slugify(value: str) -> str:
    """Generate a URL-safe slug from a string."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return slug[:60] or "item"


def yaml_quote(value: str) -> str:
    """Quote a value for YAML frontmatter."""
    safe = str(value or "").replace('"', '\\"')
    return f'"{safe}"'
