"""MCP server over stdio (optional), so any MCP-capable assistant can search PersonalOS.

Works with Claude Code, Claude Desktop and other MCP clients, including desktop apps that run local models.
It speaks JSON-RPC on stdin/stdout only: no ports are opened. Tools are read-only unless
integrations.mcp.allow_capture is true, which adds a tool that creates new inbox notes.
"""
import json
import sys

from .. import __version__

NAME = "mcp"
DESCRIPTION = "MCP server (stdio) exposing memory search to MCP-capable AI assistants"
PROTOCOL_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]

TOOLS = [
    {"name": "search_memory",
     "description": "Search the user's PersonalOS memory (notes, AI memory, archived conversations). Returns "
                    "ranked snippets with a trust label, the file path, a loc and the date. Active memory first.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "a few specific keywords"},
         "limit": {"type": "integer", "minimum": 1, "maximum": 25},
         "all_tiers": {"type": "boolean", "description": "always include long-term memory"}},
         "required": ["query"]}},
    {"name": "read_memory",
     "description": "Read part of an indexed file returned by search_memory (secrets are redacted).",
     "inputSchema": {"type": "object", "properties": {
         "path": {"type": "string"}, "loc": {"type": "string", "description": "e.g. L12-40 or 'line 100-140'"}},
         "required": ["path"]}},
    {"name": "list_inbox",
     "description": "List unprocessed notes in the user's PersonalOS inbox.",
     "inputSchema": {"type": "object", "properties": {}}},
]
CAPTURE_TOOL = {
    "name": "capture_note",
    "description": "Create a NEW note in the user's PersonalOS inbox. Never edits existing notes. Only use when "
                   "the user asked to save something.",
    "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}, "title": {"type": "string"}},
                    "required": ["text"]}}


def enable(cfg):
    from ..integrations.claude_code import launcher
    cfg.data["integrations"][NAME]["enabled"] = True
    cfg.save()
    cmd = launcher()
    return ["enabled. Register it with your assistant, for example:",
            f"  Claude Code:    claude mcp add personalos -- \"{cmd}\" mcp",
            '  JSON clients:   {"mcpServers": {"personalos": {"command": "' + cmd.replace("\\", "\\\\")
            + '", "args": ["mcp"]}}}',
            "tools are read-only; set integrations.mcp.allow_capture to true to allow inbox capture"]


def disable(cfg):
    cfg.data["integrations"][NAME]["enabled"] = False
    cfg.save()
    return ["disabled; `personalos mcp` will now refuse to start. Remove it from your assistant's MCP list too."]


def status(cfg):
    return {"allow_capture": bool(cfg.integration(NAME).get("allow_capture"))}


def _fmt_hits(res):
    lines = []
    for tier in ("tier1", "tier2"):
        for h in res.get(tier, []):
            head = f" > {h['heading']}" if h["heading"] and h["heading"] != "frontmatter" else ""
            when = f"conversation {h['ts']}" if h["kind"] == "transcript" and h["ts"] else f"modified {h['date']}"
            lines.append(f"[{h['label']}] {h['title']}{head}\n  path: {h['path']}\n  loc: {h['loc']}  ({when})\n"
                         f"  {' '.join(h['snip'].split())[:400]}")
    return "\n\n".join(lines) or "no matches"


def call_tool(cfg, name, args):
    from .. import index, vault
    if name == "search_memory":
        limit = max(1, min(int(args.get("limit") or cfg.data["search"]["limit"]), 25))
        res = index.search(cfg, str(args["query"]), limit, bool(args.get("all_tiers")))
        return _fmt_hits(res)
    if name == "read_memory":
        r = index.show(cfg, args["path"], args.get("loc"))
        return f"[{r['label']}] {r['path']} (modified {r['date']})\n\n{r['text']}"
    if name == "list_inbox":
        notes = vault.list_notes(cfg, "inbox")
        return "\n".join(f"- {n['title']} ({n['modified']}) {n['rel']}" for n in notes) or "inbox is empty"
    if name == "capture_note" and cfg.integration(NAME).get("allow_capture"):
        p = vault.capture(cfg, args["text"], args.get("title"), source="mcp")
        return f"created {p}"
    raise KeyError(f"unknown tool {name}")


def handle(cfg, msg):
    """Return the JSON-RPC response for one message, or None for notifications."""
    if not isinstance(msg, dict) or "id" not in msg:
        return None
    mid, method, params = msg["id"], msg.get("method"), msg.get("params") or {}

    def ok(result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        return ok({"protocolVersion": version, "capabilities": {"tools": {}},
                   "serverInfo": {"name": "personalos", "version": __version__}})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        tools = TOOLS + ([CAPTURE_TOOL] if cfg.integration(NAME).get("allow_capture") else [])
        return ok({"tools": tools})
    if method == "tools/call":
        try:
            text = call_tool(cfg, params.get("name"), params.get("arguments") or {})
            return ok({"content": [{"type": "text", "text": text}], "isError": False})
        except Exception as e:  # reported to the client as a tool error, never as a crash
            return ok({"content": [{"type": "text", "text": f"error: {e}"}], "isError": True})
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve(cfg, stdin=None, stdout=None):
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    for raw in stdin:
        try:
            msg = json.loads(raw.decode("utf-8"))
        except ValueError:
            resp = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            resp = handle(cfg, msg)
        if resp is not None:
            stdout.write((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
            stdout.flush()
