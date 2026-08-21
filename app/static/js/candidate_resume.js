(() => {
  const entry = document.getElementById(
    "candidate-entry",
  );

  if (!entry) {
    return;
  }

  const status = document.getElementById(
    "resume-status",
  );

  const storageKey =
    `mau-soap:resume:${entry.dataset.examToken}`;

  let resumeToken;

  try {
    resumeToken =
      window.localStorage.getItem(
        storageKey,
      );
  } catch (_error) {
    return;
  }

  if (
    !resumeToken ||
    resumeToken.length < 20
  ) {
    if (resumeToken) {
      window.localStorage.removeItem(
        storageKey,
      );
    }

    return;
  }

  status.hidden = false;

  fetch(entry.dataset.resumeUrl, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken":
        entry.dataset.csrfToken,
    },
    body: JSON.stringify({
      resume_token: resumeToken,
    }),
  })
    .then(async (response) => {
      const payload = await response
        .json()
        .catch(() => null);

      if (
        response.ok &&
        payload?.redirect_url
      ) {
        window.location.replace(
          payload.redirect_url,
        );
        return;
      }

      if (
        response.status === 400 ||
        response.status === 404
      ) {
        window.localStorage.removeItem(
          storageKey,
        );

        status.hidden = true;
        return;
      }

      status.textContent =
        "A saved attempt exists, but it " +
        "could not be restored yet. You " +
        "can retry by refreshing this page.";
    })
    .catch(() => {
      status.textContent =
        "A saved attempt exists, but the " +
        "server could not be reached. " +
        "Reconnect and refresh this page " +
        "to resume.";
    });
})();