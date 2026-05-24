# Valetudo Reality Probe

Status: HARDWARE-EXCLUDED in this workspace. Real request/response captures require the Pi and Roborock S5.

Required endpoints for physical acceptance:

- `GET /api/v2/robot/state`
- `GET /api/v2/robot/state/attributes`
- `PUT /api/v2/robot/capabilities/BasicControlCapability`
- `PUT /api/v2/robot/capabilities/GoToLocationCapability`

Acceptance capture checklist:

- raw state values during idle, goto, stop, dock, stuck/unreachable if reproducible.
- position payload format and update frequency.
- map identity availability: `map_id` or `map_hash`; if absent, places remain `unverified_static`.
- stop command response time and physical stopping behavior.
- raw transport and command error payloads when Valetudo is unreachable.
