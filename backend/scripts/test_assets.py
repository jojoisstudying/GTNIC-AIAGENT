"""Offline tests for photo asset migration, review gates, and generation cache."""
import base64
import io
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from src import config
from src.carousel.agents import designer
from src.carousel.tools import asset_library, cloudflare_pose_generator


class FakeResponse:
    ok = True
    status_code = 200
    headers = {"content-type": "application/json"}
    content = b""
    text = ""
    image_b64 = ""
    response_json = True

    def json(self):
        if not self.response_json:
            raise ValueError("not JSON")
        return {"result": {"image": self.image_b64}}


class AssetWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.reference = self.root / "data" / "people" / "operator_01" / "reference.png"
        self.reference.parent.mkdir(parents=True)
        Image.new("RGB", (32, 48), "navy").save(self.reference)
        self.db = self.root / "data" / "app.db"
        with sqlite3.connect(self.db) as connection:
            connection.execute("CREATE TABLE assets (id INTEGER PRIMARY KEY, path TEXT UNIQUE, tags TEXT, description TEXT)")
        self.old_root, self.old_db = config.ROOT, asset_library.DB
        config.ROOT, asset_library.DB = self.root, self.db
        output = io.BytesIO()
        generated = Image.new("RGBA", (120, 160), (20, 40, 60, 255))
        for y in range(160):
            generated.putpixel((0, y), (20, 40, 60, 0))
            generated.putpixel((119, y), (20, 40, 60, 0))
        generated.save(output, format="PNG")
        self.generated_png = output.getvalue()
        FakeResponse.image_b64 = base64.b64encode(self.generated_png).decode("ascii")

    def tearDown(self):
        config.ROOT, asset_library.DB = self.old_root, self.old_db
        self.temp.cleanup()

    def test_generation_is_cached_and_requires_approval(self):
        with (
            patch.dict(os.environ, {"CLOUDFLARE_ACCOUNT_ID": "test-account", "CLOUDFLARE_API_TOKEN": "test-token"}),
            patch.object(cloudflare_pose_generator.requests, "post", return_value=FakeResponse()) as post,
            patch.object(cloudflare_pose_generator, "_remove_background", wraps=cloudflare_pose_generator._remove_background) as remove_bg,
        ):
            # Replace the real local inference with deterministic transparent input.
            remove_bg.side_effect = lambda _image: self.generated_png
            first = cloudflare_pose_generator.generate_pose("operator_01", "senyum")
            second = cloudflare_pose_generator.generate_pose("operator_01", "senyum")

        self.assertEqual(post.call_count, 1)
        self.assertEqual(remove_bg.call_count, 1)
        request = post.call_args
        self.assertTrue(request.kwargs["data"]["prompt"].startswith("Edit the provided"))
        self.assertEqual(request.kwargs["data"]["width"], "1024")
        self.assertIn("input_image_0", request.kwargs["files"])
        filename, image_bytes, content_type = request.kwargs["files"]["input_image_0"]
        self.assertEqual(filename, "reference.png")
        self.assertEqual(content_type, "image/png")
        with Image.open(io.BytesIO(image_bytes)) as reference:
            self.assertLess(reference.width, 512)
            self.assertLess(reference.height, 512)
        self.assertEqual(first["status"], "pending_review")
        self.assertTrue(second["cached"])
        self.assertEqual(first["id"], second["id"])
        self.assertIsNone(asset_library.find_pose(["senyum"]))
        approved_id = asset_library.set_status(first["cache_key"][:16], "approved")
        self.assertEqual(approved_id, first["id"])
        self.assertEqual(asset_library.find_pose(["senyum"]), first["path"])
        with Image.open(first["path"]) as image:
            self.assertEqual(image.size, (120, 160))
            self.assertEqual(image.getchannel("A").getextrema()[0], 0)

    def test_remove_background_uses_local_rembg_and_returns_transparent_png(self):
        opaque = io.BytesIO()
        Image.new("RGB", (40, 60), "gray").save(opaque, format="PNG")
        cutout = io.BytesIO()
        subject = Image.new("RGBA", (40, 60), (0, 0, 0, 0))
        for y in range(10, 50):
            for x in range(12, 28):
                subject.putpixel((x, y), (200, 100, 50, 255))
        subject.save(cutout, format="PNG")
        rembg_stub = SimpleNamespace(
            new_session=lambda _model: object(),
            remove=lambda _data, session: cutout.getvalue(),
        )
        with patch.dict("sys.modules", {"rembg": rembg_stub}):
            result = cloudflare_pose_generator._remove_background(opaque.getvalue())
        with Image.open(io.BytesIO(result)) as image:
            self.assertEqual(image.mode, "RGBA")
            self.assertLess(image.width, 40)  # transparent margins are cropped
            self.assertLess(image.height, 60)
            self.assertEqual(image.getchannel("A").getextrema()[0], 0)

    def test_cutout_beats_newer_opaque_asset(self):
        opaque_path = self.root / "data/assets/generated/opaque.png"
        cutout_path = self.root / "data/assets/generated/person_cutout.png"
        opaque_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (120, 160), "gray").save(opaque_path)
        transparent = Image.new("RGBA", (120, 160), (0, 0, 0, 0))
        for y in range(4, 156):
            for x in range(20, 100):
                transparent.putpixel((x, y), (200, 100, 50, 255))
        transparent.save(cutout_path)
        asset_library.add_asset(str(opaque_path), ["senyum"], "legacy generated photo",
                                model="flux-model", person_id="operator_01")
        asset_library.add_asset(str(cutout_path), ["senyum"], "reviewed cutout")
        self.assertEqual(asset_library.find_pose(["senyum"]), str(cutout_path))
        self.assertEqual(asset_library.find_opaque_generated_pose(["senyum"])["path"], str(opaque_path))

    def test_placeholder_is_not_selected_when_no_real_asset_exists(self):
        placeholder_path = self.root / "data/assets/placeholder_senyum.png"
        placeholder_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (16, 24), (0, 0, 0, 0)).save(placeholder_path)
        asset_library.add_asset(str(placeholder_path), ["senyum"], "placeholder")
        self.assertEqual(asset_library.find_pose(["senyum"]), str(placeholder_path))
        self.assertTrue(asset_library.is_placeholder(asset_library.find_pose(["senyum"])))

    def test_stage_existing_opaque_asset_without_cloudflare_generation(self):
        opaque_path = self.root / "data/assets/generated/legacy.png"
        opaque_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (120, 160), "gray").save(opaque_path)
        legacy = {"id": 12, "path": str(opaque_path), "tags": ["senyum"],
                  "person_id": "operator_01", "model": "flux-model"}
        result_bytes = io.BytesIO()
        transparent = Image.new("RGBA", (120, 160), (0, 0, 0, 0))
        for y in range(3, 157):
            for x in range(20, 100):
                transparent.putpixel((x, y), (180, 120, 60, 255))
        transparent.save(result_bytes, format="PNG")
        with (
            patch.object(cloudflare_pose_generator, "_remove_background", return_value=result_bytes.getvalue()),
            patch.object(cloudflare_pose_generator.requests, "post") as cloudflare_post,
        ):
            result = cloudflare_pose_generator.stage_cutout_from_asset(legacy)
        self.assertEqual(result["status"], "pending_review")
        self.assertEqual(result["tags"], ["senyum"])
        cloudflare_post.assert_not_called()
        self.assertIsNone(asset_library.find_pose(["senyum"]))
        asset_library.set_status(result["id"], "approved")
        self.assertEqual(asset_library.find_pose(["senyum"]), result["path"])

    def test_generated_image_quality_gate_requires_real_transparency(self):
        opaque = self.root / "opaque.png"
        transparent = self.root / "cutout.png"
        Image.new("RGBA", (120, 200), (40, 50, 60, 255)).save(opaque)
        image = Image.new("RGBA", (120, 200), (0, 0, 0, 0))
        for y in range(10, 190):
            for x in range(30, 90):
                image.putpixel((x, y), (40, 50, 60, 255))
        image.save(transparent)
        self.assertFalse(cloudflare_pose_generator.quality_check_generated(opaque)["ok"])
        self.assertTrue(cloudflare_pose_generator.quality_check_generated(transparent)["ok"])

    def test_generated_image_quality_gate_requires_portrait_shape(self):
        landscape = self.root / "landscape.png"
        image = Image.new("RGBA", (200, 120), (0, 0, 0, 0))
        for y in range(10, 110):
            for x in range(10, 190):
                image.putpixel((x, y), (40, 50, 60, 255))
        image.save(landscape)

        result = cloudflare_pose_generator.quality_check_generated(landscape)

        self.assertFalse(result["ok"])
        self.assertIn("bentuk cutout bukan portrait (tinggi harus melebihi lebar)", result["issues"])
        self.assertEqual(result["metrics"]["aspect_ratio"], 1.6667)

    def test_generate_and_stage_apply_the_same_quality_gate(self):
        opaque_path = self.root / "data/assets/generated/old_opaque.png"
        opaque_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (120, 160), "gray").save(opaque_path)
        old_asset = {"id": 44, "path": str(opaque_path), "tags": ["senyum"],
                     "person_id": "operator_01", "model": "flux-model"}
        cutout = Image.new("RGBA", (120, 160), (0, 0, 0, 0))
        for y in range(10, 150):
            for x in range(25, 95):
                cutout.putpixel((x, y), (40, 80, 120, 255))
        image_buffer = io.BytesIO()
        cutout.save(image_buffer, format="PNG")
        with patch.object(cloudflare_pose_generator, "_remove_background", return_value=image_buffer.getvalue()):
            staged = cloudflare_pose_generator.stage_cutout_from_asset(old_asset)
        self.assertTrue(cloudflare_pose_generator.quality_check_generated(staged["path"])["ok"])

    def test_designer_stages_every_unique_pose_once(self):
        old_output = config.OUTPUT_DIR
        config.OUTPUT_DIR = self.root / "output"
        config.OUTPUT_DIR.mkdir(parents=True)
        staged_calls = []

        def fake_generate(person_id, pose):
            staged_calls.append((person_id, pose))
            path = self.root / f"{pose}_generated.png"
            image = Image.new("RGBA", (120, 160), (0, 0, 0, 0))
            for y in range(10, 150):
                for x in range(25, 95):
                    image.putpixel((x, y), (40, 80, 120, 255))
            image.save(path)
            return {"id": len(staged_calls), "path": str(path), "status": "pending_review"}

        plan = {"slides": [
            {"role": "cover", "headline": "Panduan Aman", "subtext": "Mulai dari kebiasaan yang benar.", "pose_tags": ["senyum"]},
            {"role": "content", "headline": "Periksa Area", "subtext": "Cek jalur kerja sebelum menyalakan mesin produksi.", "pose_tags": ["menunjuk"]},
            {"role": "cta", "headline": "Siap Bekerja Aman", "subtext": "Diskusikan panduan ini bersama tim.", "pose_tags": ["senyum"]},
        ]}
        brand = {"company": "Test", "colors": {"primary": "#0B2A5B", "secondary": "#EAF1FF",
                  "accent": "#FFB400", "text_on_primary": "#FFFFFF"}}
        try:
            with (
                patch.dict(os.environ, {"CLOUDFLARE_POSE_GENERATION": "true",
                                        "CLOUDFLARE_POSE_PERSON_ID": "operator_01"}),
                patch.object(cloudflare_pose_generator, "generate_pose", side_effect=fake_generate),
            ):
                result = designer.run(plan, brand, self.root / "slides", on_step=lambda _message: None)
            self.assertEqual(staged_calls, [("operator_01", "senyum"), ("operator_01", "menunjuk")])
            self.assertEqual(len(result["pending_review"]), 2)
        finally:
            config.OUTPUT_DIR = old_output


if __name__ == "__main__":
    unittest.main()
