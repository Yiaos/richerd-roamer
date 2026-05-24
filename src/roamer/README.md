# TRANSITIONAL Legacy Tree

`src/roamer/` is the legacy orchestration runtime. Phase E replaces body orchestration with `src/roamerd/`.

This tree remains only for compatibility reference and legacy shim migration. New runtime work must not add orchestration behavior here.

Removal condition: roamerd has completed Pi acceptance and the external callers have migrated to the ControlBridge/compat shim path.
