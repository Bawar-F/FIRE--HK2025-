# IDENTIFIRE – Fire Risk Testing Rig

A portable sampling and burn-test device for local ignition risk assessment, designed to evaluate fire risk in various environments through controlled combustion testing.

## What we're building
- Sample collection: get consistent material samples
- Controlled burning: ignite samples safely and measure burn rates
- Data recording: track what burns how fast under what conditions
- Safety systems: ventilation, emergency stops, proper procedures

## Project layout
```
├── teams/           # Each team's work area
│   ├── pignite/     # Ignition & sensors (eldarna)
│   ├── rotom/       # Chamber & UI (kammare)
│   └── charmander/  # Sampling & waste (material gathering)
├── shared/          # Code, docs, and files used by multiple teams
├── docs/            # Project documentation
├── tests/           # Test procedures and safety checklists
└── photos/          # Visual documentation (encouraged!)
```

## Contributing

### Quick start
1. Clone the repo
2. Make a branch: feature/fix-name
3. Work in your team's folder: teams/pignite, teams/rotom, or teams/charmander
4. Commit and push with clear messages

### Team responsibilities
- Pignite (eldarna): ignition control, cameras, temperature measurement
- Rotom (kammare): chamber design, ventilation, user interface, environmental monitoring
- Charmander (material gathering): sample collection, positioning, waste handling

### Working style
- Work in your team folder; avoid changing other teams' work without asking
- Document with photos/videos when possible
- Ask for help early; tag reviewers in PRs: @username

### File organization tips
- Put photos in photos/[team]/YYYY-MM-DD/
- Save test results in your team folder
- Use simple, descriptive file names
- Include dates in important files

## Shared resources
- Common code: shared/
- Test procedures: tests/
- Troubleshooting: docs/troubleshooting.md
- Outstanding issues: docs/outstanding-issues.md

## What success looks like
1. We can collect a material sample of known size
2. We can ignite it safely in a controlled environment
3. We can measure how fast it burns
4. We can record data reliably
5. We can dispose of waste safely and clear the chamber
6. We can do this repeatedly and safely

## Quick links
- Requirements: docs/requirements.md
- SOP (operator flow): docs/SOP.md
- Troubleshooting: docs/troubleshooting.md
- Outstanding issues: docs/outstanding-issues.md
- Interfaces: shared/interfaces/
- Photos guide: photos/README.md
