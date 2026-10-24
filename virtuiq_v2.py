import re
import sqlite3
from datetime import datetime

import pandas as pd
import streamlit as st
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

APP_TITLE = "VIRTU-IQ V2"
DB_PATH = "virtuiq_history.db"

st.set_page_config(page_title=APP_TITLE, page_icon="⚽", layout="wide")
st.markdown("""
<style>
.block-container{max-width:1100px;padding-top:1rem}
.hero{background:linear-gradient(120deg,#a90020,#e21b3c);color:white;border-radius:18px;padding:22px;margin-bottom:16px}
.hero h1{margin:0}.hero p{margin:6px 0 0}
</style>
<div class="hero"><h1>⚽ VIRTU-IQ V2</h1>
<p>Instant Football screenshot reader · 1X2 odds analysis · prediction tracker</p></div>
""", unsafe_allow_html=True)

st.warning("Important: this version ranks outcomes from the odds you provide. It is not a trained virtual-football model, cannot see SportyBet's hidden engine, and cannot guarantee winners. A ranking score is NOT a win probability.")

def connect():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS predictions(
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, fixture TEXT,
        home TEXT, away TEXT, home_odds REAL, draw_odds REAL, away_odds REAL,
        pick TEXT, selection TEXT, odds REAL, market_probability REAL,
        ranking_score REAL, reason TEXT, actual_result TEXT DEFAULT '',
        settled INTEGER DEFAULT 0)""")
        con.commit()

init_db()

def valid_odds(x):
    try:
        return 1.0 < float(x) < 1000
    except (ValueError, TypeError):
        return False

def parse_ocr(text):
    rows = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        nums = re.findall(r"(?<!\w)(\d{1,2}\.\d{1,3})(?!\w)", line)
        if len(nums) < 3:
            continue
        try:
            h, d, a = map(float, nums[-3:])
        except ValueError:
            continue
        if not all(valid_odds(x) for x in (h, d, a)):
            continue
        names = line
        for n in nums:
            names = re.sub(r"(?<!\w)" + re.escape(n) + r"(?!\w)", " ", names)
        names = re.sub(r"\b\d{1,4}\b", " ", names)
        names = re.sub(r"\b(1X2|ODDS|HOME|DRAW|AWAY|ENGLAND|SPAIN|GERMANY|ITALY|FRANCE)\b", " ", names, flags=re.I)
        names = re.sub(r"[|•·:;,_\-–—]+", " ", names)
        names = re.sub(r"\s+", " ", names).strip()
        parts = re.split(r"\s+(?:VS?\.?|VERSUS)\s+", names, flags=re.I)
        if len(parts) >= 2:
            home, away = parts[0].strip(), parts[1].strip()
        else:
            words = names.split()
            if len(words) < 2:
                continue
            home, away = " ".join(words[:-1]), words[-1]
        if home and away and home.lower() != away.lower():
            rows.append({"Home team": home[:60], "Away team": away[:60],
                         "Home odds": h, "Draw odds": d, "Away odds": a})
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates()
    return df.reset_index(drop=True)

def analyse(h, d, a):
    odds = [float(h), float(d), float(a)]
    raw = [1 / x for x in odds]
    total = sum(raw)
    probs = [x / total for x in raw]
    labels = ["Home", "Draw", "Away"]
    i = max(range(3), key=lambda j: probs[j])
    ordered = sorted(probs, reverse=True)
    gap = ordered[0] - ordered[1]
    score = max(0, min(100, probs[i] * 75 + gap * 25))
    return labels[i], odds[i], probs[i], score, total - 1, gap

tabs = st.tabs(["📷 Scan & analyse", "📊 Prediction history", "ℹ️ How it works"])
with tabs[0]:
    st.subheader("1. Upload a SportyBet screenshot")
    upload = st.file_uploader("Choose a clear screenshot", type=["png", "jpg", "jpeg", "webp"])
    if upload:
        image = Image.open(upload).convert("RGB")
        st.image(image, caption="Uploaded screenshot", use_container_width=True)
        if st.button("🔎 Read screenshot (OCR)", type="primary"):
            try:
                import pytesseract
                processed = ImageOps.grayscale(image)
                processed = ImageEnhance.Contrast(processed).enhance(2.2)
                processed = ImageEnhance.Sharpness(processed).enhance(1.5).filter(ImageFilter.SHARPEN)
                text = pytesseract.image_to_string(processed, config="--psm 6")
                st.session_state["ocr_text"] = text
                st.session_state["ocr_rows"] = parse_ocr(text)
                st.session_state["ocr_ran"] = True
            except ImportError:
                st.error("Install OCR package with: !pip -q install pytesseract")
            except Exception as e:
                st.error("OCR engine may be missing. In Colab run: !apt-get -qq update && !apt-get -qq install -y tesseract-ocr && !pip -q install pytesseract. " + str(e))
    if st.session_state.get("ocr_ran"):
        with st.expander("Check OCR text"):
            st.text_area("Recognized text", st.session_state.get("ocr_text", ""), height=150)
        if isinstance(st.session_state.get("ocr_rows"), pd.DataFrame) and not st.session_state["ocr_rows"].empty:
            st.success(f"Possible fixture rows found: {len(st.session_state['ocr_rows'])}. Verify the odds carefully.")

    st.subheader("2. Verify or enter fixtures")
    st.caption("Correct the team names and all three decimal odds before analysing.")
    if "fixture_data" not in st.session_state:
        found = st.session_state.get("ocr_rows")
        st.session_state["fixture_data"] = found.copy() if isinstance(found, pd.DataFrame) and not found.empty else pd.DataFrame([{"Home team":"","Away team":"","Home odds":2.0,"Draw odds":3.2,"Away odds":3.5}])
    if st.session_state.get("ocr_ran") and st.session_state.get("loaded_ocr_text") != st.session_state.get("ocr_text"):
        found = st.session_state.get("ocr_rows")
        if isinstance(found, pd.DataFrame) and not found.empty:
            st.session_state["fixture_data"] = found.copy()
        st.session_state["loaded_ocr_text"] = st.session_state.get("ocr_text")
    edited = st.data_editor(st.session_state["fixture_data"], num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={
            "Home team": st.column_config.TextColumn(required=True),
            "Away team": st.column_config.TextColumn(required=True),
            "Home odds": st.column_config.NumberColumn(min_value=1.01, max_value=999.0, format="%.2f", required=True),
            "Draw odds": st.column_config.NumberColumn(min_value=1.01, max_value=999.0, format="%.2f", required=True),
            "Away odds": st.column_config.NumberColumn(min_value=1.01, max_value=999.0, format="%.2f", required=True)})
    st.session_state["fixture_data"] = edited.copy()
    n = st.slider("Maximum outcomes to display", 1, 5, 5)
    if st.button("⚡ Analyse fixtures", type="primary", use_container_width=True):
        df = edited.copy()
        for col in ["Home team", "Away team"]:
            df[col] = df[col].fillna("").astype(str).str.strip()
        for col in ["Home odds", "Draw odds", "Away odds"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df[(df["Home team"] != "") & (df["Away team"] != "")].dropna(subset=["Home odds","Draw odds","Away odds"])
        df = df[df[["Home odds","Draw odds","Away odds"]].apply(lambda row: all(valid_odds(x) for x in row), axis=1)]
        out = []
        for _, r in df.iterrows():
            pick, odds, prob, score, overround, gap = analyse(r["Home odds"], r["Draw odds"], r["Away odds"])
            selection = {"Home": r["Home team"], "Draw": "Draw", "Away": r["Away team"]}[pick]
            gap_pct = gap * 100
            uncertainty = ("the leader is clearly separated from the next option" if gap_pct >= 12 else
                           "the market shows a moderate gap" if gap_pct >= 5 else
                           "the top two outcomes are close; uncertainty is high")
            out.append({"Fixture": f"{r['Home team']} vs {r['Away team']}", "Home":r["Home team"],"Away":r["Away team"],
                "Home odds":float(r["Home odds"]),"Draw odds":float(r["Draw odds"]),"Away odds":float(r["Away odds"]),
                "Pick":pick,"Selection":selection,"Odds":odds,"Market implied %":round(prob*100,1),
                "Ranking score (not probability)":round(score,1),"Overround %":round(overround*100,1),
                "Reason":f"{pick} has the largest normalized share of the supplied 1X2 odds ({prob*100:.1f}%); {uncertainty}. This is not an independent prediction.",
                "_score":score,"_prob":prob})
        out.sort(key=lambda x:(x["_score"],x["_prob"]), reverse=True)
        st.session_state["results"] = out[:n]
        st.session_state["all_results"] = out
        st.session_state["analysed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if st.session_state.get("results"):
        results = st.session_state["results"]
        st.subheader("3. Ranked outcomes")
        st.caption("The ranking uses supplied odds; it does not mean the top pick is likely to win with that ranking score.")
        a,b,c = st.columns(3)
        a.metric("Fixtures analysed", len(st.session_state.get("all_results",[])))
        b.metric("Outcomes shown", len(results))
        c.metric("Analysed at", st.session_state.get("analysed_at",""))
        for i,r in enumerate(results,1):
            with st.container(border=True):
                left,right=st.columns([3,1])
                with left:
                    st.markdown(f"### #{i} · {r['Fixture']}")
                    st.markdown(f"**Selection: {r['Selection']}**")
                    st.write(f"Odds: **{r['Odds']:.2f}** · Market-implied share: **{r['Market implied %']:.1f}%**")
                    st.caption(r["Reason"])
                with right:
                    st.metric("Ranking score",f"{r['Ranking score (not probability)']:.1f}/100")
                    st.caption("Not a probability")
        export = pd.DataFrame(results).drop(columns=["_score","_prob"],errors="ignore")
        st.download_button("⬇️ Download analysis CSV", export.to_csv(index=False).encode(), "virtuiq_v2_analysis.csv","text/csv",use_container_width=True)
        if st.button("💾 Save these picks to history",use_container_width=True):
            with connect() as con:
                for r in results:
                    con.execute("""INSERT INTO predictions(created_at,fixture,home,away,home_odds,draw_odds,away_odds,pick,selection,odds,market_probability,ranking_score,reason)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (datetime.now().isoformat(timespec="seconds"),r["Fixture"],r["Home"],r["Away"],r["Home odds"],r["Draw odds"],r["Away odds"],r["Pick"],r["Selection"],r["Odds"],r["Market implied %"],r["Ranking score (not probability)"],r["Reason"]))
                con.commit()
            st.success(f"Saved {len(results)} picks. Record their actual results in Prediction history.")

with tabs[1]:
    st.subheader("Prediction history & performance")
    with connect() as con:
        hist = pd.read_sql_query("SELECT * FROM predictions ORDER BY id DESC",con)
    if hist.empty:
        st.info("No picks saved yet. Analyse fixtures and save them first.")
    else:
        settled = hist[hist["settled"] == 1]
        correct = int((settled["pick"] == settled["actual_result"]).sum())
        x1,x2,x3,x4=st.columns(4)
        x1.metric("Saved picks",len(hist)); x2.metric("Settled",len(settled)); x3.metric("Correct",correct)
        x4.metric("Observed hit rate",f"{correct/len(settled)*100:.1f}%" if len(settled) else "No settled picks")
        st.caption("Observed hit rate is historical only; it does not guarantee future performance.")
        st.dataframe(hist[["id","created_at","fixture","pick","odds","market_probability","actual_result","settled"]],use_container_width=True,hide_index=True)
        pending=hist[hist["settled"]==0]
        if not pending.empty:
            options={f"#{int(r.id)} · {r.fixture} · {r.pick} @ {r.odds:.2f}":int(r.id) for r in pending.itertuples()}
            chosen=st.selectbox("Choose a completed pick",list(options.keys()))
            actual=st.radio("Actual result",["Home","Draw","Away"],horizontal=True)
            if st.button("✅ Record actual result",type="primary"):
                with connect() as con:
                    con.execute("UPDATE predictions SET actual_result=?,settled=1 WHERE id=?",(actual,options[chosen]))
                    con.commit()
                st.rerun()
        st.download_button("⬇️ Export full history",hist.to_csv(index=False).encode(),"virtuiq_history.csv","text/csv",use_container_width=True)
        if st.button("Clear all saved history"):
            st.session_state["confirm_clear"] = True
        if st.session_state.get("confirm_clear"):
            st.warning("This deletes all prediction records in this app database.")
            yes,no=st.columns(2)
            if yes.button("Confirm delete",type="primary"):
                with connect() as con:
                    con.execute("DELETE FROM predictions"); con.commit()
                st.session_state["confirm_clear"]=False
                st.rerun()
            if no.button("Cancel"):
                st.session_state["confirm_clear"]=False
                st.rerun()

with tabs[2]:
    st.subheader("How this version works")
    st.markdown("""
- **Screenshot OCR:** attempts to read text. It can misread team abbreviations or decimal odds, so verify the table.
- **Market-implied share:** takes the reciprocal of each decimal odd and normalizes the three values so they add to 100%.
- **Ranking score:** combines the leading normalized share and its gap over the second outcome. It is a sorting score, not a calibrated probability.
- **Results tracker:** save picks, then record Home, Draw, or Away after each virtual match completes.
- **Not included yet:** no trained historical virtual-football model, no access to SportyBet's private engine, and no guarantee of results.

The next evidence-based improvement is to collect many records from the exact virtual product and test whether any patterns beat the odds baseline on unseen results.
""")
    st.info("Google Colab can run Python in your phone browser, but a Streamlit app needs a temporary public tunnel or hosted deployment to open as a web page. We can set up the phone steps after the code is ready.")

st.markdown("---")
st.caption("VIRTU-IQ V2 · Independent analysis tool. Gambling involves risk; never stake money you cannot afford to lose.")
