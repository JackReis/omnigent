{
  "status": "PASS",
  "source": "omnigent",
  "route": "ringer",
  "worker": 2,
  "prompt": "Implement the minimum deny-by-default claim gate identified in the ADR-0019 admission pass for Bifrost hub hardening. The claim gate must check canonical Beads claim evidence and caller identity, reject replay/stale/malformed/unavailable cases, and produce auditable evidence. Do not enable Ringside write operations merely by completing implementation; enablement requires the separately recorded proof verdict.\n\nAcceptance criteria:\n1. Fixtures prove allowed claim, absent claim, wrong claimant, replay/stale claim, malformed authority envelope, and unavailable Beads behavior\n2. All failures deny writes\n3. Successful proof emits stable evidence tied to a Beads identifier and claimant identity\n4. Ringside remains read-only unless the proof passes and an explicit approval is recorded\n5. Artifact, verification, commit, push, revocation/rollback are recorded\n\nBead: hermes-9ill.4\nParent epic: hermes-9ill [epic] Bifrost hub hardening \u2014 Ringer-gated execution"
}
