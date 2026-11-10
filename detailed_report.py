"""Ten-page student report, generated from retained assessment evidence."""
from io import BytesIO
from pathlib import Path
import hashlib
import re

from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from student_report import (
    FONT, BOLD, NAVY, MUTED, PALE, INK, WIDTH, HEIGHT, LEFT, RIGHT, CONTENT,
    wrap, deductions, locations, diagnostic_lines,
)

MONO = "Courier"
mono_path = Path(__file__).with_name("fonts") / "DejaVuSansMono.ttf"
if mono_path.exists():
    pdfmetrics.registerFont(TTFont("GradeAIMono", str(mono_path)))
    MONO = "GradeAIMono"


def clean(value):
    return re.sub(r"(?:/[^\s:]+)+/submission\.c", "submission.c", str(value))


def task_family(source, title):
    lowered = (title + " " + source).lower()
    if "travelling salesman" in lowered or "traveling salesman" in lowered or re.search(r"\btsp\b", lowered):
        return "tsp"
    if "factorial" in lowered:
        return "factorial"
    if "maximum" in lowered or "largest" in lowered:
        return "maximum"
    return "general"


def proposed_tests(source, title):
    family = task_family(source, title)
    if family == "tsp":
        return [
            ("Two cities", "Matrix [[0,7],[7,0]].", "A required round trip costs 14."),
            ("Known four-city case", "[[0,10,15,20],[10,0,35,25],[15,35,0,30],[20,25,30,0]].",
             "Minimum round-trip cost 80, if the contract requires returning to the start."),
            ("Smallest accepted n", "Try n=0 and n=1 separately.", "Confirm rejection or the specified single-city result."),
            ("Invalid input", "Use a non-numeric token or a missing matrix entry.", "Reject incomplete data before using it."),
            ("Size and bitmask boundary", "Try MAX_N and MAX_N+1 after defining a safe MAX_N.",
             "Prevent invalid shifts and allocation beyond the memory budget."),
            ("Large edge costs", "Choose weights near the documented cost limit.",
             "Check addition to INF and accumulated-tour overflow."),
        ]
    if family == "factorial":
        upper = 20 if re.search(r"unsigned\s+long\s+long", source) else 12
        return [
            ("Base case", "n=0", "Expected factorial 1."),
            ("Identity", "n=1", "Expected factorial 1."),
            ("Ordinary valid case", "n=5", "Expected factorial 120."),
            ("Representation boundary", f"n={upper}", "Check the result against an independent reference."),
            ("Out-of-domain input", f"n=-1 and n={upper + 1}", "Handle according to the stated input contract."),
            ("Input failure", "A non-numeric token and empty input.", "Check scanf's return before using the input."),
        ]
    if family == "maximum":
        return [
            ("Equal values", "5,5", "For maximum-of-two, expected result 5."),
            ("Reversed arguments", "8,5 then 5,8", "For maximum-of-two, both results should be 8."),
            ("Negative values", "-5,-2", "For maximum-of-two, expected result -2."),
            ("Zero boundary", "0,-1", "For maximum-of-two, expected result 0."),
            ("Contract boundaries", "Use the smallest and largest allowed inputs.", "Stay within the selected domain."),
            ("Assignment meaning", "If this is second-largest or an array task, define duplicate and length rules.",
             "The maximum-of-two contract does not cover those tasks."),
        ]
    return [
        ("Normal case", "Use a representative input allowed by the assignment.", "Record an independently checked expected answer."),
        ("Smallest input", "Use the smallest valid size or value.", "Check the base case."),
        ("Boundary input", "Use the greatest supported size or magnitude.", "Respect arithmetic and memory limits."),
        ("Invalid input", "Use malformed or missing data.", "Reject or handle according to the specification."),
        ("Repeated or equal values", "Use duplicates where the task accepts collections.", "Confirm the assignment's duplicate policy."),
        ("Regression case", "Repeat any recorded counterexample after repair.", "The same failure should no longer occur."),
    ]


def recorded_inputs(result):
    artifacts = result.get("tool_artifacts", {})
    text = artifacts.get("klee_test_inputs", "")
    errors = " ".join(artifacts.get("klee_errors", []))
    failed_ids = set(re.findall(r"(test\d+)\.[A-Za-z]+\.err", errors))
    examples = []
    for block in re.split(r"(?=ktest file\s*:)", text):
        file_id = re.search(r"(test\d+)\.ktest", block)
        if not file_id or (failed_ids and file_id.group(1) not in failed_ids):
            continue
        names = dict(re.findall(r"object (\d+): name:\s*'([^']+)'", block))
        values = dict(re.findall(r"object (\d+): int\s*:\s*(-?\d+)", block))
        pairs = [names[k] + "=" + v for k, v in values.items()
                 if k in names and not names[k].endswith("_stat")][:4]
        if pairs:
            examples.append(file_id.group(1) + " - " + ", ".join(pairs))
        if len(examples) == 2:
            break
    return examples


def render_detailed_pdf(name, roll, title, result):
    if result.get("approval_status") != "approved":
        raise PermissionError("Faculty approval is required for PDF release.")
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(WIDTH, HEIGHT))
    pdf.setTitle("GradeAI detailed student assessment")
    pdf.setAuthor("GradeAI")
    issues = deductions(result)
    source = result.get("source", "")
    source_lines = source.splitlines()
    records = result.get("agent_details", [])
    by_key = {a["key"]: a for a in records}
    provisional = result.get("provisional_score", result["score"])
    approved = result.get("approved_score", result["score"])
    delta = approved - provisional
    family = task_family(source, title)

    def draw(x, y, value, width=CONTENT, size=9, count=3, bold=False, color=INK, mono=False):
        face = MONO if mono else BOLD if bold else FONT
        lines = wrap(clean(value), width, face, size)
        chosen = lines[:count]
        if len(lines) > count:
            end = chosen[-1]
            while end and pdfmetrics.stringWidth(end + "...", face, size) > width:
                end = end[:-1]
            chosen[-1] = end + "..."
        for i, line in enumerate(chosen):
            text = pdf.beginText(x, y - i * size * 1.35)
            text.setFont(face, size)
            text.setCharSpace(0)
            text.setFillColor(color)
            text.textOut(line)
            pdf.drawText(text)
        return y - len(chosen) * size * 1.35

    def header(page, heading, subheading=""):
        pdf.setFillColor(NAVY)
        pdf.rect(0, HEIGHT - 15, WIDTH, 15, fill=1, stroke=0)
        draw(LEFT, HEIGHT - 49, "GradeAI programming assessment", size=17, bold=True, count=1, color=NAVY)
        draw(LEFT, HEIGHT - 75, heading, size=12, bold=True, count=1)
        if subheading:
            draw(LEFT, HEIGHT - 94, subheading, size=8, count=1, color=MUTED)
        draw(LEFT, 28, f'Faculty-approved | {result.get("submission_id", "")}',
             width=CONTENT - 85, size=7, count=1, color=MUTED)
        draw(RIGHT - 75, 28, f"Page {page} of 10", width=75, size=7, count=1, color=MUTED)

    def panel(y, heading, items, height=115):
        pdf.setFillColor(PALE)
        pdf.roundRect(LEFT, y - height + 14, CONTENT, height, 6, fill=1, stroke=0)
        draw(LEFT + 10, y - 2, heading, width=CONTENT - 20, size=10, bold=True, count=1, color=NAVY)
        cursor = y - 23
        for label, value, lines in items:
            draw(LEFT + 10, cursor, label + " " + str(value),
                 width=CONTENT - 20, size=8.5, count=lines)
            cursor -= lines * 11.5 + 3

    def agent_card(y, key, number, height):
        agent = by_key.get(key)
        if not agent:
            agent = dict(name=key, status="NOT RECORDED", purpose="No stage record retained.",
                         inputs=[], steps=[], outputs=[], result="Ask faculty for the missing analysis record.",
                         evidence_ids=[])
        heading = f'{number:02d} {agent["name"]} | {agent["status"]}'
        panel(y, heading, [
            ("Purpose", agent.get("purpose", ""), 1),
            ("Input", " | ".join(agent.get("inputs", [])), 1),
            ("Analysis", " ".join(agent.get("steps", [])), 2),
            ("Output", " | ".join(agent.get("outputs", [])), 2),
            ("Result", agent.get("result", ""), 2),
            ("Evidence", ", ".join(agent.get("evidence_ids", [])) or "Operational record", 1),
        ], height)
        # Card body is intentionally bounded. Full data remain in faculty review.

    # 1. Marks and honest scope.
    header(1, "Assessment overview and rubric")
    draw(LEFT, 731, title, size=12, bold=True, count=2)
    draw(LEFT, 692, f"Student {name} | Roll {roll}", size=10, count=1)
    draw(LEFT, 673, "Approval " + str(result.get("approved_at", "Unavailable")), size=8, count=1, color=MUTED)
    draw(LEFT, 641, "Approved score", size=10, bold=True, count=1, color=NAVY)
    draw(LEFT, 606, f"{approved}/100", size=29, bold=True, count=1, color=NAVY)
    draw(LEFT + 192, 639, f"Provisional rubric total {provisional}/100", width=CONTENT - 192, count=1)
    draw(LEFT + 192, 617, f"Faculty adjustment {delta:+g} points", width=CONTENT - 192, count=1)
    draw(LEFT + 192, 595, "Unresolved checks require review" if result.get("review_required") else "Read each checked scope",
         width=CONTENT - 192, count=1, color=MUTED)
    draw(LEFT, 563, "Rubric breakdown", size=11, bold=True, count=1, color=NAVY)
    y = 539
    pdf.setFillColor(PALE)
    pdf.rect(LEFT, y - 12, CONTENT, 25, fill=1, stroke=0)
    for x, text, width in [(LEFT+5,"Criterion",155),(LEFT+163,"Awarded",55),
                           (LEFT+224,"Held / lost",62),(LEFT+293,"Decision / evidence",CONTENT-298)]:
        draw(x, y, text, width, size=8, bold=True, count=1)
    y -= 32
    issue_map = {i["criterion"]: i for i in issues}
    for row in result.get("rubric", [])[:5]:
        item = issue_map.get(row["criterion"])
        draw(LEFT+5, y, row["criterion"], 155, size=8.8, bold=True, count=2)
        draw(LEFT+163, y, f'{row["score"]}/{row["max"]}', 55, count=1)
        loss = f'{item["lost"]} ' + ("held" if item["kind"] == "Withheld" else "lost") if item else "0"
        draw(LEFT+224, y, loss, 62, count=1)
        draw(LEFT+293, y, row.get("status", "Recorded") + " [" + row.get("evidence_id", "") + "]",
             CONTENT-298, size=8.5, count=2)
        pdf.setStrokeColor(colors.HexColor("#d8e2ed"))
        pdf.line(LEFT, y-20, RIGHT, y-20)
        y -= 40
    draw(LEFT, 287, "Main improvement priorities", size=11, bold=True, count=1, color=NAVY)
    for i, item in enumerate(issues[:3]):
        draw(LEFT, 266-i*37, f'{i+1}. {item["where"]}. {item["action"]}', size=9, count=2)
    draw(LEFT, 140, "Faculty comments", size=10, bold=True, count=1)
    draw(LEFT, 122, result.get("faculty_note") or "No additional comments recorded.", size=9, count=3)
    draw(LEFT, 68, "Held points are unverified credit. Heuristic deductions require instructor judgement. This report does not add new execution results.",
         size=8, count=2, color=MUTED)
    pdf.showPage()

    # 2. Every unawarded rubric category has a source location, reason and action.
    header(2, "Where improvement is needed", "Locations refer to the original submitted source on page 9.")
    if not issues:
        panel(730, "No rubric deduction recorded", [
            ("Next step", "Review incomplete checks and run the proposed tests on page 8.", 2),
            ("Scope", "Full marks under a rubric do not establish correctness outside the checked domain.", 2),
        ], 130)
    for index, item in enumerate(issues[:5]):
        panel(730-index*122, f'{index+1}. {item["criterion"]} - {item["lost"]} points '
              + ("withheld" if item["kind"] == "Withheld" else "not awarded"),
              [("Where", item["where"], 1), ("Why", item["reason"], 3),
               ("Improve", item["action"], 3)], 113)
    draw(LEFT, 79, "Tool configuration gaps and heuristic scores are identified separately from demonstrated source defects. Ask faculty about any criterion whose evidence does not justify a deduction.",
         size=8, count=3, color=MUTED)
    pdf.showPage()

    # 3. Concrete repair examples and a reasoned revision sequence.
    header(3, "How to revise the code", "Examples are repair guidance. Adapt them to the assignment and retest.")
    main_lines = locations(source, r"\bint\s+main\s*\(\s*\)")
    first_main = f"Line {main_lines[0]}" if main_lines else "Entry point"
    panel(730, "1. Use a clear function interface", [
        ("Where", first_main, 1),
        ("Before", "int main() {" if main_lines else "No empty-parameter main prototype was identified.", 1),
        ("Suggested form", "int main(void) {", 1),
        ("Why", "A prototype declares the parameter list explicitly and resolves the strict-prototype warning when it is present.", 2),
    ], 130)
    scan_lines = locations(source, r"\bscanf\s*\(")
    match = re.search(r'scanf\s*\(\s*"%d"\s*,\s*&\s*([A-Za-z_]\w*)', source)
    variable = match.group(1) if match else "value"
    panel(583, "2. Preserve or add input validation", [
        ("Where", "Input-reading lines " + (", ".join(map(str, scan_lines[:6])) or "as required by your program"), 1),
        ("Example", f'if (scanf("%d", &{variable}) != 1) return 1;', 1),
        ("Then", "Check the accepted range before using a value in indexing, allocation, arithmetic or shifts.", 2),
        ("Check", "If these guards already exist, retain them. Their presence is not a defect and should not be removed to reduce branch counts.", 2),
    ], 140)
    if family == "tsp":
        bounds = "Before computing 1 << n or indexing a DP table, validate n against both the integer bit width and a documented memory budget."
        algorithm = "A standard Held-Karp TSP recurrence commonly requires O(n^2 * 2^n) time and O(n * 2^n) space. Confirm the recurrence used by your code before claiming these bounds."
        action = "Explain the purpose of each state and transition. Check memoization, unreachable-state handling and addition to INF. Loop counts alone do not justify an inefficiency claim."
    elif family == "factorial":
        limit = 20 if re.search(r"unsigned\s+long\s+long", source) else 12
        bounds = f"Define a factorial domain that fits the accumulator. The common limit for this representation is {limit}; check the actual target type and assignment contract."
        algorithm = "Trace n=0 and n=1 to verify initialization. Compare a normal result and the largest accepted input with an independent reference."
        action = "Keep the input guard and the base-case result. Use a named helper if it makes the calculation easier to test."
    else:
        bounds = "Validate collection sizes, array indices and arithmetic ranges before performing the corresponding operation."
        algorithm = "Explain why each loop, branch and function is required by the algorithm. Separate required work from repeated work."
        action = "Use a small example to trace the algorithm. Change only the part supported by the diagnostic or failing test."
    panel(425, "3. Review bounds and arithmetic", [
        ("Where", "Range checks, array allocation, shifts and accumulators", 1),
        ("Review prompt", bounds, 3),
        ("Status", "This is a review task unless a recorded verifier finding identifies a violation.", 2),
    ], 128)
    panel(279, "4. Explain the algorithm and retest", [
        ("Reasoning", algorithm, 3), ("Action", action, 3),
        ("After repair", "Compile again, rerun the same contract, compare proposed tests and ask faculty to reassess the affected criterion.", 2),
    ], 150)
    pdf.showPage()

    # 4-7. Four pages contain all 14 agents with inputs/actions/outputs/results.
    groups = [
        (4, "Planning compilation and LLVM analysis", ["coordinator","scheduler","compilation","llvm"], 1),
        (5, "Execution verification and safety analysis", ["symbolic","smt","verification","security"], 5),
        (6, "Code review knowledge and retrieval", ["semantic","knowledge","graphrag"], 9),
        (7, "Evaluation feedback and learning history", ["evaluation","feedback","analytics"], 12),
    ]
    for page, heading, keys, number in groups:
        header(page, heading, "These are recorded outcomes. A completed stage can still have a limited or inconclusive verification scope.")
        height = 148 if len(keys) == 4 else 193
        interval = 155 if len(keys) == 4 else 204
        for i, key in enumerate(keys):
            agent_card(730-i*interval, key, number+i, height)
        if page == 7:
            draw(LEFT, 83, "Scores come from the rubric and faculty approval. History counts describe earlier attempts; they do not establish learning gains.",
                 size=8, count=3, color=MUTED)
        pdf.showPage()

    # 8. Differentiate proposed test plans from actually executed symbolic checks.
    header(8, "Tests to run after revision", "Suggested tests below have not been executed by this report generator.")
    draw(LEFT, 731, "Profile " + str(result.get("assignment_profile", "Legacy assessment")), bold=True, count=1)
    draw(LEFT, 711, result.get("assessment_mode", "See recorded stage scopes."), size=8.5, count=4)
    y = 641
    for index, (label, value, expected) in enumerate(proposed_tests(source, title)[:5], 1):
        panel(y, f"{index}. {label}", [
            ("Input", value, 2), ("Check", expected, 2),
        ], 80)
        y -= 82
    symbolic = by_key.get("symbolic", {})
    log = "\n".join(symbolic.get("raw_evidence", []))
    counts = re.findall(r"KLEE: done: (?:completed paths|partially completed paths|generated tests)\s*=\s*\d+", log)
    draw(LEFT, 214, "Recorded execution coverage", bold=True, count=1, size=10)
    draw(LEFT, 195, " | ".join(counts) or "No path-count summary was retained. Inspect the symbolic-execution record.",
         size=8.5, count=2)
    draw(LEFT, 161, "Recorded symbolic inputs", size=10, bold=True, count=1)
    examples = recorded_inputs(result)
    draw(LEFT, 142, " | ".join(examples) or "No compact numeric input example was retained. Inspect the linked tool evidence.",
         size=8.5, count=3)
    draw(LEFT, 81, "Input objects may include passing paths. Match a generated test to its error artifact before calling it a counterexample. Printed-output correctness remains unchecked in open-main mode.",
         size=8, count=3, color=MUTED)
    pdf.showPage()

    # 9. Source with original line numbers and diagnostic/heuristic review markers.
    header(9, "Submitted source and review map", "Review markers identify diagnostic or heuristic review locations, not necessarily defects.")
    flagged = set()
    for agent in result.get("agents", []):
        flagged.update(diagnostic_lines(agent.get("evidence", "")))
    if any(i["criterion"] == "Complexity Agent" for i in issues):
        flagged.update(locations(source, r"\b(for|while|do|if|switch|case)\b"))
    if main_lines:
        flagged.update(main_lines)
    indexed = list(enumerate(source_lines, 1))
    if len(indexed) > 108:
        selected = set(range(1, 37)) | set(range(max(1, len(indexed)-17),len(indexed)+1))
        for line in sorted(flagged):
            selected.update(range(max(1,line-1),min(len(indexed),line+1)+1))
        indexed = [(n, value) for n, value in indexed if n in selected][:108]
    if not indexed:
        draw(LEFT, 730, "The source was not retained in this legacy record. Ask faculty for the original submission.", count=3)
    else:
        half = 54
        two_columns = len(indexed) > half
        col_width = (CONTENT-20)/2 if two_columns else CONTENT
        for pos, (number, value) in enumerate(indexed):
            col, row = divmod(pos, half)
            prefix = ">" if number in flagged else " "
            draw(LEFT+col*(col_width+20),730-row*10.4,
                 f"{prefix}{number:4d} {value.expandtabs(4)}",
                 col_width, size=7 if two_columns else 8.5, count=1, mono=True,
                 color=NAVY if number in flagged else INK)
    draw(LEFT, 143, f"Source lines {len(source_lines)}. Displayed {len(indexed)}. Long code lines may be shortened. Full source and diagnostics remain in faculty review.",
         size=8, count=3, color=MUTED)
    draw(LEFT, 94, "Read a marked line together with the explanation on page 2. A loop marker is a request to justify the algorithm, not an instruction to remove required work.",
         size=8.5, count=3)
    pdf.showPage()

    # 10. Evidence, learning resources, interpretation corrections and next actions.
    header(10, "Evidence learning resources and next steps")
    y = 731
    evidence = result.get("evidence_log", [])
    for e in evidence[:16]:
        draw(LEFT, y, e["id"], 115, size=8, bold=True, count=1)
        draw(LEFT+119, y, e["agent"] + ". " + e["fact"], CONTENT-119, size=8, count=2)
        y -= 30
    resource_y = min(y-12, 305)
    draw(LEFT, resource_y, "Course resources linked to this attempt", size=10, bold=True, count=1, color=NAVY)
    resource_y -= 21
    notes = result.get("retrieved_notes", [])
    if notes:
        for note in notes[:2]:
            draw(LEFT, resource_y, note["title"] + " - " + note["text"], size=8.3, count=3)
            draw(LEFT, resource_y-35, note["source"], size=7.5, count=1, color=MUTED)
            resource_y -= 56
    else:
        draw(LEFT, resource_y, "No source-cited course resources were retained for this attempt.", size=8.5, count=2)
    corrections = result.get("report_corrections", [])
    if corrections:
        draw(LEFT, 112, "Interpretation corrections " + " ".join(corrections), size=7.8, count=4, color=MUTED)
    else:
        draw(LEFT, 112, "Next steps: repair the supported findings, document necessary algorithmic work, run the proposed tests and submit a new attempt for fresh analysis.",
             size=8.5, count=3)
    draw(LEFT, 58, "Source SHA-256 " + hashlib.sha256(source.encode("utf-8")).hexdigest(), size=6.7, count=1, color=MUTED)
    pdf.save()
    return buffer.getvalue()
