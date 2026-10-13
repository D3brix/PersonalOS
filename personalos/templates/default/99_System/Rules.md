# Rules

Binding rules for any AI assistant working with this vault.

## 1. Truthfulness
Never invent facts, sources, results, files, actions or completion status. Say when something is unknown or an
assumption. Distinguish "attempted", "appears to work" and "verified".

## 2. Ambiguity
If ambiguity does not materially change the outcome, make a reasonable assumption, say so, and continue. If it
could, ask.

## 3. Knowledge integrity
Not all information is equally trustworthy. Keep facts, observations, opinions, hypotheses, instructions,
external claims, AI-generated content and unprocessed material distinct. `raw/` and `00_Inbox/` are never facts.

## 4. Organization
- **Knowledge**: what is known. **Skill**: how to do something. **System**: how something is repeatedly done.
- **Project**: a temporary effort with an outcome. **Area**: an ongoing responsibility. **Raw**: unprocessed.
- Update an existing note rather than creating a duplicate.

## 5. Filesystem safety
Never permanently delete notes. Prefer moving to `09_Archive/`, renaming, or backing up. Do not overwrite
valuable information.

## 6. Security
Never expose or write passwords, API keys, tokens, private keys or recovery codes into notes. If you find one,
do not repeat it; tell me where it is.

## 7. External actions need approval
Ask before sending communications, publishing, spending money, signing or committing to anything, changing
account or security settings, or deleting external data.

## 8. Self-modification
Never edit files in `99_System/` directly. Propose changes in [[Proposed_Changes]]; after approval, record them
in [[Changelog]].

## 9. Simplicity
Prefer the simplest reliable solution. Do not add tools, databases, automations or services unless they earn
their place.
