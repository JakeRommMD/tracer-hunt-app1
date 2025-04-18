# nucmed_trivia_app.py
"""
Nuclear Medicine Trivia Trainer
--------------------------------
Streamlit web app with three mini‑games to drill radiopharmaceutical factoids.

Mini‑games
===========
1. **Flashcards** – simple front/back reveal.
2. **Multiple Choice** – classic 4‑option quiz.
3. **Match‑Up** – interactive matching of 1–3 columns with shuffle, retry,
   colour feedback per cell, non‑wrapping & padded row labels, and stable
   dropdowns that work across reruns.

Quick start
-----------
```bash
pip install streamlit pandas
streamlit run nucmed_trivia_app.py
```
"""

from __future__ import annotations
import random
from typing import List, Dict

import pandas as pd
import streamlit as st

st.set_page_config(page_title="NucMed Trivia Trainer", page_icon="☢️", layout="centered")

# ---------------------------------------------------------------------
# Load CSV
# ---------------------------------------------------------------------
@st.cache_data
def load_data(uploaded_file=None):
    df = pd.read_csv(uploaded_file) if uploaded_file else pd.read_csv("radionuclides_radiopharmaceuticals_master.csv")
    df.columns = df.columns.str.strip()
    return df

df = load_data(st.sidebar.file_uploader("⬆️ Upload a custom CSV (optional)", type="csv"))
columns: List[str] = [c for c in df.columns if df[c].notna().any()]
if df.empty:
    st.error("CSV appears empty – please upload a valid file.")
    st.stop()

# ---------------------------------------------------------------------
# Session‑state helpers
# ---------------------------------------------------------------------

def init_flashcards():
    st.session_state.deck = df.sample(frac=1).to_dict("records")
    st.session_state.qnum = 0

def next_flashcard():
    st.session_state.qnum = (st.session_state.qnum + 1) % len(st.session_state.deck)


def reset_mcq():
    st.session_state.mcq_submitted = False
    st.session_state.mcq_feedback_msg = ""
    st.session_state.mcq_feedback_type = "info"
    st.session_state.mcq_option_bank = {}
    st.session_state.score = 0


def init_match(shuffle_rows: bool = True):
    if shuffle_rows or "match_rows" not in st.session_state:
        st.session_state.match_rows = df.sample(n=min(6, len(df))).reset_index(drop=True)
    st.session_state.match_choice = {}   # (row_idx, col) -> choice
    st.session_state.match_submitted = False

# bootstrap state once -------------------------------------------------
if "deck" not in st.session_state:
    init_flashcards()
if "mcq_submitted" not in st.session_state:
    reset_mcq()
if "match_rows" not in st.session_state:
    init_match()

# ---------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------
GAME_TYPES = ["Flashcards", "Multiple Choice", "Match‑Up"]

st.sidebar.title("⚡ Game Controls")
game_type = st.sidebar.selectbox("Choose a game", GAME_TYPES)

if st.sidebar.button("🔄 Reset All"):
    init_flashcards()
    reset_mcq()
    init_match()

st.sidebar.markdown(f"**MCQ Score:** {st.session_state.get('score', 0)}")

# ---------------------------------------------------------------------
# FLASHCARDS
# ---------------------------------------------------------------------
if game_type == "Flashcards":
    st.header("Flashcards 🃏")
    front = st.sidebar.selectbox("Field on the front:", columns,
                                 index=columns.index("Radiopharmaceutical ") if "Radiopharmaceutical " in columns else 0)
    back_opts = [c for c in columns if c != front]
    back = st.sidebar.selectbox("Field on the back:", back_opts,
                                index=back_opts.index("Uses") if "Uses" in back_opts else 0)

    card = st.session_state.deck[st.session_state.qnum]
    st.markdown(f"### **{card.get(front, 'N/A')}**")
    with st.expander("Show Answer"):
        st.markdown(card.get(back, "—") or "—")
    st.button("Next ▶", on_click=next_flashcard)

# ---------------------------------------------------------------------
# MULTIPLE CHOICE
# ---------------------------------------------------------------------
elif game_type == "Multiple Choice":
    st.header("Multiple Choice 🎯")
    col_q = st.sidebar.selectbox("Ask about:", columns,
                                 index=columns.index("Radiopharmaceutical ") if "Radiopharmaceutical " in columns else 0)
    col_a = st.sidebar.selectbox("Identify:", [c for c in columns if c != col_q],
                                 index=columns.index("Uses") if "Uses" in columns and col_q != "Uses" else 0)

    qkey = (st.session_state.qnum, col_q, col_a)
    if qkey not in st.session_state.mcq_option_bank:
        row = st.session_state.deck[st.session_state.qnum]
        correct = row.get(col_a, "")
        distractors = df[col_a].dropna().loc[lambda s: s != correct].unique().tolist()
        random.shuffle(distractors)
        options = distractors[:3] + [correct]
        random.shuffle(options)
        st.session_state.mcq_option_bank[qkey] = {"options": options, "answer": correct}

    options = st.session_state.mcq_option_bank[qkey]["options"]
    correct = st.session_state.mcq_option_bank[qkey]["answer"]
    row = st.session_state.deck[st.session_state.qnum]

    st.markdown(f"**{col_q}:**  ")
    st.markdown(row.get(col_q, ""))

    choice = st.radio("Select the correct answer:", options,
                      key=f"mcq_choice_{st.session_state.qnum}",
                      disabled=st.session_state.mcq_submitted)

    if st.session_state.mcq_feedback_msg:
        (st.success if st.session_state.mcq_feedback_type == "success" else st.error)(st.session_state.mcq_feedback_msg)

    if not st.session_state.mcq_submitted and st.button("Submit ✅"):
        st.session_state.mcq_submitted = True
        if choice == correct:
            st.session_state.score += 1
            st.session_state.mcq_feedback_type = "success"
            st.session_state.mcq_feedback_msg = "Correct!"
        else:
            st.session_state.mcq_feedback_type = "error"
            st.session_state.mcq_feedback_msg = f"Incorrect. **Correct answer:** {correct}"
        st.rerun()
    elif st.session_state.mcq_submitted and st.button("Next ▶"):
        next_flashcard()
        reset_mcq()
        st.rerun()

# ---------------------------------------------------------------------
# MATCH‑UP
# ---------------------------------------------------------------------
else:
    st.header("Match‑Up 🧩")

    base_col = st.sidebar.selectbox("Rows show:", columns,
                                    index=columns.index("Radiopharmaceutical ") if "Radiopharmaceutical " in columns else 0)

    target_cols = st.sidebar.multiselect(
        "Match with (1‑3):",
        [c for c in columns if c != base_col],
        default=[c for c in ["Mechanism of Localization"] if c in columns][:1],
        max_selections=3,
    )

    if st.sidebar.button("Shuffle 🔀"):
        init_match(shuffle_rows=True)
        # also reset pools so they reshuffle once
        st.session_state.pop("match_answer_pools", None)

    if not target_cols:
        st.info("Select at least one ‘Match with’ column.")
        st.stop()

    # ---------- stable answer pools ------------------------------------- #
    if (
        "match_answer_pools" not in st.session_state
        or set(st.session_state.match_answer_pools.keys()) != set(target_cols)
    ):
        st.session_state.match_answer_pools = {
            c: random.sample(df[c].dropna().astype(str).unique().tolist(),
                             k=len(df[c].dropna().unique()))
            for c in target_cols
        }
    answer_pools: Dict[str, List[str]] = st.session_state.match_answer_pools

    # ---------- header --------------------------------------------------- #
    widths = [3] + [2] * len(target_cols)   # extra width for first col
    hcols = st.columns(widths)
    hcols[0].markdown(f"### {base_col}")
    for i, tc in enumerate(target_cols, 1):
        hcols[i].markdown(f"### {tc}")

    # ---------- rows ----------------------------------------------------- #
    for idx, row in st.session_state.match_rows.iterrows():
        cols_stream = st.columns(widths)
        base_text = str(row[base_col]) if pd.notna(row[base_col]) else ""
        cols_stream[0].markdown(
            f"<div style='padding:4px 16px 4px 0; white-space: nowrap;'>{base_text}</div>",
            unsafe_allow_html=True,
        )
        for j, tcol in enumerate(target_cols, 1):
            key = (idx, tcol)
            default_val = st.session_state.match_choice.get(key, "Select")
            display_pool = ["Select"] + answer_pools[tcol]
            choice = cols_stream[j].selectbox(
                label=f"{idx}-{tcol}",
                options=display_pool,
                index=display_pool.index(default_val) if default_val in display_pool else 0,
                key=f"match_{idx}_{tcol}",
                label_visibility="collapsed",
            )
            st.session_state.match_choice[key] = choice

            # feedback icon ------------------------------------------------ #
            if st.session_state.match_submitted:
                real_ans_series = df.loc[df[base_col] == row[base_col], tcol].dropna()
                real_ans = str(real_ans_series.iloc[0]) if not real_ans_series.empty else ""
                icon = "✅" if choice == real_ans else "❌"
                cols_stream[j].markdown(icon)

    # ---------- buttons & score ---------------------------------------- #
    if not st.session_state.match_submitted:
        if st.button("Check Answers ✅"):
            st.session_state.match_submitted = True
            st.rerun()
    else:
        total_cells = len(st.session_state.match_rows) * len(target_cols)
        correct_cells = 0
        for idx, row in st.session_state.match_rows.iterrows():
            for tcol in target_cols:
                key = (idx, tcol)
                user_ans = st.session_state.match_choice.get(key, "Select")
                real_ans_series = df.loc[df[base_col] == row[base_col], tcol].dropna()
                real_ans = str(real_ans_series.iloc[0]) if not real_ans_series.empty else ""
                if user_ans == real_ans:
                    correct_cells += 1
        st.success(f"Score: {correct_cells} / {total_cells}")
        if st.button("Retry 🔄"):
            init_match(shuffle_rows=False)
            st.rerun()

# ---------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------
st.markdown("""---  
Made with ❤️ & Streamlit.""")
