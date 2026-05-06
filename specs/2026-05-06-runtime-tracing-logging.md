# Runtime Tracing and Logging

Date: 2026-05-06
Status: Draft for review

## Goal

Roamer should produce structured logs that can reconstruct one complete request chain
across wake, listen, ASR, local actions, Discord fallback, TTS, audio playback, motion,
perception, Bluetooth, and reminder actions.

The primary debugging workflow should be:

```bash
grep '"request_id":"<id>"' logs/roamer.log
```

That output should show the ordered timeline for a single user request, including timing
for the hardware trigger, VAD endpointing, ASR, routing, fallback delivery, TTS, and
playback.

## Scope

In scope:

- Generic tracing for every action executed through the plugin registry.
- Request ID propagation across daemon requests, wake-triggered requests, and nested actions.
- Detailed phase logs for the voice pipeline.
- Full recognized/sent text in transcript and Discord-related logs when transcript logging is enabled.
- Log rotation and retention through the existing logging config.
- Sensitive token/auth/proxy redaction with leading and trailing characters retained.

Out of scope for this spec:

- Distributed tracing backends.
- Metrics aggregation dashboards.
- Semantic filtering of ASR text before fallback.
- Per-chunk audio or VAD logs.
- Recording or storing raw audio payloads in logs.

## Current Problem

Existing logs are useful but incomplete:

- `listen.asr_transcript` logs final transcript text, but does not show when recording,
  VAD, or ASR started.
- `wake.asr_transcript` logs wake phrase matching, but does not show GPIO trigger timing.
- `converse.route_text` logs routing, but does not by itself prove whether Discord send
  was attempted or completed.
- `speak.playback` summarizes playback, but does not show TTS start/end or audio
  playback start/end.
- Non-converse actions do not have a guaranteed `action.start` / `action.done` pair.

The result is that failures can require guessing which stage stopped the request.

## Architecture

Logging has three layers:

```text
PluginRegistry.run()
  -> generic action tracing for all registered actions

request_context()
  -> request_id propagation across nested calls

capability/service phase logs
  -> domain-specific timing points only the local component can know
```

### Registry-Level Action Tracing

`PluginRegistry.run(action_name, **kwargs)` is the canonical execution boundary for
registered actions. It should emit generic action logs for every registered action:

```text
action.start
action.done
action.exception
```

This must apply to newly registered actions automatically. For example, after:

```python
registry.register("foo.bar", FooBarAction(config))
registry.run("foo.bar", text="hello")
```

the logs must include `action.start` and either `action.done` or `action.exception`
without requiring `FooBarAction` to call `log_event()` itself.

`run_action()` remains a thin compatibility wrapper around `registry.run()` and should
not duplicate action logs.

### Request ID Rules

Rules:

- If a request already has a request ID, keep it for all nested action and phase logs.
- If `PluginRegistry.run()` is called without an active request ID, generate one.
- `serve` should use the inbound `request_id` when present, otherwise generate one.
- `wake` should generate one request ID per accepted SU-03T trigger/listen/route chain.
- Follow-up commands are separate user requests and should get separate request IDs.
- Nested calls such as `converse -> speak -> audio.play` must share the parent request ID.

Request IDs are diagnostic correlation IDs, not security tokens.

## Log Event Contract

Every JSON log line keeps the existing envelope:

```json
{
  "ts": "2026-05-06T13:49:08.132+08:00",
  "level": "INFO",
  "component": "listen",
  "event": "asr_transcript",
  "request_id": "8567276a665d"
}
```

### Generic Action Fields

`action.start`:

```json
{
  "component": "action",
  "event": "action.start",
  "request_id": "8567276a665d",
  "action": "listen",
  "args": {
    "timeout": 8.0,
    "save_audio": null,
    "debug": false,
    "use_endpointing": true
  }
}
```

`action.done`:

```json
{
  "component": "action",
  "event": "action.done",
  "request_id": "8567276a665d",
  "action": "listen",
  "ok": true,
  "error_code": null,
  "duration_ms": 6148.1
}
```

`action.exception`:

```json
{
  "component": "action",
  "event": "action.exception",
  "request_id": "8567276a665d",
  "action": "motion.goto",
  "exception_type": "TimeoutError",
  "message": "command timed out",
  "duration_ms": 3000.4
}
```

### Text Logging Rules

Text fields should be logged in full when `logging.log_transcripts` is true.

This includes:

- recognized ASR transcript text
- wake command text after wake phrase stripping
- routed converse text
- Discord fallback content
- TTS text
- action args containing text-like fields

Text-like keys include:

```text
text
content
input
message
prompt
command_text
```

When `logging.log_transcripts` is false:

- transcript/content fields should be empty strings or omitted, depending on the existing
  event shape.
- timing, route, action, result, and error fields must still be logged.
- content length may be logged as a non-sensitive diagnostic field.

Empty recognized text should not produce transcript events. For example, if ASR returns
`""` or whitespace only, do not emit `listen.asr_transcript` or `wake.asr_transcript`.

### Sensitive Value Rules

Authentication and connection secrets must always be redacted, regardless of
`log_transcripts`.

Sensitive keys include any key containing:

```text
token
secret
password
authorization
proxy
```

Redaction should preserve enough edge characters for debugging:

```text
abcd***wxyz
```

URLs with embedded credentials should redact only the userinfo section and keep host/path
available when possible.

## Required Events

### Wake

Component: `wake`

```text
wake.trigger_wait_start
wake.trigger_hit
wake.trigger_rejected
wake.trigger_timeout
wake.listen_start
wake.listen_done
wake.route_start
wake.route_done
wake.preroll_restart
wake.asr_transcript
```

Required fields:

- `request_id`
- `session_id` where available
- `turn_id` where available
- `timeout_sec` for waits/listens
- `accepted` or `reason` for trigger decisions
- `matched`, `phrase`, `command_text`, `in_followup` for ASR transcript matching
- `ok`, `error_code`, `duration_ms` for stage completion

### Endpointing / Streaming VAD

Component: `endpoint`

```text
endpoint.record_start
endpoint.speech_start
endpoint.endpoint_reached
endpoint.record_done
endpoint.record_failed
```

Required fields:

- `max_record_sec`
- `silence_sec`
- `min_speech_sec`
- `no_speech_timeout_sec`
- `chunk_duration_sec`
- `threshold`
- `total_chunks`
- `speech_chunks`
- `record_duration_sec`
- `speech_duration_sec`
- `endpoint_latency_sec` when available
- `wall_duration_sec`
- `reason` on failure or early stop

Do not log every chunk. Only log state transitions.

### Listen / Offline VAD / ASR

Component: `listen`

```text
listen.record_start
listen.record_done
listen.vad_start
listen.vad_done
listen.asr_start
listen.asr_done
listen.asr_transcript
```

Required fields:

- `use_endpointing`
- `timeout_sec`
- `save_audio`
- `audio_path` only when `logging.log_audio_paths` allows it
- `speech_detected`
- `segment_count`
- `duration_sec`
- `confidence`
- `text` for non-empty ASR transcript when `log_transcripts` is true
- `endpoint_metrics` when endpointing was used

### Converse

Component: `converse`

```text
converse.route_text
```

Required fields:

- `session_id`
- `turn_id`
- `text`
- `matched`
- `route`
- `action`
- `error_code` where applicable

The existing `converse.route_text` event remains the canonical routing decision log.

### Discord Fallback

Component: `discord`

```text
discord.send_request
discord.send_result
```

Required fields:

- `session_id`
- `turn_id`
- `channel_id`
- `content`
- `content_length`
- `mention_configured`
- `timeout_sec`
- `ok`
- `status_code`
- `message_id` on success
- `error_code` on failure

`content` should be the exact Discord message content when `log_transcripts` is true.

### Speak / TTS / Playback

Component: `speak`

```text
speak.start
speak.tts_start
speak.tts_done
speak.play_start
speak.play_done
speak.playback
```

Required fields:

- `text`
- `style`
- `play`
- `audio_path` only when `logging.log_audio_paths` allows it
- `duration_sec`
- `played`
- `warning_code`
- `error_code`
- `duration_ms`

`speak.playback` remains a summary event for compatibility with existing log queries.

### Audio

Component: `audio`

```text
audio.record_start
audio.record_done
audio.play_start
audio.play_done
audio.stream_start
audio.stream_done
audio.stream_error
```

Required fields:

- `file` or `output`
- `duration_sec`
- `chunk_duration_sec`
- `max_duration_sec`
- `chunk_count`
- `ok`
- `error_code`
- `duration_ms`

`audio.stream_done` can be emitted when the generator closes, including service shutdown.

### Other Registered Actions

Motion, perception, Bluetooth, reminder, and future plugin actions are covered by
registry-level action logs by default.

They do not need custom phase logs unless their internal workflow has multiple stages that
are independently useful for debugging.

## Example Complete Timeline

Wake command routed to Discord fallback:

```text
action.start action=wake
wake.trigger_wait_start
wake.trigger_hit
wake.listen_start
endpoint.record_start
endpoint.speech_start
endpoint.endpoint_reached
endpoint.record_done
listen.vad_start
listen.vad_done
listen.asr_start
listen.asr_done
listen.asr_transcript text="richard 北京天气怎么样"
wake.asr_transcript text="richard 北京天气怎么样" command_text="北京天气怎么样"
wake.route_start
converse.route_text text="北京天气怎么样" route="discord"
discord.send_request content="@Richerd 北京天气怎么样\n通过 roamer control node 语音播报回复"
discord.send_result ok=true
wake.route_done
action.done action=wake ok=true
```

Local command routed to TTS playback:

```text
action.start action=wake
wake.trigger_hit
endpoint.record_start
endpoint.speech_start
endpoint.endpoint_reached
listen.asr_transcript text="richard 现在几点了"
converse.route_text text="现在几点了" route="local" action="time.now"
action.start action=speak
speak.start text="现在是 22:04"
speak.tts_start
speak.tts_done
speak.play_start
action.start action=audio.play
audio.play_start
audio.play_done ok=true
action.done action=audio.play ok=true
speak.play_done played=true
speak.playback played=true
action.done action=speak ok=true
action.done action=wake ok=true
```

## Implementation Plan

### Step 1: Registry Action Tracing

Files:

```text
src/roamer/platform/plugin_registry.py
src/roamer/platform/runtime.py
tests/core/test_plugin_registry.py
tests/platform/test_runtime_action_logging.py
```

Work:

- Move generic tracing into `PluginRegistry.run()`.
- Generate a request ID if none exists.
- Preserve existing request ID when present.
- Log start/done/exception with elapsed time.
- Ensure `run_action()` does not emit duplicate logs.
- Add tests proving a newly registered action automatically logs.

### Step 2: Voice Pipeline Phase Logs

Files:

```text
src/roamer/plugins/interaction/capabilities/wake.py
src/roamer/plugins/interaction/services/endpointing.py
src/roamer/plugins/interaction/capabilities/listen.py
src/roamer/plugins/interaction/capabilities/speak.py
src/roamer/plugins/interaction/capabilities/audio.py
src/roamer/plugins/interaction/services/discord_client.py
tests/plugins/interaction/test_runtime_logging.py
tests/plugins/interaction/test_endpointing.py
tests/plugins/interaction/test_discord_client.py
```

Work:

- Add only state-transition logs, not per-chunk logs.
- Keep transcript events suppressed for empty text.
- Ensure all phase logs inherit the same active request ID.
- Update existing tests that assumed transcript/playback events were first in the log list.

### Step 3: Verification on Roamer

Commands:

```bash
pytest tests/core/test_plugin_registry.py tests/platform/test_runtime_action_logging.py tests/plugins/interaction/test_runtime_logging.py tests/plugins/interaction/test_endpointing.py tests/plugins/interaction/test_discord_client.py
pytest -m 'not hardware'
```

After deploy:

```bash
sudo systemctl restart roamer-serve.service roamer-wake.service
tail -f logs/roamer.log
```

Manual tests:

```bash
roamer converse --no-wakeword --timeout 4 --max-turns 1
roamer wake --once --timeout 30
```

For each test, find the returned or logged `request_id` and verify that all related events
are queryable with one grep.

## Success Criteria

1. Every `registry.run()` call emits exactly one `action.start` and one terminal event:
   `action.done` or `action.exception`.
2. A newly registered action gets action tracing without adding any logging code to the
   action implementation.
3. Nested actions inherit the parent request ID.
4. `serve`, `wake`, `converse`, `listen`, `speak`, `audio`, and `discord` events for one
   request can be correlated by one `request_id`.
5. Non-empty ASR transcript, command text, routed text, Discord content, and TTS text are
   logged in full when `logging.log_transcripts=true`.
6. Empty transcript text does not produce transcript events.
7. Token/auth/proxy/password/secret fields remain redacted even when full transcript
   logging is enabled.
8. No per-chunk audio/VAD log spam is introduced.
9. Existing JSON output contract for CLI commands remains unchanged.
10. Existing log rotation and three-day cleanup behavior remains intact.

## Boundaries

Always:

- Preserve the structured JSONL log format.
- Keep `request_id` stable within one request chain.
- Keep secret redaction independent from transcript logging.
- Add tests for tracing behavior before implementation.

Ask first:

- Adding a new logging dependency.
- Changing log file location or retention defaults.
- Logging raw audio paths by default.
- Logging raw audio data or binary payloads.

Never:

- Log raw tokens, passwords, authorization headers, or proxy credentials.
- Log every VAD/audio chunk in normal operation.
- Change CLI JSON response shape only to support logging.
- Add semantic reject/fallback filtering in the logging layer.

## Open Questions

- Should `request_id` be included in CLI JSON responses for all commands, or only logged?
- Should full text logging be enabled by default on production Roamer, or explicitly enabled
  in local config?
