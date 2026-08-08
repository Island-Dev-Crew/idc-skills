---
name: deep-modules
description: Shared vocabulary and enforcement for designing deep modules — a lot of behaviour behind a small interface, placed at a clean seam, testable through that interface. Use when designing or improving a module's interface, deciding where a seam goes, making code more testable or AI-navigable, enforcing package boundaries, or when another skill needs the deep-module language. Differentiator - carries both the design vocabulary and the dependency-cruiser rules that make entry points the only way in.
---

# Deep Modules — leverage behind a small interface

Design **deep modules**: a lot of behaviour behind a small interface, at a clean seam, testable through that interface. The aim is **leverage** for callers, **locality** for maintainers, and testability for everyone. This is the vocabulary the fleet uses wherever code is designed or restructured — plus the machine rule that keeps it honest.

## Glossary — use these terms exactly

Don't substitute "component," "service," "API," or "boundary." Consistent language is the whole point.

- **Module** — anything with an interface and an implementation. Scale-agnostic: a function, class, package, or tier-spanning slice.
- **Interface** — *everything a caller must know to use the module correctly*: the type signature, but also invariants, ordering constraints, error modes, required configuration, performance characteristics. Broader than "API" or "signature" (those are only the type-level surface).
- **Implementation** — what's inside; the body of code.
- **Depth** — leverage at the interface: how much behaviour a caller or test can exercise per unit of interface they must learn. **Deep** = a lot of behaviour behind a small interface. **Shallow** = the interface is nearly as complex as the implementation (avoid).
- **Seam** *(Michael Feathers)* — a place where you can alter behaviour without editing in that place; the *location* where a module's interface lives. Where to put the seam is its own decision, distinct from what goes behind it.
- **Adapter** — a concrete thing satisfying an interface at a seam. Describes *role* (what slot it fills), not substance.
- **Leverage** — what callers get from depth: one implementation pays back across N call sites and M tests.
- **Locality** — what maintainers get: change, bugs, knowledge, and verification concentrate in one place. Fix once, fixed everywhere.

## Principles

- **Depth is a property of the interface, not the implementation.** A deep module can be internally composed of small, mockable parts — they just aren't part of the interface. A module has an **external seam** (its interface) and may have **internal seams** (private, used by its own tests).
- **The deletion test.** Imagine deleting the module. If complexity vanishes, it was a pass-through. If complexity reappears across N callers, it earned its keep. A seam kept solely so tests can inject a fake also passes, but only if faking it is materially cheaper than exercising the real dependency — otherwise delete it. When this conflicts with "accept dependencies, don't create them" below, the deletion test wins: testability doesn't justify a seam nothing else needs.
- **The interface is the test surface.** Callers and tests cross the same seam. Wanting to test *past* the interface means the module is the wrong shape.
- **One adapter is a hypothetical seam; two adapters is a real one.** An adapter counts once it exists in code or is committed work — contracted, scheduled, staffed; a roadmap wish doesn't count. Don't introduce a seam unless something actually varies across it.

## Designing for testability

1. **Accept dependencies, don't create them** — `processOrder(order, paymentGateway)`, not a `new StripeGateway()` inside.
2. **Return results, don't produce side effects** — `calculateDiscount(cart): Discount`, not `applyDiscount(cart): void`.
3. **Small surface area** — fewer methods, fewer tests; fewer params, simpler setup.

When designing an interface, ask: can I reduce the methods? simplify the params? hide more complexity inside?

## Rejected framings

- **Depth as implementation-lines ÷ interface-lines** (Ousterhout's ratio): rewards padding. Use depth-as-leverage.
- **"Interface" as the TS `interface` keyword / a class's public methods**: too narrow — interface here is *every fact a caller must know*.
- **"Boundary"**: overloaded with DDD's bounded context. Say **seam** or **interface**.

## Enforcement — make entry points the only way in

Vocabulary without enforcement is advisory. To make it `enforced`, wire [dependency-cruiser](https://github.com/sverweij/dependency-cruiser) so each package's public surface is its **entry points** (its root files) and everything in subfolders is private:

```
src/packages/<name>/
  index.ts     ← an entry point (public). Packages may expose SEVERAL small ones.
  client.ts    ← another entry point — not one giant barrel.
  lib/         ← implementation: hidden from outside, free to import each other.
  tests/       ← co-located tests + fixtures (a subfolder, so private).
```

Four `error` rules: (1) code outside a package imports only that package's entry points, never its subfolders; (2) a package's own files import each other freely; (3) tests reach any package's entry points and their own fixtures, never subfolder internals; (4) no dependency cycles. A verified-working config for these four is at [`references/dependency-cruiser.template.cjs`](references/dependency-cruiser.template.cjs) — start there rather than re-deriving it: dependency-cruiser only substitutes a captured `$1` into the `to.path`/`to.pathNot` of the *same rule*, never into `from.path`/`from.pathNot`, and a `$1` placed on the `from` side is a silent no-op that lets rule (1) contradict rule (2) with zero lint error. **Prove the rules bite** — the completion criterion for enforcement: run the boundary lint on a clean tree (pass), add a deep import to a test (must fail with the boundary rule), revert (pass again). A config that doesn't fail on a violation is worthless. Then link the packages README from `CLAUDE.md`/`AGENTS.md` so an agent discovers the boundary instead of tripping on it.

This lint enforces the seam half only — entry points are the only way in. Depth (whether a module earned its seam via the deletion test) stays advisory: a design judgment made in review, not something a clean lint pass proves.

## Where this feeds

The `deep-modules` vocabulary is the language a keystone rebuild speaks — when `diagnose` finds no correct test seam, or a review flags Shotgun Surgery, the fix is a deepening described in exactly these terms.

**No authority without evidence. One adapter is a hypothesis; two adapters is a seam.**
