# Changelog

## [Unreleased]
### Added/Changed
- MyPlanner v0: context assembly + truncation, required Engine call, kind=plan ledger, tracking-issue section upsert
- Pilot migration to mythings.testing: local SpyEngine/FakeGh deleted; SpyEngine(result=EngineResult) call sites became ScriptedEngine(str); the tracking-issue gh double is gh_tracking() over shared FakeGh; _attended_env autouse now wraps the promoted attended_env fixture (the promotion docs/tools/README.md deferred until a third consumer). Planner-specific manifest/repo-root builders stay local.
