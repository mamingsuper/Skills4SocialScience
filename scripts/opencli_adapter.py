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
# Content Type Classification
# ============================================

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


def classify_content_type(title: str, description: str, platform: str) -> str:
    """Classify a search result into skill/paper/resource."""
    text = f"{title} {description}".lower()

    hint = ALL_PLATFORMS.get(platform, {}).get("content_hint", "")
    if hint == "paper":
        return "paper"

    paper_hits = sum(1 for s in PAPER_SIGNALS if s in text)
    skill_hits = sum(1 for s in SKILL_SIGNALS if s in text)
    resource_hits = sum(1 for s in RESOURCE_SIGNALS if s in text)

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
