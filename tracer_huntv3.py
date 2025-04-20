# nucmed_trivia_app.py
"""
Nuclear Medicine Trivia Trainer – progress‑aware
------------------------------------------------
* Flashcards & MCQ: progress bar, balloons at 100 %.
* Match‑Up: dropdown matching with per‑cell ✅/❌, shuffle/retry.
* All state flags unified (`match_submitted`).
"""

from __future__ import annotations
import random
from typing import List, Dict
import pandas as pd
import streamlit as st

st.set_page_config(page_title="NucMed Trivia Trainer", page_icon="☢️", layout="centered")

# ---------------------------------------------------------------------
# Load CSV + stable row IDs
# ---------------------------------------------------------------------
@st.cache_data
def load_data(uploaded_file=None):
    df = pd.read_csv(uploaded_file) if uploaded_file else pd.read_csv(
        "radionuclides_radiopharmaceuticals_master.csv")
    df.columns = df.columns.str.strip()
    df = df.reset_index().rename(columns={"index": "__row_id"})
    return df

df = load_data(st.sidebar.file_uploader("⬆️ Upload a custom CSV (optional)", type="csv"))
columns: List[str] = [c for c in df.columns if df[c].notna().any()]
if df.empty:
    st.error("CSV is empty – please upload a valid file.")
    st.stop()

total_rows = len(df)

# ---------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------

def init_flash():
    st.session_state.deck = df.sample(frac=1).to_dict("records")
    st.session_state.qnum = 0

def next_flash():
    st.session_state.qnum = (st.session_state.qnum + 1) % len(st.session_state.deck)


def reset_mcq():
    st.session_state.mcq_submitted = False
    st.session_state.mcq_msg = ""
    st.session_state.mcq_type = "info"
    st.session_state.mcq_opts = {}


def init_match(shuffle=True):
    if shuffle or "match_rows" not in st.session_state:
        st.session_state.match_rows = df.sample(n=min(6, total_rows)).reset_index(drop=True)
    st.session_state.match_choice = {}
    st.session_state.match_submitted = False

# Global ledgers
st.session_state.setdefault("seen", {})          # mode_key -> set(row_ids)
st.session_state.setdefault("celebrated", set()) # balloons already shown

# Bootstrap
if "deck" not in st.session_state:
    init_flash(); reset_mcq(); init_match()

# ---------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------
game = st.sidebar.selectbox("Choose a game", ["Flashcards", "Multiple Choice", "Match‑Up"])
if st.sidebar.button("🔄 Reset All"):
    init_flash(); reset_mcq(); init_match(); st.session_state.seen = {}; st.session_state.celebrated = set()

# Helper: progress bar -------------------------------------------------

def show_progress(key):
    seen = len(st.session_state.seen.get(key, set()))
    val = min(seen / total_rows, 1.0)
    st.progress(val, text=f"Reviewed {seen}/{total_rows}")
    if val == 1.0:
        if key not in st.session_state.celebrated:
            st.session_state.celebrated.add(key)
            st.balloons(); st.success("🎉 Completed!")
        else:
            st.success("Completed ✔")

# ---------------------------------------------------------------------
# Flashcards
# ---------------------------------------------------------------------
if game == "Flashcards":
    st.header("Flashcards 🃏")
    front = st.sidebar.selectbox("Front field", columns, index=columns.index("Radiopharmaceutical ") if "Radiopharmaceutical " in columns else 0)
    backs = [c for c in columns if c != front]
    back = st.sidebar.selectbox("Back field", backs, index=backs.index("Uses") if "Uses" in backs else 0)

    key = ("flash", front, back)
    st.session_state.seen.setdefault(key, set())
    show_progress(key)

    card = st.session_state.deck[st.session_state.qnum]
    st.markdown(f"### **{card.get(front, 'N/A')}**")
    with st.expander("Show answer"):
        st.markdown(card.get(back, "—") or "—")

    if st.button("Next ▶"):
        st.session_state.seen[key].add(card["__row_id"])
        next_flash(); st.rerun()

# ---------------------------------------------------------------------
# Multiple Choice
# ---------------------------------------------------------------------
elif game == "Multiple Choice":
    st.header("Multiple Choice 🎯")
    col_q = st.sidebar.selectbox("Ask about", columns, index=columns.index("Radiopharmaceutical ") if "Radiopharmaceutical " in columns else 0)
    col_a = st.sidebar.selectbox("Identify", [c for c in columns if c != col_q], index=columns.index("Uses") if "Uses" in columns and col_q != "Uses" else 0)

    key = ("mcq", col_q, col_a)
    st.session_state.seen.setdefault(key, set())
    show_progress(key)

    row = st.session_state.deck[st.session_state.qnum]; rid = row["__row_id"]
    qkey = (rid, col_q, col_a)
    if qkey not in st.session_state.mcq_opts:
        correct = row.get(col_a, "")
        distract = df[col_a].dropna().loc[lambda s: s != correct].unique().tolist(); random.shuffle(distract)
        st.session_state.mcq_opts[qkey] = random.sample(distract, k=min(3, len(distract))) + [correct]
    opts = st.session_state.mcq_opts[qkey]

    st.markdown(f"**{col_q}:**"); st.markdown(row.get(col_q, ""))
    choice = st.radio("Choose", opts, key=f"mcq{rid}", disabled=st.session_state.mcq_submitted)

    if st.session_state.mcq_msg:
        (st.success if st.session_state.mcq_type == "success" else st.error)(st.session_state.mcq_msg)

    if not st.session_state.mcq_submitted and st.button("Submit ✅"):
        st.session_state.mcq_submitted = True
        st.session_state.seen[key].add(rid)
        if choice == row.get(col_a, ""):
            st.session_state.mcq_type = "success"; st.session_state.mcq_msg = "Correct!"
        else:
            st.session_state.mcq_type = "error"; st.session_state.mcq_msg = f"Incorrect. Correct: {row.get(col_a, '')}"
        st.rerun()
    elif st.session_state.mcq_submitted and st.button("Next ▶"):
        reset_mcq(); next_flash(); st.rerun()

# ---------------------------------------------------------------------
# MATCH‑UP  (unchanged logic, no progress bar—game has its own score)
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
        init_match(shuffle=True)
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
            
    st.info("Click Shuffle on the side bar to get a new batch to match!")

# ---------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------
st.markdown("""---  
Made with ❤️ & Streamlit.""")
