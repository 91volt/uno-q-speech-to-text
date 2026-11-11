const $ = (id) => document.getElementById(id);
let recording = false,
  busy = false,
  stream,
  context,
  node,
  source,
  mute,
  chunks = [],
  sampleRate = 16000,
  heard = false,
  silence = 0,
  total = 0,
  timer;
let flushing = false,
  flushResolve;
function status(text, error = false) {
  $("status").textContent = text;
  $("status").className = error ? "error" : "";
}
function controls() {
  $("record").disabled = recording || busy;
  $("stop").disabled = !recording;
  $("file").disabled = recording || busy;
}
async function shutdown() {
  clearTimeout(timer);
  recording = false;
  controls();
  if (node) {
    node.port.onmessage = null;
    node.disconnect();
  }
  source?.disconnect();
  mute?.disconnect();
  stream?.getTracks().forEach((t) => t.stop());
  if (context && context.state !== "closed") await context.close();
  $("level").value = 0;
}
async function pcm16(audio, rate) {
  if (rate !== 16000) {
    const offline = new OfflineAudioContext(
      1,
      Math.ceil((audio.length * 16000) / rate),
      16000,
    );
    const buffer = offline.createBuffer(1, audio.length, rate);
    buffer.copyToChannel(audio, 0);
    const src = offline.createBufferSource();
    src.buffer = buffer;
    src.connect(offline.destination);
    src.start();
    audio = (await offline.startRendering()).getChannelData(0);
  }
  const bytes = new ArrayBuffer(audio.length * 2),
    view = new DataView(bytes);
  for (let i = 0; i < audio.length; i++) {
    const x = Math.max(-1, Math.min(1, audio[i]));
    view.setInt16(i * 2, Math.round(x * (x < 0 ? 32768 : 32767)), true);
  }
  return bytes;
}
async function submit(audio, rate) {
  busy = true;
  controls();
  status("Transcribing on UNO Q…");
  const start = performance.now();
  try {
    const bytes = await pcm16(audio, rate);
    const res = await fetch("/api/transcribe", {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: bytes,
    });
    const result = await res.json();
    if (!res.ok) throw Error(result.error || `Request failed (${res.status})`);
    if (result.text.trim())
      $("transcript").textContent +=
        ($("transcript").textContent ? "\n\n" : "") + result.text.trim();
    status(
      result.text.trim()
        ? "Done. Ready for another phrase."
        : "No speech recognized. Try speaking closer to the microphone.",
    );
    $("metrics").textContent =
      `${result.audio_seconds.toFixed(1)} s audio · ${result.processing_seconds.toFixed(2)} s on board · ${result.real_time_factor.toFixed(2)}× real time · ${((performance.now() - start) / 1000).toFixed(2)} s total`;
  } catch (e) {
    status(e.message, true);
  } finally {
    busy = false;
    controls();
  }
}
async function finish() {
  if (!recording) return;
  // Set busy before awaiting shutdown so another recording cannot start midway.
  busy = true;
  recording = false;
  controls();
  flushing = true;
  if (node)
    await new Promise((resolve) => {
      flushResolve = resolve;
      node.port.postMessage("flush");
      setTimeout(resolve, 250);
    });
  flushing = false;
  flushResolve = null;
  await shutdown();
  const length = chunks.reduce((n, c) => n + c.length, 0);
  if (length < sampleRate * 0.1) {
    busy = false;
    controls();
    status("Recording was too short. Try again.");
    return;
  }
  const audio = new Float32Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    audio.set(chunk, offset);
    offset += chunk.length;
  }
  chunks = [];
  await submit(audio, sampleRate);
}
$("record").onclick = async () => {
  if (recording || busy) return;
  busy = true;
  controls();
  try {
    if (!navigator.mediaDevices?.getUserMedia)
      throw Error(
        "Microphone access needs localhost or HTTPS. Use the ADB forwarding URL.",
      );
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    context = new AudioContext();
    await context.audioWorklet.addModule("/static/capture.js");
    await context.resume();
    sampleRate = context.sampleRate;
    source = context.createMediaStreamSource(stream);
    node = new AudioWorkletNode(context, "capture");
    mute = context.createGain();
    mute.gain.value = 0;
    source.connect(node).connect(mute).connect(context.destination);
    chunks = [];
    heard = false;
    silence = 0;
    total = 0;
    recording = true;
    busy = false;
    controls();
    status("Listening… speak now.");
    node.port.onmessage = ({ data }) => {
      if (data === "flushed") {
        flushResolve?.();
        return;
      }
      if (!recording && !flushing) return;
      chunks.push(data);
      total += data.length / sampleRate;
      if (!recording) return;
      let power = 0;
      for (const x of data) power += x * x;
      const rms = Math.sqrt(power / data.length);
      $("level").value = rms;
      if (rms > 0.009) {
        heard = true;
        silence = 0;
      } else if (heard) silence += data.length / sampleRate;
      if (total >= 25 || ($("autostop").checked && heard && silence >= 1.0))
        finish();
    };
    timer = setTimeout(finish, 26000);
  } catch (e) {
    await shutdown();
    busy = false;
    controls();
    status(e.message, true);
  }
};
$("stop").onclick = finish;
$("file").onchange = async () => {
  const file = $("file").files[0];
  if (!file) return;
  if (file.size > 20 * 1024 * 1024) {
    status("Please select a file smaller than 20 MB.", true);
    return;
  }
  busy = true;
  controls();
  let decoder;
  try {
    decoder = new AudioContext();
    const audio = await decoder.decodeAudioData(await file.arrayBuffer());
    if (audio.duration > 30)
      throw Error("Please select a recording of 30 seconds or less.");
    const mono = new Float32Array(audio.length);
    for (let c = 0; c < audio.numberOfChannels; c++) {
      const channel = audio.getChannelData(c);
      for (let i = 0; i < mono.length; i++)
        mono[i] += channel[i] / audio.numberOfChannels;
    }
    await submit(mono, audio.sampleRate);
  } catch (e) {
    status(e.message, true);
  } finally {
    await decoder?.close();
    busy = false;
    controls();
    $("file").value = "";
  }
};
$("clear").onclick = () => {
  $("transcript").textContent = "";
  $("metrics").textContent = "";
};
$("copy").onclick = async () => {
  try {
    await navigator.clipboard.writeText($("transcript").textContent);
    status("Transcript copied.");
  } catch (e) {
    status("Select the transcript and copy it manually.", true);
  }
};
window.addEventListener("pagehide", () => {
  recording = false;
  stream?.getTracks().forEach((t) => t.stop());
  context?.close();
});
try {
  const res = await fetch("/api/health");
  if (!res.ok) throw Error("Board is unavailable.");
  const h = await res.json();
  if (!h.ready) throw Error(h.error || "The speech model is not loaded.");
  $("engine").textContent = h.engine + " · English";
  status("Ready. All recognition runs on your UNO Q.");
  controls();
} catch (e) {
  $("file").disabled = true;
  status(e.message, true);
}
