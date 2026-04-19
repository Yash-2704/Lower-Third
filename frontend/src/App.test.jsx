import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import App from "./App";

global.fetch = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
});

const mockSuccessResponse = {
  instance_id:        "lt_test01",
  video_url:          "/assets/lt_test01.webm",
  cache_hit:          false,
  qc_passed:          true,
  qc_warnings:        [],
  min_contrast_ratio: 17.8,
  manifest: {
    schema_version: "2.0",
    instance_id:    "lt_test01",
    duration_ms:    8000,
    loop:           true,
    qc:             { passed: true, warnings: [] },
    ffmpeg_overlay: "overlay=0:0:format=auto:enable='between(t,{IN},{OUT})'",
  },
};

describe("Form view", () => {
  it("renders the page title", () => {
    render(<App />);
    expect(screen.getByText("Lower Third Generator")).toBeTruthy();
  });

  it("renders the prompt textarea", () => {
    render(<App />);
    expect(screen.getByPlaceholderText(/Describe the lower third/)).toBeTruthy();
  });

  it("submit button is disabled when prompt is empty", () => {
    render(<App />);
    const btn = screen.getByRole("button", { name: /Generate/ });
    expect(btn.disabled).toBe(true);
  });

  it("submit button is disabled when prompt is only whitespace", () => {
    render(<App />);
    const textarea = screen.getByPlaceholderText(/Describe the lower third/);
    fireEvent.change(textarea, { target: { value: "   " } });
    const btn = screen.getByRole("button", { name: /Generate/ });
    expect(btn.disabled).toBe(true);
  });

  it("submit button is enabled when prompt has content", () => {
    render(<App />);
    const textarea = screen.getByPlaceholderText(/Describe the lower third/);
    fireEvent.change(textarea, { target: { value: "test prompt" } });
    const btn = screen.getByRole("button", { name: /Generate/ });
    expect(btn.disabled).toBe(false);
  });

  it("renders fps selector with default 30", () => {
    render(<App />);
    const select = screen.getByDisplayValue("30");
    expect(select).toBeTruthy();
  });

  it("renders style selector", () => {
    render(<App />);
    expect(screen.getByDisplayValue("minimal_dark_bar")).toBeTruthy();
  });
});

describe("Loading view", () => {
  it("shows loading text after submit", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockSuccessResponse,
    });
    render(<App />);
    const textarea = screen.getByPlaceholderText(/Describe the lower third/);
    fireEvent.change(textarea, { target: { value: "test prompt" } });
    fireEvent.click(screen.getByRole("button", { name: /Generate/ }));
    await waitFor(() => {
      expect(screen.getByText(/Generating lower third/)).toBeTruthy();
    });
  });
});

describe("Result view", () => {
  beforeEach(async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockSuccessResponse,
    });
    render(<App />);
    const textarea = screen.getByPlaceholderText(/Describe the lower third/);
    fireEvent.change(textarea, { target: { value: "test prompt" } });
    fireEvent.click(screen.getByRole("button", { name: /Generate/ }));
    await waitFor(() =>
      expect(screen.queryByText(/Generating lower third/)).toBeFalsy()
    );
  });

  it("shows Preview heading", () => {
    expect(screen.getByText("Preview")).toBeTruthy();
  });

  it("shows video element", () => {
    const video = document.querySelector("video");
    expect(video).toBeTruthy();
  });

  it("video src contains the video url", () => {
    const video = document.querySelector("video");
    expect(video.src).toContain("lt_test01.webm");
  });

  it("shows instance id", () => {
    expect(screen.getByText(/lt_test01/)).toBeTruthy();
  });

  it("shows cache miss", () => {
    expect(screen.getByText(/MISS/)).toBeTruthy();
  });

  it("shows qc passed", () => {
    expect(screen.getByText(/Passed/)).toBeTruthy();
  });

  it("shows manifest section", () => {
    expect(screen.getByText("Manifest")).toBeTruthy();
  });

  it("shows Generate Another button", () => {
    expect(screen.getByRole("button", { name: /Generate Another/ })).toBeTruthy();
  });

  it("Generate Another resets to form view", () => {
    fireEvent.click(screen.getByRole("button", { name: /Generate Another/ }));
    expect(screen.getByText("Lower Third Generator")).toBeTruthy();
    expect(screen.getByPlaceholderText(/Describe the lower third/)).toBeTruthy();
  });
});

describe("Error handling", () => {
  it("shows error message on API failure", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ error: "LLM parsing failed" }),
    });
    render(<App />);
    const textarea = screen.getByPlaceholderText(/Describe the lower third/);
    fireEvent.change(textarea, { target: { value: "test" } });
    fireEvent.click(screen.getByRole("button", { name: /Generate/ }));
    await waitFor(() => {
      expect(screen.getByText(/LLM parsing failed/)).toBeTruthy();
    });
  });

  it("shows network error message on fetch failure", async () => {
    global.fetch.mockRejectedValueOnce(new Error("Failed to fetch"));
    render(<App />);
    const textarea = screen.getByPlaceholderText(/Describe the lower third/);
    fireEvent.change(textarea, { target: { value: "test" } });
    fireEvent.click(screen.getByRole("button", { name: /Generate/ }));
    await waitFor(() => {
      expect(screen.getByText(/Network error/)).toBeTruthy();
    });
  });
});
