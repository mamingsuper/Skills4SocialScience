#!/usr/bin/env python3
"""
Trending Content Aggregator for AI4SS.
Discovers what's hot this week across GitHub Trending, Hacker News,
HuggingFace, and Papers With Code. Creates Jekyll files for PR review.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

# Import shared utilities
sys.path.insert(0, str(Path(__file__).parent))
from ai4ss_utils import (
    build_dedup_registry,
    load_taxonomy_keywords,
    normalize_url,
    score_relevance,
    slugify,
    yaml_quote,
)


# ============================================
# Data Model
# ============================================

@dataclass
class TrendingItem:
    title: str
    description: str
    url: str
    source: str  # github-trending, hackernews, huggingface, paperswithcode
    content_type: str  # skill, paper, resource
    score: float  # relevance score from ai4ss_utils
    popularity: int  # stars, points, likes, etc.
    tags: List[str]
    metadata: Dict


# ============================================
# Source: GitHub Trending
# ============================================

def fetch_github_trending(keywords: List[str], token: Optional[str] = None) -> List[TrendingItem]:
    """Fetch trending repos from GitHub search API sorted by recent stars."""
    items = []
    headers = {
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'AI4SS-TrendingAggregator',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    if token:
        headers['Authorization'] = f"Bearer {token}"

    # Search for repos created/pushed in the last 7 days with AI/ML topics
    queries = [
        "AI social science stars:>10 pushed:>2026-03-10",
        "machine learning research tool stars:>20 pushed:>2026-03-10",
        "LLM research stars:>30 pushed:>2026-03-10",
        "NLP social science stars:>5 pushed:>2026-03-10",
        "causal inference tool stars:>5 pushed:>2026-03-10",
    ]

    for query in queries:
        params = urllib.parse.urlencode({
            'q': query,
            'sort': 'stars',
            'order': 'desc',
            'per_page': '10',
        })
        url = f"https://api.github.com/search/repositories?{params}"

        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))

                for repo in data.get('items', []):
                    desc = repo.get('description', '') or ''
                    items.append(TrendingItem(
                        title=repo.get('name', ''),
                        description=desc[:300],
                        url=repo.get('html_url', ''),
                        source='github-trending',
                        content_type='skill' if any(kw in desc.lower() for kw in ['skill', 'agent', 'claude', 'prompt']) else 'resource',
                        score=0.0,  # scored later
                        popularity=repo.get('stargazers_count', 0),
                        tags=[str(t) for t in (repo.get('topics', []) or [])[:5]],
                        metadata={
                            'language': repo.get('language'),
                            'forks': repo.get('forks_count', 0),
                            'owner': (repo.get('owner') or {}).get('login', ''),
                        }
                    ))
        except Exception as exc:
            print(f"[WARN] GitHub trending search failed: {exc}")

        time.sleep(0.5)

    return items


# ============================================
# Source: Hacker News (Algolia API)
# ============================================

def fetch_hackernews_trending(keywords: List[str]) -> List[TrendingItem]:
    """Fetch trending HN posts via Algolia API."""
    items = []

    search_terms = [
        "AI social science",
        "LLM research tool",
        "machine learning social",
        "NLP research",
        "causal inference AI",
        "computational social science",
    ]

    for term in search_terms:
        params = urllib.parse.urlencode({
            'query': term,
            'tags': 'story',
            'numericFilters': 'points>30',
            'hitsPerPage': '10',
        })
        url = f"https://hn.algolia.com/api/v1/search?{params}"

        try:
            request = urllib.request.Request(url, headers={
                'User-Agent': 'AI4SS-TrendingAggregator'
            })
            with urllib.request.urlopen(request, timeout=15) as response:
                data = json.loads(response.read().decode('utf-8'))

                for hit in data.get('hits', []):
                    story_url = hit.get('url', '') or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
                    title = hit.get('title', '')
                    points = hit.get('points', 0) or 0

                    # Determine content type from title
                    title_lower = title.lower()
                    if any(kw in title_lower for kw in ['paper', 'arxiv', 'research', 'study']):
                        content_type = 'paper'
                    elif any(kw in title_lower for kw in ['tool', 'framework', 'library', 'release']):
                        content_type = 'resource'
                    else:
                        content_type = 'resource'

                    items.append(TrendingItem(
                        title=title,
                        description=title,  # HN titles are self-descriptive
                        url=story_url,
                        source='hackernews',
                        content_type=content_type,
                        score=0.0,
                        popularity=points,
                        tags=['hackernews'],
                        metadata={
                            'hn_id': hit.get('objectID', ''),
                            'num_comments': hit.get('num_comments', 0),
                            'author': hit.get('author', ''),
                        }
                    ))
        except Exception as exc:
            print(f"[WARN] HN search for '{term}' failed: {exc}")

        time.sleep(0.3)

    return items


# ============================================
# Source: HuggingFace Trending
# ============================================

def fetch_huggingface_trending(keywords: List[str]) -> List[TrendingItem]:
    """Fetch trending models/datasets from HuggingFace."""
    items = []

    search_terms = [
        "social science",
        "text classification",
        "sentiment analysis",
        "named entity recognition",
        "survey analysis",
    ]

    for term in search_terms:
        for endpoint in ["models", "datasets"]:
            url = f"https://huggingface.co/api/{endpoint}?search={urllib.parse.quote(term)}&sort=likes&direction=-1&limit=5"
            try:
                request = urllib.request.Request(url, headers={
                    'User-Agent': 'AI4SS-TrendingAggregator'
                })
                with urllib.request.urlopen(request, timeout=15) as response:
                    data = json.loads(response.read().decode('utf-8'))

                    for item in data:
                        item_id = item.get('id', '') or item.get('modelId', '')
                        likes = item.get('likes', 0) or 0
                        downloads = item.get('downloads', 0) or 0

                        if endpoint == "datasets":
                            link = f"https://huggingface.co/datasets/{item_id}"
                            content_type = 'resource'
                        else:
                            link = f"https://huggingface.co/{item_id}"
                            content_type = 'resource'

                        items.append(TrendingItem(
                            title=item_id.split('/')[-1] if '/' in item_id else item_id,
                            description=f"HuggingFace {endpoint.rstrip('s')}: {item_id}",
                            url=link,
                            source='huggingface',
                            content_type=content_type,
                            score=0.0,
                            popularity=likes + (downloads // 100),
                            tags=(item.get('tags', []) or [])[:5],
                            metadata={
                                'hf_type': endpoint,
                                'downloads': downloads,
                                'likes': likes,
                                'full_id': item_id,
                            }
                        ))
            except Exception as exc:
                print(f"[WARN] HuggingFace {endpoint} search for '{term}' failed: {exc}")

        time.sleep(0.3)

    return items


# ============================================
# Aggregator
# ============================================

def aggregate_and_score(
    all_items: List[TrendingItem],
    existing_urls: Set[str],
    keywords: List[str],
    min_score: float = 4.0,
) -> List[TrendingItem]:
    """Deduplicate, score, filter, and sort all trending items."""

    # Deduplicate by normalized URL
    seen: Set[str] = set()
    unique: List[TrendingItem] = []
    for item in all_items:
        norm = normalize_url(item.url)
        if norm in seen or norm in existing_urls:
            continue
        seen.add(norm)
        unique.append(item)

    # Score each item
    for item in unique:
        item.score = score_relevance(
            title=item.title,
            description=item.description,
            source=item.source,
            stars=item.popularity,
            keywords=keywords,
        )

    # Filter by minimum score
    qualified = [item for item in unique if item.score >= min_score]

    # Sort by score descending, then popularity
    qualified.sort(key=lambda x: (x.score, x.popularity), reverse=True)

    return qualified


# ============================================
# Jekyll File Generation
# ============================================

def generate_jekyll_files(
    items: List[TrendingItem],
    repo_root: Path,
    dry_run: bool = False,
) -> Dict[str, int]:
    """Generate Jekyll markdown files from trending items."""
    counts = {'skills': 0, 'papers': 0, 'resources': 0}

    for item in items:
        if item.content_type == 'skill':
            counts['skills'] += _generate_skill_file(item, repo_root, dry_run)
        elif item.content_type == 'paper':
            counts['papers'] += _generate_paper_file(item, repo_root, dry_run)
        else:
            counts['resources'] += _generate_resource_file(item, repo_root, dry_run)

    return counts


def _generate_skill_file(item: TrendingItem, repo_root: Path, dry_run: bool) -> int:
    category = "research-engineering"
    skills_dir = repo_root / "_skills" / category
    skills_dir.mkdir(parents=True, exist_ok=True)

    owner = item.metadata.get('owner', '')
    slug = slugify(f"{owner}-{item.title}" if owner else item.title)
    filepath = skills_dir / f"{slug}.md"

    if filepath.exists():
        return 0

    tags_list = "[" + ", ".join(yaml_quote(t) for t in item.tags if t) + "]" if item.tags else "[]"
    content = f"""---
layout: skill
title: {yaml_quote(item.title)}
description: {yaml_quote(item.description[:180])}
category: {category}
link: {item.url}
source: {item.source}
stars: {item.popularity}
last_updated: {datetime.now().strftime('%Y-%m-%d')}
tags: {tags_list}
relevance_score: {item.score:.1f}
permalink: /skills/{category}/{slug}/
---

## {item.title}

Auto-discovered by AI4SS trending aggregator from {item.source}.

- Link: {item.url}
- Popularity: {item.popularity}
- Relevance Score: {item.score:.1f}
"""

    if dry_run:
        print(f"[DRY-RUN] Would create skill: {filepath}")
    else:
        filepath.write_text(content, encoding='utf-8')
        print(f"[SKILL] Created: {filepath}")
    return 1


def _generate_paper_file(item: TrendingItem, repo_root: Path, dry_run: bool) -> int:
    papers_dir = repo_root / "_papers" / "0-general"
    papers_dir.mkdir(parents=True, exist_ok=True)

    slug = slugify(item.title)
    filepath = papers_dir / f"{slug}.md"

    if filepath.exists():
        return 0

    authors = item.metadata.get('authors', []) or []
    authors_json = json.dumps(authors[:3], ensure_ascii=False)
    tags_list = "[" + ", ".join(yaml_quote(t) for t in item.tags if t) + "]" if item.tags else "[]"

    content = f"""---
layout: paper
title: {yaml_quote(item.title)}
description: {yaml_quote(item.description[:200])}
authors: {authors_json}
year: {item.metadata.get('published', '')[:4] if item.metadata.get('published') else datetime.now().year}
category: general
link: {item.url}
source: {item.source}
tags: {tags_list}
relevance_score: {item.score:.1f}
permalink: /papers/{slug}/
---

## {item.title}

{item.description}

Auto-discovered by AI4SS trending aggregator from {item.source}.

- [Read Paper]({item.url})
"""

    if dry_run:
        print(f"[DRY-RUN] Would create paper: {filepath}")
    else:
        filepath.write_text(content, encoding='utf-8')
        print(f"[PAPER] Created: {filepath}")
    return 1


def _generate_resource_file(item: TrendingItem, repo_root: Path, dry_run: bool) -> int:
    resources_dir = repo_root / "_resources" / "0-general"
    resources_dir.mkdir(parents=True, exist_ok=True)

    slug = slugify(item.title)
    filepath = resources_dir / f"{slug}.md"

    if filepath.exists():
        return 0

    tags_list = "[" + ", ".join(yaml_quote(t) for t in item.tags if t) + "]" if item.tags else "[]"

    content = f"""---
layout: resource
title: {yaml_quote(item.title)}
description: {yaml_quote(item.description[:200])}
type: repository
category: research-tool
link: {item.url}
source: {item.source}
stars: {item.popularity}
last_updated: {datetime.now().strftime('%Y-%m-%d')}
tags: {tags_list}
relevance_score: {item.score:.1f}
permalink: /resources/{slug}/
---

## {item.title}

{item.description}

Auto-discovered by AI4SS trending aggregator from {item.source}.

- [View Resource]({item.url})
"""

    if dry_run:
        print(f"[DRY-RUN] Would create resource: {filepath}")
    else:
        filepath.write_text(content, encoding='utf-8')
        print(f"[RESOURCE] Created: {filepath}")
    return 1


# ============================================
# PR Summary Generation
# ============================================

def generate_pr_summary(items: List[TrendingItem], counts: Dict[str, int]) -> str:
    """Generate a markdown summary table for the PR body."""
    date = datetime.now().strftime('%Y-%m-%d')
    lines = [
        f"## Weekly Trending Discoveries ({date})",
        "",
        f"Found **{len(items)}** relevant items: "
        f"{counts.get('skills', 0)} skills, "
        f"{counts.get('papers', 0)} papers, "
        f"{counts.get('resources', 0)} resources.",
        "",
        "| # | Title | Source | Type | Score | Popularity |",
        "|---|-------|--------|------|-------|------------|",
    ]

    for i, item in enumerate(items[:30], 1):
        title_short = item.title[:50] + "..." if len(item.title) > 50 else item.title
        lines.append(
            f"| {i} | [{title_short}]({item.url}) | {item.source} | {item.content_type} | {item.score:.1f} | {item.popularity} |"
        )

    lines.append("")
    lines.append("*Auto-generated by AI4SS Trending Aggregator*")

    return "\n".join(lines)


# ============================================
# Main
# ============================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI4SS Trending Content Aggregator")
    parser.add_argument("--repo-root", default=".", help="Repository root directory")
    parser.add_argument("--min-score", type=float, default=4.0, help="Minimum relevance score (0-10)")
    parser.add_argument("--max-items", type=int, default=20, help="Maximum items to include")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing files")
    parser.add_argument("--output-summary", help="Write PR summary to this file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()

    print("[INFO] AI4SS Trending Aggregator starting...")

    # Load dedup registry and keywords
    existing_urls = build_dedup_registry(repo_root)
    keywords = load_taxonomy_keywords(repo_root)
    print(f"[INFO] Loaded {len(existing_urls)} existing URLs for dedup")
    print(f"[INFO] Loaded {len(keywords)} keywords for scoring")

    github_token = os.getenv('GITHUB_TOKEN')

    # Fetch from all sources
    print("[INFO] Fetching from GitHub Trending...")
    github_items = fetch_github_trending(keywords, token=github_token)
    print(f"[INFO] GitHub: {len(github_items)} raw items")

    print("[INFO] Fetching from Hacker News...")
    hn_items = fetch_hackernews_trending(keywords)
    print(f"[INFO] HN: {len(hn_items)} raw items")

    print("[INFO] Fetching from HuggingFace...")
    hf_items = fetch_huggingface_trending(keywords)
    print(f"[INFO] HuggingFace: {len(hf_items)} raw items")

    # Aggregate
    all_items = github_items + hn_items + hf_items
    print(f"[INFO] Total raw items: {len(all_items)}")

    qualified = aggregate_and_score(all_items, existing_urls, keywords, min_score=args.min_score)
    qualified = qualified[:args.max_items]
    print(f"[INFO] Qualified after scoring + dedup: {len(qualified)}")

    if not qualified:
        print("[INFO] No new trending items found above threshold.")
        return 0

    # Generate Jekyll files
    counts = generate_jekyll_files(qualified, repo_root, dry_run=args.dry_run)
    print(f"[INFO] Generated: {counts}")

    # Generate PR summary
    summary = generate_pr_summary(qualified, counts)
    if args.output_summary:
        Path(args.output_summary).write_text(summary, encoding='utf-8')
        print(f"[INFO] PR summary written to {args.output_summary}")
    else:
        print("\n" + summary)

    return 0


if __name__ == "__main__":
    sys.exit(main())
