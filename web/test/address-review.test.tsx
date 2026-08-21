import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AddressReview } from "@/components/address-review";

describe("single-address review flow", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  });

  afterEach(() => vi.useRealTimers());

  it("reviews a valid address and enables copying only the final result", async () => {
    render(<AddressReview />);

    fireEvent.click(screen.getByRole("button", { name: /alamat lengkap/i }));
    fireEvent.click(screen.getByRole("button", { name: /periksa alamat/i }));
    expect(screen.getByText(/sedang membaca alamat/i)).toBeInTheDocument();

    await act(async () => vi.advanceTimersByTimeAsync(900));

    expect(screen.getByRole("heading", { name: "Siap diproses" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /salin alamat final/i })).toBeEnabled();
    expect(screen.getByText(/jalan braga no\. 99/i)).toBeInTheDocument();
  });

  it("requires explicit confirmation and revalidation before copying", async () => {
    render(<AddressReview />);

    fireEvent.click(screen.getByRole("button", { name: /perlu konfirmasi/i }));
    fireEvent.click(screen.getByRole("button", { name: /periksa alamat/i }));
    await act(async () => vi.advanceTimersByTimeAsync(900));

    expect(screen.getByRole("heading", { name: "Perlu konfirmasi" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /salin alamat final/i })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: /gunakan 40115/i }));
    expect(screen.getByRole("heading", { name: /perubahan belum divalidasi/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /validasi ulang perubahan/i }));
    await act(async () => vi.advanceTimersByTimeAsync(750));

    expect(screen.getByRole("heading", { name: "Siap diproses" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /salin alamat final/i })).toBeEnabled();
  });
});
