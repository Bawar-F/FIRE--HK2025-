# Interface – Safety & Interlocks

## Signals
- ESTOP (input): forces SAFE state
- DOOR_CLOSED (input): required to IGNITE
- SAFE_TO_OPEN (output): asserted when cooldown threshold met

## Behavior
- IGNITE only when DOOR_CLOSED and ESTOP not active
- On ESTOP: abort ignition, extinguish, keep closed until SAFE_TO_OPEN
