#!/usr/bin/env python3
"""
Auto-collect Claude Code Skills into the Jekyll skills collection.
Based on the search-skill methodology from GBSOSS/skill-from-masters.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List, Set, Optional

SEARCH_URL = "https://api.github.com/search/repositories"
REPO_URL_TEMPLATE = "https://api.github.com/repos/{owner}/{repo}"

# ============================================
# Data Sources (by trust level)
# Based on search-skill methodology
# ============================================

# Tier 1 - Official / High Trust
TIER1_SOURCES = [
    "anthropics/skills",
    "ComposioHQ/awesome-claude-skills",
]

# Tier 2 - Community Curated
TIER2_SOURCES = [
    "travisvn/awesome-claude-skills",
    "skill-from-masters/skill-from-masters",
    "syxihuang/claude-code-skills",
    "Shaoipu/Claude-Code-Skill-Base",
]

# Skills keywords for social science research
SKILL_KEYWORDS = [
    "research",
    "academic",
    "social science",
    "data analysis",
    "literature review",
    "writing",
    "paper",
    "论文",
    "研究",
    "stata",
    "python",
    "r language",
    "causal inference",
    "survey",
    "experiment",
    "reproducibility",
    "open science",
    "visualization",
    "workflow",
    "automation",
    "productivity",
    "office",
    "document",
    "presentation",
    "slide",
    "excel",
    "tableau",
    "text analysis",
    "nlp",
    "machine learning",
    "llm",
    "gpt",
    "ai",
]

# Category mapping for skills
CATEGORY_KEYWORDS = {
    "literature": ["literature", "paper", "论文", "review", "reading", "academic search", "scholar"],
    "data-collection": ["data collection", "爬虫", "scraper", "crawl", "api", "fetch", "download"],
    "data-analysis": ["analysis", "analysis", "分析", "statistics", "statistical", "stata", "r language", "python", "regression", "causal"],
    "writing": ["writing", "写作", "write", "document", "latex", "markdown", "paper writing", "论文写作"],
    "presentation": ["presentation", "slide", "ppt", "powerpoint", "keynote", "演示", "slides"],
    "design": ["design", "visualization", "chart", "graph", "可视化", "infographic", "figure"],
    "research-engineering": ["research engineering", "code", "programming", "开发", "coding", "agent", "automation", "workflow", "pipeline"],
}


def dedupe_preserve_order(values: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    result: List[str] = []
    for item in values:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def build_skill_queries() -> List[str]:
    """Build queries for finding skills related to social science research."""
    queries: List[str] = []
    
    # Add keyword combinations
    for keyword in SKILL_KEYWORDS:
        queries.append(f"{keyword} claude code skill")
        queries.append(f"{keyword} claude agent")
    
    # Add research-specific combinations
    research_queries = [
        "social science research tool",
        "academic writing assistant",
        "data analysis skill",
        "literature review automation",
        "research workflow automation",
        "paper writing assistant",
    ]
    queries.extend(research_queries)
    
    return dedupe_preserve_order(queries)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root directory")
    parser.add_argument("--max-new", type=int, default=5, help="Maximum number of new skills to add")
    parser.add_argument("--min-new", type=int, default=1, help="Preferred minimum new skills per run")
    parser.add_argument("--min-stars", type=int, default=5, help="Minimum stars for primary search")
    parser.add_argument("--lookback-days", type=int, default=60, help="Primary search window in days")
    parser.add_argument("--fallback-min-stars", type=int, default=10, help="Minimum stars for fallback searches")
    parser.add_argument("--pages-per-query", type=int, default=2, help="Pages to request per query")
    parser.add_argument("--per-page", type=int, default=30, help="Items per page for GitHub search")
    parser.add_argument("--dry-run", action="store_true", help="Print candidates without writing files")
    return parser.parse_args()


def normalize_link(link: str) -> str:
    return link.strip().lower().rstrip("/")


def slugify(value: str) -> str:
    # Remove Chinese characters and convert to slug
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    # Remove multiple consecutive dashes
    slug = re.sub(r"-+", "-", slug)
    return slug or "skill"


def yaml_quote(value: str) -> str:
    safe = str(value or "").replace('"', '\\"')
    return f'"{safe}"'


def yaml_list(values: Iterable[str]) -> str:
    normalized = [item for item in values if item]
    if not normalized:
        return "[]"
    return "[" + ", ".join(yaml_quote(item) for item in normalized) + "]"


def github_headers(token: str | None) -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "AI4SS-SkillCollector",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def extract_front_matter(md_text: str) -> Dict[str, str]:
    if not md_text.startswith("---"):
        return {}

    parts = md_text.split("---", 2)
    if len(parts) < 3:
        return {}

    body = parts[1]
    metadata: Dict[str, str] = {}
    for line in body.splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        metadata[key.strip()] = val.strip().strip('"')
    return metadata


def load_existing_links(skills_dir: Path) -> Set[str]:
    links: Set[str] = set()
    # Search all subdirectories under _skills
    for md_path in skills_dir.rglob("*.md"):
        # Skip index.md files
        if md_path.name == "index.md":
            continue
        metadata = extract_front_matter(md_path.read_text(encoding="utf-8"))
        link = metadata.get("link")
        if link:
            links.add(normalize_link(link))
    return links


def classify_skill(topics: List[str], description: str, name: str) -> str:
    """Classify skill into appropriate category based on keywords."""
    normalized_topics = {item.lower() for item in topics}
    text = f"{description} {name}".lower()
    
    # Check each category
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in normalized_topics or keyword in text for keyword in keywords):
            return category
    
    # Default to research-engineering for AI/tech related skills
    if any(token in normalized_topics or token in text for token in ["agent", "automation", "code", "programming", "workflow"]):
        return "research-engineering"
    
    return "research-engineering"


def get_source_tier(full_name: str) -> int:
    """Determine the trust tier of a source repository."""
    for tier1 in TIER1_SOURCES:
        if full_name.lower().endswith(tier1.lower()):
            return 1
    for tier2 in TIER2_SOURCES:
        if full_name.lower().endswith(tier2.lower()):
            return 2
    return 3


def parse_updated_timestamp(value: str) -> int:
    if not value:
        return 0
    try:
        normalized = value.replace("Z", "+00:00")
        return int(dt.datetime.fromisoformat(normalized).timestamp())
    except ValueError:
        return 0


def is_skill_repo(topics: List[str], description: str, name: str) -> bool:
    """Check if a repository is a skill/repository (has SKILL.md or similar)."""
    text = f"{description} {name}".lower()
    
    # Check for skill-related indicators
    skill_indicators = ["skill", "claude", "agent", "prompt", "tool", "workflow", "automation", "assistant"]
    
    return any(indicator in text for indicator in skill_indicators)


def enrich_ranking_fields(item: Dict[str, object]) -> None:
    """Add ranking fields to an item."""
    topics = item.get("topics") or []
    if isinstance(topics, list):
        topics = [str(t) for t in topics]
    else:
        topics = []
    
    description = str(item.get("description") or "")
    name = str(item.get("name") or "")
    
    # Calculate relevance score based on keyword matches
    text = f"{description} {name} {' '.join(topics)}".lower()
    keyword_hits = sum(1 for kw in SKILL_KEYWORDS if kw in text)
    
    # Check if it's a skill repo
    has_skill_file = is_skill_repo(topics, description, name)
    
    item["_keyword_hits"] = keyword_hits
    item["_is_skill"] = has_skill_file
    item["_updated_ts"] = parse_updated_timestamp(str(item.get("updated_at") or ""))
    item["_tier"] = get_source_tier(str(item.get("full_name") or ""))


def ranking_key(item: Dict[str, object]) -> tuple:
    """Generate ranking key for sorting skills."""
    stars = int(item.get("stargazers_count") or 0)
    updated_ts = int(item.get("_updated_ts") or 0)
    tier = int(item.get("_tier") or 3)
    keyword_hits = int(item.get("_keyword_hits") or 0)
    is_skill = int(item.get("_is_skill") or 0)
    
    # Higher tier = better (lower number)
    # Higher stars = better
    # Higher keyword hits = better
    # Recent update = better
    # Is skill repo = better
    return (-tier, stars, keyword_hits, is_skill, updated_ts)


def parse_github_repo(link: str) -> tuple[str, str] | None:
    match = re.match(r"^https?://github\.com/([^/]+)/([^/#?]+)", link.strip(), re.IGNORECASE)
    if not match:
        return None
    owner = match.group(1)
    repo = match.group(2).removesuffix(".git")
    return owner, repo


def github_repo_details(owner: str, repo: str, token: str | None) -> Dict[str, object] | None:
    url = REPO_URL_TEMPLATE.format(owner=owner, repo=repo)
    request = urllib.request.Request(url, headers=github_headers(token))
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        enrich_ranking_fields(payload)
        return payload
    except Exception as exc:
        print(f"[WARN] repo detail failed: {owner}/{repo} -> {exc}")
        return None


def github_search(
    query: str,
    token: str | None,
    *,
    lookback_days: int | None,
    sort: str,
    order: str,
    per_page: int,
    page: int,
) -> List[Dict[str, object]]:
    query_parts = [query, "archived:false", "fork:false"]

    if lookback_days and lookback_days > 0:
        since_date = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=lookback_days)).date().isoformat()
        query_parts.append(f"pushed:>={since_date}")

    full_query = " ".join(query_parts)
    params = urllib.parse.urlencode(
        {
            "q": full_query,
            "sort": sort,
            "order": order,
            "per_page": str(per_page),
            "page": str(page),
        }
    )
    url = f"{SEARCH_URL}?{params}"
    request = urllib.request.Request(url, headers=github_headers(token))

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 422:
            print(f"[WARN] query failed: {query} (page={page}) -> HTTP 422: Unprocessable Entity - simplifying query")
            return []
        elif e.code == 403:
            print(f"[WARN] query failed: {query} (page={page}) -> HTTP 403: Forbidden")
            return []
        else:
            print(f"[WARN] query failed: {query} (page={page}) -> {e}")
            return []
    except Exception as e:
        print(f"[WARN] query failed: {query} (page={page}) -> {e}")
        return []

    return payload.get("items", [])


def collect_candidates(
    *,
    queries: List[str],
    min_stars: int,
    lookback_days: int | None,
    token: str | None,
    sort: str,
    order: str,
    pages_per_query: int,
    per_page: int = 30,
) -> List[Dict[str, object]]:
    seen: Set[str] = set()
    candidates: List[Dict[str, object]] = []

    for query in queries:
        for page in range(1, pages_per_query + 1):
            items = github_search(
                query,
                token,
                lookback_days=lookback_days,
                sort=sort,
                order=order,
                per_page=per_page,
                page=page,
            )

            if not items:
                break

            for item in items:
                link = normalize_link(str(item.get("html_url", "")))
                if not link or link in seen:
                    continue

                stars = int(item.get("stargazers_count") or 0)
                if stars < min_stars:
                    continue

                enrich_ranking_fields(item)
                seen.add(link)
                candidates.append(item)

            if len(items) < per_page:
                break

    candidates.sort(key=ranking_key, reverse=True)
    return candidates


def build_markdown(item: Dict[str, object], used_slugs: Set[str], category: str) -> tuple[str, str]:
    """Build Jekyll markdown for a skill."""
    repo_name = str(item.get("name") or "Untitled")
    owner = str((item.get("owner") or {}).get("login") or "unknown")
    description = str(item.get("description") or "A Claude Code skill for social science research.")
    description = description.replace("\n", " ").strip()
    if len(description) > 180:
        description = description[:177].rstrip() + "..."

    topics = [str(topic) for topic in (item.get("topics") or [])][:6]
    stars = int(item.get("stargazers_count") or 0)
    updated_at = str(item.get("updated_at") or "")[:10]
    license_name = ""
    license_obj = item.get("license") or {}
    if isinstance(license_obj, dict):
        license_name = str(license_obj.get("spdx_id") or "")
    
    tier = int(item.get("_tier") or 3)
    source_tier = "Tier 1 (Official)" if tier == 1 else ("Tier 2 (Community)" if tier == 2 else "Tier 3 (Other)")

    base_slug = slugify(f"{owner}-{repo_name}")
    slug = base_slug
    idx = 2
    while slug in used_slugs:
        slug = f"{base_slug}-{idx}"
        idx += 1
    used_slugs.add(slug)

    link = str(item.get("html_url") or "")
    markdown = f"""---
layout: skill
title: {yaml_quote(repo_name)}
description: {yaml_quote(description)}
category: {category}
link: {link}
source: github-auto
stars: {stars}
last_updated: {updated_at}
license: {yaml_quote(license_name)}
source_tier: {yaml_quote(source_tier)}
tags: {yaml_list(topics)}
permalink: /skills/{category}/{slug}/
---

## {repo_name} ({owner})

Auto-collected by AI4SS from GitHub discovery.

- GitHub: {link}
- Stars: {stars}
- Last updated: {updated_at}
- Category: {category}
- Source Tier: {source_tier}

Use this skill as a reference for AI-enabled social science research workflows.
"""

    return slug, markdown


def write_new_candidates(
    candidates: List[Dict[str, object]],
    *,
    existing_links: Set[str],
    used_slugs: Set[str],
    skills_dir: Path,
    dry_run: bool,
    max_new: int,
    start_count: int = 0,
) -> int:
    new_count = start_count

    for item in candidates:
        if new_count >= max_new:
            break

        link = normalize_link(str(item.get("html_url") or ""))
        if not link or link in existing_links:
            continue

        topics = [str(topic) for topic in (item.get("topics") or [])]
        description = str(item.get("description") or "")
        name = str(item.get("name") or "")
        
        category = classify_skill(topics, description, name)
        
        # Ensure category directory exists
        category_dir = skills_dir / category
        category_dir.mkdir(parents=True, exist_ok=True)

        slug, markdown = build_markdown(item, used_slugs, category)
        output_path = category_dir / f"{slug}.md"

        if dry_run:
            print(f"[DRY-RUN] would create: {output_path}")
        else:
            output_path.write_text(markdown, encoding="utf-8")
            print(f"[NEW] {output_path}")

        existing_links.add(link)
        new_count += 1

    return new_count


def get_all_used_slugs(skills_dir: Path) -> Set[str]:
    """Get all used slugs from existing skills."""
    slugs: Set[str] = set()
    for md_path in skills_dir.rglob("*.md"):
        if md_path.name == "index.md":
            continue
        # Extract slug from filename
        slugs.add(md_path.stem)
    return slugs


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    skills_dir = repo_root / "_skills"

    if not skills_dir.exists():
        print(f"[ERROR] skills directory not found: {skills_dir}")
        return 1

    token = os.getenv("GITHUB_TOKEN")
    existing_links = load_existing_links(skills_dir)
    used_slugs = get_all_used_slugs(skills_dir)
    print(f"[INFO] existing skills: {len(used_slugs)}")

    # Build queries
    skill_queries = build_skill_queries()
    print(f"[INFO] skill query count: {len(skill_queries)}")

    # Collect candidates
    candidates = collect_candidates(
        queries=skill_queries,
        min_stars=args.min_stars,
        lookback_days=args.lookback_days,
        token=token,
        sort="stars",
        order="desc",
        pages_per_query=args.pages_per_query,
        per_page=args.per_page,
    )
    print(f"[INFO] candidates found: {len(candidates)}")

    # Filter to skill repositories
    skill_candidates = [c for c in candidates if c.get("_is_skill", False)]
    print(f"[INFO] skill candidates: {len(skill_candidates)}")

    # If not enough skill candidates, use all candidates
    if len(skill_candidates) < args.min_new:
        skill_candidates = candidates[:args.max_new * 2]

    new_count = write_new_candidates(
        skill_candidates,
        existing_links=existing_links,
        used_slugs=used_slugs,
        skills_dir=skills_dir,
        dry_run=args.dry_run,
        max_new=args.max_new,
    )

    if new_count > 0:
        print(f"[INFO] added {new_count} skills")
    else:
        print("[INFO] no new skills found")

    return 0


if __name__ == "__main__":
    sys.exit(main())
