#!/usr/bin/env python3
"""
Cross-platform keyword search driver for AI4SS using opencli.
Searches multiple web platforms for AI x social science content,
scores/deduplicates results, and generates Jekyll collection files.

Usage:
    python opencli_search.py --platforms hackernews,stackoverflow
    python opencli_search.py --platforms hackernews --keywords "causal inference,AI research"
    python opencli_search.py --dry-run --type skill
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

sys.path.insert(0, str(Path(__file__).parent))
from ai4ss_utils import (
    build_dedup_registry,
    load_taxonomy_keywords,
    normalize_url,
    score_relevance,
    slugify,
    yaml_quote,
)
from opencli_adapter import (
    ALL_PLATFORMS,
    PUBLIC_PLATFORMS,
    browse_trending,
    check_opencli_available,
    classify_content_type,
    search_platform,
)


# ============================================
# Search Query Groups
# ============================================

# Bilingual keyword groups targeting different collection types
SEARCH_QUERIES = {
    "skills": [
        "AI research tool",
        "Claude Code skill",
        "LLM automation workflow",
        "academic productivity tool",
        "research automation",
        "AI agent social science",
        "AI科研工具",
        "学术生产力工具",
    ],
    "papers": [
        "social science AI",
        "causal inference machine learning",
        "NLP survey research",
        "computational social science",
        "LLM text analysis research",
        "AI政治学经济学",
        "因果推断机器学习",
    ],
    "resources": [
        "research data pipeline",
        "academic workflow automation",
        "open science toolkit",
        "social science dataset",
        "text analysis framework",
        "数据分析工具包",
        "社会科学数据集",
    ],
}


# ============================================
# Core Search Logic
# ============================================

def run_keyword_searches(
    platforms: List[str],
    queries: Dict[str, List[str]],
    *,
    max_per_query: int = 5,
    timeout: int = 30,
) -> List[Dict]:
    """Run keyword searches across platforms and return all results.

    Args:
        platforms: List of platform names to search
        queries: Dict mapping content_type to list of search queries
        max_per_query: Max results per (platform, query) pair
        timeout: Timeout per search command

    Returns:
        List of normalized result dicts from opencli_adapter
    """
    all_results = []

    for platform in platforms:
        if platform not in ALL_PLATFORMS:
            print(f"[WARN] Unknown platform: {platform}, skipping")
            continue

        for content_type, query_list in queries.items():
            for query in query_list:
                print(f"  [{platform}] Searching: {query}")
                results = search_platform(
                    platform, query, limit=max_per_query, timeout=timeout,
                )
                # Tag results with the intended content type from query group
                for r in results:
                    r["query_content_type"] = content_type
                all_results.extend(results)
                time.sleep(0.5)  # rate limiting between queries

    return all_results


def run_trending_browse(
    platforms: List[str],
    *,
    max_per_platform: int = 10,
    timeout: int = 30,
) -> List[Dict]:
    """Browse trending content from platforms (no keyword search)."""
    all_results = []

    for platform in platforms:
        if platform not in ALL_PLATFORMS:
            continue
        print(f"  [{platform}] Browsing trending...")
        results = browse_trending(platform, limit=max_per_platform, timeout=timeout)
        all_results.extend(results)
        time.sleep(0.5)

    return all_results


def deduplicate_and_score(
    results: List[Dict],
    existing_urls: Set[str],
    keywords: List[str],
    *,
    min_score: float = 3.0,
    max_items: int = 20,
) -> List[Dict]:
    """Deduplicate results against existing collections, score, and filter."""
    seen: Set[str] = set()
    unique = []

    for item in results:
        url = item.get("url", "")
        if not url:
            continue
        norm = normalize_url(url)
        if norm in seen or norm in existing_urls:
            continue
        seen.add(norm)

        # Score relevance
        score = score_relevance(
            title=item.get("title", ""),
            description=item.get("description", ""),
            source=item.get("source", "").replace("opencli-", ""),
            stars=item.get("popularity", 0),
            keywords=keywords,
        )
        item["score"] = score

        # Resolve content type: prefer query hint, fall back to classifier
        if "query_content_type" in item:
            item["content_type"] = item["query_content_type"]
        # If content classifier gave a strong signal, use it instead
        classified = classify_content_type(
            item.get("title", ""), item.get("description", ""), ""
        )
        if classified != "resource":  # resource is the default, so only override if classifier is confident
            item["content_type"] = classified

        unique.append(item)

    # Filter by minimum score
    qualified = [r for r in unique if r["score"] >= min_score]

    # Sort by score descending, then popularity
    qualified.sort(key=lambda x: (x["score"], x.get("popularity", 0)), reverse=True)

    return qualified[:max_items]


# ============================================
# Jekyll File Generation
# ============================================

def generate_jekyll_files(
    items: List[Dict],
    repo_root: Path,
    *,
    dry_run: bool = False,
) -> Dict[str, int]:
    """Generate Jekyll markdown files from search results."""
    counts = {"skills": 0, "papers": 0, "resources": 0}

    for item in items:
        ct = item.get("content_type", "resource")
        if ct == "skill":
            counts["skills"] += _write_skill(item, repo_root, dry_run)
        elif ct == "paper":
            counts["papers"] += _write_paper(item, repo_root, dry_run)
        else:
            counts["resources"] += _write_resource(item, repo_root, dry_run)

    return counts


def _write_skill(item: Dict, repo_root: Path, dry_run: bool) -> int:
    category = "research-engineering"
    skills_dir = repo_root / "_skills" / category
    skills_dir.mkdir(parents=True, exist_ok=True)

    slug = slugify(item["title"])
    filepath = skills_dir / f"{slug}.md"
    if filepath.exists():
        return 0

    tags = item.get("tags", [])
    tags_yaml = "[" + ", ".join(yaml_quote(t) for t in tags if t) + "]" if tags else "[]"
    today = datetime.now().strftime("%Y-%m-%d")

    content = f"""---
layout: skill
title: {yaml_quote(item['title'])}
description: {yaml_quote(item['description'][:180])}
category: {category}
link: {item['url']}
source: {item['source']}
stars: {item.get('popularity', 0)}
last_updated: {today}
tags: {tags_yaml}
relevance_score: {item['score']:.1f}
permalink: /skills/{category}/{slug}/
---

## {item['title']}

{item['description']}

Auto-discovered by AI4SS opencli search from {item['source']}.

- [View]({item['url']})
- Relevance Score: {item['score']:.1f}
"""
    if dry_run:
        print(f"  [DRY-RUN] Would create skill: {filepath.name}")
    else:
        filepath.write_text(content, encoding="utf-8")
        print(f"  [SKILL] Created: {filepath.name}")
    return 1


def _write_paper(item: Dict, repo_root: Path, dry_run: bool) -> int:
    papers_dir = repo_root / "_papers" / "0-general"
    papers_dir.mkdir(parents=True, exist_ok=True)

    slug = slugify(item["title"])
    filepath = papers_dir / f"{slug}.md"
    if filepath.exists():
        return 0

    tags = item.get("tags", [])
    tags_yaml = "[" + ", ".join(yaml_quote(t) for t in tags if t) + "]" if tags else "[]"

    content = f"""---
layout: paper
title: {yaml_quote(item['title'])}
description: {yaml_quote(item['description'][:200])}
authors: []
year: {datetime.now().year}
category: general
link: {item['url']}
source: {item['source']}
tags: {tags_yaml}
relevance_score: {item['score']:.1f}
permalink: /papers/{slug}/
---

## {item['title']}

{item['description']}

Auto-discovered by AI4SS opencli search from {item['source']}.

- [Read Paper]({item['url']})
"""
    if dry_run:
        print(f"  [DRY-RUN] Would create paper: {filepath.name}")
    else:
        filepath.write_text(content, encoding="utf-8")
        print(f"  [PAPER] Created: {filepath.name}")
    return 1


def _write_resource(item: Dict, repo_root: Path, dry_run: bool) -> int:
    resources_dir = repo_root / "_resources" / "0-general"
    resources_dir.mkdir(parents=True, exist_ok=True)

    slug = slugify(item["title"])
    filepath = resources_dir / f"{slug}.md"
    if filepath.exists():
        return 0

    tags = item.get("tags", [])
    tags_yaml = "[" + ", ".join(yaml_quote(t) for t in tags if t) + "]" if tags else "[]"
    today = datetime.now().strftime("%Y-%m-%d")

    content = f"""---
layout: resource
title: {yaml_quote(item['title'])}
description: {yaml_quote(item['description'][:200])}
type: repository
category: research-tool
link: {item['url']}
source: {item['source']}
stars: {item.get('popularity', 0)}
last_updated: {today}
tags: {tags_yaml}
relevance_score: {item['score']:.1f}
permalink: /resources/{slug}/
---

## {item['title']}

{item['description']}

Auto-discovered by AI4SS opencli search from {item['source']}.

- [View Resource]({item['url']})
"""
    if dry_run:
        print(f"  [DRY-RUN] Would create resource: {filepath.name}")
    else:
        filepath.write_text(content, encoding="utf-8")
        print(f"  [RESOURCE] Created: {filepath.name}")
    return 1


# ============================================
# Summary Generation
# ============================================

def generate_summary(items: List[Dict], counts: Dict[str, int]) -> str:
    """Generate markdown summary for PR body."""
    date = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"## OpenCLI Multi-Platform Search Results ({date})",
        "",
        f"Found **{len(items)}** relevant items: "
        f"{counts.get('skills', 0)} skills, "
        f"{counts.get('papers', 0)} papers, "
        f"{counts.get('resources', 0)} resources.",
        "",
        "| # | Title | Platform | Type | Score | Popularity |",
        "|---|-------|----------|------|-------|------------|",
    ]

    for i, item in enumerate(items[:30], 1):
        title_short = item["title"][:50] + "..." if len(item["title"]) > 50 else item["title"]
        lines.append(
            f"| {i} | [{title_short}]({item['url']}) | {item['source']} | "
            f"{item.get('content_type', 'resource')} | {item['score']:.1f} | {item.get('popularity', 0)} |"
        )

    lines.append("")
    lines.append("*Auto-generated by AI4SS opencli search*")
    return "\n".join(lines)


# ============================================
# CLI
# ============================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI4SS Cross-Platform Keyword Search via opencli"
    )
    parser.add_argument(
        "--platforms",
        default="hackernews,stackoverflow",
        help="Comma-separated platform names (default: hackernews,stackoverflow)",
    )
    parser.add_argument(
        "--keywords",
        help="Comma-separated custom keywords (overrides defaults)",
    )
    parser.add_argument(
        "--type",
        choices=["skill", "paper", "resource", "auto"],
        default="auto",
        help="Target content type (auto = search all groups)",
    )
    parser.add_argument(
        "--max-results", type=int, default=20,
        help="Max results to keep after scoring",
    )
    parser.add_argument(
        "--min-score", type=float, default=3.0,
        help="Minimum relevance score (0-10)",
    )
    parser.add_argument(
        "--repo-root", default=".",
        help="Repository root directory",
    )
    parser.add_argument(
        "--output-summary",
        help="Write summary markdown to this file",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print results without writing files",
    )
    parser.add_argument(
        "--browse-trending", action="store_true",
        help="Also browse trending/hot content (not just keyword search)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]

    print("[INFO] AI4SS opencli Search starting...")

    # Check opencli is available
    if not check_opencli_available():
        print("[ERROR] opencli not found. Install: npm install -g @jackwener/opencli")
        return 1

    print(f"[INFO] Platforms: {', '.join(platforms)}")

    # Load dedup registry and keywords
    existing_urls = build_dedup_registry(repo_root)
    taxonomy_keywords = load_taxonomy_keywords(repo_root)
    print(f"[INFO] {len(existing_urls)} existing URLs for dedup")
    print(f"[INFO] {len(taxonomy_keywords)} keywords for scoring")

    # Build query set
    if args.keywords:
        custom_queries = [q.strip() for q in args.keywords.split(",") if q.strip()]
        target_type = args.type if args.type != "auto" else "resource"
        queries = {target_type: custom_queries}
    elif args.type != "auto":
        queries = {args.type: SEARCH_QUERIES.get(args.type, SEARCH_QUERIES["resources"])}
    else:
        queries = SEARCH_QUERIES

    # Run keyword searches
    print("[INFO] Running keyword searches...")
    results = run_keyword_searches(platforms, queries, max_per_query=5, timeout=30)
    print(f"[INFO] Keyword search: {len(results)} raw results")

    # Optionally browse trending
    if args.browse_trending:
        print("[INFO] Browsing trending content...")
        trending = run_trending_browse(platforms, max_per_platform=10, timeout=30)
        print(f"[INFO] Trending browse: {len(trending)} raw results")
        results.extend(trending)

    if not results:
        print("[INFO] No results found from any platform.")
        return 0

    # Deduplicate and score
    qualified = deduplicate_and_score(
        results, existing_urls, taxonomy_keywords,
        min_score=args.min_score, max_items=args.max_results,
    )
    print(f"[INFO] Qualified after dedup + scoring: {len(qualified)}")

    if not qualified:
        print("[INFO] No results above minimum score threshold.")
        return 0

    # Generate Jekyll files
    counts = generate_jekyll_files(qualified, repo_root, dry_run=args.dry_run)
    print(f"[INFO] Generated: {counts}")

    # Summary
    summary = generate_summary(qualified, counts)
    if args.output_summary:
        Path(args.output_summary).write_text(summary, encoding="utf-8")
        print(f"[INFO] Summary written to {args.output_summary}")
    else:
        print("\n" + summary)

    return 0


if __name__ == "__main__":
    sys.exit(main())
