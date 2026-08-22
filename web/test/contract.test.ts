import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  buildParseRequest,
  composeAddressText,
  newRequestId,
  toReviewResult,
  type ContractResponse,
} from "@/lib/contract";

// The frozen examples in contracts/examples are the authority here. Testing the
// adapter against hand-written fixtures would only prove it matches itself.
const EXAMPLES = resolve(dirname(fileURLToPath(import.meta.url)), "../../contracts/examples");

const example = (name: string) =>
  JSON.parse(readFileSync(resolve(EXAMPLES, name), "utf-8"));

const REQUEST_ID = /^[A-Za-z0-9][A-Za-z0-9_-]{7,63}$/;

describe("request building", () => {
  it("produces the shape the frozen request schema requires", () => {
    const request = buildParseRequest("Jl. Asia Afrika No. 1, Bandung");
    expect(request.document_type).toBe("address_parse_request");
    expect(request.schema_version).toBe("1.0.0");
    expect(request.request_id).toMatch(REQUEST_ID);
    expect(request.input.address_text).toBe("Jl. Asia Afrika No. 1, Bandung");
    expect(Object.keys(request.input).sort()).toEqual([
      "address_text",
      "geocoding_consent",
    ]);
  });

  it("never requests geocoding unless the caller opts in", () => {
    expect(buildParseRequest("x").input.geocoding_consent).toBe(false);
    expect(
      buildParseRequest("x", { geocodingConsent: true }).input.geocoding_consent,
    ).toBe(true);
  });

  it("generates request ids that satisfy the contract pattern", () => {
    for (let index = 0; index < 50; index += 1) {
      expect(newRequestId()).toMatch(REQUEST_ID);
    }
  });

  it("matches the frozen example request field for field", () => {
    const frozen = example("success.request.json");
    const built = buildParseRequest(frozen.input.address_text, {
      geocodingConsent: frozen.input.geocoding_consent,
      requestId: frozen.request_id,
    });
    expect(built).toEqual(frozen);
  });
});

describe("response mapping", () => {
  it("maps the ready example onto a final review", () => {
    const response = example("success.response.json") as ContractResponse;
    const result = toReviewResult(response);
    expect(result.status).toBe("SIAP_DIPROSES");
    expect(result.isFinal).toBe(true);
    expect(result.issues).toHaveLength(0);
    expect(result.id).toBe(response.request_id);
    expect(result.normalizedAddress).toBe(response.normalized_address.value);
    expect(result.versions.reference).toBe(response.versions.reference_data);
  });

  it("shows only redacted input, never the raw address text", () => {
    const response = example("success.response.json") as ContractResponse;
    const result = toReviewResult(response);
    expect(result.redactedInput).toBe(response.pii.redacted_text.value);
  });

  it("carries every issue with its severity, fields, and question", () => {
    const response = example("ambiguity.response.json") as ContractResponse;
    const result = toReviewResult(response);
    expect(result.status).toBe("PERLU_KONFIRMASI");
    expect(result.isFinal).toBe(false);
    expect(result.issues).toHaveLength(response.quality_gate.issues.length);
    const [issue] = result.issues;
    const [source] = response.quality_gate.issues;
    expect(issue.reasonCode).toBe(source.reason_code);
    expect(issue.severity).toBe(source.severity);
    expect(issue.affectedFields).toEqual(source.affected_fields);
    expect(issue.question).toBe(source.clarification_question);
    expect(issue.title).not.toBe("");
  });

  it("never reports final when the gate found a high-severity conflict", () => {
    const response = example("invalid.response.json") as ContractResponse;
    const result = toReviewResult(response);
    expect(result.status).toBe("TIDAK_VALID");
    expect(result.isFinal).toBe(false);
    expect(result.issues.some((issue) => issue.severity === "high")).toBe(true);
  });

  it("marks a component with an unapplied correction as a suggestion", () => {
    const response = example("ambiguity.response.json") as ContractResponse;
    const pending = response.corrections.find(
      (correction) => correction.decision === "requires_confirmation",
    );
    expect(pending).toBeDefined();
    const result = toReviewResult(response);
    const component = result.components.find(
      (item) => item.field === pending!.field,
    );
    expect(component?.state).toBe("suggested");
    expect(component?.suggestion).toBe(pending!.proposed_value.value);
  });

  it("keeps model_score as a score and only for model-derived values", () => {
    const response = example("ambiguity.response.json") as ContractResponse;
    const result = toReviewResult(response);
    for (const entry of response.components) {
      const mapped = result.components.find(
        (item) => item.field === entry.field,
      );
      if (entry.result.model_score === null) {
        expect(mapped?.modelScore).toBeUndefined();
      } else {
        expect(mapped?.modelScore).toBe(entry.result.model_score);
      }
    }
  });

  it("emits only severities the quality gate can produce", () => {
    for (const name of [
      "success.response.json",
      "ambiguity.response.json",
      "invalid.response.json",
      "external-failure.response.json",
    ]) {
      const result = toReviewResult(example(name) as ContractResponse);
      for (const issue of result.issues) {
        expect(["high", "medium"]).toContain(issue.severity);
      }
    }
  });

  it("does not let an external geocoder failure invalidate the address", () => {
    const response = example("external-failure.response.json") as ContractResponse;
    const result = toReviewResult(response);
    expect(result.status).toBe("SIAP_DIPROSES");
    expect(result.isFinal).toBe(true);
  });

  it("maps every frozen example without throwing", () => {
    for (const name of [
      "success.response.json",
      "ambiguity.response.json",
      "invalid.response.json",
      "external-failure.response.json",
    ]) {
      const result = toReviewResult(example(name) as ContractResponse);
      expect(result.components.length).toBeGreaterThan(0);
      expect(result.redactedInput).not.toBe("");
    }
  });
});

describe("re-validation input", () => {
  it("rebuilds an address line from edited components", () => {
    const response = example("ambiguity.response.json") as ContractResponse;
    const result = toReviewResult(response);
    const text = composeAddressText(result.components);
    expect(text).not.toBe("");
    for (const component of result.components) {
      if (component.value.trim()) {
        expect(text).toContain(component.value.trim());
      }
    }
  });
});
