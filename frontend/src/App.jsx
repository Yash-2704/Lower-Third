import { useReducer, useRef } from "react";

const API_BASE = "http://localhost:8001";
const DEFAULT_FPS = 30;

const initialState = {
  view: "form",
  prompt: "",
  fps: DEFAULT_FPS,
  upstreamStyle: "minimal_dark_bar",
  error: null,
  result: null,
  generationTimeMs: null,
};

function reducer(state, action) {
  switch (action.type) {
    case "SET_PROMPT":
      return { ...state, prompt: action.payload };
    case "SET_FPS":
      return { ...state, fps: action.payload };
    case "SET_STYLE":
      return { ...state, upstreamStyle: action.payload };
    case "START_GENERATION":
      return { ...state, view: "loading", error: null, result: null };
    case "GENERATION_SUCCESS":
      return {
        ...state,
        view: "result",
        result: action.payload.result,
        generationTimeMs: action.payload.generationTimeMs,
      };
    case "GENERATION_ERROR":
      return { ...state, view: "form", error: action.payload };
    case "RESET":
      return { ...initialState };
    default:
      return state;
  }
}

export default function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const abortRef = useRef(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!state.prompt.trim()) return;

    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    dispatch({ type: "START_GENERATION" });
    const startTime = Date.now();

    try {
      const res = await fetch(`${API_BASE}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          prompt: state.prompt,
          upstream_signals: { style: state.upstreamStyle },
          project_fps: state.fps,
          tts_timestamps: null,
          instance_id: null,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        dispatch({
          type: "GENERATION_ERROR",
          payload: data.error ?? "An unexpected error occurred",
        });
        return;
      }

      dispatch({
        type: "GENERATION_SUCCESS",
        payload: { result: data, generationTimeMs: Date.now() - startTime },
      });
    } catch (err) {
      if (err.name === "AbortError") return;
      const isNetworkError =
        err.message?.toLowerCase().includes("fetch") ||
        err instanceof TypeError;
      dispatch({
        type: "GENERATION_ERROR",
        payload: isNetworkError
          ? `Network error — is the backend running at ${API_BASE}?`
          : "An unexpected error occurred",
      });
    }
  }

  if (state.view === "loading") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4">
        <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-xl font-semibold">Generating lower third...</p>
        <p className="text-gray-400 text-sm">
          This may take 30–60 seconds on first render
        </p>
      </div>
    );
  }

  if (state.view === "result") {
    const { result, generationTimeMs } = state;
    return (
      <div className="max-w-3xl mx-auto px-6 py-10 flex flex-col gap-8">
        <h2 className="text-2xl font-bold">Preview</h2>

        <video
          src={API_BASE + result.video_url}
          controls
          loop={result.manifest?.loop === true}
          className="w-full rounded-lg bg-black"
        />

        <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-gray-400">
          <span>Instance:</span>
          <span className="text-white font-mono">{result.instance_id}</span>
          <span>Time:</span>
          <span className="text-white font-mono">{generationTimeMs}ms</span>
          <span>Cache:</span>
          <span className="text-white font-mono">{result.cache_hit ? "HIT" : "MISS"}</span>
          <span>QC:</span>
          <span className={result.qc_passed ? "text-green-400" : "text-red-400"}>{result.qc_passed ? "✓ Passed" : "✗ Failed"}</span>
        </div>

        {result.qc_warnings?.length > 0 && (
          <div className="flex flex-col gap-2">
            {result.qc_warnings.map((w, i) => (
              <div
                key={i}
                className="border border-yellow-500 bg-yellow-900/30 text-yellow-300 rounded px-4 py-2 text-sm"
              >
                {w}
              </div>
            ))}
          </div>
        )}

        <h2 className="text-2xl font-bold">Manifest</h2>
        <pre className="bg-gray-900 rounded-lg p-4 text-xs font-mono overflow-auto max-h-96 text-gray-200">
          {JSON.stringify(
            (({ instance_id: _, ...rest }) => rest)(result.manifest ?? {}),
            null,
            2,
          )}
        </pre>

        <button
          onClick={() => dispatch({ type: "RESET" })}
          className="self-start bg-blue-600 hover:bg-blue-700 text-white font-semibold px-6 py-2 rounded-lg transition-colors"
        >
          Generate Another
        </button>
      </div>
    );
  }

  // form view
  return (
    <div className="max-w-2xl mx-auto px-6 py-10 flex flex-col gap-6">
      <h1 className="text-3xl font-bold">Lower Third Generator</h1>

      {state.error && (
        <div className="border border-red-500 bg-red-900/30 text-red-300 rounded px-4 py-3 text-sm">
          {state.error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <textarea
          rows={4}
          className="w-full bg-gray-800 border border-gray-600 rounded-lg px-4 py-3 text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500 resize-y"
          placeholder="Describe the lower third animation you want..."
          value={state.prompt}
          onChange={(e) =>
            dispatch({ type: "SET_PROMPT", payload: e.target.value })
          }
        />

        <div className="flex gap-4">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-400 uppercase tracking-wide">
              FPS
            </label>
            <select
              className="bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-gray-100 focus:outline-none focus:border-blue-500"
              value={state.fps}
              onChange={(e) =>
                dispatch({ type: "SET_FPS", payload: Number(e.target.value) })
              }
            >
              <option value={24}>24</option>
              <option value={25}>25</option>
              <option value={30}>30</option>
            </select>
          </div>

          <div className="flex flex-col gap-1 flex-1">
            <label className="text-xs text-gray-400 uppercase tracking-wide">
              Style
            </label>
            <select
              className="bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-gray-100 focus:outline-none focus:border-blue-500"
              value={state.upstreamStyle}
              onChange={(e) =>
                dispatch({ type: "SET_STYLE", payload: e.target.value })
              }
            >
              <option value="minimal_dark_bar">minimal_dark_bar</option>
              <option value="bold_red_bar">bold_red_bar</option>
              <option value="bold_blue_bar">bold_blue_bar</option>
              <option value="bold_green_bar">bold_green_bar</option>
            </select>
          </div>
        </div>

        <button
          type="submit"
          disabled={!state.prompt.trim()}
          className="bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold px-6 py-2 rounded-lg transition-colors self-start"
        >
          Generate
        </button>
      </form>
    </div>
  );
}
