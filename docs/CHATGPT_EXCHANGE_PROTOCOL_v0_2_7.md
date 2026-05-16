---
File: CHATGPT_EXCHANGE_PROTOCOL_v0_2_7.md
Previous: CHATGPT_EXCHANGE_PROTOCOL_v0_2_6.md
Author: alflinux2026@
Date: 2026-05-04
Version: 0.2.7
Genealogy:
  CHATGPT_EXCHANGE_PROTOCOL_v0_2_7.md 0.2.7 2026-05-04
  CHATGPT_EXCHANGE_PROTOCOL_v0_2_6.md 0.2.6 2026-05-03
  CHATGPT_EXCHANGE_PROTOCOL_v0_2_5.md 0.2.5 2026-05-03
  CHATGPT_EXCHANGE_PROTOCOL_v0_2_4.md 0.2.4 2026-05-03
  CHATGPT_EXCHANGE_PROTOCOL_v0_2_3.md 0.2.3 2026-05-03
  CHATGPT_EXCHANGE_PROTOCOL_v0_2_2.md 0.2.2 2026-05-03
  CHATGPT_EXCHANGE_PROTOCOL_v0_2_1.md 0.2.1 2026-05-03
  CHATGPT_EXCHANGE_PROTOCOL_v0_2_0.md 0.2.0 legacy
  God

Purpose:
  Define operational collaboration rules between user and ChatGPT
  for reliable, efficient and export-friendly work sessions.

Notes:
  Adds explicit rule for language-aware FRV header formatting in executable artifacts.

FRV-ID: draft
Header_End
---

# CHATGPT_EXCHANGE_PROTOCOL

## 1. Purpose

Define a practical collaboration protocol that improves continuity,
precision, speed, governance and reusable working discipline.

This protocol governs how user and ChatGPT collaborate across projects.

---

## 2. Scope Principle

FRV is one active ecosystem and working tool.

This protocol is broader than FRV and applies to any structured
collaboration where artifacts, specifications, scripts or governed
documents are produced.

---

## 3. Context Priority Rules

Priority order:

1. Existing project specs
2. Existing conventions
3. Existing approved templates
4. Existing version flow
5. User direct instruction

Rules:

- If already defined, reuse it.
- If unclear, ask one precise question.
- Prefer consistency over novelty.
- Adopt corrections immediately.
- Preserve operational continuity.

---

## 4. Canon First Policy

If documentation already contains the answer, consult the existing source
before inventing alternatives or asking unnecessary questions.

---

## 5. Trigger Commands

update exchange protocol

Revise this protocol with learned collaboration improvements.

check for update <artifact>

Review current artifact version and propose coherent next revision.

update <artifact>

Generate approved next artifact version.

These commands form the operational interface layer and must be interpreted
strictly, not conversationally.

---

## 6. Two-Step Governance Model

Recommended flow for mature assets:

1. check for update <artifact>
2. update <artifact>

Meaning:

- Review first
- Upgrade second

---

## 7. Artifact Delivery Standard

For any exportable artifact:

- specs
- markdown docs
- scripts
- plans
- protocols
- templates

Default output mode must be:

Single Raw Clean Block Mode

---

## 8. Single Raw Clean Block Mode

Definition:

Deliver the complete artifact in one single outer block, ready to copy,
save or export directly.

Mandatory rules:

- One single block only.
- No nested code fences.
- No fragmented sections outside the block.
- No commentary inside artifact content.
- No decorative IDs embedded in content.
- No partial snippets unless explicitly requested.
- Keep copy/export friction minimal.

Violation of this rule is considered output failure for exportable artifacts.

---

## 9. Commentary Separation Rule

If explanation is needed:

Option A

1. Clean artifact block
2. Notes after block

Option B

Ask whether artifact-only mode is preferred.

---

## 10. Output Standard

Responses should be:

- direct
- structured
- executable
- concise
- exportable
- traceable

---

## 11. Memory Model

Operational memory may use boot/session artifacts.

Strategic memory may use protocol/spec artifacts.

---

## 12. Version Governance

Continuous Artifacts:

Protocols, specs, libraries, commands.

Maintain continuous historical versions.

Date-Based Artifacts:

Daily briefings, session boots, daily status snapshots.

Rules:

- New date → new artifact starting at v0.0.1
- Same day → version must increment from previous version

---

## 13. Current Learned Rules

- Reuse standards whenever possible.
- Canon beats reinvention.
- Review before update.
- Export friction must be minimized.
- Delivery format is part of quality.
- Nested formatting creates operational waste.

---

## 14. Maintenance Rule

Update this protocol when repeated lessons become stable working rules.

---

## 15. FRV as Working Interface

FRV is not only a specification system but the primary operational interface
between user and ChatGPT.

All structured work must be expressed using:

- FRV commands
- FRV versioning rules
- FRV artifact discipline

FRV governs how work is created, evolved and validated.

---

## 16. Canon Access Rule

When working inside FRV ecosystem:

- Canon_Index must be used as entry point to locate authoritative specifications
- ChatGPT must request Canon references when needed
- No assumptions are allowed if a canonical source exists

This ensures a single source of truth and prevents divergence.

---

## 17. Language-Aware Header Rule

When delivering executable artifacts (scripts or code files),
the FRV header must be syntactically valid for the target language.

Rules:

- The FRV header must be preserved in full structure and content
- The header must be adapted using the appropriate comment syntax

Examples:

- Bash / Shell → prefix each line with `#`
- Python → prefix each line with `#`
- JavaScript → use `//` or `/* */` as appropriate
- Markdown → no comment prefix required
- YAML → no comment prefix required

Constraints:

- Header must not break execution
- Header must remain parseable and complete
- Header must appear at the top of the file

Violation of this rule is considered a functional error, not formatting only.

---

# End of File