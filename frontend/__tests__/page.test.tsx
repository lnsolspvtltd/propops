import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ApprovalQueue from "@/app/page";

// Mock fetch
global.fetch = vi.fn();

const mockDraft = {
  draft_id: "draft-1",
  incident_id: "incident-1",
  incident_title: "Broken Window - Unit 203",
  urgency: "EMERGENCY" as const,
  subject: "Re: Broken Window - Unit 203",
  body: "Thank you for reporting the broken window...",
  recipient: "tenant@example.com",
  created_at: new Date().toISOString(),
};

const mockDraftHigh = {
  ...mockDraft,
  draft_id: "draft-2",
  urgency: "HIGH" as const,
};

const mockDraftMedium = {
  ...mockDraft,
  draft_id: "draft-3",
  urgency: "MEDIUM" as const,
};

describe("ApprovalQueue", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (global.fetch as any).mockClear();
  });

  it("renders empty state when no drafts pending", async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    });

    render(<ApprovalQueue />);

    await waitFor(() => {
      expect(screen.getByText("All caught up!")).toBeInTheDocument();
      expect(screen.getByText("No drafts waiting for approval.")).toBeInTheDocument();
    });
  });

  it("displays loading skeletons initially", () => {
    (global.fetch as any).mockImplementationOnce(
      () => new Promise(() => {}) // Never resolves
    );

    render(<ApprovalQueue />);

    const skeletons = document.querySelectorAll(".animate-pulse");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("fetches and displays pending drafts sorted by urgency", async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => [mockDraftMedium, mockDraftHigh, mockDraft],
    });

    render(<ApprovalQueue />);

    await waitFor(() => {
      const drafts = screen.getAllByRole("button", { pressed: false });
      // First draft should be EMERGENCY (due to sorting)
      expect(drafts[0]).toHaveTextContent("Broken Window - Unit 203");
      expect(drafts[0]).toHaveTextContent("EMERGENCY");
    });
  });

  it("shows draft details when card is clicked", async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => [mockDraft],
    });

    render(<ApprovalQueue />);

    await waitFor(() => {
      const draftCard = screen.getByRole("button", { pressed: false });
      fireEvent.click(draftCard);
    });

    await waitFor(() => {
      expect(screen.getByText(mockDraft.subject)).toBeInTheDocument();
      expect(screen.getByText(`To: ${mockDraft.recipient}`)).toBeInTheDocument();
      expect(screen.getByText(mockDraft.body)).toBeInTheDocument();
    });
  });

  it("approves draft optimistically and updates UI", async () => {
    const approveFetch = {
      ok: true,
      json: async () => ({ status: "approved" }),
    };

    (global.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [mockDraft],
      })
      .mockResolvedValueOnce(approveFetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      });

    render(<ApprovalQueue />);

    await waitFor(() => {
      const draftCard = screen.getByRole("button", { pressed: false });
      fireEvent.click(draftCard);
    });

    const approveBtn = screen.getByRole("button", { name: /Approve & Send/i });
    await userEvent.click(approveBtn);

    // Draft should be removed immediately (optimistic update)
    await waitFor(() => {
      expect(screen.getByText("All caught up!")).toBeInTheDocument();
    });

    // Verify the approve API was called
    expect((global.fetch as any).mock.calls[1][0]).toContain("/approve");
  });

  it("rejects draft and removes from queue", async () => {
    const rejectFetch = {
      ok: true,
      json: async () => ({ status: "rejected" }),
    };

    (global.fetch as any)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [mockDraft],
      })
      .mockResolvedValueOnce(rejectFetch)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      });

    render(<ApprovalQueue />);

    await waitFor(() => {
      const draftCard = screen.getByRole("button", { pressed: false });
      fireEvent.click(draftCard);
    });

    const rejectBtn = screen.getByRole("button", { name: /Reject/i });
    await userEvent.click(rejectBtn);

    // Draft should be removed
    await waitFor(() => {
      expect(screen.getByText("All caught up!")).toBeInTheDocument();
    });

    expect((global.fetch as any).mock.calls[1][0]).toContain("/reject");
  });

  it("handles API errors gracefully", async () => {
    (global.fetch as any).mockRejectedValueOnce(new Error("Network error"));

    render(<ApprovalQueue />);

    await waitFor(() => {
      expect(screen.getByText(/Error loading drafts/i)).toBeInTheDocument();
      expect(screen.getByText(/Network error/i)).toBeInTheDocument();
    });
  });

  it("displays urgency badges with correct colors", async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => [mockDraft],
    });

    render(<ApprovalQueue />);

    await waitFor(() => {
      const badge = screen.getByLabelText("Urgency: EMERGENCY");
      expect(badge).toHaveClass("bg-red-600/20");
      expect(badge).toHaveClass("text-red-400");
    });
  });

  it("closes detail panel on X button click", async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => [mockDraft],
    });

    render(<ApprovalQueue />);

    await waitFor(() => {
