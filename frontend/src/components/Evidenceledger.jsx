import React, { useState } from "react";

// Expects:
// scoreResult = { score, breakdown: [{jd_requirement, matched, matched_resume_line, confidence}], missing_skills }
// bulletResults = [{ bulletText, approved, unsupported_claims, claim_matches }]

export default function EvidenceLedger({ scoreResult, bulletResults }) {
  const [activeCitation, setActiveCitation] = useState(null);
  const [expandedSources, setExpandedSources] = useState({});

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-8">
      {/* ---- Fit Score ---- */}
      <section className="border rounded-lg p-5 bg-white shadow-sm">
        <div className="flex items-baseline justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-800">Fit Score</h2>
          <span className="text-4xl font-bold text-indigo-600">{scoreResult.score}</span>
        </div>

        <div className="space-y-2">
          {scoreResult.breakdown.map((item, i) => (
            <div
              key={i}
              className={`flex items-start justify-between p-3 rounded-md border ${
                item.matched ? "border-green-200 bg-green-50" : "border-red-200 bg-red-50"
              }`}
            >
              <div className="flex-1">
                <p className="font-medium text-sm text-gray-800">{item.jd_requirement}</p>
                {item.matched ? (
                  <button
                    onClick={() => setActiveCitation(item.matched_resume_line)}
                    className="text-xs text-indigo-600 underline mt-1"
                  >
                    View evidence
                  </button>
                ) : (
                  <p className="text-xs text-red-600 mt-1">No match found in resume</p>
                )}
              </div>
              <span className={`text-lg ${item.matched ? "text-green-600" : "text-red-500"}`}>
                {item.matched ? "✓" : "✗"}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* ---- Citation popover ---- */}
      {activeCitation && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-gray-900 text-white text-sm px-4 py-3 rounded-lg shadow-lg max-w-md">
          <p className="text-gray-300 text-xs mb-1">Source line in resume:</p>
          <p>"{activeCitation}"</p>
          <button
            onClick={() => setActiveCitation(null)}
            className="text-xs text-gray-400 mt-2 underline"
          >
            Close
          </button>
        </div>
      )}

      {/* ---- Tailored Bullets ---- */}
      <section className="border rounded-lg p-5 bg-white shadow-sm">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Tailored Bullets</h2>
        {bulletResults.length === 0 ? (
          <p className="text-sm text-gray-500 italic">
            No tailored bullets generated for this run.
          </p>
        ) : (
          <div className="space-y-4">
            {bulletResults.map((b, i) => (
            <div
              key={i}
              className={`p-4 rounded-md border ${
                b.approved ? "border-green-200 bg-green-50" : "border-red-200 bg-red-50"
              }`}
            >
              <p className="text-sm text-gray-800 mb-2">{b.bulletText}</p>

              {b.approved ? (
                <span className="text-xs font-medium text-green-700">
                  ✓ Verified against resume
                </span>
              ) : (
                <div>
                  <span className="text-xs font-medium text-red-700 block mb-1">
                    ✗ Rejected — unsupported claim(s)
                  </span>
                  <div className="flex flex-wrap gap-1">
                    {b.unsupported_claims.map((c, j) => (
                      <span
                        key={j}
                        className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded"
                      >
                        {c}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Keep the ledger calm: show only the three clearest sources first. */}
              {(() => {
                const supportedClaims = b.claim_matches?.filter(
                  (cm) => cm.supported && cm.best_match_sentence,
                ) || [];
                const topClaims = supportedClaims
                  .filter((cm) => cm.claim.split(" ").length <= 2)
                  .slice(0, 3);
                const visibleClaims = expandedSources[i] ? supportedClaims : topClaims;

                return (
                  <>
                    {visibleClaims.map((cm, k) => (
                  <button
                    key={k}
                    onClick={() => setActiveCitation(cm.best_match_sentence)}
                    className="text-xs text-indigo-600 underline mr-2 mt-2 inline-block"
                  >
                    "{cm.claim}" source
                  </button>
                    ))}
                    {supportedClaims.length > 3 && (
                      <button
                        onClick={() => setExpandedSources((current) => ({
                          ...current,
                          [i]: !current[i],
                        }))}
                        className="text-xs text-gray-400 underline ml-2 mt-2 inline-block"
                      >
                        {expandedSources[i]
                          ? "Show fewer sources"
                          : `+${supportedClaims.length - 3} more sources`}
                      </button>
                    )}
                  </>
                );
              })()}
            </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}