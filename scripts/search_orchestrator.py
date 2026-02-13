#!/usr/bin/env python3
"""
Multi-channel Search Orchestrator for Skills4SocialScience
Implements dual-thread search: Scholar (academic) + Skill (practical)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set, Optional


# ============================================
# Data Models
# ============================================

@dataclass
class SearchResult:
    """Unified search result schema"""
    title: str
    description: str
    link: str
    source: str  # 'semantic-scholar', 'arxiv', 'github', etc.
    result_type: str  # 'paper', 'repository', 'tutorial', 'dataset'
    published_date: Optional[str] = None
    authors: Optional[List[str]] = None
    stars: Optional[int] = None
    citations: Optional[int] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for Jekyll frontmatter"""
        desc = self.description[:200] + '...' if len(self.description) > 200 else self.description
        return {
            'title': self.title,
            'description': desc,
            'link': self.link,
            'source': self.source,
            'type': self.result_type,
            'published_date': self.published_date,
            'authors': (self.authors or [])[:3],
            'stars': self.stars,
            'citations': self.citations,
            'tags': self.tags or [],
            'metadata': self.metadata or {}
        }


@dataclass
class SearchConfig:
    """Configuration for search orchestrator"""
    repo_root: str = "."
    github_token: Optional[str] = None
    youtube_api_key: Optional[str] = None
    max_results: int = 20
    scholar_ratio: float = 0.6
    output_format: str = "markdown"  # markdown, json
    dry_run: bool = False


# ============================================
# Base Adapter
# ============================================

class BaseAdapter:
    """Abstract base class for search adapters"""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path.home() / ".ai4ss_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.source_name = self.__class__.__name__.lower().replace('adapter', '')

    def search(self, query: str, **kwargs) -> List[SearchResult]:
        """Execute search query"""
        raise NotImplementedError

    def get_rate_limit_info(self) -> Dict:
        """Return rate limit information"""
        return {'source': self.source_name, 'limit': 'Not specified'}

    def _get_cache_key(self, query: str, **kwargs) -> str:
        """Generate cache key"""
        key_parts = [self.source_name, query]
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}={v}")
        return "-".join(key_parts).lower().replace(" ", "_")

    def _load_from_cache(self, cache_key: str) -> Optional[List]:
        """Load results from cache"""
        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    cached = json.load(f)
                # Check if cache is fresh (24 hours)
                if time.time() - cached.get('timestamp', 0) < 86400:
                    return cached.get('results', [])
            except Exception:
                pass
        return None

    def _save_to_cache(self, cache_key: str, results: List):
        """Save results to cache"""
        cache_file = self.cache_dir / f"{cache_key}.json"
        try:
            with open(cache_file, 'w') as f:
                json.dump({
                    'timestamp': time.time(),
                    'results': [asdict(r) if isinstance(r, SearchResult) else r for r in results]
                }, f)
        except Exception:
            pass


# ============================================
# Scholar Channel Adapters
# ============================================

class SemanticScholarAdapter(BaseAdapter):
    """Adapter for Semantic Scholar API (Scholar thread)"""

    API_BASE = "https://api.semanticscholar.org/graph/v1"

    def search(self, query: str, limit: int = 20, year: Optional[str] = None) -> List[SearchResult]:
        cache_key = self._get_cache_key(query, limit=limit, year=year)
        cached = self._load_from_cache(cache_key)
        if cached:
            return [SearchResult(**r) for r in cached]

        url = f"{self.API_BASE}/paper/search"
        params = {
            'query': query,
            'limit': str(limit),
            'fields': 'paperId,title,abstract,authors,year,citationCount,publicationVenue,url'
        }
        if year:
            params['year'] = year

        full_url = f"{url}?{urllib.parse.urlencode(params)}"
        results = []

        try:
            with urllib.request.urlopen(full_url, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))

                for item in data.get('data', []):
                    result = SearchResult(
                        title=item.get('title', ''),
                        description=item.get('abstract', '')[:500] or item.get('title', ''),
                        link=item.get('url', f"https://www.semanticscholar.org/paper/{item.get('paperId', '')}"),
                        source=self.source_name,
                        result_type='paper',
                        published_date=str(item.get('year', '')) if item.get('year') else None,
                        authors=[a.get('name', '') for a in item.get('authors', [])],
                        citations=item.get('citationCount', 0),
                        tags=[item.get('publicationVenue', 'unknown')],
                        metadata={
                            'paperId': item.get('paperId'),
                            'venue': item.get('publicationVenue')
                        }
                    )
                    results.append(result)

            self._save_to_cache(cache_key, [asdict(r) for r in results])
        except Exception as exc:
            print(f"[WARN] Semantic Scholar search failed: {exc}")

        return results


class ArxivAdapter(BaseAdapter):
    """Adapter for arXiv API (Scholar thread)"""

    API_BASE = "http://export.arxiv.org/api/query"

    def search(self, query: str, max_results: int = 20, categories: Optional[List[str]] = None) -> List[SearchResult]:
        cache_key = self._get_cache_key(query, max_results=max_results)
        cached = self._load_from_cache(cache_key)
        if cached:
            return [SearchResult(**r) for r in cached]

        params = {
            'search_query': f"all:{query}" + (f" AND cat:{','.join(categories)}" if categories else ""),
            'start': '0',
            'max_results': str(max_results),
            'sortBy': 'submittedDate',
            'sortOrder': 'descending'
        }

        full_url = f"{self.API_BASE}?{urllib.parse.urlencode(params)}"
        results = []

        try:
            with urllib.request.urlopen(full_url, timeout=30) as response:
                data = response.read().decode('utf-8')

                # Parse arXiv XML response
                import xml.etree.ElementTree as ET
                root = ET.fromstring(data)

                for entry in root.findall('{http://www.w3.org/2005/Atom}entry'):
                    title = entry.find('{http://www.w3.org/2005/Atom}title')
                    summary = entry.find('{http://www.w3.org/2005/Atom}summary')
                    published = entry.find('{http://www.w3.org/2005/Atom}published')
                    authors = entry.findall('{http://www.w3.org/2005/Atom}author')
                    link = entry.find('{http://www.w3.org/2005/Atom}id')

                    if title is not None and summary is not None:
                        result = SearchResult(
                            title=title.text,
                            description=summary.text[:300],
                            link=link.text if link is not None else '',
                            source=self.source_name,
                            result_type='paper',
                            published_date=published.text[:10] if published is not None else None,
                            authors=[a.find('{http://www.w3.org/2005/Atom}name').text for a in authors if a.find('{http://www.w3.org/2005/Atom}name') is not None],
                            tags=['preprint'],
                            metadata={'source': 'arxiv'}
                        )
                        results.append(result)

            self._save_to_cache(cache_key, [asdict(r) for r in results])
        except Exception as exc:
            print(f"[WARN] arXiv search failed: {exc}")

        return results


# ============================================
# Skill Channel Adapters
# ============================================

class GitHubAdapter(BaseAdapter):
    """Adapter for GitHub API (Skill thread)"""

    API_BASE = "https://api.github.com"
    SEARCH_URL = f"{API_BASE}/search/repositories"
    REPO_URL_TEMPLATE = f"{API_BASE}/repos/{{owner}}/{{repo}}"

    def __init__(self, cache_dir: Optional[Path] = None, token: Optional[str] = None):
        super().__init__(cache_dir)
        self.token = token

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'AI4SS-SearchOrchestrator',
            'X-GitHub-Api-Version': '2022-11-28'
        }
        if self.token:
            headers['Authorization'] = f"Bearer {self.token}"
        return headers

    def search(self, query: str, limit: int = 20, min_stars: int = 10) -> List[SearchResult]:
        cache_key = self._get_cache_key(query, limit=limit, min_stars=min_stars)
        cached = self._load_from_cache(cache_key)
        if cached:
            return [SearchResult(**r) for r in cached]

        params = {
            'q': f"{query} stars:>={min_stars}",
            'sort': 'stars',
            'order': 'desc',
            'per_page': str(limit)
        }

        url = f"{self.SEARCH_URL}?{urllib.parse.urlencode(params)}"
        results = []

        try:
            request = urllib.request.Request(url, headers=self._get_headers())
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))

                for item in data.get('items', []):
                    result = SearchResult(
                        title=item.get('name', ''),
                        description=item.get('description', '')[:200],
                        link=item.get('html_url', ''),
                        source=self.source_name,
                        result_type='repository',
                        published_date=item.get('updated_at', '')[:10] if item.get('updated_at') else None,
                        stars=item.get('stargazers_count', 0),
                        tags=[str(t) for t in (item.get('topics', []) or [])[:5]],
                        metadata={
                            'language': item.get('language'),
                            'license': item.get('license', {}).get('spdx_id', ''),
                            'forks': item.get('forks_count', 0)
                        }
                    )
                    results.append(result)

            self._save_to_cache(cache_key, [asdict(r) for r in results])
        except Exception as exc:
            print(f"[WARN] GitHub search failed: {exc}")

        return results


# ============================================
# Search Orchestrator
# ============================================

class SearchOrchestrator:
    """Coordinates multi-channel search across Scholar and Skill threads"""

    DISCIPLINES = [
        "political science",
        "economics",
        "sociology",
        "psychology",
        "public policy",
        "communication research"
    ]

    WORKFLOW_STAGES = [
        "literature review",
        "research design",
        "data collection",
        "data analysis",
        "writing",
        "presentation"
    ]

    def __init__(self, config: SearchConfig):
        self.config = config
        self.cache_dir = Path.home() / ".ai4ss_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Initialize adapters
        self.scholar_adapters = [
            SemanticScholarAdapter(self.cache_dir),
            ArxivAdapter(self.cache_dir)
        ]

        self.skill_adapters = [
            GitHubAdapter(self.cache_dir, token=config.github_token)
        ]

    def _build_scholar_query(self, query: str, discipline: Optional[str] = None,
                           workflow_stage: Optional[str] = None) -> str:
        """Build optimized query for academic search"""
        parts = []

        if discipline:
            parts.append(f'"{discipline}"')
        if workflow_stage:
            parts.append(f'"{workflow_stage}"')

        parts.extend(['AI', 'LLM', 'machine learning'])

        return ' '.join(parts)

    def _build_skill_query(self, query: str, discipline: Optional[str] = None,
                         workflow_stage: Optional[str] = None) -> str:
        """Build optimized query for practical resources"""
        parts = []

        if discipline:
            parts.append(f'"{discipline}"')
        if workflow_stage:
            parts.append(f'"{workflow_stage}"')

        # Add skill-oriented keywords
        skill_keywords = ['tool', 'framework', 'tutorial', 'guide', 'workflow', 'pipeline']
        parts.append(f"({' OR '.join(skill_keywords)})")

        return ' '.join(parts)

    def search_dual_thread(
        self,
        query: str,
        discipline: Optional[str] = None,
        workflow_stage: Optional[str] = None
    ) -> Dict[str, List[SearchResult]]:
        """Execute dual-thread search"""
        print(f"[INFO] Starting dual-thread search: {query}")
        print(f"[INFO] Discipline: {discipline or 'all'}, Stage: {workflow_stage or 'all'}")

        # Thread 1: Scholar (Academic)
        print("[INFO] Thread 1: Searching academic sources...")
        scholar_count = int(self.config.max_results * self.config.scholar_ratio)
        scholar_query = self._build_scholar_query(query, discipline, workflow_stage)

        scholar_results = []
        for adapter in self.scholar_adapters:
            try:
                results = adapter.search(scholar_query, limit=scholar_count // len(self.scholar_adapters))
                scholar_results.extend(results)
            except Exception as exc:
                print(f"[WARN] {adapter.source_name} search failed: {exc}")

        # Deduplicate and limit
        scholar_results = self._deduplicate_scholar(scholar_results)[:scholar_count]
        print(f"[INFO] Found {len(scholar_results)} academic results")

        # Thread 2: Skill (Practical)
        print("[INFO] Thread 2: Searching practical resources...")
        skill_count = self.config.max_results - scholar_count
        skill_query = self._build_skill_query(query, discipline, workflow_stage)

        skill_results = []
        for adapter in self.skill_adapters:
            try:
                results = adapter.search(skill_query, limit=skill_count)
                skill_results.extend(results)
            except Exception as exc:
                print(f"[WARN] {adapter.source_name} search failed: {exc}")

        skill_results = self._deduplicate_skill(skill_results)[:skill_count]
        print(f"[INFO] Found {len(skill_results)} practical results")

        return {
            'scholar': scholar_results,
            'skill': skill_results
        }

    def _deduplicate_scholar(self, results: List[SearchResult]) -> List[SearchResult]:
        """Remove duplicates based on title similarity"""
        seen = set()
        unique = []
        for result in results:
            key = result.title.lower().strip()
            if key not in seen:
                seen.add(key)
                unique.append(result)
        return unique

    def _deduplicate_skill(self, results: List[SearchResult]) -> List[SearchResult]:
        """Remove duplicates based on URL"""
        seen = set()
        unique = []
        for result in results:
            key = result.link.lower().strip()
            if key not in seen:
                seen.add(key)
                unique.append(result)
        return unique

    def search_by_discipline_stage_matrix(self) -> Dict[str, Dict[str, Dict]]:
        """Search for all discipline x stage combinations"""
        results = {}
        for discipline in self.DISCIPLINES:
            results[discipline] = {}
            for stage in self.WORKFLOW_STAGES:
                query = f"{discipline} {stage}"
                results[discipline][stage] = self.search_dual_thread(
                    query=query,
                    discipline=discipline,
                    workflow_stage=stage
                )
        return results


# ============================================
# Jekyll Generator
# ============================================

class JekyllGenerator:
    """Generates Jekyll markdown files from search results"""

    PAPERS_DIR = "_papers/0-general"
    RESOURCES_DIR = "_resources/0-general"

    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root).resolve()

    def generate_paper(self, result: SearchResult, dry_run: bool = False) -> bool:
        """Generate a Jekyll markdown file for a paper"""
        self.repo_root.mkdir(parents=True, exist_ok=True)
        papers_dir = self.repo_root / self.PAPERS_DIR
        papers_dir.mkdir(parents=True, exist_ok=True)

        # Generate slug
        slug = result.title.lower()[:50].replace(" ", "-").replace("/", "-")
        filename = papers_dir / f"{slug}.md"

        if filename.exists():
            return False

        frontmatter = f"""---
layout: paper
title: {result.title}
description: {result.description[:200]}
authors: {json.dumps(result.authors or [], ensure_ascii=False)}
year: {result.published_date[:4] if result.published_date else '2024'}
journal: {result.metadata.get('venue', 'unknown') if result.metadata else 'unknown'}
category: general
link: {result.link}
source: {result.source}
citations: {result.citations or 0}
tags: {json.dumps(result.tags or [], ensure_ascii=False)}
permalink: /papers/{slug}/
---

## {result.title}

{result.description}

### Details

- **Authors**: {', '.join(result.authors or [])}
- **Published**: {result.published_date}
- **Journal/Venue**: {result.metadata.get('venue', 'unknown') if result.metadata else 'unknown'}
- **Citations**: {result.citations or 0}
- **Source**: {result.source}

### Access

- [Read Paper]({result.link})
"""

        if dry_run:
            print(f"[DRY-RUN] Would create paper: {filename}")
            return True
        else:
            filename.write_text(frontmatter, encoding='utf-8')
            print(f"[PAPER] Created: {filename}")
            return True

    def generate_resource(self, result: SearchResult, dry_run: bool = False) -> bool:
        """Generate a Jekyll markdown file for a resource"""
        self.repo_root.mkdir(parents=True, exist_ok=True)
        resources_dir = self.repo_root / self.RESOURCES_DIR
        resources_dir.mkdir(parents=True, exist_ok=True)

        # Generate slug
        slug = result.title.lower()[:50].replace(" ", "-").replace("/", "-")
        filename = resources_dir / f"{slug}.md"

        if filename.exists():
            return False

        category = 'research-tool'
        if result.result_type == 'dataset':
            category = 'dataset'
        elif result.result_type == 'repository':
            category = 'research-tool'

        frontmatter = f"""---
layout: resource
title: {result.title}
description: {result.description[:200]}
type: {result.result_type}
category: {category}
link: {result.link}
source: {result.source}
stars: {result.stars or 0}
last_updated: {result.published_date or 'N/A'}
tags: {json.dumps(result.tags or [], ensure_ascii=False)}
metadata: {json.dumps(result.metadata or {}, ensure_ascii=False)}
permalink: /resources/{slug}/
---

## {result.title}

{result.description}

### Details

- **Type**: {result.result_type}
- **Stars**: {result.stars or 0}
- **Last Updated**: {result.published_date or 'N/A'}
- **Source**: {result.source}

### Access

- [View Resource]({result.link})
"""

        if dry_run:
            print(f"[DRY-RUN] Would create resource: {filename}")
            return True
        else:
            filename.write_text(frontmatter, encoding='utf-8')
            print(f"[RESOURCE] Created: {filename}")
            return True


# ============================================
# Main
# ============================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Multi-channel search orchestrator for AI4SS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python search_orchestrator.py --query "causal inference"
  python search_orchestrator.py --discipline economics --workflow-stage analysis
  python search_orchestrator.py --matrix --dry-run
        """
    )

    parser.add_argument("--query", help="Search query string")
    parser.add_argument("--discipline", help="Academic discipline (e.g., economics, sociology)")
    parser.add_argument("--workflow-stage", help="Research workflow stage (e.g., literature, analysis)")
    parser.add_argument("--max-results", type=int, default=20, help="Maximum total results")
    parser.add_argument("--scholar-ratio", type=float, default=0.6,
                       help="Ratio of scholar results (0-1, default 0.6)")
    parser.add_argument("--repo-root", default=".", help="Repository root directory")
    parser.add_argument("--github-token", help="GitHub API token")
    parser.add_argument("--youtube-api-key", help="YouTube API key")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing files")
    parser.add_argument("--matrix", action="store_true", help="Run full discipline x stage matrix")
    parser.add_argument("--output", choices=['markdown', 'json'], default='markdown',
                       help="Output format")

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    config = SearchConfig(
        repo_root=args.repo_root,
        github_token=args.github_token or os.getenv('GITHUB_TOKEN'),
        youtube_api_key=args.youtube_api_key or os.getenv('YOUTUBE_API_KEY'),
        max_results=args.max_results,
        scholar_ratio=args.scholar_ratio,
        dry_run=args.dry_run
    )

    orchestrator = SearchOrchestrator(config)
    generator = JekyllGenerator(config.repo_root)

    if args.matrix:
        print("[INFO] Running full discipline x stage matrix search")
        results = orchestrator.search_by_discipline_stage_matrix()
        print(f"[INFO] Searched {len(results)} disciplines × {len(list(results.values())[0] if results else 0)} stages")
    elif args.query or args.discipline or args.workflow_stage:
        query = args.query or f"{args.discipline or ''} {args.workflow_stage or ''}"
        results = orchestrator.search_dual_thread(
            query=query,
            discipline=args.discipline,
            workflow_stage=args.workflow_stage
        )

        # Generate Jekyll content
        papers_count = 0
        resources_count = 0

        for result in results['scholar']:
            if generator.generate_paper(result, dry_run=config.dry_run):
                papers_count += 1

        for result in results['skill']:
            if generator.generate_resource(result, dry_run=config.dry_run):
                resources_count += 1

        if args.output == 'json':
            output = {
                'scholar': [asdict(r) for r in results['scholar']],
                'skill': [asdict(r) for r in results['skill']],
                'stats': {
                    'papers': papers_count,
                    'resources': resources_count
                }
            }
            print(json.dumps(output, indent=2, ensure_ascii=False))
        else:
            print(f"[INFO] Generated {papers_count} papers and {resources_count} resources")
    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
