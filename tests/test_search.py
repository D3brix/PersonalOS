import os
import time

from helpers import Sandbox

from personalos import index


class SearchAccuracy(Sandbox):
    def setUp(self):
        super().setUp()
        self.index()

    def test_known_queries_find_the_right_note_first(self):
        expected = {
            "crop rotation": "Crop_Rotation",
            "sourdough starter": "Sourdough_Basics",
            "knee warm-up lesson": "Lessons_Learned",
            "why did we choose sqlite decision": "Decision_Log",
            "half marathon pace": "Half_Marathon_Training",
            "spaced repetition flashcards": "Spaced_Repetition",
        }
        for q, title in expected.items():
            self.assertEqual(self.top_titles(q, 3)[0], title, q)

    def test_long_term_memory_is_found(self):
        self.assertIn("Bike_Repair_2024", self.top_titles("bike chain", 3))
        self.assertIn("Clipping_Composting_Article", self.top_titles("coffee grounds", 3))

    def test_tiering_and_labels(self):
        res = index.search(self.cfg, "goals marathon", 5)
        for h in res["tier1"]:
            self.assertEqual(h["tier"], 1)
        labels = {h["title"]: h["label"] for h in res["tier1"]}
        self.assertEqual(labels.get("Goals"), "AUTHORITATIVE")
        raw = index.search(self.cfg, "coffee grounds", 5)
        self.assertEqual((raw["tier1"] + raw["tier2"])[0]["label"], "RAW")

    def test_one_result_per_file(self):
        res = index.search(self.cfg, "crop rotation", 10, all_tiers=True)
        paths = [h["path"] for h in res["tier1"] + res["tier2"]]
        self.assertEqual(len(paths), len(set(paths)))

    def test_kind_filter(self):
        res = index.search(self.cfg, "goals", 10, all_tiers=True, kinds=["system"])
        self.assertTrue(res["tier1"])
        self.assertTrue(all(h["kind"] == "system" for h in res["tier1"] + res["tier2"]))

    def test_hostile_queries_do_not_crash(self):
        for q in ['"', "AND OR NOT", "*", "title:secret", "NEAR(a b)", "'; drop table files; --", "", "🙂", "a" * 5000]:
            index.search(self.cfg, q)

    def test_or_fallback(self):
        res = index.search(self.cfg, "sourdough zzzunknownword")
        self.assertEqual(res["mode"], "OR")
        self.assertTrue(res["tier1"] + res["tier2"])


class IncrementalIndex(Sandbox):
    def test_add_update_remove(self):
        st, _, _ = self.index()
        self.assertGreater(st["added"], 20)
        st, _, _ = self.index()
        self.assertEqual((st["added"], st["updated"], st["removed"]), (0, 0, 0))

        new = self.vault_dir / "04_Knowledge" / "Beekeeping.md"
        new.write_text("# Beekeeping\n\nVarroa mites are the main threat to honeybee colonies.\n", encoding="utf-8")
        st, _, _ = self.index()
        self.assertEqual(st["added"], 1)
        self.assertEqual(self.top_titles("varroa")[0], "Beekeeping")

        time.sleep(0.05)
        new.write_text("# Beekeeping\n\nOxalic acid treatment in winter.\n", encoding="utf-8")
        os.utime(new, (time.time() + 5, time.time() + 5))
        st, _, _ = self.index()
        self.assertEqual(st["updated"], 1)
        self.assertEqual(self.top_titles("varroa"), [])
        self.assertEqual(self.top_titles("oxalic")[0], "Beekeeping")

        new.unlink()
        st, _, _ = self.index()
        self.assertEqual(st["removed"], 1)
        self.assertEqual(self.top_titles("oxalic"), [])

    def test_touch_without_change_is_not_reindexed(self):
        self.index()
        f = self.vault_dir / "Current_Focus.md"
        os.utime(f, (time.time() + 10, time.time() + 10))
        st, _, _ = self.index()
        self.assertEqual(st["updated"], 0)

    def test_extra_source_folder(self):
        lt = self.tmp / "old-docs"
        lt.mkdir()
        (lt / "thesis.txt").write_text("Notes on medieval trade routes.", encoding="utf-8")
        self.cfg.data["extra_sources"] = [{"path": str(lt), "kind": "archived", "tier": 2, "extensions": [".txt"]}]
        self.cfg.save()
        self.index()
        res = index.search(self.cfg, "medieval trade")
        hit = (res["tier1"] + res["tier2"])[0]
        self.assertEqual((hit["label"], hit["tier"]), ("ARCHIVED DOC", 2))

    def test_show_returns_slice_and_refuses_unindexed(self):
        self.index()
        p = self.vault_dir / "04_Knowledge" / "Gardening" / "Crop_Rotation.md"
        r = index.show(self.cfg, str(p), "L5-8")
        self.assertIn("Crop rotation", r["text"])
        self.assertNotIn("Rule of thumb", r["text"])
        with self.assertRaises(index.NotIndexed):
            index.show(self.cfg, str(self.cfg.path))
