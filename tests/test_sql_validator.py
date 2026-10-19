import unittest

from agents.sql_agent import validate_sql


class TestSQLValidator(unittest.TestCase):
    def test_allows_select(self):
        self.assertTrue(validate_sql("SELECT id FROM projects")["valid"])

    def test_blocks_destructive_keyword(self):
        self.assertFalse(validate_sql("SELECT DELETE FROM projects")["valid"])

    def test_allows_column_containing_blocked_word(self):
        self.assertTrue(validate_sql("SELECT updated_at FROM projects")["valid"])

    def test_blocks_stacked_destructive_statement(self):
        self.assertFalse(
            validate_sql("SELECT 1; DROP TABLE projects")["valid"]
        )

    def test_blocks_stacked_select_statements(self):
        self.assertFalse(validate_sql("SELECT 1; SELECT 2")["valid"])


if __name__ == "__main__":
    unittest.main()