import io
import re

import pandas as pd
import plotly.graph_objects as go
from docx import Document

from dashboard import charts
from dashboard import data as d
from dashboard.report import build_report


def course():
    raw = d.load_sample()
    return d.prepare(raw, d.default_exclusions(raw["pre"]))


def test_sample_data_is_detected_like_a_canvas_export():
    c = course()
    assert c.excluded == ["Test Student"]
    assert c.n_questions == 9 and len(c.questions) == 9
    assert all(q.correct for q in c.questions)
    assert c.ksa == ("EVAL_01", "EVAL_02")
    assert len(c.likert) == 12 and list(c.free_text) == ["EVAL_15", "EVAL_16", "EVAL_17", "EVAL_18"]
    assert c.enroll["Listing Name"].nunique() == 1          # other Catalog listings filtered out


def test_summary_is_consistent():
    s = d.summary(course())
    assert s["enrolled"] >= s["pre"] >= s["post"] >= s["evaluation"] > 0
    assert s["post_avg"] > s["pre_avg"]
    assert 0 <= s["ksa_improved"] <= 1 and -1 <= s["sentiment_median"] <= 1


def test_every_chart_builds():
    c = course()
    s = d.summary(c)
    figures = [charts.funnel(c, s), charts.flow(c, s), charts.dropout_by_pre_score(c), charts.score_distribution(c),
               charts.score_change(c), charts.question_errors(c), charts.answer_breakdown(c, 1), charts.ksa_levels(c),
               charts.ksa_change(c), charts.likert(c),
               charts.sentiment(charts.score_comments(c, "EVAL_17"), "compound sentiment score")]
    assert all(isinstance(f, go.Figure) for f in figures)


def test_word_report():
    doc = Document(io.BytesIO(build_report(course())))
    headings = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
    assert {"Key findings", "Test results", "Learner feedback"} <= set(headings)
    assert len(doc.inline_shapes) >= 6


def test_reposted_evaluation_is_merged():
    raw = d.load_sample()
    full = raw["eval"]
    # Simulate a repost: the second copy gets new Canvas question IDs, and one learner answers both copies
    original, repost = full.iloc[: len(full) // 2].copy(), full.iloc[len(full) // 2:].copy()
    repost.columns = [re.sub(r"^7(\d{3}):", r"8\1:", str(c)) for c in repost.columns]
    again = original.iloc[[0]].copy()
    again.columns = repost.columns
    again["submitted"] = "2099-01-01 00:00:00 UTC"
    again.iloc[0, list(again.columns).index(next(c for c in again.columns if "(EVAL_18)" in c))] = "Reposted answer"
    repost = pd.concat([repost, again], ignore_index=True)

    assert d.survey_mismatch([original, repost]) == []
    merged = d.combine_surveys([original, repost])
    assert len(merged) == full["id"].nunique()
    assert list(merged.columns[:len(original.columns)]) == [c for c in original.columns if c in merged.columns]
    row = merged[merged["id"] == original["id"].iat[0]]
    assert row[next(c for c in merged.columns if "(EVAL_18)" in c)].iat[0] == "Reposted answer"   # latest kept

    c = d.prepare({**raw, "eval": merged}, d.default_exclusions(raw["pre"]))
    assert len(c.evaluation) == len(course().evaluation)
    assert c.ksa == ("EVAL_01", "EVAL_02") and len(c.likert) == 12
