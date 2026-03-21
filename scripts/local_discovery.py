#!/usr/bin/env python3
"""
AI4SS Local Interactive Discovery — 本地交互式内容发现工具

从多个平台搜索 AI x 社会科学内容，逐条展示，你选择保留或跳过。
确认的内容自动生成 Jekyll 文件，最后可选择 git commit + push。

Usage:
    python scripts/local_discovery.py
    python scripts/local_discovery.py --platforms arxiv,stackoverflow
    python scripts/local_discovery.py --keywords "causal inference,AI agent"
    python scripts/local_discovery.py --platforms bilibili,zhihu --keywords "社会科学AI"
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
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
    save_rejected_item,
    score_relevance,
    slugify,
    yaml_quote,
)
from opencli_adapter import (
    ALL_PLATFORMS,
    PUBLIC_PLATFORMS,
    COOKIE_PLATFORMS,
    check_opencli_available,
    classify_content_type,
    get_opencli_version,
    search_platform,
    browse_trending,
)


# ============================================
# Default Search Queries
# ============================================

DEFAULT_QUERIES = {
    "skills": [
        "social science research skills",
        "research skills AI",
        "academic research workflow",
        "AI research tool",
        "LLM automation workflow",
        "Claude Code skill",
        "科研技能",
        "学术研究方法",
    ],
    "papers": [
        "computational social science",
        "causal inference machine learning",
        "LLM text analysis research",
        "NLP survey research",
        "social science AI paper",
        "社会科学AI",
    ],
    "resources": [
        "research data pipeline",
        "open science toolkit",
        "social science dataset",
        "text analysis framework",
        "academic productivity tool",
        "数据分析工具",
    ],
}


# ============================================
# Terminal Colors
# ============================================

class C:
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    RED = "\033[31m"
    RESET = "\033[0m"


def colored(text: str, color: str) -> str:
    return f"{color}{text}{C.RESET}"


# ============================================
# Interactive Review
# ============================================

def display_item(item: Dict, index: int, total: int) -> None:
    """Display a single search result for review."""
    ct = item.get("content_type", "resource")
    ct_colors = {"paper": C.MAGENTA, "skill": C.CYAN, "resource": C.GREEN}
    ct_display = colored(ct.upper(), ct_colors.get(ct, C.GREEN))

    score = item.get("score", 0)
    score_color = C.GREEN if score >= 5 else C.YELLOW if score >= 3 else C.RED
    score_display = colored(f"{score:.1f}", score_color)

    print()
    print(colored(f"━━━ [{index}/{total}] ━━━━━━━━━━━━━━━━━━━━━━━━━━━", C.DIM))
    print(f"  {colored('Title:', C.BOLD)} {item['title']}")
    if item.get("description") and item["description"] != item["title"]:
        desc = item["description"][:120]
        print(f"  {colored('Desc:', C.BOLD)}  {desc}")
    if item.get("extra"):
        print(f"  {colored('Info:', C.BOLD)}  {item['extra']}")
    print(f"  {colored('URL:', C.BOLD)}   {item.get('url', 'N/A')}")
    print(f"  {colored('From:', C.BOLD)}  {item['source']}  |  "
          f"Type: {ct_display}  |  "
          f"Score: {score_display}  |  "
          f"Popularity: {item.get('popularity', 0)}")


def prompt_action() -> str:
    """Prompt user for action on current item.

    Returns: 'y' (accept), 'n' (skip), 's' (accept as skill),
             'p' (accept as paper), 'r' (accept as resource), 'q' (quit)
    """
    prompt = (
        f"  {colored('[y]', C.GREEN)} Accept  "
        f"{colored('[n]', C.RED)} Skip (won't show again)  "
        f"{colored('[s/p/r]', C.YELLOW)} Accept as Skill/Paper/Resource  "
        f"{colored('[?]', C.DIM)} Skip once (show again next time)  "
        f"{colored('[q]', C.DIM)} Quit\n"
        f"  > "
    )
    while True:
        try:
            choice = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return "q"
        if choice in ("y", "n", "s", "p", "r", "q", "?", ""):
            return choice if choice else "?"  # default: skip once
        print(f"  {colored('Invalid choice. Use y/n/s/p/r/?/q', C.RED)}")


# ============================================
# Jekyll File Generation
# ============================================

def write_jekyll_file(item: Dict, repo_root: Path) -> Optional[Path]:
    """Generate a Jekyll markdown file for an accepted item. Returns the file path."""
    ct = item.get("content_type", "resource")
    today = datetime.now().strftime("%Y-%m-%d")
    slug = slugify(item["title"])
    tags = item.get("tags", [])
    tags_yaml = "[" + ", ".join(yaml_quote(t) for t in tags if t) + "]" if tags else "[]"

    if ct == "skill":
        category = "research-engineering"
        out_dir = repo_root / "_skills" / category
        out_dir.mkdir(parents=True, exist_ok=True)
        filepath = out_dir / f"{slug}.md"
        if filepath.exists():
            print(f"  {colored('Already exists, skipping.', C.YELLOW)}")
            return None
        content = f"""---
layout: skill
title: {yaml_quote(item['title'])}
description: {yaml_quote(item.get('description', '')[:180])}
category: {category}
link: {item.get('url', '')}
source: {item['source']}
stars: {item.get('popularity', 0)}
last_updated: {today}
tags: {tags_yaml}
relevance_score: {item.get('score', 0):.1f}
permalink: /skills/{category}/{slug}/
---

## {item['title']}

{item.get('description', '')}

- [View]({item.get('url', '')})
"""

    elif ct == "paper":
        out_dir = repo_root / "_papers" / "0-general"
        out_dir.mkdir(parents=True, exist_ok=True)
        filepath = out_dir / f"{slug}.md"
        if filepath.exists():
            print(f"  {colored('Already exists, skipping.', C.YELLOW)}")
            return None
        content = f"""---
layout: paper
title: {yaml_quote(item['title'])}
description: {yaml_quote(item.get('description', '')[:200])}
authors: []
year: {datetime.now().year}
category: general
link: {item.get('url', '')}
source: {item['source']}
tags: {tags_yaml}
relevance_score: {item.get('score', 0):.1f}
permalink: /papers/{slug}/
---

## {item['title']}

{item.get('description', '')}

- [Read Paper]({item.get('url', '')})
"""

    else:  # resource
        out_dir = repo_root / "_resources" / "0-general"
        out_dir.mkdir(parents=True, exist_ok=True)
        filepath = out_dir / f"{slug}.md"
        if filepath.exists():
            print(f"  {colored('Already exists, skipping.', C.YELLOW)}")
            return None
        content = f"""---
layout: resource
title: {yaml_quote(item['title'])}
description: {yaml_quote(item.get('description', '')[:200])}
type: repository
category: research-tool
link: {item.get('url', '')}
source: {item['source']}
stars: {item.get('popularity', 0)}
last_updated: {today}
tags: {tags_yaml}
relevance_score: {item.get('score', 0):.1f}
permalink: /resources/{slug}/
---

## {item['title']}

{item.get('description', '')}

- [View Resource]({item.get('url', '')})
"""

    filepath.write_text(content, encoding="utf-8")
    return filepath


# ============================================
# Git Operations
# ============================================

def git_commit_and_push(files: List[Path], repo_root: Path) -> bool:
    """Stage files, commit, and optionally push."""
    if not files:
        return False

    print()
    print(colored("━━━ Git Operations ━━━━━━━━━━━━━━━━━━━━━━━━", C.BOLD))
    print(f"  {len(files)} files to commit:")
    for f in files:
        rel = f.relative_to(repo_root)
        print(f"    + {rel}")

    try:
        choice = input(f"\n  {colored('[c]', C.GREEN)} Commit  {colored('[p]', C.CYAN)} Commit + Push  {colored('[n]', C.RED)} Skip\n  > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False

    if choice not in ("c", "p"):
        print(f"  {colored('Skipped git operations. Files are saved locally.', C.YELLOW)}")
        return False

    # Stage files
    for f in files:
        subprocess.run(["git", "add", str(f)], cwd=str(repo_root))

    # Commit
    today = datetime.now().strftime("%Y-%m-%d")
    msg = f"feat: add curated content from local discovery ({today})"
    result = subprocess.run(
        ["git", "commit", "-m", msg],
        cwd=str(repo_root),
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  {colored('Commit failed:', C.RED)} {result.stderr.strip()}")
        return False
    print(f"  {colored('Committed!', C.GREEN)} {msg}")

    if choice == "p":
        result = subprocess.run(
            ["git", "push"],
            cwd=str(repo_root),
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print(f"  {colored('Pushed to remote!', C.GREEN)}")
        else:
            print(f"  {colored('Push failed:', C.RED)} {result.stderr.strip()}")
            print(f"  You can push manually: git push")

    return True


# ============================================
# Main Discovery Flow
# ============================================

def run_discovery(
    platforms: List[str],
    queries: Dict[str, List[str]],
    repo_root: Path,
    *,
    min_score: float = 2.0,
    browse: bool = False,
) -> None:
    """Run the full interactive discovery flow."""

    # Header
    print()
    print(colored("╔══════════════════════════════════════════════════╗", C.CYAN))
    print(colored("║    AI4SS Local Interactive Content Discovery     ║", C.CYAN))
    print(colored("╚══════════════════════════════════════════════════╝", C.CYAN))
    print()

    version = get_opencli_version()
    print(f"  opencli version: {colored(version, C.GREEN)}")
    print(f"  Platforms: {colored(', '.join(platforms), C.BLUE)}")
    total_queries = sum(len(v) for v in queries.values())
    print(f"  Queries: {colored(str(total_queries), C.BLUE)} across {len(queries)} categories")
    print()

    # Load dedup registry
    existing_urls = build_dedup_registry(repo_root)
    keywords = load_taxonomy_keywords(repo_root)
    print(f"  {len(existing_urls)} existing items for dedup")
    print(f"  {len(keywords)} scoring keywords loaded")
    print()

    # Collect results
    print(colored("Phase 1: Searching platforms...", C.BOLD))
    all_results: List[Dict] = []

    for platform in platforms:
        if platform not in ALL_PLATFORMS:
            print(f"  {colored(f'Unknown platform: {platform}', C.RED)}")
            continue

        for content_type, query_list in queries.items():
            for query in query_list:
                print(f"  [{colored(platform, C.BLUE)}] {query}...", end=" ", flush=True)
                results = search_platform(platform, query, limit=5, timeout=30)
                print(f"{len(results)} results")
                for r in results:
                    r["query_content_type"] = content_type
                all_results.extend(results)
                time.sleep(0.3)

    if browse:
        print()
        print(colored("Browsing trending content...", C.BOLD))
        for platform in platforms:
            print(f"  [{colored(platform, C.BLUE)}] trending...", end=" ", flush=True)
            results = browse_trending(platform, limit=10, timeout=30)
            print(f"{len(results)} results")
            all_results.extend(results)
            time.sleep(0.3)

    if not all_results:
        print(f"\n  {colored('No results found from any platform.', C.RED)}")
        return

    # Deduplicate and score
    print()
    print(colored("Phase 2: Deduplicating and scoring...", C.BOLD))
    seen: Set[str] = set()
    unique: List[Dict] = []
    for item in all_results:
        url = item.get("url", "")
        if not url:
            continue
        norm = normalize_url(url)
        if norm in seen or norm in existing_urls:
            continue
        seen.add(norm)

        score = score_relevance(
            title=item.get("title", ""),
            description=item.get("description", ""),
            source=item.get("source", "").replace("opencli-", ""),
            stars=item.get("popularity", 0),
            keywords=keywords,
        )
        item["score"] = score

        # Resolve content type
        if "query_content_type" in item:
            item["content_type"] = item["query_content_type"]
        classified = classify_content_type(
            item.get("title", ""), item.get("description", ""), ""
        )
        if classified != "resource":
            item["content_type"] = classified

        if score >= min_score:
            unique.append(item)

    unique.sort(key=lambda x: (x["score"], x.get("popularity", 0)), reverse=True)

    print(f"  {len(all_results)} raw -> {len(unique)} unique (score >= {min_score})")

    if not unique:
        print(f"\n  {colored('No items passed the minimum score threshold.', C.YELLOW)}")
        return

    # Interactive review
    print()
    print(colored("Phase 3: Interactive review", C.BOLD))
    print(f"  Review {len(unique)} items one by one. Accept the ones you want to add.")
    print()

    accepted_files: List[Path] = []
    accepted_count = 0
    rejected_count = 0
    skipped_once_count = 0

    for i, item in enumerate(unique, 1):
        display_item(item, i, len(unique))
        action = prompt_action()

        if action == "q":
            print(f"\n  {colored('Quit. Finishing up...', C.DIM)}")
            break
        elif action == "n":
            # Permanent reject — save to _data/rejected.json
            save_rejected_item(
                repo_root,
                url=item.get("url", ""),
                title=item.get("title", ""),
                source=item.get("source", ""),
            )
            rejected_count += 1
            print(f"  {colored('Rejected (永久跳过)', C.RED)}")
            continue
        elif action == "?":
            # Skip once — will appear again next time
            skipped_once_count += 1
            continue
        elif action in ("s", "p", "r"):
            type_map = {"s": "skill", "p": "paper", "r": "resource"}
            item["content_type"] = type_map[action]
            action = "y"

        if action == "y":
            filepath = write_jekyll_file(item, repo_root)
            if filepath:
                accepted_files.append(filepath)
                accepted_count += 1
                print(f"  {colored('Saved!', C.GREEN)} {filepath.relative_to(repo_root)}")
            else:
                skipped_once_count += 1

    # Summary
    print()
    print(colored("━━━ Summary ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", C.BOLD))
    remaining = len(unique) - accepted_count - rejected_count - skipped_once_count
    print(f"  {colored(str(accepted_count), C.GREEN)} accepted, "
          f"{colored(str(rejected_count), C.RED)} rejected (永久), "
          f"{colored(str(skipped_once_count), C.YELLOW)} skipped (下次还会出现), "
          f"{remaining} remaining")

    # Git
    if accepted_files:
        git_commit_and_push(accepted_files, repo_root)
    else:
        print(f"  {colored('No files to commit.', C.DIM)}")

    print()
    print(colored("Done!", C.GREEN))


# ============================================
# CLI
# ============================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI4SS Local Interactive Content Discovery",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/local_discovery.py
  python scripts/local_discovery.py --platforms arxiv,stackoverflow
  python scripts/local_discovery.py --keywords "causal inference,AI agent"
  python scripts/local_discovery.py --platforms bilibili,zhihu --keywords "社会科学AI"
  python scripts/local_discovery.py --browse  (also browse trending content)

Available public platforms (no login):
  arxiv, stackoverflow, wikipedia, hackernews, weread, apple-podcasts

Cookie-based platforms (need Chrome login):
  twitter, reddit, bilibili, zhihu, xiaohongshu, youtube
""",
    )
    parser.add_argument(
        "--platforms", default="twitter,arxiv,stackoverflow",
        help="Comma-separated platforms (default: twitter,arxiv,stackoverflow)",
    )
    parser.add_argument(
        "--keywords",
        help="Comma-separated custom keywords (overrides default queries)",
    )
    parser.add_argument(
        "--type", choices=["skill", "paper", "resource", "all"], default="all",
        help="Search only this content type (default: all)",
    )
    parser.add_argument(
        "--min-score", type=float, default=2.0,
        help="Minimum relevance score to show (default: 2.0)",
    )
    parser.add_argument(
        "--repo-root", default=".",
        help="Repository root (default: current directory)",
    )
    parser.add_argument(
        "--browse", action="store_true",
        help="Also browse trending/hot content from each platform",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]

    if not check_opencli_available():
        print(f"{colored('ERROR:', C.RED)} opencli not installed.")
        print("Install: npm install -g @jackwener/opencli")
        return 1

    # Build queries
    if args.keywords:
        custom = [q.strip() for q in args.keywords.split(",") if q.strip()]
        target = args.type if args.type != "all" else "resources"
        queries = {target: custom}
    elif args.type != "all":
        queries = {args.type: DEFAULT_QUERIES.get(args.type + "s", DEFAULT_QUERIES["resources"])}
    else:
        queries = DEFAULT_QUERIES

    run_discovery(
        platforms=platforms,
        queries=queries,
        repo_root=repo_root,
        min_score=args.min_score,
        browse=args.browse,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
