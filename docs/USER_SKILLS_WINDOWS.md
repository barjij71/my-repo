# JARVIS Windows user skills

The Windows assistant supports a local, user-managed skill library.

## Import

Open Settings & Access → User Skills Library and upload one .md, .markdown, .txt, or .json file. Markdown may include simple frontmatter with name, description, and keywords fields. JSON supports name, optional description, optional keywords, and content or instructions.

## Limits and storage

- Maximum 50 skills.
- Maximum input file size: 100,000 characters.
- Maximum instructions per skill: 12,000 characters.
- At most three enabled skills are added to one request, with an aggregate prompt budget of 18,000 characters.
- Skills are stored locally under the current Windows user's %LOCALAPPDATA%/JARVIS/skills.json directory (or the platform user-data fallback).

## Safety

New imports are disabled until reviewed and enabled. Imported text is treated as untrusted reference material. It cannot override system safety rules, grant permissions, add tools, or execute code. The skill manager accepts text formats only and rejects scripts and archives. Removing a skill deletes its local entry.

The skill library is local to this Windows profile; it does not currently synchronize automatically with Android. The Android app has its own skill library and prompt integration.
