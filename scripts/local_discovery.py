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
    classify_content,
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
    """Display a single search result for review with smart classification."""
    classification = item.get("classification", {})
    ct = classification.get("type", item.get("content_type", "resource"))
    subcategory = classification.get("subcategory", "")
    suitability = classification.get("suitability", "maybe")
    reason = classification.get("reason", "")

    ct_colors = {"paper": C.MAGENTA, "skill": C.CYAN, "resource": C.GREEN}
    ct_display = colored(ct.upper(), ct_colors.get(ct, C.GREEN))

    suit_icons = {"recommended": "✅", "maybe": "🤔", "not_recommended": "❌"}
    suit_colors = {"recommended": C.GREEN, "maybe": C.YELLOW, "not_recommended": C.RED}
    suit_display = f"{suit_icons.get(suitability, '?')} {colored(reason, suit_colors.get(suitability, C.DIM))}"

    score = item.get("score", 0)
    score_color = C.GREEN if score >= 5 else C.YELLOW if score >= 3 else C.RED
    score_display = colored(f"{score:.1f}", score_color)

    print()
    if suitability == "not_recommended":
        print(colored(f"━━━ [{index}/{total}] ━━━ ❌ 不推荐 ━━━━━━━━━━━━━━", C.RED))
    else:
        print(colored(f"━━━ [{index}/{total}] ━━━━━━━━━━━━━━━━━━━━━━━━━━━", C.DIM))

    print(f"  {colored('Title:', C.BOLD)} {item['title']}")
    if item.get("description") and item["description"] != item["title"]:
        desc = item["description"][:120]
        print(f"  {colored('Desc:', C.BOLD)}  {desc}")
    if item.get("extra"):
        print(f"  {colored('Info:', C.BOLD)}  {item['extra']}")
    print(f"  {colored('URL:', C.BOLD)}   {item.get('url', 'N/A')}")
    print(f"  {colored('From:', C.BOLD)}  {item['source']}  |  Score: {score_display}  |  Pop: {item.get('popularity', 0)}")
    print(f"  {colored('分类:', C.BOLD)}  {ct_display} → {colored(subcategory, C.BLUE)}  |  {suit_display}")


def prompt_action(item: Dict) -> str:
    """Prompt user for action on current item.

    Returns: 'y' (accept with auto-classification), 'n' (permanent reject),
             's' (accept as skill), 'p' (accept as paper), 'r' (accept as resource),
             'c' (change subcategory), '?' (skip once), 'q' (quit)
    """
    suitability = item.get("classification", {}).get("suitability", "maybe")

    # For not_recommended items, default to 'n' (reject)
    if suitability == "not_recommended":
        default_action = "n"
        default_hint = "默认: 拒绝"
    else:
        default_action = "?"
        default_hint = "默认: 跳过一次"

    prompt = (
        f"  {colored('[y]', C.GREEN)} Accept (用推荐分类)  "
        f"{colored('[n]', C.RED)} Reject (永久)  "
        f"{colored('[s/p/r]', C.YELLOW)} Accept as Skill/Paper/Resource\n"
        f"  {colored('[c]', C.BLUE)} Change subcategory  "
        f"{colored('[?]', C.DIM)} Skip once  "
        f"{colored('[q]', C.DIM)} Quit  "
        f"{colored(f'[Enter={default_hint}]', C.DIM)}\n"
        f"  > "
    )
    while True:
        try:
            choice = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return "q"
        if choice in ("y", "n", "s", "p", "r", "c", "q", "?", ""):
            return choice if choice else default_action
        print(f"  {colored('Invalid choice. Use y/n/s/p/r/c/?/q', C.RED)}")


# Subcategory choices for interactive selection
SUBCATEGORY_CHOICES = {
    "skill": {
        "1": ("analysis", "数据分析 Analysis"),
        "2": ("writing", "学术写作 Writing"),
        "3": ("design", "研究设计 Design"),
        "4": ("research-engineering", "研究工程 Research Engineering"),
    },
    "paper": {
        "1": ("general", "综合 General"),
        "2": ("methodology", "方法论 Methodology"),
        "3": ("application", "应用 Application"),
        "4": ("ethics-policy", "伦理政策 Ethics & Policy"),
        "5": ("review", "综述 Review"),
    },
    "resource": {
        "1": ("research-tool", "研究工具 Research Tool"),
        "2": ("dataset", "数据集 Dataset"),
        "3": ("workflow", "工作流指南 Workflow Guide"),
        "4": ("community", "社区资源 Community"),
    },
}


def prompt_subcategory(content_type: str, current_sub: str) -> str:
    """Let user choose a subcategory interactively."""
    choices = SUBCATEGORY_CHOICES.get(content_type, {})
    if not choices:
        return current_sub

    print(f"\n  {colored(f'Choose subcategory for {content_type.upper()}:', C.BOLD)}")
    for key, (sub_key, label) in choices.items():
        marker = " ← current" if sub_key == current_sub else ""
        print(f"    {colored(f'[{key}]', C.CYAN)} {label}{colored(marker, C.DIM)}")

    try:
        choice = input(f"  > ").strip()
    except (EOFError, KeyboardInterrupt):
        return current_sub

    if choice in choices:
        return choices[choice][0]
    return current_sub


# ============================================
# Jekyll File Generation
# ============================================

def write_jekyll_file(item: Dict, repo_root: Path) -> Optional[Path]:
    """Generate a Jekyll markdown file for an accepted item. Returns the file path."""
    ct = item.get("content_type", "resource")
    subcategory = item.get("subcategory", "")
    today = datetime.now().strftime("%Y-%m-%d")
    slug = slugify(item["title"])
    tags = item.get("tags", [])
    tags_yaml = "[" + ", ".join(yaml_quote(t) for t in tags if t) + "]" if tags else "[]"

    if ct == "skill":
        category = subcategory or "research-engineering"
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
        paper_cat = subcategory or "general"
        # Papers use _papers/<category-dir>/ for filesystem, category field in frontmatter
        paper_dir_name = f"0-{paper_cat}" if paper_cat != "general" else "0-general"
        out_dir = repo_root / "_papers" / paper_dir_name
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
category: {paper_cat}
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
        resource_cat = subcategory or "research-tool"
        out_dir = repo_root / "_resources" / f"0-{resource_cat}"
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
category: {resource_cat}
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
    top_n: int = 10,
    browse: bool = False,
) -> None:
    """Run auto-review + interactive approval of top N items."""

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

    # Deduplicate, classify, and score
    print()
    print(colored("Phase 2: Auto-review — classifying and filtering...", C.BOLD))
    seen: Set[str] = set()
    all_scored: List[Dict] = []
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

        # Smart classification: type + subcategory + suitability
        classification = classify_content(
            item.get("title", ""), item.get("description", ""),
            item.get("source", "").replace("opencli-", ""),
        )
        item["classification"] = classification
        item["content_type"] = classification["type"]
        item["subcategory"] = classification["subcategory"]

        all_scored.append(item)

    # --- Auto-review: reject, skip, or shortlist ---
    auto_rejected = []
    shortlist = []
    auto_skipped = []

    for item in all_scored:
        suit = item["classification"]["suitability"]
        score = item["score"]

        if suit == "not_recommended" or score < min_score:
            # Auto-reject: not relevant to AI4SS
            auto_rejected.append(item)
            save_rejected_item(
                repo_root,
                url=item.get("url", ""),
                title=item.get("title", ""),
                source=item.get("source", ""),
            )
        elif suit == "recommended" and score >= 4.0:
            # High confidence: shortlist for manual approval
            shortlist.append(item)
        else:
            # Maybe: auto-skip (will appear again next time)
            auto_skipped.append(item)

    # Sort shortlist by score desc, take top N
    shortlist.sort(key=lambda x: (x["score"], x.get("popularity", 0)), reverse=True)
    shortlist = shortlist[:top_n]

    print(f"  {len(all_results)} raw → {len(all_scored)} unique")
    print(f"  {colored(f'✅ {len(shortlist)}', C.GREEN)} shortlisted for your review")
    print(f"  {colored(f'❌ {len(auto_rejected)}', C.RED)} auto-rejected (irrelevant / low score, saved to rejected.json)")
    print(f"  {colored(f'⏭️  {len(auto_skipped)}', C.YELLOW)} auto-skipped (uncertain, will reappear next time)")

    if not shortlist:
        print(f"\n  {colored('No high-quality items found this round.', C.YELLOW)}")
        # Show best of the auto-skipped as hint
        if auto_skipped:
            auto_skipped.sort(key=lambda x: x["score"], reverse=True)
            best = auto_skipped[0]
            print(f"  Best 'maybe': {best['title'][:60]}... (score: {best['score']:.1f})")
            print(f"  Try lowering --min-score or widening platforms.")
        return

    # Interactive review of shortlisted items only
    print()
    print(colored(f"Phase 3: Review top {len(shortlist)} items", C.BOLD))
    print(f"  Only the best items are shown. Accept, reject, or tweak category.")
    print()

    accepted_files: List[Path] = []
    accepted_count = 0
    rejected_count = 0
    skipped_once_count = 0

    for i, item in enumerate(shortlist, 1):
        display_item(item, i, len(shortlist))
        action = prompt_action(item)

        if action == "q":
            print(f"\n  {colored('Quit. Finishing up...', C.DIM)}")
            break
        elif action == "n":
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
            skipped_once_count += 1
            continue
        elif action in ("s", "p", "r"):
            type_map = {"s": "skill", "p": "paper", "r": "resource"}
            item["content_type"] = type_map[action]
            default_sub = SUBCATEGORY_CHOICES.get(item["content_type"], {}).get("1", ("", ""))[0]
            item["subcategory"] = prompt_subcategory(item["content_type"], item.get("subcategory", default_sub))
            action = "y"
        elif action == "c":
            item["subcategory"] = prompt_subcategory(item["content_type"], item.get("subcategory", ""))
            action = "y"

        if action == "y":
            filepath = write_jekyll_file(item, repo_root)
            if filepath:
                accepted_files.append(filepath)
                accepted_count += 1
                print(f"  {colored('✓ Saved!', C.GREEN)} {filepath.relative_to(repo_root)}")
            else:
                skipped_once_count += 1

    # Summary
    print()
    print(colored("━━━ Summary ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", C.BOLD))
    print(f"  {colored(str(accepted_count), C.GREEN)} accepted")
    print(f"  {colored(str(rejected_count), C.RED)} manually rejected")
    print(f"  {colored(str(skipped_once_count), C.YELLOW)} skipped (下次还会出现)")
    print(f"  {colored(str(len(auto_rejected)), C.DIM)} auto-rejected this round")

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
        help="Minimum relevance score for auto-review (default: 2.0)",
    )
    parser.add_argument(
        "--top-n", type=int, default=10,
        help="Number of top items to present for manual review (default: 10)",
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
        top_n=args.top_n,
        browse=args.browse,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
