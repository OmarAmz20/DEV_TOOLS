import random
import unittest
from wallpaper_studio import recipes,palette


class RecipeTests(unittest.TestCase):
    def test_all_recipes_and_custom_accents_are_readable(self):
        rng=random.Random(42)
        accents=["", "#FFFFFF", "#000000", "#FF0000"]+[f"#{rng.randrange(16777216):06X}" for _ in range(20)]
        for name in recipes.PRESETS:
            for accent in accents:
                for stronger in (False,True):
                    with self.subTest(recipe=name,accent=accent,stronger=stronger):
                        result=recipes.resolve(recipes.sample_base(),{"preset":name,"accent":accent,"high_contrast":stronger})
                        for p in result.values():
                            metrics=recipes.metrics(p)
                            self.assertGreaterEqual(metrics["text"],7 if stronger else 4.5)
                            self.assertGreaterEqual(metrics["secondary"],4.5)
                            self.assertGreaterEqual(metrics["accent"],4.5)
                            self.assertEqual(len(p["ansi"]),16)
                            self.assertTrue(all(recipes.valid_hex(c) for c in p["ansi"]))

    def test_semantic_colours_keep_distinct_hues(self):
        p=recipes.resolve(recipes.sample_base(),{"preset":"nord"})["dark"]
        red=palette.hex_to_rgb(p["ansi"][1]);green=palette.hex_to_rgb(p["ansi"][2])
        self.assertGreater(red[0],red[1]);self.assertGreater(green[1],green[0])

    def test_css_has_correct_foreground_and_corner_roles(self):
        p=recipes.resolve(recipes.sample_base(),{"preset":"dracula"})["dark"]
        css=recipes.gtk_css(p,True,{"shape":"square"})
        self.assertIn("border-radius: 0px",css);self.assertIn("@define-color error_fg_color",css)
        self.assertIn("@accent_fg_color",css)


if __name__=="__main__":unittest.main()
