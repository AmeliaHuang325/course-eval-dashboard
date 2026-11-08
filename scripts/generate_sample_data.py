"""Generate a synthetic course in Canvas LMS export format.

Writes four files to sample_data/ with the same layout as the real exports:

* Pre-test Quiz Student Analysis Report.csv     (Canvas quiz "Student Analysis" report)
* Post-test Quiz Student Analysis Report.csv
* Evaluation Survey Student Analysis Report.csv (Canvas survey "Student Analysis" report)
* enrollments_export.csv                        (Canvas Catalog enrollment export)

Every learner, question, answer and comment is invented. Run from the repo root:

    python scripts/generate_sample_data.py
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

RNG = np.random.default_rng(2024)
OUT = Path(__file__).resolve().parents[1] / "sample_data"

COURSE = "DEMO-101-W Community Preparedness Fundamentals"
SECTION = "DEMO-101-W "          # Canvas keeps the trailing space from the section name
SECTION_ID, COURSE_ID, LISTING_ID, CATALOG_ID = 2101, 880, 4501, 31
START = datetime(2025, 9, 2)

N_ENROLLED = 190
P_START, P_FINISH, P_EVAL = 0.74, 0.76, 0.50      # enrolled -> pre-test -> post-test -> evaluation

# Learners are numbered IDs, not names, so the sample can't be mistaken for real people

# (code suffix, question, options, index of correct option, pre-test P(correct), post-test P(correct))
QUESTIONS = [
    ("01", "Which item belongs in a basic household emergency kit?",
     ["a. A three-day supply of water", "b. A desktop computer", "c. Decorative candles only", "d. Frozen food"], 0, 0.88, 0.97),
    ("02", "What is the main purpose of a community risk assessment?",
     ["a. To assign blame after a disaster", "b. To identify hazards and the people most exposed to them",
      "c. To replace emergency plans", "d. To estimate insurance premiums"], 1, 0.70, 0.93),
    ("03", "True or False: Warning messages are most effective when they include a specific action to take.",
     ["a. True", "b. False"], 0, 0.80, 0.95),
    ("04", "Which group is often most affected during extreme heat events?",
     ["a. Older adults living alone", "b. Office workers", "c. Professional athletes", "d. Tourists in hotels"], 0, 0.62, 0.90),
    ("05", "What does a 'shelter-in-place' instruction ask people to do?",
     ["a. Leave the area immediately", "b. Stay indoors and protect themselves where they are",
      "c. Go to the nearest school", "d. Call emergency services first"], 1, 0.75, 0.94),
    ("06", "Which source of information should residents check first during an emergency?",
     ["a. Social media rumors", "b. Official local alerts", "c. Neighbors' opinions", "d. Last year's news"], 1, 0.84, 0.96),
    ("07", "Why are volunteer organizations important during recovery?",
     ["a. They replace government agencies", "b. They only collect donations",
      "c. They extend local capacity and reach underserved residents", "d. They are not important"], 2, 0.52, 0.84),
    ("08", "True or False: Preparedness plans should be reviewed only after a disaster occurs.",
     ["a. True", "b. False"], 1, 0.68, 0.91),
    ("09", "Which step comes first when building a neighborhood preparedness plan?",
     ["a. Buying generators", "b. Printing flyers", "c. Mapping local hazards and resources", "d. Scheduling drills"], 2, 0.36, 0.70),
]

LEVELS = ["None", "Little", "Basic", "Intermediate", "Advanced"]
LIKERT = ["Strongly Disagree", "Disagree", "Neither Agree nor Disagree", "Agree", "Strongly Agree"]
STATEMENTS = [
    "The learning objectives were clear from the start.",
    "The materials were easy to follow.",
    "The pace of the course worked for me.",
    "The content applies to my day-to-day work.",
    "The examples were practical.",
    "I feel more confident helping my community prepare.",
    "The hands-on activities deepened my understanding.",
    "The difficulty level was about right.",
    "The course kept me engaged.",
    "The course was worth the time I spent on it.",
    "The course was well run from start to finish.",
    "I would tell a colleague to take this course.",
]

# Open-ended answers are composed from parts so responses vary like real comments
VALUABLE_PARTS = ["The hazard mapping exercise", "The case studies", "The warning message workshop",
                  "The module on reaching vulnerable residents", "The emergency kit checklist",
                  "The recovery planning module", "The volunteer coordination discussion", "The templates and checklists"]
VALUABLE_REASONS = ["because I can use it right away at work.", "since it was very practical and clear.",
                    "as it changed how I think about planning.", "because the examples were realistic.",
                    "since it connected well to my community's needs.", "because it was engaging and well explained."]
LEAST_PARTS = ["The history section", "The long videos in module 3", "The reading list", "The first module", "The quiz review"]
LEAST_REASONS = ["felt repetitive.", "was too long for the time we had.", "was not very relevant to my role.",
                 "had poor audio and was hard to follow.", "covered things I already knew."]
OPENERS = {
    "positive": ["Great course, thank you!", "Really enjoyed this training.", "Excellent instructor and well organized content.",
                 "Very helpful and practical.", "Well designed course, highly recommend."],
    "neutral": ["The course was fine overall.", "Good content, but", "Mostly useful."],
    "negative": ["Some parts were frustrating.", "The pace felt too slow for me.", "Too much reading for one week."],
}
SUGGESTION_PARTS = ["More local case studies would help.", "Please add downloadable slides.",
                    "Captions on the videos would improve accessibility.", "A follow-up session on recovery planning would be useful.",
                    "Shorter modules would fit my work schedule better.", "The quizzes could include more scenario questions.",
                    "Some links in module 2 were broken.", "More time for group discussion would be great."]
TOPICS = ["Recovery planning", "Volunteer management", "Risk communication", "Heat preparedness",
          "Flood response basics", "Working with schools on drills", "No preference."]


def ts(day_offset: float) -> str:
    return (START + timedelta(days=float(day_offset))).strftime("%Y-%m-%d %H:%M:%S UTC")


def learners() -> pd.DataFrame:
    names = [f"Learner {i:04d}" for i in range(1, N_ENROLLED + 1)]
    ids = RNG.choice(np.arange(20000, 99999), size=N_ENROLLED, replace=False)
    ability = RNG.normal(0, 0.9, N_ENROLLED)               # shifts each learner's chance of answering correctly
    started = RNG.random(N_ENROLLED) < P_START
    finished = started & (RNG.random(N_ENROLLED) < P_FINISH - 0.10 * (ability > 1.0))   # some strong learners drop
    evaluated = finished & (RNG.random(N_ENROLLED) < P_EVAL)
    return pd.DataFrame({"name": names, "id": ids, "ability": ability,
                         "started": started, "finished": finished, "evaluated": evaluated})


def answer(p_correct: float, ability: float, options: list[str], correct: int) -> tuple[str, float]:
    p = 1 / (1 + np.exp(-(np.log(p_correct / (1 - p_correct)) + ability)))
    if RNG.random() < p:
        return options[correct], 1.0
    wrong = [o for i, o in enumerate(options) if i != correct]
    return wrong[RNG.integers(len(wrong))], 0.0


def quiz(people: pd.DataFrame, prefix: str, day_lo: float, day_hi: float, first_qid: int) -> pd.DataFrame:
    rows = []
    for _, person in people.iterrows():
        attempts = 2 if (prefix == "PRE" and RNG.random() < 0.06) else 1
        for attempt in range(1, attempts + 1):
            rec = {"name": person["name"], "id": person["id"], "sis_id": np.nan, "section": SECTION,
                   "section_id": SECTION_ID, "section_sis_id": np.nan,
                   "submitted": ts(RNG.uniform(day_lo, day_hi)), "attempt": attempt}
            correct_count = 0
            for k, (code, text, options, correct, p_pre, p_post) in enumerate(QUESTIONS):
                p = (p_pre if prefix == "PRE" else p_post) - (0.08 if attempt == 1 and attempts == 2 else 0)
                chosen, pts = answer(min(max(p, 0.05), 0.98), person["ability"], options, correct)
                rec[f"{first_qid + k}: ({prefix}_{code}) {text}"] = chosen
                rec["1.0" if k == 0 else f"1.0.{k}"] = pts
                correct_count += int(pts)
            rec["n correct"] = correct_count
            rec["n incorrect"] = len(QUESTIONS) - correct_count
            rec["score"] = float(correct_count)
            rows.append(rec)
    return pd.DataFrame(rows)


def survey(people: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, person in people.iterrows():
        rec = {"name": person["name"], "id": person["id"], "sis_id": np.nan, "section": SECTION,
               "section_id": SECTION_ID, "section_sis_id": np.nan,
               "submitted": ts(RNG.uniform(10, 40)), "attempt": 1,
               "7001: Thank you for completing the course!\nPlease answer the questions below.": np.nan, "0.0": 0}
        points, k = [], 0

        def put(qid: int, code: str, text: str, value, scored: bool):
            nonlocal k
            rec[f"{qid}: ({code}) {text}"] = value
            rec["1.0" if k == 0 else f"1.0.{k}"] = 1.0 if (scored and value not in (None, "")) else 0.0
            points.append(rec["1.0" if k == 0 else f"1.0.{k}"])
            k += 1

        before = int(np.clip(round(RNG.normal(1.9, 0.8)), 0, 4))
        after = int(np.clip(before + RNG.choice([0, 1, 1, 1, 2, 2], p=[0.18, 0.2, 0.2, 0.17, 0.15, 0.1]), 0, 4))
        na = RNG.random() < 0.05
        put(7002, "EVAL_01", "How would you rate your knowledge of this topic BEFORE the course?",
            "Not Applicable" if na else LEVELS[before], True)
        put(7003, "EVAL_02", "How would you rate your knowledge of this topic AFTER the course?",
            "Not Applicable" if na else LEVELS[after], True)

        tone = RNG.normal(0.3, 0.75)
        for j, statement in enumerate(STATEMENTS):
            level = int(np.clip(round(3 + tone + RNG.normal(0, 0.55)), 0, 4))
            value = "Not Applicable" if RNG.random() < 0.03 else LIKERT[level]
            put(7004 + j, f"EVAL_{j + 3:02d}", statement, value, True)

        def pick(pool):
            return pool[RNG.integers(len(pool))]

        def blank(p):
            return RNG.random() < p

        most = "" if blank(0.25) else ("All of it was useful." if RNG.random() < 0.1
                                       else f"{pick(VALUABLE_PARTS)}, {pick(VALUABLE_REASONS)}")
        least = "" if blank(0.35) else (pick(["I found every part worthwhile.", "N/A"]) if RNG.random() < 0.25
                                        else f"{pick(LEAST_PARTS)} {pick(LEAST_REASONS)}")
        mood = "positive" if tone > 0.45 else ("negative" if tone < -0.2 else "neutral")
        opener = pick(OPENERS[mood])
        detail = pick(SUGGESTION_PARTS)
        comment = "" if blank(0.3) else (f"{opener} {detail[0].lower() + detail[1:]}" if opener.endswith("but")
                                         else f"{opener} {detail}")
        put(7016, "EVAL_15", "What was the most useful part of the course, and why?", most, False)
        put(7017, "EVAL_16", "What was the least useful part of the course, and why?", least, False)
        put(7018, "EVAL_17", "Any other comments or suggestions?", comment, False)
        put(7019, "EVAL_18", "Which training topics would you like to see next?", "" if blank(0.4) else pick(TOPICS), False)

        rec["n correct"] = int(sum(points))
        rec["n incorrect"] = len(points) - int(sum(points))
        rec["score"] = float(sum(points))
        rows.append(rec)
    return pd.DataFrame(rows)


def enrollments(people: pd.DataFrame) -> pd.DataFrame:
    base = {"Catalog Id": CATALOG_ID, "Catalog Name": "Demo Training Catalog", "Listing Subtitle": np.nan, "SKU": np.nan}
    rows = []
    for _, person in people.iterrows():
        created = RNG.uniform(-20, 5)
        dropped = (not person["started"]) and RNG.random() < 0.08
        status = "Dropped" if dropped else ("Completed" if person["evaluated"] else "Active")
        user = person["name"].lower().replace(" ", "")
        rows.append({**base, "Listing Id": LISTING_ID, "Listing Name": COURSE, "Listing Status": "Open For Enrollment",
                     "Canvas Course ID": COURSE_ID, "Canvas Section Id": SECTION_ID,
                     "Student Name": person["name"], "Student Email": f"{user}@example.org",
                     "Canvas User Id": person["id"], "Registered Through": "Catalog",
                     "Created At": ts(created), "Status": status,
                     "Completed At": ts(created + RNG.uniform(15, 45)) if status == "Completed" else np.nan,
                     "Certificate Attainable": "Yes", "Requirement Count": "3",
                     "Requirement Completed Count": str(int(person["started"]) + int(person["finished"]) + int(person["evaluated"])),
                     "Requirement Completed Percentage": f"{(int(person['started']) + int(person['finished']) + int(person['evaluated'])) / 3:.0%}"})
    # A Catalog export lists every course, so add a few other listings
    for listing_id, listing in [(4502, "DEMO-205-W Heat Resilience for Local Governments"),
                                (4503, "DEMO-310-W Recovery Planning Essentials")]:
        for k in range(int(RNG.integers(60, 120))):
            name = f"Learner {listing_id - 4500}{k + 1:03d}"
            status = RNG.choice(["Completed", "Active", "Dropped"], p=[0.6, 0.35, 0.05])
            rows.append({**base, "Listing Id": listing_id, "Listing Name": listing, "Listing Status": "Open For Enrollment",
                         "Canvas Course ID": listing_id - 3600, "Canvas Section Id": listing_id - 2400,
                         "Student Name": name, "Student Email": f"{name.lower().replace(' ', '')}@example.org",
                         "Canvas User Id": int(RNG.integers(100000, 199999)), "Registered Through": "Catalog",
                         "Created At": ts(RNG.uniform(-60, 0)), "Status": status, "Completed At": np.nan,
                         "Certificate Attainable": "Yes", "Requirement Count": "3",
                         "Requirement Completed Count": "3" if status == "Completed" else "1",
                         "Requirement Completed Percentage": "100%" if status == "Completed" else "33%"})
    return pd.DataFrame(rows)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    people = learners()
    pre = quiz(people[people.started], "PRE", 0, 6, 5001)
    test_account = pre.iloc[[0]].assign(name="Test Student", id=11111, score=0.0, **{"n correct": 0, "n incorrect": 9})
    pre = pd.concat([pre, test_account], ignore_index=True)       # instructors often leave a test submission
    post = quiz(people[people.finished], "POST", 8, 30, 5010)
    evaluation = survey(people[people.evaluated])
    enroll = enrollments(people)

    pre.to_csv(OUT / "Pre-test Quiz Student Analysis Report.csv", index=False)
    post.to_csv(OUT / "Post-test Quiz Student Analysis Report.csv", index=False)
    evaluation.to_csv(OUT / "Evaluation Survey Student Analysis Report.csv", index=False)
    enroll.to_csv(OUT / "enrollments_export.csv", index=False)
    print(f"enrolled {N_ENROLLED} | pre-test rows {len(pre)} | post-test {len(post)} | evaluation {len(evaluation)} "
          f"| catalog rows {len(enroll)}")


if __name__ == "__main__":
    main()
