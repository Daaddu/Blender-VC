import unittest

from blender_voice_commands import Command, parse_command


class ParseCommandTests(unittest.TestCase):
    def test_create_object(self):
        self.assertEqual(parse_command("Create   sphere"), Command("add", ("sphere",)))

    def test_transform_values(self):
        self.assertEqual(
            parse_command("move -1 2.5 .25"),
            Command("move", (-1.0, 2.5, 0.25)),
        )

    def test_delete_all_and_save(self):
        self.assertEqual(parse_command("remove all"), Command("delete_all"))
        self.assertEqual(parse_command("save file"), Command("save"))

    def test_rejects_unsupported_text(self):
        with self.assertRaises(ValueError):
            parse_command("make the scene beautiful")


if __name__ == "__main__":
    unittest.main()
