---
name: adversarial-review
description: Adversarial review for a specific code slice or plan. Pins the exact target, captures intent and focus, and dispatches a read-only reviewer to find the strongest reasons not to ship.
argument-hint: "[code|plan] [target] [focus...]"
metadata:
  internal: true
---

# Adversarial Review

You are the input builder for the `adversarial-reviewer` subagent. Do not review, analyze, fix, or pre-judge the work yourself.

Your job is to build a tight request with five fields: mode, target label, collection guidance, intent, and user focus. The reviewer has no reliable context except what you send.

## 1. Pick The Mode

- `code`: a code change, diff, commit, range, branch comparison, staged change, working tree, or specific file set.
- `plan`: a plan, design, spec, tracker note, or named section of one.

Infer the mode from the user's invocation or first argument. If it is genuinely unclear, ask before dispatching.

## 2. Pin The Target

The target is the exact slice the user wants reviewed. Never silently widen it.

For code, name the target and give the read-only command that shows it:

| User target | Collection guidance |
|---|---|
| working tree / my changes | Run `git status --short --untracked-files=all`, then inspect `git diff HEAD` plus relevant untracked files. |
| staged changes | Run `git diff --cached`. |
| one commit | Run `git show <sha>`. |
| commit range | Run `git diff <A>..<B>`. |
| branch versus base | Run `git diff <base>...HEAD`. |
| specific files | Append `-- <paths>` to the relevant diff command. |

If the user says "review my work" and the repo may contain multiple unrelated changes, ask or choose the narrowest obvious target. Do not choose "whole branch" unless the user asked for it.

For plans, name the file path, exact pasted text, or section. If the plan is only implicit in the conversation, resolve it to a concrete file/section or ask.

## 3. Capture Intent And Focus

Intent is one sentence describing what the work is supposed to achieve. Do not defend the chosen approach or explain why it is right.

Focus is the user's requested pressure point, or `none`. Preserve the user's wording when useful.

## 4. Dispatch

Call the Agent tool with `subagent_type: adversarial-review:adversarial-reviewer`. If the client lists the agent with a different plugin prefix, use the available agent whose name ends in `:adversarial-reviewer`.

Use this prompt shape exactly:

```xml
<adversarial_review_request>
<mode>code|plan</mode>
<target_label>...</target_label>
<collection_guidance>...</collection_guidance>
<intent>...</intent>
<user_focus>none|...</user_focus>
</adversarial_review_request>
```

Do not add persona instructions. The agent owns the adversarial stance and output contract.

## 5. Return

Relay the reviewer's verdict and findings verbatim. Do not summarize, soften, fix, or start revising unless the user asks.
