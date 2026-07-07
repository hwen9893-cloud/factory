# Novel Factory Prototype

Independent prototype for `factory.novel`.

This folder is intentionally self-contained and uses only Python standard library in the first iteration.
The default model backend is `mock`, so the framework can be tested before Ollama is connected.

## Scope

Initial pipeline:

```text
story_seed
  -> skill.novel.outline
  -> skill.novel.plot
  -> skill.novel.chapter
  -> skill.novel.dialogue
  -> skill.qa.consistency
  -> skill.novel.export
```

`skill.novel.screenplay` is reserved for a later iteration.

## Run

From repository root:

```bash
python3 -m novel_factory.scripts.run_demo
```

Outputs are written to:

```text
novel_factory/runs/run_0001/
```

## Switch To Ollama Later

Set the backend in `novel_factory/acs_novel_factory/center/model/profiles.json`:

```json
{
  "novel_write": {
    "backend": "ollama",
    "model": "llama3.1:8b",
    "base_url": "http://127.0.0.1:11434"
  }
}
```

The current skeleton keeps model calls behind `ModelClient`, matching `docs/34-center.model接口规范.md`.
