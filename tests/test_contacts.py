import tempfile
import unittest
from pathlib import Path

from app.contacts import (
    Contact,
    load_contacts,
    normalize_email,
    render_template,
    validate_contact,
)


class ContactTests(unittest.TestCase):
    def test_load_contacts_requires_expected_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            path.write_text("email\nperson@example.com\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_contacts(path)

    def test_validate_contact_requires_email_and_adult(self):
        contact = Contact(2, "A", "B", "bad", "", "", "", "", "17", "")
        self.assertEqual(validate_contact(contact), ["invalid_email", "under_18"])

    def test_normalize_email(self):
        self.assertEqual(normalize_email(" User@Example.COM "), "user@example.com")

    def test_render_template_reports_missing_values(self):
        rendered, missing = render_template("Hi {{first_name}} {{city}}", {"first_name": "Sam"})
        self.assertEqual(rendered, "Hi Sam ")
        self.assertEqual(missing, ["city"])


if __name__ == "__main__":
    unittest.main()
