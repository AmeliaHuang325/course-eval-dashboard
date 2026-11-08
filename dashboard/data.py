"""Load Canvas LMS exports and prepare them for the dashboard with course_eval."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

import course_eval as ce

SAMPLE_DIR = Path(__file__).resolve().parents[1] / "sample_data"
SAMPLE_FILES = {
    "pre": "Pre-test Quiz Student Analysis Report.csv",
    "post": "Post-test Quiz Student Analysis Report.csv",
    "eval": "Evaluation Survey Student Analysis Report.csv",
    "enroll": "enrollments_export.csv",
}

LEVELS = ["none", "little", "basic", "intermediate", "advanced"]
LIKERT = ["strongly disagree", "disagree", "neither agree nor disagree", "agree", "strongly agree"]
NOT_APPLICABLE = {"not applicable", "n/a", "na", ""}
QUESTION_COLUMN = re.compile(r"^\d+:\s*\((?P<code>[^)]+)\)\s*(?P<text>.*)$", re.S)


@dataclass
class Question:
    number: int
    pre_code: str
    post_code: str | None
    text: str
    options: list[str]
    correct: str | None


@dataclass
class Course:
    title: str
    date_range: str
    n_questions: int
    enroll: pd.DataFrame
    pre: pd.DataFrame
    post: pd.DataFrame
    evaluation: pd.DataFrame
    questions: list[Question]
    ksa: tuple[str, str] | None
    likert: dict[str, str]
    free_text: dict[str, str]
    false_rates: pd.DataFrame
    excluded: list[str] = field(default_factory=list)


def read_csv(source, survey: bool = False) -> pd.DataFrame:
    """Read a Canvas export from a path, bytes or an uploaded file."""
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    kwargs = {"keep_default_na": False, "na_values": ""} if survey else {}
    return pd.read_csv(source, low_memory=False, **kwargs)


def load_sample() -> dict[str, pd.DataFrame]:
    return {key: read_csv(SAMPLE_DIR / name, survey=(key == "eval")) for key, name in SAMPLE_FILES.items()}


def question_map(raw: pd.DataFrame) -> dict[str, tuple[str, list[str], str | None]]:
    """code -> (question text, answer options, correct answer) from a raw Canvas quiz report."""
    out, cols = {}, list(raw.columns)
    for i, col in enumerate(cols):
        m = QUESTION_COLUMN.match(str(col))
        if not m:
            continue
        answers = raw[col].dropna().astype(str)
        options = sorted(answers.unique().tolist())
        correct = None
        if i + 1 < len(cols):                       # Canvas puts the points column right after the answer column
            points = pd.to_numeric(raw[cols[i + 1]], errors="coerce")
            right = raw.loc[points > 0, col].dropna()
            correct = right.mode().iat[0] if len(right) else None
        out[m["code"].strip()] = (" ".join(m["text"].split()), options, correct)
    return out


def _normalized(series: pd.Series) -> set[str]:
    return set(series.dropna().astype(str).str.strip().str.lower()) - NOT_APPLICABLE


def classify_survey(raw: pd.DataFrame) -> tuple[tuple[str, str] | None, dict[str, str], dict[str, str]]:
    """Find the before/after self-rating pair, Likert statements and free-text questions."""
    ksa, likert, free_text = [], {}, {}
    for col in raw.columns:
        m = QUESTION_COLUMN.match(str(col))
        if not m:
            continue
        code, text = m["code"].strip(), " ".join(m["text"].split())
        values = _normalized(raw[col])
        if values and values <= set(LEVELS):
            ksa.append(code)
        elif values and values <= set(LIKERT):
            likert[code] = text
        elif values:
            free_text[code] = text
    return (tuple(ksa[:2]) if len(ksa) >= 2 else None), likert, free_text


def default_exclusions(raw_pre: pd.DataFrame) -> list[str]:
    """Names that look like instructor or test submissions."""
    names = raw_pre["name"].dropna().astype(str).unique()
    return sorted(n for n in names if re.search(r"\b(test|demo|instructor)\b", n, re.I))


def prepare(raw: dict[str, pd.DataFrame], exclude: list[str] | None = None, title: str | None = None) -> Course:
    exclude = list(exclude or [])
    pre_q, post_q = question_map(raw["pre"]), question_map(raw["post"])
    ksa, likert, free_text = classify_survey(raw["eval"])

    pre = ce.filter_max_attempts(raw["pre"], exclude)
    post = ce.filter_max_attempts(raw["post"], exclude)
    evaluation = ce.filter_max_attempts(raw["eval"], exclude)
    for frame in (pre, post, evaluation):
        ce.rename_columns_with_info_within_parentheses(frame)

    n_questions = ce.count_quiz_questions(pre)
    pre, post = ce.avg_score(pre, n_questions), ce.avg_score(post, n_questions)
    false_rates = pd.concat([ce.false_counts_false_rate(pre, n_questions),
                             ce.false_counts_false_rate(post, n_questions)], axis=1, keys=["Pre_Test", "Post_Test"])

    # Pair pre/post questions by their number: PRE_01 <-> POST_01
    post_by_number = {re.sub(r"\D", "", c): c for c in post_q}
    questions = []
    for i, (code, (text, options, correct)) in enumerate(pre_q.items(), start=1):
        questions.append(Question(i, code, post_by_number.get(re.sub(r"\D", "", code)), text, options, correct))

    # A Catalog export lists every course: keep the rows for this course's section(s)
    enroll = raw["enroll"]
    sections = set(raw["pre"].get("section_id", pd.Series(dtype=float)).dropna()) | \
        set(raw["post"].get("section_id", pd.Series(dtype=float)).dropna())
    if "Canvas Section Id" in enroll and sections and enroll["Canvas Section Id"].isin(sections).any():
        enroll = enroll[enroll["Canvas Section Id"].isin(sections)]
    if exclude and "Student Name" in enroll:
        enroll = enroll[~enroll["Student Name"].isin(exclude)]

    if title is None:
        if "Listing Name" in enroll and enroll["Listing Name"].nunique() == 1:
            title = str(enroll["Listing Name"].iat[0])
        else:
            title = str(raw["pre"]["section"].dropna().iat[0]).strip() if "section" in raw["pre"] else "Course"

    dates = pd.to_datetime(pd.concat([raw[k]["submitted"] for k in ("pre", "post", "eval") if "submitted" in raw[k]]),
                           errors="coerce", utc=True).dropna()
    date_range = f"{dates.min():%b %d, %Y} – {dates.max():%b %d, %Y}" if len(dates) else ""

    return Course(title, date_range, n_questions, enroll.reset_index(drop=True), pre, post, evaluation,
                  questions, ksa, likert, free_text, false_rates, exclude)


def level_scores(course: Course) -> pd.DataFrame:
    """Before/after self-ratings as numbers 1-5 for learners who answered both."""
    if not course.ksa:
        return pd.DataFrame(columns=["before", "after", "change"])
    before, after = course.ksa
    lookup = {level: i + 1 for i, level in enumerate(LEVELS)}
    scores = pd.DataFrame({
        "before": course.evaluation[before].astype(str).str.strip().str.lower().map(lookup),
        "after": course.evaluation[after].astype(str).str.strip().str.lower().map(lookup),
    }).dropna()
    scores["change"] = scores["after"] - scores["before"]
    return scores


def summary(course: Course) -> dict:
    """Headline numbers shared by the KPI cards and the Word report."""
    ids = {k: set(getattr(course, k)["id"]) for k in ("pre", "post", "evaluation")}
    enrolled = course.enroll["Canvas User Id"].nunique() if "Canvas User Id" in course.enroll else len(course.enroll)
    both = course.pre[course.pre["id"].isin(ids["post"])]
    levels = level_scores(course)
    sentiment = None
    comment_col = next((c for c in reversed(list(course.free_text)) if "comment" in course.free_text[c].lower()
                        or "suggestion" in course.free_text[c].lower()), None)
    if comment_col:
        scored = ce.process_sentiment(course.evaluation, comment_col, "compound")
        sentiment = float(scored["compound sentiment score"].median()) if len(scored) else None
    hardest = course.false_rates["Post_Test"]["false_rate"].idxmax()
    return {
        "enrolled": enrolled,
        "pre": len(course.pre), "post": len(course.post), "evaluation": len(course.evaluation),
        "pre_avg": course.pre["score_percentage"].mean(), "post_avg": course.post["score_percentage"].mean(),
        "both": len(both),
        "left_after_pre": len(ids["pre"] - ids["post"]),
        "ksa_n": len(levels), "ksa_improved": float((levels["change"] > 0).mean()) if len(levels) else None,
        "sentiment_median": sentiment, "comment_col": comment_col,
        "hardest_q": int(hardest.lstrip("q")),
        "hardest_rate": float(course.false_rates["Post_Test"].loc[hardest, "false_rate"]),
    }
