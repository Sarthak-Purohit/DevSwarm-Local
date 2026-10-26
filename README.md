# DevSwarm Local

**An Air-Gapped, Containerized Multi-Agent Coding Orchestrator**

## What is DevSwarm Local?
DevSwarm Local is a completely offline, autonomous AI software development platform designed to run on a standard **16GB RAM workstation**. 

Instead of relying on a single AI chat window, DevSwarm coordinates a local team of specialized AI agents—a **Planner**, a **Coder**, and a **Reviewer**. These agents work together to break down your feature requests, write code in parallel, run automated tests, and fix their own bugs before presenting the final code to you for approval.

## The Goal
The primary goal of this project is to democratize autonomous AI coding by making it free, private, and safe to run on consumer hardware. We solve four major problems with current AI coding tools:

1. **Zero Cloud Costs & 100% Privacy:** By using quantized local models (Ollama), we eliminate expensive cloud API token fees. Your proprietary code never leaves your laptop.
2. **Conflict-Free Parallelism:** Traditional local agents overwrite each other's files. We use **Git Worktrees** to give every agent its own isolated folder, allowing Frontend and Backend agents to code simultaneously without collisions.
3. **Safe Execution:** AI-generated code is untrusted. We sandbox all agent test executions (like `pytest`) inside ephemeral **Docker containers** so they cannot harm your host operating system.
4. **Explainable AI (No Black Boxes):** Developers shouldn't merge code they don't understand. Our system forces agents to stream their step-by-step reasoning in plain English to a live web dashboard before altering any files.

## How It Works
1. **Plan:** You submit a feature request on the web dashboard. The Planner agent scans your codebase and breaks the request into subtasks.
2. **Code & Test:** Coder agents spin up isolated Git worktrees, write the code, and run unit tests inside Docker. If a test fails, the agent reads the error and repairs the code automatically (up to 3 times).
3. **Review:** A dedicated Reviewer agent audits the final Git diff for security flaws and logic bugs.
4. **Approve:** You review the agent's explanation and a side-by-side code diff on the dashboard, then click "Approve & Merge" to safely add it to your main branch.

## Tech Stack
- **Orchestration & AI:** Python 3.10+, Ollama (Local SLMs like `Qwen2.5-Coder`), Pydantic
- **Systems & Sandbox:** Git CLI (`git worktree`), Docker Engine (`devswarm-sandbox`), FastAPI
- **Context Management:** Python Built-in `ast` (for lightweight code skeletonization), `sqlite3`
- **Frontend Dashboard:** React (Vite), Tailwind CSS, `react-diff-viewer-continued`