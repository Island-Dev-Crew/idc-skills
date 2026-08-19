# Transcript analysis — “One Cancelled Gym Class. That's How Agent Swarm Attacks Start.”

- Source: <https://youtu.be/4f5AJrJPilM>
- Creator: AI News & Strategy Daily | Nate B Jones
- Transcript duration observed: 00:21:03
- Evidence: 596 cleaned timestamped lines. Per the request, this lane used the transcript only; no visual claim is made.

## Threat chain extracted from the transcript

1. A skill already runs inside an agent that has useful authority (00:02:10–00:02:49).
2. The local skill can point to external documentation (00:02:28–00:02:39).
3. A mutable external link can change after the local skill was scanned (00:03:02–00:03:16).
4. The changed page can instruct the agent to download and run code (00:03:30–00:03:51).
5. That code can search for SSH keys, cloud credentials, and Git tokens (00:03:34–00:04:19).
6. A scanner can be correct at scan time and still miss the later flip; the transcript describes a legitimate page that later changed (00:07:26–00:08:22).
7. Child agents and broad credentials compound impact; emergency response needs agent kill, network cut, child shutdown, credential revocation, and retained audit evidence (00:14:57–00:16:29).

The transcript is a secondary account. The underlying mutable-link campaign and scanner-blind-spot pattern were cross-checked against primary disclosures from [Zenity](https://zenity.io/research/ai-total), [Zenity's agent-supply-chain analysis](https://zenity.io/blog/research/securing-the-agent-supply-chain), and AIR's [Story of Skills](https://www.air.security/blog-posts/the-story-of-skills) / [Circus of Skills](https://www.air.security/blog-posts/the-circus-of-skills). OWASP's [Agentic Skills Top 10](https://owasp.org/www-project-agentic-skills-top-10/) supplies the broader taxonomy. Exact industry counts belong to those primary sources, not to this transcript analysis.

## Control synthesis for release 2.0.2

| Threat | 2.0.2 control | Enforcement status |
|---|---|---|
| Local skill tamper | Signed manifest hashes every regular file in all 50 skill trees; inventory additions, symlinks, collisions, and byte drift fail. | Enforced by verifier after trusted bootstrap. |
| Attacker swaps key and manifest | Release fingerprint is a fixed constant, both public artifacts must match it, CLI fingerprint override is removed, and the detached signature requires the external private key. | Enforced, assuming out-of-band fingerprint bootstrap and uncompromised signing approval. |
| New external link | Every HTTP(S) occurrence and network-command occurrence is signed; any new reference changes the manifest comparison. | Enforced. |
| Mutable runtime instructions | `runtime-instruction` references require HTTPS, content SHA-256, final URL, and re-fetch verification. | Enforced for references classified this way. Current Forge skills contain no runtime-instruction reference. |
| Fetch-and-execute | Pipe-to-interpreter, process substitution, dynamic fetch/eval, download-to-file, and network package execution are denied unless an exact signed line-hash exception explains a non-executed example or reviewed setup. | Enforced for the implemented pattern classes; not a full shell parser. |
| Scanner bypass through wide encoding | Non-UTF-8, NUL-bearing, and wide-encoded skill content fails closed. | Enforced. |
| Installed-copy drift | Installer verifies before writes and checks source, staged, and installed bytes; PreToolUse requires the installed skill root. | Enforced when the hook is actually configured and its blocking probe is observed. |
| Excess authority | Individual skills now add mutation, spend, secret, origin, and unattended-run boundaries. | Mixed: some hooks/scripts enforced, many runtime decisions advisory. |
| Emergency shutdown / revocation | Not implemented by the integrity gate. | Explicit residual; requires platform identity, network, credential, and incident-response controls. |

## Why one repository gate is stronger than 50 self-checkers

A checker embedded in each skill shares the skill's trust plane and multiplies the attack surface. Release 2.0.2 uses one signed inventory and one external trust anchor. A repository editor can change the policy, verifier, or skills, but cannot produce a valid new release signature without the 1Password-held key and operator approval. The unavoidable first bootstrap remains external: a consumer must compare the public-key fingerprint through a trusted channel before executing repository code.

## Honest boundary

The gate detects specified byte, inventory, reference, remote-pin, and fetch/execute drift at preflight. It does not prove that signed instructions are benevolent, sandbox an agent, stop every obfuscated command, prevent a same-user attacker from changing files after verification, revoke credentials, or attest the entire execution path. Those are separate controls, not hidden sixth checks.
