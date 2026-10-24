import unittest
from signaldesk.core import demo_extract, validate_item, priority

class SignalDeskTests(unittest.TestCase):
    def test_tentative_deadline_stays_textual(self):
        text = "We should try to finish the payment bug before Friday if possible."
        result = demo_extract(text)
        self.assertEqual(len(result["items"]), 1)
        item = result["items"][0]
        self.assertEqual(item["deadline_text"], "before Friday")
        self.assertIsNone(item["deadline_value"])
        self.assertEqual(item["deadline_certainty"], "tentative")
        self.assertLessEqual(item["confidence"], 0.7)

    def test_schedule_uncertainty_not_a_task(self):
        result = demo_extract("The release might move to Monday.")
        self.assertEqual(len(result["items"]), 0)
        self.assertEqual(len(result["schedule_signals"]), 1)

    def test_blocker_preserved(self):
        result = demo_extract("Ananya may check the payment bug, but she is waiting on the API team.")
        self.assertTrue(result["items"])
        self.assertIn("API team", result["items"][0]["blocked_by"])

    def test_priority_explained(self):
        item = {"source_text":"payment issue", "deadline_text":"before Friday",
                "deadline_value":None, "deadline_certainty":"tentative", "blocked_by":"API team"}
        result = priority(item)
        self.assertEqual(result["priority_score"], 47)
        self.assertIn("impact +20", result["priority_rationale"])
        self.assertIn("blocker +15", result["priority_rationale"])

    def test_evidence_validation(self):
        item = {"evidence_quote":"not in source", "owner_status":"unknown", "owner":None,
                "deadline_value":None, "deadline_certainty":"unknown", "commitment_level":"tentative",
                "confidence":0.5, "missing":[], "clarification_questions":[]}
        issues = validate_item(item, "Different source sentence.")
        self.assertTrue(any("not found verbatim" in issue for issue in issues))

    def test_pronoun_is_not_an_owner(self):
        item = demo_extract("We should try to finish the payment bug before Friday if possible.")["items"][0]
        self.assertIsNone(item["owner"])
        self.assertIn("confirmed_owner", item["missing"])

    def test_pilot_shift_is_schedule_signal(self):
        result = demo_extract("The pilot might shift to next week.")
        self.assertEqual(len(result["items"]), 0)
        self.assertEqual(len(result["schedule_signals"]), 1)

    def test_all_demo_scenarios_pass_validation(self):
        text = "Maya will prepare the launch FAQ by 2026-11-05. The mobile team is waiting on the analytics endpoint."
        for item in demo_extract(text)["items"]:
            self.assertEqual(validate_item(item, text), [])

if __name__ == "__main__":
    unittest.main()
