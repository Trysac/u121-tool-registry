# Project record

## Objective
Versioned registry of agent tools with a bounded JSON Schema subset validator, semver resolution, permission checks before every call, and MCP-shaped export.

## Scope
- The public API documented in README.md, which is fully typed and tested.

## Out of scope
- Full JSON Schema ($ref, oneOf, patterns, formats).
- Remote tool discovery.
- Sandboxing tool execution.
- Persistence of tool definitions.

## Effort Metrics

| Metric | Value |
|---|---|
| Tokens (input / output) | 1227254 / 18245 |
| Hours (human) | pending measurement |
| Cost (USD) | 0.2772 |

## Factory run u121 (measured from API usage)

| Phase | Model | Batch | Input | Output | Cache write | Cache read | Cost (USD) |
|---|---|---|---|---|---|---|---|
| generation | gemini-3.8-flash | yes | 4328 | 12581 | 0 | 0 | 0.0252 |
| fix-1 | gemini-3.8-flash | no | 20166 | 2295 | 0 | 25361 | 0.0256 |
| fix-2 | gemini-3.8-flash | no | 16837 | 293 | 0 | 20918 | 0.0153 |
| fix-3 | gemini-3.8-flash | no | 47034 | 778 | 0 | 175047 | 0.0513 |
| fix-4 | gemini-3.8-flash | no | 90110 | 645 | 0 | 324578 | 0.0943 |
| audit | gemini-3.1-flash-lite | no | 71272 | 515 | 0 | 279045 | 0.0256 |
| docs | gemini-3.1-flash-lite | no | 152558 | 1138 | 0 | 0 | 0.0398 |

Total: $0.2772. Prices: Anthropic list prices.
