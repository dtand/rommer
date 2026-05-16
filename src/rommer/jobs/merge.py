"""Merge strategies for parallel agent runs."""

import json
import sqlite3
from collections import Counter

from rommer.config import Project


def merge_discoveries(project: Project, job_ids: list[str], strategy: str = "union") -> dict:
    """Merge discoveries from multiple parallel job runs.

    Strategies:
    - union: Keep all unique discoveries (dedupe by address)
    - consensus: Only keep discoveries found by 2+ agents
    - hybrid: Union for confirmed, consensus for probable/scratch

    Returns summary dict.
    """
    conn = project.get_db()

    # Collect all staged candidates from the parallel runs
    # Each job's worker writes to a staging table (job_discovery) instead of discovery
    all_candidates = []
    for job_id in job_ids:
        rows = conn.execute(
            "SELECT * FROM job_discovery WHERE job_id = ?", (job_id,)
        ).fetchall()
        for r in rows:
            all_candidates.append({
                "job_id": r["job_id"],
                "label": r["label"],
                "address": r["address"],
                "data_type": r["data_type"],
                "confidence": r["confidence"],
                "notes": r["notes"],
                "metadata": r["metadata"],
            })

    if strategy == "union":
        merged = _merge_union(all_candidates)
    elif strategy == "consensus":
        merged = _merge_consensus(all_candidates, threshold=2)
    elif strategy == "hybrid":
        merged = _merge_hybrid(all_candidates)
    else:
        merged = _merge_union(all_candidates)

    # Insert merged discoveries into the main discovery table
    project_id = conn.execute("SELECT id FROM project LIMIT 1").fetchone()
    project_id = project_id[0] if project_id else 0

    inserted = 0
    for d in merged:
        existing = conn.execute(
            "SELECT id FROM discovery WHERE address = ?", (d["address"],)
        ).fetchone()
        if existing:
            continue

        conn.execute(
            """INSERT INTO discovery
               (project_id, label, address, data_type, tier, confidence,
                source, discovery_method, notes, metadata)
               VALUES (?, ?, ?, ?, ?, ?, 'knowledge_analysis', 'agent', ?, ?)""",
            (project_id, d["label"], d["address"], d["data_type"],
             "golden" if d["confidence"] == "confirmed" else "scratch",
             d["confidence"], d.get("notes", ""),
             d["metadata"] if d.get("metadata") else None),  # already JSON string from staging
        )
        inserted += 1

    conn.commit()

    # Clean up staging table
    for job_id in job_ids:
        conn.execute("DELETE FROM job_discovery WHERE job_id = ?", (job_id,))
    conn.commit()
    conn.close()

    return {
        "total_candidates": len(all_candidates),
        "unique_addresses": len(set(c["address"] for c in all_candidates)),
        "merged": len(merged),
        "inserted": inserted,
        "strategy": strategy,
    }


def _merge_union(candidates: list[dict]) -> list[dict]:
    """Keep all unique discoveries, prefer highest confidence on conflicts."""
    by_address: dict[str, dict] = {}
    confidence_rank = {"confirmed": 3, "probable": 2, "speculative": 1}

    for c in candidates:
        addr = c["address"]
        if addr not in by_address:
            by_address[addr] = c
        else:
            # Keep the one with higher confidence, or richer metadata
            existing = by_address[addr]
            existing_rank = confidence_rank.get(existing.get("confidence", ""), 0)
            new_rank = confidence_rank.get(c.get("confidence", ""), 0)
            if new_rank > existing_rank:
                by_address[addr] = c
            elif new_rank == existing_rank and c.get("metadata") and not existing.get("metadata"):
                by_address[addr] = c

    return list(by_address.values())


def _merge_consensus(candidates: list[dict], threshold: int = 2) -> list[dict]:
    """Only keep discoveries found by multiple agents."""
    # Count how many distinct jobs found each address
    addr_jobs: dict[str, set[str]] = {}
    addr_best: dict[str, dict] = {}

    for c in candidates:
        addr = c["address"]
        job_id = c.get("job_id", "")
        addr_jobs.setdefault(addr, set()).add(job_id)
        if addr not in addr_best or (c.get("metadata") and not addr_best[addr].get("metadata")):
            addr_best[addr] = c

    return [
        addr_best[addr]
        for addr, jobs in addr_jobs.items()
        if len(jobs) >= threshold
    ]


def _merge_hybrid(candidates: list[dict]) -> list[dict]:
    """Union for confirmed, consensus for everything else."""
    confirmed = [c for c in candidates if c.get("confidence") == "confirmed"]
    rest = [c for c in candidates if c.get("confidence") != "confirmed"]

    merged_confirmed = _merge_union(confirmed)
    merged_rest = _merge_consensus(rest, threshold=2)

    # Combine, deduplicating by address
    by_address = {c["address"]: c for c in merged_rest}
    for c in merged_confirmed:
        by_address[c["address"]] = c  # confirmed takes priority

    return list(by_address.values())
