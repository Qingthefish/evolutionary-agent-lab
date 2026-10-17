# Contribution guide

The team uses WeChat for discussion and [docs/team-roadmap.md](docs/team-roadmap.md) for task claims, progress and acceptance. Qingthefish coordinates the register and final merging; Codex and teammates can assist with review. Technical areas A/B/C/D do not assign people. Anyone may propose to claim an available card.

## Claim and develop

1. Read the Roadmap card and its prerequisites. Check active cards for overlapping files/interfaces and agree the scope in WeChat.
2. Have the coordinator record the owner/status on **main before coding**. A local or unmerged branch copy is not a shared claim. Refresh main and verify your card.
3. Create one focused branch from the current baseline. Reuse existing modules and implement the card's observable acceptance; coordinate shared-file edits instead of duplicating work.
4. Push a focused PR that references the card ID. Report actual changes, checks/skips, evidence, blockers and review fixes; use your actual contributor identity.
5. After review and acceptance, merge without rewriting published history. The coordinator records the PR, reviewer, corrections, actual result/limitations and merged revision in the same Roadmap card, then marks it Done.

Feature owners report progress through WeChat and their PR. The coordinator maintains the Roadmap so parallel feature branches do not all edit the same register. Discuss handoffs and record the new owner before another member takes over; retain previous contributions. An explicitly requested documentation/maintenance change may reference that request and its PR instead of inventing a feature assignment.

```bash
git switch main
git pull --ff-only origin main
# Confirm that your agreed Roadmap claim is visible here.
git switch -c feat/CARD-ID-short-description
```

Do not edit another person's branch or force-push shared history. Use a different reviewer where practical; verified, focused merges follow the owner's standing authorization. Posting a PR or passing tests alone does not establish that the card's acceptance is met.

## Review and evidence

Link the relevant requirement/card and state the concrete before/after behavior. Include checks actually run, skipped checks, relevant failure/negative cases and remaining limitations. Keep detailed evidence in the PR/ignored run artifacts and only a concise dated result/link in the Roadmap. Document-only changes need link and consistency checks, not artificial runtime tests. Preserve original experiment configuration and raw artifacts; exclude secrets and private run data from commits.

Every member must make significant ongoing code contributions, as the announcement requires. Preserve actual authorship and disclose AI assistance/reuse under the applicable course rules; do not manufacture attribution or substitute a bulk upload at the end. Do not copy personal session transcripts into project documentation.
