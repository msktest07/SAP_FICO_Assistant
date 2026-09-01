import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import app
from api.index import app as api_app


class KnowledgeTests(unittest.TestCase):
    def test_vendor_payment_question_matches_accounts_payable(self):
        context = {"module": "FI", "product": "SAP S/4HANA", "release": "2023", "country": "Global"}
        result = app.create_answer("How do I execute an automatic vendor payment in F110?", context)
        self.assertTrue(result["matched"])
        self.assertEqual(result["topic"], "Accounts Payable")
        self.assertIn("F110", result["transactions"])

    @patch.object(app, "fetch_web_answer", return_value="A general web summary explains the concept and recommends validating assumptions against the system context.")
    def test_unknown_question_uses_dynamic_fallback(self, mock_web_answer):
        context = {"module": "All", "product": "SAP S/4HANA", "release": "Current", "country": "Global"}
        result = app.create_answer("Explain quantum networking hardware", context)
        self.assertFalse(result["matched"])
        self.assertEqual(result["source"], "General web answer")
        self.assertIn("general web summary", result["answer"]) 
        mock_web_answer.assert_called_once_with("Explain quantum networking hardware", "All")

    def test_ecc_requires_ecc_release(self):
        context, errors = app.validate_question({"question": "Explain vendor payments", "module": "FI", "product": "SAP ECC", "release": "2023", "country": "Global"})
        self.assertIsNone(context)
        self.assertTrue(any("ECC 6.0" in error for error in errors))

    def test_short_question_is_rejected(self):
        context, errors = app.validate_question({"question": "GL?", "module": "FI", "product": "SAP S/4HANA", "release": "Current", "country": "Global"})
        self.assertIsNone(context)
        self.assertIn("Question must contain at least 8 characters.", errors)


class DatabaseTests(unittest.TestCase):
    def test_database_schema_initializes(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.db"
            with patch.object(app, "DATABASE", database):
                app.initialize_database()
                with closing(app.connect()) as connection:
                    tables = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIn("conversations", tables)
            self.assertIn("feedback", tables)


class ApiIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = api_app.test_client()
        self.client.application.config["TESTING"] = True

    def test_dashboard_endpoint_returns_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.db"
            with patch("api.index.DATABASE", database):
                from api import index as api_module
                api_module.initialize_database()
                with closing(api_module.connect()) as db:
                    db.execute(
                        "INSERT INTO conversations (id, question, answer, topic, module, product, release_name, country, confidence, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        ("c1", "Vendor payment question", "Answer", "Accounts Payable", "FI", "SAP S/4HANA", "2023", "Global", 82, "2026-01-01T00:00:00+00:00"),
                    )
                    db.execute(
                        "INSERT INTO feedback (conversation_id, rating, comment, created_at) VALUES (?, ?, ?, ?)",
                        ("c1", "helpful", "great", "2026-01-01T00:00:00+00:00"),
                    )
                    db.commit()
                response = self.client.get("/api/dashboard")
                self.assertEqual(response.status_code, 200)
                data = response.get_json()
                self.assertEqual(data["questions"], 1)
                self.assertEqual(data["helpful"], 1)
                self.assertGreaterEqual(data["knowledgeTopics"], 1)

    def test_conversation_update_routes_work(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.db"
            with patch("api.index.DATABASE", database):
                from api import index as api_module
                api_module.initialize_database()
                with closing(api_module.connect()) as db:
                    db.execute(
                        "INSERT INTO conversations (id, question, answer, topic, module, product, release_name, country, confidence, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        ("c2", "Vendor payments", "Answer", "Accounts Payable", "FI", "SAP S/4HANA", "2023", "Global", 80, "2026-01-01T00:00:00+00:00"),
                    )
                    db.commit()
                response = self.client.get("/api/conversations/c2")
                self.assertEqual(response.status_code, 200)
                data = response.get_json()
                self.assertEqual(data["question"], "Vendor payments")

                update = self.client.post("/api/conversations/c2", json={"action": "update", "question": "How do I execute an automatic vendor payment in F110?", "module": "FI", "product": "SAP S/4HANA", "release": "2023", "country": "Global"})
                self.assertEqual(update.status_code, 200)
                body = update.get_json()
                self.assertIn("topic", body)

                delete = self.client.delete("/api/conversations/c2")
                self.assertEqual(delete.status_code, 200)

    def test_database_uses_temp_storage_in_serverless_runtime(self):
        from api import index as api_module
        with patch.dict("os.environ", {"VERCEL": "1"}, clear=False):
            path = api_module.resolve_database_path()
            self.assertIn("Temp", str(path), msg=f"Expected a writable temp path, got {path}")
            self.assertTrue(path.parent.exists(), msg=f"Temp parent does not exist: {path.parent}")


if __name__ == "__main__":
    unittest.main()
