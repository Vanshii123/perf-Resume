import React, { useEffect, useState } from "react";
import EvidenceLedger from "./components/Evidenceledger";

const STAGES = [
  { id: "reading", label: "Reading JD" },
  { id: "extracting", label: "Extracting Requirements" },
  { id: "parsing", label: "Parsing Resume" },
  { id: "scoring", label: "Scoring Fit" },
  { id: "generating", label: "Generating Bullets" },
  { id: "verifying", label: "Verifying Claims" },
  { id: "complete", label: "Complete" },
];

function PipelineVisualizer({ activeStage }) {
  const activeIndex = STAGES.findIndex((stage) => stage.id === activeStage);

  return (
    <div className="overflow-x-auto mb-6" aria-label="Analysis pipeline">
      <div className="flex items-start min-w-max px-1 py-2">
        {STAGES.map((stage, index) => {
          const isDone = index < activeIndex;
          const isActive = index === activeIndex;
          const stateClass = isDone
            ? "border-green-600 bg-green-50 text-green-700"
            : isActive
              ? "border-indigo-600 bg-indigo-50 text-indigo-600 animate-pulse scale-110"
              : "border-gray-300 bg-gray-50 text-gray-400";

          return (
            <React.Fragment key={stage.id}>
              <div className="flex w-32 flex-col items-center text-center">
                <div className={`flex h-8 w-8 items-center justify-center rounded-full border-2 text-sm font-semibold ${stateClass}`}>
                  {isDone ? "✓" : index + 1}
                </div>
                <span className="mt-2 text-xs font-medium">{stage.label}</span>
              </div>
              {index < STAGES.length - 1 && (
                <div className={`mt-4 h-0.5 w-10 shrink-0 ${index < activeIndex ? "bg-green-600" : "bg-gray-300"}`} />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}

export default function App() {
  const [jdText, setJdText] = useState("");
  const [resumeFile, setResumeFile] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeStage, setActiveStage] = useState(null);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!resumeFile || !jdText.trim()) return;

    setLoading(true);
    setError(null);
    setActiveStage("reading");
    setTimeout(() => setActiveStage("extracting"), 400);
    setTimeout(() => setActiveStage("parsing"), 900);
    setTimeout(() => setActiveStage("scoring"), 1400);
    setTimeout(() => setActiveStage("generating"), 1800);
    setTimeout(() => setActiveStage("verifying"), 2600);
    try {
      const formData = new FormData();
      formData.append("jd_text", jdText);
      formData.append("resume_file", resumeFile);

      const res = await fetch("http://15.252.146.6:8000/analyze", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Request failed (${res.status})`);
      }

      const data = await res.json();
      setResult(data);
      setActiveStage("complete");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">Resume Fit Verifier</h1>

      <form onSubmit={handleSubmit} className="space-y-4 mb-8">
        <textarea
          className="w-full border rounded-md p-3 text-sm"
          rows={6}
          placeholder="Paste job description here..."
          value={jdText}
          onChange={(e) => setJdText(e.target.value)}
        />
        <input
          type="file"
          accept=".pdf"
          onChange={(e) => setResumeFile(e.target.files[0])}
          className="text-sm"
        />
        <button
          type="submit"
          disabled={loading}
          className="bg-indigo-600 text-white px-4 py-2 rounded-md text-sm disabled:opacity-50"
        >
          {loading ? (
            <span className="flex items-center gap-1.5" aria-label="Analyzing">
              <span className="h-2 w-2 rounded-full bg-white animate-pulse" />
              <span className="h-2 w-2 rounded-full bg-white animate-pulse" />
              <span className="h-2 w-2 rounded-full bg-white animate-pulse" />
            </span>
          ) : "Analyze Fit"}
        </button>
      </form>

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      {loading && <PipelineVisualizer activeStage={activeStage} />}

      {result && (
        <ResultsBoundary
          fallback={
            <EvidenceLedger
              scoreResult={result.scoreResult}
              bulletResults={result.bulletResults}
            />
          }
        >
          <EnhancedResults result={result} />
        </ResultsBoundary>
      )}
    </div>
  );
}

function ScoreRing({ score }) {
  const [displayScore, setDisplayScore] = useState(0);
  const radius = 48;
  const circumference = 2 * Math.PI * radius;
  const color = score < 40 ? "#ef4444" : score <= 70 ? "#f59e0b" : "#10b981";

  useEffect(() => {
    const startedAt = performance.now();
    let frameId;

    const animate = (now) => {
      const progress = Math.min((now - startedAt) / 800, 1);
      const eased = 1 - (1 - progress) ** 3;
      setDisplayScore(Math.round(score * eased));
      if (progress < 1) frameId = requestAnimationFrame(animate);
    };

    frameId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frameId);
  }, [score]);

  const offset = circumference - (displayScore / 100) * circumference;

  return (
    <div className="flex flex-col items-center" aria-label={`Fit Score ${displayScore}`}>
      <div className="relative h-30 w-30">
        <svg width="120" height="120" viewBox="0 0 120 120" className="-rotate-90">
          <circle cx="60" cy="60" r={radius} fill="none" stroke="#e5e7eb" strokeWidth="10" />
          <circle
            cx="60"
            cy="60"
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
          />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center text-2xl font-bold text-gray-800">
          {displayScore}
        </span>
      </div>
      <span className="mt-2 text-xs font-semibold uppercase tracking-wide text-gray-500">Fit Score</span>
    </div>
  );
}

function SkillBreakdown({ breakdown }) {
  return (
    <section className="border rounded-lg p-5 bg-white shadow-sm">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">Skills Breakdown</h2>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
        {breakdown.map((item, index) => {
          const evidence = item.matched_resume_line || "No matching evidence found";
          const trustClass = !item.matched
            ? "bg-red-50 text-red-700 border-red-200"
            : evidence.length > 20
              ? "bg-green-50 text-green-700 border-green-200"
              : "bg-yellow-50 text-yellow-700 border-yellow-200";
          const dotClass = !item.matched
            ? "bg-red-500"
            : evidence.length > 20
              ? "bg-green-500"
              : "bg-yellow-500";

          return (
            <div key={`${item.jd_requirement}-${index}`} className="relative group">
              <div className={`flex items-center justify-between rounded-full border px-3 py-1.5 text-sm font-medium ${trustClass}`}>
                <span>{item.jd_requirement}</span>
                <span className={`ml-2 h-2 w-2 rounded-full ${dotClass}`} aria-label="Evidence strength" />
              </div>
              <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-2 hidden w-56 -translate-x-1/2 rounded-md bg-gray-900 p-2 text-xs text-white shadow-lg group-hover:block">
                {evidence}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function BulletDiffView({ bulletResults }) {
  if (bulletResults.length === 0) {
    return (
      <section className="border rounded-lg p-5 bg-white shadow-sm">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Tailored Bullets</h2>
        <p className="text-sm text-gray-500 italic">No tailored bullets generated for this run.</p>
      </section>
    );
  }

  return (
    <section className="border rounded-lg p-5 bg-white shadow-sm">
      <h2 className="text-lg font-semibold text-gray-800 mb-4">Tailored Bullets</h2>
      <div className="space-y-4">
        {bulletResults.map((bullet, index) => {
          const source = bullet.claim_matches?.find((claim) => claim.best_match_sentence)?.best_match_sentence;
          const sources = bullet.claim_matches?.filter((claim) => claim.supported && claim.claim).slice(0, 3) || [];

          return (
            <div key={index} className="grid gap-3 md:grid-cols-2 animate-in fade-in duration-500">
              <div className="rounded-md border border-gray-200 bg-gray-50 p-4">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">Original</p>
                <p className="text-sm text-gray-500 line-through">{source || "No source sentence available"}</p>
              </div>
              <div className="rounded-md border border-gray-200 border-l-4 border-l-green-500 bg-white p-4">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-green-700">Tailored</p>
                <p className="text-sm text-gray-800">{bullet.bulletText}</p>
                {bullet.approved ? (
                  <span className="mt-3 inline-block text-xs font-medium text-green-700">✓ Verified against resume</span>
                ) : (
                  <span className="mt-3 inline-block text-xs font-medium text-red-700">✗ Rejected claim</span>
                )}
                <div className="mt-2 flex flex-wrap gap-1">
                  {sources.map((claim, sourceIndex) => (
                    <span key={sourceIndex} className="rounded-full bg-green-50 px-2 py-0.5 text-xs text-green-700">
                      {claim.claim}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

class ResultsBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) return this.props.fallback;
    return this.props.children;
  }
}

function EnhancedResults({ result }) {
  const scoreResult = result.scoreResult;
  const bulletResults = result.bulletResults || [];

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <section className="border rounded-lg bg-white p-5 shadow-sm">
        <ScoreRing score={scoreResult.score} />
      </section>
      <SkillBreakdown breakdown={scoreResult.breakdown} />
      <BulletDiffView bulletResults={bulletResults} />
    </div>
  );
}
