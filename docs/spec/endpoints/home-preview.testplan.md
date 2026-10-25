# Home preview test plan

1. Shared contract fixtures: valid states and strict extra-field, invalid public reason, unknown evidence, clocks, fixtures, full/partial count, PEN validation.
2. Pure priority tests across eight groups, ongoing-first, stable tie and dynamic English cup classification; other countries' Cup not treated as domestic English cup.
3. Isolated PostgreSQL 127.0.0.1:55441 only. Build existing baseline tables + apply new Supabase migration; inspect constraints; fixtures use generated test IDs. Seed deterministic DB evidence, no source/provider calls. Verify no operational DB writes.
4. Service/API integration: recommendations → chosen fixture → same stored payload; pending, facts-only, previous after failure; no valid version; invalid stored mock/identity; bounded calls; rollback and duplicate slot; kickoff crossing and target disable.
5. Vertex adapter: fixed STOP response, MAX_TOKENS/blocked/empty/malformed/extra fields/unregistered refs. Production HTTP calls only in explicit smoke command.
6. FE type/build/E2E: request identity cancellation, errors retain correct selected fixture, no polling/live score, missing sources, source clocks; L3 local API with external-call traps.

PRE-02 external coverage gaps do not authorize synthesizing provider responses. MCP is unavailable; official API read-only responses were captured before adapters were implemented. No automatic publication of unverified grounding claims.
