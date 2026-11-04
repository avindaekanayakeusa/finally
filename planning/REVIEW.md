# Review of changes since HEAD

**Decision: Fix the issues below before committing.**

Reviewed staged, unstaged, and untracked changes, including the deleted files. Application source and tests are unchanged.

## Findings

1. **[P1] The independent-reviewer plugin cannot run its hook.**  
   Location: `Independent reviewer/.claude-plugin/hooks/hooks.json:1-10`  
   The hook lives inside `.claude-plugin/`, but the manifest does not declare that custom location. Default discovery expects `hooks/hooks.json` at the plugin root. The configuration also places the command directly under `Stop` instead of inside a nested `hooks` array, and its shell command has an unclosed quote and an unfinished output filename. Installing the marketplace plugin therefore does not provide a working review. Move the hook to the standard location, correct its structure, and supply a complete command targeting `planning/REVIEW.md`. Verify the plugin independently of the project-level hook, which could otherwise hide this failure. See the [official plugin reference](https://code.claude.com/docs/en/plugins-reference).

2. **[P2] The required replacement LLM skill is missing.**  
   Location: `planning/PLAN.md:403`, `README.md:81`  
   Both documents direct agents to `.claude/skills/openai-llm/SKILL.md`, but that file is absent from the working tree. Git shows a staged rename followed by an unstaged deletion; the staged contents are still the old Cerebras instructions. Restore the replacement with the actual OpenAI instructions and stage its final contents. Otherwise agents either find no skill or, if only the existing index is committed, receive instructions for the wrong provider.

3. **[P2] Adding a ticker does not make an immediate buy work in Massive mode.**  
   Location: `planning/PLAN.md:444`  
   The plan promises that executing watchlist changes first makes “add PYPL and buy 5” work in one response. However, `MassiveDataSource.add_ticker()` only registers the ticker; its price arrives on a later poll. An immediate trade therefore fails the plan's own no-cached-price rule. Specify a bounded wait or fetch for the first valid quote before trading, or explicitly document that the buy fails until a quote arrives. Include this scenario in future chat integration tests.

4. **[P3] Documentation points to two other missing files.**  
   Location: `README.md:82`; deletion of `planning/MARKET_DATA_SUMMARY.md`  
   The README advertises `.claude/agents/change-reviewer.md`, but the agents directory is empty. The deleted market-data summary is still referenced by `CLAUDE.md:5`. Remove or correct these references, or restore the intended files, so users and agents can follow the documented workflows.

## Verification

- JSON parsing passed for the marketplace, plugin manifest, plugin hook, and project settings; valid JSON alone does not validate hook structure or shell syntax.
- `git diff --check HEAD` passed.
- Compared the new trading and streaming contracts with the existing market-data implementation.
- Did not execute the review hooks or call live providers. Application tests were not rerun because application source and tests did not change.
- No implementation files were modified during this review.
