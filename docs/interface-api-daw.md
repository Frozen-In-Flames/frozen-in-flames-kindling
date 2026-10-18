# Interface, API, and DAW Integration (Part 14)

## Interface (14.1)

The interface contract: prompt + lyrics with section markers; direct
tempo/key/structure/mood/instrumentation/energy controls; scene
timeline (sections, parts, lyrics, automation); region selection +
edit requests; asset library (voices, instruments, presets) and artist
profile with evidence; take/version comparison, undo, branch; and an
explanation for every generated choice with correction. The API below
is the source of truth: every interface control maps to an endpoint,
and the OpenAPI spec is generated from the handler registry so they
cannot drift.

## API (14.2)

Versioned (`v1`), in `kindling/api/handlers.py`: scene create/read/
update, render and edit jobs, job status/cancellation, asset register/
list/get, profile get/register, export submit. `openapi_spec()`
generates the OpenAPI 3.0 description from the same registry.
Behavior stays stable within the major version.

## CLI and local app (14.3)

`kindling/api/cli.py`: `kindling render scene.json --out out.wav
--tier draft --seed 0` renders reproducibly (same handlers as the
API, so CLI output matches interface output); `kindling api-spec`;
`kindling daw-export`. Runs on the Draft tier with the deterministic
reference renderer.

## DAW bridge (14.4)

Phase one, in `kindling/api/daw.py`: export stems (24-bit WAV, all
from 0) with a tempo/meter map and README; import MIDI to a scene;
import stems as referenced audio. Phase two (plugin) is MAY and not
built; the bridge format is documented for it.
