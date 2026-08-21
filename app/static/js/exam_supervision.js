const CLIENT_EVENT_COOLDOWN_MS = 5000;
const DETECTION_INTERVAL_MS = 500;
const FACE_ABSENCE_SAMPLE_LIMIT = 3;
const GAZE_DEVIATION_SAMPLE_LIMIT = 4;

const sessionRoot = document.getElementById("exam-session");

if (sessionRoot) {
  const violationUrl = sessionRoot.dataset.violationUrl;
  const submittedUrl = sessionRoot.dataset.submittedUrl;
  const csrfToken = sessionRoot.dataset.csrfToken;
  const monitorType = sessionRoot.dataset.monitorType;
  const warningLimit = Number(sessionRoot.dataset.warningLimit);
  const mediapipeModuleUrl = sessionRoot.dataset.mediapipeModuleUrl;
  const mediapipeWasmUrl = sessionRoot.dataset.mediapipeWasmUrl;
  const faceLandmarkerModelUrl =
    sessionRoot.dataset.faceLandmarkerModelUrl;

  const examForm = document.getElementById("exam-form");
  const questionContainer = document.getElementById(
    "question-container",
  );
  const preview = document.getElementById("monitor-preview");
  const monitorStatus = document.getElementById("monitor-status");
  const warningPanel = document.getElementById("integrity-warning");
  const warningMessage = document.getElementById(
    "integrity-warning-message",
  );
  const warningCount = document.getElementById(
    "integrity-warning-count",
  );

  const lastReportedAt = new Map();

  let warningTimer;
  let cameraStream;
  let faceLandmarker;
  let detectionTimer;
  let lastVideoTime = -1;
  let faceAbsenceSamples = 0;
  let gazeDeviationSamples = 0;
  let focusEventsEnabled = false;
  let activeFaceAbsence;

  function setMonitorStatus(message, state = "pending") {
    monitorStatus.textContent = message;
    monitorStatus.dataset.state = state;
  }

  function displayWarning(message, count = null) {
    warningMessage.textContent = message;
    warningCount.textContent = Number.isInteger(count)
      ? `Warning ${count} of ${warningLimit}.`
      : "";

    warningPanel.hidden = false;

    window.clearTimeout(warningTimer);
    warningTimer = window.setTimeout(() => {
      warningPanel.hidden = true;
    }, 7000);
  }

  function collectResponses() {
    const responses = {};
    const form = new FormData(examForm);

    form.forEach((value, name) => {
      if (
        !name.startsWith("question_") ||
        typeof value !== "string"
      ) {
        return;
      }

      responses[name.slice("question_".length)] = value;
    });

    return responses;
  }

  async function reportViolation(violationType, metadata = {}) {
    const now = Date.now();
    const previous = lastReportedAt.get(violationType) || 0;

    if (now - previous < CLIENT_EVENT_COOLDOWN_MS) {
      return null;
    }

    lastReportedAt.set(violationType, now);

    try {
      const response = await fetch(violationUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify({
          violation_type: violationType,
          metadata,
          responses: collectResponses(),
        }),
      });

      const payload = await response.json();

      if (payload.submitted) {
        if (
          violationType === "face_not_detected" &&
          payload.warning_id &&
          metadata.recording_supported
        ) {
          sessionRoot.dataset.evidenceUploadPending = "true";
          displayWarning(
            payload.message,
            payload.warning_count,
          );
          return payload;
        }

        if (
          sessionRoot.dataset.evidenceUploadPending === "true"
        ) {
          return payload;
        }

        window.location.assign(submittedUrl);
        return payload;
      }

      if (
        payload.warning_limit_reached &&
        !payload.message
      ) {
        displayWarning(
          "The maximum warning count has been reached.",
          payload.warning_count,
        );
        return payload;
      }

      if (!response.ok) {
        return null;
      }

      sessionRoot.dataset.warningCount =
        payload.warning_count;

      displayWarning(
        payload.message,
        payload.warning_count,
      );

      return payload;
    } catch (_error) {
      setMonitorStatus(
        "The supervision service could not be reached. Reconnecting…",
        "error",
      );

      return null;
    }
  }

  function supportedRecordingType() {
    if (!window.MediaRecorder) {
      return null;
    }

    const candidates = [
      "video/webm;codecs=vp8",
      "video/webm",
      "video/mp4",
    ];

    return (
      candidates.find((type) =>
        MediaRecorder.isTypeSupported(type),
      ) || ""
    );
  }

  function beginFaceAbsenceEvidence() {
    if (activeFaceAbsence) {
      return;
    }

    const startedAtMs = Date.now();
    const chunks = [];
    const mimeType = supportedRecordingType();
    let recorder = null;

    if (
      mimeType !== null &&
      cameraStream?.active
    ) {
      const options = {
        videoBitsPerSecond: 300000,
      };

      if (mimeType) {
        options.mimeType = mimeType;
      }

      try {
        recorder = new MediaRecorder(
          cameraStream,
          options,
        );

        recorder.addEventListener(
          "dataavailable",
          (event) => {
            if (event.data.size > 0) {
              chunks.push(event.data);
            }
          },
        );

        recorder.start(1000);
      } catch (_error) {
        recorder = null;
      }
    }

    activeFaceAbsence = {
      chunks,
      recorder,
      startedAtMs,
      warningPromise: null,
    };
  }

  function stopAbsenceRecorder(absence) {
    return new Promise((resolve) => {
      const finish = () => {
        const type =
          absence.recorder?.mimeType ||
          absence.chunks[0]?.type ||
          "video/webm";

        resolve(
          new Blob(absence.chunks, {type}),
        );
      };

      if (
        !absence.recorder ||
        absence.recorder.state === "inactive"
      ) {
        finish();
        return;
      }

      absence.recorder.addEventListener(
        "stop",
        finish,
        {once: true},
      );

      absence.recorder.stop();
    });
  }

  async function uploadFaceAbsenceEvidence(
    absence,
    endedAtMs,
  ) {
    const clip = await stopAbsenceRecorder(absence);

    if (!absence.warningPromise) {
      return;
    }

    const warning = await absence.warningPromise;
    const redirectAfterUpload =
      warning?.submitted === true;

    if (!warning?.warning_id || clip.size === 0) {
      if (redirectAfterUpload) {
        window.location.assign(submittedUrl);
      }

      return;
    }

    const form = new FormData();
    const extension = clip.type.startsWith("video/mp4")
      ? "mp4"
      : "webm";

    form.append(
      "video",
      clip,
      `face-absence.${extension}`,
    );
    form.append(
      "started_at",
      new Date(absence.startedAtMs).toISOString(),
    );
    form.append(
      "ended_at",
      new Date(endedAtMs).toISOString(),
    );
    form.append(
      "duration_ms",
      String(endedAtMs - absence.startedAtMs),
    );

    try {
      const response = await fetch(
        `${violationUrl}/${warning.warning_id}/evidence`,
        {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "X-CSRFToken": csrfToken,
          },
          body: form,
        },
      );

      if (!response.ok) {
        setMonitorStatus(
          "Camera is active, but an evidence clip could not be uploaded.",
          "error",
        );
      }
    } catch (_error) {
      setMonitorStatus(
        "Camera is active, but an evidence clip could not be uploaded.",
        "error",
      );
    } finally {
      if (redirectAfterUpload) {
        window.location.assign(submittedUrl);
      }
    }
  }

  function finishFaceAbsenceEvidence() {
    if (!activeFaceAbsence) {
      return;
    }

    const absence = activeFaceAbsence;
    activeFaceAbsence = null;

    void uploadFaceAbsenceEvidence(
      absence,
      Date.now(),
    );
  }

  function keyboardShortcut(event) {
    const modifiers = [];

    if (event.ctrlKey) {
      modifiers.push("Ctrl");
    }

    if (event.metaKey) {
      modifiers.push("Meta");
    }

    if (event.altKey) {
      modifiers.push("Alt");
    }

    if (event.shiftKey) {
      modifiers.push("Shift");
    }

    modifiers.push(event.key);

    return modifiers.join("+").slice(0, 100);
  }

  function installClipboardControls() {
    ["copy", "cut", "paste"].forEach(
      (eventName) => {
        document.addEventListener(
          eventName,
          (event) => {
            event.preventDefault();

            reportViolation("copy_paste", {
              source: eventName,
            });
          },
        );
      },
    );

    document.addEventListener(
      "contextmenu",
      (event) => {
        if (
          questionContainer.contains(event.target)
        ) {
          event.preventDefault();

          reportViolation("copy_paste", {
            source: "contextmenu",
          });
        }
      },
    );

    document.addEventListener(
      "keydown",
      (event) => {
        if (event.repeat) {
          return;
        }

        const key = event.key.toLowerCase();

        const clipboardShortcut =
          (event.ctrlKey || event.metaKey) &&
          ["c", "v", "x"].includes(key);

        if (clipboardShortcut) {
          event.preventDefault();

          reportViolation("copy_paste", {
            source: "keyboard",
            shortcut: keyboardShortcut(event),
          });
        }
      },
    );
  }

  function installCaptureAndFocusDetection() {
    document.addEventListener(
      "keydown",
      (event) => {
        if (event.repeat) {
          return;
        }

        const key = event.key.toLowerCase();
        const printScreen = key === "printscreen";

        const windowsSnip =
          event.metaKey &&
          event.shiftKey &&
          key === "s";

        const macCapture =
          event.metaKey &&
          event.shiftKey &&
          ["3", "4", "5"].includes(key);

        if (
          printScreen ||
          windowsSnip ||
          macCapture
        ) {
          event.preventDefault();

          reportViolation(
            "screenshot_attempt",
            {
              source: "keyboard",
              shortcut: keyboardShortcut(event),
            },
          );
        }
      },
    );

    document.addEventListener(
      "visibilitychange",
      () => {
        if (
          focusEventsEnabled &&
          document.visibilityState === "hidden"
        ) {
          reportViolation("focus_loss", {
            source: "visibilitychange",
            visibility_state:
              document.visibilityState,
          });
        }
      },
    );

    window.addEventListener("blur", () => {
      if (focusEventsEnabled) {
        reportViolation("focus_loss", {
          source: "window_blur",
        });
      }
    });
  }

  function horizontalEyeRatio(
    landmarks,
    irisIndex,
    cornerOne,
    cornerTwo,
  ) {
    const leftEdge = Math.min(
      landmarks[cornerOne].x,
      landmarks[cornerTwo].x,
    );

    const rightEdge = Math.max(
      landmarks[cornerOne].x,
      landmarks[cornerTwo].x,
    );

    const width = rightEdge - leftEdge;

    if (width <= 0) {
      return 0.5;
    }

    return (
      (landmarks[irisIndex].x - leftEdge) /
      width
    );
  }

  function gazeRatio(landmarks) {
    const leftEye = horizontalEyeRatio(
      landmarks,
      468,
      33,
      133,
    );

    const rightEye = horizontalEyeRatio(
      landmarks,
      473,
      362,
      263,
    );

    return (leftEye + rightEye) / 2;
  }

  function processFaceResult(result) {
    const faces = result.faceLandmarks || [];

    if (faces.length === 0) {
      beginFaceAbsenceEvidence();

      faceAbsenceSamples += 1;
      gazeDeviationSamples = 0;

      setMonitorStatus(
        "Face not detected. Return to the camera view.",
        "warning",
      );

      if (
        faceAbsenceSamples >=
          FACE_ABSENCE_SAMPLE_LIMIT &&
        !activeFaceAbsence.warningPromise
      ) {
        activeFaceAbsence.warningPromise =
          reportViolation(
            "face_not_detected",
            {
              source: "mediapipe",
              duration_ms:
                FACE_ABSENCE_SAMPLE_LIMIT *
                DETECTION_INTERVAL_MS,
              recording_supported: Boolean(
                activeFaceAbsence.recorder,
              ),
            },
          );
      }

      return;
    }

    faceAbsenceSamples = 0;
    finishFaceAbsenceEvidence();

    setMonitorStatus(
      "Camera supervision is active.",
      "active",
    );

    if (monitorType !== "eye_gaze") {
      return;
    }

    const ratio = gazeRatio(faces[0]);

    const deviated =
      ratio < 0.22 ||
      ratio > 0.78;

    gazeDeviationSamples = deviated
      ? gazeDeviationSamples + 1
      : 0;

    if (
      gazeDeviationSamples >=
      GAZE_DEVIATION_SAMPLE_LIMIT
    ) {
      gazeDeviationSamples = 0;

      reportViolation("gaze_deviation", {
        source: "mediapipe",
        duration_ms:
          GAZE_DEVIATION_SAMPLE_LIMIT *
          DETECTION_INTERVAL_MS,
        gaze_ratio: Number(ratio.toFixed(3)),
      });
    }
  }

  function beginDetectionLoop() {
    detectionTimer = window.setInterval(() => {
      if (
        !faceLandmarker ||
        preview.readyState <
          HTMLMediaElement.HAVE_CURRENT_DATA ||
        preview.currentTime === lastVideoTime
      ) {
        return;
      }

      lastVideoTime = preview.currentTime;

      const result =
        faceLandmarker.detectForVideo(
          preview,
          performance.now(),
        );

      processFaceResult(result);
    }, DETECTION_INTERVAL_MS);
  }

  function enableFocusDetectionSoon() {
    window.setTimeout(() => {
      focusEventsEnabled = true;
    }, 1500);
  }

  async function createFaceLandmarker(
    vision,
    FaceLandmarker,
  ) {
    const options = {
      baseOptions: {
        modelAssetPath: faceLandmarkerModelUrl,
        delegate: "GPU",
      },
      runningMode: "VIDEO",
      numFaces: 1,
      minFaceDetectionConfidence: 0.5,
      minFacePresenceConfidence: 0.5,
      minTrackingConfidence: 0.5,
    };

    try {
      return await FaceLandmarker.createFromOptions(
        vision,
        options,
      );
    } catch (_gpuError) {
      delete options.baseOptions.delegate;

      return FaceLandmarker.createFromOptions(
        vision,
        options,
      );
    }
  }

  async function initializeCameraMonitoring() {
    if (!navigator.mediaDevices?.getUserMedia) {
      setMonitorStatus(
        "This browser cannot access a webcam.",
        "error",
      );

      reportViolation("face_not_detected", {
        source: "camera_api_unavailable",
      });

      enableFocusDetectionSoon();
      return;
    }

    try {
      cameraStream =
        await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: {
            facingMode: "user",
            width: {ideal: 640},
            height: {ideal: 480},
          },
        });

      preview.srcObject = cameraStream;
      await preview.play();

      setMonitorStatus(
        "Loading the on-device supervision model…",
        "pending",
      );

      const {
        FaceLandmarker,
        FilesetResolver,
      } = await import(mediapipeModuleUrl);

      const vision =
        await FilesetResolver.forVisionTasks(
          mediapipeWasmUrl,
        );

      faceLandmarker =
        await createFaceLandmarker(
          vision,
          FaceLandmarker,
        );

      setMonitorStatus(
        "Camera supervision is active.",
        "active",
      );

      beginDetectionLoop();
    } catch (error) {
      console.error(
        "Camera supervision initialization failed:",
        error,
      );

      setMonitorStatus(
        "Camera supervision could not start. Check camera permission and connectivity.",
        "error",
      );

      reportViolation("face_not_detected", {
        source: "camera_initialization",
      });
    } finally {
      enableFocusDetectionSoon();
    }
  }

  function stopCameraMonitoring() {
    window.clearInterval(detectionTimer);

    cameraStream
      ?.getTracks()
      .forEach((track) => track.stop());

    faceLandmarker?.close();
  }

  installClipboardControls();
  installCaptureAndFocusDetection();
  initializeCameraMonitoring();

  window.addEventListener(
    "pagehide",
    stopCameraMonitoring,
    {once: true},
  );
}