// Asset library persisted in IndexedDB.
// Records mirror the Python library semantics: versioned, content-addressed
// audio blobs, consent on voice characters, cascading delete.

const DB_NAME = "kindling";
const DB_VERSION = 1;

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains("assets")) {
        db.createObjectStore("assets", { keyPath: "id" });
      }
      if (!db.objectStoreNames.contains("audio")) {
        db.createObjectStore("audio", { keyPath: "sha" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function tx(db, stores, mode, fn) {
  return new Promise((resolve, reject) => {
    const t = db.transaction(stores, mode);
    t.oncomplete = () => resolve();
    t.onerror = () => reject(t.error);
    fn(t);
  });
}

function getAll(db, store) {
  return new Promise((resolve, reject) => {
    const out = [];
    const t = db.transaction(store, "readonly");
    const req = t.objectStore(store).openCursor();
    req.onsuccess = () => {
      const c = req.result;
      if (c) { out.push(c.value); c.continue(); }
      else resolve(out);
    };
    req.onerror = () => reject(req.error);
  });
}

function getOne(db, store, key) {
  return new Promise((resolve, reject) => {
    const t = db.transaction(store, "readonly");
    const req = t.objectStore(store).get(key);
    req.onsuccess = () => resolve(req.result || null);
    req.onerror = () => reject(req.error);
  });
}

export async function sha256Hex(float32) {
  // Hash the 16-bit quantized bytes, matching the content-address idea.
  const n = float32.length;
  const bytes = new Uint8Array(n * 2);
  const dv = new DataView(bytes.buffer);
  for (let i = 0; i < n; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    dv.setInt16(i * 2, Math.round(s * 32767), true);
  }
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, "0")).join("");
}

export function slugify(name) {
  return (name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "asset");
}

const PREFIX = { voice: "voice_", instrument: "inst_", preset: "preset_" };

export async function saveAsset({ kind, name, payload, audioMono, sampleRate, consent }) {
  const db = await openDb();
  const id = PREFIX[kind] + slugify(name);
  const existing = await getOne(db, "assets", id);
  const version = existing ? `v${parseInt(existing.version.slice(1), 10) + 1}` : "v1";
  let audioSha = null;
  if (audioMono) {
    audioSha = await sha256Hex(audioMono);
    const has = await getOne(db, "audio", audioSha);
    if (!has) {
      await tx(db, ["audio"], "readwrite", t => {
        t.objectStore("audio").put({ sha: audioSha, sampleRate, pcm: audioMono });
      });
    }
  }
  const record = {
    id, kind: "kindling/asset-record", assetKind: kind, name,
    version, owner: "owner", createdAt: new Date().toISOString(),
    sourceAudioSha: audioSha, consent: consent || null,
    payload, parent: existing ? existing.id : null,
  };
  await tx(db, ["assets"], "readwrite", t => {
    t.objectStore("assets").put(record);
  });
  return record;
}

export async function listAssets() {
  const db = await openDb();
  const all = await getAll(db, "assets");
  // Factory seeds first (the default voice), then newest first.
  // User assets are never reordered or removed by seeding.
  return all.sort((a, b) =>
    ((b.factory ? 1 : 0) - (a.factory ? 1 : 0)) ||
    b.createdAt.localeCompare(a.createdAt));
}

export async function hasAsset(id) {
  const db = await openDb();
  return (await getOne(db, "assets", id)) !== null;
}

export async function putRecord(record) {
  const db = await openDb();
  await tx(db, ["assets"], "readwrite", t => {
    t.objectStore("assets").put(record);
  });
  return record;
}

export async function getAsset(id) {
  const db = await openDb();
  return getOne(db, "assets", id);
}

export async function getAudio(sha) {
  const db = await openDb();
  return getOne(db, "audio", sha);
}

export async function renameAsset(id, name) {
  const db = await openDb();
  const rec = await getOne(db, "assets", id);
  if (!rec) throw new Error("asset not found");
  rec.name = name;
  await tx(db, ["assets"], "readwrite", t => {
    t.objectStore("assets").put(rec);
  });
  return rec;
}

export async function deleteAsset(id) {
  const db = await openDb();
  const rec = await getOne(db, "assets", id);
  if (!rec) return;
  await tx(db, ["assets"], "readwrite", t => {
    t.objectStore("assets").delete(id);
  });
  // Cascade: drop the audio blob when no other asset references it.
  if (rec.sourceAudioSha) {
    const rest = await getAll(db, "assets");
    const stillUsed = rest.some(r => r.sourceAudioSha === rec.sourceAudioSha);
    if (!stillUsed) {
      await tx(db, ["audio"], "readwrite", t => {
        t.objectStore("audio").delete(rec.sourceAudioSha);
      });
    }
  }
}
