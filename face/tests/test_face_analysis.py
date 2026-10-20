import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from face_analysis import FACE_MESH, analyze_photo, calculate_three_courts


class ThreeCourtTests(unittest.TestCase):
	def test_equal_sections_have_equal_ratios(self) -> None:
		ratios = calculate_three_courts(0, 100, 200, 300)
		self.assertEqual(ratios, {"upper": 33.3, "middle": 33.3, "lower": 33.3})

	def test_sections_are_normalized_to_face_height(self) -> None:
		ratios = calculate_three_courts(20, 100, 190, 270)
		self.assertEqual(ratios, {"upper": 32.0, "middle": 36.0, "lower": 32.0})

	def test_rejects_unordered_landmarks(self) -> None:
		with self.assertRaises(ValueError):
			calculate_three_courts(0, 120, 100, 300)

	def test_rejects_non_finite_landmarks(self) -> None:
		with self.assertRaises(ValueError):
			calculate_three_courts(0, float("nan"), 200, 300)

	def test_balanced_sections_are_described_as_balanced(self) -> None:
		from face_analysis import _interpret_courts

		summary, reading = _interpret_courts({"upper": 33.3, "middle": 33.3, "lower": 33.3})
		self.assertIn("삼정이 고르게", summary)
		self.assertIn("三停平等", reading)

	def test_longer_court_uses_its_classical_reading(self) -> None:
		from face_analysis import _interpret_courts

		cases = (
			({"upper": 40.0, "middle": 30.0, "lower": 30.0}, "상정", "上停长少年忙"),
			({"upper": 30.0, "middle": 40.0, "lower": 30.0}, "중정", "中停长福禄昌"),
			({"upper": 30.0, "middle": 30.0, "lower": 40.0}, "하정", "下停长老吉祥"),
		)
		for ratios, court, passage in cases:
			with self.subTest(court=court):
				summary, reading = _interpret_courts(ratios)
				self.assertIn(f"{court}이 상대적으로 길게", summary)
				self.assertIn(passage, reading)

	def test_rejects_non_image_bytes(self) -> None:
		with self.assertRaisesRegex(ValueError, "이미지를 읽을 수 없습니다"):
			analyze_photo(b"not an image")

	def test_rejects_image_with_no_face(self) -> None:
		ok, encoded = cv2.imencode(".jpg", np.zeros((240, 320, 3), dtype=np.uint8))
		self.assertTrue(ok)
		with self.assertRaisesRegex(ValueError, "얼굴을 찾지 못했어요"):
			analyze_photo(encoded.tobytes())

	def test_analyzer_returns_three_landmark_measurements(self) -> None:
		points = [SimpleNamespace(x=0.5, y=0.5) for _ in range(468)]
		points[33] = SimpleNamespace(x=0.4, y=0.4)
		points[263] = SimpleNamespace(x=0.6, y=0.4)
		points[10] = SimpleNamespace(x=0.5, y=0.2)
		points[105] = SimpleNamespace(x=0.45, y=0.4)
		points[334] = SimpleNamespace(x=0.55, y=0.4)
		points[1] = SimpleNamespace(x=0.5, y=0.6)
		points[152] = SimpleNamespace(x=0.5, y=0.8)
		mesh_result = SimpleNamespace(
			multi_face_landmarks=[SimpleNamespace(landmark=points)]
		)
		ok, encoded = cv2.imencode(".jpg", np.zeros((240, 320, 3), dtype=np.uint8))
		self.assertTrue(ok)

		with patch.object(FACE_MESH, "process", return_value=mesh_result):
			result = analyze_photo(encoded.tobytes())

		self.assertEqual(result["method"], "전통 삼정 풀이")
		self.assertIn("reading", result)
		self.assertEqual(
			[item["ratio"] for item in result["measurements"]],
			[33.3, 33.3, 33.3],
		)
		self.assertEqual(result["measurements"][0]["region"], "이마 끝선 추정점~눈썹선")
		self.assertEqual(result["measurements"][1]["region"], "눈썹선~코끝")
		self.assertEqual(result["measurements"][2]["region"], "코끝~턱끝")


if __name__ == "__main__":
	unittest.main()