"""Entity consolidation and cluster analysis for Drive RAG.

This module provides tools for:
- Analyzing entity clusters to find potential duplicates
- Computing similarity between entities
- Generating consolidation recommendations
"""

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

import structlog

from drive_rag.entities import get_graphiti_client, DRIVE_RAG_GROUP_ID

logger = structlog.get_logger(__name__)


@dataclass
class EntityCluster:
    """A cluster of potentially duplicate entities."""

    canonical: dict  # The suggested canonical entity
    duplicates: list[dict]  # Entities that may be duplicates
    similarity_scores: list[float]  # Similarity score for each duplicate
    merge_confidence: str  # "high", "medium", "low"
    entity_type: str  # The entity type (Person, Organization, etc.)


@dataclass
class ConsolidationReport:
    """Report of entity consolidation analysis."""

    total_entities: int
    unique_types: dict[str, int]  # Count by entity type
    clusters: list[EntityCluster]
    potential_duplicates: int
    recommendations: list[str]


def extract_entity_text(entity: dict) -> str:
    """Extract searchable text from an entity for comparison."""
    name = entity.get("name", "")
    summary = entity.get("summary", "")
    return f"{name} {summary}".lower()


def compute_name_similarity(name1: str, name2: str) -> float:
    """Compute similarity between two entity names.

    Uses multiple heuristics:
    - Exact match
    - Substring containment
    - Abbreviation matching
    - Token overlap
    """
    n1 = name1.lower().strip()
    n2 = name2.lower().strip()

    # Exact match
    if n1 == n2:
        return 1.0

    # One is substring of other
    if n1 in n2 or n2 in n1:
        shorter = min(len(n1), len(n2))
        longer = max(len(n1), len(n2))
        return 0.7 + (0.3 * shorter / longer)

    # Check for abbreviation (e.g., "NSF" vs "National Science Foundation")
    words1 = n1.split()
    words2 = n2.split()

    # Check if one is abbreviation of other
    if len(words1) == 1 and len(words1[0]) <= 5:
        # n1 might be abbreviation
        initials = "".join(w[0] for w in words2 if w)
        if n1 == initials:
            return 0.9
    if len(words2) == 1 and len(words2[0]) <= 5:
        # n2 might be abbreviation
        initials = "".join(w[0] for w in words1 if w)
        if n2 == initials:
            return 0.9

    # Token overlap (Jaccard similarity)
    set1 = set(words1)
    set2 = set(words2)

    if not set1 or not set2:
        return 0.0

    intersection = set1 & set2
    union = set1 | set2
    jaccard = len(intersection) / len(union)

    return jaccard * 0.8  # Scale down token overlap


def find_similar_entities(entities: list[dict], threshold: float = 0.6) -> list[tuple[dict, dict, float]]:
    """Find pairs of similar entities above a threshold.

    Args:
        entities: List of entity dictionaries
        threshold: Minimum similarity score (0-1)

    Returns:
        List of (entity1, entity2, similarity) tuples
    """
    similar_pairs = []

    for i, e1 in enumerate(entities):
        name1 = e1.get("name", "")
        for e2 in entities[i + 1:]:
            name2 = e2.get("name", "")

            similarity = compute_name_similarity(name1, name2)

            if similarity >= threshold:
                similar_pairs.append((e1, e2, similarity))

    return similar_pairs


def cluster_similar_entities(entities: list[dict], threshold: float = 0.6) -> list[EntityCluster]:
    """Group similar entities into clusters.

    Args:
        entities: List of entity dictionaries
        threshold: Minimum similarity score to cluster together

    Returns:
        List of EntityCluster objects
    """
    if not entities:
        return []

    # Find all similar pairs
    similar_pairs = find_similar_entities(entities, threshold)

    # Build adjacency list
    adjacency: dict[str, set[str]] = defaultdict(set)
    entity_by_uuid: dict[str, dict] = {e.get("uuid", ""): e for e in entities}
    similarity_map: dict[tuple[str, str], float] = {}

    for e1, e2, sim in similar_pairs:
        uuid1 = e1.get("uuid", "")
        uuid2 = e2.get("uuid", "")
        adjacency[uuid1].add(uuid2)
        adjacency[uuid2].add(uuid1)
        similarity_map[(uuid1, uuid2)] = sim
        similarity_map[(uuid2, uuid1)] = sim

    # Find connected components (clusters)
    visited: set[str] = set()
    clusters: list[EntityCluster] = []

    for uuid in adjacency:
        if uuid in visited:
            continue

        # BFS to find all connected entities
        cluster_uuids = []
        queue = [uuid]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            cluster_uuids.append(current)

            for neighbor in adjacency[current]:
                if neighbor not in visited:
                    queue.append(neighbor)

        if len(cluster_uuids) < 2:
            continue

        # Build cluster
        cluster_entities = [entity_by_uuid[u] for u in cluster_uuids if u in entity_by_uuid]

        # Choose canonical (longest name, or most recent)
        canonical = max(cluster_entities, key=lambda e: len(e.get("name", "")))
        duplicates = [e for e in cluster_entities if e.get("uuid") != canonical.get("uuid")]

        # Calculate similarity scores
        canonical_uuid = canonical.get("uuid", "")
        scores = [
            similarity_map.get((canonical_uuid, d.get("uuid", "")), 0.0)
            for d in duplicates
        ]

        # Determine confidence based on average similarity
        avg_sim = sum(scores) / len(scores) if scores else 0
        if avg_sim >= 0.85:
            confidence = "high"
        elif avg_sim >= 0.7:
            confidence = "medium"
        else:
            confidence = "low"

        # Infer entity type from labels
        labels = canonical.get("labels", [])
        entity_type = next((l for l in labels if l != "Entity"), "Entity")

        clusters.append(EntityCluster(
            canonical=canonical,
            duplicates=duplicates,
            similarity_scores=scores,
            merge_confidence=confidence,
            entity_type=entity_type,
        ))

    return clusters


async def analyze_entity_clusters(
    group_id: str = DRIVE_RAG_GROUP_ID,
    similarity_threshold: float = 0.6,
    max_entities: int = 500,
) -> ConsolidationReport:
    """Analyze entities for potential duplicates and generate consolidation report.

    Args:
        group_id: Graphiti group ID to analyze
        similarity_threshold: Minimum similarity to consider as potential duplicate
        max_entities: Maximum entities to fetch for analysis

    Returns:
        ConsolidationReport with clusters and recommendations
    """
    client = get_graphiti_client()

    # Search for all entities (broad query)
    # We'll do multiple searches to cover different entity types
    all_entities = []

    search_queries = [
        "project research grant",
        "person researcher developer",
        "organization university nonprofit",
        "software tool platform",
        "funding NSF program",
    ]

    seen_uuids = set()

    for query in search_queries:
        try:
            result = await client.search_nodes(
                query=query,
                group_ids=[group_id],
                max_results=max_entities // len(search_queries),
            )

            # Parse the result (MCP response format)
            if isinstance(result, dict):
                content = result.get("result", {}).get("content", [])
                if content and isinstance(content[0], dict):
                    text = content[0].get("text", "{}")
                    parsed = json.loads(text)
                    nodes = parsed.get("nodes", [])

                    for node in nodes:
                        uuid = node.get("uuid", "")
                        if uuid and uuid not in seen_uuids:
                            seen_uuids.add(uuid)
                            all_entities.append(node)

        except Exception as e:
            logger.warning("search_query_failed", query=query, error=str(e))

    logger.info("fetched_entities_for_analysis", count=len(all_entities))

    # Count by type
    type_counts: dict[str, int] = defaultdict(int)
    for entity in all_entities:
        labels = entity.get("labels", ["Entity"])
        for label in labels:
            if label != "Entity":
                type_counts[label] += 1
                break
        else:
            type_counts["Entity"] += 1

    # Find clusters
    clusters = cluster_similar_entities(all_entities, similarity_threshold)

    # Generate recommendations
    recommendations = []

    high_confidence = [c for c in clusters if c.merge_confidence == "high"]
    medium_confidence = [c for c in clusters if c.merge_confidence == "medium"]

    if high_confidence:
        recommendations.append(
            f"Found {len(high_confidence)} high-confidence duplicate clusters that should be merged."
        )

    if medium_confidence:
        recommendations.append(
            f"Found {len(medium_confidence)} medium-confidence clusters that may need manual review."
        )

    # Check for common issues
    for cluster in clusters:
        if any("(" in d.get("name", "") or ")" in d.get("name", "") for d in cluster.duplicates):
            recommendations.append(
                f"Entity '{cluster.canonical.get('name')}' has variations with parenthetical notes - consider standardizing."
            )

    if not clusters:
        recommendations.append("No potential duplicates found. Entity extraction appears consistent.")

    # Count potential duplicates
    potential_duplicates = sum(len(c.duplicates) for c in clusters)

    return ConsolidationReport(
        total_entities=len(all_entities),
        unique_types=dict(type_counts),
        clusters=clusters,
        potential_duplicates=potential_duplicates,
        recommendations=recommendations,
    )


def format_consolidation_report(report: ConsolidationReport) -> dict:
    """Format consolidation report as a dictionary for API response."""
    return {
        "summary": {
            "total_entities": report.total_entities,
            "entity_types": report.unique_types,
            "potential_duplicates": report.potential_duplicates,
            "cluster_count": len(report.clusters),
        },
        "clusters": [
            {
                "canonical": {
                    "uuid": c.canonical.get("uuid"),
                    "name": c.canonical.get("name"),
                    "summary": c.canonical.get("summary", "")[:200],
                },
                "duplicates": [
                    {
                        "uuid": d.get("uuid"),
                        "name": d.get("name"),
                        "similarity": score,
                    }
                    for d, score in zip(c.duplicates, c.similarity_scores)
                ],
                "confidence": c.merge_confidence,
                "entity_type": c.entity_type,
            }
            for c in report.clusters
        ],
        "recommendations": report.recommendations,
    }
