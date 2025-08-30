# Interface – Sample Transfer

Purpose: move a sample into the chamber.

## Inputs
- Command: SAMPLE_RELEASE (bool)
- Status: SAMPLE_PRESENT (bool), SAMPLE_JAMMED (bool)

## Timing
- Transfer must complete within 10 s or fault

## Error handling
- On SAMPLE_JAMMED: stop motion, keep chamber closed, prompt operator
