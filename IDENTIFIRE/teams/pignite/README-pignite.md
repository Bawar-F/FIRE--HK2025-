# Pignite – Ignition, Fire Sensing, Thermal Camera

Purpose: prototype and validate ignition, fire sensing, and thermal camera workflows. Software covers sensors/camera/antändning.

## What lives here
- hw/: schematics or notes for the igniter and sensors
- fw/: firmware for any controllers you use
- sw/: small utilities or scripts specific to this module (shared code goes in shared/)

## Acceptance (first milestone)
- Can trigger a controlled ignition
- Logs ignition_time_s, burn_rate_mm_per_min, and a basic temperature profile
- Snapshot(s) or a short clip from the thermal camera
