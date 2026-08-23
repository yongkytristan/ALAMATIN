import { describe, expect, it } from "vitest";
import { DEMO_ADDRESSES, confirmationFixture, invalidFixture, readyFixture } from "@/lib/fixtures";
import { parseAddress } from "@/lib/api";

/**
 * The demo buttons are the first thing anyone touches, so a mis-wired one is a
 * broken product tour. Two failures already happened here: keyword routing
 * mis-classified an address once its wording changed, and against the real
 * backend all three buttons collapsed to a single status because the sample
 * addresses omitted the designators the rule extractor needs.
 */
describe("demo addresses", () => {
  it("routes each demo address to its intended fixture", async () => {
    await expect(parseAddress(DEMO_ADDRESSES.ready)).resolves.toMatchObject({
      status: readyFixture.status,
    });
    await expect(parseAddress(DEMO_ADDRESSES.confirmation)).resolves.toMatchObject({
      status: confirmationFixture.status,
    });
    await expect(parseAddress(DEMO_ADDRESSES.invalid)).resolves.toMatchObject({
      status: invalidFixture.status,
    });
  });

  it("demonstrates three distinct statuses", () => {
    const statuses = [readyFixture.status, confirmationFixture.status, invalidFixture.status];
    expect(new Set(statuses).size).toBe(3);
  });

  it("keeps the demo addresses distinct", () => {
    const values = Object.values(DEMO_ADDRESSES);
    expect(new Set(values).size).toBe(values.length);
  });

  it("spells out the designators the rule extractor needs", () => {
    // Without "Kel."/"Kec." the shipped extractor recovers neither field, so
    // even a correct address returns PERLU_KONFIRMASI from the real backend and
    // the SIAP_DIPROSES button demonstrates nothing.
    expect(DEMO_ADDRESSES.ready).toMatch(/\bKel\./);
    expect(DEMO_ADDRESSES.ready).toMatch(/\bKec\./);
  });

  it("keeps the invalid sample a reference contradiction, not a gap", () => {
    // Only an administrative conflict the governed reference can prove reaches
    // TIDAK_VALID. A village merely absent from the reference is medium.
    expect(DEMO_ADDRESSES.invalid).toMatch(/Kel\. Braga/i);
    expect(DEMO_ADDRESSES.invalid).toMatch(/Kec\. Coblong/i);
  });
});
