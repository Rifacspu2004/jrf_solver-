"""
Unit and Integration Test Suite for UGC NET JRF Solver Multi-Key Engine
"""

import os
import time
import unittest
from unittest.mock import MagicMock, patch
from solver_core import (
    chunk_text,
    chunk_pdf_text,
    deduplicate_solutions,
    extract_text_from_pdf,
    question_numbers_in_text,
    process_single_pdf,
    save_checkpoint,
    load_checkpoint,
    request_stop,
    clear_stop_request,
    is_stop_requested,
    MultiKeyManager,
    KeyHealth,
    call_openrouter,
)
from export_utils import (
    convert_to_dataframe,
    generate_markdown_study_notes,
    generate_pdf_study_guide,
)

class TestSolverMultiKeyEngine(unittest.TestCase):
    def setUp(self):
        self.test_json = "test_output.json"
        clear_stop_request()

    def tearDown(self):
        if os.path.exists(self.test_json):
            os.remove(self.test_json)
        if os.path.exists(self.test_json + ".tmp"):
            os.remove(self.test_json + ".tmp")
        clear_stop_request()

    def test_multi_key_rotation_and_failover(self):
        km = MultiKeyManager()
        gemini_keys = ["gemini_key_1", "gemini_key_2", "gemini_key_3"]
        groq_keys = ["groq_key_1", "groq_key_2"]
        km.update_keys(gemini_keys=gemini_keys, groq_keys=groq_keys, openrouter_keys=[])

        self.assertEqual(km.total_keys(), 5)

        # First key should be gemini_key_1
        candidate, idx = km.get_candidate_key()
        self.assertEqual(candidate.key, "gemini_key_1")
        self.assertEqual(idx, 1)

        # Mark key 1 failed with 60s cooldown
        km.mark_key_failed(candidate, cooldown_seconds=60.0)

        # Next call should automatically fail over to key 2
        candidate2, idx2 = km.get_candidate_key()
        self.assertEqual(candidate2.key, "gemini_key_2")
        self.assertEqual(idx2, 2)

        # Mark key 2 success - should rotate to key 3 next
        km.mark_key_success(candidate2)
        self.assertEqual(candidate2.success_count, 1)

        # Alternating check: next candidate should be key 3
        candidate3, idx3 = km.get_candidate_key()
        self.assertEqual(candidate3.key, "gemini_key_3")
        self.assertEqual(idx3, 3)

    def test_chunking_with_overlap(self):
        text = "A" * 9000
        chunks = chunk_text(text, chunk_size=4000, overlap=300)
        self.assertTrue(len(chunks) >= 3)
        for c in chunks:
            self.assertLessEqual(len(c), 4000)

    def test_deduplication(self):
        duplicate_data = [
            {"question_number": 1, "question_text": "What is Dijkstra?", "correct_option": "Option 2"},
            {"question_number": 1, "question_text": "What is Dijkstra?", "correct_option": "Option 2"},
            {"question_number": 1, "question_text": "What is 4NF?", "correct_option": "Option 4"}
        ]
        unique = deduplicate_solutions(duplicate_data)
        self.assertEqual(len(unique), 2)

    def test_pdf_chunking_keeps_question_boundaries(self):
        text = (
            "--- [Page 1] ---\n"
            "1. " + ("First question text " * 3) + "\n(A) one\n(B) two\n"
            "2. " + ("Second question text " * 3) + "\n(A) three\n(B) four"
        )
        chunks = chunk_pdf_text(text, chunk_size=100)
        self.assertEqual(len(chunks), 2)
        self.assertIn("1.", chunks[0])
        self.assertNotIn("2.", chunks[0])
        self.assertIn("2.", chunks[1])

    def test_pdf_chunking_skips_instructions_and_accepts_quoted_question_text(self):
        text = (
            "--- [Page 2] ---\nInstructions for the Candidates\n"
            "1. Write your roll number here.\n"
            "--- [Page 3] ---\n"
            "58. “If X, then Y unless Z” is represented by which formula?\n"
            "(1) Option one\n(2) Option two\n"
            "59. Which statement is correct?\n"
            "(1) Option three\n(2) Option four"
        )
        chunks = chunk_pdf_text(text, chunk_size=200)
        combined = "\n".join(chunks)
        self.assertNotIn("Instructions for the Candidates", combined)
        self.assertTrue(any("58." in chunk for chunk in chunks))
        self.assertTrue(any("59." in chunk for chunk in chunks))

    def test_failed_chunk_is_retryable_and_not_completed(self):
        pdf_text = "--- [Page 1] ---\n1. Which option is correct?"
        answer = {
            "question_number": "1",
            "question_text": "Which option is correct?",
            "correct_option": "A",
            "explanation": "Option A follows from the stated condition.",
        }
        key_manager = MultiKeyManager()
        with patch("solver_core.extract_text_from_pdf", return_value=pdf_text), patch(
            "solver_core.dispatch_with_multi_key_failover",
            side_effect=[RuntimeError("temporary API failure"), [answer]],
        ) as dispatch:
            entry = process_single_pdf(
                "paper.pdf",
                key_manager,
                chunk_size=1000,
                inter_request_delay=0,
            )
            self.assertEqual(entry["status"], "failed")
            self.assertEqual(entry["processed_chunks"], [])
            self.assertIn("0", entry["failed_chunks"])

            entry = process_single_pdf(
                "paper.pdf",
                key_manager,
                chunk_size=1000,
                inter_request_delay=0,
                existing_entry=entry,
            )

        self.assertEqual(dispatch.call_count, 2)
        self.assertEqual(entry["status"], "completed")
        self.assertEqual(entry["processed_chunks"], [0])
        self.assertEqual(entry["solutions"], [answer])

    def test_incomplete_model_response_does_not_complete_chunk(self):
        pdf_text = (
            "--- [Page 1] ---\n"
            "1. First question?\n(1) A\n(2) B\n"
            "2. Second question?\n(1) C\n(2) D"
        )
        answer = {
            "question_number": "1",
            "question_text": "First question?",
            "correct_option": "A",
            "explanation": "The condition identifies A.",
        }
        with patch("solver_core.extract_text_from_pdf", return_value=pdf_text), patch(
            "solver_core.dispatch_with_multi_key_failover",
            return_value=[answer],
        ):
            entry = process_single_pdf(
                "paper.pdf",
                MultiKeyManager(),
                chunk_size=1000,
                inter_request_delay=0,
            )

        self.assertEqual(entry["status"], "failed")
        self.assertEqual(entry["processed_chunks"], [])
        self.assertIn("2", entry["failed_chunks"]["0"])

    def test_legacy_solutions_are_archived_during_reprocessing(self):
        old_solution = {"question_number": "3w", "question_text": "Corrupted extracted question"}
        new_solution = {
            "question_number": "1",
            "question_text": "Which option is correct?",
            "correct_option": "A",
            "explanation": "The stated condition implies A.",
        }
        existing_entry = {
            "filename": "paper.pdf",
            "status": "completed",
            "processed_chunks": [0],
            "total_chunks": 1,
            "solutions": [old_solution],
        }
        with patch(
            "solver_core.extract_text_from_pdf",
            return_value="--- [Page 1] ---\n1. Which option is correct?",
        ), patch(
            "solver_core.dispatch_with_multi_key_failover",
            return_value=[new_solution],
        ):
            entry = process_single_pdf(
                "paper.pdf",
                MultiKeyManager(),
                chunk_size=1000,
                inter_request_delay=0,
                existing_entry=existing_entry,
            )

        self.assertEqual(entry["status"], "completed")
        self.assertEqual(entry["solutions"], [new_solution])
        self.assertEqual(entry["legacy_solutions"], [old_solution])

    def test_pause_resume_signal(self):
        self.assertFalse(is_stop_requested())
        request_stop()
        self.assertTrue(is_stop_requested())
        clear_stop_request()
        self.assertFalse(is_stop_requested())

    def test_pdf_study_guide_export(self):
        dataset = [{
            "filename": "sample.pdf",
            "solutions": [{
                "question_number": 1,
                "question_text": "What is 2 + 2?",
                "options": {"A": "3", "B": "4"},
                "correct_option": "B",
                "explanation": "Adding two and two gives four.",
            }],
        }]
        pdf = generate_pdf_study_guide(dataset)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 1000)

    def test_openrouter_uses_configured_api_key(self):
        response = MagicMock()
        response.json.return_value = {"choices": [{"message": {"content": "[]"}}]}
        client = MagicMock()
        client.__enter__.return_value.post.return_value = response
        with patch("solver_core.httpx.Client", return_value=client):
            self.assertEqual(call_openrouter("configured-key", "prompt"), "[]")

        headers = client.__enter__.return_value.post.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer configured-key")

    def test_2017_uploaded_pdf_preserves_all_75_question_boundaries(self):
        pdf_path = os.path.join(
            "pyq_sources",
            "UGC NET Paper 3_ Computer Science Nov 2017 English.pdf",
        )
        if not os.path.exists(pdf_path):
            self.skipTest("The uploaded 2017 sample PDF is not available.")

        chunks = chunk_pdf_text(extract_text_from_pdf(pdf_path), chunk_size=2500)
        question_numbers = [
            int(number)
            for chunk in chunks
            for number in question_numbers_in_text(chunk)
        ]
        self.assertEqual(question_numbers, list(range(1, 76)))
        self.assertLessEqual(max(map(len, chunks)), 2500)

if __name__ == "__main__":
    unittest.main()
