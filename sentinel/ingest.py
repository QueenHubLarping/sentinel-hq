"""
Sentinel corpus ingestion — reads corpus/ and builds the decision knowledge
graph in LOCAL self-hosted Cognee (Ollama-backed; nothing leaves the laptop).

This is the `remember` phase, done as two steps:
  cognee.add()      — stage each document into the dataset
  cognee.cognify()  — extract entities and build the graph across all documents

Each ADR / PR / Slack file is added separately and tagged with its source type so
cognify can extract *cross-document* relationships — the multi-hop chain Sentinel
relies on (PR --reverses--> EngineeringDecision --justified_by--> ArchitecturalReason).

corpus/
  adrs/   — Architecture Decision Records   (source_type: ADR)
  slack/  — static "Slack" exports          (source_type: Slack)
  prs/    — PR metadata                      (source_type: PR)
"""

import os
import re
from pathlib import Path
from uuid import UUID, uuid5

import cognee
from cognee.tasks.ingestion.data_item import DataItem

CORPUS_DIR = Path(__file__).parent.parent / "corpus"
DATASET_NAME = "sentinel_decisions"

# Fixed namespace so data_ids are stable across runs — lets resolve.py do
# selective forget by data_id without querying the DB each time.
_SENTINEL_NS = UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7")


def corpus_file_data_id(filename: str) -> UUID:
    """Return the stable data_id for a corpus file given its basename."""
    return uuid5(_SENTINEL_NS, filename)


def adr_dir() -> Path:
    """Resolve the directory Sentinel reads ADRs from.

    ADRs are the one source that lives in the *consuming* repository, so the team
    edits them where they work — not inside Sentinel. Resolution order:

      1. SENTINEL_ADR_DIR        — explicit override (set in a workflow if ADRs
                                   live somewhere other than docs/adr).
      2. $GITHUB_WORKSPACE/docs/adr — the checked-out repo when running inside a
                                   GitHub Action (e.g. sentinel-test-repo).
      3. corpus/adrs             — the bundled demo corpus (local dev / tests).

    data_ids derive from the file *basename* (see corpus_file_data_id), so a given
    ADR keeps a stable id regardless of which directory it was read from — selective
    forget in resolve.py keeps working across this switch.
    """
    explicit = os.environ.get("SENTINEL_ADR_DIR")
    if explicit and Path(explicit).is_dir():
        return Path(explicit)

    workspace = os.environ.get("GITHUB_WORKSPACE")
    if workspace:
        repo_adrs = Path(workspace) / "docs" / "adr"
        if repo_adrs.is_dir():
            return repo_adrs

    return CORPUS_DIR / "adrs"


def _iter_corpus_files():
    """Yield (path, source_type) for every document Sentinel ingests.

    ADRs come from the consuming repo (see adr_dir); Slack threads and historical PR
    metadata still come from the bundled corpus until live connectors exist for them.
    """
    for path in sorted(adr_dir().glob("*.md")):
        yield path, "ADR"
    for subdir, source_type in (("slack", "Slack"), ("prs", "PR")):
        for path in sorted((CORPUS_DIR / subdir).glob("*.md")):
            yield path, source_type


# ---------------------------------------------------------------------------
# Metadata extraction helpers (Task 1 + Task 3)
# ---------------------------------------------------------------------------

def _parse_cross_refs(content: str, meta: dict) -> None:
    """
    Parse the '## Cross-References' section of a corpus file into meta (in-place).

    Keys already present in meta (e.g. from frontmatter) are skipped — cross-refs
    never overwrite or duplicate authoritative frontmatter values.  The one
    exception: repeated occurrences of the *same* key within the cross-refs block
    itself (e.g. two 'related_to' lines) are merged with ', '.
    """
    m = re.search(r'## Cross-References\s*\n(.*?)(?=\n## |\Z)', content, re.DOTALL)
    if not m:
        return
    # Track which keys we set from this cross-refs block (distinct from pre-existing keys)
    seen_in_section: set = set()
    for line in m.group(1).splitlines():
        line = line.strip().lstrip("- ").strip()
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if not k or not v:
            continue
        if k not in meta:
            # New key — set it and note that it came from this block
            meta[k] = v
            seen_in_section.add(k)
        elif k in seen_in_section:
            # Repeated key within this same cross-refs block — merge (e.g. two related_to lines)
            meta[k] = meta[k] + ", " + v
        # else: key was already in meta before this call (e.g. from frontmatter) — skip


def _extract_metadata(path: Path, source_type: str) -> dict:
    """
    Extract structured metadata from a corpus file.

    Reads the file at *path* and parses frontmatter-style bold headers
    (**Field:** value) plus the optional '## Cross-References' section.

    Fault-tolerant: never raises — if any step fails the returned dict
    contains whatever was successfully collected up to that point, and the
    caller falls back to the bare tag header.
    """
    meta: dict = {}
    try:
        content = path.read_text(encoding="utf-8")

        if source_type == "ADR":
            # --- Frontmatter-style bold fields (**Label:** value) ---
            for label, key in [
                ("Status", "status"),
                ("Date", "date"),
                ("Author", "author"),
                ("Component", "component"),
            ]:
                m = re.search(rf'\*\*{label}:\*\*\s*(.+)', content)
                if m:
                    meta[key] = m.group(1).strip()

            # Strip leading '@' from author handle
            if "author" in meta:
                meta["author"] = meta["author"].lstrip("@")

            # Decision summary: pull the descriptive title from the H1 heading
            # (most reliable single-line source; strip "ADR-NNN: " prefix)
            m = re.search(r'^# ADR-\d+[:\s]+(.+)', content, re.MULTILINE)
            if m:
                meta["decision"] = m.group(1).strip()[:80]

            # Task 3 — decision_status: active unless Status explicitly says Superseded
            status_val = meta.get("status", "")
            meta["decision_status"] = (
                "superseded" if "superseded" in status_val.lower() else "active"
            )

            # Cross-references (implements:, discussed_in:, …) added by Task 2
            _parse_cross_refs(content, meta)

        elif source_type == "PR":
            # PR number from filename (e.g. "PR-42-implement-async-email.md" → "42")
            m = re.match(r'PR-(\d+)', path.name)
            if m:
                meta["pr_number"] = m.group(1)

            # Frontmatter fields
            for label, key in [
                ("Author", "author"),
                ("Date", "date"),
                ("Status", "status"),
                ("Component", "component"),
            ]:
                m = re.search(rf'\*\*{label}:\*\*\s*(.+)', content)
                if m:
                    meta[key] = m.group(1).strip()
            if "author" in meta:
                meta["author"] = meta["author"].lstrip("@")

            # Cross-references first — they contain clean filenames for 'implements'
            # (e.g. "ADR-001-async-email.md") which are better for graph linking than
            # the free-text "## Implements" body section.
            _parse_cross_refs(content, meta)

            # Fall back to body extraction for 'implements' if cross-refs didn't supply it
            if "implements" not in meta:
                m = re.search(r'## Implements\s*\n+(.+)', content)
                if m:
                    meta["implements"] = m.group(1).strip()
                else:
                    m = re.search(r'\bImplements\s+(ADR-\d+)', content, re.IGNORECASE)
                    if m:
                        meta["implements"] = m.group(1)

        elif source_type == "Slack":
            for label, key in [("Channel", "channel"), ("Date", "date")]:
                m = re.search(rf'\*\*{label}:\*\*\s*(.+)', content)
                if m:
                    meta[key] = m.group(1).strip()

            # Unique @handles in bold, deduplicated in encounter order
            raw = re.findall(r'\*\*(@[\w-]+)\*\*', content)
            seen: list = list(dict.fromkeys(raw))
            if seen:
                meta["participants"] = ", ".join(seen)

            _parse_cross_refs(content, meta)

    except Exception:
        pass  # fault-tolerant: return whatever was collected so far
    return meta


def _build_header(path: Path, source_type: str, meta: dict) -> str:
    """
    Build the enriched multi-line tag header prepended to each corpus document.

    Groups tags logically onto up to three lines:
      Line 1 — identity + status/date + decision_status (ADR only)
      Line 2 — component, author, decision summary / pr_number / participants
      Line 3 — cross-document links (implements, discussed_in, related_to)

    Falls back gracefully when meta fields are absent.
    """
    name = path.name

    def _tag(k: str) -> str:
        v = meta.get(k, "")
        return f"[{k}: {v}]" if v else ""

    if source_type == "ADR":
        line1_parts = [
            f"[source_type: {source_type}]",
            f"[file: {name}]",
        ] + [t for t in (_tag("status"), _tag("date"), _tag("decision_status")) if t]

        line2_parts = [
            t for t in (_tag("component"), _tag("author"), _tag("decision")) if t
        ]

        line3_parts = [
            t for t in (_tag("implements"), _tag("discussed_in"), _tag("related_to")) if t
        ]

        lines = [" ".join(line1_parts)]
        if line2_parts:
            lines.append(" ".join(line2_parts))
        if line3_parts:
            lines.append(" ".join(line3_parts))
        return "\n".join(lines)

    elif source_type == "PR":
        line1_parts = [f"[source_type: {source_type}]", f"[file: {name}]"]
        if meta.get("pr_number"):
            line1_parts.append(f"[pr_number: {meta['pr_number']}]")
        line1_parts += [t for t in (_tag("status"), _tag("date")) if t]

        line2_parts = [
            t for t in (
                _tag("component"), _tag("author"),
                _tag("implements"), _tag("discussed_in"),
            ) if t
        ]

        lines = [" ".join(line1_parts)]
        if line2_parts:
            lines.append(" ".join(line2_parts))
        return "\n".join(lines)

    elif source_type == "Slack":
        line1_parts = [f"[source_type: {source_type}]", f"[file: {name}]"]
        line1_parts += [t for t in (_tag("channel"), _tag("date")) if t]

        line2_parts = [
            t for t in (
                _tag("participants"), _tag("related_to"), _tag("component"),
            ) if t
        ]

        lines = [" ".join(line1_parts)]
        if line2_parts:
            lines.append(" ".join(line2_parts))
        return "\n".join(lines)

    # Unknown source type — bare fallback
    return f"[source_type: {source_type}] [file: {name}]"


# ---------------------------------------------------------------------------
# Main ingestion pipeline
# ---------------------------------------------------------------------------

async def ingest_corpus() -> None:
    files = list(_iter_corpus_files())
    print(f"-> Staging {len(files)} corpus file(s) into local Cognee...")

    staged = 0
    for path, source_type in files:
        content = path.read_text(encoding="utf-8")
        # Build enriched metadata header; fall back to bare tag on any error.
        try:
            meta = _extract_metadata(path, source_type)
            # A superseded ADR is a *retired* decision — no longer institutional
            # memory — so we leave it out of the graph entirely. This is how
            # '/sentinel intentional' takes durable effect on ephemeral CI runners:
            # the resolve step sets the ADR's status to Superseded in docs/adr, and
            # the next ingest simply doesn't add it, so detection stops flagging PRs
            # that contradict it. (No graph persistence required.)
            if source_type == "ADR" and meta.get("decision_status") == "superseded":
                print(f"   - skipping {path.name} (ADR superseded — retired from memory)")
                continue
            header = _build_header(path, source_type, meta)
        except Exception:
            header = f"[source_type: {source_type}] [file: {path.name}]"
        tagged = f"{header}\n\n{content}"
        # DataItem gives each file a stable, addressable data_id (for selective forget)
        # and a human-readable label (the filename) visible in datasets.list_data().
        item = DataItem(
            data=tagged,
            label=path.name,
            data_id=corpus_file_data_id(path.name),
        )
        await cognee.add(item, dataset_name=DATASET_NAME)
        staged += 1
        print(f"   + {path.name} ({source_type})")

    print(f"-> cognify() — extracting entities + building graph from {staged} doc(s)...")
    await cognee.cognify(datasets=[DATASET_NAME])
    print(f"OK: graph built from {staged} documents in dataset '{DATASET_NAME}'.")


if __name__ == "__main__":
    import asyncio

    from sentinel.connection import setup_cognee

    async def _run():
        await setup_cognee()
        await ingest_corpus()

    asyncio.run(_run())
