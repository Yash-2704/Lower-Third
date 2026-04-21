import { useReducer, useRef } from "react";

const API_BASE = "http://localhost:8001";

const STAGES = [
  { id: "brand_resolve", label: "Brand Resolution" },
  { id: "llm_parse", label: "Parsing Prompt (LLM)" },
  { id: "cache_check", label: "Cache Check" },
  { id: "geometry", label: "Geometric Corrections" },
  { id: "interpolation", label: "Frame Interpolation" },
  { id: "render", label: "Rendering Frames" },
  { id: "encode", label: "Encoding Video" },
  { id: "qc", label: "Quality Check" },
  { id: "manifest", label: "Writing Manifest" },
];

const initialState = {
  view: "form",
  prompt: "",
  durationValue: 30,
  durationUnit: "seconds",
  error: null,
  result: null,
  generationTimeMs: null,
  completedStages: new Set(),
  activeStage: null,
};

function reducer(state, action) {
  switch (action.type) {
    case "SET_PROMPT":
      return { ...state, prompt: action.value };
    case "SET_DURATION_VALUE":
      return { ...state, durationValue: action.value };
    case "SET_DURATION_UNIT":
      return { ...state, durationUnit: action.value };
    case "START_GENERATION":
      return {
        ...state,
        view: "loading",
        error: null,
        result: null,
        completedStages: new Set(),
        activeStage: STAGES[0].id,
      };
    case "STAGE_COMPLETE":
      return {
        ...state,
        completedStages: new Set([...state.completedStages, action.stage]),
        activeStage: action.nextStage ?? null,
      };
    case "GENERATION_SUCCESS":
      return {
        ...state,
        view: "result",
        result: action.result,
        generationTimeMs: action.generationTimeMs,
        activeStage: null,
      };
    case "GENERATION_ERROR":
      return { ...state, view: "form", error: action.error, activeStage: null };
    case "RESET":
      return { ...initialState };
    default:
      return state;
  }
}

function durationMs(value, unit) {
  return value * (unit === "minutes" ? 60_000 : 1_000);
}

export default function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const abortRef = useRef(null);
  const startTimeRef = useRef(null);

  async function handleGenerate() {
    if (!state.prompt.trim()) return;
    if (abortRef.current) abortRef.current.abort();

    const controller = new AbortController();
    abortRef.current = controller;
    startTimeRef.current = Date.now();

    dispatch({ type: "START_GENERATION" });

    try {
      const res = await fetch(`${API_BASE}/generate/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          prompt: state.prompt,
          upstream_signals: {},
          total_duration_ms: durationMs(state.durationValue, state.durationUnit),
          tts_timestamps: null,
          instance_id: null,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: res.statusText }));
        dispatch({ type: "GENERATION_ERROR", error: err.error ?? "Unknown error" });
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = JSON.parse(line.slice(6));

          if (payload.error) {
            dispatch({ type: "GENERATION_ERROR", error: payload.error });
            return;
          }

          if (payload.result) {
            dispatch({
              type: "GENERATION_SUCCESS",
              result: payload.result,
              generationTimeMs: Date.now() - startTimeRef.current,
            });
            return;
          }

          if (payload.stage) {
            const idx = STAGES.findIndex((s) => s.id === payload.stage);
            const nextStage = STAGES[idx + 1]?.id ?? null;
            dispatch({ type: "STAGE_COMPLETE", stage: payload.stage, nextStage });
          }
        }
      }
    } catch (e) {
      if (e.name !== "AbortError") {
        dispatch({ type: "GENERATION_ERROR", error: e.message });
      }
    }
  }

  if (state.view === "loading") {
    return (
      <div className="min-h-screen bg-gray-950 text-white flex flex-col items-center justify-center p-8">
        <h1 className="text-2xl font-bold mb-8">Generating lower third…</h1>
        <div className="w-full max-w-md space-y-3">
          {STAGES.map((s) => {
            const done = state.completedStages.has(s.id);
            const active = state.activeStage === s.id;
            return (
              <div
                key={s.id}
                className={`flex items-center gap-3 p-3 rounded-lg border transition-all ${
                  done
                    ? "border-green-700 bg-green-950/40"
                    : active
                    ? "border-blue-500 bg-blue-950/40"
                    : "border-gray-700 bg-gray-900/40"
                }`}
              >
                <span className="w-6 text-center">
                  {done ? (
                    <span className="text-green-400">✓</span>
                  ) : active ? (
                    <span className="inline-block w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <span className="text-gray-600">○</span>
                  )}
                </span>
                <span
                  className={`text-sm font-medium ${
                    done
                      ? "text-green-300 line-through decoration-green-600"
                      : active
                      ? "text-blue-300"
                      : "text-gray-500"
                  }`}
                >
                  {s.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  if (state.view === "result") {
    const { result } = state;
    return (
      <div className="min-h-screen bg-gray-950 text-white flex flex-col items-center justify-center p-8 gap-6">
        <h1 className="text-3xl font-bold">Lower Third Generated</h1>
        <div className="w-full max-w-2xl bg-gray-900 rounded-xl p-6 flex flex-col gap-4">
          <video
            src={API_BASE + result.video_url}
            controls
            loop={result.manifest?.loop === true}
            className="w-full rounded-lg bg-black"
          />
          <div className="grid grid-cols-2 gap-2 text-sm text-gray-300">
            <span className="text-gray-500">Instance ID</span>
            <span className="font-mono">{result.instance_id}</span>
            <span className="text-gray-500">Generation time</span>
            <span>{state.generationTimeMs} ms</span>
            <span className="text-gray-500">Cache hit</span>
            <span>{result.cache_hit ? "Yes" : "No"}</span>
            <span className="text-gray-500">QC passed</span>
            <span className={result.qc_passed ? "text-green-400" : "text-red-400"}>
              {result.qc_passed ? "Yes" : "No"}
            </span>
          </div>
          {result.qc_warnings?.length > 0 && (
            <div className="space-y-1">
              {result.qc_warnings.map((w, i) => (
                <div key={i} className="text-yellow-300 text-xs bg-yellow-900/30 border border-yellow-700 rounded px-3 py-2">
                  {w}
                </div>
              ))}
            </div>
          )}
          <details className="text-xs">
            <summary className="cursor-pointer text-gray-400 mb-2">Manifest</summary>
            <pre className="bg-gray-800 rounded p-3 overflow-auto max-h-96 text-gray-300">
              {JSON.stringify(
                Object.fromEntries(
                  Object.entries(result.manifest).filter(([k]) => k !== "instance_id")
                ),
                null,
                2
              )}
            </pre>
          </details>
          <button
            onClick={() => dispatch({ type: "RESET" })}
            className="mt-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg font-semibold transition-colors"
          >
            Generate Another
          </button>
        </div>
      </div>
    );
  }

  // Form view — two-column layout
  return (
    <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center p-8">
      <div className="w-full max-w-5xl grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Left: inputs */}
        <div className="flex flex-col gap-5">
          <div>
            <h1 className="text-3xl font-bold mb-1">Lower Third Generator</h1>
            <p className="text-gray-400 text-sm">Describe the lower third you want to create.</p>
          </div>

          {state.error && (
            <div className="text-red-400 bg-red-950/40 border border-red-700 rounded-lg px-4 py-3 text-sm">
              {state.error}
            </div>
          )}

          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium text-gray-300">Prompt</label>
            <textarea
              rows={5}
              placeholder="e.g. John Smith, CEO of Acme Corp, blue bar, slide in from left"
              value={state.prompt}
              onChange={(e) => dispatch({ type: "SET_PROMPT", value: e.target.value })}
              className="bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 text-sm text-white placeholder-gray-600 resize-none focus:outline-none focus:border-blue-500 transition-colors"
            />
          </div>

          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium text-gray-300">Duration</label>
            <div className="flex gap-2">
              <input
                type="number"
                min="1"
                value={state.durationValue}
                onChange={(e) =>
                  dispatch({ type: "SET_DURATION_VALUE", value: Math.max(1, Number(e.target.value)) })
                }
                className="w-24 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 transition-colors"
              />
              <select
                value={state.durationUnit}
                onChange={(e) => dispatch({ type: "SET_DURATION_UNIT", value: e.target.value })}
                className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 transition-colors"
              >
                <option value="seconds">Seconds</option>
                <option value="minutes">Minutes</option>
              </select>
            </div>
          </div>

          <button
            onClick={handleGenerate}
            disabled={!state.prompt.trim()}
            className="px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:cursor-not-allowed rounded-lg font-semibold transition-colors"
          >
            Generate
          </button>
        </div>

        {/* Right: example output */}
        <div className="flex flex-col gap-3">
          <p className="text-sm font-medium text-gray-300">Example output</p>
          <video
            src={`${API_BASE}/assets/lt_0af2ce67.webm`}
            autoPlay
            muted
            loop
            playsInline
            className="w-full rounded-xl bg-black border border-gray-800"
          />
          <p className="text-xs text-gray-600 text-center">Sample lower third animation</p>
        </div>
      </div>
    </div>
  );
}
