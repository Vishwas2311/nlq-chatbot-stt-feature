# Production acceptance checklist

The code package is merge-ready; production approval requires every applicable
item below to have named evidence and an owner.

## Merge and regression

- [ ] Existing chatbot tests recorded before merge and pass after merge.
- [ ] No behavioral change to `/ews-chatbot/chat`, sessions, history, Oracle,
      Redis history, MCP, NL2SQL or LLM workflows.
- [ ] Overlay Python tests and the target chatbot's merged frontend tests pass
      in the target dependency set.
- [ ] Lint, strict typing, SAST, dependency and secret scans pass.

## Identity and authorization

- [ ] JWT signature, permitted algorithm, issuer, audience and expiry are
      verified by the injected chatbot auth dependency.
- [ ] Caller IDs come only from verified claims.
- [ ] Missing/invalid token returns 401 before multipart parsing.
- [ ] Authenticated but unauthorized caller returns 403.

## Data protection

- [ ] Azure key is held only in the approved runtime secret manager.
- [ ] Previously exposed/photographed keys remain rotated.
- [ ] Browser bundle and responses contain no Azure key.
- [ ] Audio/transcripts are not persisted, cached or logged.
- [ ] Logs contain only request/correlation ID, status, byte/duration counts and
      latency; log access and retention meet company policy.
- [ ] TLS verification remains enabled and endpoint host allowlisting is exact.

## Capacity and resilience

- [ ] Existing async Redis is used for distributed principal/client/global rate
      limits and concurrency leases across every replica.
- [ ] Redis outage fails closed for new STT requests.
- [ ] Upload byte, decoded duration, locale and real container/codec validation
      are enabled before Azure invocation.
- [ ] Timeout and at-most-one-retry behavior is approved.
- [ ] Azure Speech quota/concurrency and application peak load are tested.

## Network, browser and operations

- [ ] Target runtime can reach only the approved Azure Speech HTTPS endpoint.
- [ ] CORS uses explicit approved frontend origins; no wildcard with credentials.
- [ ] Microphone works on the supported HTTPS browsers and permission denial is
      handled.
- [ ] Transcript populates the current textbox but never auto-sends.
- [ ] Azure metrics confirm synthetic live requests reached the intended Speech
      resource.
- [ ] Monitoring, alerts, budget, key rotation, rollback and incident owners are
      documented.
