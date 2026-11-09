"""Course Evaluation Dashboard: interactive analysis of Canvas LMS course exports."""

import re

import pandas as pd
import streamlit as st

from dashboard import charts
from dashboard import data as d
from dashboard.report import build_report

st.set_page_config(page_title="Course Evaluation Dashboard", page_icon="📊", layout="wide")

st.markdown("""
<style>
  .block-container {padding-top: 2rem; max-width: 1280px;}
  .hero {background: #1F4E79; color: white;
         padding: 1.4rem 1.8rem; border-radius: 16px; margin-bottom: 1.2rem;}
  .hero h1 {color: white; font-size: 1.75rem; margin: 0 0 .2rem 0; padding: 0;}
  .hero p {color: #DCE6F2; margin: 0; font-size: .95rem;}
  .hero .kicker {color: #9ECAE1; font-size: .78rem; font-weight: 700; letter-spacing: .08em;
                 text-transform: uppercase; margin-bottom: .35rem;}
  .pill {display: inline-block; background: rgba(255,255,255,.18); border-radius: 999px;
         padding: .15rem .7rem; margin-left: .5rem; font-size: .78rem; vertical-align: middle;}
  div[data-testid="stMetric"] {background: #F5F8FC; border: 1px solid #E3E7EC; border-radius: 14px; padding: .8rem 1rem;}
  div[data-testid="stMetricLabel"] p {font-size: .85rem; color: #5B6B7F;}
  .stTabs [role="tablist"] {gap: .5rem;}
  .stTabs [role="tab"] {padding: .45rem 1.1rem !important; border-radius: 8px 8px 0 0;}
  .stTabs [role="tab"][aria-selected="true"] {background: #1F4E79; color: white;}
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def sample_data() -> dict:
    return d.load_sample()


@st.cache_data(show_spinner=False)
def uploaded_data(pre: bytes, post: bytes, evaluations: tuple[bytes, ...], enroll: bytes) -> dict:
    surveys = [d.read_csv(b, survey=True) for b in evaluations]
    return {"pre": d.read_csv(pre), "post": d.read_csv(post), "eval": d.combine_surveys(surveys),
            "enroll": d.read_csv(enroll), "eval_mismatch": d.survey_mismatch(surveys), "eval_files": len(surveys)}


# Sidebar -----------------------------------------------------------------------
with st.sidebar:
    st.header("Data")
    source = st.radio("Source", ["Sample course (synthetic)", "Upload Canvas exports"], label_visibility="collapsed")
    raw = None
    if source.startswith("Sample"):
        raw = sample_data()
        st.caption("A fictional course generated in Canvas export format. No real learner data.")
    else:
        files = {
            "pre": st.file_uploader("Pre-test · Quiz Student Analysis report", type="csv"),
            "post": st.file_uploader("Post-test · Quiz Student Analysis report", type="csv"),
            "eval": st.file_uploader("Evaluation · Survey Student Analysis report(s)", type="csv",
                                     accept_multiple_files=True,
                                     help="If the evaluation was reposted, upload every copy. They're merged, and a "
                                          "learner who answered more than once is counted once (latest response)."),
            "enroll": st.file_uploader("Enrollments · Canvas Catalog export", type="csv"),
        }
        st.caption("Files are processed in memory for this session only and are never stored.")
        if all(files.values()):
            raw = uploaded_data(files["pre"].getvalue(), files["post"].getvalue(),
                                tuple(f.getvalue() for f in files["eval"]), files["enroll"].getvalue())
            if raw["eval_files"] > 1:
                st.caption(f"Merged {raw['eval_files']} evaluation files into {len(raw['eval'])} responses.")
            if raw["eval_mismatch"]:
                st.warning("The evaluation files don't have the same questions. Only in some files: "
                           + ", ".join(raw["eval_mismatch"]))

    if raw is not None:
        names = sorted(raw["pre"]["name"].dropna().astype(str).unique())
        exclude = st.multiselect("Exclude test or instructor accounts", names, default=d.default_exclusions(raw["pre"]))

    st.divider()
    st.markdown("Built with [**course_eval**](https://github.com/AmeliaHuang325/course_eval), "
                "a Python package for analyzing Canvas course evaluations.")

if raw is None:
    st.info("Upload the four Canvas exports in the sidebar, or switch back to the sample course.")
    st.stop()

try:
    course = d.prepare(raw, exclude)
    s = d.summary(course)
except (KeyError, ValueError) as err:
    st.error(f"These files don't look like Canvas Student Analysis / Catalog exports ({err}).")
    st.stop()

# Header and KPIs ---------------------------------------------------------------
badge = "Synthetic sample" if source.startswith("Sample") else "Uploaded data"
st.markdown(f"""<div class="hero"><div class="kicker">Canvas LMS course evaluation</div>
<h1>{course.title}<span class="pill">{badge}</span></h1>
<p>Built from Canvas LMS quiz, survey and Catalog exports · {course.date_range} ·
{course.n_questions}-question pre/post test · {len(course.likert)} evaluation statements</p></div>""",
            unsafe_allow_html=True)

k = st.columns(6)
k[0].metric("Enrolled", f"{s['enrolled']:,}", help="Learners enrolled in this course section (Canvas Catalog export).")
k[1].metric("Pre-test", s["pre"], f"{s['pre'] / max(s['enrolled'], 1):.0%}", delta_color="off",
            help="Learners who took the pre-test, as a share of enrolled.")
k[2].metric("Post-test", s["post"], f"{s['post'] / max(s['pre'], 1):.0%}", delta_color="off",
            help="Learners who took the post-test, as a share of pre-test takers.")
k[3].metric("Evaluations", s["evaluation"], f"{s['evaluation'] / max(s['post'], 1):.0%}", delta_color="off",
            help="Completed course evaluations, as a share of post-test takers.")
k[4].metric("Post-test avg", f"{s['post_avg']:.0f}%", f"{s['post_avg'] - s['pre_avg']:+.0f} pts",
            help=f"Average post-test score; pre-test average was {s['pre_avg']:.0f}%.")
if s["ksa_improved"] is not None:
    k[5].metric("Rated higher", f"{s['ksa_improved']:.0%}", f"of {s['ksa_n']}", delta_color="off",
                help="Share of learners whose self-rated knowledge/skills level was higher after the course.")

tabs = st.tabs(["Participation", "Test results", "Question deep-dive", "Self-assessment", "Feedback", "Report"])

# Participation -------------------------------------------------------------------
with tabs[0]:
    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Course funnel")
        st.plotly_chart(charts.funnel(course, s), use_container_width=True)
    with right:
        st.subheader("Where learners went")
        st.plotly_chart(charts.flow(course, s), use_container_width=True)
    st.subheader("Did pre-test scores predict who left?")
    st.caption(f"{s['left_after_pre']} learners took the pre-test but not the post-test.")
    st.plotly_chart(charts.dropout_by_pre_score(course), use_container_width=True)

# Test results ----------------------------------------------------------------------
with tabs[1]:
    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Score distribution")
        st.plotly_chart(charts.score_distribution(course), use_container_width=True)
    with right:
        st.subheader("Individual change")
        st.caption(f"{s['both']} learners took both tests. Points above the line improved.")
        st.plotly_chart(charts.score_change(course), use_container_width=True)
    st.subheader("Incorrect answers by question")
    st.caption("Hover a bar to read the question.")
    st.plotly_chart(charts.question_errors(course), use_container_width=True)

# Question deep-dive ---------------------------------------------------------------------
with tabs[2]:
    labels = {q.number: f"Q{q.number}. {q.text}" for q in course.questions}
    number = st.selectbox("Question", list(labels), format_func=labels.get)
    question = course.questions[number - 1]
    pre_rate = course.false_rates["Pre_Test"]["false_rate"].iat[number - 1]
    post_rate = course.false_rates["Post_Test"]["false_rate"].iat[number - 1]
    c1, c2, c3 = st.columns(3)
    c1.metric("Correct on pre-test", f"{1 - pre_rate:.0%}")
    c2.metric("Correct on post-test", f"{1 - post_rate:.0%}", f"{(pre_rate - post_rate) * 100:+.0f} pts")
    c3.metric("Answer options", len(question.options))
    if question.correct:
        answer = re.sub(r"^[a-d]\.\s*", "", question.correct)
        st.success(f"**Correct answer:** {answer}")
    st.plotly_chart(charts.answer_breakdown(course, number), use_container_width=True)

# Self-assessment ----------------------------------------------------------------------------
with tabs[3]:
    if course.ksa:
        left, right = st.columns(2, gap="large")
        with left:
            st.subheader("Self-rated level, before vs. after")
            st.plotly_chart(charts.ksa_levels(course), use_container_width=True)
        with right:
            st.subheader("Change per learner")
            st.plotly_chart(charts.ksa_change(course), use_container_width=True)
    if course.likert:
        st.subheader("Evaluation statements")
        st.caption("Sorted by share of agreement. Neutral answers are split around zero.")
        st.plotly_chart(charts.likert(course), use_container_width=True)

# Feedback ----------------------------------------------------------------------------------------
with tabs[4]:
    if not course.free_text:
        st.info("The evaluation has no open-ended questions.")
    else:
        code = st.selectbox("Open-ended question", list(course.free_text), format_func=course.free_text.get,
                            index=list(course.free_text).index(s["comment_col"]) if s["comment_col"] else 0)
        scored = charts.score_comments(course, code)
        score_col = "compound sentiment score"
        if len(scored):
            m1, m2, m3 = st.columns(3)
            m1.metric("Responses", len(scored))
            m2.metric("Median sentiment", f"{scored[score_col].median():+.2f}")
            m3.metric("Positive responses", f"{(scored[score_col] > 0.05).mean():.0%}")
            st.plotly_chart(charts.sentiment(scored, score_col), use_container_width=True)
            st.dataframe(
                scored.rename(columns={code: "Response", score_col: "Sentiment"}),
                hide_index=True, use_container_width=True,
                column_config={"Sentiment": st.column_config.ProgressColumn(min_value=-1, max_value=1, format="%.2f")})
            st.caption("Sentiment from NLTK's VADER model, via course_eval.process_sentiment.")
        else:
            st.info("No responses to this question.")

# Report ---------------------------------------------------------------------------------------------
with tabs[5]:
    st.subheader("Word report")
    st.write("A ready-to-edit .docx with the key findings written out, every chart from the "
             "`course_eval` library, and all open-ended comments with sentiment scores.")
    from dashboard.report import findings
    for item in findings(course, s):
        st.markdown(f"- {item}")
    if st.button("Build report", type="primary"):
        with st.spinner("Building report…"):
            st.session_state["report"] = build_report(course)
    if "report" in st.session_state:
        safe = re.sub(r"[^A-Za-z0-9]+", "_", course.title).strip("_")
        st.download_button("Download .docx", st.session_state["report"], file_name=f"{safe}_evaluation_report.docx",
                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
