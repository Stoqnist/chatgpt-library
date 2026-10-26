import unittest
import app

class RoutineTests(unittest.TestCase):
    def test_domains(self):
        self.assertEqual(app.selected_domains('hello'), ['health', 'planner'])

    def test_conditional_domains(self):
        self.assertEqual(app.selected_domains('food and rent'), ['health', 'home', 'finance', 'planner'])

    def test_emergency(self):
        self.assertTrue(app.possible_emergency('chest pain'))

if __name__ == '__main__':
    unittest.main()
