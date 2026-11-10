import os, re, subprocess, tempfile
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from xml.sax.saxutils import escape


def run(command, timeout=8):
    try:
        p = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False,
                           env=os.environ.copy())
        return p.returncode, (p.stdout + '\n' + p.stderr)[:6000]
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return -1, str(e)


def agent(name, maximum, score, analysis, improvement, evidence=''):
    return {'name': name, 'max': maximum, 'score': max(0, min(maximum, score)),
            'analysis': analysis, 'improvement': improvement, 'evidence': evidence}


def _evaluate_static(source, title):
    # Source is NEVER executed. Only syntax-checking and static analysis are permitted.
    agents = []
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, 'submission.c')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(source)
        rc, compiler = run(['gcc', '-fsyntax-only', '-Wall', '-Wextra', '-Wpedantic', path])
        warnings = len(re.findall(r'warning:', compiler))
        compiled = rc == 0
        agents.append(agent('Compilation Agent', 35, max(0, 35 - warnings * 3) if compiled else 0,
            'GCC syntax check passed.' if compiled else 'GCC found compilation errors.',
            'Resolve compiler warnings.' if compiled else 'Fix the reported syntax/type errors before resubmitting.', compiler))
        agents.append(agent('Testing Agent', 15, 0,
            'Not evaluated: running untrusted student code requires an isolated execution service and assignment-specific tests.',
            'Instructor must configure hidden test cases; this score remains unawarded until tests run.'))
        function_count = len(re.findall(r'\b(?:int|void|float|double|char|long|short)\s+\**\s*[A-Za-z_]\w*\s*\([^;{}]*\)\s*\{', source))
        comments = bool(re.search(r'//|/\*', source))
        design = min(15, 5 + min(function_count, 3)*2 + (4 if comments else 0))
        agents.append(agent('Design Quality Agent', 15, design,
            f'Static heuristics identified {function_count} function definition(s); comments present: {comments}.',
            'Use meaningful names, smaller functions, and explanatory comments. Human review is required.'))
        loops = len(re.findall(r'\b(for|while|do)\b', source))
        branches = len(re.findall(r'\b(if|switch|case)\b', source))
        complexity = max(0, 20 - max(0, loops-2)*2 - max(0, branches-4))
        agents.append(agent('Complexity Agent', 20, complexity,
            f'Heuristic counts: {loops} loop keyword(s), {branches} branch keyword(s). Not a proof of time complexity.',
            'Review nested loops and conditional branches; document expected time/space complexity.'))
        rc2, cppcheck = run(['cppcheck', '--enable=warning,style,performance,portability', '--template=gcc', '--quiet', path])
        findings = len(re.findall(r':(?:\d+:)?\d+: (?:warning|style|performance|error):', cppcheck))
        optimization = max(0, 15 - findings*2) if rc2 == 0 else 0
        agents.append(agent('Optimization Agent', 15, optimization,
            f'Cppcheck reported approximately {findings} issue(s). Static findings may include false positives.' if rc2 == 0 else 'Cppcheck did not complete successfully. Manual review required; optimization points are withheld.',
            'Review flagged issues and measure performance with realistic inputs.', cppcheck))
        unsafe = [x for x in ['gets(', 'strcpy(', 'strcat(', 'sprintf(', 'system('] if x in source]
        agents.append(agent('Security Agent (diagnostic)', 0, 0,
            'Potentially unsafe API patterns: ' + (', '.join(unsafe) if unsafe else 'none found by simple pattern scan.'),
            'Prefer bounded APIs and validate input. A clean scan does not establish security.'))
    return {'score': sum(a['score'] for a in agents), 'agents': agents,
            'status': 'provisional; correctness tests not executed'}



def evaluate(source, title, profile="main"):
    from time import perf_counter
    from reports import normalize_result
    from verification import execute, stage, PROFILES
    from knowledge import enrich
    start = perf_counter()
    result = _evaluate_static(source, title)
    result["source"] = source
    result["assignment_profile"] = profile
    tool_records, artifacts = execute(source, profile)
    # Correctness credit requires an explicit function contract and both completed verifiers.
    checked = profile != "main" and all(
        tool_records[k]["status"] == "COMPLETED" for k in ("symbolic", "verification"))
    testing = result["agents"][1]
    testing["score"] = 15 if checked else 0
    testing["criterion_status"] = "Satisfied within scope" if checked else "Review required"
    testing["analysis"] = (
        "Function contract checked by completed KLEE and CBMC runs in the selected bounded domain."
        if checked else "No functional correctness credit established. Inspect the selected profile and tool outcomes.")
    testing["improvement"] = "Review counterexamples and verification scope. Open-main mode checks safety, not expected output."
    result["score"] = sum(a["score"] for a in result["agents"])
    result["provisional_score"] = result["score"]
    result = normalize_result(result, source, title)
    by_key = {d["key"]: d for d in result["agent_details"]}
    for key, record in tool_records.items():
        by_key[key].update(record)
    evidence = result["evidence_log"]
    for key, record in tool_records.items():
        evidence.append({"id": "TOOL-" + key.upper(), "agent": by_key[key]["name"],
                         "authority": "actual tool output within the selected harness scope",
                         "fact": record["status"] + ": " + record["result"],
                         "raw": "\n".join(record.get("raw_evidence", []))})
    local, graph, notes = enrich(source, title, list(by_key.values()), evidence)
    for record in local:
        by_key[record["key"]].update(record)
    artifacts.update(knowledge_graph=graph, retrieved_notes=notes)
    result["tool_artifacts"] = artifacts
    result["retrieved_notes"] = notes
    for key in ("knowledge", "graphrag"):
        evidence.append({"id": "TOOL-" + key.upper(), "agent": by_key[key]["name"],
                         "authority": "local graph construction and retrieval",
                         "fact": by_key[key]["result"], "raw": "\n".join(by_key[key]["raw_evidence"])})
    by_key["coordinator"].update(
        steps=["Run static checks.", "Invoke the selected LLVM/KLEE, Z3 and CBMC adapters.",
               "Build evidence graph, retrieve course notes and preserve per-stage outcomes."],
        outputs=[f"Assignment profile: {PROFILES[profile]}", f"Evidence records: {len(evidence)}"],
        result="Coordinated actual tool adapters. Inspect each stage for completed, blocked or inconclusive outcomes.")
    by_key["scheduler"].update(
        steps=["Use a fixed sequential schedule to limit Mac memory use.",
               "Apply 8-second static checks, a 90-second Docker deadline, 60-second CBMC deadline, and bounded Z3 queries."],
        outputs=["Stage failures do not become passing checks."],
        result="Fixed resource schedule applied. No RL scheduler is configured.")
    by_key["evaluation"].update(
        steps=["Aggregate static rubric points and explicit contract-check points.",
               "Require faculty review of incomplete checks and diagnostic findings."],
        outputs=[f'Provisional total: {result["score"]}/100', "Profile: " + PROFILES[profile]],
        result="Bounded functional verification can contribute 15 points for a completed function-contract profile.")
    by_key["evaluation"]["evidence_ids"] = [e["id"] for e in evidence]
    by_key["feedback"]["evidence_ids"] = [e["id"] for e in evidence]
    by_key["feedback"].update(
        inputs=["Tool evidence, rubric records and retrieved notes."],
        steps=["Collect recorded tool findings and template improvement suggestions.",
               "Attach graph-retrieved course resources; no LLM is called."],
        outputs=[f"{d['name']}: {d['result']}" for d in by_key.values()
                 if d["key"] in ("symbolic", "smt", "verification")] +
                [n["source"] + ": " + n["text"] for n in notes],
        result="Rule-based feedback assembled from actual evidence and cited course notes.")
    result["analysis_elapsed_ms"] = round((perf_counter() - start) * 1000, 2)
    result["assessment_mode"] = (
        "GCC/Cp pcheck static analysis; Docker Clang/LLVM and KLEE; native Z3 query replay and CBMC; "
        "local knowledge graph and graph-guided lexical retrieval. Profile: " + PROFILES[profile]).replace("Cp pcheck", "Cppcheck")
    if artifacts.get("input_model") == "integer_tokens":
        result["assessment_mode"] += (
            ". Single %d scanf calls use a signed-integer token model with success, matching failure and EOF; "
            "printf output is abstracted. Text parsing and expected output are not verified")
    result["report_schema_version"] = 4
    result["review_required"] = any(
        d["status"] in ("UNAVAILABLE", "BLOCKED", "VIOLATED", "INCONCLUSIVE", "REVIEW REQUIRED", "FAILED / REVIEW")
        for d in by_key.values())
    return result


from reports import pdf_report
