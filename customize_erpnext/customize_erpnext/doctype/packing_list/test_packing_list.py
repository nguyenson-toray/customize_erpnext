# Copyright (c) 2026, IT Team - TIQN and Contributors
# See license.txt

import base64
import glob
import os
import re
import shutil

from frappe.tests import IntegrationTestCase

from .packing_list import read_scale_ocr

# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]

TEST_IMAGES = os.path.join(os.path.dirname(__file__), "test_images")


class IntegrationTestPackingList(IntegrationTestCase):
	"""
	Integration tests for PackingList.
	Use this class for testing interactions between multiple components.
	"""

	pass


class TestScaleOCR(IntegrationTestCase):
	"""Read real scale photos end-to-end (red mask -> localise -> ssocr -> kg).

	The expected weight IS the filename prefix: "<kg>_<description>.jpg". To add
	a case, drop a photo in test_images/ named after what the scale actually
	showed — no code change needed.

	Keep the photos that used to break OCR, e.g. "5.86_nen-pccc-nhieu-vat-do.jpg":
	the biggest red blob there is a PCCC box (5x more red pixels than the display),
	which the old "largest red cluster only" logic locked onto.
	"""

	def _samples(self):
		out = []
		for path in sorted(glob.glob(os.path.join(TEST_IMAGES, "*.jpg"))):
			m = re.match(r"([0-9]+\.?[0-9]*)_", os.path.basename(path))
			if m:
				out.append((path, float(m.group(1))))
		return out

	def _b64(self, data):
		return "base64," + base64.b64encode(data).decode()

	def test_reads_real_scale_photos(self):
		if not shutil.which("ssocr"):
			self.skipTest("ssocr is not installed (sudo apt-get install ssocr)")
		samples = self._samples()
		self.assertTrue(samples, "No sample photos in test_images/")

		for path, expected in samples:
			name = os.path.basename(path)
			with self.subTest(image=name):
				with open(path, "rb") as fh:
					res = read_scale_ocr(self._b64(fh.read()), 2) or {}
				self.assertTrue(res.get("ok"), f"{name}: not read (reason={res.get('reason')})")
				self.assertEqual(res.get("value"), expected, f"{name}: wrong kg")

	def test_refuses_photos_shot_too_far(self):
		"""test_images/too_far/ must NEVER produce a number.

		Real shots whose digits fall under MIN_DIGIT_PX. Guards against loosening
		the gate later: a wrong weight is worse than no weight, and these came back
		as confident nonsense before the gates existed.
		"""
		if not shutil.which("ssocr"):
			self.skipTest("ssocr is not installed (sudo apt-get install ssocr)")
		paths = sorted(glob.glob(os.path.join(TEST_IMAGES, "too_far", "*.jpg")))
		self.assertTrue(paths, "No sample photos in test_images/too_far/")
		for path in paths:
			name = os.path.basename(path)
			with self.subTest(image=name):
				with open(path, "rb") as fh:
					res = read_scale_ocr(self._b64(fh.read()), 2) or {}
				self.assertFalse(res.get("ok"), f"{name}: must refuse, got {res.get('value')}")
				self.assertIsNone(res.get("value"))

	def test_refuses_instead_of_guessing_when_digits_too_small(self):
		"""A far/downscaled photo must be refused, never guessed.

		Digits below MIN_DIGIT_PX carry too little information; upscaling cannot
		invent detail and ssocr then returns confident nonsense (real example from
		the old 480x640 photos: 13px digits produced a confident "8.88").
		"""
		if not shutil.which("ssocr"):
			self.skipTest("ssocr is not installed (sudo apt-get install ssocr)")
		samples = self._samples()
		self.assertTrue(samples, "No sample photos in test_images/")

		import io

		from PIL import Image

		path, _expected = samples[0]
		im = Image.open(path).convert("RGB")
		im = im.resize((im.width // 4, im.height // 4), Image.LANCZOS)  # ~ the old 480x640
		buf = io.BytesIO()
		im.save(buf, "JPEG", quality=95)

		res = read_scale_ocr(self._b64(buf.getvalue()), 2) or {}
		self.assertFalse(res.get("ok"), f"must refuse a too-small photo, got {res.get('value')}")
		self.assertIsNone(res.get("value"))
