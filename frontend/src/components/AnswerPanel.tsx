import type { QueryResponse } from "../types/api";

export default function AnswerPanel({ answer }: { answer: QueryResponse | null }) {
  if (!answer) return null;
  return (
    <section className="panel answerPanel">
      <span className="eyebrow">Answer</span>
      {answer.error && <p className="warning">Gemini failed, but retrieved evidence is still shown.</p>}
      <p className="answerText">{answer.answer}</p>
      <div className="answerStats">
        <div>
          <strong>{Math.round(answer.confidence * 100)}%</strong>
          <span>Confidence</span>
        </div>
        <div>
          <strong>{answer.used_modalities.length ? answer.used_modalities.join(" · ") : "Evidence"}</strong>
          <span>Evidence used</span>
        </div>
      </div>
    </section>
  );
}
