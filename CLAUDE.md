@AGENTS.md
Sandbox checks use Docker Desktop: see AGENTS.md section 9.
Every pull request that changes code gets a separate variable-comment pass: each changed function starts with a `# Variables:` block describing its key variables in plain English. See AGENTS.md section 7.1.
When you ask the developer to add or change lines in a `.env.example` (or `.env`) file, give the file's full absolute Windows path (for example `C:\Users\nicol\Capstone_Project_CMU\.worktrees\<worktree>\.env.example`), never a path relative to the repository or a worktree.
