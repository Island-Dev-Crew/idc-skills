# COVENANTS — the standing law

1. **No authority without evidence.** Nothing crosses a gate on claims alone; a claim is
   done only when a captured, hashed piece of evidence — from a check that could have
   failed — proves it.
2. **State enforced-vs-advisory for every rule, explicitly** — never imply it.
3. **Never launder `unverified` into `verified`.** Mark unverified work `unverified`.
4. **Two vetting lenses, never conflated:** the defect-tied gate (confidence = 10 minus the
   sum of real, unaddressed, in-scope defects; promote at ≥9) and any generic documentation
   pass (its case scores are the signal, not its generic confidence number).
5. **One concern per island. Don't duplicate meaning across islands. References one level deep.**
6. **Dual-harness:** every island ships an `agents/openai.yaml` sidecar; user-invoked islands
   carry `policy.allow_implicit_invocation: false` so `disable-model-invocation` reaches Codex.
7. **The 40-island cap is the hard ceiling.** Growth stops when a cut stops earning its place;
   a new island must earn a distinct concern, never pad a count.
8. **Adversarial re-vetting is an asymptote** — fresh executors surface new marginal edges every
   round. The honest close is "every real defect fixed and verified, confidence ≥9," not "loop
   until a judge stops finding anything." A wowed prototype is not a passed gate.
