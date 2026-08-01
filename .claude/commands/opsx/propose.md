---
name: "OPSX: Propose"
description: Propose a new change - create it and generate all artifacts in one step
allowed-tools: Bash(openspec:*), mcp__claude_ai_Linear__list_projects, mcp__claude_ai_Linear__get_project, mcp__claude_ai_Linear__save_issue, mcp__claude_ai_Linear__save_status_update
category: Workflow
tags: [workflow, artifacts, experimental]
---

Propose a new change - create the change and generate all artifacts in one step.

I'll create a change with artifacts:
- proposal.md (what & why)
- design.md (how)
- tasks.md (implementation steps)

Once tasks.md exists, its tasks are also synced into the matching Linear project as issues.

When ready to implement, run /opsx:apply

---

**Store selection:** If the user names a store (a store is a standalone OpenSpec repo registered on this machine) or the work lives in one, run `openspec store list --json` to discover registered store ids, then pass `--store <id>` on the commands that read or write specs and changes (`new change`, `status`, `instructions`, `list`, `show`, `validate`, `archive`, `doctor`, `context`). Other commands do not take the flag. Hints printed by commands already carry the flag; keep it on follow-ups. Without a store, commands act on the nearest local `openspec/` root.

**Input**: The argument after `/opsx:propose` is the change name (kebab-case), OR a description of what the user wants to build.

**Steps**

1. **If no input provided, ask what they want to build**

   Use the **AskUserQuestion tool** (open-ended, no preset options) to ask:
   > "What change do you want to work on? Describe what you want to build or fix."

   From their description, derive a kebab-case name (e.g., "add user authentication" → `add-user-auth`).

   **IMPORTANT**: Do NOT proceed without understanding what the user wants to build.

2. **Create the change directory**
   ```bash
   openspec new change "<name>"
   ```
   This creates a scaffolded change in the planning home resolved by the CLI with `.openspec.yaml`.

3. **Get the artifact build order**
   ```bash
   openspec status --change "<name>" --json
   ```
   Parse the JSON to get:
   - `applyRequires`: array of artifact IDs needed before implementation (e.g., `["tasks"]`)
   - `artifacts`: list of all artifacts with their status and dependencies
   - `planningHome`, `changeRoot`, `artifactPaths`, and `actionContext`: path and scope context. Use these instead of assuming repo-local paths.

4. **Create artifacts in sequence until apply-ready**

   Use the **TodoWrite tool** to track progress through the artifacts.

   Loop through artifacts in dependency order (artifacts with no pending dependencies first):

   a. **For each artifact that is `ready` (dependencies satisfied)**:
      - Get instructions:
        ```bash
        openspec instructions <artifact-id> --change "<name>" --json
        ```
      - The instructions JSON includes:
        - `context`: Project background (constraints for you - do NOT include in output)
        - `rules`: Artifact-specific rules (constraints for you - do NOT include in output)
        - `template`: The structure to use for your output file
        - `instruction`: Schema-specific guidance for this artifact type
        - `resolvedOutputPath`: Resolved path or pattern to write the artifact
        - `dependencies`: Completed artifacts to read for context
      - Read any completed dependency files for context
      - Create the artifact file using `template` as the structure and write it to `resolvedOutputPath`
      - Apply `context` and `rules` as constraints - but do NOT copy them into the file
      - Show brief progress: "Created <artifact-id>"
      - **If this artifact is `tasks`**: once the file is written, immediately do step 5 (Sync tasks to Linear) before moving on — don't defer it to the end, so a crash/interrupt later in the run doesn't leave tasks.md written but unsynced.

   b. **Continue until all `applyRequires` artifacts are complete**
      - After creating each artifact, re-run `openspec status --change "<name>" --json`
      - Check if every artifact ID in `applyRequires` has `status: "done"` in the artifacts array
      - Stop when all `applyRequires` artifacts are done

   c. **If an artifact requires user input** (unclear context):
      - Use **AskUserQuestion tool** to clarify
      - Then continue with creation

5. **Sync tasks to Linear**

   This runs once, right after `tasks.md` is written (see 4.a). Skip entirely if the change has no `tasks.md` (shouldn't normally happen, since `tasks` is required for apply-readiness).

   a. **Resolve the Linear project and team**: match the change's subject matter (from `proposal.md`'s "Why"/"What Changes", or the change name itself) against `mcp__claude_ai_Linear__list_projects`. If there's one clear, confident match, use it. If there's no match or more than one plausible candidate, use **AskUserQuestion** to ask which Linear project this change belongs to — never guess silently, and never skip the sync silently either. Then resolve the project's team: `mcp__claude_ai_Linear__get_project` returns a `teams` array — `save_issue` requires `team` when creating an issue, so this must be resolved before step 5.c. If the project belongs to more than one team, use **AskUserQuestion** to ask which team rather than picking arbitrarily.

   b. **Parse tasks.md**: read the file just written. It's structured as `## N. Group Name` headings followed by `- [ ] N.M Task description` checkboxes (see the tasks artifact's own format rules). Extract each group heading and its ordered list of tasks.

      **Idempotency guard**: a heading or task line may already carry a trailing `<!-- linear:XXX -->` annotation from a prior sync (propose re-run, or resumed after a crash mid-loop). Note which headings/tasks are already annotated — never create a duplicate Linear issue for something that already has one.

   c. **For each group heading without a `<!-- linear:XXX -->` annotation**, create one Linear issue via `mcp__claude_ai_Linear__save_issue` (omit `id` to create; pass `team` and `project` from step 5.a — both required), titled after the group heading (e.g. "1. GCP Infrastructure (fresh build)"), with a description noting it was generated from `<changeRoot>/tasks.md` for change `<name>`. **Then append the created issue's identifier as a trailing HTML comment on the heading line itself** (e.g. `## 1. GCP Infrastructure (fresh build) <!-- linear:PEN-230 -->`), so a re-run can find and reuse it instead of creating a second group issue. **If the heading is already annotated**, skip creating a group issue and reuse that annotation's id as `parentId` in step 5.d.

   d. **For each task without a `<!-- linear:XXX -->` annotation**, create one Linear sub-issue via `mcp__claude_ai_Linear__save_issue` (omit `id` to create; pass `team` and `project` from step 5.a, and `parentId` set to the group's issue id — newly created or reused per step 5.c), titled with the task's own description (drop the `N.M` numeric prefix from the title, but keep the exact task ID in the issue description, e.g. "Task 2.3 — openspec/changes/<name>/tasks.md", so a task can be traced back to its checkbox and vice versa). **Tasks that already have an annotation are skipped entirely** — already synced, don't touch them or their checkbox line.

      **Then edit `tasks.md` itself** to append the created sub-issue's identifier as a trailing HTML comment on that same checkbox line, e.g.:
      ```
      - [ ] 2.3 Pick the detector to move forward with, based on the benchmark <!-- linear:PEN-231 -->
      ```
      This is what `/opsx:apply` uses later to move the right issue to "In Progress" without re-searching Linear — do this for every newly-created task, not just a sample, and don't let it break the `- [ ] N.M ` checkbox parsing (`/opsx:apply` and `openspec status` must still recognize the line as the same task).

   e. **Report what was created**: a short summary (issue count per group) as part of the final output, not the full list of Linear URLs unless the user asks.

   f. **Also post a project status update** (`mcp__claude_ai_Linear__save_status_update`, `type: "project"`) on the same Linear project, summarizing the proposal (why, key decisions, what's still open) — post this once a project is known from step 5.a, even if issue creation in 5.b-e partially failed afterward, since the proposal itself is worth reflecting. If step 5.a's project resolution never completed (still ambiguous, or the user didn't answer), there is no valid project to post to — skip this step entirely rather than guessing.

6. **Show final status**
   ```bash
   openspec status --change "<name>"
   ```

**Output**

After completing all artifacts, summarize:
- Change name and location
- List of artifacts created with brief descriptions
- Linear sync result: which project, how many group issues and task sub-issues were created, and the project status update
- What's ready: "All artifacts created! Ready for implementation."
- Prompt: "Run `/opsx:apply` to start implementing."

**Artifact Creation Guidelines**

- Follow the `instruction` field from `openspec instructions` for each artifact type
- The schema defines what each artifact should contain - follow it
- Read dependency artifacts for context before creating new ones
- Use `template` as the structure for your output file - fill in its sections
- **IMPORTANT**: `context` and `rules` are constraints for YOU, not content for the file
  - Do NOT copy `<context>`, `<rules>`, `<project_context>` blocks into the artifact
  - These guide what you write, but should never appear in the output

**Guardrails**
- Create ALL artifacts needed for implementation (as defined by schema's `apply.requires`)
- Always read dependency artifacts before creating a new one
- If context is critically unclear, ask the user - but prefer making reasonable decisions to keep momentum
- If a change with that name already exists, ask if user wants to continue it or create a new one
- Verify each artifact file exists after writing before proceeding to next
- Never guess a Linear project when resolving step 5.a — ask if it's ambiguous
- The Linear sync in step 5 must not block or fail the OpenSpec artifact creation itself — if Linear sync errors out, report the error clearly but leave the already-written OpenSpec files intact
- Never create a duplicate Linear issue for a group heading or task that already has a `<!-- linear:XXX -->` annotation — re-running propose, or resuming after a crash mid-sync, must be safe
