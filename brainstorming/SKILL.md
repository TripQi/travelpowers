---
name: brainstorming
description: "You MUST use this before any creative work - creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design before implementation."
---

# Brainstorming Ideas Into Designs

## Overview

Help turn ideas into fully formed designs and specs through natural collaborative dialogue.

Start by understanding the current project context, then ask questions one at a time to refine the idea. Once you understand what you're building, present the design and get user approval.

<HARD-GATE>
Do NOT invoke any implementation skill, write any code, scaffold any project, or take any implementation action until you have presented a design, the user has approved it, and the execution handoff context is prepared.
</HARD-GATE>

## Anti-Pattern: "This Is Too Simple To Need A Design"

Every project goes through this process. A todo list, a single-function utility, a config change - all of them. "Simple" projects are where unexamined assumptions cause the most wasted work. The design can be short (a few sentences for truly simple projects), but you MUST present it and get approval.

## Fast-Track Mode
<!-- workflow-contract:brainstorming.fast_track_eligibility -->

For truly trivial changes that would suffer from full-workflow overhead, a fast-track path is available. **All 7 eligibility criteria must be met** — if any single criterion fails, use the standard workflow.

### Eligibility Criteria (ALL must be true)

1. **Single file:** The change touches at most 1 source file (tests excluded from this count).
2. **≤ 30 lines:** Total lines added/modified/deleted is 50 or fewer.
3. **No new dependencies:** No new packages, libraries, or external services.
4. **No API changes:** No changes to public APIs, CLI interfaces, data formats, or configuration schemas.
5. **Obviously correct:** The change is a bug fix with clear root cause, a typo fix, or a mechanical refactor with no behavioral change.
6. **Existing tests cover it:** Tests already exist that will validate the change (or the change is to tests themselves).
7. **User approval:** The user explicitly approves fast-track after reviewing the criteria.

### Fast-Track Process

1. **Write fast-track spec** — save to `docs/designs/YYYY-MM-DD-<topic>-design.md` with a `## Fast-Track Spec` section containing:
   - One-sentence description of the change
   - File to modify
   - Lines to change (approximate)
   - How existing tests validate it
   - Eligibility checklist confirmation (all 7 items checked)
2. **Execute directly** — implement the change, run existing tests, commit.
3. **Commit with tag** — commit message must start with `[fast-track]` (e.g., `[fast-track] Fix off-by-one in pagination`).

### Fast-Track Does NOT Skip

- Writing a design doc (the fast-track spec IS the design doc, just shorter)
- User approval
- Testing
- Git commit

It only skips: writing-plans, compile-plans, and executing-plan-issues (the full JSONL execution loop).

## Checklist

You MUST create a task for each of these items and complete them in order:

1. **Explore project context** - check files, docs, recent commits
2. **Ask clarifying questions** - one at a time, understand purpose/constraints/success criteria
3. **Propose 2-3 approaches** - with trade-offs and your recommendation
4. **Present design** - in sections scaled to their complexity, get user approval after each section
4a. **Fast-track gate** - if the change meets all 7 fast-track eligibility criteria: propose fast-track to the user. If approved, write the fast-track spec, execute directly, and commit with `[fast-track]` tag. Skip steps 5-7.
5. **Write design doc** - save to `docs/designs/YYYY-MM-DD-<topic>-design.md` and commit
<!-- workflow-contract:brainstorming.worktree_handoff -->
6. **Create dedicated worktree + handoff context** - prepare and record `worktree_path`, `branch`, `base_branch`
<!-- workflow-contract:brainstorming.transition_writing_plans -->
7. **Transition to implementation** - invoke writing-plans skill to create implementation plan

## Process Flow

```dot
digraph brainstorming {
    "Explore project context" [shape=box];
    "Ask clarifying questions" [shape=box];
    "Propose 2-3 approaches" [shape=box];
    "Present design sections" [shape=box];
    "User approves design?" [shape=diamond];
    "Fast-track eligible?" [shape=diamond];
    "Write fast-track spec + execute + commit" [shape=box];
    "Write design doc" [shape=box];
    "Create dedicated worktree + handoff" [shape=box];
    "Invoke writing-plans skill" [shape=doublecircle];

    "Explore project context" -> "Ask clarifying questions";
    "Ask clarifying questions" -> "Propose 2-3 approaches";
    "Propose 2-3 approaches" -> "Present design sections";
    "Present design sections" -> "User approves design?";
    "User approves design?" -> "Present design sections" [label="no, revise"];
    "User approves design?" -> "Fast-track eligible?" [label="yes"];
    "Fast-track eligible?" -> "Write fast-track spec + execute + commit" [label="yes, user approves"];
    "Fast-track eligible?" -> "Write design doc" [label="no"];
    "Write design doc" -> "Create dedicated worktree + handoff";
    "Create dedicated worktree + handoff" -> "Invoke writing-plans skill";
}
```

**The terminal state is invoking writing-plans.** Do NOT invoke frontend-design, mcp-builder, or any other implementation skill. The ONLY skill you invoke after brainstorming is writing-plans.

## The Process

**Understanding the idea:**
- Check out the current project state first (files, docs, recent commits)
- Ask questions one at a time to refine the idea
- Prefer multiple choice questions when possible, but open-ended is fine too
- Only one question per message - if a topic needs more exploration, break it into multiple questions
- Focus on understanding: purpose, constraints, success criteria

**Exploring approaches:**
- Propose 2-3 different approaches with trade-offs
- Present options conversationally with your recommendation and reasoning
- Lead with your recommended option and explain why

**Presenting the design:**
- Once you believe you understand what you're building, present the design
- Scale each section to its complexity: a few sentences if straightforward, up to 200-300 words if nuanced
- Ask after each section whether it looks right so far
- Cover: architecture, components, data flow, error handling, testing
- Be ready to go back and clarify if something doesn't make sense

## After the Design

**Documentation:**
- Write the validated design to `docs/designs/YYYY-MM-DD-<topic>-design.md`
- Use writing-clearly-and-concisely skill if available
- Commit the design document to git

**Execution Handoff (required):**
- Create or validate a dedicated worktree for implementation
- Record this handoff block in the design doc (or in the transition message):
  - `design_doc`: exact path
  - `worktree_path`: absolute path
  - `branch`: implementation branch name
  - `base_branch`: upstream base branch
  - `open_risks`: short list (or `none`)
- If worktree already exists, verify it points to the intended branch and is usable

**Implementation:**
- Invoke the writing-plans skill to create a detailed implementation plan
- Pass the handoff block above in the first writing-plans message
- Do NOT invoke any other skill. writing-plans is the next step.

## Key Principles

- **One question at a time** - Don't overwhelm with multiple questions
- **Multiple choice preferred** - Easier to answer than open-ended when possible
- **YAGNI ruthlessly** - Remove unnecessary features from all designs
- **Explore alternatives** - Always propose 2-3 approaches before settling
- **Incremental validation** - Present design, get approval before moving on
- **Handoff completeness** - No implementation planning without explicit worktree and branch context
- **Be flexible** - Go back and clarify when something doesn't make sense
