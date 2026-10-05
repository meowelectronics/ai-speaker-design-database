# Loudspeaker Design Knowledge Base

The rebuildable seed is `data/knowledge/speaker_design_knowledge.json`. It stores
equation summaries, units, assumptions, source IDs, implementation references, workflow
stages, and limitations. The ignored SQLite database is an index, not a driver catalog.
The [source register](SOURCES.md) documents links and retrieval limits.

## Workflow Gates

1. Define bandwidth, SPL/distance, intended placement, net volume, amplifier limits,
   construction constraints, and budget scope.
2. Bind every branch to an exact user-selected driver identity and data source.
3. Validate T/S units and consistency; include measured series losses where applicable.
4. Model net enclosure volume, losses, tuning, response, impedance, excursion, and
   port/PR behavior. Initial alignment formulas are not acceptance criteria.
5. Check real driver geometry, cutouts, volume displacement, bracing, sealing,
   crossover space, and manufacturing clearance independently of the acoustic model.
6. Measure individual drivers on the finished baffle with credible voltage/distance,
   microphone calibration, angles, phase, and timing reference.
7. Calculate the complex acoustic sum and electrical load using measured FRD/ZMA,
   component losses, polarity, and acoustic-center offset.
8. Generate an auditable package; then physically verify response, excursion, noise,
   heating, impedance, and intended room placement.

## Equation Areas

The seed indexes SPL/distance/power scaling, T/S forward/inverse conversion,
added-mass and sealed-test-box measurement, series-resistance Q correction, sealed
alignments, port geometry and velocity screens, room modes/SBIR, baffle-step estimates,
nearfield splicing, gating resolution, Zobel/L-pad starting values, angular power
averaging, acoustic-center delays, and provenance hashes.

Search an equation with `python -B -m scripts.system_design.speaker_knowledge_db search "QUERY"`.
Consult the original cited references for unimplemented alignment tables; do not
invent constants or treat rounded datasheet values as measured parameters.

## Measurement and Model Limits

Gated farfield resolution is approximately inverse gate duration, not a sharp validity
cutoff. Nearfield source summation requires compatible timing and phase. Microphone
calibration does not remove reflections. Off-axis interpolation cannot reconstruct
unknown vertical/rear data, and endpoint holds do not create measured frequency coverage.

Lumped models do not certify motor/suspension nonlinearity, compression, panel modes,
port noise, thermal safety, room performance, or fit for a particular printer. All
readiness labels require prototype validation and retain those limitations.