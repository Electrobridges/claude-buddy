# Claude Code Session Format (`~/.claude/projects`)

**English** · [Español](formato-jsonl.md)

Documented by inspecting 39 real sessions (Claude Code 2.1.331, November 2026).
**Unofficial** format: it may change between versions, so the parser must tolerate
unknown types and fields.

## Folder Structure

```
~/.claude/projects/
└── <encoded-cwd>/                    e.g. c--dev-Buddy-chatui
    ├── <session-id>.jsonl            one session = one file (name = sessionId)
    ├── <session-id>/
    │   ├── subagents/agent-*.jsonl   subagent transcripts (+ .meta.json)
    │   ├── tool-results/*.txt        long tool outputs
    │   └── custom-title.json         {"customTitle": "..."} (optional)
    └── memory/*.md                   project memory (not sessions)
```

- Sessions = only `*/<uuid>.jsonl` at the top level. Ignore `subagents/`, `tool-results/`, `memory/`.
- **The folder name is a lossy encoding**: `:`, `\`, `/`, spaces, and `.` all become `-`
  (`c:\dev\Buddy chatui` → `c--dev-Buddy-chatui`). It cannot be decoded: the actual `cwd`
  must be read from inside the `.jsonl`.
- The same path may appear twice with different drive-letter casing (`C--…` from the CLI,
  `c--…` from VS Code). To group by project, normalize case on Windows.
- The `CLAUDE_CONFIG_DIR` environment variable can be honored if it points to another config folder.

## Records

Each line is a JSON object with a `type` field. The first line is **not** necessarily
a message (it is usually `queue-operation`, `session-owner`, or `mode`). In the sample: 0 corrupt
lines, and `sessionId` always matches the filename.

| `type` | Use for Claude Buddy |
|---|---|
| `user` | User message **or** tool result (see below) |
| `assistant` | Model response; **one record per content block** |
| `ai-title` | `aiTitle`: auto-generated title (rewritten multiple times) |
| `custom-title` | `customTitle`: user-defined title (takes precedence) |
| `summary` | `summary`: title from older versions |
| `last-prompt` | `lastPrompt`: last prompt sent |
| `system` | Events (`subtype`: `compact_boundary`, `api_error`, `turn_duration`…) |
| `attachment`, `api-request*`, `file-history-*`, `mode`, `permission-mode`, `queue-operation`, `session-owner`, `cost-state`, `tools-used`, `atis-latch`, `agent-name`, `teleported-from`, `artifact-*` | Internal: ignore |

Common fields on `user`/`assistant`/`system`/`attachment`: `uuid`, `parentUuid` (conversation
tree), `sessionId`, `timestamp`, `cwd`, `gitBranch`, `version`, `entrypoint`, `isSidechain`.

- `timestamp`: ISO 8601 UTC with milliseconds (`2026-11-24T12:08:31.123Z`).
- `entrypoint`: `claude-vscode`, `cli`, `claude-desktop`, `sdk-ts` (and presumably `sdk-py`).
- `cwd`: may change within a session (always to a **subdirectory** of the initial one).
  The original project directory is the `cwd` of the **first** record that has one.

### `message` in `user`

`message = {"role": "user", "content": str | [blocks]}`, with `text`, `image`,
`document`, and `tool_result` blocks.

A `user` record is **not** a real prompt if any of the following apply:

- it has `toolUseResult` (`tool_result` content; it is the response to a tool),
- `isMeta: true` (injected notices), `isCompactSummary: true` (post-compaction summary),
- `isSidechain: true` (subagent; did not appear in top-level files).

Within a real prompt, some text blocks are injected context rather than user text:
`<ide_opened_file>`, `<ide_selection>` (VS Code sends these as a **separate** block before the text),
`<system-reminder>`, `<task-notification>`, `<local-command-stdout>`.
Special cases:

- `<command-name>/xyz</command-name>…<command-args>…` → slash command; display as `/xyz args`.
- `<pasted_content …>…</pasted_content>` → user-pasted text; this is real content.
- Image-only prompts → no text.

### `message` in `assistant`

Anthropic API format (`id`, `model`, `content`, `stop_reason`, `usage`…).
A single response is split across **multiple consecutive records with the same `message.id`**,
one per block (`thinking`, `text`, `tool_use`). To count or display responses, you must
group by `message.id`.

## Conversation Order and Branching (Phase 3)

`uuid` / `parentUuid` form a tree. In real data there are around 745 branches, but
nearly all of them (744) are **parallel tool results**: each `tool_result` hangs off
its `tool_use`, and the conversation continues only from the last one. True branches (where the user
rewinds and edits a message) are rare.

History is built as follows:

1. Leaf = last non-sidechain `user`/`assistant` record in the file.
2. Main chain = ancestors of the leaf following `parentUuid`; if `null`, follow
   `logicalParentUuid` (`compact_boundary` records break the chain this way).
3. Records are traversed **in file order**, displaying those on the main chain.
   Off-chain tool results are accepted (parallel calls), and of those,
   only errors (`is_error`) are displayed.
4. Consecutive `assistant` records with the same `message.id` are merged into a single response.

## Proposed Definitions for Phase 1

- **Title**: first real user prompt (applying the rules above), truncated to one line.
  If none exists, `customTitle` → `aiTitle` → `summary` → `(sin título)` (untitled).
- **Last activity**: maximum `timestamp` in the file; if none, the file's `mtime`.
- **Message count**: real user prompts + assistant responses with visible text
  (grouped by `message.id`). Does not count tool calls or tool results.
- **Project**: initial `cwd`; if missing, the encoded folder name.
