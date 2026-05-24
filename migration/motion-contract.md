# Motion Contract

This contract freezes the Phase D boundary between `roamerd` and the ROS 2 motion substrate.

## Coordinate Frame

- coordinate frame: Valetudo map frame as reported by the bridge node.
- units: millimeters.
- angle convention: bridge-reported radians; callers may omit angle.
- map identity: `map_id` and `map_hash` are carried in `RobotState`.

## Motion Primitives

- `goto(x, y, angle?)`: command a physical move to coordinates.
- `home()`: command docking.
- `stop()`: bounded best-effort physical stop via `Stop.srv`.
- `locate()`: trigger robot locate behavior if available.

## RobotState

`RobotState` publishes physical state, x/y/angle, battery, docked state, `map_id`, `map_hash`, and state age.

RobotState is expected at 1Hz plus event-driven updates. A stale RobotState means no fresh update before the configured threshold. New `goto` and `home` are rejected while stale; `stop` remains allowed.

## Cancel, Stop, Preemption, Shutdown

- action cancel -> physical stop.
- client timeout -> no automatic cancel; action may become running-detached.
- preemption -> cancel current goal, call stop, then start the new goal.
- emergency -> direct `Stop.srv`.
- shutdown order: cancel goals -> call stop -> bounded wait -> destroy ROS client/executor.

## Map Invalidation

If `map_id` or `map_hash` changes, persisted places become stale and need reconfirmation.

## Arrival Tolerance

Arrival tolerance is evaluated in `roamerd`, not the bridge node. The bridge reports physical state; `roamerd` compares current position to the semantic goal with configured arrival tolerance.

## GoTo Lifecycle

The bridge action remains open until physical terminal state: idle, error, stuck, unreachable, canceled, stopped, or unknown. The bridge result does not contain semantic success.

## Running-Detached

running-detached is first-class. If the client times out while the robot continues moving, the action stays observable and can be queried, stopped, canceled, or preempted.

## Error Taxonomy

Errors are grouped as transport, command, physical terminal, or policy. Results include `error_code` and `error_message`.

## Stop.srv Safety Envelope

`Stop.srv` is bounded best-effort while the bridge is alive. If the bridge is unavailable, ROS 2 cannot send a stop command; systemd restart and the S5's low-risk hardware safety are the mitigation.
