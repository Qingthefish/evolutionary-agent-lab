# Contribution guide

The final team is not yet confirmed. Human task allocation is deferred and does not block scope preparation.

1. Start from the current main branch and use a focused branch for a change.
2. Define the requirement and observable acceptance evidence before implementation.
3. Implement and inspect the change; run relevant checks. Document what was actually verified.
4. Commit with the actual contributor's identity. Use a pull request for teammate review where available.
5. Preserve experiment configuration and raw artifacts; keep credentials and private run data out of commits.

Every team member must make significant code contributions throughout the project, according to the course announcement. Do not manufacture attribution, backdate activity, or replace collaboration with a bulk upload at the end.

AI-assisted development and cross-course reuse must follow the relevant course rules. Record approved reused components and distinguish them from new implementation and results.

## Starting a change

From the repository root, after cloning and configuring your own Git identity:

```bash
git switch main
git pull --ff-only origin main
git switch -c docs/requirement-review
```

Use a descriptive branch for your actual task. Review the diff before committing, push your branch, and open a pull request. Avoid overwriting another contributor's changes or rewriting published history.

## Review evidence

Explain the concrete requirement, resulting behavior, checks actually run, and remaining limitations. For documents, check links and consistency. For implementation, run the relevant behavior checks documented in README.md and preserve failed-run evidence. The offline foundation checks do not establish model performance or sandbox isolation.

Commit messages and author identities should reflect actual work. Do not use shared accounts or commit on behalf of another member to simulate contributions.
