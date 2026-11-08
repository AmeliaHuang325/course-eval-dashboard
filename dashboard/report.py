"""Build a Word report with course_eval's charts and auto-written findings."""

from __future__ import annotations

from datetime import date
from io import BytesIO

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

import course_eval as ce

from .data import Course, summary

NAVY = RGBColor(0x1F, 0x4E, 0x79)


def _figure(doc: Document, fig, width: float = 6.0, caption: str | None = None) -> None:
    if fig is None:
        return
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    doc.add_picture(buffer, width=Inches(width))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    if caption:
        p = doc.add_paragraph(caption)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.runs[0].italic, p.runs[0].font.size = True, Pt(9)


def findings(course: Course, s: dict) -> list[str]:
    items = [
        f"{s['enrolled']} learners enrolled; {s['pre']} took the pre-test ({s['pre'] / max(s['enrolled'], 1):.0%}), "
        f"{s['post']} took the post-test and {s['evaluation']} completed the evaluation.",
        f"Average quiz score rose from {s['pre_avg']:.0f}% on the pre-test to {s['post_avg']:.0f}% on the post-test "
        f"(+{s['post_avg'] - s['pre_avg']:.0f} points).",
        f"Question {s['hardest_q']} remained the hardest after the course: {s['hardest_rate']:.0%} of post-test "
        f"answers were incorrect" + (f" (“{course.questions[s['hardest_q'] - 1].text}”)." if len(course.questions) >= s['hardest_q'] else "."),
        f"{s['left_after_pre']} learners took the pre-test but not the post-test.",
    ]
    if s["ksa_improved"] is not None:
        items.append(f"{s['ksa_improved']:.0%} of the {s['ksa_n']} learners who rated themselves before and after "
                     "reported a higher knowledge/skills level after the course.")
    if s["sentiment_median"] is not None:
        tone = "positive" if s["sentiment_median"] > 0.05 else "negative" if s["sentiment_median"] < -0.05 else "neutral"
        items.append(f"Open-ended comments were {tone} overall (median sentiment score {s['sentiment_median']:.2f} on a −1 to 1 scale).")
    return items


def build_report(course: Course) -> bytes:
    s = summary(course)
    doc = Document()
    doc.styles["Normal"].font.name, doc.styles["Normal"].font.size = "Calibri", Pt(11)

    title = doc.add_heading(course.title, level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for line in (course.date_range, f"Course evaluation report · generated {date.today():%b %d, %Y}"):
        p = doc.add_paragraph(line)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_heading("Key findings", level=1)
    for item in findings(course, s):
        doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("Participant journey", level=1)
    _figure(doc, ce.plot_funnel_diagram_no_program(s["enrolled"], course.pre, course.post, course.evaluation),
            caption="Learners reaching each course milestone")

    doc.add_heading("Test results", level=1)
    _figure(doc, ce.plot_test_score_distribution(course.pre, course.n_questions), caption="Pre-test score distribution")
    _figure(doc, ce.plot_test_score_distribution(course.post, course.n_questions), caption="Post-test score distribution")
    _figure(doc, ce.plot_test_false_rates(course.false_rates), caption="Share of incorrect answers by question")
    _figure(doc, ce.plot_participant_drop_between_tests_pre(course.pre, course.post),
            caption="Pre-test scores of learners who stayed vs. left before the post-test")

    if course.ksa:
        doc.add_heading("Self-assessed knowledge and skills", level=1)
        before, after = course.ksa
        _figure(doc, ce.plot_ksa_distribution(course.evaluation, before, after), width=5.5,
                caption="Self-rated level before and after the course")
        _figure(doc, ce.plot_ksa_level_differences(course.evaluation, before, after), width=5.5,
                caption="Change in self-rated level (after − before)")

    if s["comment_col"]:
        doc.add_heading("Learner feedback", level=1)
        scored = ce.process_sentiment(course.evaluation, s["comment_col"], "compound")
        if len(scored):
            _figure(doc, ce.plot_compound_sentiment_scores(scored, "compound sentiment score"),
                    caption="Sentiment of open-ended comments")
        for code, question in course.free_text.items():
            answers = ce.process_sentiment(course.evaluation, code, "compound")
            if not len(answers):
                continue
            doc.add_heading(question, level=2)
            table = doc.add_table(rows=1, cols=2)
            table.style = "Light Grid Accent 1"
            table.rows[0].cells[0].text, table.rows[0].cells[1].text = "Comment", "Sentiment"
            for text, score in answers.itertuples(index=False):
                row = table.add_row().cells
                row[0].text, row[1].text = str(text), f"{score:+.2f}"

    for heading in [p for p in doc.paragraphs if p.style.name.startswith("Heading")]:
        for run in heading.runs:
            run.font.color.rgb = NAVY

    out = BytesIO()
    doc.save(out)
    return out.getvalue()
