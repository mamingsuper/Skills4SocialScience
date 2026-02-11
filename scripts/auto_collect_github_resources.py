#!/usr/bin/env python3
"""Auto-collect GitHub repositories into the Jekyll resources collection."""

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
from typing import Dict, Iterable, List, Set

SEARCH_URL = "https://api.github.com/search/repositories"
REPO_URL_TEMPLATE = "https://api.github.com/repos/{owner}/{repo}"

RESEARCH_STEPS = [
    "literature review",
    "data collection",
    "data cleaning",
    "causal inference",
    "survey experiment",
    "reproducible research",
    "open science workflow",
    "analysis pipeline",
    "scientific writing",
    "visualization",
]

DISCIPLINES = [
    "political science",
    "economics",
    "sociology",
    "psychology",
    "public policy",
    "education research",
    "communication research",
    "anthropology",
]

TOPIC_QUERIES = [
    "topic:computational-social-science",
    "topic:open-science",
    "topic:social-science",
    "topic:causal-inference",
    "topic:survey-methods",
]

SEED_REPOS = [
    "awesomelistsio/awesome-open-science",
    "compsocialscience/summer-institute",
    "GESISCSS/awesome-computational-social-science",
    "ExpectedParrot/edsl",
    "siyaozheng/AI4SS-skills",
    "TIGER-AI-Lab/OpenResearcher",
]


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


def build_primary_queries() -> List[str]:
    queries: List[str] = []
    step_clause = " OR ".join(f'"{step}"' for step in RESEARCH_STEPS)

    for discipline in DISCIPLINES:
        queries.append(
            f'"{discipline}" ({step_clause}) (AI OR LLM OR agentic) (tool OR framework OR pipeline)'
        )
        queries.append(
            f'"{discipline}" (computational OR digital) "open science" (toolkit OR workflow)'
        )

    for step in RESEARCH_STEPS:
        queries.append(
            f'"social science" "{step}" (AI OR LLM OR agentic) (tool OR framework OR pipeline)'
        )

    return dedupe_preserve_order(queries)


def build_fallback_queries() -> List[str]:
    keyword_queries = [
        '"social science" "agentic workflow" toolkit',
        '"reproducible research" "social science" "AI tool"',
        '"computational social science" "open science" toolkit',
        '"social science" "LLM" framework',
        '"causal inference" "social science" "AI tool"',
        '"survey experiment" "AI" "research workflow"',
    ]
    return dedupe_preserve_order(TOPIC_QUERIES + keyword_queries)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root directory")
    parser.add_argument("--max-new", type=int, default=8, help="Maximum number of new resources to add")
    parser.add_argument("--min-new", type=int, default=2, help="Preferred minimum new resources per run")
    parser.add_argument("--min-stars", type=int, default=15, help="Minimum stars for primary search")
    parser.add_argument("--lookback-days", type=int, default=45, help="Primary search window in days")
    parser.add_argument("--fallback-min-stars", type=int, default=40, help="Minimum stars for fallback searches")
    parser.add_argument(
        "--fallback-lookback-days",
        type=int,
        default=3650,
        help="Fallback search window in days (large value ~= broad historical scan)",
    )
    parser.add_argument("--pages-per-query", type=int, default=4, help="Pages to request per query")
    parser.add_argument("--per-page", type=int, default=30, help="Items per page for GitHub search")
    parser.add_argument("--dry-run", action="store_true", help="Print candidates without writing files")
    return parser.parse_args()


def normalize_link(link: str) -> str:
    return link.strip().lower().rstrip("/")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "resource"


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
        "User-Agent": "AI4SS-AutoCollector",
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


def load_existing_links(resources_dir: Path) -> Set[str]:
    links: Set[str] = set()
    for md_path in resources_dir.glob("*.md"):
        metadata = extract_front_matter(md_path.read_text(encoding="utf-8"))
        link = metadata.get("link")
        if link:
            links.add(normalize_link(link))
    return links


def classify_resource(topics: List[str], description: str) -> str:
    normalized_topics = {item.lower() for item in topics}
    text = (description or "").lower()

    if any(token in normalized_topics or token in text for token in ["dataset", "data", "benchmark-dataset"]):
        return "dataset"
    if any(token in normalized_topics or token in text for token in ["benchmark", "leaderboard", "evaluation"]):
        return "benchmark"
    if any(token in normalized_topics or token in text for token in ["workflow", "reproducibility", "open-science", "pipeline", "toolkit"]):
        return "workflow"
    if any(token in normalized_topics or token in text for token in ["community", "awesome", "list", "directory"]):
        return "community"
    return "research-tool"


def parse_updated_timestamp(value: str) -> int:
    if not value:
        return 0
    try:
        normalized = value.replace("Z", "+00:00")
        return int(dt.datetime.fromisoformat(normalized).timestamp())
    except ValueError:
        return 0


def match_completeness(item: Dict[str, object]) -> tuple[int, int]:
    fields = [
        str(item.get("name") or ""),
        str(item.get("full_name") or ""),
        str(item.get("description") or ""),
    ]
    topics = item.get("topics") or []
    if isinstance(topics, list):
        fields.extend(str(topic) for topic in topics)

    haystack = " ".join(fields).lower()
    step_hits = sum(1 for step in RESEARCH_STEPS if step in haystack)
    discipline_hits = sum(1 for discipline in DISCIPLINES if discipline in haystack)
    full_match = 1 if step_hits > 0 and discipline_hits > 0 else 0
    total_hits = step_hits + discipline_hits
    return full_match, total_hits


def enrich_ranking_fields(item: Dict[str, object]) -> None:
    full_match, total_hits = match_completeness(item)
    item["_match_full"] = full_match
    item["_match_hits"] = total_hits
    item["_updated_ts"] = parse_updated_timestamp(str(item.get("updated_at") or ""))


def ranking_key(item: Dict[str, object]) -> tuple[int, int, int, int]:
    stars = int(item.get("stargazers_count") or 0)
    updated_ts = int(item.get("_updated_ts") or 0)
    full_match = int(item.get("_match_full") or 0)
    hit_count = int(item.get("_match_hits") or 0)
    return stars, updated_ts, full_match, hit_count


def parse_github_repo(link: str) -> tuple[str, str] | None:
    match = re.match(r"^https?://github\.com/([^/]+)/([^/#?]+)", link.strip(), flags=re.IGNORECASE)
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
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] repo detail failed: {owner}/{repo} -> {exc}")
        return None


def upsert_front_matter(md_text: str, updates: Dict[str, str]) -> str:
    if not md_text.startswith("---"):
        return md_text

    parts = md_text.split("---", 2)
    if len(parts) < 3:
        return md_text

    lines = parts[1].strip("\n").splitlines()
    keep_lines: List[str] = []

    key_pattern = re.compile(r"^([A-Za-z0-9_-]+)\s*:")
    for line in lines:
        match = key_pattern.match(line)
        if match and match.group(1) in updates:
            continue
        keep_lines.append(line)

    for key, yaml_value in updates.items():
        keep_lines.append(f"{key}: {yaml_value}")

    updated_front_matter = "\n".join(keep_lines)
    return f"---\n{updated_front_matter}\n---{parts[2]}"


def refresh_existing_github_metrics(resources_dir: Path, token: str | None, dry_run: bool) -> int:
    updated_count = 0
    for md_path in resources_dir.glob("*.md"):
        original = md_path.read_text(encoding="utf-8")
        metadata = extract_front_matter(original)
        link = metadata.get("link", "")
        parsed = parse_github_repo(link)
        if not parsed:
            continue

        owner, repo = parsed
        details = github_repo_details(owner, repo, token)
        if not details:
            continue

        stars = int(details.get("stargazers_count") or 0)
        updated_at = str(details.get("updated_at") or "")[:10]
        license_name = ""
        license_obj = details.get("license") or {}
        if isinstance(license_obj, dict):
            license_name = str(license_obj.get("spdx_id") or "")

        updated = upsert_front_matter(
            original,
            {
                "stars": str(stars),
                "last_updated": updated_at,
                "license": yaml_quote(license_name),
            },
        )

        if updated == original:
            continue

        if dry_run:
            print(f"[DRY-RUN] would refresh metrics: {md_path}")
        else:
            md_path.write_text(updated, encoding="utf-8")
            print(f"[REFRESH] {md_path}")
        updated_count += 1

    return updated_count


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

    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

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
            try:
                items = github_search(
                    query,
                    token,
                    lookback_days=lookback_days,
                    sort=sort,
                    order=order,
                    per_page=per_page,
                    page=page,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[WARN] query failed: {query} (page={page}) -> {exc}")
                break

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


def fetch_seed_candidates(token: str | None, min_stars: int) -> List[Dict[str, object]]:
    candidates: List[Dict[str, object]] = []
    for full_name in SEED_REPOS:
        if "/" not in full_name:
            continue
        owner, repo = full_name.split("/", 1)
        details = github_repo_details(owner, repo, token)
        if not details:
            continue

        stars = int(details.get("stargazers_count") or 0)
        if stars < min_stars:
            continue
        candidates.append(details)

    candidates.sort(key=ranking_key, reverse=True)
    return candidates


def build_markdown(item: Dict[str, object], used_slugs: Set[str]) -> tuple[str, str]:
    repo_name = str(item.get("name") or "Untitled")
    owner = str((item.get("owner") or {}).get("login") or "unknown")
    description = str(item.get("description") or "GitHub repository relevant to AI-enabled social science research.")
    description = description.replace("\n", " ").strip()
    if len(description) > 180:
        description = description[:177].rstrip() + "..."

    topics = [str(topic) for topic in (item.get("topics") or [])][:6]
    category = classify_resource(topics, description)
    stars = int(item.get("stargazers_count") or 0)
    updated_at = str(item.get("updated_at") or "")[:10]
    license_name = ""
    license_obj = item.get("license") or {}
    if isinstance(license_obj, dict):
        license_name = str(license_obj.get("spdx_id") or "")

    base_slug = slugify(f"{owner}-{repo_name}")
    slug = base_slug
    idx = 2
    while slug in used_slugs:
        slug = f"{base_slug}-{idx}"
        idx += 1
    used_slugs.add(slug)

    link = str(item.get("html_url") or "")
    markdown = f"""---
layout: resource
title: {yaml_quote(repo_name)}
description: {yaml_quote(description)}
type: GitHub Repository
category: {category}
link: {link}
source: github-auto
stars: {stars}
last_updated: {updated_at}
license: {yaml_quote(license_name)}
tags: {yaml_list(topics)}
permalink: /resources/{slug}/
---
## {repo_name} ({owner})

Auto-collected by AI4SS from GitHub discovery.

- GitHub: {link}
- Stars: {stars}
- Last updated: {updated_at}
- Category: {category}

Use this repository as a candidate tool/reference for AI-enabled social science workflows.
"""

    return slug, markdown


def write_new_candidates(
    candidates: List[Dict[str, object]],
    *,
    existing_links: Set[str],
    used_slugs: Set[str],
    resources_dir: Path,
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

        slug, markdown = build_markdown(item, used_slugs)
        output_path = resources_dir / f"{slug}.md"

        if dry_run:
            print(f"[DRY-RUN] would create: {output_path}")
        else:
            output_path.write_text(markdown, encoding="utf-8")
            print(f"[NEW] {output_path}")

        existing_links.add(link)
        new_count += 1

    return new_count


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    resources_dir = repo_root / "_resources"

    if not resources_dir.exists():
        print(f"[ERROR] resources directory not found: {resources_dir}")
        return 1

    token = os.getenv("GITHUB_TOKEN")
    existing_links = load_existing_links(resources_dir)
    used_slugs = {path.stem for path in resources_dir.glob("*.md")}
    print(f"[INFO] existing resources: {len(used_slugs)}")

    refreshed_count = refresh_existing_github_metrics(resources_dir, token, args.dry_run)
    if refreshed_count > 0:
        print(f"[INFO] refreshed stars for {refreshed_count} existing resources")

    primary_queries = build_primary_queries()
    fallback_queries = build_fallback_queries()
    print(f"[INFO] primary query count: {len(primary_queries)}")
    print(f"[INFO] fallback query count: {len(fallback_queries)}")

    primary_candidates = collect_candidates(
        queries=primary_queries,
        min_stars=args.min_stars,
        lookback_days=args.lookback_days,
        token=token,
        sort="updated",
        order="desc",
        pages_per_query=args.pages_per_query,
        per_page=args.per_page,
    )
    print(f"[INFO] primary candidates: {len(primary_candidates)}")

    fallback_candidates = collect_candidates(
        queries=fallback_queries,
        min_stars=args.fallback_min_stars,
        lookback_days=args.fallback_lookback_days,
        token=token,
        sort="stars",
        order="desc",
        pages_per_query=args.pages_per_query,
        per_page=args.per_page,
    )
    print(f"[INFO] fallback candidates: {len(fallback_candidates)}")

    combined_candidates: List[Dict[str, object]] = []
    candidate_seen: Set[str] = set()

    for item in primary_candidates + fallback_candidates:
        link = normalize_link(str(item.get("html_url") or ""))
        if not link or link in candidate_seen:
            continue
        candidate_seen.add(link)
        combined_candidates.append(item)

    combined_candidates.sort(key=ranking_key, reverse=True)

    new_count = write_new_candidates(
        combined_candidates,
        existing_links=existing_links,
        used_slugs=used_slugs,
        resources_dir=resources_dir,
        dry_run=args.dry_run,
        max_new=args.max_new,
    )

    if new_count < args.min_new:
        seed_candidates = fetch_seed_candidates(token, args.fallback_min_stars)
        print(f"[INFO] seed candidates: {len(seed_candidates)}")
        new_count = write_new_candidates(
            seed_candidates,
            existing_links=existing_links,
            used_slugs=used_slugs,
            resources_dir=resources_dir,
            dry_run=args.dry_run,
            max_new=args.max_new,
            start_count=new_count,
        )

    if new_count > 0:
        print(f"[INFO] added {new_count} resources")
    elif refreshed_count == 0:
        print("[INFO] no new repositories found")

    if new_count < args.min_new:
        print(
            f"[WARN] below target {new_count}/{args.min_new}. "
            "Insufficient qualified candidates after primary + fallback + seed layers."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
