"""Interactive Plotly charts for the dashboard."""

from __future__ import annotations

import textwrap

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import course_eval as ce

from .data import LEVELS, LIKERT, Course, level_scores

# Same palette as the R Shiny training-outreach dashboard:
# navy #1F4E79 as the main color, ColorBrewer Blues for amounts and before/after,
# ColorBrewer Pastel1 for categories, and #E3E7EC for "none".
NAVY = "#1F4E79"
BLUES = ["#DEEBF7", "#C6DBEF", "#9ECAE1", "#6BAED6", "#4292C6", "#2171B5", "#08519C", "#08306B"]
PASTEL1 = ["#FBB4AE", "#B3CDE3", "#CCEBC5", "#DECBE4", "#FED9A6", "#FFFFCC", "#E5D8BD", "#FDDAEC", "#F2F2F2"]
NONE_GREY, GREY = "#E3E7EC", "#A6B1BE"
NEGATIVE, NEGATIVE_LIGHT = PASTEL1[0], PASTEL1[7]           # pastel red / pink for losses and disagreement
PRE, POST = BLUES[3], NAVY                                 # before = light blue, after = navy
STAGES = [NAVY, BLUES[5], BLUES[3], BLUES[2]]
FONT = "Inter, Segoe UI, Helvetica, Arial, sans-serif"


def _style(fig: go.Figure, height: int = 380, legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=30, b=10), font=dict(family=FONT, size=13, color="#1F2A37"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None),
        hoverlabel=dict(bgcolor="white", font_family=FONT),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor="#D5DBE3")
    fig.update_yaxes(gridcolor="#EEF1F5", zeroline=False)
    return fig


def _wrap(text: str, width: int = 60) -> str:
    return "<br>".join(textwrap.wrap(text, width))


# Participation ----------------------------------------------------------------

def funnel(course: Course, s: dict) -> go.Figure:
    stages = ["Enrolled", "Pre-test", "Post-test", "Evaluation"]
    values = [s["enrolled"], s["pre"], s["post"], s["evaluation"]]
    fig = go.Figure(go.Funnel(
        y=stages, x=values, textinfo="value+percent initial", marker=dict(color=STAGES),
        connector=dict(fillcolor=NONE_GREY, line=dict(color=NONE_GREY, width=1)),
        hovertemplate="%{y}: %{x} learners (%{percentInitial:.0%} of enrolled)<extra></extra>"))
    return _style(fig, 360, legend=False)


def flow(course: Course, s: dict) -> go.Figure:
    pre_ids, post_ids, eval_ids = (set(getattr(course, k)["id"]) for k in ("pre", "post", "evaluation"))
    started = s["pre"]
    labels = ["Enrolled", "Took pre-test", "Never started", "Took post-test", "Left after pre-test",
              "Completed evaluation", "Skipped evaluation"]
    values = [started, max(s["enrolled"] - started, 0),
              len(pre_ids & post_ids), len(pre_ids - post_ids),
              len(post_ids & eval_ids), len(post_ids - eval_ids)]
    fig = go.Figure(go.Sankey(
        arrangement="snap",
        textfont=dict(color="#1F2A37", size=13, shadow="none"),   # solid dark labels, no glow over the flows
        node=dict(label=labels, pad=18, thickness=16, line=dict(width=0),
                  color=[NAVY, BLUES[5], NONE_GREY, BLUES[3], NONE_GREY, BLUES[2], NONE_GREY]),
        link=dict(source=[0, 0, 1, 1, 3, 3], target=[1, 2, 3, 4, 5, 6], value=values,
                  color=["rgba(33,113,181,.30)", "rgba(227,231,236,.8)", "rgba(107,174,214,.35)",
                         "rgba(227,231,236,.8)", "rgba(158,202,225,.45)", "rgba(227,231,236,.8)"],
                  hovertemplate="%{source.label} → %{target.label}: %{value}<extra></extra>")))
    return _style(fig, 360, legend=False)


def dropout_by_pre_score(course: Course) -> go.Figure:
    post_ids = set(course.post["id"])
    df = course.pre.assign(group=np.where(course.pre["id"].isin(post_ids), "Took both tests", "Left after pre-test"))
    counts = df.groupby(["score_percentage", "group"]).size().unstack(fill_value=0)
    fig = go.Figure()
    for group, color in [("Took both tests", NAVY), ("Left after pre-test", NEGATIVE)]:
        if group in counts:
            fig.add_bar(x=counts.index, y=counts[group], name=group, marker_color=color,
                        hovertemplate="Pre-test %{x:.0f}%: %{y} learners<extra>" + group + "</extra>")
    fig.update_layout(barmode="stack", bargap=0.15)
    fig.update_xaxes(title="Pre-test score (%)", ticksuffix="%")
    fig.update_yaxes(title="Learners")
    return _style(fig, 340)


# Test results -----------------------------------------------------------------

def score_distribution(course: Course) -> go.Figure:
    step = 100 / course.n_questions
    levels = [round(i * step, 1) for i in range(course.n_questions + 1)]
    labels = [f"{v:.0f}%" for v in levels]
    fig = go.Figure()
    for name, df, color in [("Pre-test", course.pre, PRE), ("Post-test", course.post, POST)]:
        counts = df["score_percentage"].round(1).value_counts().reindex(levels, fill_value=0)
        mean = df["score_percentage"].mean()
        fig.add_bar(x=labels, y=counts.values, name=f"{name} (avg {mean:.0f}%)", marker_color=color,
                    text=[c if c else "" for c in counts.values], textposition="outside",
                    hovertemplate="Score %{x}: %{y} learners<extra>" + name + "</extra>")
    fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.05)
    fig.update_xaxes(title="Score", type="category")
    fig.update_yaxes(title="Learners")
    return _style(fig, 360)


def score_change(course: Course) -> go.Figure:
    both = course.pre[["id", "score_percentage"]].merge(
        course.post[["id", "score_percentage"]], on="id", suffixes=("_pre", "_post"))
    pairs = both.groupby(["score_percentage_pre", "score_percentage_post"]).size().reset_index(name="n")
    improved = pairs["score_percentage_post"] > pairs["score_percentage_pre"]
    fig = go.Figure()
    fig.add_scatter(x=[0, 100], y=[0, 100], mode="lines", line=dict(color=NONE_GREY, dash="dot", width=2),
                    hoverinfo="skip", showlegend=False)
    for mask, name, color in [(improved, "Improved", NAVY), (~improved, "No gain", GREY)]:
        part = pairs[mask]
        fig.add_scatter(x=part["score_percentage_pre"], y=part["score_percentage_post"], mode="markers", name=name,
                        marker=dict(size=7 + np.sqrt(part["n"]) * 5, color=color, opacity=0.75,
                                    line=dict(width=1, color="white")), cliponaxis=False,
                        customdata=part["n"],
                        hovertemplate="Pre %{x:.0f}% → Post %{y:.0f}%<br>%{customdata} learners<extra></extra>")
    fig.update_xaxes(title="Pre-test score (%)", range=[-5, 110], ticksuffix="%")
    fig.update_yaxes(title="Post-test score (%)", range=[-5, 112], ticksuffix="%")
    return _style(fig, 360)


def question_errors(course: Course) -> go.Figure:
    rates = course.false_rates
    labels = [f"Q{i}" for i in range(1, len(rates) + 1)]
    texts = [_wrap(q.text, 55) for q in course.questions] + [""] * (len(rates) - len(course.questions))
    fig = go.Figure()
    for key, name, color in [("Pre_Test", "Pre-test", PRE), ("Post_Test", "Post-test", POST)]:
        fig.add_bar(x=labels, y=rates[key]["false_rate"], name=name, marker_color=color, customdata=texts,
                    text=[f"{v:.0%}" for v in rates[key]["false_rate"]], textposition="outside",
                    hovertemplate="<b>%{x}</b>: %{y:.0%} answered incorrectly<br>%{customdata}<extra>" + name + "</extra>")
    fig.update_layout(barmode="group", bargap=0.25, uniformtext_minsize=9)
    fig.update_yaxes(title="Answered incorrectly", tickformat=".0%",
                     range=[0, max(0.1, float(rates.xs("false_rate", axis=1, level=1).max().max())) * 1.25])
    return _style(fig, 380)


def answer_breakdown(course: Course, number: int) -> go.Figure:
    q = course.questions[number - 1]
    fig = make_subplots(rows=1, cols=2, specs=[[{"type": "domain"}, {"type": "domain"}]], horizontal_spacing=0.08)
    palette = PASTEL1[1:]
    options = q.options or sorted(course.pre[q.pre_code].dropna().astype(str).unique())
    wrong = [o for o in options if o != q.correct]
    colors = {opt: NAVY if opt == q.correct else palette[wrong.index(opt) % len(palette)] for opt in options}
    for col, (df, code) in enumerate([(course.pre, q.pre_code), (course.post, q.post_code)], start=1):
        if code is None or code not in df:
            continue
        counts = df[code].dropna().astype(str).value_counts().reindex(options).dropna()
        share = counts.get(q.correct, 0) / max(counts.sum(), 1)
        fig.add_annotation(text=f"<b>{'Pre-test' if col == 1 else 'Post-test'}</b><br>{share:.0%} correct",
                           x=0.21 if col == 1 else 0.79, y=0.5, xref="paper", yref="paper", showarrow=False,
                           font=dict(size=15, color=NAVY))
        names = [("✓ " if opt == q.correct else "") + opt for opt in counts.index]
        fig.add_pie(labels=names, values=counts.values, hole=0.55, row=1, col=col, sort=False,
                    marker=dict(colors=[colors.get(o, GREY) for o in counts.index], line=dict(color="white", width=2)),
                    textinfo="percent", textposition="inside", insidetextorientation="horizontal",
                    hovertemplate="%{label}<br>%{value} learners (%{percent})<extra></extra>")
    fig = _style(fig, 460)
    fig.update_layout(uniformtext=dict(minsize=10, mode="hide"), margin=dict(l=10, r=10, t=20, b=70),
                      legend=dict(orientation="h", yanchor="top", y=-0.08, xanchor="center", x=0.5))
    return fig


# Self-assessment --------------------------------------------------------------

def ksa_levels(course: Course) -> go.Figure:
    scores = level_scores(course)
    names = [lvl.title() for lvl in LEVELS]
    fig = go.Figure()
    for col, name, color in [("before", "Before the course", BLUES[2]), ("after", "After the course", NAVY)]:
        counts = scores[col].value_counts().reindex(range(1, 6), fill_value=0)
        fig.add_bar(x=names, y=counts.values, name=name, marker_color=color, text=counts.values, textposition="outside",
                    hovertemplate="%{x}: %{y} learners<extra>" + name + "</extra>")
    fig.update_layout(barmode="group", bargap=0.3)
    fig.update_yaxes(title="Learners")
    return _style(fig, 360)


def ksa_change(course: Course) -> go.Figure:
    change = level_scores(course)["change"].astype(int).value_counts().sort_index()
    labels = ["No change" if c == 0 else (f"+{c} level{'s' if c > 1 else ''}" if c > 0 else f"{c} level{'s' if c < -1 else ''}")
              for c in change.index]
    colors = [NAVY if c > 0 else (NONE_GREY if c == 0 else NEGATIVE) for c in change.index]
    fig = go.Figure(go.Bar(x=labels, y=change.values, marker_color=colors, text=change.values, textposition="outside",
                           hovertemplate="%{x}: %{y} learners<extra></extra>"))
    fig.update_yaxes(title="Learners")
    return _style(fig, 360, legend=False)


def likert(course: Course) -> go.Figure:
    order = [lvl.title() for lvl in LIKERT]
    colors = {"Strongly Disagree": NEGATIVE, "Disagree": NEGATIVE_LIGHT, "Neither Agree Nor Disagree": NONE_GREY,
              "Agree": BLUES[2], "Strongly Agree": NAVY}
    rows = []
    for code, statement in course.likert.items():
        answers = course.evaluation[code].astype(str).str.strip().str.title()
        answers = answers[answers.isin(order)]
        shares = answers.value_counts(normalize=True).reindex(order, fill_value=0)
        rows.append((_wrap(statement, 48), shares))
    rows.sort(key=lambda r: r[1]["Agree"] + r[1]["Strongly Agree"])
    fig = go.Figure()
    for level in order:
        values = [r[1][level] for r in rows]
        sign = -1 if "Disagree" in level and "Neither" not in level else 1
        if level == "Neither Agree Nor Disagree":
            fig.add_bar(y=[r[0] for r in rows], x=[v / 2 for v in values], base=[-v / 2 for v in values], orientation="h",
                        name="Neutral", marker_color=colors[level], customdata=values,
                        hovertemplate="%{customdata:.0%} neutral<extra></extra>")
            continue
        fig.add_bar(y=[r[0] for r in rows], x=[sign * v for v in values], orientation="h", name=level,
                    marker_color=colors[level], customdata=values,
                    hovertemplate="%{customdata:.0%} " + level.lower() + "<extra></extra>")
    fig.update_layout(barmode="relative", bargap=0.35)
    fig.update_xaxes(tickformat=".0%", range=[-0.5, 1.05], title="Share of responses (disagree ← → agree)")
    return _style(fig, max(380, 42 * len(rows)))


# Feedback ---------------------------------------------------------------------

def sentiment(scored: pd.DataFrame, score_col: str) -> go.Figure:
    values = scored[score_col]
    fig = go.Figure()
    fig.add_box(x=values, boxpoints="all", jitter=0.5, pointpos=0, marker=dict(color=NAVY, size=7, opacity=0.6),
                line=dict(color=BLUES[5]), fillcolor="rgba(158,202,225,.25)", name="",
                customdata=[_wrap(str(t), 60) for t in scored.iloc[:, 0]],
                hovertemplate="Score %{x:.2f}<br>%{customdata}<extra></extra>")
    fig.add_vrect(x0=-1, x1=-0.05, fillcolor=NEGATIVE_LIGHT, opacity=0.45, line_width=0, layer="below")
    fig.add_vrect(x0=0.05, x1=1, fillcolor=BLUES[0], opacity=0.6, line_width=0, layer="below")
    fig.update_xaxes(range=[-1.05, 1.05], title="Sentiment score (−1 negative · 0 neutral · +1 positive)")
    fig.update_yaxes(showticklabels=False)
    return _style(fig, 260, legend=False)


def score_comments(course: Course, code: str, kind: str = "compound") -> pd.DataFrame:
    return ce.process_sentiment(course.evaluation, code, kind)
