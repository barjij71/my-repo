import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import vm from "node:vm";

class Element {
  constructor(id = "") {
    this.id = id;
    this.children = [];
    this.dataset = {};
    this.disabled = false;
    this.hidden = false;
    this.value = "";
    this.textContent = "";
    this.style = {};
    this.listeners = new Map();
    this.attributes = new Map();
    this.classes = new Set();
    this.classList = {
      add: (...names) => names.forEach((name) => this.classes.add(name)),
      remove: (...names) => names.forEach((name) => this.classes.delete(name)),
      toggle: (name, force) => {
        const enabled = force === undefined ? !this.classes.has(name) : force;
        if (enabled) this.classes.add(name);
        else this.classes.delete(name);
        return enabled;
      },
    };
  }

  get lastChild() {
    return this.children.at(-1) || null;
  }

  addEventListener(name, callback) {
    const listeners = this.listeners.get(name) || [];
    listeners.push(callback);
    this.listeners.set(name, listeners);
  }

  setAttribute(name, value) {
    this.attributes.set(name, value);
  }

  append(...items) {
    this.children.push(...items);
  }

  prepend(item) {
    this.children.unshift(item);
  }

  replaceChildren(...items) {
    this.children = [...items];
  }

  remove() {
    this.parent?.children.splice(this.parent.children.indexOf(this), 1);
  }

  focus() {}

  click() {
    for (const listener of this.listeners.get("click") || []) {
      listener({ target: this, preventDefault() {} });
    }
  }
}

class FakeRecognition {
  static instances = [];

  constructor() {
    this.startCount = 0;
    FakeRecognition.instances.push(this);
  }

  start() {
    this.startCount++;
  }

  stop() {
    setTimeout(() => this.onend?.(), 0);
  }

  recognize(transcript) {
    this.onresult?.({ results: [[{ transcript }]] });
  }
}

class FakeAudio {
  static instances = [];
  static failNextPlay = false;

  constructor(url) {
    this.url = url;
    FakeAudio.instances.push(this);
  }

  play() {
    if (FakeAudio.failNextPlay) {
      FakeAudio.failNextPlay = false;
      return Promise.reject(new Error("mock playback failure"));
    }
    return Promise.resolve();
  }

  pause() {}
  removeAttribute() {}
  load() {}
}

const elements = new Map();
const document = {
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, new Element(id));
    return elements.get(id);
  },
  createElement() {
    return new Element();
  },
  createTextNode(text) {
    return { textContent: text };
  },
  querySelectorAll() {
    return [];
  },
  querySelector() {
    return null;
  },
};

Object.assign(globalThis, {
  document,
  window: {
    SpeechRecognition: FakeRecognition,
    addEventListener() {},
    crypto: { randomUUID: () => "ui-test-request" },
  },
  Audio: FakeAudio,
  prompt: () => "local-ui-test-token",
  setInterval: () => 1,
  fetch: async (path, options = {}) => {
    if (options.headers?.Authorization) {
      globalThis.authorizationHeaders.push(options.headers.Authorization);
    }
    if (path === "/api/status") {
      return jsonResponse({
        ready: true,
        provider_statuses: [],
        configured_providers: [],
      });
    }
    if (path === "/api/system") {
      return jsonResponse({
        cpu_percent: 10,
        memory_percent: 30,
        disk_percent: 40,
        uptime: "1h 2m",
        network_connected: true,
        battery_percent: null,
        battery_plugged: null,
      });
    }
    if (path === "/api/voice/status") return jsonResponse({ ready: true, engine: "piper" });
    if (path === "/api/chat/history") return jsonResponse({ messages: [], count: 0, limit: 500 });
    if (path === "/api/chat") {
      globalThis.chatRequests++;
      return jsonResponse({ reply: "A mocked reply.", history_saved: true });
    }
    if (path === "/api/voice/synthesize") {
      if (options.signal?.aborted) throw new DOMException("Aborted", "AbortError");
      return {
        ok: true,
        headers: { get: () => null },
        blob: async () => new Blob(["mock audio"], { type: "audio/wav" }),
      };
    }
    throw new Error(`Unexpected request: ${path}`);
  },
  chatRequests: 0,
  authorizationHeaders: [],
});
Object.defineProperty(globalThis, "navigator", {
  configurable: true,
  value: { mediaDevices: { enumerateDevices: async () => [], addEventListener() {} } },
});
URL.createObjectURL = () => "blob:mock-audio";
URL.revokeObjectURL = () => {};

function jsonResponse(body) {
  return { ok: true, json: async () => body };
}

async function waitFor(predicate, message) {
  const deadline = Date.now() + 3000;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 10));
  }
  assert.fail(message);
}

const html = readFileSync(resolve(process.argv[2]), "utf8");
const start = html.indexOf("<script>");
const end = html.lastIndexOf("</script>");
assert.ok(start >= 0 && end > start, "dashboard inline script exists");
vm.runInThisContext(html.slice(start + "<script>".length, end), {
  filename: "static/index.html",
});

elements.get("connect").click();
await waitFor(() => elements.get("systemStatus").dataset.state === "connected", "dashboard connects");
assert.equal(
  globalThis.authorizationHeaders[0],
  "Bearer local-ui-test-token",
  "a click Event is ignored and the prompted token is used for authenticated requests",
);
elements.get("liveToggle").click();
assert.equal(FakeRecognition.instances.length, 1, "LIVE starts one recognition session");

FakeRecognition.instances[0].recognize("hello JARVIS");
FakeRecognition.instances[0].recognize("duplicate result");
await waitFor(() => FakeAudio.instances.length === 1, "synthesis reaches audio playback");
assert.equal(globalThis.chatRequests, 1, "one recognition result submits one chat request");
assert.equal(FakeRecognition.instances.length, 1, "recognition stays stopped during playback");
await new Promise((resolvePromise) => setTimeout(resolvePromise, 20));
assert.equal(
  FakeRecognition.instances.length,
  1,
  "recognition does not resume until the playback completion event",
);

FakeAudio.instances[0].onended();
await waitFor(() => FakeRecognition.instances.length === 2, "recognition resumes after playback");
assert.equal(FakeRecognition.instances.length, 2, "playback completion starts exactly one new session");

FakeAudio.failNextPlay = true;
FakeRecognition.instances[1].recognize("test playback recovery");
await waitFor(() => globalThis.chatRequests === 2, "second chat request completes");
await waitFor(() => FakeRecognition.instances.length === 3, "recognition recovers after playback failure");
assert.equal(FakeRecognition.instances.length, 3, "playback failure does not duplicate recognition");

FakeRecognition.instances[2].recognize("test user cancellation");
await waitFor(() => FakeAudio.instances.length === 3, "third response starts playback");
elements.get("stopVoice").click();
await waitFor(() => FakeRecognition.instances.length === 4, "recognition resumes after speech cancellation");
assert.equal(globalThis.chatRequests, 3, "cancellation does not resubmit the recognized message");
console.log("Dashboard voice lifecycle passed: deferred resume, duplicate-result guard, playback failure recovery, and cancellation.");
