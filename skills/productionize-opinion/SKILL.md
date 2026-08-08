---
name: productionize-opinion
description: Distill an operator's own raw material — transcripts, notes, decisions, chat history — into durable workspace context that carries their voice, process, and opinions, so an agent amplifies how they think. Use when capturing brand voice, encoding a decision process, building a second brain, or when the user mentions "productionize my opinion", "ingest agent", "distill my voice", "capture how I think", or "second brain". Differentiator - mines the operator, not external sources; distilled inferences are marked as inferences, never laundered into stated fact.
---

# Productionize Opinion — capture the fuzzy value

Jake Van Clief's core thesis, made a discipline: the durable, hard-to-automate value is **your opinion** — the fuzzy metrics, the "in my niche it's done this way," the process no model was trained on. *"You get substance by giving opinion."* Anthropic and OpenAI will make the models better; they cannot make a reward function for how *you* think a thing should be done. This island turns raw operator material into the context files that carry that, so an agent's work is amplified by your judgement instead of averaged toward the industry mean.

It mines *you* — which is what separates it from [`research`](../research/SKILL.md) (external primary sources) and [`grill`](../grill/SKILL.md) (interactive interview). Here the source is your own exhaust: transcripts, voice notes, chat history where you said "no, not like that," past decisions, things you've written.

## The ingest → distill loop

### 1. Ingest — raw material to an inbox

Drop the raw material into the workspace `inbox/` (created by [`workspace-scaffold`](../workspace-scaffold/SKILL.md) and documented in [folder-workspace's map template](../folder-workspace/references/map-template.md)): recorded thoughts, meeting transcripts, the chat turns where you corrected the AI, prior writing. Volume is fine — this stage does not judge, it collects. Redact secrets, credentials, and third-party PII — including confidential business relationships like an NDA'd client name — on the way in; if any slipped through, scrub it during distill before it lands in a context file.

### 2. Distill — extract the patterns, not just the words

Read the raw material and extract, in order:

- **Stated preferences** — what you explicitly said you want ("don't use 'hey guys' energy," "always cite the source"). These are *facts you stated* — record them as such, each dated to its source. When two stated preferences conflict across sources, keep both dated rather than silently picking one; mark which supersedes as an **inference**, never as a new stated fact.
- **Revealed patterns** — the *why* under the words: why you talk a certain way, what you consistently reach for, what you reject. These are *inferences* — record them **marked as inferred**, not as stated fact. Distilling an inference and presenting it as your stated opinion is the laundering the forge forbids; a distilled voice file must say which lines you said and which the distiller guessed.
- **Decisions and their reasons** — past choices *already made in the raw material*, with the *why*, so the process is repeatable. This island only *harvests* decisions already in the exhaust; for a decision being made **now**, [`grill`](../grill/SKILL.md) emits the ADR — don't duplicate that here. On a repeat ingest, a decision still open at the last pass gets logged once it resolves in the exhaust — cross-reference any grill ADR already opened for it so the two don't diverge.

Write the result to durable context files in the workspace — a `voice.md`, a `process.md`, a decision log — small and lean (a tuned context file is a short one; see [`skill-tune`](../skill-tune/SKILL.md)). **Cite the raw source beside each extracted line** (e.g. `voice.md ⟵ inbox/2026-06-call.txt`, or an inline `(source: …)` tag), so the traceability the completion criterion demands is actually checkable against the artifact.

### 3. Constrain — turn corrections into rules

Every "no, you're off" in the chat history is a constraint. Convert them into positive rules (per [`writing-for-agents`](../writing-for-agents/SKILL.md) — steer toward the target, not away from the banned thing): "write clear declarative sentences" beats "don't be verbose." Each rule you add is a piece of your brain the agent now runs on.

**Done when** the distilled context files carry stated preferences (as facts, conflicts dated and reconciled only as marked inference), revealed patterns (marked as inferences), and decisions with reasons — each line traceable to its raw source, and none of the inferred lines presented as something you stated.

Enforced-vs-advisory: these rules are **advisory** — no script enforces the inference marking, the source citation, or the redaction pass; the done-when review is the gate, and [`workspace-audit`](../workspace-audit/SKILL.md) can only check the files exist, not that a line is honestly labelled or that raw material was scrubbed. State that; the discipline lives in the review, not in a hook.

## The point

This is how you hand a version of your judgement to an employee, a subagent, or a fresh session — they will not *be* you, but their work is shaped by how you think at a higher level. It also feeds [`skill-tune`](../skill-tune/SKILL.md): your correction history is exactly the eval signal for tuning a voice skill. And it is what makes a [`folder-workspace`](../folder-workspace/SKILL.md) *yours* rather than generic — the rooms fill with your opinion, and the map routes to it.

**No authority without evidence. Mark the inference as an inference; never launder a guess into your stated opinion.**
