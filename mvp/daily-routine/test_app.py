import unittest
import app

class RoutineTests(unittest.TestCase):
    def test_domains(self):
        self.assertEqual(app.selected_domains('hello'), ['health', 'planner'])

if __name__ == '__main__':
    unittest.main()
