const form = document.getElementById("hb-form");
const jobStatus = document.getElementById("job-status");
const logOutput = document.getElementById("log-output");
const scanBtn = document.getElementById("scan-btn");
const stopBtn = document.getElementById("stop-btn");
const hbRestartBtn = document.getElementById("hb-restart-btn");
const piRebootBtn = document.getElementById("pi-reboot-btn");
const titlesList = document.getElementById("titles-list");
const titlesJson = document.getElementById("titles-json");
const subtitleTrack = document.getElementById("subtitle-track");
const dvdTitle = document.getElementById("dvd-title");

let scanData = null;

function updateTitlesInput() {
  const checked = [...document.querySelectorAll('input[name="title-checkbox"]:checked')];
  const payload = checked.map((el) => {
    const row = el.closest(".title-row");
    const filename = row ? row.querySelector('input[name="title-filename"]') : null;
    return {
      number: el.value,
      filename: filename ? filename.value : "",
    };
  });
  titlesJson.value = JSON.stringify(payload);
  updateSubtitleOptions(payload.length > 0 ? payload[0].number : null);
}

function updateSubtitleOptions(titleNumber) {
  subtitleTrack.innerHTML = '<option value="none">None</option>';
  if (!scanData || !titleNumber) {
    return;
  }
  const title = scanData.titles.find((t) => String(t.number) === String(titleNumber));
  if (!title || !title.subtitles) {
    return;
  }
  title.subtitles.forEach((sub) => {
    const opt = document.createElement("option");
    opt.value = String(sub.index);
    opt.textContent = `Track ${sub.index}: ${sub.label}`;
    subtitleTrack.appendChild(opt);
  });
}

function renderTitles(titles, longest) {
  titlesList.innerHTML = "";
  if (!titles || titles.length === 0) {
    titlesList.textContent = "No titles found.";
    return;
  }
  const defaultTitle = longest || titles[0].number;
  titles.forEach((title) => {
    const row = document.createElement("div");
    row.className = "title-row";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.name = "title-checkbox";
    checkbox.value = String(title.number);
    if (title.number === defaultTitle) {
      checkbox.checked = true;
    }
    checkbox.addEventListener("change", updateTitlesInput);

    const name = document.createElement("div");
    name.textContent = `${title.name} (#${title.number})`;
    const duration = document.createElement("small");
    duration.textContent = title.duration || "unknown";

    const filename = document.createElement("input");
    filename.name = "title-filename";
    filename.className = "title-filename";
    filename.placeholder = "Optional filename";
    filename.addEventListener("input", updateTitlesInput);

    row.appendChild(checkbox);
    row.appendChild(name);
    row.appendChild(duration);
    row.appendChild(filename);
    titlesList.appendChild(row);
  });
  updateTitlesInput();
}

async function fetchStatus() {
  const res = await fetch("/status");
  const data = await res.json();
  jobStatus.textContent = JSON.stringify(data.job, null, 2);
  if (data.log_tail) {
    logOutput.textContent = data.log_tail;
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const formData = new FormData(form);
  const res = await fetch("/start", { method: "POST", body: formData });
  const data = await res.json();
  if (!data.ok) {
    alert(data.error || "Failed to start job.");
  }
  fetchStatus();
});

scanBtn.addEventListener("click", async () => {
  logOutput.textContent = "Scanning... this can take a minute.";
  const res = await fetch("/scan");
  const data = await res.json();
  logOutput.textContent = data.output || "No output.";
  if (data.titles) {
    scanData = { titles: data.titles };
    renderTitles(data.titles, data.longest);
  }
  if (data.dvd_title && dvdTitle) {
    dvdTitle.textContent = data.dvd_title;
  }
});

stopBtn.addEventListener("click", async () => {
  await fetch("/stop", { method: "POST" });
  fetchStatus();
});

hbRestartBtn.addEventListener("click", async () => {
  await fetch("/handbrake/restart", { method: "POST" });
  fetchStatus();
});

piRebootBtn.addEventListener("click", async () => {
  if (!confirm("Reboot the Pi now?")) {
    return;
  }
  await fetch("/pi/reboot", { method: "POST" });
});

// ── Baseball Sim Deploy ──
const deployBtn = document.getElementById("deploy-btn");
const deployStatus = document.getElementById("deploy-status");
const deployLog = document.getElementById("deploy-log");

if (deployBtn) {
  deployBtn.addEventListener("click", async () => {
    if (!confirm("Pull & redeploy Baseball Sim?")) return;
    deployStatus.textContent = "Starting deploy...";
    const res = await fetch("/deploy/start", { method: "POST" });
    const data = await res.json();
    if (!data.ok) alert(data.error || "Deploy failed.");
    fetchDeployStatus();
  });
}

async function fetchDeployStatus() {
  try {
    const res = await fetch("/deploy/status");
    const data = await res.json();
    deployStatus.textContent = JSON.stringify(data.job, null, 2);
    if (data.log_tail) deployLog.textContent = data.log_tail;
  } catch (e) {}
}

// ── MyFlow Deploy ──
const mfDeployBtn = document.getElementById("mf-deploy-btn");
const mfDeployStatus = document.getElementById("mf-deploy-status");
const mfDeployLog = document.getElementById("mf-deploy-log");
const mfServiceStatus = document.getElementById("mf-service-status");
const mfCommit = document.getElementById("mf-commit");

if (mfDeployBtn) {
  mfDeployBtn.addEventListener("click", async () => {
    if (!confirm("Pull & redeploy MyFlow?")) return;
    mfDeployStatus.textContent = "Starting deploy...";
    const res = await fetch("/myflow/deploy/start", { method: "POST" });
    const data = await res.json();
    if (!data.ok) alert(data.error || "Deploy failed.");
    fetchMyFlowDeployStatus();
  });
}

async function fetchMyFlowDeployStatus() {
  try {
    const res = await fetch("/myflow/deploy/status");
    const data = await res.json();
    mfDeployStatus.textContent = JSON.stringify(data.job, null, 2);
    if (data.log_tail) mfDeployLog.textContent = data.log_tail;
  } catch (e) {}
}

async function fetchMyFlowServiceStatus() {
  try {
    const res = await fetch("/myflow/status");
    const data = await res.json();
    if (mfServiceStatus) mfServiceStatus.textContent = data.status;
    if (mfCommit && data.commit) {
      mfCommit.textContent = data.commit + " — " + (data.message || "") + " (" + (data.last_pull || "") + ")";
    }
  } catch (e) {}
}

setInterval(fetchStatus, 5000);
setInterval(fetchDeployStatus, 5000);
setInterval(fetchMyFlowDeployStatus, 5000);
setInterval(fetchMyFlowServiceStatus, 15000);
fetchStatus();
fetchDeployStatus();
fetchMyFlowDeployStatus();
fetchMyFlowServiceStatus();
