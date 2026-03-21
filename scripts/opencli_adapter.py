#!/usr/bin/env python3
"""
OpenCLI Adapter for AI4SS content curation.
Wraps the `opencli` CLI tool to run keyword searches across multiple web platforms,
then maps results to a common schema for scoring and Jekyll file generation.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from ai4ss_utils import normalize_url


# ============================================
# Platform Registry
# ============================================

# Each platform defines:
#   search_style: how the CLI accepts queries
#     "positional" = opencli <platform> search "query"
#     "flag"       = opencli <platform> search --query "query"
#     "top_only"   = no search, only opencli <platform> top
#   fields: maps platform-specific JSON keys to our schema
#   url_prefix: optional prefix to build full URLs from IDs
#   content_hint: default content type hint

PUBLIC_PLATFORMS = {
    "arxiv": {
        "search_style": "positional",
        "fields": {"title": "title", "url": "id", "popularity": None, "description": "title", "extra": "authors"},
        "url_prefix": "https://arxiv.org/abs/",
        "content_hint": "paper",
    },
    "stackoverflow": {
        "search_style": "flag",
        "fields": {"title": "title", "url": "url", "popularity": "score", "description": "title"},
        "content_hint": "qa",
    },
    "wikipedia": {
        "search_style": "positional",
        "fields": {"title": "title", "url": "url", "popularity": None, "description": "snippet"},
        "content_hint": "reference",
    },
    "hackernews": {
        "search_style": "top_only",
        "fields": {"title": "title", "url": "url", "popularity": "points", "description": "title"},
        "content_hint": "tech_news",
    },
    "weread": {
        "search_style": "positional",
        "fields": {"title": "title", "url": "bookId", "popularity": "rank", "description": "author"},
        "url_prefix": "https://weread.qq.com/web/bookDetail/",
        "content_hint": "book",
    },
    "apple-podcasts": {
        "search_style": "positional",
        "fields": {"title": "title", "url": "id", "popularity": "episodes", "description": "author"},
        "url_prefix": "https://podcasts.apple.com/podcast/id",
        "content_hint": "podcast",
    },
}

COOKIE_PLATFORMS = {
    "twitter": {
        "search_style": "flag",
        "fields": {"title": "text", "url": "url", "popularity": "likes", "description": "text"},
        "content_hint": "social",
    },
    "reddit": {
        "search_style": "positional",
        "fields": {"title": "title", "url": "url", "popularity": "score", "description": "title"},
        "content_hint": "discussion",
    },
    "bilibili": {
        "search_style": "positional",
        "fields": {"title": "title", "url": "url", "popularity": "score", "description": "title"},
        "content_hint": "video",
    },
    "zhihu": {
        "search_style": "positional",
        "fields": {"title": "title", "url": "url", "popularity": None, "description": "title"},
        "content_hint": "qa",
    },
    "xiaohongshu": {
        "search_style": "positional",
        "fields": {"title": "title", "url": "url", "popularity": "likes", "description": "title"},
        "content_hint": "social",
    },
    "youtube": {
        "search_style": "positional",
        "fields": {"title": "title", "url": "url", "popularity": "views", "description": "title"},
        "content_hint": "video",
    },
}

ALL_PLATFORMS = {**PUBLIC_PLATFORMS, **COOKIE_PLATFORMS}


# ============================================
# Content Type & Subcategory Classification
# ============================================

# --- Top-level type signals ---
PAPER_SIGNALS = [
    "paper", "arxiv", "论文", "study", "journal", "conference",
    "icml", "neurips", "acl", "emnlp", "aaai", "iclr",
]
SKILL_SIGNALS = [
    "skill", "workflow", "tutorial", "how-to", "guide", "教程",
    "prompt", "agent", "claude", "技巧", "方法",
]
RESOURCE_SIGNALS = [
    "tool", "toolkit", "package", "library", "framework", "dataset",
    "工具", "开源", "repository", "platform", "software",
]

# --- Skill subcategory signals (maps to _skills/<category>/) ---
SKILL_SUBCATEGORIES = {
    "analysis": [
        "data analysis", "statistics", "regression", "stata", "spss", "r language",
        "python data", "pandas", "visualization", "causal inference", "econometrics",
        "statistical", "quantitative", "modeling",
        "数据分析", "统计", "可视化", "因果推断", "回归",
    ],
    "writing": [
        "writing", "write", "draft", "paper writing", "academic writing", "latex",
        "manuscript", "proofreading", "editor", "论文写作", "写作", "撰写",
    ],
    "design": [
        "research design", "methodology", "experiment design", "survey design",
        "open science", "reproducibility", "preregistration", "研究设计", "开放科学",
    ],
    "research-engineering": [
        "agent", "claude", "llm", "gpt", "automation", "pipeline", "code",
        "programming", "engineering", "api", "scraping", "自动化", "编程", "工程",
    ],
}

# --- Paper subcategory signals (maps to _papers/ frontmatter category) ---
PAPER_SUBCATEGORIES = {
    "methodology": [
        "method", "framework", "approach", "technique", "algorithm", "model",
        "方法", "算法", "框架",
    ],
    "application": [
        "application", "case study", "applied", "using", "deployment",
        "应用", "案例",
    ],
    "ethics-policy": [
        "ethics", "bias", "fairness", "policy", "governance", "regulation",
        "伦理", "偏见", "政策",
    ],
    "review": [
        "survey", "review", "overview", "landscape", "state of the art", "meta-analysis",
        "综述", "回顾",
    ],
    "general": [],  # fallback
}

# --- Resource subcategory signals ---
RESOURCE_SUBCATEGORIES = {
    "research-tool": [
        "tool", "toolkit", "platform", "app", "software", "service",
        "工具", "平台", "软件",
    ],
    "dataset": [
        "dataset", "corpus", "benchmark", "data collection", "data repository",
        "数据集", "语料", "数据仓库",
    ],
    "workflow": [
        "workflow", "guide", "tutorial", "handbook", "course", "lesson",
        "教程", "指南", "课程",
    ],
    "community": [
        "community", "forum", "group", "newsletter", "conference", "meetup",
        "社区", "论坛",
    ],
}

# --- Suitability: signals that content is NOT relevant to AI4SS ---
IRRELEVANT_SIGNALS = [
    # Pure tech / not social science
    "game dev", "gaming", "crypto", "blockchain", "nft", "web3",
    "devops", "kubernetes", "docker", "frontend", "react", "vue", "angular",
    "mobile app", "ios", "android", "swift", "kotlin",
    # Entertainment
    "meme", "funny", "drama", "celebrity", "gossip", "movie review",
    # Finance/trading
    "stock pick", "trading strategy", "forex", "day trading",
    # Too generic
    "what is ai", "ai for beginners",
]

# Positive signals: content IS relevant to social science research
RELEVANT_SIGNALS = [
    "social science", "political science", "economics", "sociology", "psychology",
    "public policy", "communication", "anthropology", "education",
    "research", "academic", "scholarly", "university", "professor",
    "causal", "survey", "experiment", "qualitative", "quantitative",
    "nlp", "text analysis", "computational social", "digital humanities",
    "社会科学", "政治学", "经济学", "社会学", "心理学", "学术", "科研",
]


def classify_content(title: str, description: str, platform: str) -> Dict:
    """Smart classification: type + subcategory + suitability.

    Returns:
        {
            "type": "skill" | "paper" | "resource",
            "subcategory": "analysis" | "writing" | ... ,
            "suitability": "recommended" | "maybe" | "not_recommended",
            "reason": "why this classification",
        }
    """
    text = f"{title} {description}".lower()

    # --- Suitability check ---
    irrelevant_hits = sum(1 for s in IRRELEVANT_SIGNALS if s in text)
    relevant_hits = sum(1 for s in RELEVANT_SIGNALS if s in text)

    if irrelevant_hits >= 2 and relevant_hits == 0:
        suitability = "not_recommended"
        reason = "与社会科学研究关系不大"
    elif relevant_hits >= 2:
        suitability = "recommended"
        reason = "高度相关"
    elif relevant_hits >= 1:
        suitability = "maybe"
        reason = "可能相关，请人工确认"
    else:
        suitability = "maybe"
        reason = "关联度不确定"

    # --- Top-level type (two-pass: direct signals + subcategory boost) ---
    hint = ALL_PLATFORMS.get(platform, {}).get("content_hint", "")
    if hint == "paper":
        content_type = "paper"
    else:
        paper_hits = sum(1 for s in PAPER_SIGNALS if s in text)
        skill_hits = sum(1 for s in SKILL_SIGNALS if s in text)
        resource_hits = sum(1 for s in RESOURCE_SIGNALS if s in text)

        # Boost: if subcategory signals match strongly, count that toward parent type
        skill_sub_hits = max(
            (sum(1 for s in sigs if s in text) for sigs in SKILL_SUBCATEGORIES.values()),
            default=0,
        )
        paper_sub_hits = max(
            (sum(1 for s in sigs if s in text) for sigs in PAPER_SUBCATEGORIES.values()),
            default=0,
        )
        resource_sub_hits = max(
            (sum(1 for s in sigs if s in text) for sigs in RESOURCE_SUBCATEGORIES.values()),
            default=0,
        )

        # Add subcategory boost (capped at 2) to top-level scores
        skill_total = skill_hits + min(skill_sub_hits, 2)
        paper_total = paper_hits + min(paper_sub_hits, 2)
        resource_total = resource_hits + min(resource_sub_hits, 2)

        best = max(skill_total, paper_total, resource_total)
        if best == 0:
            content_type = "resource"
        elif paper_total == best:
            content_type = "paper"
        elif skill_total == best:
            content_type = "skill"
        else:
            content_type = "resource"

    # --- Subcategory ---
    if content_type == "skill":
        subcategory = _match_subcategory(text, SKILL_SUBCATEGORIES, "research-engineering")
    elif content_type == "paper":
        subcategory = _match_subcategory(text, PAPER_SUBCATEGORIES, "general")
    else:
        subcategory = _match_subcategory(text, RESOURCE_SUBCATEGORIES, "research-tool")

    return {
        "type": content_type,
        "subcategory": subcategory,
        "suitability": suitability,
        "reason": reason,
    }


def _match_subcategory(text: str, subcategories: Dict[str, List[str]], default: str) -> str:
    """Find the best matching subcategory by keyword hits."""
    best_key = default
    best_hits = 0
    for key, signals in subcategories.items():
        hits = sum(1 for s in signals if s in text)
        if hits > best_hits:
            best_hits = hits
            best_key = key
    return best_key


# Legacy wrapper for backward compatibility
def classify_content_type(title: str, description: str, platform: str) -> str:
    """Classify into skill/paper/resource (legacy interface)."""
    result = classify_content(title, description, platform)
    return result["type"]

    best = max(paper_hits, skill_hits, resource_hits)
    if best == 0:
        return "resource"
    if paper_hits == best:
        return "paper"
    if skill_hits == best:
        return "skill"
    return "resource"


# ============================================
# OpenCLI Runner
# ============================================

def _build_search_cmd(platform: str, query: str) -> List[str]:
    """Build the correct CLI command for a platform's search style."""
    config = ALL_PLATFORMS.get(platform, {})
    style = config.get("search_style", "positional")

    if style == "top_only":
        # No search command, use top
        return ["opencli", platform, "top", "-f", "json"]
    elif style == "flag":
        return ["opencli", platform, "search", "--query", query, "-f", "json"]
    elif style == "intercept":
        # Intercept-based platforms (e.g., twitter) use positional
        return ["opencli", platform, "search", query, "-f", "json"]
    else:
        # Positional (default)
        return ["opencli", platform, "search", query, "-f", "json"]


def run_opencli(
    cmd: List[str],
    *,
    limit: int = 10,
    timeout: int = 30,
) -> List[Dict]:
    """Run an opencli command and return parsed JSON results."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            if stderr and "error:" in stderr.lower():
                print(f"  [WARN] {' '.join(cmd[:3])} error: {stderr[:150]}")
            if not result.stdout.strip():
                return []

        output = result.stdout.strip()
        if not output:
            return []

        data = json.loads(output)
        if isinstance(data, list):
            # Filter out error entries
            data = [d for d in data if not (isinstance(d, dict) and "Status" in d and "Error" in str(d.get("Status", "")))]
            return data[:limit]
        if isinstance(data, dict) and "results" in data:
            return data["results"][:limit]
        return []

    except subprocess.TimeoutExpired:
        print(f"  [WARN] Timed out ({timeout}s): {' '.join(cmd[:3])}")
        return []
    except json.JSONDecodeError:
        print(f"  [WARN] Invalid JSON from: {' '.join(cmd[:3])}")
        return []
    except FileNotFoundError:
        print("[ERROR] opencli not found. Install: npm install -g @jackwener/opencli")
        return []
    except Exception as exc:
        print(f"  [WARN] {' '.join(cmd[:3])} failed: {exc}")
        return []


def _normalize_item(item: Dict, platform: str) -> Optional[Dict]:
    """Normalize a raw opencli result to a common schema."""
    config = ALL_PLATFORMS.get(platform, {})
    fields = config.get("fields", {})

    # Title
    title_key = fields.get("title", "title")
    title = str(item.get(title_key, "")).strip()
    if not title:
        return None

    # URL
    url_key = fields.get("url", "url")
    url = str(item.get(url_key, "")).strip()
    url_prefix = config.get("url_prefix", "")
    if url_prefix and url and not url.startswith("http"):
        url = url_prefix + url

    # Popularity
    pop_key = fields.get("popularity")
    popularity = 0
    if pop_key and pop_key in item:
        try:
            raw_pop = str(item[pop_key]).replace(",", "")
            popularity = int(float(raw_pop))
        except (ValueError, TypeError):
            pass

    # Description
    desc_key = fields.get("description", "title")
    desc_candidates = [
        item.get("description"), item.get("snippet"),
        item.get("text"), item.get("content"),
        item.get(desc_key),
    ]
    description = next((str(d) for d in desc_candidates if d), title)

    # Extra info (authors, channel, etc.)
    extra_key = fields.get("extra")
    extra = str(item.get(extra_key, "")) if extra_key else ""

    content_type = classify_content_type(title, description, platform)

    tags = []
    if "tags" in item and isinstance(item["tags"], list):
        tags = [str(t) for t in item["tags"][:5]]

    return {
        "title": title[:200],
        "description": description[:300],
        "url": url,
        "popularity": popularity,
        "source": f"opencli-{platform}",
        "content_type": content_type,
        "tags": tags,
        "extra": extra,
        "raw": item,
    }


def search_platform(
    platform: str,
    query: str,
    *,
    limit: int = 10,
    timeout: int = 30,
) -> List[Dict]:
    """Search a platform via opencli and return normalized results."""
    cmd = _build_search_cmd(platform, query)
    raw_results = run_opencli(cmd, limit=limit, timeout=timeout)

    if not raw_results:
        return []

    results = []
    for item in raw_results:
        normalized = _normalize_item(item, platform)
        if normalized:
            results.append(normalized)
    return results


def browse_trending(
    platform: str,
    *,
    limit: int = 10,
    timeout: int = 30,
) -> List[Dict]:
    """Browse trending/hot content (no keyword)."""
    for command in ["top", "hot", "trending"]:
        cmd = ["opencli", platform, command, "-f", "json"]
        raw = run_opencli(cmd, limit=limit, timeout=timeout)
        if raw:
            results = []
            for item in raw:
                normalized = _normalize_item(item, platform)
                if normalized:
                    results.append(normalized)
            return results
    return []


def check_opencli_available() -> bool:
    """Check if opencli is installed."""
    try:
        result = subprocess.run(
            ["opencli", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_opencli_version() -> str:
    """Get opencli version string."""
    try:
        result = subprocess.run(
            ["opencli", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"
