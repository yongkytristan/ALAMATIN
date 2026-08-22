import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AddressReview } from "@/components/address-review";
import { confirmationFixture, invalidFixture, readyFixture } from "@/lib/fixtures";
import type { ReviewResult } from "@/lib/types";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const schema = JSON.parse(
  readFileSync(resolve(ROOT, "contracts/address-api.v1.schema.json"), "utf-8"),
);
const REASON_CODES: string[] =
  schema.$defs.qualityIssue.properties.reason_code.enum;

const FIXTURES: Array<[string, ReviewResult]> = [
  ["ready", readyFixture],
  ["confirmation", confirmationFixture],
  ["invalid", invalidFixture],
];

// The frozen gate's severity for each reason code. A fixture that disagrees
// demonstrates a state the real backend can never produce.
const FROZEN_SEVERITY: Record<string, "high" | "medium"> = {
  KODEPOS_TIDAK_COCOK: "high",
  ADMINISTRATIVE_CONFLICT: "high",
  KELURAHAN_TIDAK_DITEMUKAN: "medium",
  MISSING_ADMINISTRATIVE_FIELDS: "medium",
  AMBIGUOUS_ADMINISTRATIVE_CANDIDATES: "medium",
  CORRECTION_REQUIRES_CONFIRMATION: "medium",
};

// ALM-024 confines high severity to the fields the reference can contradict.
const CRITICAL_FIELDS = [
  "KELURAHAN",
  "KECAMATAN",
  "KOTA_KABUPATEN",
  "PROVINSI",
  "KODEPOS",
];

describe("fixtures match the frozen quality gate", () => {
  it.each(FIXTURES)("%s uses only contract reason codes", (_name, fixture) => {
    for (const issue of fixture.issues) {
      expect(REASON_CODES).toContain(issue.reasonCode);
    }
  });

  it.each(FIXTURES)("%s uses each code's frozen severity", (_name, fixture) => {
    for (const issue of fixture.issues) {
      expect(issue.severity).toBe(FROZEN_SEVERITY[issue.reasonCode]);
    }
  });

  it.each(FIXTURES)("%s status follows the frozen precedence", (_name, fixture) => {
    const expected = fixture.issues.some((issue) => issue.severity === "high")
      ? "TIDAK_VALID"
      : fixture.issues.length
        ? "PERLU_KONFIRMASI"
        : "SIAP_DIPROSES";
    expect(fixture.status).toBe(expected);
    expect(fixture.isFinal).toBe(expected === "SIAP_DIPROSES");
  });

  it.each(FIXTURES)("%s keeps high severity on critical fields only", (_name, fixture) => {
    for (const issue of fixture.issues) {
      if (issue.severity !== "high") continue;
      for (const field of issue.affectedFields) {
        expect(CRITICAL_FIELDS).toContain(field);
      }
    }
  });
});

describe("UI behaviour against the contract", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  afterEach(() => vi.useRealTimers());

  const openConfirmationCase = async () => {
    render(<AddressReview />);
    fireEvent.click(screen.getByRole("button", { name: /perlu konfirmasi/i }));
    fireEvent.click(screen.getByRole("button", { name: /periksa alamat/i }));
    await act(async () => vi.advanceTimersByTimeAsync(900));
  };

  it("shows the redacted input instead of rebuilding it from components", async () => {
    await openConfirmationCase();
    const strip = screen.getByLabelText(/input setelah redaksi pii/i);
    expect(strip).toHaveTextContent(confirmationFixture.redactedInput);
  });

  it("offers accept and reject driven by the suggestion, not a reason code", async () => {
    // The old implementation gated these buttons on "POSTAL_CODE_CONFLICT",
    // which the frozen contract does not define, so they never appeared with
    // real API data.
    expect(confirmationFixture.issues[0].reasonCode).toBe(
      "CORRECTION_REQUIRES_CONFIRMATION",
    );
    const suggested = confirmationFixture.components.find(
      (item) => item.state === "suggested",
    );
    expect(suggested?.suggestion).toBeTruthy();

    await openConfirmationCase();
    expect(
      screen.getByRole("button", {
        name: new RegExp(`gunakan ${suggested!.suggestion}`, "i"),
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: new RegExp(`pertahankan ${suggested!.value}`, "i"),
      }),
    ).toBeInTheDocument();
  });

  it("applies a confirmation to the suggested field and keeps it unfinished", async () => {
    const suggested = confirmationFixture.components.find(
      (item) => item.state === "suggested",
    )!;
    await openConfirmationCase();
    fireEvent.click(
      screen.getByRole("button", {
        name: new RegExp(`gunakan ${suggested.suggestion}`, "i"),
      }),
    );
    // Confirming is not the same as finalising: the result must be revalidated.
    expect(
      screen.getByRole("heading", { name: /perubahan belum divalidasi/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /salin alamat final/i }),
    ).toBeDisabled();
  });

  it("can edit a component from the keyboard alone", async () => {
    await openConfirmationCase();
    const [editButton] = screen.getAllByRole("button", { name: /^edit /i });
    editButton.focus();
    expect(editButton).toHaveFocus();
    fireEvent.click(editButton);
    const field = screen.getByRole("textbox", { name: /^edit /i });
    fireEvent.change(field, { target: { value: "40115" } });
    fireEvent.keyDown(field, { key: "Enter" });
    expect(
      screen.queryByRole("textbox", { name: /^edit /i }),
    ).not.toBeInTheDocument();
  });

  it("reaches a final, copyable result without any code change", async () => {
    const suggested = confirmationFixture.components.find(
      (item) => item.state === "suggested",
    )!;
    await openConfirmationCase();
    fireEvent.click(
      screen.getByRole("button", {
        name: new RegExp(`gunakan ${suggested.suggestion}`, "i"),
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: /validasi ulang perubahan/i }));
    await act(async () => vi.advanceTimersByTimeAsync(750));
    expect(screen.getByRole("heading", { name: "Siap diproses" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /salin alamat final/i })).toBeEnabled();
  });
});
