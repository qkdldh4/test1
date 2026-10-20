const MEDIAPIPE_MODULE_URL = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.21/vision_bundle.mjs";
const MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";
const WASM_URL = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.21/wasm";
const MAX_IMAGE_BYTES = 8 * 1024 * 1024;
const MAX_IMAGE_DIMENSION = 5000;
const MAX_IMAGE_PIXELS = 20_000_000;
const ANALYSIS_DIMENSION = 1280;
const BALANCE_TOLERANCE_PERCENTAGE_POINTS = 4;

const courts = [
	{ key: "upper", name: "상정", region: "이마 끝선 추정점~눈썹선", note: "고전 풀이: 초년은 분주하다." },
	{ key: "middle", name: "중정", region: "눈썹선~코끝", note: "고전 풀이: 중년의 복록이 창성하다." },
	{ key: "lower", name: "하정", region: "코끝~턱끝", note: "고전 풀이: 노년이 길상하다." },
];

const video = document.querySelector("#camera-video");
const stage = document.querySelector("#camera-stage");
const preview = document.querySelector("#photo-preview");
const captureCanvas = document.querySelector("#photo-canvas");
const startButton = document.querySelector("#start-camera");
const captureButton = document.querySelector("#capture-photo");
const analyzeButton = document.querySelector("#analyze-photo");
const retakeButton = document.querySelector("#retake-photo");
const filePicker = document.querySelector("#file-picker");
const fileInput = document.querySelector("#photo-file");
const status = document.querySelector("#camera-status");
const statusText = document.querySelector("#status-text");
const errorMessage = document.querySelector("#error-message");
const resultCard = document.querySelector("#result-card");
const emptyState = document.querySelector("#empty-state");

let cameraStream = null;
let photoBlob = null;
let photoUrl = null;
let faceLandmarkerPromise = null;

function setStatus(state, message) {
	status.dataset.state = state;
	statusText.textContent = message;
}

function showError(message) {
	errorMessage.textContent = message;
	errorMessage.classList.add("visible");
}

function clearError() {
	errorMessage.textContent = "";
	errorMessage.classList.remove("visible");
}

function stopCamera() {
	if (cameraStream) {
		cameraStream.getTracks().forEach((track) => track.stop());
		cameraStream = null;
	}
	video.srcObject = null;
	stage.classList.remove("is-live");
}

function clearPhoto() {
	if (photoUrl) URL.revokeObjectURL(photoUrl);
	photoUrl = null;
	photoBlob = null;
	preview.removeAttribute("src");
	stage.classList.remove("has-photo");
	analyzeButton.hidden = true;
	retakeButton.hidden = true;
	resultCard.classList.remove("visible");
	document.querySelector("#analysis-method").textContent = "";
	document.querySelector("#result-summary").textContent = "";
	document.querySelector("#measurements").replaceChildren();
	document.querySelector("#traditional-note").textContent = "";
	document.querySelector("#result-disclaimer").textContent = "";
	emptyState.hidden = false;
	filePicker.hidden = false;
	setStatus("off", "카메라 꺼짐");
}

function setPhoto(blob) {
	clearError();
	stopCamera();
	clearPhoto();
	photoBlob = blob;
	photoUrl = URL.createObjectURL(blob);
	preview.src = photoUrl;
	stage.classList.add("has-photo");
	startButton.hidden = true;
	captureButton.hidden = true;
	analyzeButton.hidden = false;
	retakeButton.hidden = false;
	filePicker.hidden = true;
	emptyState.hidden = true;
	setStatus("ready", "사진 준비됨");
}

async function startCamera() {
	clearError();
	if (!navigator.mediaDevices?.getUserMedia) {
		showError("이 브라우저에서는 카메라를 열 수 없습니다. 사진 파일을 선택해 주세요.");
		return;
	}
	try {
		cameraStream = await navigator.mediaDevices.getUserMedia({
			audio: false,
			video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 960 } },
		});
		video.srcObject = cameraStream;
		await video.play();
		stage.classList.add("is-live");
		startButton.hidden = true;
		captureButton.hidden = false;
		filePicker.hidden = true;
		setStatus("live", "카메라 준비됨");
	} catch (error) {
		const message = error.name === "NotAllowedError"
			? "카메라 권한이 차단되어 있어요. 브라우저에서 권한을 허용하거나 사진 파일을 선택해 주세요."
			: "카메라를 열 수 없어요. 다른 앱에서 카메라를 사용 중인지 확인하거나 사진 파일을 선택해 주세요.";
		showError(message);
		setStatus("off", "카메라 꺼짐");
	}
}

async function getFaceLandmarker() {
	if (!faceLandmarkerPromise) {
		faceLandmarkerPromise = (async () => {
			const { FaceLandmarker, FilesetResolver } = await import(MEDIAPIPE_MODULE_URL);
			const vision = await FilesetResolver.forVisionTasks(WASM_URL);
			return FaceLandmarker.createFromOptions(vision, {
				baseOptions: { modelAssetPath: MODEL_URL },
				runningMode: "IMAGE",
				numFaces: 1,
				minFaceDetectionConfidence: 0.6,
				minFacePresenceConfidence: 0.6,
				outputFaceBlendshapes: false,
				outputFacialTransformationMatrixes: false,
			});
		})().catch((error) => {
			faceLandmarkerPromise = null;
			throw error;
		});
	}
	return faceLandmarkerPromise;
}

function alignedY(landmarks, index, width, height, centerX, centerY, angle) {
	const point = landmarks[index];
	const deltaX = point.x * width - centerX;
	const deltaY = point.y * height - centerY;
	return -Math.sin(angle) * deltaX + Math.cos(angle) * deltaY;
}

function measureThreeCourts(landmarks, width, height) {
	const leftEye = landmarks[33];
	const rightEye = landmarks[263];
	const leftX = leftEye.x * width;
	const leftY = leftEye.y * height;
	const rightX = rightEye.x * width;
	const rightY = rightEye.y * height;
	const angle = Math.atan2(rightY - leftY, rightX - leftX);
	const centerX = (leftX + rightX) / 2;
	const centerY = (leftY + rightY) / 2;
	const topY = alignedY(landmarks, 10, width, height, centerX, centerY, angle);
	const browY = (
		alignedY(landmarks, 105, width, height, centerX, centerY, angle)
		+ alignedY(landmarks, 334, width, height, centerX, centerY, angle)
	) / 2;
	const noseTipY = alignedY(landmarks, 1, width, height, centerX, centerY, angle);
	const chinY = alignedY(landmarks, 152, width, height, centerX, centerY, angle);
	if (!(topY < browY && browY < noseTipY && noseTipY < chinY)) {
		throw new Error("얼굴이 기울어져 기준점을 정렬하기 어려워요. 정면에서 다시 촬영해 주세요.");
	}
	const faceHeight = chinY - topY;
	return {
		upper: Math.round((browY - topY) / faceHeight * 1000) / 10,
		middle: Math.round((noseTipY - browY) / faceHeight * 1000) / 10,
		lower: Math.round((chinY - noseTipY) / faceHeight * 1000) / 10,
	};
}

function interpretCourts(ratios) {
	const values = courts.map((court) => ratios[court.key]);
	if (Math.max(...values) - Math.min(...values) <= BALANCE_TOLERANCE_PERCENTAGE_POINTS) {
		return {
			summary: "삼정이 고르게 자리한 상",
			reading: "《신상전편·면삼정》은 '삼정이 고르면 평생 의식주가 모자라지 않는다(三停平等，一生衣禄无亏)'고 풀이합니다. 여기서 균형 판정의 4%p는 앱이 정한 비교 기준입니다.",
		};
	}

	const dominant = courts.reduce((current, court) => ratios[court.key] > ratios[current.key] ? court : current);
	const readings = {
		upper: "《신상전편·면삼정》은 '상정이 길면 초년이 분주하다(上停长少年忙)'고 풀이합니다. 초년의 활동이 많고 삶의 기초를 다지는 시기로 읽었습니다.",
		middle: "《신상전편·면삼정》은 '중정이 길면 복록이 창성하다(中停长福禄昌)'고 풀이합니다. 중년의 사회 활동과 생활 기반이 왕성한 형으로 읽었습니다.",
		lower: "《신상전편·면삼정》은 '하정이 길면 노년이 길상하다(下停长老吉祥)'고 풀이합니다. 삶의 후반부가 안정되는 형으로 읽었습니다.",
	};
	return {
		summary: `${dominant.name}이 상대적으로 길게 측정된 상`,
		reading: `${readings[dominant.key]} 이 풀이는 전통 관상서의 길흉 해석이며 실제 과거·미래를 단정하지 않습니다.`,
	};
}

function renderResult(ratios) {
	const interpretation = interpretCourts(ratios);
	document.querySelector("#analysis-method").textContent = "전통 삼정 풀이";
	document.querySelector("#result-summary").textContent = interpretation.summary;
	document.querySelector("#traditional-note").textContent = interpretation.reading;
	document.querySelector("#result-disclaimer").textContent = "이 결과는 사진에서 추정한 얼굴 비율에 전통 관상서의 해석을 적용한 문화 정보입니다. 문헌·전승에 따른 해석 차이가 있으며, 실제 운명이나 성격을 예측하지 않습니다. 상정의 시작점은 실제 헤어라인이 아닌 모델의 이마 기준점입니다.";

	const measurements = courts.map((court) => {
		const row = document.createElement("div");
		row.className = "measurement";
		const topline = document.createElement("div");
		topline.className = "measurement-topline";
		const name = document.createElement("span");
		name.className = "measurement-name";
		name.textContent = court.name;
		const ratio = document.createElement("span");
		ratio.className = "measurement-ratio";
		ratio.textContent = `${ratios[court.key].toFixed(1)}%`;
		topline.append(name, ratio);
		const track = document.createElement("div");
		track.className = "measurement-track";
		track.setAttribute("role", "meter");
		track.setAttribute("aria-valuemin", "0");
		track.setAttribute("aria-valuemax", "100");
		track.setAttribute("aria-valuenow", String(ratios[court.key]));
		track.setAttribute("aria-label", `${court.name} 비율`);
		const fill = document.createElement("div");
		fill.className = "measurement-fill";
		fill.style.width = `${ratios[court.key]}%`;
		track.append(fill);
		const note = document.createElement("p");
		note.className = "measurement-note";
		note.textContent = `${court.region} · ${court.note}`;
		row.append(topline, track, note);
		return row;
	});
	document.querySelector("#measurements").replaceChildren(...measurements);
	document.querySelector(".measurement-details").open = false;
	emptyState.hidden = true;
	resultCard.classList.add("visible");
	document.querySelector("#announcer").textContent = `전통 삼정 풀이: ${interpretation.summary}. ${interpretation.reading}`;
	setStatus("ready", "카드 완성");
}

async function analyzePhoto() {
	if (!photoBlob || analyzeButton.disabled) return;
	clearError();
	analyzeButton.disabled = true;
	analyzeButton.textContent = "분석 중...";
	setStatus("ready", "브라우저에서 분석 중");
	try {
		const faceLandmarker = await getFaceLandmarker();
		const imageBitmap = await createImageBitmap(photoBlob);
		if (imageBitmap.width > MAX_IMAGE_DIMENSION || imageBitmap.height > MAX_IMAGE_DIMENSION || imageBitmap.width * imageBitmap.height > MAX_IMAGE_PIXELS) {
			imageBitmap.close();
			throw new Error("사진 크기가 너무 큽니다. 20MP 이하 사진을 선택해 주세요.");
		}

		const scale = Math.min(1, ANALYSIS_DIMENSION / Math.max(imageBitmap.width, imageBitmap.height));
		const imageCanvas = document.createElement("canvas");
		imageCanvas.width = Math.round(imageBitmap.width * scale);
		imageCanvas.height = Math.round(imageBitmap.height * scale);
		imageCanvas.getContext("2d").drawImage(imageBitmap, 0, 0, imageCanvas.width, imageCanvas.height);
		imageBitmap.close();

		const result = faceLandmarker.detect(imageCanvas);
		if (!result.faceLandmarks?.length) {
			throw new Error("얼굴을 찾지 못했어요. 이마와 턱이 보이도록 정면에서 촬영해 주세요.");
		}
		renderResult(measureThreeCourts(result.faceLandmarks[0], imageCanvas.width, imageCanvas.height));
	} catch (error) {
		const message = error instanceof TypeError && /fetch|import/i.test(error.message)
			? "분석 모델을 불러오지 못했어요. 인터넷 연결을 확인하고 다시 눌러 주세요. 사진은 외부로 전송되지 않습니다."
			: error.message || "사진을 분석하지 못했어요. 다시 촬영해 주세요.";
		showError(message);
		setStatus("ready", "분석할 수 없음");
	} finally {
		analyzeButton.disabled = false;
		analyzeButton.innerHTML = '관상 카드 보기 <span aria-hidden="true">↗</span>';
	}
}

startButton.addEventListener("click", startCamera);

captureButton.addEventListener("click", () => {
	if (!video.videoWidth || !video.videoHeight) {
		showError("카메라 화면이 준비될 때까지 잠시 기다려 주세요.");
		return;
	}
	const scale = Math.min(1, ANALYSIS_DIMENSION / Math.max(video.videoWidth, video.videoHeight));
	captureCanvas.width = Math.round(video.videoWidth * scale);
	captureCanvas.height = Math.round(video.videoHeight * scale);
	const context = captureCanvas.getContext("2d");
	context.translate(captureCanvas.width, 0);
	context.scale(-1, 1);
	context.drawImage(video, 0, 0, captureCanvas.width, captureCanvas.height);
	captureCanvas.toBlob((blob) => {
		if (blob) setPhoto(blob);
		else showError("사진을 만들지 못했어요. 다시 촬영해 주세요.");
	}, "image/jpeg", 0.88);
});

retakeButton.addEventListener("click", () => {
	clearPhoto();
	startButton.hidden = false;
	startCamera();
});

fileInput.addEventListener("change", () => {
	const file = fileInput.files?.[0];
	if (!file) return;
	if (!file.type.startsWith("image/")) {
		showError("JPG, PNG 또는 WEBP 이미지 파일을 선택해 주세요.");
		fileInput.value = "";
		return;
	}
	if (file.size > MAX_IMAGE_BYTES) {
		showError("사진은 8MB 이하로 선택해 주세요.");
		fileInput.value = "";
		return;
	}
	setPhoto(file);
	fileInput.value = "";
});

analyzeButton.addEventListener("click", analyzePhoto);
window.addEventListener("beforeunload", () => {
	stopCamera();
	if (photoUrl) URL.revokeObjectURL(photoUrl);
	if (faceLandmarkerPromise) faceLandmarkerPromise.then((landmarker) => landmarker.close()).catch(() => {});
});