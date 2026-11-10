"""Local evidence graph and graph-guided retrieval with explicit course citations."""
from collections import Counter
import json
from pathlib import Path
import re

from verification import stage


def enrich(source, title, details, evidence):
    concepts = {"verification_limits"}
    if any(t in source for t in ("scanf", "gets", "fgets")):
        concepts.add("input_validation")
    if "factorial" in source or any(d["status"] == "VIOLATED" for d in details):
        concepts.add("unsigned_integer_range" if re.search(r"unsigned\s+long\s+long", source) else "integer_range")
    if any("Function contract" in x for d in details for x in d.get("inputs", [])):
        concepts.add("functional_contract")
    nodes = [{"id": "submission", "type": "submission", "label": title}]
    triples = []
    for record in evidence:
        nodes.append({"id": record["id"], "type": "evidence", "label": record["agent"]})
        triples.append(["submission", "has_evidence", record["id"]])
    for concept in sorted(concepts):
        nodes.append({"id": concept, "type": "course_concept", "label": concept})
        triples.append(["submission", "requires_review_of", concept])
    graph = {"nodes": nodes, "triples": triples}
    kg = stage("knowledge", "COMPLETED", "Built a local typed evidence graph for this submission.",
               ["Create submission and evidence nodes.", "Attach relevant course-concept nodes and typed edges."],
               [f"Graph nodes: {len(nodes)}", f"Typed relations: {len(triples)}"],
               ["\n".join(" | ".join(edge) for edge in triples)])
    kg["inputs"] = ["Actual compiler and verifier records.", "Submitted source and assignment title."]
    notes_path = Path(__file__).with_name("course_notes.json")
    notes = json.loads(notes_path.read_text())
    query = Counter(re.findall(r"[a-z]+", (title + " " + " ".join(concepts)).lower()))
    retrieved = []
    for note in notes:
        if note["concept"] not in concepts:
            continue
        tokens = Counter(re.findall(r"[a-z]+", (note["title"] + " " + note["text"]).lower()))
        score = sum(min(v, tokens[k]) for k, v in query.items())
        retrieved.append({**note, "retrieval_score": score + 1})
    retrieved.sort(key=lambda n: (-n["retrieval_score"], n["id"]))
    rag = stage("graphrag", "COMPLETED", "Retrieved graph-linked course notes with lexical ranking.",
                ["Traverse submission-to-concept edges.", "Select matching bundled notes and rank token overlap.",
                 "Return text with stable note IDs and source citations."],
                [n["id"] + ": " + n["title"] for n in retrieved],
                [n["source"] + "\n" + n["text"] for n in retrieved])
    rag["inputs"] = ["Local evidence graph.", "Bundled course_notes.json resource index."]
    return [kg, rag], graph, retrieved
