import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import app


class KnowledgeTests(unittest.TestCase):
    def test_vendor_payment_question_matches_accounts_payable(self):
        context = {"module": "FI", "product": "SAP S/4HANA", "release": "2023", "country": "Global"}
        result = app.create_answer("How do I execute an automatic vendor payment in F110?", context)
        self.assertTrue(result["matched"])
        self.assertEqual(result["topic"], "Accounts Payable")
        self.assertIn("F110", result["transactions"])

    def test_unknown_question_does_not_guess(self):
        context = {"module": "All", "product": "SAP S/4HANA", "release": "Current", "country": "Global"}
        result = app.create_answer("Explain quantum networking hardware", context)
        self.assertFalse(result["matched"])
        self.assertIn("could not find enough", result["answer"])

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


if __name__ == "__main__":
    unittest.main()
