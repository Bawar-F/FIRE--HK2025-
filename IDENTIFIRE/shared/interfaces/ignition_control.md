# Interface – Ignition Control

## States
- IDLE → HEATING → IGNITING → DONE/FAILED

## Commands
- IGNITE (start)
- ABORT (stop)

## Telemetry
- coil_temp_c (optional)
- ignition_detected (bool)
- t_ignition_s (float)

## Timeouts
- Max ignition attempt: 60 s, then FAILED and extinguish.
