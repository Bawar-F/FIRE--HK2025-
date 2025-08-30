# SOP – Operator Flow

Based on the concept flow (report Fig. 6).

1. Place unit; insert/stabilize legs; ensure ventilation path.
2. Pre-burn checklist.
3. Start test via UI.
4. System checks sample present; if not, show error and abort.
5. Ignite with coil; monitor thermal/IR.
6. If dangerous state: show error, stop ignition, extinguish, wait; then prompt user.
7. On success: measure time_to_ignition_s and burn_rate_mm_per_min.
8. Extinguish by suffocation; begin cooldown.
9. When chamber safe-to-open: handle waste transfer, close path.
10. Save data (CSV row) and notes; add selected photos.
