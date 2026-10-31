"""
AI Resume & Job Match Analyzer - web version (Streamlit).

Run it on your own computer:   streamlit run web_app.py
All the thinking happens in analyzer.py, the same file the desktop app uses.
"""

import io
import os
import tempfile

import streamlit as st

import analyzer as a

# Put your repository address here. The sidebar link is hidden until you do.
GITHUB_URL = "https://github.com/YOUR-USERNAME/YOUR-REPO-NAME"

st.set_page_config(page_title="AI Resume & Job Match Analyzer",
                   page_icon=":page_facing_up:", layout="wide")


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def read_upload(uploaded_file):
    """Save the upload to a temporary file, read it with analyzer.read_file,
    and always delete the temporary file again."""
    suffix = os.path.splitext(uploaded_file.name)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
        temp.write(uploaded_file.getvalue())
        temp_path = temp.name
    try:
        text = a.read_file(temp_path)
    finally:
        os.remove(temp_path)
    if not text.strip():
        raise a.FileReadError("No readable text was found in this file.")
    return text


def forget(key):
    if key in st.session_state:
        del st.session_state[key]


def sync_upload(uploaded, text_key):
    """When a NEW file is uploaded, read it and put its text in the text box.
    Must run before the text box with the same key is drawn."""
    marker_key, error_key = text_key + "_file", text_key + "_error"
    if uploaded is None:
        forget(marker_key)
        forget(error_key)
        return

    marker = f"{uploaded.name}:{uploaded.size}"
    if st.session_state.get(marker_key) != marker:       # a new file
        st.session_state[marker_key] = marker
        forget(error_key)
        try:
            st.session_state[text_key] = read_upload(uploaded)
        except a.FileReadError as error:
            st.session_state[error_key] = str(error)
        except Exception as error:
            st.session_state[error_key] = f"Could not read this file: {error}"

    if st.session_state.get(error_key):
        st.error(st.session_state[error_key])


def load_sample():
    st.session_state["resume_text"] = a.SAMPLE_RESUME
    st.session_state["job_text"] = a.SAMPLE_JOB


def clear_all():
    st.session_state["resume_text"] = ""
    st.session_state["job_text"] = ""
    forget("result")


def chips(skills, color, preferred):
    """Coloured skill names, e.g. :green[Python] :green[SQL]"""
    parts = []
    for skill in skills:
        label = skill + (" (nice-to-have)" if skill in preferred else "")
        parts.append(f":{color}[{label}]")
    return "  ".join(parts)


def make_pdf(sections):
    buffer = io.BytesIO()
    a.write_pdf_report(sections, buffer)
    return buffer.getvalue()


def make_docx(sections):
    buffer = io.BytesIO()
    a.write_docx_report(sections, buffer)
    return buffer.getvalue()


# ------------------------------------------------------------
# Showing a result
# ------------------------------------------------------------
def show_results(result):
    preferred = result["preferred_skills"]
    final = result["final_score"]

    st.divider()
    st.header("Results")

    c1, c2, c3 = st.columns(3)
    c1.metric("Overall match", f"{final:.1f}%")
    c2.metric(f"Skill match (counts {a.SKILL_WEIGHT:.0%})",
              f"{result['skill_score']:.1f}%")
    c3.metric(f"Text similarity (counts {a.TEXT_WEIGHT:.0%})",
              f"{result['text_score']:.1f}%")
    st.progress(max(0.0, min(final / 100, 1.0)))

    status = f"**{result['status_text']}**"
    if final >= 80:
        st.success(status)
    elif final >= 60:
        st.warning(status)
    else:
        st.error(status)
    st.info("Why this score: " + result["explanation"])

    left, right = st.columns(2)
    with left:
        st.subheader("Matched skills")
        st.markdown(chips(result["matched_skills"], "green", preferred) or "None")
    with right:
        st.subheader("Missing skills")
        st.markdown(chips(result["missing_skills"], "red", preferred) or "None")

    if a.HAS_MATPLOTLIB and result["categories"]:
        st.subheader("Skills by category")
        st.pyplot(a.build_category_figure(result["categories"], final))

    st.subheader("Learning plan (most important first)")
    if not result["missing_skills"]:
        st.success("You have all the recognized skills from the job description.")
    else:
        for line in result["learning_plan"]:
            st.markdown(line)
        if result["learning_hours"]:
            st.caption(f"Rough total: about {result['learning_hours']} hours. "
                       "Time estimates are rough guesses.")
        with st.expander("Learning links"):
            for skill in result["missing_skills"]:
                links = a.get_learning_links(skill)
                if links:
                    rows = "\n".join(f"- [{label}]({url})" for label, url in links)
                    st.markdown(f"**{skill}**\n{rows}")
                else:
                    st.markdown(f"**{skill}**: no course needed, show it in your resume.")

    st.subheader("Resume tips")
    if result["resume_tips"]:
        for tip in result["resume_tips"]:
            st.markdown(f"- {tip}")
    else:
        st.success("No major issues found. Your resume structure looks solid.")

    st.subheader("Download the report")
    sections = a.build_report_sections(result)
    d1, d2, d3 = st.columns(3)
    if a.HAS_REPORTLAB:
        d1.download_button("PDF report", data=make_pdf(sections),
                           file_name="Resume_Analysis_Report.pdf",
                           mime="application/pdf")
    else:
        d1.caption("PDF export needs the reportlab package.")
    d2.download_button(
        "Word report", data=make_docx(sections),
        file_name="Resume_Analysis_Report.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    d3.download_button("Text report", data=a.build_report(result).encode("utf-8"),
                       file_name="Resume_Analysis_Report.txt", mime="text/plain")


# ------------------------------------------------------------
# The page
# ------------------------------------------------------------
with st.sidebar:
    st.header("How it works")
    st.markdown(
        "- Finds skills from a list of 124 skills and their aliases\n"
        "- Required skills count double, \"nice to have\" skills count once\n"
        f"- Overall score = {a.SKILL_WEIGHT:.0%} skill match + "
        f"{a.TEXT_WEIGHT:.0%} text similarity\n"
        "- 80% and above is Excellent, 60% and above is Good")
    if "YOUR-USERNAME" not in GITHUB_URL:
        st.markdown(f"[Source code on GitHub]({GITHUB_URL})")
    st.caption("Scanned PDFs (OCR): "
               + ("available" if a.ocr_available() else "not available here"))

st.title("AI Resume & Job Match Analyzer")
st.write("Compare your resume with a job description. See your match score, "
         "the skills you are missing, and what to learn next.")
st.info("Privacy: your files are read in memory on the server and are not saved "
        "by this app. The app runs on a shared online server, so do not upload "
        "anything you would not want processed there. The desktop version keeps "
        "everything on your own computer.")

col_resume, col_job = st.columns(2)
with col_resume:
    st.subheader("Your resume")
    resume_file = st.file_uploader("Upload a PDF, Word or text file",
                                   type=["pdf", "docx", "txt"], key="resume_upload")
    sync_upload(resume_file, "resume_text")
    st.text_area("Resume text", key="resume_text", height=320,
                 placeholder="Paste your resume here, or upload a file above.")
with col_job:
    st.subheader("Job description")
    job_file = st.file_uploader("Upload a PDF, Word or text file",
                                type=["pdf", "docx", "txt"], key="job_upload")
    sync_upload(job_file, "job_text")
    st.text_area("Job description text", key="job_text", height=320,
                 placeholder="Paste the job description here, or upload a file above.")

b1, b2, b3 = st.columns([1, 1, 1])
analyze_clicked = b1.button("Analyze resume", type="primary")
b2.button("Load sample", on_click=load_sample)
b3.button("Clear all", on_click=clear_all)

if analyze_clicked:
    resume = st.session_state.get("resume_text", "").strip()
    job = st.session_state.get("job_text", "").strip()
    if not resume:
        st.warning("Please add your resume first.")
    elif not job:
        st.warning("Please add the job description.")
    else:
        result = a.run_analysis(resume, job)
        if not result["required_skills"]:
            forget("result")
            st.warning("No recognized skills were found in the job description. "
                       "Check that it lists skills such as Python, SQL or Excel.")
        else:
            st.session_state["result"] = result

if "result" in st.session_state:
    show_results(st.session_state["result"])
