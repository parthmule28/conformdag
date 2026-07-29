# Architecture

The implementation architecture is defined by the active OpenSpec change:

`openspec/changes/build-conformdag-v1-beta/design.md`

The core boundary is a local CLI with non-executing source analysis by default. Optional Airflow runtime inspection is isolated in pinned Docker profiles, and optional semantic evaluation uses a user-selected OpenAI-compatible endpoint. All engines produce one canonical versioned report model.
