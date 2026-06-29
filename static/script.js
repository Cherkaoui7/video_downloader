const urlInput = document.getElementById("urlInput");
const downloadBtn = document.getElementById("downloadBtn");
const statusDiv = document.getElementById("status");
const cookieToggle = document.getElementById("cookieToggle");
const cookieBody = document.getElementById("cookieBody");
const cookieBadge = document.getElementById("cookieBadge");
const cookieInput = document.getElementById("cookieInput");
const cookieFilename = document.getElementById("cookieFilename");
const removeCookieBtn = document.getElementById("removeCookieBtn");

function showStatus(msg, type) {
  statusDiv.textContent = msg;
  statusDiv.className = "status " + type;
  statusDiv.classList.remove("hidden");
}

function hideStatus() {
  statusDiv.classList.add("hidden");
}

cookieToggle.addEventListener("click", () => {
  cookieBody.classList.toggle("hidden");
});

async function checkCookieStatus() {
  try {
    const res = await fetch("/cookie-status");
    const data = await res.json();
    if (data.loaded) {
      cookieBadge.textContent = `Loaded (${(data.size / 1024).toFixed(1)} KB)`;
      cookieBadge.className = "cookie-badge loaded";
      removeCookieBtn.classList.remove("hidden");
    } else {
      cookieBadge.textContent = "Not loaded";
      cookieBadge.className = "cookie-badge";
      removeCookieBtn.classList.add("hidden");
    }
  } catch {
    cookieBadge.textContent = "Not loaded";
    cookieBadge.className = "cookie-badge";
  }
}

checkCookieStatus();

cookieInput.addEventListener("change", async () => {
  const file = cookieInput.files[0];
  if (!file) return;

  const form = new FormData();
  form.append("cookie", file);

  try {
    const res = await fetch("/upload-cookie", { method: "POST", body: form });
    const data = await res.json();
    if (res.ok) {
      cookieFilename.textContent = "✓ " + file.name;
      await checkCookieStatus();
      showStatus("Cookies loaded successfully!", "success");
    } else {
      showStatus(data.error || "Failed to upload cookies", "error");
    }
  } catch {
    showStatus("Failed to upload cookies", "error");
  }
});

removeCookieBtn.addEventListener("click", async () => {
  try {
    await fetch("/remove-cookie", { method: "POST" });
    cookieFilename.textContent = "";
    cookieInput.value = "";
    await checkCookieStatus();
    showStatus("Cookies removed.", "info");
  } catch {
    showStatus("Failed to remove cookies", "error");
  }
});

downloadBtn.addEventListener("click", async () => {
  const url = urlInput.value.trim();
  if (!url) {
    showStatus("Please enter a URL.", "error");
    return;
  }

  const quality = document.querySelector('input[name="quality"]:checked').value;

  downloadBtn.disabled = true;
  downloadBtn.innerHTML = '<span class="spinner"></span> Downloading...';
  showStatus("Preparing your download...", "info");

  try {
    const res = await fetch("/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, quality }),
    });
    const data = await res.json();

    if (!res.ok) {
      let msg = data.error || "Download failed.";
      if (msg.length > 200) msg = msg.substring(0, 200) + "...";
      showStatus(msg, "error");
      return;
    }

    showStatus("Download ready! Saving file...", "success");
    const a = document.createElement("a");
    const title = data.title || data.file;
    a.href = "/file/" + encodeURIComponent(data.file) + "?title=" + encodeURIComponent(title);
    a.download = title;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    showStatus("Download started!", "success");
  } catch (e) {
    showStatus("Network error: " + e.message, "error");
  } finally {
    downloadBtn.disabled = false;
    downloadBtn.textContent = "Download";
  }
});

urlInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") downloadBtn.click();
});
