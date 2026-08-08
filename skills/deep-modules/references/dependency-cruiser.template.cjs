/**
 * Verified-working dependency-cruiser config for the deep-modules layout:
 *
 *   src/packages/<name>/
 *     index.ts     <- an entry point (public)
 *     client.ts    <- another entry point (public)
 *     lib/         <- implementation, private
 *     tests/       <- co-located tests + fixtures, private
 *
 * Adjust the `src/packages` prefix below if your repo uses a different root.
 *
 * GOTCHA this file exists to save you from: dependency-cruiser only
 * substitutes a captured `$1` into the `to.path` / `to.pathNot` of the SAME
 * rule that captured it in `from.path`. A `$1` written into `from.path` or
 * `from.pathNot` is a silent no-op — the rule still "passes" with 0
 * violations, which reads as a clean boundary when nothing was checked.
 * Every rule below captures on `from` and refers on `to`, never the reverse.
 */
module.exports = {
  forbidden: [
    {
      // Rule 1a: code entirely outside src/packages/ may not reach into
      // any package's private (subfolder) files.
      name: 'no-external-deep-import',
      severity: 'error',
      comment:
        "Code outside src/packages/ may import only a package's entry points (its root files), never anything in a subfolder like lib/ or tests/.",
      from: { pathNot: '^src/packages/' },
      to: { path: '^src/packages/[^/]+/.+/' },
    },
    {
      // Rule 1b: one package may not reach into ANOTHER package's private
      // files — only that package's entry points. Its own subfolder is
      // exempted via the captured package name ($1), which is rule 2
      // (a package's own files import each other freely).
      name: 'no-cross-package-deep-import',
      severity: 'error',
      comment:
        "A package may freely import its own internals (rule 2), but another package's subfolders are off limits — only that package's entry points.",
      from: { path: '^src/packages/([^/]+)/' },
      to: {
        path: '^src/packages/[^/]+/.+/',
        pathNot: '^src/packages/$1/',
      },
    },
    {
      // Rule 3: a package's own tests may reach entry points (any
      // package's) and their own fixtures, but must not reach past the
      // entry point into lib/ — even within the same package. This is a
      // tighter carve-out than rule 2, which otherwise lets same-package
      // files import each other freely.
      name: 'tests-only-via-entry-points',
      severity: 'error',
      comment:
        "A package's tests may import entry points and their own fixtures under tests/, but not lib/ or any other subfolder directly — bypassing the entry point defeats what the test is meant to exercise.",
      from: { path: '^src/packages/[^/]+/tests/' },
      to: {
        path: '^src/packages/[^/]+/.+/',
        pathNot: '^src/packages/[^/]+/tests/',
      },
    },
    {
      // Rule 4: no dependency cycles, package-internal or cross-package.
      name: 'no-circular',
      severity: 'error',
      comment: 'Dependency cycles defeat the deletion test — you cannot delete one module without the other.',
      from: {},
      to: { circular: true },
    },
  ],
  options: {
    tsPreCompilationDeps: true,
  },
};
