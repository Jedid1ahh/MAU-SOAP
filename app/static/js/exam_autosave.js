(() => {
  const sessionRoot =
    document.getElementById(
      "exam-session",
    );

  const examForm =
    document.getElementById(
      "exam-form",
    );

  const status =
    document.getElementById(
      "autosave-status",
    );

  if (
    !sessionRoot ||
    !examForm ||
    !status
  ) {
    return;
  }

  const autosaveUrl =
    sessionRoot.dataset.autosaveUrl;

  const submittedUrl =
    sessionRoot.dataset.submittedUrl;

  const csrfToken =
    sessionRoot.dataset.csrfToken;

  const examToken =
    sessionRoot.dataset.examToken;

  const resumeStorageKey =
    `mau-soap:resume:${examToken}`;

  const draftStorageKey =
    `mau-soap:draft:${examToken}`;

  const AUTOSAVE_DELAY_MS = 1000;
  const AUTOSAVE_INTERVAL_MS = 15000;

  let resumeToken = "";
  let initialized = false;
  let stopped = false;
  let saveTimer;
  let saveInFlight = false;
  let saveQueued = false;
  let lastSavedSnapshot = "";

  function setStatus(
    message,
    state = "idle",
  ) {
    status.textContent = message;
    status.dataset.state = state;
  }

  function collectResponses() {
    const responses = {};

    examForm
      .querySelectorAll(
        "[name^='question_']",
      )
      .forEach((control) => {
        const questionId =
          control.name.slice(
            "question_".length,
          );

        if (
          !(questionId in responses)
        ) {
          responses[questionId] = "";
        }

        if (
          control.type !== "radio" ||
          control.checked
        ) {
          responses[questionId] =
            control.value;
        }
      });

    return responses;
  }

  function applyResponses(
    responses,
  ) {
    if (
      !responses ||
      typeof responses !== "object"
    ) {
      return;
    }

    examForm
      .querySelectorAll(
        "[name^='question_']",
      )
      .forEach((control) => {
        const questionId =
          control.name.slice(
            "question_".length,
          );

        const answer =
          responses[questionId];

        if (
          typeof answer !== "string"
        ) {
          return;
        }

        if (
          control.type === "radio"
        ) {
          control.checked =
            control.value === answer;
        } else {
          control.value = answer;
        }
      });
  }

  function writeLocalDraft(
    responses,
  ) {
    try {
      window.localStorage.setItem(
        draftStorageKey,
        JSON.stringify({
          responses,
          updatedAt:
            new Date().toISOString(),
        }),
      );
    } catch (_error) {
      setStatus(
        (
          "Changes are waiting to save, " +
          "but browser backup is " +
          "unavailable."
        ),
        "error",
      );
    }
  }

  function readLocalDraft() {
    try {
      const stored =
        window.localStorage.getItem(
          draftStorageKey,
        );

      if (!stored) {
        return null;
      }

      const parsed =
        JSON.parse(stored);

      return (
        parsed &&
        typeof parsed.responses ===
          "object"
      )
        ? parsed
        : null;
    } catch (_error) {
      try {
        window.localStorage.removeItem(
          draftStorageKey,
        );
      } catch (_storageError) {
        return null;
      }

      return null;
    }
  }

  function clearLocalDraft() {
    try {
      window.localStorage.removeItem(
        draftStorageKey,
      );
    } catch (_error) {
      // A successful server save remains
      // authoritative when browser
      // storage is unavailable.
    }
  }

  function rememberResumeToken() {
    if (
      !resumeToken ||
      resumeToken.length < 20
    ) {
      return;
    }

    try {
      window.localStorage.setItem(
        resumeStorageKey,
        resumeToken,
      );
    } catch (_error) {
      setStatus(
        (
          "Server autosave is active, " +
          "but automatic browser resume " +
          "is unavailable."
        ),
        "error",
      );
    }
  }

  function formatSavedTime(value) {
    const savedAt =
      new Date(value);

    if (
      Number.isNaN(
        savedAt.getTime(),
      )
    ) {
      return "Progress saved.";
    }

    return (
      "Progress saved at " +
      savedAt.toLocaleTimeString(
        [],
        {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        },
      ) +
      "."
    );
  }

  async function saveProgress({
    force = false,
    keepalive = false,
  } = {}) {
    if (
      !initialized ||
      stopped
    ) {
      return;
    }

    if (saveInFlight) {
      saveQueued = true;
      return;
    }

    const responses =
      collectResponses();

    const snapshot =
      JSON.stringify(responses);

    if (
      !force &&
      snapshot === lastSavedSnapshot
    ) {
      return;
    }

    if (!navigator.onLine) {
      writeLocalDraft(responses);

      setStatus(
        (
          "Offline. Your latest answers " +
          "are backed up on this device."
        ),
        "offline",
      );

      return;
    }

    saveInFlight = true;

    setStatus(
      "Saving answers…",
      "saving",
    );

    try {
      const response = await fetch(
        autosaveUrl,
        {
          method: "POST",
          credentials: "same-origin",
          keepalive,
          headers: {
            Accept: "application/json",
            "Content-Type":
              "application/json",
            "X-CSRFToken":
              csrfToken,
          },
          body: JSON.stringify({
            responses,
          }),
        },
      );

      const payload = await response
        .json()
        .catch(() => null);

      if (
        response.status === 409 &&
        payload?.submitted
      ) {
        stopped = true;
        clearLocalDraft();

        if (
          sessionRoot.dataset
            .evidenceUploadPending
          !== "true"
        ) {
          window.location.assign(
            submittedUrl,
          );
        }

        return;
      }

      if (!response.ok) {
        writeLocalDraft(
          collectResponses(),
        );

        setStatus(
          (
            "Answers are backed up on " +
            "this device while server " +
            "saving retries."
          ),
          "error",
        );

        return;
      }

      lastSavedSnapshot = snapshot;

      const currentResponses =
        collectResponses();

      if (
        JSON.stringify(
          currentResponses,
        ) === snapshot
      ) {
        clearLocalDraft();
      } else {
        writeLocalDraft(
          currentResponses,
        );

        saveQueued = true;
      }

      setStatus(
        formatSavedTime(
          payload.last_saved_at,
        ),
        "saved",
      );
    } catch (_error) {
      writeLocalDraft(
        collectResponses(),
      );

      setStatus(
        (
          "Connection interrupted. Your " +
          "latest answers are backed up " +
          "on this device."
        ),
        "offline",
      );
    } finally {
      saveInFlight = false;

      if (
        saveQueued &&
        !stopped
      ) {
        saveQueued = false;
        void saveProgress();
      }
    }
  }

  function scheduleSave() {
    window.clearTimeout(
      saveTimer,
    );

    writeLocalDraft(
      collectResponses(),
    );

    setStatus(
      "Changes waiting to save…",
      "pending",
    );

    saveTimer = window.setTimeout(
      () => {
        void saveProgress();
      },
      AUTOSAVE_DELAY_MS,
    );
  }

  function initializeAutosave(
    serverState = {},
  ) {
    if (initialized) {
      return;
    }

    initialized = true;

    resumeToken =
      serverState.resumeToken ||
      sessionRoot.dataset.resumeToken ||
      "";

    rememberResumeToken();

    const localDraft =
      readLocalDraft();

    if (localDraft) {
      applyResponses(
        localDraft.responses,
      );

      setStatus(
        (
          "Recovered answers from this " +
          "device. Saving them to the " +
          "server…"
        ),
        "saving",
      );

      void saveProgress({
        force: true,
      });

      return;
    }

    lastSavedSnapshot =
      JSON.stringify(
        collectResponses(),
      );

    if (
      serverState.lastSavedAt
    ) {
      setStatus(
        formatSavedTime(
          serverState.lastSavedAt,
        ),
        "saved",
      );
    }
  }

  examForm.addEventListener(
    "input",
    scheduleSave,
  );

  examForm.addEventListener(
    "change",
    scheduleSave,
  );

  examForm.addEventListener(
    "submit",
    (event) => {
      if (
        event.defaultPrevented
      ) {
        return;
      }

      stopped = true;

      window.clearTimeout(
        saveTimer,
      );
    },
  );

  document.addEventListener(
    "mau-soap:questions-loaded",
    (event) => {
      initializeAutosave(
        event.detail,
      );
    },
    {
      once: true,
    },
  );

  document.addEventListener(
    "visibilitychange",
    () => {
      if (
        document.visibilityState ===
        "hidden"
      ) {
        void saveProgress({
          force: true,
          keepalive: true,
        });
      }
    },
  );

  window.addEventListener(
    "online",
    () => {
      setStatus(
        (
          "Connection restored. " +
          "Saving answers…"
        ),
        "saving",
      );

      void saveProgress({
        force: true,
      });
    },
  );

  window.addEventListener(
    "pagehide",
    () => {
      void saveProgress({
        force: true,
        keepalive: true,
      });
    },
  );

  window.setInterval(
    () => {
      void saveProgress();
    },
    AUTOSAVE_INTERVAL_MS,
  );

  if (
    examForm.querySelector(
      "[name^='question_']",
    )
  ) {
    initializeAutosave();
  }
})();