import tempfile
import unittest
from pathlib import Path

from app.contacts import (
    Contact,
    is_personal_email,
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

    def test_load_contacts_allows_missing_age_and_birth_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contacts.csv"
            path.write_text(
                "first_name,last_name,email,phone,city,state,gender\n"
                "Sam,Sample,sam@example.com,555,Austin,TX,M\n",
                encoding="utf-8",
            )

            contacts = load_contacts(path)

            self.assertEqual(len(contacts), 1)
            self.assertEqual(contacts[0].age, "")
            self.assertEqual(contacts[0].birth_date, "")

    def test_validate_contact_requires_email_and_adult(self):
        contact = Contact(2, "A", "B", "bad", "", "", "", "", "17", "")
        self.assertEqual(validate_contact(contact), ["invalid_email", "under_18"])

    def test_validate_contact_allows_missing_age(self):
        contact = Contact(2, "A", "B", "adult@gmail.com", "", "", "", "", "", "")
        self.assertEqual(validate_contact(contact), [])

    def test_personal_email_classification(self):
        self.assertTrue(is_personal_email("person@gmail.com"))
        self.assertTrue(is_personal_email("person@outlook.com"))
        self.assertFalse(is_personal_email("person@alayacare.com"))

    def test_normalize_email(self):
        self.assertEqual(normalize_email(" User@Example.COM "), "user@example.com")

    def test_render_template_reports_missing_values(self):
        rendered, missing = render_template("Hi {{first_name}} {{city}}", {"first_name": "Sam"})
        self.assertEqual(rendered, "Hi Sam ")
        self.assertEqual(missing, ["city"])


if __name__ == "__main__":
    unittest.main()
