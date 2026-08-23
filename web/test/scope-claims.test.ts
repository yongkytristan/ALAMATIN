import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

/**
 * The reference covers Jawa Barat only, and docs/limitations.md states plainly
 * that there is "no national coverage and no claim to any". The interface used
 * to say "Periksa satu alamat Indonesia", which promised exactly that.
 *
 * A seller pasting a Jakarta address gets OUTSIDE_REFERENCE_COVERAGE, so
 * implying national scope in the hero copy sets them up to be surprised by the
 * product's own honest answer.
 */
const files = ["components/address-review.tsx", "app/layout.tsx"] as const;

const read = (name: string) => readFileSync(name, "utf8");

describe("scope claims in the interface", () => {
  it("never implies national coverage", () => {
    for (const name of files) {
      const text = read(name);
      // "Indonesia" may legitimately appear in prose about Indonesian
      // addresses, but not as the scope of what this build checks.
      expect(text).not.toMatch(/alamat Indonesia/i);
      expect(text).not.toMatch(/seluruh Indonesia/i);
      expect(text).not.toMatch(/fulfillment Indonesia/i);
    }
  });

  it("names Jawa Barat as the coverage", () => {
    expect(read("components/address-review.tsx")).toMatch(/di Jawa Barat/);
    expect(read("app/layout.tsx")).toMatch(/Jawa Barat/);
  });

  it("states the reference size the data actually has", () => {
    // 5,957 rows in data/processed/jabar-reference-v1-verified.json. A number
    // shown to a user must match the artifact, not a remembered figure.
    expect(read("components/address-review.tsx")).toMatch(/5\.957 kelurahan\/desa/);
  });

  it("teaches a placeholder format the extractor can actually parse", () => {
    // Without Kel./Kec. the rule extractor recovers neither field, so a user
    // copying the placeholder would land in PERLU_KONFIRMASI and conclude the
    // product is broken.
    const text = read("components/address-review.tsx");
    const placeholder = text.match(/placeholder="Contoh: ([^"]+)"/)?.[1] ?? "";
    expect(placeholder).toMatch(/\bKel\./);
    expect(placeholder).toMatch(/\bKec\./);
  });
});
