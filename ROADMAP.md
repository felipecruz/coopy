# Start your AIFlow roadmap

<!-- aiflow:starter:v5 -->

**AIFlow status: Not started.** This is an untouched starter document. AIFlow has not been used for this roadmap yet.

Click **copy setup prompt** below, then paste it into your coding agent. The agent will inspect this project and replace this document with a versioned roadmap.

Once this document changes, AIFlow switches to its normal preview: select list items and copy an implementation request. Copying the setup prompt alone does not change this file.

## Setup prompt

```text
Create a well-researched, useful ROADMAP for this project at {project_path}.

This document is an unused AIFlow starter. Your task is to understand the project,
reconstruct its implemented capabilities from the current code and Git history,
and replace this starter with an evidence-based, versioned roadmap. This is a
documentation task: do not implement features in this step. Do not create
implementation commits, tags, releases, or branches during roadmap setup.

1. Establish the project context

Locate the project associated with the target file. Read applicable AGENTS.md
instructions, README files, existing planning documents, architecture notes,
manifests, build scripts, and test configuration. Identify the repository root,
current branch, and whether this is a monorepo. If there are multiple products,
focus on the product containing this roadmap and explain that scope.

Understand who uses the product, what problem it solves, its main user journeys,
and its design constraints. Identify entry points, major components, dependencies,
data storage, external integrations, and deployment or distribution mechanisms.
Read representative implementation and test files; do not infer capabilities
solely from filenames, package dependencies, comments, or marketing claims.

Inspect the existing target document before writing. If another process or the
user has replaced the starter with real content, preserve that work and reconcile
with it instead of overwriting it. Never reset, stash, discard, or modify unrelated
working-tree changes. Do not expose secrets or private configuration in the roadmap.

2. Reconstruct development from Git evidence

Use read-only Git inspection. Start with git status --short, the current branch,
git log --oneline --decorate, and local tags. Review a manageable recent window
(for example, 50 commits), then inspect older history where needed to understand
major capabilities and milestones. Use git show --stat, relevant commit diffs,
and path-specific logs to connect changes to behavior. Follow renamed files when
necessary. Review release notes and version manifests alongside tags.

Group commits into user-visible capabilities, reliability improvements, and
meaningful architectural milestones. Do not turn every commit into a feature.
Verify each claimed capability against the current code: a change may have been
reverted, superseded, only partially integrated, or removed. Commit messages and
tags alone are not proof that a feature works or was released. Inspect relevant
tests and distinguish their existence from tests actually run during this task.

For each completed capability, identify the actual implementation commit or a
small set of commits when feasible. Verify each hash exists and supports the
claim; use full hashes in the file. A baseline/import commit is not proof of the
original implementation history. Describe that limitation honestly rather than
assigning an unrelated commit. Distinguish committed behavior from local,
uncommitted changes and from proposals.

If Git history is absent, shallow, or incomplete, say so briefly and rely on code,
tests, and documentation. Do not initialize Git, fetch remote history, fabricate
provenance, or block useful roadmap work just to fill in commit rows. Omit a
Commit row when no meaningful implementation commit can be verified.

3. Separate facts, gaps, and proposed work

Build a concise inventory of what exists, what is partial, and what is missing.
Look for concrete gaps in the main user journeys, error handling, persistence,
recovery, accessibility, performance, testing, packaging, and documentation.
Include a gap only when relevant to this project's actual purpose. Treat TODO
comments as clues, not as unquestioned commitments. Prefer a few valuable next
steps over a generic catalogue of features or speculative rewrites.

When safe and practical, run the project's documented build or focused checks.
Record exact checks and outcomes. If checks cannot run, explain why and label
validation as unverified; do not imply a successful run. Avoid installs, services,
network calls, or changes to external systems merely to research the roadmap.

If the product goal or desired direction cannot reasonably be inferred, ask a
short, targeted question before inventing priorities. Otherwise proceed using
clearly stated assumptions. Separate observed limitations from proposed ideas.
Do not invent customers, deadlines, release dates, ownership, or business promises.

4. Design a small, coherent version plan

Use existing version conventions and verified release milestones when available.
Distinguish historical versions from planned versions. Never imply that a proposed
version has shipped. For an unversioned project, use about three planning groups,
such as v0.1 — Foundation, v0.2 — Reliability and workflow, and v0.3 — Polish.
State that these are planning labels, not historical releases. Adapt names and
numbers to the project; do not impose v0.1 on an established versioned product.

Every version must use a second-level heading in this exact shape:
## v0.2 — Descriptive version goal
A numeric major.minor or major.minor.patch version is required so AIFlow can
discover it as a destination for limitation follow-ups. Put release/planning
status in the introductory sentence beneath the heading. Do not put dates or
status before the version number. Avoid duplicate version headings.

Give each version a short user-facing goal and a clear exit criterion. Order work
by dependencies and usefulness. Establish a verified current baseline, then a
near-term version with specific work, then a modest later version. Aim for roughly
3–5 substantial items per version when appropriate; use fewer for a tiny project.
Do not add filler to meet a count. Keep later proposals clearly provisional.

Each item should describe an outcome a coding agent can implement and validate
in a focused change. Explain the current problem, desired behavior, and observable
acceptance criteria. Mention dependencies using stable feature IDs. Split items
that bundle unrelated changes; avoid vague tasks such as "improve UX" or "fix bugs".
Prefer product behavior over prescribing implementation details without evidence.

5. Write a clean Markdown document that works with AIFlow

Start with a project-specific title and a brief overview of purpose, audience,
current state, and guiding constraints. Add a short evidence note describing the
branch/revision and sources inspected, and any material uncertainty. Then present
the version groups and their feature items. Keep supporting prose concise and
easy to scan. Include relevant repository-relative paths as evidence where useful.

Use stable, document-wide unique feature IDs F1, F2, F3, and so on. Preserve any
existing IDs rather than renumbering established work. Mark verified, fully
implemented items with [x]. Leave partial, planned, and unverified items unchecked
with [ ]. Do not mark a feature implemented solely because a commit mentions it.
Use this shape for planned or incomplete work:
- [ ] **F1 — Short outcome-oriented title.** Problem, intended behavior, and
  concrete acceptance criteria. Depends on F2 only if that dependency is real.

For verified implemented work, use:
- [x] **F2 — Implemented feature.** Describe the behavior that exists today.

Also record implementation status and supporting evidence in the detail table.
This initial roadmap should show verified implemented items as checked already.
AIFlow also uses checked items for request selection, so explain that users should
adjust the selection before copying an implementation request. Preserve selections
in real existing content. Avoid nested task lists for acceptance criteria or status notes: AIFlow
gives every list item a selectable checkbox. Use continuation prose instead.

Beneath implemented or partially implemented items, add a two-column Markdown
table, indented two spaces, with this shape (replace examples with real facts):

  | Item | Content |
  | --- | --- |
  | Status | Done |
  | Timestamp | YYYY-MM-DD |
  | Details | The actual behavior that exists today. |
  | Commit | `<full 40-character hash>` — which part of this feature it implements. |
  | Validation | Specific checks and observed results, or an honest not-run explanation. |
  | Limitation | A concrete remaining gap that can become an actionable follow-up. |

Status is exactly one of Done, Planned, In progress, Partial, or Blocked; explain
partial or local-only work in Details, never in the Status cell. Add Timestamp
(today's date) only to Done items. Use only the row labels of the AIFlow format
below, in that order, so the app recognizes done items and Limitation actions. Omit
rows that do not apply: never invent a hash, include fake placeholder values, or
add a Limitation row saying "None". Keep each table cell on one source line and
escape literal pipe characters. A long description should wrap visually, not become
a broken Markdown row. For planned items, a Status row saying Planned is sufficient;
do not add empty Commit or Validation rows.

Keep a limitation attached to the feature it qualifies. If it already has a planned
follow-up, reference that feature ID instead of duplicating its work. The UI lets
the user hover over a Limitation row, choose one of the document's versions, and
add a follow-up to that version. Make limitation wording specific enough for this
action to produce a useful task. Do not claim an observed limitation is fixed.

End with a short prose note on open decisions only if there are real unresolved
questions. Do not leave the starter marker, setup instructions, sample templates,
placeholder tasks, or a copy of this prompt in the finished roadmap. Start the
finished file with the AIFlow roadmap marker on its own first line.

{roadmap_spec}

6. Validate and deliver the roadmap

Before saving, reread the target to detect changes made during your research and
reconcile them. Confirm that the document accurately separates implemented,
partial, and planned work; all commit references are real; IDs are unique;
dependencies make sense; version headings are discoverable; tables have two
columns; verified implemented items are checked, and partial, planned, or unverified
items are unchecked. Verify that scope and proposed versions
suit the project's maturity and that the first next step is actually actionable.
After saving, run the check command named in the AIFlow format above and fix every
error it reports; fix its warnings too unless they would require inventing facts.

Save the finished Markdown to {roadmap_file}. Keep changes limited to this
document unless I explicitly ask otherwise. In your final response, link to the
file, briefly explain the evidence used and the version plan, suggest the first
few items to select, and disclose any important gaps in history or validation.
```
