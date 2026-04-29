"""
Hot or Not - Radionuclide Cram Mode

A Streamlit minigame for rapid radionuclide fact recall.
The player must keep the HOT meter above the NOT zone while answering
two-choice questions about half-life, decay mode, emissions, and generation.

MVP features:
- CSV-backed questions
- Two clickable answer cards
- HOT meter with time-based decay
- Difficulty levels
- XP, streaks, speed bonus
- Round win/loss logic
- End-of-round summary
"""

from __future__ import annotations

import random
import time
from pathlib import Path

import pandas as pd
import streamlit as st


# ---------------------------------------------------------------------
# Optional live refresh support
# ---------------------------------------------------------------------
# This package is optional.
# Install with:
#   pip install streamlit-autorefresh
#
# If not installed, the app still works, but the HOT meter updates mainly
# when the user clicks buttons or Streamlit reruns.
try:
    from streamlit_autorefresh import st_autorefresh

    HAS_AUTOREFRESH = True
except ImportError:
    HAS_AUTOREFRESH = False


# ---------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------
st.set_page_config(
    page_title="Hot or Not",
    page_icon="🔥",
    layout="centered",
)


# ---------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------
DATA_DIR = Path("data/hot_or_not")

FACT_TYPE_LABELS = {
    "half_life": "Half-Life",
    "decay_mode": "Decay Mode",
    "emission": "Emission",
    "generation": "Generation",
    "common_use": "Common Use",
}

DIFFICULTY_SETTINGS = {
    1: {
        "name": "Warm Background",
        "decay_rate": 1.0,
        "correct_bump": 12,
        "wrong_penalty": 10,
    },
    2: {
        "name": "Mild Uptake",
        "decay_rate": 1.5,
        "correct_bump": 10,
        "wrong_penalty": 12,
    },
    3: {
        "name": "Physiologic Activity",
        "decay_rate": 2.0,
        "correct_bump": 9,
        "wrong_penalty": 15,
    },
    4: {
        "name": "Intense Focal Uptake",
        "decay_rate": 2.5,
        "correct_bump": 8,
        "wrong_penalty": 18,
    },
    5: {
        "name": "Hot Lab Meltdown",
        "decay_rate": 3.0,
        "correct_bump": 7,
        "wrong_penalty": 20,
    },
}

XP_LEVELS = [
    {"level": 1, "name": "Non-Avid", "xp_required": 0},
    {"level": 2, "name": "Mild Uptake", "xp_required": 100},
    {"level": 3, "name": "Heterogenous Uptake", "xp_required": 250},
    {"level": 4, "name": "Focal Uptake", "xp_required": 500},
    {"level": 5, "name": "Bone Scan Banger", "xp_required": 900},
    {"level": 6, "name": "Howard's Apprentice", "xp_required": 1400},
    {"level": 7, "name": "Basically a 3/5 Resident", "xp_required": 2200},
    {"level": 8, "name": "Mettler Himself", "xp_required": 3200},
]

STARTING_HOT = 65.0
MAX_HOT = 100.0
NOT_THRESHOLD = 20.0


# ---------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------
st.markdown(
    """
    <style>
    .game-title {
        font-size: 2.4rem;
        font-weight: 800;
        margin-bottom: 0.2rem;
        text-align: center;
    }

    .subtitle {
        text-align: center;
        opacity: 0.8;
        margin-bottom: 1.5rem;
    }

    .question-card {
        border: 1px solid rgba(250, 250, 250, 0.15);
        border-radius: 18px;
        padding: 1.25rem;
        margin: 1rem 0;
        background: rgba(255, 255, 255, 0.04);
        text-align: center;
    }

    .radionuclide {
        font-size: 2.2rem;
        font-weight: 800;
        margin: 0.5rem 0;
    }

    .prompt-text {
        font-size: 1.15rem;
        opacity: 0.9;
    }

    .feedback-box {
        border-radius: 14px;
        padding: 1rem;
        margin-top: 1rem;
        background: rgba(255, 255, 255, 0.06);
    }

    .small-muted {
        font-size: 0.9rem;
        opacity: 0.75;
    }

    div.stButton > button {
        width: 100%;
        min-height: 5rem;
        border-radius: 18px;
        font-size: 1.05rem;
        font-weight: 700;
        white-space: normal;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------
@st.cache_data
def load_questions(data_dir: Path) -> pd.DataFrame:
    """
    Load Hot or Not fact files from data/hot_or_not/.

    Expected file format for each PSV:
        item_id|radionuclide|prompt|correct_option|explanation|difficulty

    Optional columns:
        distractor_group

    The fact_type is inferred from the filename.
    Example:
        half_life.psv -> fact_type = "half_life"
    """
    if not data_dir.exists():
        return pd.DataFrame()

    required_columns = {
        "item_id",
        "radionuclide",
        "prompt",
        "correct_option",
        "explanation",
        "difficulty",
    }

    base_columns = [
        "question_id",
        "item_id",
        "radionuclide",
        "fact_type",
        "prompt",
        "correct_option",
        "explanation",
        "difficulty",
    ]

    supported_optional_columns = [
        "distractor_group",
    ]

    frames = []

    for path in sorted(data_dir.glob("*.psv")):
        fact_type = path.stem

        # Skip empty placeholder files.
        if path.stat().st_size == 0:
            continue

        try:
            df = pd.read_csv(path, sep="|", quotechar='"', skip_blank_lines=True)
        except pd.errors.EmptyDataError:
            continue

        df.columns = df.columns.str.strip()

        # Skip files that only have a header and no rows.
        if df.empty:
            continue

        missing = required_columns - set(df.columns)
        if missing:
            raise ValueError(
                f"{path.name} is missing required column(s): "
                f"{', '.join(sorted(missing))}"
            )

        df = df.copy()
        df["fact_type"] = fact_type
        df["question_id"] = (
            df["fact_type"].astype(str) + "_" + df["item_id"].astype(str)
        )

        df["difficulty"] = (
            pd.to_numeric(df["difficulty"], errors="coerce")
            .fillna(1)
            .astype(int)
            .clip(1, 5)
        )

        optional_columns = [
            col for col in supported_optional_columns if col in df.columns
        ]

        frames.append(df[base_columns + optional_columns])

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)

    # Basic cleanup
    text_cols = [
        "question_id",
        "item_id",
        "radionuclide",
        "fact_type",
        "prompt",
        "correct_option",
        "explanation",
        "distractor_group",
    ]

    for col in text_cols:
        if col in combined.columns:
            combined[col] = combined[col].astype(str).str.strip()

    combined = combined.dropna(subset=["radionuclide", "correct_option"])
    combined = combined[combined["correct_option"].str.len() > 0]

    # Normalize optional distractor_group.
    # If a file does not have distractor_group, fall back to correct_option.
    # This preserves old behavior while letting emission.psv opt into smarter grouping.
    if "distractor_group" not in combined.columns:
        combined["distractor_group"] = combined["correct_option"]
    else:
        combined["distractor_group"] = combined["distractor_group"].fillna("")
        combined.loc[
            combined["distractor_group"].str.len() == 0,
            "distractor_group",
        ] = combined["correct_option"]

    return combined


# ---------------------------------------------------------------------
# XP helpers
# ---------------------------------------------------------------------
def get_xp_level(total_xp: int) -> dict:
    current = XP_LEVELS[0]
    for level in XP_LEVELS:
        if total_xp >= level["xp_required"]:
            current = level
    return current


def get_next_xp_level(total_xp: int) -> dict | None:
    for level in XP_LEVELS:
        if total_xp < level["xp_required"]:
            return level
    return None


def get_streak_multiplier(streak: int) -> float:
    if streak >= 10:
        return 2.0
    if streak >= 6:
        return 1.5
    if streak >= 3:
        return 1.25
    return 1.0


def calculate_xp_for_answer(is_correct: bool, answer_time: float, streak: int) -> tuple[int, dict]:
    if not is_correct:
        return 0, {
            "base_xp": 0,
            "speed_bonus": 0,
            "multiplier": 1.0,
        }

    base_xp = 10
    speed_bonus = 5 if answer_time < 3.0 else 0
    multiplier = get_streak_multiplier(streak)
    earned = round((base_xp + speed_bonus) * multiplier)

    return earned, {
        "base_xp": base_xp,
        "speed_bonus": speed_bonus,
        "multiplier": multiplier,
    }


# ---------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------
def init_global_state() -> None:
    st.session_state.setdefault("hon_total_xp", 0)
    st.session_state.setdefault("hon_lifetime_rounds", 0)
    st.session_state.setdefault("hon_lifetime_correct", 0)
    st.session_state.setdefault("hon_lifetime_answered", 0)


def reset_round_state() -> None:
    keys_to_clear = [
        "hon_round_active",
        "hon_round_complete",
        "hon_round_lost",
        "hon_round_questions",
        "hon_question_index",
        "hon_hot_meter",
        "hon_last_tick",
        "hon_question_started_at",
        "hon_streak",
        "hon_best_streak",
        "hon_round_correct",
        "hon_round_answered",
        "hon_round_xp",
        "hon_feedback",
        "hon_options",
        "hon_settings",
    ]

    for key in keys_to_clear:
        st.session_state.pop(key, None)


def start_round(
    df: pd.DataFrame,
    selected_fact_types: list[str],
    max_difficulty: int,
    round_length: int,
    difficulty_level: int,
) -> None:
    reset_round_state()

    filtered = df.copy()

    if selected_fact_types:
        filtered = filtered[filtered["fact_type"].isin(selected_fact_types)]

    filtered = filtered[filtered["difficulty"] <= max_difficulty]

    if filtered.empty:
        st.error("No questions match the selected filters.")
        return

    # Only keep fact types that have at least 2 unique answer choices.
    # Otherwise we cannot generate a wrong answer from the same category.
    eligible_fact_types = []
    for fact_type, group in filtered.groupby("fact_type"):
        if group["correct_option"].nunique() >= 2:
            eligible_fact_types.append(fact_type)

    filtered = filtered[filtered["fact_type"].isin(eligible_fact_types)]

    if filtered.empty:
        st.error(
            "No eligible questions found. Each selected fact type needs at least "
            "two unique correct_option values so the app can generate distractors."
        )
        return

    sampled = filtered.sample(
        n=min(round_length, len(filtered)),
        replace=False,
        random_state=None,
    ).to_dict("records")

    # Dynamically generate one incorrect option for each sampled question.
    # Distractors come from other correct answers in the same fact type.
    generated_questions = []

    for question in sampled:
        fact_type = question["fact_type"]
        correct_option = str(question["correct_option"])

        same_fact_type = filtered[filtered["fact_type"] == fact_type].copy()

        correct_group = str(question.get("distractor_group", "")).strip()

        distractor_rows = same_fact_type[
            same_fact_type["distractor_group"].astype(str).str.strip() != correct_group
        ]

        distractor_pool = (
            distractor_rows["correct_option"]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        if not distractor_pool:
            continue

        question = question.copy()
        question["incorrect_option"] = random.choice(distractor_pool)
        generated_questions.append(question)

    if not generated_questions:
        st.error("Could not generate any questions with distractors.")
        return

    st.session_state.hon_round_active = True
    st.session_state.hon_round_complete = False
    st.session_state.hon_round_lost = False
    st.session_state.hon_round_questions = generated_questions
    st.session_state.hon_question_index = 0
    st.session_state.hon_hot_meter = STARTING_HOT
    st.session_state.hon_last_tick = time.time()
    st.session_state.hon_question_started_at = time.time()
    st.session_state.hon_streak = 0
    st.session_state.hon_best_streak = 0
    st.session_state.hon_round_correct = 0
    st.session_state.hon_round_answered = 0
    st.session_state.hon_round_xp = 0
    st.session_state.hon_feedback = None
    st.session_state.hon_options = {}
    st.session_state.hon_settings = {
        "difficulty_level": difficulty_level,
        "round_length": round_length,
        "selected_fact_types": selected_fact_types,
        "max_difficulty": max_difficulty,
    }


def apply_decay() -> None:
    if not st.session_state.get("hon_round_active", False):
        return

    if st.session_state.get("hon_round_complete", False):
        return

    now = time.time()
    last_tick = st.session_state.get("hon_last_tick", now)
    elapsed = max(0.0, now - last_tick)

    difficulty_level = st.session_state.hon_settings["difficulty_level"]
    decay_rate = DIFFICULTY_SETTINGS[difficulty_level]["decay_rate"]

    st.session_state.hon_hot_meter = max(
        0.0,
        st.session_state.hon_hot_meter - elapsed * decay_rate,
    )
    st.session_state.hon_last_tick = now

    if st.session_state.hon_hot_meter <= NOT_THRESHOLD:
        st.session_state.hon_round_lost = True
        st.session_state.hon_round_complete = True
        st.session_state.hon_round_active = False


def get_current_question() -> dict | None:
    questions = st.session_state.get("hon_round_questions", [])
    idx = st.session_state.get("hon_question_index", 0)

    if idx >= len(questions):
        return None

    return questions[idx]


def get_shuffled_options(question: dict) -> list[str]:
    question_id = question["question_id"]

    if question_id not in st.session_state.hon_options:
        options = [
            str(question["correct_option"]),
            str(question["incorrect_option"]),
        ]
        random.shuffle(options)
        st.session_state.hon_options[question_id] = options

    return st.session_state.hon_options[question_id]


def submit_answer(selected_option: str) -> None:
    question = get_current_question()

    if question is None:
        return

    now = time.time()
    answer_time = now - st.session_state.get("hon_question_started_at", now)

    correct_option = str(question["correct_option"])
    is_correct = selected_option == correct_option

    difficulty_level = st.session_state.hon_settings["difficulty_level"]
    settings = DIFFICULTY_SETTINGS[difficulty_level]

    st.session_state.hon_round_answered += 1
    st.session_state.hon_lifetime_answered += 1

    if is_correct:
        st.session_state.hon_round_correct += 1
        st.session_state.hon_lifetime_correct += 1
        st.session_state.hon_streak += 1
        st.session_state.hon_best_streak = max(
            st.session_state.hon_best_streak,
            st.session_state.hon_streak,
        )
        st.session_state.hon_hot_meter = min(
            MAX_HOT,
            st.session_state.hon_hot_meter + settings["correct_bump"],
        )
    else:
        st.session_state.hon_streak = 0
        st.session_state.hon_hot_meter = max(
            0.0,
            st.session_state.hon_hot_meter - settings["wrong_penalty"],
        )

    earned_xp, xp_details = calculate_xp_for_answer(
        is_correct=is_correct,
        answer_time=answer_time,
        streak=st.session_state.hon_streak,
    )

    st.session_state.hon_total_xp += earned_xp
    st.session_state.hon_round_xp += earned_xp

    st.session_state.hon_feedback = {
        "is_correct": is_correct,
        "selected_option": selected_option,
        "correct_option": correct_option,
        "explanation": str(question["explanation"]),
        "answer_time": answer_time,
        "earned_xp": earned_xp,
        "xp_details": xp_details,
    }

    # Check loss immediately after wrong-answer penalty.
    if st.session_state.hon_hot_meter <= NOT_THRESHOLD:
        st.session_state.hon_round_lost = True
        st.session_state.hon_round_complete = True
        st.session_state.hon_round_active = False
        return

    # Advance to next question.
    st.session_state.hon_question_index += 1

    if st.session_state.hon_question_index >= len(st.session_state.hon_round_questions):
        st.session_state.hon_round_complete = True
        st.session_state.hon_round_active = False
        st.session_state.hon_lifetime_rounds += 1

        # Completion bonuses
        st.session_state.hon_total_xp += 25
        st.session_state.hon_round_xp += 25

        if st.session_state.hon_round_correct == st.session_state.hon_round_answered:
            st.session_state.hon_total_xp += 50
            st.session_state.hon_round_xp += 50
    else:
        st.session_state.hon_question_started_at = time.time()


# ---------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------
def render_hot_meter(value: float) -> None:
    value = max(0.0, min(MAX_HOT, value))
    progress_value = value / MAX_HOT

    label = f"HOT Meter: {value:.0f}/100 | NOT Zone below {NOT_THRESHOLD:.0f}"

    st.progress(progress_value, text=label)

    if value <= NOT_THRESHOLD:
        st.error("❄️ NOT ZONE")
    elif value < 40:
        st.warning("⚠️ Getting cold...")
    else:
        st.success("🔥 Still HOT")


def render_xp_bar() -> None:
    total_xp = st.session_state.get("hon_total_xp", 0)
    current_level = get_xp_level(total_xp)
    next_level = get_next_xp_level(total_xp)

    if next_level is None:
        st.progress(1.0, text=f"Level {current_level['level']}: {current_level['name']} — MAX LEVEL")
        return

    current_floor = current_level["xp_required"]
    next_floor = next_level["xp_required"]
    span = next_floor - current_floor
    progress = (total_xp - current_floor) / span if span else 1.0

    st.progress(
        progress,
        text=(
            f"Level {current_level['level']}: {current_level['name']} "
            f"— {total_xp}/{next_floor} XP"
        ),
    )


def render_feedback() -> None:
    feedback = st.session_state.get("hon_feedback")

    if not feedback:
        return

    if feedback["is_correct"]:
        st.success(
            f"🔥 HOT! +{feedback['earned_xp']} XP "
            f"({feedback['answer_time']:.1f} sec)"
        )
    else:
        st.error(
            f"❄️ NOT! Correct answer: {feedback['correct_option']}"
        )

    with st.expander("Explanation", expanded=not feedback["is_correct"]):
        st.write(feedback["explanation"])

        if feedback["is_correct"]:
            details = feedback["xp_details"]
            st.caption(
                f"Base XP: {details['base_xp']} | "
                f"Speed bonus: {details['speed_bonus']} | "
                f"Streak multiplier: {details['multiplier']}x"
            )


def render_round_summary() -> None:
    lost = st.session_state.get("hon_round_lost", False)
    answered = st.session_state.get("hon_round_answered", 0)
    correct = st.session_state.get("hon_round_correct", 0)
    accuracy = correct / answered if answered else 0

    st.markdown("---")

    if lost:
        st.error("❄️ Round over — you dropped into the NOT zone.")
    else:
        st.success("🔥 Round cleared!")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Correct", f"{correct}/{answered}")
    col2.metric("Accuracy", f"{accuracy:.0%}")
    col3.metric("Best streak", st.session_state.get("hon_best_streak", 0))
    col4.metric("XP earned", st.session_state.get("hon_round_xp", 0))

    if not lost:
        st.caption("Round clear bonus: +25 XP. Perfect round bonus: +50 XP.")

    if st.button("Play Again 🔁", type="primary"):
        reset_round_state()
        st.rerun()


# ---------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------
init_global_state()

st.markdown("<div class='game-title'>🔥 Hot or Not</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='subtitle'>Radionuclide cram mode: keep your HOT meter above the NOT zone.</div>",
    unsafe_allow_html=True,
)

try:
    questions_df = load_questions(DATA_DIR)
except Exception as exc:
    st.error(f"Could not load question file: {exc}")
    st.stop()

if questions_df.empty:
    st.error(
        "No Hot or Not question files found. "
        "Create PSV files in data/hot_or_not/, such as half_life.psv or emission.psv."
    )
    st.stop()


# Sidebar settings
with st.sidebar:
    st.header("🔥 Hot or Not Settings")

    fact_types = sorted(questions_df["fact_type"].dropna().unique().tolist())

    selected_fact_types = st.multiselect(
        "Fact types",
        fact_types,
        default=fact_types,
        format_func=lambda x: FACT_TYPE_LABELS.get(x, x.replace("_", " ").title()),
    )

    max_difficulty = st.slider(
        "Question difficulty included",
        min_value=1,
        max_value=5,
        value=2,
        help="Only questions with difficulty less than or equal to this value are included.",
    )

    difficulty_level = st.selectbox(
        "HOT meter difficulty",
        options=list(DIFFICULTY_SETTINGS.keys()),
        format_func=lambda x: f"Level {x}: {DIFFICULTY_SETTINGS[x]['name']}",
        index=0,
    )

    round_length = st.slider(
        "Round length",
        min_value=5,
        max_value=50,
        value=20,
        step=5,
    )

    live_refresh = st.checkbox(
        "Live HOT meter refresh",
        value=HAS_AUTOREFRESH,
        disabled=not HAS_AUTOREFRESH,
        help=(
            "Requires streamlit-autorefresh. "
            "If disabled or unavailable, decay still works but updates mostly on interaction."
        ),
    )

    if not HAS_AUTOREFRESH:
        st.caption("Optional: `pip install streamlit-autorefresh` for live meter decay.")

    if st.button("Reset Hot or Not Progress"):
        for key in list(st.session_state.keys()):
            if key.startswith("hon_"):
                del st.session_state[key]
        init_global_state()
        st.rerun()


# Apply decay every rerun.
apply_decay()

# Optional live refresh while round is active.
if (
    HAS_AUTOREFRESH
    and live_refresh
    and st.session_state.get("hon_round_active", False)
    and not st.session_state.get("hon_round_complete", False)
):
    st_autorefresh(interval=1000, key="hon_live_refresh")


# Top metrics
render_xp_bar()

metric_cols = st.columns(4)
metric_cols[0].metric("Lifetime XP", st.session_state.get("hon_total_xp", 0))
metric_cols[1].metric("Current streak", st.session_state.get("hon_streak", 0))
metric_cols[2].metric("Rounds cleared", st.session_state.get("hon_lifetime_rounds", 0))

lifetime_answered = st.session_state.get("hon_lifetime_answered", 0)
lifetime_correct = st.session_state.get("hon_lifetime_correct", 0)
lifetime_accuracy = lifetime_correct / lifetime_answered if lifetime_answered else 0
metric_cols[3].metric("Lifetime accuracy", f"{lifetime_accuracy:.0%}")


# Start screen
if (
    not st.session_state.get("hon_round_active", False)
    and not st.session_state.get("hon_round_complete", False)
):
    st.markdown("### Start a round")

    available_df = questions_df[
        (questions_df["fact_type"].isin(selected_fact_types))
        & (questions_df["difficulty"] <= max_difficulty)
    ]

    eligible_count = 0
    for _, group in available_df.groupby("fact_type"):
        if group["correct_option"].nunique() >= 2:
            eligible_count += len(group)

    selected_count = eligible_count

    st.info(
        f"{selected_count} eligible questions available with the current filters. "
        f"Your round will use up to {round_length}."
    )

    difficulty = DIFFICULTY_SETTINGS[difficulty_level]
    st.write(
        f"**HOT meter level:** {difficulty['name']}  \n"
        f"Decay: `{difficulty['decay_rate']}` points/sec | "
        f"Correct: `+{difficulty['correct_bump']}` | "
        f"Wrong: `-{difficulty['wrong_penalty']}`"
    )

    if st.button("Start Round ▶", type="primary"):
        start_round(
            df=questions_df,
            selected_fact_types=selected_fact_types,
            max_difficulty=max_difficulty,
            round_length=round_length,
            difficulty_level=difficulty_level,
        )
        st.rerun()



# Active round
elif st.session_state.get("hon_round_active", False):
    render_hot_meter(st.session_state.get("hon_hot_meter", STARTING_HOT))

    questions = st.session_state.get("hon_round_questions", [])
    idx = st.session_state.get("hon_question_index", 0)
    total = len(questions)

    question = get_current_question()

    if question is None:
        st.session_state.hon_round_complete = True
        st.session_state.hon_round_active = False
        st.rerun()

    st.caption(f"Question {idx + 1} / {total}")

    st.markdown(
        f"""
        <div class="question-card">
            <div class="small-muted">{FACT_TYPE_LABELS.get(question["fact_type"], question["fact_type"].replace("_", " ").title())}</div>
            <div class="radionuclide">{question["radionuclide"]}</div>
            <div class="prompt-text">{question["prompt"]}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    options = get_shuffled_options(question)

    col1, col2 = st.columns(2)

    with col1:
        if st.button(options[0], key=f"hon_answer_{question['question_id']}_0"):
            apply_decay()
            submit_answer(options[0])
            st.rerun()

    with col2:
        if st.button(options[1], key=f"hon_answer_{question['question_id']}_1"):
            apply_decay()
            submit_answer(options[1])
            st.rerun()

    render_feedback()

    st.markdown("---")
    st.caption(
        "Tip: answer in under 3 seconds for a speed bonus. "
        "Streak multipliers start at 3, 6, and 10 correct in a row."
    )


# Completed round
elif st.session_state.get("hon_round_complete", False):
    render_hot_meter(st.session_state.get("hon_hot_meter", STARTING_HOT))
    render_feedback()
    render_round_summary()