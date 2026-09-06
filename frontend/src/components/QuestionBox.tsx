interface Props {
  question: string;
  disabled: boolean;
  loading: boolean;
  onChange: (value: string) => void;
  onAsk: () => void;
}

const SUGGESTED_QUESTIONS = [
  "What are the key events in this source?",
  "Which visual evidence supports the answer?",
  "Summarize the timeline with citations."
];

export default function QuestionBox({ question, disabled, loading, onChange, onAsk }: Props) {
  return (
    <section className="panel">
      <div className="sectionHeader">
        <div>
          <span className="eyebrow">Question</span>
          <h2>Ask The Source</h2>
        </div>
        <span className="muted">{question.trim().length} chars</span>
      </div>
      <textarea value={question} disabled={disabled} onChange={(event) => onChange(event.target.value)} />
      <div className="questionActions">
        <div className="suggestedQuestions">
          {SUGGESTED_QUESTIONS.map((suggestion) => (
            <button key={suggestion} className="compactButton" disabled={disabled || loading} onClick={() => onChange(suggestion)} type="button">
              {suggestion}
            </button>
          ))}
        </div>
        <button className="primaryButton" disabled={disabled || loading || !question.trim()} onClick={onAsk}>
          {loading ? "Asking..." : "Ask"}
        </button>
      </div>
    </section>
  );
}
