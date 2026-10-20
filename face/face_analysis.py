"""MediaPipe landmark measurements and traditional three-court notes."""

from __future__ import annotations

import math
import threading

import cv2
import mediapipe as mp
import numpy as np


MAX_IMAGE_DIMENSION = 5000
ANALYSIS_DIMENSION = 1280
MAX_IMAGE_PIXELS = 20_000_000
BALANCE_TOLERANCE_PERCENTAGE_POINTS = 4.0
FACE_MESH = mp.solutions.face_mesh.FaceMesh(
	static_image_mode=True,
	max_num_faces=1,
	refine_landmarks=False,
	min_detection_confidence=0.6,
)
FACE_MESH_LOCK = threading.Lock()

COURTS = (
	("상정", "이마 끝선 추정점~눈썹선", "고전 풀이: 초년은 분주하다."),
	("중정", "눈썹선~코끝", "고전 풀이: 중년의 복록이 창성하다."),
	("하정", "코끝~턱끝", "고전 풀이: 노년이 길상하다."),
)


def calculate_three_courts(
	top_y: float,
	brow_y: float,
	nose_tip_y: float,
	chin_y: float,
) -> dict[str, float]:
	"""Return the vertical proportions of upper, middle, and lower courts."""
	boundaries = (top_y, brow_y, nose_tip_y, chin_y)
	if not all(math.isfinite(value) for value in boundaries):
		raise ValueError("얼굴 기준점을 안정적으로 찾지 못했어요. 정면에서 다시 촬영해 주세요.")
	if not top_y < brow_y < nose_tip_y < chin_y:
		raise ValueError("얼굴 각도가 너무 기울어져 있어요. 정면에서 다시 촬영해 주세요.")

	face_height = chin_y - top_y
	return {
		"upper": round((brow_y - top_y) / face_height * 100, 1),
		"middle": round((nose_tip_y - brow_y) / face_height * 100, 1),
		"lower": round((chin_y - nose_tip_y) / face_height * 100, 1),
	}


def _aligned_y(landmarks: object, index: int, width: int, height: int, center_x: float, center_y: float, angle: float) -> float:
	point = landmarks[index]
	delta_x = point.x * width - center_x
	delta_y = point.y * height - center_y
	return -math.sin(angle) * delta_x + math.cos(angle) * delta_y


def _interpret_courts(ratios: dict[str, float]) -> tuple[str, str]:
	keys = ("upper", "middle", "lower")
	if max(ratios.values()) - min(ratios.values()) <= BALANCE_TOLERANCE_PERCENTAGE_POINTS:
		return (
			"삼정이 고르게 자리한 상",
			"《신상전편·면삼정》은 '삼정이 고르면 평생 의식주가 모자라지 않는다(三停平等，一生衣禄无亏)'고 풀이합니다. 여기서 균형 판정의 4%p는 앱이 정한 비교 기준입니다.",
		)

	dominant = max(keys, key=ratios.__getitem__)
	label = dict(zip(keys, (court[0] for court in COURTS)))[dominant]
	readings = {
		"상정": "《신상전편·면삼정》은 '상정이 길면 초년이 분주하다(上停长少年忙)'고 풀이합니다. 초년의 활동이 많고 삶의 기초를 다지는 시기로 읽었습니다.",
		"중정": "《신상전편·면삼정》은 '중정이 길면 복록이 창성하다(中停长福禄昌)'고 풀이합니다. 중년의 사회 활동과 생활 기반이 왕성한 형으로 읽었습니다.",
		"하정": "《신상전편·면삼정》은 '하정이 길면 노년이 길상하다(下停长老吉祥)'고 풀이합니다. 삶의 후반부가 안정되는 형으로 읽었습니다.",
	}
	return f"{label}이 상대적으로 길게 측정된 상", f"{readings[label]} 이 풀이는 전통 관상서의 길흉 해석이며 실제 과거·미래를 단정하지 않습니다."


def analyze_photo(image_bytes: bytes) -> dict[str, object]:
	"""Measure three-court proportions and return a folklore-labeled result."""
	if not image_bytes:
		raise ValueError("이미지를 읽을 수 없습니다. 다시 촬영해 주세요.")
	encoded_image = np.frombuffer(image_bytes, dtype=np.uint8)
	image = cv2.imdecode(encoded_image, cv2.IMREAD_COLOR)
	if image is None:
		raise ValueError("이미지를 읽을 수 없습니다. 다시 촬영해 주세요.")

	height, width = image.shape[:2]
	if max(height, width) > MAX_IMAGE_DIMENSION or width * height > MAX_IMAGE_PIXELS:
		raise ValueError("사진 크기가 너무 큽니다. 더 낮은 해상도로 촬영해 주세요.")

	scale = min(1.0, ANALYSIS_DIMENSION / max(width, height))
	if scale < 1.0:
		image = cv2.resize(
			image,
			None,
			fx=scale,
			fy=scale,
			interpolation=cv2.INTER_AREA,
		)
		height, width = image.shape[:2]

	rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
	rgb_image.flags.writeable = False
	with FACE_MESH_LOCK:
		mesh_result = FACE_MESH.process(rgb_image)

	if not mesh_result.multi_face_landmarks:
		raise ValueError("얼굴을 찾지 못했어요. 이마와 턱이 보이도록 정면에서 촬영해 주세요.")

	landmarks = mesh_result.multi_face_landmarks[0].landmark
	left_eye = landmarks[33]
	right_eye = landmarks[263]
	left_x, left_y = left_eye.x * width, left_eye.y * height
	right_x, right_y = right_eye.x * width, right_eye.y * height
	angle = math.atan2(right_y - left_y, right_x - left_x)
	center_x = (left_x + right_x) / 2
	center_y = (left_y + right_y) / 2

	top_y = _aligned_y(landmarks, 10, width, height, center_x, center_y, angle)
	brow_y = (
		_aligned_y(landmarks, 105, width, height, center_x, center_y, angle)
		+ _aligned_y(landmarks, 334, width, height, center_x, center_y, angle)
	) / 2
	nose_tip_y = _aligned_y(landmarks, 1, width, height, center_x, center_y, angle)
	chin_y = _aligned_y(landmarks, 152, width, height, center_x, center_y, angle)
	ratios = calculate_three_courts(top_y, brow_y, nose_tip_y, chin_y)

	keys = ("upper", "middle", "lower")
	measurements = [
		{"name": label, "region": region, "ratio": ratios[key], "note": note}
		for key, (label, region, note) in zip(keys, COURTS)
	]
	summary, reading = _interpret_courts(ratios)
	return {
		"method": "전통 삼정 풀이",
		"summary": summary,
		"reading": reading,
		"measurements": measurements,
		"disclaimer": "《신상전편·면삼정》 계열의 전통 해석을 소개하는 문화 정보입니다. 이 앱은 이마 상단 추정점~눈썹~코끝~턱끝 기준을 채택했으며, 문헌·전승마다 경계 표현이 다를 수 있습니다. 4%p 균형 허용오차는 앱 자체 기준입니다. MediaPipe는 실제 헤어라인을 검출하지 않습니다. 얼굴 비율로 성격·능력·건강·운명을 판단할 과학적 근거는 없습니다.",
	}


def close_analyzer() -> None:
	with FACE_MESH_LOCK:
		FACE_MESH.close()