"""A single report model shared by faculty review and approved PDF export."""
from copy import deepcopy

PIPELINE = [
    ("coordinator", "Coordinator Agent", "Plan assessment and link retained evidence."),
    ("scheduler", "Scheduler Agent", "Apply the local fixed execution order and process timeouts."),
    ("compilation", "Compilation Agent", "Check C syntax and compiler diagnostics."),
    ("llvm", "LLVM IR / Structure Agent", "Generate LLVM IR and structural analysis."),
    ("symbolic", "Symbolic Execution Agent", "Explore symbolic inputs with KLEE."),
    ("smt", "SMT Solver Agent", "Decide encoded properties with Z3."),
    ("verification", "Formal Verification Agent", "Check specified properties using CBMC."),
    ("security", "Security Analysis Agent", "Inspect static diagnostics and API patterns."),
    ("semantic", "Semantic Analysis Agent", "Review documented design, complexity and optimization heuristics."),
    ("knowledge", "Knowledge Graph Agent", "Link findings to course concepts in a knowledge graph."),
    ("graphrag", "GraphRAG Agent", "Retrieve source-cited course material."),
    ("evaluation", "Evaluation Agent", "Aggregate provisional rubric points for faculty moderation."),
    ("feedback", "Feedback Agent", "Collect rule-based improvement suggestions."),
    ("analytics", "Learning Analytics Agent", "Compute longitudinal learning measures."),
]


def review_retained_evidence(result):
    """Correct an interpretation using stored diagnostics without rerunning tools or altering marks."""
    corrections = list(result.get("report_corrections", []))
    records = result.get("agent_details", [])
    symbolic = next((a for a in records if a["key"] == "symbolic"), None)
    if symbolic:
        from verification import classify_klee
        log = "\n".join(symbolic.get("raw_evidence", []))
        status, message = classify_klee(log, [], False)
        if "Unmodelled external calls" in message and symbolic["status"] == "COMPLETED":
            symbolic.update(status=status, result=message)
            result["review_required"] = True
            corrections.append("KLEE's previous completed label was corrected to INCONCLUSIVE from retained external-call warnings. No tools were rerun.")
            for e in result.get("evidence_log", []):
                if e["id"] == "TOOL-SYMBOLIC":
                    e["fact"] = status + ": " + message
            for a in records:
                if a["key"] == "feedback":
                    a["outputs"] = [
                        "Symbolic Execution Agent: " + message
                        if v.startswith("Symbolic Execution Agent:") else v
                        for v in a.get("outputs", [])]
    source = result.get("source", "")
    if "unsigned long long" in source and "factorial" in source:
        if any(n.get("id") == "integer-range" for n in result.get("retrieved_notes", [])):
            corrections.append("The source uses unsigned long long. For a 64-bit accumulator, 20! fits; the retrieved signed-int limit of 12! does not apply to this accumulator.")
    for a in records:
        if a["key"] == "coordinator":
            a["outputs"] = [v for v in a["outputs"] if not v.startswith("Evidence records:")]
            a["outputs"].append(f'Evidence records: {len(result.get("evidence_log", []))}')
    if corrections:
        result["report_corrections"] = list(dict.fromkeys(corrections))
    return result


def normalize_result(raw, source="", title=""):
    result = deepcopy(raw)
    if raw.get("report_schema_version", 0) >= 3 and raw.get("agent_details"):
        return review_retained_evidence(result)
    source = source or result.get("source", "")
    result["source"] = source
    result.setdefault("provisional_score", raw.get("score", 0))
    legacy = raw.get("agents", [])
    evidence = []
    rubric = []
    for index, agent in enumerate(legacy, 1):
        eid = f"E{index:02d}"
        evidence.append({
            "id": eid, "agent": agent.get("name", "Unknown agent"),
            "authority": "compiler / static tool / heuristic; inspect the producing stage",
            "fact": agent.get("analysis", "No assessment recorded"),
            "raw": agent.get("evidence", ""),
        })
        if agent.get("max", 0):
            rubric.append({
                "criterion": agent["name"], "score": agent.get("score", 0),
                "max": agent["max"], "analysis": agent.get("analysis", ""),
                "improvement": agent.get("improvement", ""), "evidence_id": eid,
                 "status": agent.get("criterion_status", "Not evaluated" if agent["name"] == "Testing Agent"
                else "Provisional"),
            })
    result["rubric"] = rubric
    result["evidence_log"] = evidence
    if result.get("report_schema_version") == 2 and result.get("agent_details"):
        return result

    def matching(fragment):
        return [(i, a) for i, a in enumerate(legacy, 1)
                if fragment in a.get("name", "")]

    details = []
    for key, name, purpose in PIPELINE:
        detail = dict(
            key=key, name=name, purpose=purpose, status="NOT RUN",
            inputs=["Source, assignment title and the current static assessment record."],
            steps=[], outputs=[], result="", evidence_ids=[], improvements=[],
        )
        if key == "coordinator":
            detail.update(status="COMPLETED",
                inputs=[f"Assignment title: {title or 'Recorded assignment'}",
                        f"Source lines: {len(source.splitlines())}",
                        "Rubric: compilation 35, testing 15, design 15, complexity 20, optimization 15."],
                steps=["Run GCC syntax checking.", "Run Cppcheck and static scoring heuristics.",
                       "Preserve findings for faculty review. Tool-dependent verification is unavailable."],
                outputs=[f"{len(legacy)} assessment records", f"{len(evidence)} evidence records"],
                result="Static assessment assembled. The additional pipeline stages below have explicit execution status.")
        elif key == "scheduler":
            detail.update(status="COMPLETED",
                inputs=["Fixed local prototype configuration."],
                steps=["Execute assessment synchronously.", "Apply an 8-second timeout to each external tool."],
                outputs=["Sequential execution; no learned or adaptive scheduling."],
                result="Fixed schedule applied.",
                improvements=["Use isolated workers and durable job scheduling for a full deployment."])
        elif key in ("compilation", "security", "semantic"):
            fragments = {"compilation": ["Compilation"], "security": ["Security"],
                         "semantic": ["Design", "Complexity", "Optimization"]}[key]
            found = [pair for fragment in fragments for pair in matching(fragment)]
            detail.update(status="COMPLETED" if found else "NOT RUN")
            for i, agent in found:
                detail["steps"].append(agent.get("analysis", ""))
                detail["outputs"].append(f'{agent["name"]}: {agent.get("score", 0)}/{agent.get("max", 0)} points.')
                detail["improvements"].append(agent.get("improvement", ""))
                detail["evidence_ids"].append(f"E{i:02d}")
                if agent.get("evidence"):
                    detail.setdefault("raw_evidence", []).append(agent["evidence"])
            if key == "compilation":
                detail["steps"].insert(0, "Command: gcc -fsyntax-only -Wall -Wextra -Wpedantic submission.c")
                detail["result"] = "Syntax analysis only. Functional behaviour was not tested."
                if any("found compilation errors" in a.get("analysis", "") for _, a in found):
                    detail["status"] = "FAILED / REVIEW"
            elif key == "security":
                detail["steps"].insert(0, "Search for gets, strcpy, strcat, sprintf and system API text patterns.")
                detail["result"] = "Diagnostic pattern scan only; Cppcheck evidence is recorded under semantic review."
            else:
                detail["result"] = "Heuristic observations only. No LLM was called and no time-complexity proof was produced."
                if any("did not complete" in a.get("analysis", "") for _, a in found):
                    detail["status"] = "INCONCLUSIVE / REVIEW"
        elif key == "evaluation":
            detail.update(status="COMPLETED",
                inputs=["The six existing agent records and the current 100-point rubric."],
                steps=["Sum provisional rubric points.", "Keep testing at 0/15 because no tests were executed.",
                       "Require faculty moderation and approval before marks or PDF release."],
                outputs=[f'Provisional total: {result["provisional_score"]}/100'],
                result="Provisional assessment prepared. Missing tests are unawarded; this is not a correctness percentage.",
                evidence_ids=[e["id"] for e in evidence])
        elif key == "feedback":
            detail.update(status="COMPLETED",
                inputs=["Recorded static findings and improvement strings."],
                steps=["Collect rule-based suggestions from the existing agents."],
                outputs=[a.get("improvement", "") for a in legacy if a.get("improvement")],
                result="Template feedback generated. No external or local LLM was called.")
        else:
            reasons = {
                "llvm": "LLVM tool integration is not configured; no IR, CFG or data-flow analysis was generated.",
                "symbolic": "KLEE integration and symbolic harness are not configured.",
                "smt": "Z3 integration and property encoding are not configured.",
                "verification": "CBMC integration and property harness are not configured.",
                "knowledge": "No knowledge graph store or concept mapping is configured.",
                "graphrag": "No course corpus, retrieval index or graph retrieval is configured.",
                "analytics": "Submission history is retained in SQLite; longitudinal analytics are not implemented.",
            }
            detail["steps"] = ["Stage availability checked from the implemented application pipeline."]
            detail["outputs"] = ["No execution artifacts."]
            detail["result"] = reasons[key]
        details.append(detail)
    result["agent_details"] = details
    result["report_schema_version"] = 2
    return result



def pdf_report(name, roll, title, result):
    if result.get("approval_status") != "approved":
        raise PermissionError("An approved report is required for PDF export.")
    from student_report import render_student_pdf
    return render_student_pdf(name, roll, title,
                              normalize_result(result, result.get("source", ""), title))
