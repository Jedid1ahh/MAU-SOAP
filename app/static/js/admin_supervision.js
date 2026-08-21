const feed = document.getElementById(
  "supervision-feed",
);

if (feed) {
  const eventsUrl = feed.dataset.eventsUrl;

  const status = document.getElementById(
    "supervision-feed-status",
  );
  const list = document.getElementById(
    "supervision-event-list",
  );
  const empty = document.getElementById(
    "supervision-empty",
  );

  const cards = new Map();

  function detail(label, value) {
    const row = document.createElement("div");
    const term = document.createElement("dt");
    const description =
      document.createElement("dd");

    term.textContent = label;
    description.textContent = value;

    row.append(term, description);

    return row;
  }

  function evidencePanel(event) {
    const panel = document.createElement("div");
    panel.className = "evidence-panel";

    if (event.evidence_status === "recording") {
      panel.textContent =
        "Face still absent or evidence upload pending…";

      return panel;
    }

    if (
      event.evidence_status === "unavailable"
    ) {
      panel.textContent =
        "This browser could not record video evidence.";

      return panel;
    }

    if (event.evidence_status === "expired") {
      panel.textContent =
        "Evidence deleted after the 30-day retention period.";

      return panel;
    }

    if (!event.evidence) {
      return panel;
    }

    const video = document.createElement("video");
    video.controls = true;
    video.preload = "metadata";
    video.src = event.evidence.view_url;
    video.className = "evidence-video";

    const timing = document.createElement("p");
    const duration = (
      event.evidence.duration_ms / 1000
    ).toFixed(1);

    timing.textContent =
      `Candidate-device clip: ${
        new Date(
          event.evidence.started_at,
        ).toLocaleString()
      } – ${
        new Date(
          event.evidence.ended_at,
        ).toLocaleString()
      } (${duration} seconds). Received by server: ${
        new Date(
          event.evidence.uploaded_at,
        ).toLocaleString()
      }.`;

    const download =
      document.createElement("a");

    download.className =
      "secondary-button button-auto";
    download.href =
      event.evidence.download_url;
    download.textContent =
      "Download evidence";

    panel.append(
      video,
      timing,
      download,
    );

    return panel;
  }

  function eventCard(event) {
    const article =
      document.createElement("article");

    article.className =
      "supervision-event";
    article.dataset.warningId =
      String(event.id);

    const heading =
      document.createElement("div");
    heading.className = "card-heading";

    const title =
      document.createElement("strong");
    title.textContent =
      `${event.candidate_name} · ` +
      `${event.course_code}`;

    const badge =
      document.createElement("span");
    badge.className =
      "status-badge status-locked";
    badge.textContent =
      event.violation_type.replaceAll(
        "_",
        " ",
      );

    heading.append(title, badge);

    const message =
      document.createElement("p");
    message.textContent = event.message;

    const metadata =
      document.createElement("dl");
    metadata.className =
      "metadata-list " +
      "supervision-event-metadata";

    metadata.append(
      detail(
        "Candidate",
        event.candidate_email,
      ),
      detail(
        "Examination",
        event.exam_title,
      ),
      detail(
        "Detected",
        new Date(
          event.occurred_at,
        ).toLocaleString(),
      ),
      detail(
        "Warnings",
        `${event.warning_count} of 3`,
      ),
    );

    article.append(
      heading,
      message,
      metadata,
      evidencePanel(event),
    );

    return article;
  }

  function upsert(event) {
    const signature = JSON.stringify(event);
    const previous = cards.get(event.id);

    if (
      previous?.signature === signature
    ) {
      return;
    }

    const replacement = eventCard(event);

    if (previous) {
      previous.element.replaceWith(
        replacement,
      );
    } else {
      list.prepend(replacement);
    }

    cards.set(event.id, {
      element: replacement,
      signature,
    });
  }

  async function refresh() {
    try {
      const response = await fetch(
        eventsUrl,
        {
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
          },
        },
      );

      if (!response.ok) {
        throw new Error(
          "feed request failed",
        );
      }

      const payload =
        await response.json();

      payload.events
        .slice()
        .reverse()
        .forEach(upsert);

      empty.hidden =
        payload.events.length > 0;

      status.textContent = "Live";
      status.classList.add(
        "status-live",
      );

    } catch (_error) {
      status.textContent =
        "Reconnecting…";

      status.classList.remove(
        "status-live",
      );
    }
  }

  void refresh();

  window.setInterval(
    refresh,
    3000,
  );
}