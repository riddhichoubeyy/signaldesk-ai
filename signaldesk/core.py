from __future__ import annotations
import json, re
from datetime import datetime, date
from typing import Any

HEDGE_RE = re.compile(r"\b(may|might|could|possibly|perhaps|if possible|should try|try to|hope to|tentative|potentially)\b", re.I)
REPORTED_RE = re.compile(r"\b(said|told us|reported|mentioned|plans to|would)\b", re.I)
WAITING_RE = re.compile(r"\b(waiting on|blocked by|depends on|dependent on|awaiting|pending)\b", re.I)
SCHEDULE_RE = re.compile(r"\b(release|launch|deployment|schedule|timeline|ship date|pilot|go-live)\b.*\b(may|might|could|move|slip|delay|shift|push|postpone)\b|\b(may|might|could)\b.*\b(release|launch|deployment|schedule|timeline|pilot|go-live)\b", re.I)
DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2}|\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+20\d{2})\b", re.I)
NOT_NAMES = {"We", "They", "It", "He", "She", "You", "I", "This", "That", "There", "The", "Someone", "Everyone"}
NAME_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b")

def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text.strip()) if s.strip()]

def evidence(text: str, sentence_index: int) -> dict:
    return {"quote": text, "sentenceIndex": sentence_index}

def priority(item: dict) -> dict:
    source = item.get("source_text", "")
    impact = 20 if re.search(r"\b(payment|security|outage|production|customer|critical|data loss)\b", source, re.I) else 0
    deadline = 0
    deadline_text = (item.get("deadline_text") or "").lower()
    if item.get("deadline_value") and item.get("deadline_certainty") == "firm":
        deadline = 30
    elif deadline_text and item.get("deadline_certainty") == "tentative":
        deadline = 12
    blocker = 15 if item.get("blocked_by") else 0
    score = min(100, impact + deadline + blocker)
    label = "High" if score >= 50 else "Medium" if score >= 25 else "Low"
    reasons = []
    reasons.append(f"impact +{impact} ({'impact keyword detected' if impact else 'no impact keyword detected'})")
    reasons.append(f"deadline +{deadline} ({'explicit firm date' if deadline == 30 else 'tentative textual deadline' if deadline == 12 else 'no established deadline'})")
    reasons.append(f"blocker +{blocker} ({'blocked by another team/person' if blocker else 'no blocker recorded'})")
    return {"priority_score": score, "priority_label": label, "priority_rationale": "; ".join(reasons)}

def demo_extract(text: str, category: str = "Technology") -> dict:
    """Transparent rule-based demo. This is not a general-purpose language model."""
    sentences = split_sentences(text)
    items = []
    schedule_signals = []
    for idx, sent in enumerate(sentences):
        if SCHEDULE_RE.search(sent):
            schedule_signals.append({"text": sent, "evidence_quote": sent, "sentence_index": idx,
                                     "note": "Schedule uncertainty detected; not converted into a task."})
            continue
        # Extract action-like clauses. Keep one item per sentence in demo mode to avoid inventing.
        m = re.search(r"\b(?:need to|needs to|must|will|should|should try to|try to|finish|fix|investigate|review|check|build|create|test|deploy|update|send|prepare|analyze|analyse|resolve|complete|document|validate)\b.+", sent, re.I)
        if not m:
            continue
        title = sent.strip().rstrip(".")
        title = re.sub(r"^(we should try to|we should|we need to|we must|we will|please|i will|i should)\s+", "", title, flags=re.I)
        title = title[:140] or sent[:140]
        if title[0].islower(): title = title[0].upper()+title[1:]
        hedged = bool(HEDGE_RE.search(sent))
        reported = bool(REPORTED_RE.search(sent))
        commitment = "reported_intent" if reported else "tentative" if hedged else "committed"
        # Owner is only confirmed when explicitly assigned, not merely mentioned.
        owner = None
        owner_status = "unknown"
        owner_ev = None
        assigned = re.search(r"\b(?:assigned to|owner is|owned by)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", sent)
        will = re.search(r"\b([A-Z][a-z]+)\s+will\s+", sent)
        said = re.search(r"\b([A-Z][a-z]+)\s+said\s+(?:they|he|she)\s+would\b", sent, re.I)
        may = re.search(r"\b([A-Z][a-z]+)\s+(?:may|might|could|should)\s+", sent)
        if will and will.group(1) in NOT_NAMES: will = None
        if may and may.group(1) in NOT_NAMES: may = None
        if assigned and not hedged:
            owner, owner_status, owner_ev = assigned.group(1), "confirmed", sent
        elif will and not hedged:
            owner, owner_status, owner_ev = will.group(1), "confirmed", sent
        elif said:
            owner, owner_status, owner_ev = said.group(1), "self_declared", sent
        elif may:
            owner, owner_status, owner_ev = may.group(1), "tentative", sent
        deadline_text, deadline_value, deadline_certainty, deadline_ev = None, None, "unknown", None
        date_match = DATE_RE.search(sent)
        if date_match:
            raw = date_match.group(1)
            try:
                if re.match(r"20\d{2}-", raw):
                    parsed = date.fromisoformat(raw)
                else:
                    parsed = datetime.strptime(raw, "%d %B %Y" if len(raw.split()[1]) > 3 else "%d %b %Y").date()
                deadline_value = parsed.isoformat()
                deadline_text, deadline_certainty, deadline_ev = raw, ("tentative" if hedged else "firm"), sent
            except Exception:
                deadline_text, deadline_certainty, deadline_ev = raw, ("tentative" if hedged else "firm"), sent
        else:
            rel = re.search(r"\b(before|by|until|on|next|this)\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|week|month|morning|afternoon|EOD)\b", sent, re.I)
            if rel:
                deadline_text = rel.group(0)
                deadline_certainty = "tentative" if hedged else "textual"
                deadline_ev = sent
        blocker = None
        if WAITING_RE.search(sent):
            bm = re.search(r"\b(?:waiting on|blocked by|depends on|dependent on|awaiting|pending)\s+(?:the\s+)?(.+?)(?:[,.]|$)", sent, re.I)
            blocker = bm.group(1).strip() if bm else "Unspecified dependency"
        missing = []
        questions = []
        if not owner or owner_status in ("tentative", "self_declared"):
            missing.append("confirmed_owner")
            questions.append("Who is the confirmed owner for this item?")
        if not deadline_text:
            missing.append("deadline")
            questions.append("Is there a target deadline for this item?")
        if blocker and re.search(r"\b(waiting on|blocked by|depends on|awaiting)\s+(?:the\s+)?(?:API|platform|data|security|design|backend|frontend)\s+team\b", sent, re.I):
            missing.append("blocker_eta")
            questions.append("When is the dependency expected to be resolved?")
        item = {
            "id": f"item-{len(items)+1}", "title": title, "category": category,
            "owner": owner, "owner_status": owner_status, "owner_evidence": owner_ev,
            "deadline_text": deadline_text, "deadline_value": deadline_value,
            "deadline_certainty": deadline_certainty, "deadline_evidence": deadline_ev,
            "commitment_level": commitment, "confidence": 0.55 if hedged or reported else 0.72,
            "confidence_reasons": (["hedged wording detected"] if hedged else []) + (["reported intent detected"] if reported else []),
            "blocked_by": blocker, "source_text": sent, "evidence_quote": sent,
            "sentence_index": idx, "missing": missing, "clarification_questions": questions,
            "status": "Pending review", "review_note": ""
        }
        item.update(priority(item))
        items.append(item)
    return {"items": items, "schedule_signals": schedule_signals, "engine": "demo-rules",
            "notice": "Demo mode uses transparent rules, not a general-purpose AI model. Review every extracted item before approving."}

def validate_item(item: dict, all_source: str) -> list[str]:
    issues = []
    quote = item.get("evidence_quote") or ""
    if quote and quote not in all_source:
        issues.append("Evidence quote is not found verbatim in the source.")
    if item.get("owner_status") == "confirmed" and item.get("owner") and item["owner"] not in all_source:
        issues.append("Confirmed owner does not appear in the source.")
    if item.get("deadline_value") and item["deadline_value"] not in quote:
        issues.append("Calendar date is not explicitly present in its evidence quote.")
    if item.get("deadline_certainty") == "firm" and HEDGE_RE.search(quote):
        issues.append("Firm deadline is based on tentative language.")
    if item.get("commitment_level") == "committed" and (HEDGE_RE.search(quote) or REPORTED_RE.search(quote)):
        issues.append("Committed status conflicts with hedged or reported wording.")
    if item.get("confidence", 0) > .7 and (HEDGE_RE.search(quote) or REPORTED_RE.search(quote)):
        issues.append("Confidence is too high for hedged or reported wording.")
    if item.get("missing") and len(item.get("clarification_questions", [])) < len(item.get("missing", [])):
        issues.append("Some missing fields have no clarification question.")
    return issues

def extract_with_ai(text: str, category: str, api_key: str, model: str, base_url: str = "https://api.openai.com/v1") -> dict:
    """Optional OpenAI-compatible Chat Completions call. API key is supplied at runtime and never persisted."""
    import requests
    from .prompts import EXTRACTION_PROMPT
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": EXTRACTION_PROMPT},
            {"role": "user", "content": json.dumps({"category": category, "input": text}, ensure_ascii=False)}
        ]
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I)
    parsed = json.loads(content)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("items"), list):
        raise ValueError("Model response must be a JSON object containing an items list.")
    for i, item in enumerate(parsed["items"], 1):
        item.setdefault("id", f"item-{i}")
        item.setdefault("category", category)
        item.setdefault("source_text", item.get("evidence_quote", ""))
        item.setdefault("status", "Pending review")
        item.setdefault("review_note", "")
        item.setdefault("missing", [])
        item.setdefault("clarification_questions", [])
        item.setdefault("confidence", 0.5)
        item.setdefault("commitment_level", "tentative")
        item.setdefault("blocked_by", None)
        item.setdefault("deadline_text", None)
        item.setdefault("deadline_value", None)
        item.setdefault("deadline_certainty", "unknown")
        item.setdefault("owner_status", "unknown")
        item.setdefault("owner", None)
        item.setdefault("evidence_quote", "")
        item.setdefault("sentence_index", 0)
        item.setdefault("confidence_reasons", [])
        item.update(priority(item))
        item["validation_issues"] = validate_item(item, text)
    parsed.setdefault("schedule_signals", [])
    parsed["engine"] = f"model:{model}"
    parsed["notice"] = "AI-assisted extraction. Evidence and validation checks are advisory; review all output before approval."
    return parsed
