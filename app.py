import hmac
import json
import os

import streamlit as st

from engine import evaluate, pdf_report
from reports import normalize_result
from verification import PROFILES, tool_health
from student_report import deductions
from storage import (
    initialize, submit, get_submission, pending_submissions, approve, approved_payload,
)

DB = os.environ.get("AGENTGRADE_DB", "agentgrade.db")
FACULTY_PASSWORD = os.environ.get("FACULTY_PASSWORD", "")
initialize(DB)

st.set_page_config(page_title="GradeAI assessment and faculty review", layout="wide")
st.title("GradeAI | C assignment assessment")
st.caption("Detailed agent evidence and faculty-approved PDF reports")


def show_analysis(result, source, title):
    result = normalize_result(result, source, title)
    st.info(result.get("assessment_mode", "Legacy static assessment. Missing integrations in older records remain not run."))
    for correction in result.get("report_corrections", []):
        st.warning(correction)
    if result.get("review_required"):
        st.warning("Inspect incomplete, unavailable or violated checks before approving marks.")
    st.subheader("Rubric breakdown")
    st.table([{
        "Criterion": r["criterion"], "Status": r["status"],
        "Evidence": r["evidence_id"], "Points": f'{r["score"]}/{r["max"]}',
    } for r in result["rubric"]])
    st.subheader("Student improvement and deduction summary")
    issues = deductions(result)
    if issues:
        st.table([{
            "Criterion": item["criterion"], "Points held/lost": item["lost"],
            "Treatment": item["kind"], "Program portion": item["where"],
            "Why": item["reason"], "How to improve": item["action"],
            "Evidence": item["evidence"],
        } for item in issues])
    else:
        st.write("No rubric deductions were recorded.")
    st.subheader("How each agent analysed the code")
    for number, agent in enumerate(result["agent_details"], 1):
        with st.container(border=True):
            st.markdown(f'#### {number:02d} {agent["name"]}')
            st.write("Execution status:", agent["status"])
            st.write(agent["purpose"])
            for label, key in [("Input received", "inputs"), ("What it did", "steps"),
                               ("Output produced", "outputs"),
                               ("Improvement suggestions", "improvements")]:
                if agent.get(key):
                    st.markdown(f"**{label}**")
                    for index, value in enumerate(agent[key], 1):
                        st.write(f"{index}. {value}")
            st.write("Result:", agent["result"])
            st.write("Evidence IDs:", ", ".join(agent["evidence_ids"]) or "None")
            for raw in agent.get("raw_evidence", []):
                st.code(raw, language="text")
    st.subheader("Evidence log")
    for evidence in result["evidence_log"]:
        st.markdown(f'**{evidence["id"]} - {evidence["agent"]}**')
        st.write(evidence["fact"])
        if evidence["raw"]:
            st.code(evidence["raw"], language="text")
    st.subheader("Submitted source code")
    st.code(source, language="c", line_numbers=True)


student, results, faculty = st.tabs(
    ["Submit assignment", "Check approved result", "Faculty review"])

with student:
    with st.form("submission"):
        name = st.text_input("Student name")
        roll = st.text_input("Roll number")
        title = st.text_input("Assignment title")
        profile = st.selectbox("Trusted assignment profile", list(PROFILES),
                               format_func=lambda key: PROFILES[key])
        st.caption("Function profiles require the exact function signature shown. For a main-only program select Open C safety. "
                   "Safety mode does not compare output to the assignment's expected answer.")
        uploaded = st.file_uploader("Upload C program (.c)", type=["c"])
        send = st.form_submit_button("Submit for evaluation")
    if send:
        if not all([name.strip(), roll.strip(), title.strip(), uploaded]):
            st.error("Complete every field and attach a C file.")
        elif uploaded.size > 100_000:
            st.error("Maximum upload size is 100 KB.")
        else:
            source = uploaded.getvalue().decode("utf-8", errors="replace")
            with st.spinner("Running the tool pipeline; the sequential checks can take several minutes"):
                result = evaluate(source, title, profile)
            sid = submit(DB, name.strip(), roll.strip(), title.strip(), source, result)
            st.success("Submitted. Marks and PDF will be available after faculty approval.")
            st.write("Save your private submission ID:")
            st.code(sid)

with results:
    with st.form("lookup"):
        sid = st.text_input("Private submission ID")
        check = st.form_submit_button("Check result")
    if check:
        row = get_submission(DB, sid.strip())
        if not row:
            st.session_state.pop("approved_lookup", None)
            st.error("Submission not found.")
        elif row["status"] != "approved":
            st.session_state.pop("approved_lookup", None)
            st.info("Awaiting faculty approval. Marks and PDF are not available.")
        else:
            st.session_state["approved_lookup"] = sid.strip()
    if st.session_state.get("approved_lookup"):
        # Recheck database authorization on every rerun, including download actions.
        try:
            row, result = approved_payload(DB, st.session_state["approved_lookup"])
        except PermissionError:
            st.session_state.pop("approved_lookup", None)
            st.info("An approved result is required.")
        else:
            st.metric("Faculty-approved marks", f'{row["approved_score"]}/100')
            st.write("Faculty comments:", row["faculty_note"] or "No additional comments.")
            st.write("Approval recorded:", result["approved_at"])
            st.download_button(
                "Download approved 10-page PDF",
                data=pdf_report(row["name"], row["roll"], row["title"], result),
                file_name=f'GradeAI_approved_{row["id"]}.pdf',
                mime="application/pdf",
            )
            show_analysis(result, row["source"], row["title"])

with faculty:
    if not FACULTY_PASSWORD:
        st.warning("Set FACULTY_PASSWORD before using faculty review.")
    else:
        password = st.text_input("Faculty password", type="password")
        if password and hmac.compare_digest(password, FACULTY_PASSWORD):
            with st.expander("Tool availability on the application host"):
                if st.button("Check installed tools"):
                    st.json(tool_health())
                st.caption("Use run-mac.command for real KLEE/LLVM, Z3 and CBMC. An older Docker-only app may not have access to these tools.")
            pending = pending_submissions(DB)
            st.write(f"Pending submissions: {len(pending)}")
            if pending:
                by_id = {row["id"]: row for row in pending}
                selected = st.selectbox(
                    "Select a submission", list(by_id),
                    format_func=lambda sid: (
                        f'{by_id[sid]["name"]} | {by_id[sid]["roll"]} | {by_id[sid]["title"]} | {sid[:8]}'))
                row = by_id[selected]
                result = normalize_result(json.loads(row["result_json"]), row["source"], row["title"])
                st.write("Student:", row["name"], "| Roll:", row["roll"])
                st.write("Assignment:", row["title"])
                st.write("Submitted:", row["submitted_at"])
                st.metric("Static provisional marks", f'{result["provisional_score"]}/100')
                st.warning("Review the selected contract, checked domain, all tool outcomes and provisional marks before approval.")
                show_analysis(result, row["source"], row["title"])
                with st.form(f"approval_{selected}"):
                    score = st.number_input(
                        "Final approved score", min_value=0, max_value=100,
                        value=max(0, min(100, int(result["provisional_score"]))))
                    note = st.text_area("Faculty comments / moderation rationale")
                    decision = st.form_submit_button("Approve and publish marks and PDF")
                if decision and int(score) != int(result["provisional_score"]) and not note.strip():
                    st.error("Explain the faculty score adjustment in the comments before approving.")
                elif decision:
                    if approve(DB, selected, int(score), note):
                        st.session_state["approval_notice"] = "Approved. Marks and PDF are now available through the submission ID."
                    else:
                        st.session_state["approval_notice"] = "This submission was already reviewed. Refresh the pending list."
                    st.rerun()
            if st.session_state.get("approval_notice"):
                st.success(st.session_state.pop("approval_notice"))
        elif password:
            st.error("Invalid faculty password.")
