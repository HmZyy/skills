# skills

Claude Code skills.

| Skill | What it does |
| --- | --- |
| [delog-analyze](delog-analyze/SKILL.md) | Analyze the log loaded in a running DeLOG session: answer a question or diagnose what went wrong, plot evidence, publish derived signals, add annotations and markers. |

## Install

Link a skill into your Claude Code skills directory:

    ln -s ~/projects/hmzyy/skills/delog-analyze ~/.claude/skills/delog-analyze

## Check

    python3 tools/check_skill.py delog-analyze/SKILL.md
