from __future__ import annotations
import json, os, sqlite3, uuid
from datetime import datetime
from pathlib import Path
import pandas as pd
import streamlit as st
from signaldesk.core import demo_extract, extract_with_ai, priority, validate_item

APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "signaldesk.db"
st.set_page_config(page_title="SignalDesk AI", page_icon="🧭", layout="wide", initial_sidebar_state="expanded")

def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS items (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, category TEXT, owner TEXT, owner_status TEXT,
        deadline_text TEXT, deadline_value TEXT, deadline_certainty TEXT, commitment_level TEXT,
        confidence REAL, confidence_reasons TEXT, blocked_by TEXT, source_text TEXT, evidence_quote TEXT,
        sentence_index INTEGER, missing TEXT, clarification_questions TEXT, priority_score INTEGER,
        priority_label TEXT, priority_rationale TEXT, status TEXT, review_note TEXT,
        created_at TEXT, updated_at TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT, item_id TEXT, action TEXT, detail TEXT, created_at TEXT
    )""")
    conn.commit()
    return conn

def log_activity(conn, item_id, action, detail=""):
    conn.execute("INSERT INTO activity(item_id,action,detail,created_at) VALUES(?,?,?,?)",
                 (item_id, action, detail, datetime.now().isoformat(timespec="seconds")))
    conn.commit()

def item_to_db(conn, item, status=None, note=None):
    now = datetime.now().isoformat(timespec="seconds")
    item = dict(item)
    if status is not None: item["status"] = status
    if note is not None: item["review_note"] = note
    item.setdefault("status", "Pending review")
    item.setdefault("review_note", "")
    for key in ("priority_score", "priority_label", "priority_rationale"):
        if key not in item: item.update(priority(item))
    vals = {
        "id": item.get("id") or str(uuid.uuid4())[:8], "title": item.get("title","Untitled item"),
        "category": item.get("category","Technology"), "owner": item.get("owner"), "owner_status": item.get("owner_status","unknown"),
        "deadline_text": item.get("deadline_text"), "deadline_value": item.get("deadline_value"),
        "deadline_certainty": item.get("deadline_certainty","unknown"), "commitment_level": item.get("commitment_level","unknown"),
        "confidence": float(item.get("confidence",0.5)), "confidence_reasons": json.dumps(item.get("confidence_reasons",[])),
        "blocked_by": item.get("blocked_by"), "source_text": item.get("source_text",""), "evidence_quote": item.get("evidence_quote",""),
        "sentence_index": int(item.get("sentence_index",0)), "missing": json.dumps(item.get("missing",[])),
        "clarification_questions": json.dumps(item.get("clarification_questions",[])), "priority_score": int(item.get("priority_score",0)),
        "priority_label": item.get("priority_label","Low"), "priority_rationale": item.get("priority_rationale",""),
        "status": item.get("status","Pending review"), "review_note": item.get("review_note",""),
        "created_at": now, "updated_at": now
    }
    cols = list(vals.keys())
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("id","created_at"))
    conn.execute(f"INSERT INTO items ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)}) ON CONFLICT(id) DO UPDATE SET {updates}",
                 [vals[c] for c in cols])
    conn.commit()
    return vals["id"]

def fetch_items(conn):
    rows = conn.execute("SELECT * FROM items ORDER BY CASE status WHEN 'Pending review' THEN 0 WHEN 'Approved' THEN 1 ELSE 2 END, priority_score DESC, updated_at DESC").fetchall()
    out=[]
    for row in rows:
        d=dict(row)
        for k in ("confidence_reasons","missing","clarification_questions"):
            try: d[k]=json.loads(d[k] or "[]")
            except Exception: d[k]=[]
        out.append(d)
    return out

def get_secret_key():
    try:
        return st.secrets.get("OPENAI_API_KEY", "")
    except Exception:  # no secrets file configured
        return ""

def metric(col, label, value, help=None):
    col.metric(label, value, help=help)

conn = db()
with st.sidebar:
    st.title("🧭 SignalDesk AI")
    st.caption("Evidence-first action intelligence")
    page = st.radio("Workspace", ["Overview", "Smart Intake", "Review Queue", "Task Board", "Bottleneck Radar", "Scenario Lab", "Activity & Export", "Settings"])
    st.divider()
    st.caption("Human approval stays in control. Nothing is sent to external systems.")
    st.caption("Local SQLite persistence")

items = fetch_items(conn)
pending = [i for i in items if i["status"] == "Pending review"]
ACTIVE_STATUSES = ("Approved", "In progress", "Done")
approved = [i for i in items if i["status"] in ACTIVE_STATUSES]
blocked = [i for i in items if i.get("blocked_by") and i["status"] != "Rejected"]

if page == "Overview":
    st.title("Your work, made actionable.")
    st.write("SignalDesk turns messy updates into evidence-linked actions, visible blockers, and decisions you can review before anything is accepted.")
    cols=st.columns(4)
    metric(cols[0],"Tracked items",len(items))
    metric(cols[1],"Awaiting review",len(pending))
    metric(cols[2],"Approved / active actions",len(approved))
    metric(cols[3],"Items with blockers",len(blocked))
    st.subheader("Priority snapshot")
    if items:
        df=pd.DataFrame([{"Action":i["title"],"Priority":i["priority_label"],"Score":i["priority_score"],"Owner":i["owner"] or "Unassigned","Status":i["status"],"Blocker":i["blocked_by"] or "—"} for i in items])
        st.dataframe(df, hide_index=True)
    else:
        st.info("No items yet. Open Smart Intake or load a scenario from Scenario Lab.")
    st.subheader("Operating principles")
    a,b,c=st.columns(3)
    a.markdown("**Evidence before inference**\n\nEvery item keeps the source text that supports it.")
    b.markdown("**Uncertainty is visible**\n\nTentative dates and owners are not silently promoted to facts.")
    c.markdown("**Human approval**\n\nReview, edit, approve, or reject before an item enters the active board.")

elif page == "Smart Intake":
    st.title("Smart Intake")
    st.write("Paste an email, meeting note, project update, or incident report. SignalDesk will identify candidate actions and preserve uncertainty.")
    category=st.selectbox("Context",["Technology","Healthcare","Operations","Customer support","General"])
    input_text=st.text_area("Source text", height=220, placeholder="Example: We should try to finish the payment bug before Friday if possible. Ananya may check it, but she is waiting on the API team. The release might move to Monday.")
    with st.expander("Optional real AI provider", expanded=False):
        st.write("Use an OpenAI-compatible Chat Completions API. The key is used only for this request and is not saved to the database.")
        use_ai=st.checkbox("Use real AI model for this intake", value=False)
        api_key=st.text_input("API key", type="password", help="For deployment, prefer Streamlit Secrets rather than typing a key here.")
        base_url=st.text_input("API base URL", value="https://api.openai.com/v1")
        model=st.text_input("Model name", value="gpt-4o-mini")
    if st.button("Extract candidate actions", type="primary", disabled=not input_text.strip()):
        try:
            with st.spinner("Reading source and checking evidence..."):
                if use_ai:
                    key=api_key or get_secret_key()
                    if not key: raise ValueError("Add an API key or set OPENAI_API_KEY in Streamlit Secrets.")
                    result=extract_with_ai(input_text, category, key, model, base_url)
                else:
                    result=demo_extract(input_text, category)
            st.session_state["last_extraction"]=result
            st.session_state["last_source"]=input_text
            st.session_state["last_category"]=category
        except Exception as e:
            st.error(f"Extraction failed: {e}")
    result=st.session_state.get("last_extraction")
    if result:
        st.success(f"Extraction complete · Engine: {result.get('engine','unknown')} · {len(result.get('items',[]))} candidate actions")
        st.warning(result.get("notice","Review all items before approval."))
        for sig in result.get("schedule_signals",[]):
            with st.container(border=True):
                st.markdown("**🗓️ Schedule signal — not a task**")
                st.write(sig.get("text"))
                st.caption(sig.get("note",""))
        for idx, item in enumerate(result.get("items",[])):
            with st.container(border=True):
                st.markdown(f"**{idx+1}. {item.get('title','Untitled')}**")
                st.caption(f"Priority: {item.get('priority_label','Unscored')} · Score {item.get('priority_score',0)} · Confidence {item.get('confidence',0):.0%}")
                st.markdown("**Evidence**")
                st.info(item.get("evidence_quote") or item.get("source_text") or "No evidence quote provided.")
                if item.get("validation_issues"): st.error("Validation flags: "+"; ".join(item["validation_issues"]))
                if item.get("missing"): st.warning("Missing: "+", ".join(item["missing"]))
                if item.get("clarification_questions"):
                    for q in item["clarification_questions"]: st.write("• "+q)
        if result.get("items") and st.button("Send candidates to Review Queue", type="primary"):
            count=0
            for item in result["items"]:
                item["id"]=f"item-{uuid.uuid4().hex[:8]}"  # unique per intake so earlier items are never overwritten
                item.setdefault("category", st.session_state.get("last_category","Technology"))
                item.setdefault("source_text", item.get("evidence_quote",""))
                item.setdefault("status","Pending review")
                item_to_db(conn,item,status="Pending review")
                log_activity(conn,item.get("id"),"Created candidate",f"Engine: {result.get('engine')}")
                count+=1
            st.success(f"Added {count} candidate(s) to the Review Queue.")
            st.rerun()

elif page == "Review Queue":
    st.title("Review Queue")
    st.write("Edit the extracted fields and review source evidence before approving.")
    queue=[i for i in items if i["status"]=="Pending review"]
    if not queue: st.info("The queue is clear. Use Smart Intake or Scenario Lab to add candidates.")
    for item in queue:
        with st.expander(f"{item['priority_label']} · {item['title']} · {item['id']}", expanded=True):
            st.markdown("**Source evidence**")
            st.info(item.get("evidence_quote") or item.get("source_text") or "No evidence supplied.")
            with st.form(f"review-{item['id']}"):
                title=st.text_input("Action title",value=item["title"])
                owner=st.text_input("Owner (leave blank if unknown)",value=item["owner"] or "")
                owner_status=st.selectbox("Owner confidence",["unknown","tentative","self_declared","confirmed"],index=["unknown","tentative","self_declared","confirmed"].index(item["owner_status"] if item["owner_status"] in ["unknown","tentative","self_declared","confirmed"] else "unknown"))
                deadline_text=st.text_input("Deadline as stated",value=item["deadline_text"] or "")
                deadline_value=st.text_input("Explicit ISO date (only if present in source)",value=item["deadline_value"] or "")
                deadline_certainty=st.selectbox("Deadline certainty",["unknown","textual","tentative","firm"],index=["unknown","textual","tentative","firm"].index(item["deadline_certainty"] if item["deadline_certainty"] in ["unknown","textual","tentative","firm"] else "unknown"))
                blocker=st.text_input("Blocker / dependency",value=item["blocked_by"] or "")
                note=st.text_area("Reviewer note",value=item["review_note"] or "")
                c1,c2,c3=st.columns(3)
                save=c1.form_submit_button("Save edits")
                approve=c2.form_submit_button("Approve action",type="primary")
                reject=c3.form_submit_button("Reject")
            if save or approve or reject:
                updated=dict(item)
                updated.update({"title":title.strip() or item["title"],"owner":owner.strip() or None,"owner_status":owner_status,
                                "deadline_text":deadline_text.strip() or None,"deadline_value":deadline_value.strip() or None,
                                "deadline_certainty":deadline_certainty,"blocked_by":blocker.strip() or None,"review_note":note})
                updated.update(priority(updated))
                validation=validate_item(updated,updated.get("source_text",""))
                if approve and validation:
                    st.error("Approval blocked by validation flags: "+"; ".join(validation))
                else:
                    new_status="Approved" if approve else "Rejected" if reject else "Pending review"
                    item_to_db(conn,updated,status=new_status,note=note)
                    log_activity(conn,item["id"],new_status if approve or reject else "Edited",note)
                    st.success("Changes saved." if save else f"Item {new_status.lower()}.")
                    st.rerun()
                if validation and save: st.warning("Validation flags: "+"; ".join(validation))

elif page == "Task Board":
    st.title("Task Board")
    st.write("Approved actions only (Approved, In progress, Done). This board is a local tracker; it does not execute work in other tools.")
    view=[i for i in items if i["status"] in ACTIVE_STATUSES]
    if not view: st.info("No approved actions yet. Review candidates first.")
    for item in view:
        with st.container(border=True):
            c1,c2=st.columns([4,1])
            c1.markdown(f"### {item['title']}")
            c1.caption(f"{item['priority_label']} priority · {item['priority_score']}/100 · {item['commitment_level']}")
            c1.write(f"Owner: {item['owner'] or 'Unassigned'} · Deadline: {item['deadline_text'] or 'Not set'}")
            c1.write(f"Blocker: {item['blocked_by'] or 'None recorded'}")
            with c2:
                newstatus=st.selectbox("Status",["Approved","In progress","Done"],index=["Approved","In progress","Done"].index(item["status"] if item["status"] in ["Approved","In progress","Done"] else "Approved"),key=f"status-{item['id']}")
                if st.button("Update status",key=f"update-{item['id']}"):
                    conn.execute("UPDATE items SET status=?,updated_at=? WHERE id=?",(newstatus,datetime.now().isoformat(timespec="seconds"),item["id"]))
                    conn.commit(); log_activity(conn,item["id"],"Status changed",newstatus); st.rerun()
            with st.expander("Evidence & rationale"):
                st.write(item["evidence_quote"] or item["source_text"])
                st.caption(item["priority_rationale"])

elif page == "Bottleneck Radar":
    st.title("Bottleneck Radar")
    st.write("Surface dependencies and missing information that could stall execution.")
    if not items: st.info("No work items yet.")
    else:
        radar=[]
        for i in items:
            if i["status"]=="Rejected": continue
            if i.get("blocked_by") or i.get("missing"):
                radar.append({"Action":i["title"],"Blocked by":i.get("blocked_by") or "Unspecified / missing detail",
                              "Missing information":", ".join(i.get("missing",[])) or "—","Status":i["status"],
                              "Suggested next step": "Ask dependency owner for ETA" if i.get("blocked_by") else "Clarify missing fields before commitment"})
        if radar: st.dataframe(pd.DataFrame(radar),hide_index=True)
        else: st.success("No recorded blockers or missing fields in current items.")
        st.subheader("Blocker concentration")
        blockers=[i.get("blocked_by") for i in items if i.get("blocked_by") and i["status"]!="Rejected"]
        if blockers:
            counts=pd.Series(blockers).value_counts().rename_axis("Dependency").reset_index(name="Items")
            st.bar_chart(counts.set_index("Dependency"))
        else: st.caption("Blocker chart appears when dependencies are recorded.")

elif page == "Scenario Lab":
    st.title("Scenario Lab")
    st.write("Load realistic fictional examples to demonstrate how the system handles ambiguity. Scenarios are examples, not real company data.")
    scenarios={
      "Ambiguous engineering update": "We should try to finish the payment bug before Friday if possible. Ananya may check it, but she is waiting on the API team. The release might move to Monday. Raj said he would investigate the timeout issue, although nobody confirmed whether it is the same bug.",
      "Healthcare operations handoff": "The clinic team needs to review the new patient check-in workflow by 2026-11-03. Dr. Mehta may validate the consent screen, but the privacy team is still reviewing the wording. The pilot might shift to next week. Operations will prepare the staff checklist.",
      "Product launch readiness": "Maya will prepare the launch FAQ by 2026-11-05. The mobile team is waiting on the analytics endpoint. We might move the launch review to Friday. Omar said he would check the crash report, but we have not confirmed whether it is related to the login issue."
    }
    selected=st.selectbox("Choose a scenario",list(scenarios.keys()))
    st.text_area("Scenario source",value=scenarios[selected],height=180,key="scenario_text")
    if st.button("Load scenario into Smart Intake",type="primary"):
        st.session_state["scenario_to_load"]=st.session_state.get("scenario_text",scenarios[selected])
        st.session_state["scenario_category"]="Healthcare" if selected.startswith("Healthcare") else "Technology"
        st.session_state["last_extraction"]=demo_extract(st.session_state["scenario_to_load"],st.session_state["scenario_category"])
        st.session_state["last_source"]=st.session_state["scenario_to_load"]
        st.session_state["last_category"]=st.session_state["scenario_category"]
        st.success("Scenario extracted. Open Smart Intake to inspect results and send them to review.")
    st.subheader("Scenario test checklist")
    st.markdown("- Does tentative wording remain tentative?\n- Are schedule changes kept out of the task list?\n- Is source evidence visible?\n- Are blockers preserved?\n- Are missing fields turned into questions?")

elif page == "Activity & Export":
    st.title("Activity & Export")
    log=pd.read_sql_query("SELECT * FROM activity ORDER BY created_at DESC",conn)
    if log.empty: st.info("Activity will appear as you create, review, and update items.")
    else: st.dataframe(log,hide_index=True)
    if items:
        export=[]
        for i in items:
            export.append({k:i.get(k) for k in ["id","title","category","owner","owner_status","deadline_text","deadline_value","deadline_certainty","commitment_level","confidence","blocked_by","source_text","evidence_quote","missing","clarification_questions","priority_score","priority_label","priority_rationale","status","review_note"]})
        csv=pd.DataFrame(export).to_csv(index=False).encode("utf-8")
        js=json.dumps(export,indent=2,ensure_ascii=False).encode("utf-8")
        c1,c2=st.columns(2)
        c1.download_button("Download CSV",csv,file_name="signaldesk_items.csv",mime="text/csv")
        c2.download_button("Download JSON",js,file_name="signaldesk_items.json",mime="application/json")
    else: st.caption("Add items to enable exports.")

elif page == "Settings":
    st.title("Settings & transparency")
    st.markdown("### Extraction modes")
    st.markdown("- **Demo rules:** deterministic, free, useful for demonstrating validation concepts. Not a general language understanding model.\n- **Real AI:** optional OpenAI-compatible Chat Completions endpoint. Requires your own API key and may incur provider charges.")
    st.markdown("### Data and privacy")
    st.markdown("- Items and activity are stored in a local SQLite database in the app directory.\n- Do not paste real patient information, credentials, or confidential company data into a demo.\n- API keys entered in Smart Intake are used for that request only and are not stored in the database.\n- The application does not send emails, create tickets, or execute external actions.")
    st.markdown("### Priority score")
    st.markdown("Impact keywords: +20 · explicit firm date: +30 · recorded blocker: +15. Scores are capped at 100. Tentative textual deadlines add at most +12. Weights are heuristic, explainable, and should be reviewed for each organization.")
    st.markdown("### Reset demo data")
    confirm=st.checkbox("I understand this permanently deletes local SignalDesk items and activity.")
    if st.button("Delete all local data",disabled=not confirm):
        conn.execute("DELETE FROM items"); conn.execute("DELETE FROM activity"); conn.commit()
        st.success("Local demo data deleted."); st.rerun()

conn.close()
