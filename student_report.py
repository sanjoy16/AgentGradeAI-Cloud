"""Three-page student report with bounded layout and evidence-linked deductions."""
from io import BytesIO
from pathlib import Path
import hashlib
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT = "Helvetica"
BOLD = "Helvetica-Bold"
font_dir = Path(__file__).with_name("fonts")
if (font_dir / "DejaVuSans.ttf").exists():
    pdfmetrics.registerFont(TTFont("GradeAISans", str(font_dir / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("GradeAISansBold", str(font_dir / "DejaVuSans-Bold.ttf")))
    FONT, BOLD = "GradeAISans", "GradeAISansBold"

NAVY = colors.HexColor("#183a59")
MUTED = colors.HexColor("#52667b")
PALE = colors.HexColor("#eef3f8")
INK = colors.HexColor("#172d42")
WIDTH, HEIGHT = A4
LEFT, RIGHT = 42, WIDTH - 42
CONTENT = RIGHT - LEFT


def locations(source, pattern):
    return [i for i, line in enumerate(source.splitlines(), 1) if re.search(pattern, line)]


def code_location(source, numbers, fallback="Whole program"):
    numbers = sorted(set(n for n in numbers if 1 <= n <= len(source.splitlines())))
    if not numbers:
        return fallback
    label = "Line " + str(numbers[0])
    if len(numbers) > 1:
        label = "Lines " + ", ".join(map(str, numbers[:4]))
        if len(numbers) > 4:
            label += " and others"
    snippet = source.splitlines()[numbers[0] - 1].strip()
    return label + " - " + snippet


def diagnostic_lines(raw):
    return [int(n) for n in re.findall(r"submission\.c:(\d+)(?::\d+)?:", raw)]


def deductions(result):
    """Explain recorded points using the existing scoring rules, without altering marks."""
    source = result.get("source", "")
    entries = []
    agents = {a["name"]: a for a in result.get("agents", [])}
    for criterion in result.get("rubric", []):
        lost = max(0, criterion["max"] - criterion["score"])
        if not lost:
            continue
        name = criterion["criterion"]
        agent = agents.get(name, {})
        analysis = criterion.get("analysis", "")
        raw = agent.get("evidence", "")
        where = code_location(source, diagnostic_lines(raw))
        action = criterion.get("improvement") or "Ask the faculty reviewer to explain this criterion."
        reason = analysis or "A deduction reason was not recorded. Request faculty clarification."
        kind = "Not awarded"

        if name == "Compilation Agent":
            issues = [line.strip() for line in raw.splitlines()
                      if re.search(r"\b(?:warning|error|fatal error):", line)]
            if issues:
                reason = " ".join(issues[:2])
                if criterion["score"] > 0:
                    reason = f"{lost} points lost under the compiler-warning rule. " + reason
            if "prototype" in raw and locations(source, r"\bint\s+main\s*\(\s*\)"):
                where = code_location(source, locations(source, r"\bint\s+main\s*\(\s*\)"))
                action = "Declare the entry point as int main(void), then rebuild and resolve any remaining warnings."
            elif "No such file or directory: 'gcc'" in raw:
                kind = "Withheld"
                where = "Assessment configuration"
                reason = "The compiler was unavailable. This is not evidence of a source-code defect."
                action = "Restore the compiler and rerun this attempt before deciding compilation marks."
        elif name == "Testing Agent":
            profile = result.get("assignment_profile", "main")
            kind = "Withheld"
            where = "Assignment contract / whole program"
            records = [a for a in result.get("agent_details", [])
                       if a["key"] in ("symbolic", "verification")]
            failed = [a for a in records if a["status"] == "VIOLATED"]
            failure_log = "\n".join(v for a in failed for v in a.get("raw_evidence", []))
            failure_lines = diagnostic_lines(failure_log)
            failure_lines += [int(n) for n in re.findall(
                r"File:\s*[^\n]*submission\.c\s+Line:\s*(\d+)", failure_log)]
            if failure_lines:
                where = code_location(source, failure_lines)
            if profile == "main":
                reason = "No output-correctness contract was checked. Open-main safety checks do not establish the expected answer."
                action = "Ask faculty to supply expected-output tests or a matching function contract. These points are unverified, not a proven wrong answer."
                if failed:
                    kind = "Not awarded"
                    reason = "No correctness contract was checked. A verifier also reported a safety violation; inspect the cited program portion."
                    action = "Repair the recorded safety finding, then have faculty configure a correctness contract or output tests."
            else:
                records = [a for a in result.get("agent_details", [])
                           if a["key"] in ("symbolic", "verification")]
                reason = ". ".join(a["name"] + " " + a["status"] for a in records) or analysis
                actual_failure = any(a["status"] == "VIOLATED" for a in records)
                if actual_failure:
                    kind = "Not awarded"
                    action = "Use the recorded counterexample to reproduce the failed property, repair the relevant function and resubmit."
                else:
                    action = "Resolve the incomplete tool or harness checks and rerun. Missing verification alone does not establish incorrect code."
        elif name == "Design Quality Agent":
            functions = len(re.findall(
                r"\b(?:int|void|float|double|char|long|short)\s+\**\s*[A-Za-z_]\w*\s*\([^;{}]*\)\s*\{", source))
            comments = bool(re.search(r"//|/\*", source))
            expected = min(15, 5 + min(functions, 3) * 2 + (4 if comments else 0))
            where = code_location(source, locations(source, r"\bmain\s*\("), "Function organization and documentation")
            if criterion["score"] == expected:
                documentation_loss = 0 if comments else 4
                organization_loss = 6 - min(functions, 3) * 2
                reason = (f"Current heuristic: {documentation_loss} points for missing comments and "
                          f"{organization_loss} points from the function-count bonus. "
                          "This is a rubric heuristic, not a correctness finding.")
            action = "Explain the input limits and algorithm. Extract a helper only if it improves clarity. Ask faculty to moderate the heuristic for a short, clear solution."
        elif name == "Complexity Agent":
            where = code_location(source, locations(source, r"\b(for|while|do|if|switch|case)\b"),
                                  "Loop and branch structure")
            loops = len(re.findall(r"\b(for|while|do)\b", source))
            branches = len(re.findall(r"\b(if|switch|case)\b", source))
            rule_loss = max(0, loops - 2) * 2 + max(0, branches - 4)
            if criterion["score"] == max(0, 20 - rule_loss):
                reason = f"The keyword-count rule found {loops} loop and {branches} branch keywords. It withheld {lost} points; it does not prove inefficiency."
            action = "Review the identified loops and branches for unnecessary work and explain the expected complexity. Retain necessary validation checks."
        elif name == "Optimization Agent":
            if "did not complete" in analysis:
                kind = "Withheld"
                where = "Static-analysis configuration"
                reason = "Cppcheck did not complete. Optimization points are unverified rather than evidence of slow code."
                action = "Resolve the tool failure, rerun Cppcheck and have faculty assess this criterion."
            else:
                where = code_location(source, diagnostic_lines(raw), "Cppcheck findings / whole program")
                issues = [line.strip() for line in raw.splitlines()
                          if re.search(r"\b(warning|performance|style|error):", line)]
                reason = " ".join(issues[:2]) or analysis
                action = "Inspect the cited Cppcheck findings, verify they apply to the code, and repair or explain each finding."
        entries.append({
            "criterion": name, "score": criterion["score"], "max": criterion["max"],
            "lost": lost, "kind": kind, "where": where, "reason": reason,
            "action": action, "evidence": criterion.get("evidence_id", ""),
        })
    return entries


def wrap(value, width, font, size):
    words = str(value).replace("\n", " ").split()
    lines, current = [], ""
    for word in words:
        if current and pdfmetrics.stringWidth(current + " " + word, font, size) > width:
            lines.append(current)
            current = ""
        while pdfmetrics.stringWidth(word, font, size) > width:
            cut = len(word) - 1
            while cut > 1 and pdfmetrics.stringWidth(word[:cut], font, size) > width:
                cut -= 1
            if current:
                lines.append(current)
                current = ""
            lines.append(word[:cut])
            word = word[cut:]
        current = (current + " " + word).strip()
    if current:
        lines.append(current)
    return lines or [""]



def render_student_pdf(name, roll, title, result):
    from review_report import render_review_pdf
    return render_review_pdf(name, roll, title, result)
