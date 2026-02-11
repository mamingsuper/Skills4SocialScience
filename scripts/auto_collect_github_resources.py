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

QUERIES = [
    '"social science" AI research tool',
    '"computational social science" LLM',
    '"open science" reproducible research AI',
    'survey experiment causal inference AI',
    'knowledge graph social science',
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Repository root directory")
    parser.add_argument("--max-new", type=int, default=5, help="Maximum number of new resources to add")
    parser.add_argument("--min-stars", type=int, default=10, help="Minimum stargazer count")
    parser.add_argument("--lookback-days", type=int, default=14, help="Only keep recently updated repositories")
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
    values = [item for item in values if item]
    if not values:
        return "[]"
    return "[" + ", ".join(yaml_quote(item) for item in values) + "]"


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
    if any(token in normalized_topics or token in text for token in ["workflow", "reproducibility", "open-science", "pipeline"]):
        return "workflow"
    if any(token in normalized_topics or token in text for token in ["community", "awesome", "list", "directory"]):
        return "community"
    return "research-tool"


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
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] repo detail failed: {owner}/{repo} -> {exc}")
        return None


def upsert_front_matter(md_text: str, updates: Dict[str, str]) -> str:
    if not md_text.startswith("---"):
        return md_text

    parts = md_text.split("---", 2)
    if len(parts) < 3:
        return md_text

    front_matter_lines = parts[1].strip("\n").splitlines()

    for key, yaml_value in updates.items():
        target = f"{key}: {yaml_value}"
        replaced = False
        for idx, line in enumerate(front_matter_lines):
            if re.match(rf"^{re.escape(key)}\\s*:", line):
                front_matter_lines[idx] = target
                replaced = True
                break
        if not replaced:
            front_matter_lines.append(target)

    updated_front_matter = "\n".join(front_matter_lines)
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


def github_search(query: str, lookback_days: int, token: str | None) -> List[Dict[str, object]]:
    since_date = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=lookback_days)).date().isoformat()
    full_query = f"{query} pushed:>={since_date} archived:false fork:false"

    params = urllib.parse.urlencode(
        {
            "q": full_query,
            "sort": "updated",
            "order": "desc",
            "per_page": "30",
        }
    )
    url = f"{SEARCH_URL}?{params}"

    request = urllib.request.Request(url, headers=github_headers(token))

    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    return payload.get("items", [])


def collect_candidates(min_stars: int, lookback_days: int, token: str | None) -> List[Dict[str, object]]:
    seen: Set[str] = set()
    candidates: List[Dict[str, object]] = []

    for query in QUERIES:
        try:
            items = github_search(query, lookback_days, token)
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] query failed: {query} -> {exc}")
            continue

        for item in items:
            link = normalize_link(str(item.get("html_url", "")))
            if not link or link in seen:
                continue
            seen.add(link)

            stars = int(item.get("stargazers_count") or 0)
            if stars < min_stars:
                continue

            candidates.append(item)

    candidates.sort(key=lambda item: int(item.get("stargazers_count") or 0), reverse=True)
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

Auto-collected by AI4SS from recent GitHub updates.

- GitHub: {link}
- Stars: {stars}
- Last updated: {updated_at}
- Category: {category}

Use this repository as a candidate tool/reference for AI-enabled social science workflows.
"""

    return slug, markdown


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    resources_dir = repo_root / "_resources"

    if not resources_dir.exists():
        print(f"[ERROR] resources directory not found: {resources_dir}")
        return 1

    existing_links = load_existing_links(resources_dir)
    used_slugs = {path.stem for path in resources_dir.glob("*.md")}
    token = os.getenv("GITHUB_TOKEN")

    refreshed_count = refresh_existing_github_metrics(resources_dir, token, args.dry_run)
    if refreshed_count > 0:
        print(f"[INFO] refreshed stars for {refreshed_count} existing resources")

    candidates = collect_candidates(
        min_stars=args.min_stars,
        lookback_days=args.lookback_days,
        token=token,
    )

    new_count = 0
    for item in candidates:
        link = normalize_link(str(item.get("html_url") or ""))
        if not link or link in existing_links:
            continue

        slug, markdown = build_markdown(item, used_slugs)
        output_path = resources_dir / f"{slug}.md"

        if args.dry_run:
            print(f"[DRY-RUN] would create: {output_path}")
        else:
            output_path.write_text(markdown, encoding="utf-8")
            print(f"[NEW] {output_path}")

        existing_links.add(link)
        new_count += 1

        if new_count >= args.max_new:
            break

    if new_count > 0:
        print(f"[INFO] added {new_count} resources")
    elif refreshed_count == 0:
        print("[INFO] no new repositories found")

    return 0


if __name__ == "__main__":
    sys.exit(main())
